import itertools
import json
import random
import time

import pytest

from engine import (
    INDEX_VERSION,
    IndexFormatError,
    SearchIndex,
    iter_tokens,
    min_window,
    parse_query,
    word_tokenizer,
)

# ---- tokenizer ------------------------------------------------------------ #

def test_stopwords_removed_regardless_of_case():
    assert word_tokenizer("The World is I") == ["world"]
    assert word_tokenizer("THE IT It") == []


def test_tokenizer_drops_numbers_and_splits_contractions():
    assert word_tokenizer("In 1879 he won't stop, R2D2!") == ["stop"]
    assert word_tokenizer("Don’t panic") == ["panic"]


def test_token_offsets_point_into_original_text():
    text = "Albert   EINSTEIN, physicist."
    for token, start, end in iter_tokens(text):
        assert text[start:end].lower() == token


# ---- query parsing -------------------------------------------------------- #

def test_parse_query_dedupes_terms_and_extracts_phrases():
    parsed = parse_query('love love "nothing is a miracle" "single" life')
    assert parsed.terms == ("love", "nothing", "miracle", "single", "life")
    assert parsed.phrases == (("nothing", "miracle"),)


def test_unbalanced_quote_is_ignored():
    assert parse_query('"love life').terms == ("love", "life")
    assert parse_query('"love life').phrases == ()


# ---- min_window ----------------------------------------------------------- #

def brute_force_window(lists):
    return min(
        (max(combo) - min(combo), (min(combo), max(combo)))
        for combo in itertools.product(*lists)
    )[0]


def test_min_window_matches_brute_force():
    rng = random.Random(0)
    for _ in range(200):
        lists = [sorted(rng.sample(range(60), rng.randint(1, 6))) for _ in range(rng.randint(1, 4))]
        low, high = min_window(lists)
        assert high - low == brute_force_window(lists)
        assert all(any(low <= p <= high for p in positions) for positions in lists)


# ---- index ---------------------------------------------------------------- #

def test_postings_record_positions(index):
    assert index.postings["einstein"]["https://q.test/author/einstein/"] == [1, 4, 8]
    assert "the" not in index.postings
    assert "is" not in index.postings


def test_lookup_reports_stopwords(index):
    assert index.lookup("The") == (None, {})
    term, postings = index.lookup("Einstein")
    assert term == "einstein" and len(postings) == 2


def test_save_and_load_roundtrip(index, tmp_path):
    path = tmp_path / "index.json"
    index.save(path)
    loaded = SearchIndex.load(path)
    assert loaded.postings == index.postings
    assert loaded.documents == index.documents
    assert loaded.built_at == index.built_at
    assert not list(tmp_path.glob("*.tmp"))


def test_old_index_format_is_rejected(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"love": {"https://x/": [0]}}), encoding="utf-8")
    with pytest.raises(IndexFormatError):
        SearchIndex.load(path)


def test_malformed_index_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": INDEX_VERSION, "documents": {"u": {}}}), encoding="utf-8")
    with pytest.raises(IndexFormatError):
        SearchIndex.load(path)


def test_complete_and_top_terms(index):
    assert index.complete("lo") == ["love", "loved"]
    assert index.complete("") == []
    assert index.complete("zzz") == []
    assert dict(index.top_terms(50))["life"] == 3


# ---- search --------------------------------------------------------------- #

def urls(response):
    return [r.url for r in response.results]


def test_unknown_word_does_not_abort_search(index):
    response = index.search("einstein xyzzy")
    assert response.unknown_terms == ("xyzzy",)
    assert set(urls(response)) == {"https://q.test/author/einstein/", "https://q.test/page/1/"}


def test_misspelling_gets_a_suggestion(index):
    response = index.search("einstien")
    assert response.suggestions == {"einstien": "einstein"}
    assert response.suggested_query == "einstein"


def test_pages_with_all_words_rank_first(index):
    response = index.search("love life humor")
    coverage = [len(r.matched_terms) for r in response.results]
    assert coverage == sorted(coverage, reverse=True)
    assert response.results[0].matched_terms == ("love", "life")
    assert {r.matched_terms for r in response.results[2:]} == {("life",), ("humor",)}
    assert not response.results[0].complete


def test_proximity_breaks_ties(index):
    response = index.search("love life")
    first, second = response.results[0], response.results[1]
    assert first.url == "https://q.test/tag/love/"
    assert first.window < second.window


def test_bm25_prefers_page_with_more_occurrences(index):
    assert index.search("einstein").results[0].url == "https://q.test/author/einstein/"


def test_title_match_outranks_short_page():
    long_bio = "Ada Lovelace " + "wrote notes about engines and mathematics " * 20
    index = SearchIndex.from_pages([
        ("https://q.test/author/ada/", "Ada Lovelace · author bio", long_bio),
        ("https://q.test/tag/short/", "Quotes tagged “short”", "by Ada Lovelace short"),
    ])
    assert index.search("ada lovelace").results[0].url == "https://q.test/author/ada/"


def test_duplicate_query_words_do_not_change_scores(index):
    once = index.search("einstein")
    twice = index.search("einstein einstein Einstein")
    assert [(r.url, r.score) for r in once.results] == [(r.url, r.score) for r in twice.results]


def test_phrase_search_requires_adjacent_words(index):
    assert urls(index.search('"nothing is a miracle"')) == ["https://q.test/page/1/"]
    assert urls(index.search('"miracle nothing"')) == []
    assert urls(index.search('"einstein xyzzy"')) == []


def test_stopword_only_query(index):
    response = index.search("the is a")
    assert response.terms == () and response.total == 0


def test_long_queries_are_fast(index):
    query = " ".join(f"word{chr(97 + i)}x" for i in range(26)) + " einstein love life"
    started = time.perf_counter()
    response = index.search(query)
    assert time.perf_counter() - started < 1.0  # was 2^29 subsets before
    assert response.total == 4


def test_pagination(index):
    full = urls(index.search("life", limit=10))
    assert urls(index.search("life", limit=2)) == full[:2]
    assert urls(index.search("life", limit=2, offset=2)) == full[2:4]
    assert index.search("life", limit=2, offset=99).results == []


def test_snippet_highlights_matches_and_is_a_substring(index):
    result = index.search("imagination").results[0]
    assert [s.text for s in result.snippet if s.hit] == ["imagination"]
    text = index.documents[result.url].text
    joined = "".join(s.text for s in result.snippet).removeprefix("… ").removesuffix(" …")
    assert joined in text


def test_snippet_is_trimmed_for_long_pages(index):
    result = index.search("life").results
    far = next(r for r in result if r.url.endswith("/far/"))
    snippet = "".join(s.text for s in far.snippet)
    assert snippet.startswith("… ") and len(snippet) < len(index.documents[far.url].text)


def test_response_to_dict_is_json_serialisable(index):
    data = json.loads(json.dumps(index.search('"nothing miracle" life').to_dict()))
    assert data["phrases"] == ["nothing miracle"]
    assert data["results"][0]["snippet"][0].keys() == {"text", "hit"}
