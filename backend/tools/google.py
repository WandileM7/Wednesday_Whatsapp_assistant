from __future__ import annotations
import base64, datetime as _dt, html as _html, logging, re
import httpx
from .. import oauth
from . import register

log = logging.getLogger(__name__)

async def _gauth_headers(): return {"Authorization": f"Bearer {await oauth.access_token('google')}"}


def _b64url(data: str) -> bytes:
    """Decode Gmail's base64url body data, restoring stripped padding."""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _walk_parts(payload: dict):
    """Yield (mime_type, base64url_data) for every leaf part carrying a body,
    recursing through nested multipart/* containers."""
    if payload.get("parts"):
        for part in payload["parts"]:
            yield from _walk_parts(part)
    elif payload.get("body", {}).get("data"):
        yield payload.get("mimeType", ""), payload["body"]["data"]


def _plain_body(payload: dict) -> str:
    """Best-effort readable body: prefer text/plain, else strip a text/html part."""
    plain = html_part = None
    for mime, data in _walk_parts(payload):
        text = _b64url(data).decode("utf-8", "replace")
        if mime == "text/plain" and plain is None:
            plain = text
        elif mime == "text/html" and html_part is None:
            html_part = text
    if plain: return plain.strip()
    if html_part:
        stripped = _html.unescape(re.sub(r"<[^>]+>", " ", html_part))
        return re.sub(r"\s+", " ", stripped).strip()
    return ""

@register("gmail_search","Search Gmail. Returns subject/from/snippet.",
    {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":5,"minimum":1,"maximum":20}},"required":["query"]})
async def gmail_search(query, limit=5):
    headers = await _gauth_headers()
    async with httpx.AsyncClient(timeout=20, headers=headers) as c:
        listing = await c.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", params={"q":query,"maxResults":limit})
        listing.raise_for_status(); ids = [m["id"] for m in listing.json().get("messages",[])]
        out = []
        for mid in ids:
            r = await c.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                params={"format":"metadata","metadataHeaders":["Subject","From","Date"]})
            data = r.json(); hkv = {h["name"]:h["value"] for h in data.get("payload",{}).get("headers",[])}
            out.append({"id":mid,"thread_id":data.get("threadId"),"from":hkv.get("From"),
                        "subject":hkv.get("Subject"),"date":hkv.get("Date"),"snippet":data.get("snippet")})
    return out

@register("gmail_send","Send an email from Gmail.",
    {"type":"object","properties":{"to":{"type":"string"},"subject":{"type":"string"},"body":{"type":"string"}},"required":["to","subject","body"]})
async def gmail_send(to, subject, body):
    raw = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode()
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json={"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")})
        r.raise_for_status()
    return f"Sent to {to}."

@register("gmail_get_thread",
    "Read a full email thread by id (use the thread_id from gmail_search). Returns "
    "each message's from/date/subject and plain-text body — read a thread before "
    "drafting a reply.",
    {"type":"object","properties":{"thread_id":{"type":"string"},
     "max_chars":{"type":"integer","default":2000,"minimum":200,"maximum":8000}},
     "required":["thread_id"]})
async def gmail_get_thread(thread_id, max_chars=2000):
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.get(f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}",
                        params={"format":"full"})
        r.raise_for_status(); msgs = r.json().get("messages", [])
    out = []
    for m in msgs:
        payload = m.get("payload", {})
        hkv = {h["name"]: h["value"] for h in payload.get("headers", [])}
        out.append({"from": hkv.get("From"), "date": hkv.get("Date"),
                    "subject": hkv.get("Subject"), "body": _plain_body(payload)[:max_chars]})
    return out or "No messages in that thread."

@register("gmail_create_draft",
    "Create a Gmail draft — does NOT send. Pass thread_id to draft it as a reply "
    "inside an existing thread. Tell the user it's saved for them to review and "
    "send in Gmail; nothing leaves the outbox.",
    {"type":"object","properties":{"to":{"type":"string"},"subject":{"type":"string"},
     "body":{"type":"string"},"thread_id":{"type":"string"}},"required":["to","subject","body"]})
async def gmail_create_draft(to, subject, body, thread_id=None):
    raw = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode()
    message = {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")}
    if thread_id: message["threadId"] = thread_id
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.post("https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                         json={"message": message})
        r.raise_for_status(); draft_id = r.json().get("id")
    return f"Draft saved (id {draft_id}) — review and send it in Gmail. Nothing sent yet."

@register("calendar_list_events","List upcoming Google Calendar events.",
    {"type":"object","properties":{"limit":{"type":"integer","default":10},"days_ahead":{"type":"integer","default":7}}})
async def calendar_list_events(limit=10, days_ahead=7):
    now = _dt.datetime.utcnow()
    params = {"timeMin":now.isoformat()+"Z","timeMax":(now+_dt.timedelta(days=days_ahead)).isoformat()+"Z",
              "maxResults":limit,"singleEvents":"true","orderBy":"startTime"}
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.get("https://www.googleapis.com/calendar/v3/calendars/primary/events", params=params)
        r.raise_for_status(); items = r.json().get("items",[])
    return [{"id":e["id"],"summary":e.get("summary"),
             "start":e.get("start",{}).get("dateTime") or e.get("start",{}).get("date"),
             "end":e.get("end",{}).get("dateTime") or e.get("end",{}).get("date"),
             "location":e.get("location")} for e in items]

@register("calendar_create_event","Create a Google Calendar event.",
    {"type":"object","properties":{"summary":{"type":"string"},"start":{"type":"string"},"end":{"type":"string"},
     "description":{"type":"string"},"location":{"type":"string"}},"required":["summary","start","end"]})
async def calendar_create_event(summary, start, end, description=None, location=None):
    body = {"summary":summary,"start":{"dateTime":start},"end":{"dateTime":end}}
    if description: body["description"] = description
    if location: body["location"] = location
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", json=body)
        r.raise_for_status(); link = r.json().get("htmlLink")
    return f"Created '{summary}' â€” {link}"

@register("calendar_update_event",
    "Reschedule or edit an existing event by id (from calendar_list_events). Pass "
    "only the fields to change; start/end are ISO-8601 datetimes. Consequential — "
    "the user is asked to confirm first.",
    {"type":"object","properties":{"event_id":{"type":"string"},"summary":{"type":"string"},
     "start":{"type":"string"},"end":{"type":"string"},"description":{"type":"string"},
     "location":{"type":"string"}},"required":["event_id"]})
async def calendar_update_event(event_id, summary=None, start=None, end=None,
                                description=None, location=None):
    body: dict = {}
    if summary is not None: body["summary"] = summary
    if start is not None: body["start"] = {"dateTime": start}
    if end is not None: body["end"] = {"dateTime": end}
    if description is not None: body["description"] = description
    if location is not None: body["location"] = location
    if not body: return "Nothing to update — give at least one field to change."
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.patch(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            json=body)
        r.raise_for_status(); ev = r.json()
    return f"Updated '{ev.get('summary')}' — {ev.get('htmlLink')}"

@register("calendar_delete_event",
    "Delete an event by id (from calendar_list_events). Consequential — the user "
    "is asked to confirm first.",
    {"type":"object","properties":{"event_id":{"type":"string"}},"required":["event_id"]})
async def calendar_delete_event(event_id):
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        r = await c.delete(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}")
        if r.status_code == 410: return "That event was already gone."
        r.raise_for_status()
    return "Deleted."

async def _default_tasklist(client):
    r = await client.get("https://tasks.googleapis.com/tasks/v1/users/@me/lists")
    r.raise_for_status(); items = r.json().get("items",[])
    if not items: raise RuntimeError("No Google Tasks lists found.")
    return items[0]["id"]

@register("tasks_list","List open Google Tasks.",
    {"type":"object","properties":{"limit":{"type":"integer","default":20}}})
async def tasks_list(limit=20):
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        list_id = await _default_tasklist(c)
        r = await c.get(f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks",
            params={"maxResults":limit,"showCompleted":"false"})
        r.raise_for_status()
    return [{"id":t["id"],"title":t.get("title"),"due":t.get("due"),"notes":t.get("notes")} for t in r.json().get("items",[])]

@register("tasks_add","Add a task to Google Tasks.",
    {"type":"object","properties":{"title":{"type":"string"},"due":{"type":"string"},"notes":{"type":"string"}},"required":["title"]})
async def tasks_add(title, due=None, notes=None):
    body = {"title": title}
    if due: body["due"] = due
    if notes: body["notes"] = notes
    async with httpx.AsyncClient(timeout=20, headers=await _gauth_headers()) as c:
        list_id = await _default_tasklist(c)
        r = await c.post(f"https://tasks.googleapis.com/tasks/v1/lists/{list_id}/tasks", json=body)
        r.raise_for_status()
    return f"Added task: {title}"