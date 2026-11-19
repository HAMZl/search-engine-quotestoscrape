"""Polite breadth-first crawler for quotes.toscrape.com.

* honours robots.txt (including any Crawl-delay),
* waits ``delay`` seconds between requests and times out hung requests,
* follows redirects and uses the final URL, so ``/author/X`` and
  ``/author/X/`` are one page,
* skips pages whose content was already indexed under another URL
  (``/tag/love/`` and ``/tag/love/page/1/`` are the same page),
* indexes only the page's main content, not the header, "Top Ten tags"
  sidebar, pager or footer that repeat on every page.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from engine import DEFAULT_INDEX_PATH, SearchIndex

START_URL = "https://quotes.toscrape.com/"
DEFAULT_DELAY = 6.0          # seconds between requests
REQUEST_TIMEOUT = 10         # seconds
USER_AGENT = "quotes-search-engine/2.0 (educational crawler)"
EXCLUDED_PATHS = ("/login", "/logout")
# Page furniture that repeats on every page and would pollute the index.
NOISE_SELECTORS = (".header-box", ".tags-box", "nav", "footer", "form", "script", "style")


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    text: str


@dataclass
class CrawlReport:
    pages: list[Page] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    duplicates: int = 0
    disallowed: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# URL and HTML helpers
# --------------------------------------------------------------------------- #

def normalize_url(href: str, base: str) -> str | None:
    """Resolve *href* against *base*; return None for non-http(s) links."""
    url, _fragment = urldefrag(urljoin(base, href.strip()))
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


def is_excluded(url: str) -> bool:
    path = urlsplit(url).path
    return any(path == p or path.startswith(p + "/") for p in EXCLUDED_PATHS)


def page_title(url: str, soup: BeautifulSoup) -> str:
    """A human-readable title (every page's <title> is just "Quotes to Scrape")."""
    author = soup.select_one(".author-title")
    if author:
        return f"{author.get_text(strip=True)} · author bio"
    path = urlsplit(url).path
    if m := re.fullmatch(r"/tag/([^/]+)/(?:page/(\d+)/?)?", path):
        tag, page = m.group(1), m.group(2)
        return f"Quotes tagged “{tag}”" + (f" · page {page}" if page and page != "1" else "")
    if m := re.fullmatch(r"/page/(\d+)/?", path):
        return f"Quotes · page {m.group(1)}"
    if path == "/":
        return "Quotes · page 1"
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return url


def extract_text(soup: BeautifulSoup) -> str:
    """Main content of the page as a single whitespace-normalised string.

    Mutates *soup*, so extract links first.
    """
    root = soup.select_one(".container") or soup.body or soup
    for selector in NOISE_SELECTORS:
        for element in root.select(selector):
            element.decompose()
    # Drop the bare "Tags:" label but keep the tag names themselves.
    for tags in root.select(".tags"):
        for label in tags.find_all(string=True, recursive=False):
            label.extract()
    return " ".join(root.get_text(" ", strip=True).split())


def load_robots(session: requests.Session, start_url: str) -> RobotFileParser:
    robots = RobotFileParser()
    try:
        response = session.get(urljoin(start_url, "/robots.txt"), timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        robots.allow_all = True
        return robots
    if response.status_code in (401, 403):
        robots.disallow_all = True
    elif response.status_code >= 400:
        robots.allow_all = True  # no robots.txt means everything is allowed
    else:
        robots.parse(response.text.splitlines())
    return robots


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


# --------------------------------------------------------------------------- #
# Crawling
# --------------------------------------------------------------------------- #

def crawl(
    start_url: str = START_URL,
    delay: float = DEFAULT_DELAY,
    max_pages: int | None = None,
    session: requests.Session | None = None,
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> CrawlReport:
    """Breadth-first crawl of every page on *start_url*'s host."""
    session = session or make_session()
    start_url = normalize_url(start_url, start_url)
    scheme, host = urlsplit(start_url)[:2]

    def canonical(url: str) -> str:
        # The site redirects https://.../author/X to http://.../author/X/;
        # keep one scheme so the same page never appears under two URLs.
        parts = urlsplit(url)
        return urlunsplit(parts._replace(scheme=scheme)) if parts.netloc == host else url

    robots = load_robots(session, start_url)
    delay = max(delay, float(robots.crawl_delay(USER_AGENT) or 0))

    queue = deque([start_url])
    seen = {start_url}           # every URL ever queued, so nothing is queued twice
    indexed: set[str] = set()    # final URLs that made it into the index
    digests: set[str] = set()    # content hashes, to catch duplicate pages
    report = CrawlReport()
    requested = False

    while queue and (max_pages is None or len(report.pages) < max_pages):
        url = queue.popleft()
        if not robots.can_fetch(USER_AGENT, url):
            report.disallowed.append(url)
            continue
        if requested:
            sleep(delay)  # politeness window between requests
        requested = True

        log(f"[{len(report.pages) + 1}] {url}")
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            report.failed[url] = str(exc)
            log(f"    failed: {exc}")
            continue
        if "html" not in response.headers.get("Content-Type", "html").lower():
            continue

        final_url = canonical(normalize_url(response.url or url, url) or url)
        seen.add(final_url)
        if final_url in indexed:
            report.duplicates += 1
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            link = normalize_url(anchor["href"], final_url)
            if not link or urlsplit(link).netloc != host:
                continue
            link = canonical(link)
            if link not in seen and not is_excluded(link):
                seen.add(link)
                queue.append(link)

        title = page_title(final_url, soup)
        text = extract_text(soup)
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
        if not text or digest in digests:
            report.duplicates += 1
            continue
        digests.add(digest)
        indexed.add(final_url)
        report.pages.append(Page(final_url, title, text))

    return report


def build_index(
    path: str | Path = DEFAULT_INDEX_PATH, log: Callable[[str], None] = print, **crawl_options
) -> tuple[SearchIndex, CrawlReport]:
    """Crawl the site, build the inverted index and save it to *path*."""
    report = crawl(log=log, **crawl_options)
    built_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    index = SearchIndex.from_pages(
        ((p.url, p.title, p.text) for p in report.pages), built_at=built_at
    )
    index.save(path)
    log(
        f"Indexed {len(index)} pages and {len(index.postings)} terms "
        f"({report.duplicates} duplicates skipped, {len(report.failed)} failed) -> {path}"
    )
    return index, report
