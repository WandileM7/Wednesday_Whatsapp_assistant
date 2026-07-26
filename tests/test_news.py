"""news_digest: RSS + Atom parsing with stdlib xml.etree, topic filtering, and
graceful degradation when a feed is down. Includes the DOCTYPE guard — remote
XML must not be able to hand us an entity-expansion bomb."""
import httpx
import pytest

from backend.tools import builtin
from backend.config import settings


_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Test Wire</title>
  <item><title>Rand strengthens against the dollar</title>
        <pubDate>Sat, 26 Jul 2026 08:00:00 GMT</pubDate>
        <link>https://example.com/a</link></item>
  <item><title>Load shedding suspended</title>
        <pubDate>Sat, 26 Jul 2026 07:00:00 GMT</pubDate>
        <link>https://example.com/b</link></item>
</channel></rss>"""

_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Daily</title>
  <entry><title>Mars rover finds nothing again</title>
         <updated>2026-07-26T06:00:00Z</updated>
         <link href="https://example.org/x"/></entry>
</feed>"""

_DOCTYPE_BOMB = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<rss version="2.0"><channel><title>Bad</title>
<item><title>&lol2;</title></item></channel></rss>"""


def _feeds(monkeypatch, bodies, urls="https://a.test/rss"):
    """Serve `bodies` (str or Exception) in order, one per feed URL."""
    monkeypatch.setattr(settings, "news_feeds", urls)
    seq = iter(bodies)

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **k):
            body = next(seq)
            if isinstance(body, Exception): raise body
            return httpx.Response(200, text=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(builtin.httpx, "AsyncClient", FakeClient)


async def test_parses_rss_items(monkeypatch):
    _feeds(monkeypatch, [_RSS])
    out = await builtin.news_digest()
    assert [r["title"] for r in out] == ["Rand strengthens against the dollar",
                                         "Load shedding suspended"]
    assert out[0]["source"] == "Test Wire"
    assert "2026" in out[0]["when"]


async def test_parses_atom_entries(monkeypatch):
    _feeds(monkeypatch, [_ATOM])
    out = await builtin.news_digest()
    assert out[0]["title"] == "Mars rover finds nothing again"
    assert out[0]["source"] == "Atom Daily"


async def test_merges_multiple_feeds(monkeypatch):
    _feeds(monkeypatch, [_RSS, _ATOM], urls="https://a.test/rss,https://b.test/atom")
    titles = [r["title"] for r in await builtin.news_digest()]
    assert len(titles) == 3
    assert "Mars rover finds nothing again" in titles


async def test_one_dead_feed_does_not_kill_the_digest(monkeypatch):
    _feeds(monkeypatch, [httpx.ConnectError("down"), _ATOM],
           urls="https://dead.test/rss,https://b.test/atom")
    out = await builtin.news_digest()
    assert [r["title"] for r in out] == ["Mars rover finds nothing again"]


async def test_all_feeds_down_is_graceful(monkeypatch):
    _feeds(monkeypatch, [httpx.ConnectError("down")])
    out = await builtin.news_digest()
    assert isinstance(out, str) and "Couldn't fetch" in out


async def test_topic_filter(monkeypatch):
    _feeds(monkeypatch, [_RSS])
    out = await builtin.news_digest(topic="rand dollar")
    assert len(out) == 1 and out[0]["title"].startswith("Rand strengthens")


async def test_topic_with_no_match_says_so(monkeypatch):
    _feeds(monkeypatch, [_RSS])
    out = await builtin.news_digest(topic="badminton")
    assert isinstance(out, str) and "Nothing in the current headlines" in out


async def test_limit_is_respected(monkeypatch):
    _feeds(monkeypatch, [_RSS])
    assert len(await builtin.news_digest(limit=1)) == 1


async def test_doctype_feed_is_refused(monkeypatch):
    # the entity-expansion guard: a DOCTYPE feed is skipped, not parsed
    _feeds(monkeypatch, [_DOCTYPE_BOMB])
    out = await builtin.news_digest()
    assert isinstance(out, str) and "Couldn't fetch" in out


async def test_no_feeds_configured(monkeypatch):
    monkeypatch.setattr(settings, "news_feeds", "")
    out = await builtin.news_digest()
    assert "No news feeds configured" in out
