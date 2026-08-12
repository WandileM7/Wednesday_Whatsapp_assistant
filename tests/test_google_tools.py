"""Calendar update/delete and deeper Gmail (read-thread + create-draft).

Google is never hit: _gauth_headers is stubbed and httpx.AsyncClient is faked,
capturing the method/url/json each tool sends. The Gmail body parse is exercised
against a *nested* multipart payload (multipart/alternative inside
multipart/mixed), which is where a naive flat parse breaks on real mail.
"""
import base64

import httpx
import pytest

from backend.tools import google


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch):
    async def headers(): return {"Authorization": "Bearer test"}
    monkeypatch.setattr(google, "_gauth_headers", headers)


def _fake_http(monkeypatch, response):
    """Fake httpx.AsyncClient; records the last request and returns `response`."""
    seen: dict = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def _do(self, method, url, **k):
            seen.update(method=method, url=url, json=k.get("json"), params=k.get("params"))
            return response
        async def get(self, url, **k): return await self._do("GET", url, **k)
        async def post(self, url, **k): return await self._do("POST", url, **k)
        async def patch(self, url, **k): return await self._do("PATCH", url, **k)
        async def delete(self, url, **k): return await self._do("DELETE", url, **k)

    monkeypatch.setattr(google.httpx, "AsyncClient", lambda *a, **k: FakeClient())
    return seen


def _resp(status=200, json=None):
    return httpx.Response(status, json=json if json is not None else {},
                          request=httpx.Request("X", "https://test"))


# ---- calendar update --------------------------------------------------------

async def test_update_sends_only_changed_fields(monkeypatch):
    seen = _fake_http(monkeypatch, _resp(json={"summary": "Dentist", "htmlLink": "L"}))
    out = await google.calendar_update_event("ev123", start="2026-08-01T09:00:00")
    assert seen["method"] == "PATCH" and seen["url"].endswith("/events/ev123")
    # only start was provided — nothing else leaks into the PATCH body
    assert seen["json"] == {"start": {"dateTime": "2026-08-01T09:00:00"}}
    assert "Updated 'Dentist'" in out


async def test_update_with_no_fields_makes_no_request(monkeypatch):
    seen = _fake_http(monkeypatch, _resp())
    out = await google.calendar_update_event("ev123")
    assert "Nothing to update" in out
    assert seen == {}  # short-circuited before any HTTP call


# ---- calendar delete --------------------------------------------------------

async def test_delete_calls_delete_and_confirms(monkeypatch):
    seen = _fake_http(monkeypatch, _resp(status=204))
    out = await google.calendar_delete_event("ev123")
    assert seen["method"] == "DELETE" and seen["url"].endswith("/events/ev123")
    assert out == "Deleted."


async def test_delete_already_gone_is_graceful(monkeypatch):
    _fake_http(monkeypatch, _resp(status=410))
    out = await google.calendar_delete_event("ev123")
    assert "already gone" in out


# ---- gmail thread body (nested MIME) ---------------------------------------

def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


# multipart/mixed → [ multipart/alternative → [text/plain, text/html], application/pdf ]
_NESTED_THREAD = {"messages": [{
    "payload": {
        "mimeType": "multipart/mixed",
        "headers": [{"name": "From", "value": "landlord@example.com"},
                    {"name": "Subject", "value": "Rent"},
                    {"name": "Date", "value": "Mon, 26 Jul 2026"}],
        "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("Rent is due Friday.")}},
                {"mimeType": "text/html",
                 "body": {"data": _b64("<p>Rent is due <b>Friday</b>.</p>")}},
            ]},
            {"mimeType": "application/pdf", "filename": "invoice.pdf",
             "body": {"attachmentId": "att1"}},  # no inline data — must be skipped
        ],
    }}]}


async def test_get_thread_extracts_plain_body_from_nested_parts(monkeypatch):
    _fake_http(monkeypatch, _resp(json=_NESTED_THREAD))
    out = await google.gmail_get_thread("t1")
    assert out[0]["from"] == "landlord@example.com"
    assert out[0]["subject"] == "Rent"
    assert out[0]["body"] == "Rent is due Friday."  # text/plain preferred, not the HTML


async def test_get_thread_falls_back_to_stripped_html(monkeypatch):
    html_only = {"messages": [{"payload": {
        "mimeType": "text/html", "headers": [{"name": "From", "value": "a@b.com"}],
        "body": {"data": _b64("<p>Hello <b>there</b></p>")}}}]}
    _fake_http(monkeypatch, _resp(json=html_only))
    out = await google.gmail_get_thread("t1")
    assert out[0]["body"] == "Hello there"


# ---- gmail draft (sends nothing) -------------------------------------------

async def test_create_draft_posts_to_drafts_and_sends_nothing(monkeypatch):
    seen = _fake_http(monkeypatch, _resp(json={"id": "draft99"}))
    out = await google.gmail_create_draft("x@y.com", "Re: Rent", "Paid.", thread_id="t1")
    assert seen["method"] == "POST" and seen["url"].endswith("/drafts")
    assert seen["json"]["message"]["threadId"] == "t1"
    # the raw MIME round-trips back to the body we passed
    raw = seen["json"]["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    assert "Paid." in decoded and "Re: Rent" in decoded
    assert "Nothing sent yet" in out


def test_create_draft_is_not_approval_gated():
    # a draft leaves nothing in the outbox, so it must not sit behind the gate
    from backend.config import settings
    gated = {t.strip() for t in settings.approval_required_tools.split(",")}
    assert "gmail_create_draft" not in gated
    assert "gmail_send" in gated  # sending still is
    assert {"calendar_update_event", "calendar_delete_event"} <= gated
