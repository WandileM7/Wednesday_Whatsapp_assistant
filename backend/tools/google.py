from __future__ import annotations
import base64, datetime as _dt, logging
import httpx
from .. import oauth
from . import register

log = logging.getLogger(__name__)

async def _gauth_headers(): return {"Authorization": f"Bearer {await oauth.access_token('google')}"}

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
            out.append({"id":mid,"from":hkv.get("From"),"subject":hkv.get("Subject"),"date":hkv.get("Date"),"snippet":data.get("snippet")})
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