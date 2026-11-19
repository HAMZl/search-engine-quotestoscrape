import requests

from crawler import build_index, crawl, normalize_url, page_title
from engine import SearchIndex
from bs4 import BeautifulSoup

BASE = "https://quotes.test"


def page(body: str, links: str = "") -> str:
    return f"""<html><head><title>Quotes to Scrape</title></head><body>
    <div class="container">
      <div class="row header-box"><a href="/">Quotes to Scrape</a> <a href="/login">Login</a></div>
      <div class="row"><div class="col-md-8">{body}
        <nav><ul class="pager"><li class="next"><a href="/page/2/">Next</a></li></ul></nav>
      </div>
      <div class="col-md-4 tags-box"><h2>Top Ten tags</h2><a href="/tag/love/">love</a></div>
      {links}
    </div><footer>Made by Zyte</footer></body></html>"""


QUOTE = """<div class="quote"><span class="text">“Imagination is everything.”</span>
  <span>by <small class="author">Albert Einstein</small> <a href="/author/Albert-Einstein">(about)</a></span>
  <div class="tags">Tags: <a class="tag" href="/tag/love/page/1/">love</a></div></div>"""

SITE = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /secret/\n"),
    "/": (200, "text/html", page(QUOTE, '<a>no href</a> <a href="https://elsewhere.test/">x</a>'
                                        ' <a href="/secret/x">s</a> <a href="/broken">b</a>'
                                        ' <a href="mailto:a@b.c">m</a> <a href="/#top">top</a>')),
    "/page/2/": (200, "text/html", page("<div class='quote'><span class='text'>Second page wisdom</span></div>")),
    "/tag/love/": (200, "text/html", page("<h3>Viewing tag: love</h3>" + QUOTE)),
    "/tag/love/page/1/": (200, "text/html", page("<h3>Viewing tag: love</h3>" + QUOTE)),  # duplicate
    "/author/Albert-Einstein/": (200, "text/html", page(
        '<div class="author-details"><h3 class="author-title">Albert Einstein</h3>Physicist.</div>')),
    "/broken": (500, "text/html", "oops"),
}
REDIRECTS = {"/author/Albert-Einstein": "http://quotes.test/author/Albert-Einstein/"}


class FakeResponse:
    def __init__(self, url, status, content_type, text):
        self.url, self.status_code, self.text = url, status, text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {self.url}")


class FakeSession:
    def __init__(self):
        self.requests = []

    def get(self, url, timeout=None):
        assert timeout, "every request must have a timeout"
        self.requests.append(url)
        path = url.removeprefix(BASE).removeprefix("http://quotes.test") or "/"
        final = url
        if path in REDIRECTS:
            final = REDIRECTS[path]
            path = final.removeprefix("http://quotes.test")
        if path not in SITE:
            return FakeResponse(final, 404, "text/html", "not found")
        return FakeResponse(final, *SITE[path])


def run_crawl(**kwargs):
    session, sleeps = FakeSession(), []
    report = crawl(BASE + "/", delay=6, session=session, log=lambda _: None, sleep=sleeps.append, **kwargs)
    return report, session, sleeps


def test_crawl_indexes_each_page_once():
    report, session, _ = run_crawl()
    urls = sorted(p.url for p in report.pages)
    assert urls == [
        f"{BASE}/",
        f"{BASE}/author/Albert-Einstein/",  # redirect followed, https kept
        f"{BASE}/page/2/",
        f"{BASE}/tag/love/page/1/",  # found first, so it wins over /tag/love/
    ]
    assert report.duplicates == 1  # /tag/love/ has identical content
    assert list(report.failed) == [f"{BASE}/broken"]
    assert report.disallowed == [f"{BASE}/secret/x"]
    fetched = set(session.requests)
    assert f"{BASE}/login" not in fetched
    assert not any("elsewhere" in u or "#" in u for u in fetched)
    assert len(session.requests) == len(fetched)  # nothing fetched twice


def test_crawl_waits_between_requests():
    report, session, sleeps = run_crawl()
    page_requests = len(session.requests) - 1  # minus robots.txt
    assert sleeps == [6] * (page_requests - 1)


def test_crawl_strips_page_furniture():
    report, _, _ = run_crawl()
    home = next(p for p in report.pages if p.url == f"{BASE}/")
    assert "Imagination is everything" in home.text
    assert "love" in home.text  # tag names are kept…
    for noise in ("Tags:", "Top Ten", "Login", "Next", "Zyte", "Quotes to Scrape"):
        assert noise not in home.text  # …but the page furniture is not


def test_max_pages():
    report, _, _ = run_crawl(max_pages=2)
    assert len(report.pages) == 2


def test_titles():
    empty = BeautifulSoup("<html></html>", "html.parser")
    assert page_title(f"{BASE}/tag/love/page/3/", empty) == "Quotes tagged “love” · page 3"
    assert page_title(f"{BASE}/tag/love/page/1/", empty) == "Quotes tagged “love”"
    assert page_title(f"{BASE}/page/4/", empty) == "Quotes · page 4"
    assert page_title(f"{BASE}/", empty) == "Quotes · page 1"


def test_normalize_url():
    assert normalize_url("/a#frag", "https://X.test/b") == "https://x.test/a"
    assert normalize_url("mailto:a@b.c", "https://x.test/") is None
    assert normalize_url("javascript:void(0)", "https://x.test/") is None
    assert normalize_url("", "https://x.test/p/") == "https://x.test/p/"


def test_build_index_saves_loadable_index(tmp_path):
    path = tmp_path / "index.json"
    index, _ = build_index(path, start_url=BASE + "/", delay=0, session=FakeSession(),
                           sleep=lambda _: None, log=lambda _: None)
    loaded = SearchIndex.load(path)
    assert len(loaded) == len(index) == 4
    assert loaded.search("imagination").total == 2
