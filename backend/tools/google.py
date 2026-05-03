"""Google Workspace tools: Gmail, Calendar, Tasks."""
from __future__ import annotations

import base64
import datetime as _dt
import logging

import httpx

from .. import oauth
from . import register

log = logging.getLogger(__name__)


async def _gauth_headers() -> dict:
    return {"Authorization": f"Bearer {await oauth.access_token('google')}"}


@register(
    "gmail_search",
    "Search the user's Gmail. Returns the top messages with subject, from, snippet.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Gmail query, e.g. 'from:bob is:unread'"},
            "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
)
async def gmail_search(query: str, limit: int = 5) -> list[dict]:
    headers = await _gauth_headers()
    async with httpx.AsyncClient(timeout=20, headers=headers) as c:
        listing = await c.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": limit},
        )
        listing.raise_for_status()
        ids = [m["id"] for m in listing.json().get("messages", [])]
        out = []
        for mid in ids:
            r = await c.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            )
            data = r.json()
            headers_kv = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
            out.append({
                "id": mid,
                "from": headers_kv.get("From"),
                "subject": headers_kv.get("Subject"),
                "date": headers_kv.get("Date"),
                "snippet": data.get("snippet"),
            })
    return out


@register(
    "gmail_send",
    "Send an email from the user's Gmail account.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string"},
            "body": {"type": "string", "description": "Plain-text body"},
        },
        "required": ["to", "subject", "body"],
    },
)
async def gmail_send(to: str, subject: str, body: str) -> str:
    raw = (
        f"To: {to}\r\n"
        f"Subject: {subject}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"{body}"
    ).encode()
    payload = {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")}
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json=payload,
        )
        r.raise_for_status()
    return f"Sent to {to}."


@register(
    "calendar_list_events",
    "List upcoming events from the user's primary calendar.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            "days_ahead": {"type": "integer", "default": 7, "minimum": 1, "maximum": 90},
        },
    },
)
async def calendar_list_events(limit: int = 10, days_ahead: int = 7) -> list[dict]:
    now = _dt.datetime.utcnow()
    params = {
        "timeMin": now.isoformat() + "Z",
        "timeMax": (now + _dt.timedelta(days=days_ahead)).isoformat() + "Z",
        "maxResults": limit,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params=params,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    return [
        {
            "id": e["id"],
            "summary": e.get("summary"),
            "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
            "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
            "location": e.get("location"),
        }
        for e in items
    ]


@register(
    "calendar_create_event",
    "Create a Google Calendar event on the primary calendar.",
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Event title"},
            "start": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-05-03T14:00:00"},
            "end": {"type": "string", "description": "ISO 8601 datetime"},
            "description": {"type": "string"},
            "location": {"type": "string"},
        },
        "required": ["summary", "start", "end"],
    },
)
async def calendar_create_event(
    summary: str, start: str, end: str,
    description: str | None = None, location: str | None = None,
) -> str:
    body = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            json=body,
        )
        r.raise_for_status()
        link = r.json().get("htmlLink")
    return f"Created '{summary}' - {link}"


async def _default_tasklist(client: httpx.AsyncClient) -> str:
    r = await client.get("https://tasks.googleapis.com/tasks/v1/users/@me/lists")
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        raise RuntimeError("No Google Tasks lists found.")
    return items[0]["id"]


@register(
    "tasks_list",
    "List the user's open Google Tasks.",
    {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        },
    },
)
async def tasks_list(limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        list_id = await _default_tasklist(c)
        r = await c.get(
            f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks",
            params={"maxResults": limit, "showCompleted": "false"},
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    return [{"id": t["id"], "title": t.get("title"), "due": t.get("due"), "notes": t.get("notes")} for t in items]


@register(
    "tasks_add",
    "Add a new task to the user's default Google Tasks list.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "due": {"type": "string", "description": "Optional ISO date for the due date"},
            "notes": {"type": "string"},
        },
        "required": ["title"],
    },
)
async def tasks_add(title: str, due: str | None = None, notes: str | None = None) -> str:
    body = {"title": title}
    if due:
        body["due"] = due
    if notes:
        body["notes"] = notes
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        list_id = await _default_tasklist(c)
        r = await c.post(
            f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks",
            json=body,
        )
        r.raise_for_status()
    return f"Added task: {title}"
