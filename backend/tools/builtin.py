from __future__ import annotations
import datetime as _dt, html, re
import httpx
from . import CURRENT_USER, register

@register("search_conversations",
    "Search your past conversations with this user. Use when asked about something discussed before, or to recall details you no longer have in context.",
    {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":5,"minimum":1,"maximum":10}},"required":["query"]})
async def search_conversations(query: str, limit: int = 5):
    from .. import memory
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    return await memory.search_messages(user, query, limit)

@register("get_time","Get current local date/time as ISO-8601.",
    {"type":"object","properties":{},"additionalProperties":False})
async def get_time(): return _dt.datetime.now().isoformat(timespec="seconds")

@register("set_reminder",
    "Set a reminder to be delivered to the user later. Give when_iso (local ISO-8601, use get_time for now) or in_minutes. Optional repeat_minutes makes it recurring.",
    {"type":"object","properties":{"text":{"type":"string"},"when_iso":{"type":"string"},"in_minutes":{"type":"integer","minimum":1},"repeat_minutes":{"type":"integer","minimum":1}},"required":["text"]})
async def set_reminder(text: str, when_iso: str = "", in_minutes: int = 0, repeat_minutes: int = 0):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    if in_minutes: due = _dt.datetime.now() + _dt.timedelta(minutes=in_minutes)
    elif when_iso:
        try: due = _dt.datetime.fromisoformat(when_iso)
        except ValueError: return f"Could not parse when_iso={when_iso!r}; use ISO-8601 local time."
    else: return "Give when_iso or in_minutes."
    if due <= _dt.datetime.now(): return f"{due.isoformat(timespec='minutes')} is in the past."
    job_id = await db.add_job(user, text, due, repeat_minutes or None)
    return {"id": job_id, "due": due.isoformat(timespec="minutes"),
            "repeats": f"every {repeat_minutes}m" if repeat_minutes else "once"}

@register("list_reminders","List the user's pending reminders.",
    {"type":"object","properties":{},"additionalProperties":False})
async def list_reminders():
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    jobs = await db.pending_jobs(user)
    return [{"id": j.id, "text": j.text, "due": j.due_at.isoformat(timespec="minutes"),
             "repeats": f"every {j.recur_minutes}m" if j.recur_minutes else "once"}
            for j in jobs] or "No pending reminders."

@register("cancel_reminder","Cancel a pending reminder by id (see list_reminders).",
    {"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]})
async def cancel_reminder(id: int):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    return "Cancelled." if await db.cancel_job(user, id) else f"No pending reminder with id {id}."

@register("web_search","Search the web. Returns top results.",
    {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":5,"minimum":1,"maximum":10}},"required":["query"]})
async def web_search(query: str, limit: int = 5):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
        headers={"User-Agent":"Mozilla/5.0 Wednesday/1.0"}) as client:
        r = await client.get("https://duckduckgo.com/html/", params={"q": query})
    pattern = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
    out = []
    for m in list(pattern.finditer(r.text))[:limit]:
        url, title, snippet = m.groups()
        out.append({"url": html.unescape(re.sub(r"<[^>]+>","",url)),
                    "title": html.unescape(re.sub(r"<[^>]+>","",title)).strip(),
                    "snippet": html.unescape(re.sub(r"<[^>]+>","",snippet)).strip()})
    return out