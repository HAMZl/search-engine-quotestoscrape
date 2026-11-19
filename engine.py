"""Tokenizer, positional inverted index and ranked search.

The index maps every term to the pages it appears on and the token positions
inside each page::

    {"einstein": {"https://quotes.toscrape.com/author/Albert-Einstein/": [0, 41, 97]}}

Ranking works in three tiers, so nothing is ever enumerated exponentially:

1. **Coverage** - pages containing more of the distinct query words rank first
   (this replaces the old power-set expansion, which was O(2^n)).
2. **BM25** - classic relevance score that rewards rare words and normalises
   for page length, so long tag pages don't win just by being long.
3. **Proximity** - a boost based on the smallest window of text containing
   every matched query word.

Quoted phrases (``"nothing is a miracle"``) are required to appear as
consecutive indexed tokens.
"""

from __future__ import annotations

import bisect
import difflib
import heapq
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

INDEX_VERSION = 2
DEFAULT_INDEX_PATH = Path(__file__).resolve().with_name("inverted_index.json")

# BM25 parameters (standard defaults).
BM25_K1 = 1.2
BM25_B = 0.75
# Extra weight (in units of the word's IDF) when a query word is in the page
# title, so "albert einstein" finds Einstein's author page and not just the
# shortest page that mentions him.
TITLE_WEIGHT = 2.0

# Snippet sizing, measured in indexed tokens (stopwords are not counted).
SNIPPET_CONTEXT = 10
SNIPPET_MAX_WINDOW = 30

STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "ain", "all", "am", "an",
    "and", "any", "are", "aren", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "couldn", "d", "did",
    "didn", "do", "does", "doesn", "doing", "don", "down", "during", "each", "few",
    "for", "from", "further", "had", "hadn", "has", "hasn", "have", "haven",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "isn", "it", "its", "itself", "just",
    "ll", "m", "ma", "me", "mightn", "more", "most", "mustn", "my", "myself",
    "needn", "no", "nor", "not", "now", "o", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "re", "s",
    "same", "shan", "she", "should", "shouldn", "so", "some", "such", "t", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "ve", "very", "was", "wasn", "we", "were", "weren", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with", "won",
    "wouldn", "y", "you", "your", "yours", "yourself", "yourselves",
})
# Note: contractions such as "don't" never need listing - the tokenizer splits
# on the apostrophe, producing "don" and "t", which are both listed above.

_WORD_RE = re.compile(r"\w+")
_PHRASE_RE = re.compile(r'"([^"]*)"')


# --------------------------------------------------------------------------- #
# Tokenizing
# --------------------------------------------------------------------------- #

def iter_tokens(text: str) -> Iterator[tuple[str, int, int]]:
    """Yield ``(token, start, end)`` for every indexable word in *text*.

    A token is a purely alphabetic word, lower-cased, that is not a stopword.
    A token's *position* is its index in this sequence; ``start``/``end`` are
    character offsets into the original text (used to build snippets).
    """
    for match in _WORD_RE.finditer(text):
        word = match.group()
        if not word.isalpha():
            continue
        word = word.lower()  # lower-case *before* the stopword check
        if word in STOP_WORDS:
            continue
        yield word, match.start(), match.end()


def word_tokenizer(text: str) -> list[str]:
    """Return the indexable tokens of *text* in order."""
    return [token for token, _, _ in iter_tokens(text)]


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #

class IndexFormatError(ValueError):
    """Raised when an index file is missing fields or uses an old format."""


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    text: str
    length: int  # number of indexed tokens


@dataclass(frozen=True)
class ParsedQuery:
    terms: tuple[str, ...]                 # distinct tokens, in query order
    phrases: tuple[tuple[str, ...], ...]   # quoted phrases with 2+ tokens


@dataclass(frozen=True)
class Segment:
    text: str
    hit: bool


@dataclass
class SearchResult:
    url: str
    title: str
    score: float
    matched_terms: tuple[str, ...]
    frequency: int              # total occurrences of the matched terms
    window: int | None          # tokens spanned by all matched terms (2+ terms)
    span: tuple[int, int]       # token positions of that window
    complete: bool              # True if every known query term matched
    snippet: list[Segment] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        del data["span"]
        data["score"] = round(self.score, 4)
        return data


@dataclass
class SearchResponse:
    query: str
    terms: tuple[str, ...] = ()
    phrases: tuple[tuple[str, ...], ...] = ()
    unknown_terms: tuple[str, ...] = ()
    suggestions: dict[str, str] = field(default_factory=dict)
    total: int = 0
    offset: int = 0
    limit: int = 10
    results: list[SearchResult] = field(default_factory=list)

    @property
    def suggested_query(self) -> str | None:
        """The query with misspelt words replaced, or None if nothing to fix."""
        if not self.suggestions:
            return None
        return " ".join(self.suggestions.get(term, term) for term in self.terms)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "terms": list(self.terms),
            "phrases": [" ".join(p) for p in self.phrases],
            "unknown_terms": list(self.unknown_terms),
            "suggestions": self.suggestions,
            "suggested_query": self.suggested_query,
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "results": [r.to_dict() for r in self.results],
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def parse_query(query: str) -> ParsedQuery:
    """Split a raw query into distinct terms and quoted phrases."""
    phrases = []
    for match in _PHRASE_RE.finditer(query):
        tokens = tuple(word_tokenizer(match.group(1)))
        if len(tokens) >= 2 and tokens not in phrases:
            phrases.append(tokens)
    terms = _dedupe(word_tokenizer(query.replace('"', " ")))
    return ParsedQuery(tuple(terms), tuple(phrases))


def min_window(position_lists: Sequence[Sequence[int]]) -> tuple[int, int]:
    """Smallest ``(first, last)`` range containing one position from every list.

    Each list must be sorted ascending and non-empty. Runs in O(P log k) where P
    is the total number of positions and k the number of lists.
    """
    heap = [(positions[0], i, 0) for i, positions in enumerate(position_lists)]
    heapq.heapify(heap)
    high = max(positions[0] for positions in position_lists)
    best = (heap[0][0], high)
    while True:
        low, i, j = heapq.heappop(heap)
        if high - low < best[1] - best[0]:
            best = (low, high)
        if j + 1 == len(position_lists[i]):
            return best
        nxt = position_lists[i][j + 1]
        high = max(high, nxt)
        heapq.heappush(heap, (nxt, i, j + 1))


def build_postings(documents: dict[str, Document]) -> dict[str, dict[str, list[int]]]:
    """Build ``{term: {url: [positions]}}`` from the documents' text."""
    postings: dict[str, dict[str, list[int]]] = {}
    for url, doc in documents.items():
        for position, token in enumerate(word_tokenizer(doc.text)):
            postings.setdefault(token, {}).setdefault(url, []).append(position)
    return postings


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #

class SearchIndex:
    def __init__(
        self,
        documents: dict[str, Document],
        postings: dict[str, dict[str, list[int]]] | None = None,
        built_at: str | None = None,
    ):
        self.documents = documents
        self.postings = postings if postings is not None else build_postings(documents)
        self.built_at = built_at
        total = sum(doc.length for doc in documents.values())
        self.total_tokens = total
        self.avg_length = (total / len(documents)) if documents else 1.0
        self._vocabulary = sorted(self.postings)
        self._title_terms = {url: set(word_tokenizer(d.title)) for url, d in documents.items()}

    # ---- construction / persistence ------------------------------------- #

    @classmethod
    def from_pages(
        cls, pages: Iterable[tuple[str, str, str]], built_at: str | None = None
    ) -> "SearchIndex":
        """Build an index from ``(url, title, text)`` tuples."""
        documents = {
            url: Document(url, title, text, len(word_tokenizer(text)))
            for url, title, text in pages
        }
        return cls(documents, built_at=built_at)

    @classmethod
    def load(cls, path: str | os.PathLike = DEFAULT_INDEX_PATH) -> "SearchIndex":
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or data.get("version") != INDEX_VERSION:
            raise IndexFormatError(
                f"{path} uses an old or unknown index format. "
                "Rebuild it with: python search.py build"
            )
        try:
            documents = {
                url: Document(url, d["title"], d["text"], d["length"])
                for url, d in data["documents"].items()
            }
            postings = data["postings"]
        except (KeyError, TypeError, AttributeError) as exc:
            raise IndexFormatError(f"{path} is malformed: {exc!r}") from exc
        return cls(documents, postings, built_at=data.get("built_at"))

    def save(self, path: str | os.PathLike = DEFAULT_INDEX_PATH) -> None:
        """Write the index as compact JSON, atomically (no half-written files)."""
        data = {
            "version": INDEX_VERSION,
            "built_at": self.built_at,
            "documents": {
                url: {"title": d.title, "text": d.text, "length": d.length}
                for url, d in self.documents.items()
            },
            "postings": self.postings,
        }
        path = Path(path)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise

    # ---- inspection ------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def vocabulary(self) -> list[str]:
        return self._vocabulary

    def lookup(self, word: str) -> tuple[str | None, dict[str, list[int]]]:
        """Return ``(term, postings)`` for a single user-supplied word.

        ``term`` is None when the word is a stopword or not a word at all.
        """
        tokens = word_tokenizer(word)
        if not tokens:
            return None, {}
        return tokens[0], self.postings.get(tokens[0], {})

    def top_terms(self, limit: int = 20) -> list[tuple[str, int]]:
        """Most widespread terms as ``(term, number_of_pages)``."""
        counts = ((term, len(pages)) for term, pages in self.postings.items())
        return heapq.nlargest(limit, counts, key=lambda item: (item[1], item[0]))

    def complete(self, prefix: str, limit: int = 8) -> list[str]:
        """Vocabulary terms starting with *prefix*, most widespread first."""
        prefix = prefix.lower()
        if not prefix:
            return []
        start = bisect.bisect_left(self._vocabulary, prefix)
        matches = []
        for term in self._vocabulary[start:]:
            if not term.startswith(prefix):
                break
            matches.append(term)
        matches.sort(key=lambda t: (-len(self.postings[t]), t))
        return matches[:limit]

    def suggest(self, term: str) -> str | None:
        """Closest known spelling of an unknown term, if any is close enough."""
        matches = difflib.get_close_matches(term, self._vocabulary, n=1, cutoff=0.75)
        return matches[0] if matches else None

    def stats(self) -> dict:
        return {
            "pages": len(self.documents),
            "terms": len(self.postings),
            "tokens": self.total_tokens,
            "built_at": self.built_at,
        }

    # ---- searching ------------------------------------------------------- #

    def search(self, query: str, limit: int = 10, offset: int = 0) -> SearchResponse:
        parsed = parse_query(query)
        known = [t for t in parsed.terms if t in self.postings]
        unknown = [t for t in parsed.terms if t not in self.postings]
        suggestions = {t: s for t in unknown if (s := self.suggest(t))}
        response = SearchResponse(
            query=query,
            terms=parsed.terms,
            phrases=parsed.phrases,
            unknown_terms=tuple(unknown),
            suggestions=suggestions,
            offset=offset,
            limit=limit,
        )
        if not known:
            return response
        # A phrase containing an unknown word can never match.
        if any(t not in self.postings for phrase in parsed.phrases for t in phrase):
            return response

        candidates: set[str] = set()
        for term in known:
            candidates.update(self.postings[term])
        for phrase in parsed.phrases:
            candidates = {url for url in candidates if self._has_phrase(url, phrase)}

        results = [self._score(url, known) for url in candidates]
        results.sort(key=lambda r: (-len(r.matched_terms), -r.score, r.url))
        response.total = len(results)
        response.results = results[offset:offset + limit]
        for result in response.results:
            result.snippet = self._snippet(result)
        return response

    def _has_phrase(self, url: str, phrase: tuple[str, ...]) -> bool:
        lists = [self.postings[t].get(url) for t in phrase]
        if any(positions is None for positions in lists):
            return False
        following = [set(positions) for positions in lists[1:]]
        return any(
            all(start + i + 1 in positions for i, positions in enumerate(following))
            for start in lists[0]
        )

    def _score(self, url: str, terms: list[str]) -> SearchResult:
        doc = self.documents[url]
        n_docs = len(self.documents)
        matched = [t for t in terms if url in self.postings[t]]

        bm25 = 0.0
        frequency = 0
        for term in matched:
            tf = len(self.postings[term][url])
            df = len(self.postings[term])
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            norm = 1 - BM25_B + BM25_B * doc.length / self.avg_length
            bm25 += idf * tf * (BM25_K1 + 1) / (tf + BM25_K1 * norm)
            if term in self._title_terms[url]:
                bm25 += TITLE_WEIGHT * idf
            frequency += tf

        span = min_window([self.postings[t][url] for t in matched])
        if len(matched) > 1:
            window = span[1] - span[0] + 1
            proximity = len(matched) / window  # 1.0 when the words are adjacent
        else:
            window = None
            proximity = 0.0

        return SearchResult(
            url=url,
            title=doc.title,
            score=bm25 * (1 + proximity),
            matched_terms=tuple(matched),
            frequency=frequency,
            window=window,
            span=span,
            complete=len(matched) == len(terms),
        )

    def _snippet(self, result: SearchResult) -> list[Segment]:
        """A short excerpt around the best match, split into plain/hit segments."""
        text = self.documents[result.url].text
        tokens = list(iter_tokens(text))
        if not tokens:
            return [Segment(text[:200], False)] if text else []

        low, high = result.span
        if high - low > SNIPPET_MAX_WINDOW:  # words too far apart: show the first
            high = low
        first = max(0, low - SNIPPET_CONTEXT)
        last = min(len(tokens) - 1, high + SNIPPET_CONTEXT)
        start = tokens[first][1] if first > 0 else 0
        end = tokens[last][2] if last < len(tokens) - 1 else len(text)

        hits = set(result.matched_terms)
        segments: list[Segment] = []
        cursor = start
        for token, tok_start, tok_end in tokens[first:last + 1]:
            if token in hits:
                if tok_start > cursor:
                    segments.append(Segment(text[cursor:tok_start], False))
                segments.append(Segment(text[tok_start:tok_end], True))
                cursor = tok_end
        if end > cursor:
            segments.append(Segment(text[cursor:end], False))
        if start > 0:
            segments.insert(0, Segment("… ", False))
        if end < len(text):
            segments.append(Segment(" …", False))
        return segments
