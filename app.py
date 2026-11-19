"""Web interface for the quotes search engine.

Run locally::

    python app.py                 # http://127.0.0.1:5000
    python app.py --port 8000 --host 0.0.0.0

JSON API::

    GET /api/search?q=<query>&page=<n>
    GET /api/complete?q=<partial query>
    GET /api/stats
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from engine import DEFAULT_INDEX_PATH, IndexFormatError, SearchIndex

RESULTS_PER_PAGE = 10
MAX_QUERY_LENGTH = 200
MAX_PAGE = 100
EXAMPLE_QUERIES = ("albert einstein", "love life", '"nothing is a miracle"', "humor books")


def create_app(index: SearchIndex | None = None, index_path: str | Path = DEFAULT_INDEX_PATH) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    load_error = None
    if index is None:
        try:
            index = SearchIndex.load(index_path)
        except FileNotFoundError:
            load_error = "No index file found. Build one with: python search.py build"
        except (IndexFormatError, ValueError) as exc:
            load_error = str(exc)

    def read_query() -> tuple[str, int]:
        query = " ".join(request.args.get("q", "").split())[:MAX_QUERY_LENGTH]
        page = request.args.get("page", default=1, type=int) or 1
        return query, min(max(page, 1), MAX_PAGE)

    def run_search(query: str, page: int):
        started = time.perf_counter()
        response = index.search(query, limit=RESULTS_PER_PAGE, offset=(page - 1) * RESULTS_PER_PAGE)
        return response, time.perf_counter() - started

    @app.get("/")
    def home():
        query, page = read_query()
        context = {
            "query": query,
            "stats": index.stats() if index else None,
            "error": load_error,
            "examples": EXAMPLE_QUERIES,
        }
        if index is None:
            return render_template("index.html", **context), 503
        if not query:
            context["popular"] = [term for term, _ in index.top_terms(16)]
            return render_template("index.html", **context)

        response, elapsed = run_search(query, page)
        context.update(
            response=response,
            elapsed=elapsed,
            page=page,
            pages=max(1, math.ceil(response.total / RESULTS_PER_PAGE)),
        )
        return render_template("results.html", **context)

    @app.get("/api/search")
    def api_search():
        if index is None:
            return jsonify(error=load_error), 503
        query, page = read_query()
        if not query:
            return jsonify(error="Missing query parameter 'q'."), 400
        response, elapsed = run_search(query, page)
        return jsonify(response.to_dict() | {"page": page, "elapsed_ms": round(elapsed * 1000, 2)})

    @app.get("/api/complete")
    def api_complete():
        """Complete the last word of a partial query."""
        if index is None:
            return jsonify([])
        raw = request.args.get("q", "")[:MAX_QUERY_LENGTH]
        if not raw or raw[-1].isspace() or raw.count('"') % 2:
            return jsonify([])
        head, _, last = raw.rpartition(" ")
        prefix = f"{head} " if head else ""
        return jsonify([prefix + term for term in index.complete(last.lower())])

    @app.get("/api/stats")
    def api_stats():
        if index is None:
            return jsonify(error=load_error), 503
        return jsonify(index.stats())

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return render_template("404.html"), 404

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the search web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    create_app(index_path=args.index).run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
