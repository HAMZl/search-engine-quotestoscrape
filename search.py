"""Command-line interface for the quotes search engine.

Interactive shell (loads the saved index automatically)::

    python search.py

One-shot commands::

    python search.py find albert einstein
    python search.py find '"nothing is a miracle"'
    python search.py print love
    python search.py stats
    python search.py build --delay 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from engine import DEFAULT_INDEX_PATH, IndexFormatError, SearchIndex, SearchResponse

RESULTS_TO_SHOW = 10
POSITIONS_TO_SHOW = 10

HELP = """\
Commands:
  find <query>     search; use "quotes" for an exact phrase
  print <word>     show the pages and positions where a word occurs
  stats            show index statistics
  load [path]      load an index file (done automatically at start-up)
  build [delay]    crawl the site and rebuild the index (delay in seconds)
  help             show this message
  exit             quit"""


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #

def format_response(response: SearchResponse) -> str:
    lines: list[str] = []
    if response.unknown_terms:
        lines.append("Not in the index: " + ", ".join(response.unknown_terms))
    if response.suggested_query:
        lines.append(f"Did you mean: {response.suggested_query}")
    if not response.terms:
        lines.append("Your query only contains stopwords or no words at all.")
        return "\n".join(lines)
    if not response.results:
        lines.append("No webpages found!")
        return "\n".join(lines)

    lines.append(f"{response.total} page(s) found.")
    group = None
    for rank, result in enumerate(response.results, start=response.offset + 1):
        if result.matched_terms != group:
            group = result.matched_terms
            lines.append(f"\nResults for word(s): {', '.join(group)}")
        snippet = "".join(f"*{s.text}*" if s.hit else s.text for s in result.snippet)
        details = f"score {result.score:.2f} · {result.frequency} occurrence(s)"
        if result.window:
            details += f" · all words within {result.window} tokens"
        lines += [
            f"  {rank:>2}. {result.title}",
            f"      {result.url}",
            f"      {details}",
            f"      {snippet}",
        ]
    return "\n".join(lines)


def format_postings(index: SearchIndex, word: str) -> str:
    term, postings = index.lookup(word)
    if term is None:
        return f"'{word}' is a stopword (or not a word) and is not indexed."
    if not postings:
        return f"'{term}' is not in the inverted index!"
    lines = [f"'{term}' appears on {len(postings)} page(s):"]
    for url, positions in sorted(postings.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        shown = ", ".join(map(str, positions[:POSITIONS_TO_SHOW]))
        more = f", … (+{len(positions) - POSITIONS_TO_SHOW})" if len(positions) > POSITIONS_TO_SHOW else ""
        lines.append(f"  {len(positions):>3}x  {url}  [{shown}{more}]")
    return "\n".join(lines)


def format_stats(index: SearchIndex) -> str:
    stats = index.stats()
    return (
        f"Pages: {stats['pages']}  Terms: {stats['terms']}  "
        f"Tokens: {stats['tokens']}  Built: {stats['built_at'] or 'unknown'}"
    )


# --------------------------------------------------------------------------- #
# Interactive shell
# --------------------------------------------------------------------------- #

class Shell:
    def __init__(self, index_path: Path = DEFAULT_INDEX_PATH, out: TextIO = sys.stdout):
        self.index_path = Path(index_path)
        self.out = out
        self.index: SearchIndex | None = None

    def say(self, text: str) -> None:
        print(text, file=self.out)

    def load(self, path: Path | None = None) -> bool:
        path = Path(path) if path else self.index_path
        try:
            self.index = SearchIndex.load(path)
        except FileNotFoundError:
            self.say(f"No index file at {path}. Run 'build' to create one.")
            return False
        except (IndexFormatError, ValueError) as exc:
            self.say(f"Could not load {path}: {exc}")
            return False
        self.index_path = path
        self.say(f"Inverted index loaded successfully! ({format_stats(self.index)})")
        return True

    def _require_index(self) -> bool:
        if self.index is None:
            self.say("No index loaded. Use 'load' or 'build' first.")
            return False
        return True

    def handle(self, line: str) -> bool:
        """Run one command. Returns False when the shell should exit."""
        command, _, arg = line.strip().partition(" ")
        command, arg = command.lower(), arg.strip()
        if not command:
            return True
        if command in ("exit", "quit"):
            return False
        if command == "help":
            self.say(HELP)
        elif command == "load":
            self.load(Path(arg) if arg else None)
        elif command == "build":
            self.build(arg)
        elif command in ("print", "find", "stats"):
            if not self._require_index():
                return True
            if command == "stats":
                self.say(format_stats(self.index))
            elif not arg:
                self.say(f"Usage: {command} <{'word' if command == 'print' else 'query'}>")
            elif command == "print":
                self.say(format_postings(self.index, arg))
            else:
                self.say(format_response(self.index.search(arg, limit=RESULTS_TO_SHOW)))
        else:
            self.say(f"Unknown command '{command}'. Type 'help' for a list of commands.")
        return True

    def build(self, arg: str = "") -> None:
        from crawler import DEFAULT_DELAY, build_index  # imports requests/bs4 lazily

        try:
            delay = float(arg) if arg else DEFAULT_DELAY
        except ValueError:
            self.say("Usage: build [delay_seconds]")
            return
        self.index, _ = build_index(self.index_path, delay=delay, log=self.say)

    def run(self) -> None:
        if self.index_path.exists():
            self.load()
        else:
            self.say("No saved index found - type 'build' to crawl the site.")
        self.say("Type 'help' for commands.")
        while True:
            try:
                line = input(">> ")
            except (EOFError, KeyboardInterrupt):
                self.say("")
                return
            try:
                if not self.handle(line):
                    return
            except KeyboardInterrupt:
                self.say("\nInterrupted.")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # never crash on odd characters

    parser = argparse.ArgumentParser(description="Search engine for quotes.toscrape.com")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH, help="index file path")
    sub = parser.add_subparsers(dest="command")
    build = sub.add_parser("build", help="crawl the site and rebuild the index")
    build.add_argument("--delay", type=float, default=None, help="seconds between requests")
    build.add_argument("--max-pages", type=int, default=None, help="stop after N pages")
    find = sub.add_parser("find", help="search the index")
    find.add_argument("query", nargs="+")
    find.add_argument("-n", "--limit", type=int, default=RESULTS_TO_SHOW)
    show = sub.add_parser("print", help="show postings for a word")
    show.add_argument("word")
    sub.add_parser("stats", help="show index statistics")
    args = parser.parse_args(argv)

    if args.command is None:
        Shell(args.index).run()
        return 0

    if args.command == "build":
        from crawler import DEFAULT_DELAY, build_index

        delay = DEFAULT_DELAY if args.delay is None else args.delay
        build_index(args.index, delay=delay, max_pages=args.max_pages)
        return 0

    try:
        index = SearchIndex.load(args.index)
    except FileNotFoundError:
        print(f"No index file at {args.index}. Run: python search.py build", file=sys.stderr)
        return 1
    except (IndexFormatError, ValueError) as exc:
        print(f"Could not load {args.index}: {exc}", file=sys.stderr)
        return 1

    if args.command == "find":
        print(format_response(index.search(" ".join(args.query), limit=args.limit)))
    elif args.command == "print":
        print(format_postings(index, args.word))
    else:
        print(format_stats(index))
    return 0


if __name__ == "__main__":
    sys.exit(main())
