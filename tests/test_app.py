import pytest

from app import create_app


@pytest.fixture
def client(index):
    return create_app(index=index).test_client()


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="q"' in html
    assert "Most widespread words" in html


def test_results_page_highlights_and_groups(client):
    html = client.get("/?q=love+life+humor").get_data(as_text=True)
    assert "<mark>love</mark>" in html
    assert "Pages matching only some of your words" in html
    assert 'class="chip chip--missing"' in html


def test_results_escape_page_content(client):
    html = client.get("/?q=humor").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_results_escape_the_query(client):
    html = client.get('/?q=<img src=x onerror=alert(1)>').get_data(as_text=True)
    assert "<img src=x" not in html


def test_suggestion_and_unknown_terms(client):
    html = client.get("/?q=einstien").get_data(as_text=True)
    assert "Did you mean" in html and "einstein" in html


def test_stopword_only_and_no_results(client):
    assert "Nothing to search for" in client.get("/?q=the").get_data(as_text=True)
    assert "No pages found" in client.get("/?q=xyzzy").get_data(as_text=True)


def test_pagination_bounds(client):
    assert client.get("/?q=life&page=abc").status_code == 200
    assert client.get("/?q=life&page=-5").status_code == 200
    assert "No more results" in client.get("/?q=life&page=50").get_data(as_text=True)


def test_api_search(client):
    response = client.get('/api/search?q="nothing is a miracle"')
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1
    assert data["phrases"] == ["nothing miracle"]
    assert data["results"][0]["url"] == "https://q.test/page/1/"
    assert client.get("/api/search?q=").status_code == 400


def test_api_complete(client):
    assert client.get("/api/complete?q=albert lo").get_json() == ["albert love", "albert loved"]
    assert client.get("/api/complete?q=love ").get_json() == []
    assert client.get('/api/complete?q="lo').get_json() == []


def test_api_stats(client):
    assert client.get("/api/stats").get_json()["pages"] == 5


def test_404s(client):
    assert client.get("/nope").status_code == 404
    assert client.get("/api/nope").get_json() == {"error": "Not found."}


def test_missing_index(tmp_path):
    client = create_app(index_path=tmp_path / "missing.json").test_client()
    response = client.get("/")
    assert response.status_code == 503
    assert "python search.py build" in response.get_data(as_text=True)
    assert client.get("/api/search?q=love").status_code == 503
