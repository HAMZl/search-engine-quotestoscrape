import pytest

from engine import SearchIndex

PAGES = [
    ("https://q.test/author/einstein/", "Albert Einstein · author bio",
     "Albert Einstein was born in Ulm. Einstein loved music and physics. "
     "Einstein said imagination matters."),
    ("https://q.test/page/1/", "Quotes · page 1",
     "“There are only two ways to live your life. One is as though nothing is a miracle.” "
     "by Albert Einstein inspirational life miracle"),
    ("https://q.test/tag/love/", "Quotes tagged “love”",
     "“It is better to be hated for what you are than to be loved for what you are not.” "
     "by André Gide love life"),
    ("https://q.test/tag/humor/", "Quotes tagged “humor”",
     "“A day without sunshine is like, you know, night.” by Steve Martin humor obvious "
     "<script>alert(1)</script>"),
    ("https://q.test/tag/far/", "Spread out",
     "love " + "filler " * 40 + "life"),
]


@pytest.fixture
def index() -> SearchIndex:
    return SearchIndex.from_pages(PAGES, built_at="2026-01-01T00:00:00+00:00")
