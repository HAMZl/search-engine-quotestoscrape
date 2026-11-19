# Quotes Search Engine

By **Hamza Ahmed** ([@HAMZl](https://github.com/HAMZl))

A small search engine built from scratch over [quotes.toscrape.com](https://quotes.toscrape.com/).
A polite crawler visits every page on the site and builds a **positional inverted index**. You can
then search the index from a **web app**, an **interactive shell** or a **JSON API**.

Results are ranked by:

1. **Coverage.** Pages containing *all* of your words come first, then pages with fewer of them.
2. **Relevance.** [BM25](https://en.wikipedia.org/wiki/Okapi_BM25) scoring rewards rare words and
   normalises for page length. Words that also appear in the page title get extra weight, so
   `albert einstein` puts Einstein's author page first.
3. **Proximity.** Pages where your words appear close together get a boost. Closeness is measured
   as the smallest stretch of text that contains every matched word.

Wrap words in quotes (`"nothing is a miracle"`) to require an exact phrase. Common stopwords such
as *the* and *is* are ignored, and misspelt words get a "did you mean" suggestion.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

python app.py                   # web app at http://127.0.0.1:5000
```

The repository includes a prebuilt `inverted_index.json` (202 pages, about 4,200 terms), so you
can search right away. To
re-crawl the site, run `python search.py build`. The crawler waits 6 seconds between requests,
so a full crawl takes about 20 minutes.

## Web app

```bash
python app.py [--host 0.0.0.0] [--port 5000] [--index path/to/index.json] [--debug]
```

* A search box with autocomplete. Press <kbd>/</kbd> anywhere to focus it.
* Highlighted snippets showing the best-matching passage on each page.
* Each result shows which of your words it matched and which are missing.
* Pagination, spelling suggestions, and light and dark themes.
* The site works without JavaScript; scripts only add autocomplete and the keyboard shortcut.

For anything beyond local use, run it under a production WSGI server, for example
`pip install waitress` followed by `waitress-serve --call app:create_app`.

### JSON API

| Endpoint | Description |
| --- | --- |
| `GET /api/search?q=<query>&page=<n>` | Ranked results with scores, matched words and snippets |
| `GET /api/complete?q=<partial query>` | Completions for the last word of the query |
| `GET /api/stats` | Number of pages and terms, and when the index was built |

## Command line

```bash
python search.py                          # interactive shell
python search.py find albert einstein     # one-shot search
python search.py find '"nothing is a miracle"'
python search.py print love               # pages and positions for one word
python search.py stats
python search.py build [--delay 6] [--max-pages N]
```

Inside the shell:

```
>> find love life
>> print einstein
>> stats
>> load [path]
>> build [delay_seconds]
>> help
>> exit
```

## How it works

| File | Purpose |
| --- | --- |
| `crawler.py` | Breadth-first crawler. It honours `robots.txt`, applies a politeness delay and request timeouts, follows redirects to the canonical URL, skips pages it has already seen under another URL, and strips page furniture (header, sidebar, pager, footer) so that only the real content is indexed. |
| `engine.py` | Tokenizer, the `SearchIndex` class (build, save and load), ranking, phrase matching, snippets, spelling suggestions and autocomplete. |
| `search.py` | Command-line interface. |
| `app.py`, `templates/`, `static/` | Flask web app and JSON API. |
| `tests/` | Pytest suite. It uses a fake website, so no network access is needed. |

### Index format

`inverted_index.json` (format version 2) contains:

```jsonc
{
  "version": 2,
  "built_at": "2026-11-19T07:30:00+00:00",
  "documents": { "<url>": { "title": "...", "text": "...", "length": 123 } },
  "postings":  { "<term>": { "<url>": [0, 17, 42] } }   // token positions
}
```

Page text is stored alongside the postings so that results can show snippets. Positions count
indexed tokens only, so stopwords are skipped.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Author

**Hamza Ahmed** · GitHub: [@HAMZl](https://github.com/HAMZl) ·
Repository: [HAMZl/search-engine-quotestoscrape](https://github.com/HAMZl/search-engine-quotestoscrape)
