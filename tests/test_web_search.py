"""web_search: a provider chain (Tavily/Brave when keyed, DuckDuckGo otherwise)
with domain dedupe and an optional deep mode. Regression guards for the DDG
redirect-unwrap and the retry/fallback behaviour."""
import json

import httpx
import pytest

from backend.tools import builtin
from backend.config import settings


# ---- URL unwrapping ---------------------------------------------------------

def test_unwraps_ddg_redirect_wrapper():
    href = ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2F"
            "Gaborone&rut=deadbeef")
    assert builtin._clean_result_url(href) == "https://en.wikipedia.org/wiki/Gaborone"


def test_passes_through_a_real_absolute_url():
    url = "https://www.britannica.com/place/Gaborone"
    assert builtin._clean_result_url(url) == url


def test_adds_scheme_to_protocol_relative_non_wrapper():
    assert builtin._clean_result_url("//example.com/x") == "https://example.com/x"


# ---- dedupe -----------------------------------------------------------------

def test_dedupe_keeps_one_result_per_domain():
    rows = [{"url": "https://en.wikipedia.org/a"}, {"url": "https://en.wikipedia.org/b"},
            {"url": "https://www.britannica.com/c"}, {"url": "https://example.org/d"}]
    out = builtin._dedupe_by_domain(rows, limit=5)
    assert [r["url"] for r in out] == [
        "https://en.wikipedia.org/a", "https://www.britannica.com/c", "https://example.org/d"]


# ---- DuckDuckGo default: parsing, retry, lite fallback ----------------------

def _client_returning(get_pages=None, post_page=None):
    """FakeClient: successive .get() calls yield get_pages; .post() yields post_page."""
    seq = iter(get_pages or [])

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return httpx.Response(200, text=next(seq))
        async def post(self, *a, **k): return httpx.Response(200, text=post_page or "")
    return FakeClient


_HTML_RESULT = (
    '<a rel="nofollow" class="result__a" '
    'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fhit&rut=x">Hit</a>'
    '<a class="result__snippet" href="#">a snippet</a>')
_LITE_PAGE = (
    "<table><tr><td>1.&nbsp;</td><td>"
    "<a rel='nofollow' href=\"https://en.wikipedia.org/wiki/Gaborone\" class='result-link'>"
    "Gaborone - Wikipedia</a></td></tr>"
    "<tr><td class='result-snippet'>Capital of Botswana.</td></tr></table>")


@pytest.fixture(autouse=True)
def _no_keys_no_sleep(monkeypatch):
    # default to the free provider and skip real backoff sleeps
    monkeypatch.setattr(settings, "tavily_api_key", "")
    monkeypatch.setattr(settings, "brave_api_key", "")
    async def _instant(*_a, **_k): return None
    monkeypatch.setattr(builtin.asyncio, "sleep", _instant)


async def test_ddg_html_parses_and_unwraps(monkeypatch):
    monkeypatch.setattr(builtin.httpx, "AsyncClient", _client_returning([_HTML_RESULT]))
    results = await builtin.web_search(query="x", limit=3)
    assert results[0]["url"] == "https://example.org/hit"
    assert results[0]["title"] == "Hit"


async def test_ddg_retries_when_first_page_empty(monkeypatch):
    monkeypatch.setattr(builtin.httpx, "AsyncClient",
                        _client_returning(["", _HTML_RESULT]))
    results = await builtin.web_search(query="x", limit=3)
    assert isinstance(results, list) and results[0]["url"] == "https://example.org/hit"


async def test_ddg_falls_back_to_lite(monkeypatch):
    # all three html attempts empty → lite POST answers
    monkeypatch.setattr(builtin.httpx, "AsyncClient",
                        _client_returning(["", "", ""], post_page=_LITE_PAGE))
    results = await builtin.web_search(query="x", limit=3)
    assert isinstance(results, list)
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/Gaborone"
    assert "Botswana" in results[0]["snippet"]


async def test_all_throttled_returns_helpful_message(monkeypatch):
    monkeypatch.setattr(builtin.httpx, "AsyncClient",
                        _client_returning(["", "", ""], post_page=""))
    result = await builtin.web_search(query="x", limit=3)
    assert isinstance(result, str) and "no results" in result.lower()


# ---- hosted providers -------------------------------------------------------

def _json_client(payload):
    _req = httpx.Request("GET", "http://test")  # so raise_for_status() has a request

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): return httpx.Response(200, json=payload, request=_req)
        async def post(self, *a, **k): return httpx.Response(200, json=payload, request=_req)
    return FakeClient


async def test_uses_tavily_when_keyed(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(builtin.httpx, "AsyncClient", _json_client({"results": [
        {"url": "https://a.com", "title": "A", "content": "about a"},
        {"url": "https://b.com", "title": "B", "content": "about b"}]}))
    results = await builtin.web_search(query="x", limit=3)
    assert [r["url"] for r in results] == ["https://a.com", "https://b.com"]
    assert results[0]["snippet"] == "about a"


async def test_tavily_deep_includes_page_content(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")
    monkeypatch.setattr(builtin.httpx, "AsyncClient", _json_client({"results": [
        {"url": "https://a.com", "title": "A", "content": "snip", "raw_content": "FULL PAGE TEXT"}]}))
    results = await builtin.web_search(query="x", limit=3, deep=True)
    assert results[0]["content"] == "FULL PAGE TEXT"


async def test_uses_brave_when_keyed(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "brv-test")
    monkeypatch.setattr(builtin.httpx, "AsyncClient", _json_client({"web": {"results": [
        {"url": "https://a.com", "title": "A", "description": "desc a"}]}}))
    results = await builtin.web_search(query="x", limit=3)
    assert results[0]["url"] == "https://a.com" and results[0]["snippet"] == "desc a"


async def test_falls_back_to_ddg_when_provider_errors(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "brv-test")

    class FlakyThenDDG:
        """Brave GET raises; the DDG fallback GET returns html results."""
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, *a, **k):
            if "brave.com" in url:
                raise httpx.ConnectError("brave down")
            return httpx.Response(200, text=_HTML_RESULT)
        async def post(self, *a, **k): return httpx.Response(200, text="")
    monkeypatch.setattr(builtin.httpx, "AsyncClient", FlakyThenDDG)
    results = await builtin.web_search(query="x", limit=3)
    assert isinstance(results, list) and results[0]["url"] == "https://example.org/hit"


# ---- deep mode for non-Tavily providers -------------------------------------

async def test_deep_mode_enriches_top_results(monkeypatch):
    monkeypatch.setattr(builtin.httpx, "AsyncClient", _client_returning([_HTML_RESULT]))

    async def fake_fetch(url):
        return "EXTRACTED PAGE BODY " * 5
    monkeypatch.setattr(builtin, "fetch_page", fake_fetch)
    results = await builtin.web_search(query="x", limit=3, deep=True)
    assert "EXTRACTED PAGE BODY" in results[0].get("content", "")
