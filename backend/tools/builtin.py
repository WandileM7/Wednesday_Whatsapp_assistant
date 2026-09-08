from __future__ import annotations
import asyncio, datetime as _dt, html, logging, re
from urllib.parse import parse_qs, urlparse
import httpx
from . import CURRENT_USER, register
# Module-level only for the import-time registration decisions below; the tool
# bodies keep importing settings lazily so tests can rebind them.
from ..config import settings as _settings

log = logging.getLogger(__name__)


def _clean_result_url(href: str) -> str:
    """Turn a DuckDuckGo result href into a real destination URL.

    The HTML endpoint returns protocol-relative redirect wrappers like
    //duckduckgo.com/l/?uddg=<url-encoded-target>&rut=... — not usable by
    fetch_page. Unwrap the `uddg` target; otherwise just normalise the scheme.
    """
    href = html.unescape(re.sub(r"<[^>]+>", "", href)).strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.path.startswith("/l/") and "duckduckgo.com" in (parsed.netloc or ""):
        target = parse_qs(parsed.query).get("uddg", [""])[0]  # already decoded
        if target:
            return target
    return href

@register("fetch_page","Fetch a web page and return its readable text content. Use after web_search to read a promising result.",
    {"type":"object","properties":{"url":{"type":"string"}},"required":["url"]})
async def fetch_page(url: str):
    if not url.startswith(("http://", "https://")): return "Only http(s) URLs."
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
        headers={"User-Agent":"Mozilla/5.0 Wednesday/1.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
    try:
        import trafilatura
        text = trafilatura.extract(r.text) or ""
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S|re.I)
        text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)))
    text = text.strip()
    if not text: return "Page fetched but no readable text found."
    return text[:4000] + ("\n[truncated]" if len(text) > 4000 else "")

async def see_image(url: str, question: str = ""):
    from .. import vision
    from ..config import settings
    if not settings.enable_vision:
        return "Vision is switched off. Set ENABLE_VISION=true to allow it."
    try:
        description = await vision.describe_url(url, question)
    except Exception as exc:
        return f"Could not fetch that image: {exc}"
    return description or ("Nothing came back — the URL may not be an image, or the "
                           f"vision model ({settings.vision_model}) isn't pulled.")

# Registered always, advertised only when vision is on — agent._disabled()
# decides. Every schema costs prompt tokens, and a tool that cannot work is
# worse than absent: the model calls it and narrates a result anyway.
register("see_image",
    "Look at an image on the web and answer a question about it (or describe it). "
    "Use for image URLs found by web_search, charts, screenshots, photos.",
    {"type":"object","properties":{"url":{"type":"string"},
        "question":{"type":"string","description":"What to look for; omit for a general description"}},
     "required":["url"]})(see_image)

# Registered either way, but only *advertised* when code execution is enabled
# (see agent._tool_specs): a small model that sees a tool it can never run
# hallucinates calls to it, even for "Hi", triggering a pointless approval
# prompt. Registering it regardless means a call that arrives anyway — from
# stored history, or an MCP server, or a model that guessed the name — gets the
# honest "it's switched off" answer rather than "no such tool", which reads like
# a bug and invites the model to try a different spelling.
async def run_code(code: str):
    import asyncio
    from ..config import settings
    if not settings.enable_code_execution:
        return "Code execution is disabled. Set ENABLE_CODE_EXECUTION=true to allow it."
    proc = await asyncio.create_subprocess_exec(
        "docker","run","--rm","--network","none","--memory","512m","--cpus","1",
        "--pids-limit","128","-i","python:3.12-slim","python","-c",code,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill(); return "Timed out after 30s."
    text = out.decode(errors="replace").strip() or "(no output)"
    return text[:3000] + ("\n[truncated]" if len(text) > 3000 else "")

register("run_code",
    "Run a short Python snippet in a disposable sandbox (no network, 30s limit) "
    "and return its output. For calculations and data wrangling.",
    {"type":"object","properties":{"code":{"type":"string"}},"required":["code"]},
    )(run_code)

@register("use_skill",
    "Load the full instructions for one of your skills (listed in your system prompt) before doing a task it covers.",
    {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]})
async def use_skill(name: str):
    from .. import skills
    return skills.body(name) or f"No skill named {name!r}. Available: " + \
        (", ".join(s["name"] for s in skills.catalog()) or "none")

@register("propose_skill",
    "After completing a multi-step task worth repeating, draft it as a reusable skill. The user must review and approve it before it becomes active.",
    {"type":"object","properties":{"name":{"type":"string"},"description":{"type":"string"},"content":{"type":"string","description":"Markdown how-to: steps, tools to call, pitfalls"}},"required":["name","description","content"]})
async def propose_skill(name: str, description: str, content: str):
    from .. import skills
    path = skills.propose(name, description, content)
    return f"Drafted. It activates once the user reviews {path.name} and moves it from proposals/ into okf/skills/."

@register("search_conversations",
    "Search your past conversations with this user. Use when asked about something discussed before, or to recall details you no longer have in context.",
    {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":5,"minimum":1,"maximum":10}},"required":["query"]})
async def search_conversations(query: str, limit: int = 5):
    from .. import memory
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    return await memory.search_messages(user, query, limit)

@register("get_time",
    "Current local date and time as ISO-8601. Use for the time now, today's date, "
    "the day of the week, or to ground anything relative like 'tomorrow'.",
    {"type":"object","properties":{},"additionalProperties":False})
async def get_time(): return _dt.datetime.now().isoformat(timespec="seconds")

@register("set_reply_mode",
    "Change how you deliver replies on messaging channels, when the user asks you to "
    "stop or start sending voice notes. auto = speak only when they send a voice note; "
    "always = speak every reply; never = text only. This persists until changed. For a "
    "one-off ('read this one out'), do NOT call this — just open that reply with [voice].",
    {"type":"object","properties":{"mode":{"type":"string","enum":["auto","always","never"]}},
     "required":["mode"]})
async def set_reply_mode(mode: str):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    mode = (mode or "").strip().lower()
    if mode not in ("auto", "always", "never"):
        return f"mode must be auto, always or never — got {mode!r}."
    await db.set_pref(user, "reply_mode", mode)
    return {"auto": "Voice notes now only when they send one.",
            "always": "Speaking every reply from now on.",
            "never": "Text only from now on."}[mode]

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
    # Only actual reminders: the curator, daily-briefing and history-hygiene
    # jobs share this table but are not things the user set as reminders.
    jobs = [j for j in await db.pending_jobs(user) if j.kind == "reminder"]
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

def _clean_text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _dedupe_by_domain(results: list[dict], limit: int) -> list[dict]:
    """One result per domain, order preserved — cuts the five-Wikipedia-links
    problem and gives the model a broader spread of sources."""
    seen, out = set(), []
    for r in results:
        host = urlparse(r.get("url", "")).netloc.lower().removeprefix("www.")
        if not r.get("url") or host in seen:
            continue
        seen.add(host); out.append(r)
        if len(out) >= limit:
            break
    return out


# ---- DuckDuckGo (free default) ----------------------------------------------
# Two hosts share the same "html" markup; one is often throttled while the
# other answers. The Lite endpoint is a third, sturdier fallback.
_DDG_HTML_ENDPOINTS = ("https://html.duckduckgo.com/html/", "https://duckduckgo.com/html/")
_DDG_HTML_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
_DDG_LITE_LINK = re.compile(r'<a\b([^>]*\bresult-link\b[^>]*)>(.*?)</a>', re.S)
_DDG_LITE_SNIP = re.compile(r'<td\b[^>]*\bresult-snippet\b[^>]*>(.*?)</td>', re.S)
_HREF = re.compile(r'href="([^"]+)"')


def _parse_ddg_html(text: str) -> list[dict]:
    out = []
    for m in _DDG_HTML_RESULT.finditer(text):
        url, title, snippet = m.groups()
        out.append({"url": _clean_result_url(url), "title": _clean_text(title),
                    "snippet": _clean_text(snippet)})
    return out


def _parse_ddg_lite(text: str) -> list[dict]:
    links = [(m.group(1), m.group(2)) for m in _DDG_LITE_LINK.finditer(text)]
    snips = [m.group(1) for m in _DDG_LITE_SNIP.finditer(text)]
    out = []
    for i, (attrs, title) in enumerate(links):
        href = _HREF.search(attrs)
        if not href:
            continue
        out.append({"url": _clean_result_url(href.group(1)), "title": _clean_text(title),
                    "snippet": _clean_text(snips[i]) if i < len(snips) else ""})
    return out


async def _search_ddg(query: str, limit: int):
    """Free scrape with retry/backoff over the html hosts, then the lite host.
    Returns a list, or an explanatory string if everything is throttled."""
    last_err = None
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 Wednesday/1.0"}) as client:
        for attempt in range(3):
            try:
                r = await client.get(_DDG_HTML_ENDPOINTS[attempt % len(_DDG_HTML_ENDPOINTS)],
                                     params={"q": query})
                if results := _parse_ddg_html(r.text):
                    return results
            except Exception as exc:
                last_err = exc
            if attempt < 2:
                await asyncio.sleep(0.4 * (attempt + 1))
        try:  # last resort: the lite endpoint (POST form, sturdier markup)
            r = await client.post(_DDG_LITE_URL, data={"q": query})
            if results := _parse_ddg_lite(r.text):
                return results
        except Exception as exc:
            last_err = exc
    return ("Search returned no results after several attempts (the endpoint may be "
            "throttling)" + (f"; last error: {last_err}" if last_err else "") +
            ". Try rephrasing the query.")


# ---- SearXNG (self-hosted, keyless — preferred when configured) -------------

async def _search_searxng(query: str, limit: int):
    """Query a SearXNG instance's JSON API.

    SearXNG metasearches ~70 upstream engines and needs no API key, so it beats
    both the DDG scrape (throttled, markup-dependent) and the hosted providers
    (paid) on this project's zero-bill terms. The instance must have `json` in
    its `search.formats` — the shipped compose service sets that.
    """
    from ..config import settings
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 Wednesday/1.0"}) as client:
        r = await client.get(f"{settings.searxng_url.rstrip('/')}/search",
                             params={"q": query, "format": "json",
                                     "safesearch": 0, "language": "en"})
        r.raise_for_status()
        data = r.json()
    return [{"url": it.get("url"), "title": _clean_text(it.get("title", "")),
             "snippet": _clean_text(it.get("content") or "")}
            for it in data.get("results", [])[:limit]]


# ---- Hosted providers (used when a key is set) ------------------------------

async def _search_tavily(query: str, limit: int, deep: bool):
    from ..config import settings
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post("https://api.tavily.com/search", json={
            "api_key": settings.tavily_api_key, "query": query, "max_results": limit,
            "search_depth": "advanced" if deep else "basic",
            "include_raw_content": deep})
        r.raise_for_status()
        data = r.json()
    out = []
    for it in data.get("results", []):
        row = {"url": it.get("url"), "title": it.get("title"),
               "snippet": (it.get("content") or "")[:400]}
        if deep and it.get("raw_content"):  # Tavily fetched the page for us
            row["content"] = it["raw_content"][:2000]
        out.append(row)
    return out


async def _search_brave(query: str, limit: int):
    from ..config import settings
    async with httpx.AsyncClient(timeout=20, headers={
            "Accept": "application/json",
            "X-Subscription-Token": settings.brave_api_key}) as client:
        r = await client.get("https://api.search.brave.com/res/v1/web/search",
                             params={"q": query, "count": limit})
        r.raise_for_status()
        data = r.json()
    return [{"url": it.get("url"), "title": _clean_text(it.get("title", "")),
             "snippet": _clean_text(it.get("description", ""))}
            for it in data.get("web", {}).get("results", [])[:limit]]


async def _enrich_top(results: list[dict], n: int = 2) -> list[dict]:
    """Deep mode for providers that don't return content themselves: fetch and
    extract the top n pages so the model answers from real text, not snippets."""
    for r in results[:n]:
        if r.get("content"):
            continue
        try:
            page = await fetch_page(url=r.get("url", ""))
            if isinstance(page, str) and not page.startswith(("Only http", "Page fetched")):
                r["content"] = page[:2000] + ("…" if len(page) > 2000 else "")
        except Exception as exc:
            log.debug("deep-enrich fetch failed for %s: %s", r.get("url"), exc)
    return results


@register("web_search",
    "Search the web. Returns top results (url, title, snippet). Set deep=true for "
    "questions that need more than a snippet — it also fetches the top results' full text.",
    {"type":"object","properties":{
        "query":{"type":"string"},
        "limit":{"type":"integer","default":5,"minimum":1,"maximum":10},
        "deep":{"type":"boolean","default":False,
                "description":"Also fetch and include the full text of the top results."}},
     "required":["query"]})
async def web_search(query: str, limit: int = 5, deep: bool = False):
    from ..config import settings
    provider, results = None, None
    # Preference order: self-hosted SearXNG (free, keyless, unthrottled), then a
    # configured hosted provider, then the DDG scrape as the universal fallback.
    if settings.searxng_url:
        provider = "searxng"
        try: results = await _search_searxng(query, limit)
        except Exception as exc: log.warning("searxng search failed, falling back: %s", exc)
    if not results and settings.tavily_api_key:
        provider = "tavily"
        try: results = await _search_tavily(query, limit, deep)
        except Exception as exc: log.warning("tavily search failed, falling back: %s", exc)
    elif not results and settings.brave_api_key:
        provider = "brave"
        try: results = await _search_brave(query, limit)
        except Exception as exc: log.warning("brave search failed, falling back: %s", exc)
    if not results:  # no hosted provider, or it failed → free DuckDuckGo
        results = await _search_ddg(query, limit)
        provider = "duckduckgo" if provider is None else provider
    if isinstance(results, str):  # DDG's throttled-out message
        return results
    results = _dedupe_by_domain(results, limit)
    if deep and provider != "tavily":  # Tavily already returned page content
        results = await _enrich_top(results)
    return results

# ---- Weather (Open-Meteo, free & keyless) -----------------------------------
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle", 53: "drizzle",
    55: "dense drizzle", 56: "freezing drizzle", 57: "dense freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "heavy freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers", 82: "violent showers",
    85: "light snow showers", 86: "heavy snow showers", 95: "thunderstorm",
    96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


@register("get_weather",
    "Current conditions and a short forecast for a place. `location` is a city or "
    "'City, Country'; omit it to use the user's home location. Use for rain, "
    "forecast, sun, wind, how hot or cold it is, whether to take a jacket or "
    "umbrella — always this, never web_search.",
    {"type":"object","properties":{
        "location":{"type":"string","description":"City name, e.g. 'Johannesburg' or 'Paris, France'."},
        "units":{"type":"string","enum":["metric","imperial"],"default":"metric"}}})
async def get_weather(location: str = "", units: str = "metric"):
    from ..config import settings
    # "What's the weather?" with no city is the common case, so fall back to
    # home rather than making her ask where the user lives.
    location = (location or "").strip() or settings.default_location
    if not location:
        return "No location given and no home location configured — ask the user where."
    imperial = units == "imperial"
    tunit = "fahrenheit" if imperial else "celsius"
    wunit = "mph" if imperial else "kmh"
    tsym, wsym = ("°F", "mph") if imperial else ("°C", "km/h")
    async with httpx.AsyncClient(timeout=15,
            headers={"User-Agent": "Wednesday/1.0"}) as client:
        try:
            g = await client.get("https://geocoding-api.open-meteo.com/v1/search",
                params={"name": location, "count": 1, "language": "en", "format": "json"})
            g.raise_for_status()
            hits = g.json().get("results") or []
        except Exception as exc:
            return f"Couldn't look up '{location}': {exc}"
        if not hits:
            return f"Couldn't find a place called '{location}'."
        p = hits[0]
        name = ", ".join(x for x in (p.get("name"), p.get("admin1"),
                                     p.get("country")) if x)
        try:
            r = await client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": p["latitude"], "longitude": p["longitude"],
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                           "precipitation,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max,weather_code",
                "temperature_unit": tunit, "wind_speed_unit": wunit,
                "timezone": "auto", "forecast_days": 2})
            r.raise_for_status()
            d = r.json()
        except Exception as exc:
            return f"Weather service error for {name}: {exc}"
    cur = d.get("current", {})
    day = d.get("daily", {})
    def code(c): return _WMO.get(int(c), "unknown") if c is not None else "unknown"
    out = {
        "location": name,
        "now": {
            "condition": code(cur.get("weather_code")),
            "temp": f"{round(cur.get('temperature_2m'))}{tsym}",
            "feels_like": f"{round(cur.get('apparent_temperature'))}{tsym}",
            "humidity": f"{cur.get('relative_humidity_2m')}%",
            "wind": f"{round(cur.get('wind_speed_10m'))} {wsym}",
        },
    }
    tmax, tmin = day.get("temperature_2m_max", []), day.get("temperature_2m_min", [])
    pop, wc = day.get("precipitation_probability_max", []), day.get("weather_code", [])
    labels = ["today", "tomorrow"]
    fc = []
    for i, lbl in enumerate(labels):
        if i < len(tmax):
            fc.append({"day": lbl, "condition": code(wc[i] if i < len(wc) else None),
                       "high": f"{round(tmax[i])}{tsym}", "low": f"{round(tmin[i])}{tsym}",
                       "rain_chance": f"{pop[i]}%" if i < len(pop) and pop[i] is not None else "n/a"})
    out["forecast"] = fc
    return out


# ---- System status (conversational /doctor + /telemetry) --------------------
@register("system_status",
    "Report Wednesday's own health and system status: which services are up "
    "(model, search, TTS, database), what's linked (Google, Spotify), host CPU/"
    "memory/uptime, and any warnings. Use this for 'run diagnostics', 'how are "
    "you doing', 'system status', or 'are you okay' style questions.",
    {"type":"object","properties":{},"additionalProperties":False})
async def system_status():
    from .. import main as _main  # lazy: main imports tools at load time
    try:
        doc = await _main.doctor()
    except Exception as exc:
        doc = {"status": f"doctor failed: {exc}", "checks": {}, "warnings": []}
    try:
        tel = await _main.telemetry()
    except Exception:
        tel = {}
    mem = tel.get("memory") or {}
    up = tel.get("uptime_s")
    host = {}
    if tel:
        host = {
            "cpu": f"{tel.get('cpu_percent')}%",
            "memory": (f"{round(mem['used']/1048576)}/{round(mem['total']/1048576)} MB "
                       f"({mem.get('percent')}%)"
                       if mem.get("total") else None),
            "uptime": (f"{round(up/3600, 1)}h" if isinstance(up, (int, float)) and up >= 3600
                       else (f"{round(up/60)}m" if isinstance(up, (int, float)) else None)),
            "load": tel.get("load"),
            "clients_connected": tel.get("clients"),
        }
        host = {k: v for k, v in host.items() if v is not None}
    return {
        "status": doc.get("status", "unknown"),
        "services": doc.get("checks", {}),
        "warnings": doc.get("warnings", []),
        "host": host,
    }


@register("look",
    "Look through the user's camera and answer a question about what you see "
    "('what am I holding?', 'read this label'). Only works when their camera is "
    "on in the web app.",
    {"type":"object","properties":{"question":{"type":"string"}}})
async def look(question: str = ""):
    from .. import vision
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    frame = vision.get_frame(user)
    if not frame:
        return "No camera frame available — the user's camera isn't on."
    answer = await vision.describe(frame, question)
    return answer or "Couldn't make anything out."

@register("search_documents",
    "Search the user's own notes and documents (their docs folder) and return the "
    "best-matching passages. Use for questions about their personal files — "
    "contracts, notes, a CV — not for general knowledge.",
    {"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer","default":3,"minimum":1,"maximum":8}},"required":["query"]})
async def search_documents(query: str, limit: int = 3):
    from .. import documents
    return documents.search(query, limit)


@register("set_daily_briefing",
    "Turn on a daily briefing at a given time (24h 'HH:MM'), delivered to the "
    "user's open tab or WhatsApp. Replaces any existing one.",
    {"type":"object","properties":{"time":{"type":"string","description":"24-hour HH:MM, e.g. 07:30"}},"required":["time"]})
async def set_daily_briefing(time: str):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    try:
        hh, mm = (int(x) for x in time.strip().split(":"))
        at = _dt.time(hh, mm)
    except (ValueError, TypeError):
        return f"Couldn't read {time!r} as a 24-hour time like 07:30."
    for job in await db.pending_jobs(user):          # only ever one
        if job.kind == "briefing": await db.cancel_job(user, job.id)
    now = _dt.datetime.now()
    due = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if due <= now: due += _dt.timedelta(days=1)
    job_id = await db.add_job(user, "daily briefing", due, 24 * 60, kind="briefing")
    return {"id": job_id, "first": due.isoformat(timespec="minutes"), "repeats": "daily"}

@register("cancel_daily_briefing","Turn off the daily briefing.",
    {"type":"object","properties":{},"additionalProperties":False})
async def cancel_daily_briefing():
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    for job in await db.pending_jobs(user):
        if job.kind == "briefing":
            await db.cancel_job(user, job.id)
            return "Daily briefing off."
    return "There wasn't one set."


_FEED_MAX_BYTES = 2_000_000


def _tag(el) -> str:
    """Local tag name, dropping any {namespace} prefix (Atom vs RSS)."""
    return el.tag.rsplit("}", 1)[-1].lower()

def _parse_feed(xml_text: str) -> tuple[str, list[dict]]:
    """(feed_title, items) from an RSS or Atom document.

    Feeds are remote XML, so entity expansion is refused outright: ElementTree
    doesn't fetch external entities, but a DOCTYPE can still carry a
    billion-laughs style internal expansion. No legitimate feed needs one, so a
    DOCTYPE is grounds to skip the document rather than add a defusedxml dep.
    """
    import xml.etree.ElementTree as ET
    if "<!DOCTYPE" in xml_text[:2000].upper():
        raise ValueError("feed declares a DOCTYPE; refusing to parse")
    root = ET.fromstring(xml_text)
    feed_title = ""
    for child in root:
        if _tag(child) == "title" and child.text:
            feed_title = child.text.strip(); break
        if _tag(child) == "channel":
            for c in child:
                if _tag(c) == "title" and c.text:
                    feed_title = c.text.strip(); break
            break
    items = []
    for el in root.iter():
        if _tag(el) not in ("item", "entry"):
            continue
        row = {"title": "", "when": "", "link": ""}
        for c in el:
            name, text = _tag(c), (c.text or "").strip()
            if name == "title" and text:
                row["title"] = _clean_text(text)
            elif name in ("pubdate", "published", "updated") and text and not row["when"]:
                row["when"] = text
            elif name == "link" and not row["link"]:
                row["link"] = text or c.attrib.get("href", "")
        if row["title"]:
            items.append(row)
    return feed_title, items

@register("news_digest",
    "Recent news headlines from the user's configured feeds — what's happening, "
    "current events, the latest on a topic. Optionally filter by "
    "topic. Summarise what matters in your own words — never read out links.",
    {"type":"object","properties":{"topic":{"type":"string"},"limit":{"type":"integer","default":8,"minimum":1,"maximum":20}}})
async def news_digest(topic: str = "", limit: int = 8):
    from ..config import settings
    feeds = [u.strip() for u in settings.news_feeds.split(",") if u.strip()]
    if not feeds: return "No news feeds configured (set NEWS_FEEDS)."

    async def fetch(url: str):
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                         headers={"User-Agent": "Wednesday/1.0"}) as c:
                r = await c.get(url)
                r.raise_for_status()
                if len(r.content) > _FEED_MAX_BYTES:
                    raise ValueError("feed too large")
                return _parse_feed(r.text)
        except Exception as exc:
            log.warning("feed %s failed: %s", url, exc)
            return None

    results = await asyncio.gather(*(fetch(u) for u in feeds))
    rows = []
    for got in results:
        if not got: continue
        source, items = got
        for it in items:
            rows.append({"title": it["title"], "source": source, "when": it["when"]})
    if not rows:
        return "Couldn't fetch any news just now."
    if topic.strip():
        terms = {t for t in re.findall(r"[a-z0-9']+", topic.lower()) if len(t) > 1}
        matched = [r for r in rows
                   if terms & set(re.findall(r"[a-z0-9']+", r["title"].lower()))]
        if not matched:
            return f"Nothing in the current headlines about {topic.strip()}."
        rows = matched
    return rows[:limit]



# Unit conversion: factors to a canonical base per dimension. Temperature is
# handled separately since it needs offsets, not just scaling.
_UNITS: dict[str, tuple[str, float]] = {}
for _dim, _table in {
    "length": {"m":1.0,"metre":1.0,"meter":1.0,"metres":1.0,"meters":1.0,"km":1000.0,
               "kilometre":1000.0,"kilometer":1000.0,"cm":0.01,"mm":0.001,
               "mi":1609.344,"mile":1609.344,"miles":1609.344,"ft":0.3048,"foot":0.3048,
               "feet":0.3048,"in":0.0254,"inch":0.0254,"inches":0.0254,
               "yd":0.9144,"yard":0.9144,"yards":0.9144,"nmi":1852.0},
    "mass":   {"kg":1.0,"kilogram":1.0,"kilograms":1.0,"g":0.001,"gram":0.001,"grams":0.001,
               "mg":1e-6,"t":1000.0,"tonne":1000.0,"lb":0.45359237,"lbs":0.45359237,
               "pound":0.45359237,"pounds":0.45359237,"oz":0.028349523125,
               "ounce":0.028349523125,"ounces":0.028349523125,"st":6.35029318,"stone":6.35029318},
    "volume": {"l":1.0,"litre":1.0,"liter":1.0,"litres":1.0,"liters":1.0,"ml":0.001,
               "cl":0.01,"gal":3.785411784,"gallon":3.785411784,"gallons":3.785411784,
               "pt":0.473176473,"pint":0.473176473,"pints":0.473176473,
               "cup":0.2365882365,"cups":0.2365882365,"floz":0.0295735295625},
    "speed":  {"kmh":1.0,"kph":1.0,"km/h":1.0,"mph":1.609344,"m/s":3.6,"ms":3.6,
               "knot":1.852,"knots":1.852,"kn":1.852},
}.items():
    for _u, _f in _table.items():
        _UNITS[_u] = (_dim, _f)

_TEMPS = {"c","celsius","centigrade","f","fahrenheit","k","kelvin"}

def _to_celsius(v: float, unit: str) -> float:
    if unit in ("c", "celsius", "centigrade"): return v
    if unit in ("f", "fahrenheit"): return (v - 32) * 5 / 9
    return v - 273.15  # kelvin

def _from_celsius(c: float, unit: str) -> float:
    if unit in ("c", "celsius", "centigrade"): return c
    if unit in ("f", "fahrenheit"): return c * 9 / 5 + 32
    return c + 273.15

@register("convert_units",
    "Convert a value between units of length, mass, volume, speed or temperature "
    "(e.g. 26 miles to km, 180 lb to kg, 72 f to c).",
    {"type":"object","properties":{"value":{"type":"number"},"from_unit":{"type":"string"},
     "to_unit":{"type":"string"}},"required":["value","from_unit","to_unit"]})
async def convert_units(value: float, from_unit: str, to_unit: str):
    src, dst = from_unit.strip().lower(), to_unit.strip().lower()
    if src in _TEMPS or dst in _TEMPS:
        if not (src in _TEMPS and dst in _TEMPS):
            return f"Can't convert {from_unit} to {to_unit} — one is a temperature."
        out = _from_celsius(_to_celsius(value, src), dst)
    else:
        if src not in _UNITS: return f"Unknown unit {from_unit!r}."
        if dst not in _UNITS: return f"Unknown unit {to_unit!r}."
        (dim_a, fa), (dim_b, fb) = _UNITS[src], _UNITS[dst]
        if dim_a != dim_b:
            return f"Can't convert {dim_a} to {dim_b}."
        out = value * fa / fb
    return {"value": round(out, 4), "unit": to_unit.strip()}

@register("world_time",
    "Current local time somewhere else — pass a city ('Tokyo') or an IANA zone "
    "('Asia/Tokyo').",
    {"type":"object","properties":{"place":{"type":"string"}},"required":["place"]})
async def world_time(place: str):
    from zoneinfo import ZoneInfo, available_timezones
    q = place.strip().replace(" ", "_").lower()
    try:
        zones = available_timezones()
    except Exception:
        return "Timezone database unavailable on this machine."
    match = next((z for z in sorted(zones) if z.lower() == q), None) \
        or next((z for z in sorted(zones) if z.lower().rsplit("/", 1)[-1] == q), None)
    if match is None:
        return f"Don't know a timezone for {place!r}. Try an IANA name like 'Europe/Lisbon'."
    now = _dt.datetime.now(ZoneInfo(match))
    return {"place": match.replace("_", " "), "time": now.strftime("%H:%M"),
            "date": now.strftime("%Y-%m-%d"), "utc_offset": now.strftime("%z")}

@register("convert_currency",
    "Convert an amount between currencies at today's reference rate, e.g. 100 USD "
    "to ZAR. Use ISO codes.",
    {"type":"object","properties":{"amount":{"type":"number"},"from_code":{"type":"string"},
     "to_code":{"type":"string"}},"required":["amount","from_code","to_code"]})
async def convert_currency(amount: float, from_code: str, to_code: str):
    src, dst = from_code.strip().upper(), to_code.strip().upper()
    if src == dst: return {"amount": round(amount, 2), "currency": dst, "rate": 1.0}
    try:
        # Frankfurter: ECB reference rates, free, no API key.
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.frankfurter.app/latest",
                                 params={"amount": amount, "from": src, "to": dst})
            r.raise_for_status(); data = r.json()
    except Exception as exc:
        log.warning("currency lookup failed: %s", exc)
        return "Couldn't reach the exchange-rate service just now."
    rates = data.get("rates") or {}
    if dst not in rates:
        return f"No rate for {src}->{dst} (check the currency codes)."
    return {"amount": round(rates[dst], 2), "currency": dst,
            "date": data.get("date"), "from": f"{amount} {src}"}


@register("remember_person",
    "Save or update a fact about someone in the user's life (colleague, friend, "
    "family, doctor). One fact per call; facts accumulate against the name.",
    {"type":"object","properties":{"name":{"type":"string"},"note":{"type":"string","description":"A single durable fact, e.g. 'sister, lives in Durban'"}},"required":["name","note"]})
async def remember_person(name: str, note: str):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    if not name.strip() or not note.strip(): return "Need both a name and a note."
    action = await db.upsert_person(user, name, note)
    return f"{action.capitalize()} {name.strip()}."

async def _find_person(user: str, name: str):
    """Exact (case-insensitive) match, else a unique partial — the model often
    passes just a first name."""
    from .. import db
    if row := await db.get_person(user, name):
        return row
    needle = name.strip().lower()
    matches = [p for p in await db.list_people(user)
               if needle and needle in p.name_key]
    return matches[0] if len(matches) == 1 else None

@register("recall_person",
    "Look up what you know about someone by name. Use before answering questions "
    "about a person the user mentions.",
    {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]})
async def recall_person(name: str):
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    row = await _find_person(user, name)
    if row is None: return f"Nothing recorded about {name.strip()}."
    return {"name": row.name, "notes": [ln for ln in row.notes.splitlines() if ln.strip()]}

@register("list_people","List everyone you have notes about for this user.",
    {"type":"object","properties":{},"additionalProperties":False})
async def list_people():
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    rows = await db.list_people(user)
    return [{"name": p.name, "notes": len([ln for ln in p.notes.splitlines() if ln.strip()])}
            for p in rows] or "No people recorded yet."

@register("forget_person","Delete everything recorded about a person, by name.",
    {"type":"object","properties":{"name":{"type":"string"}},"required":["name"]})
async def forget_person(name: str):
    from .. import db
    user = CURRENT_USER.get()
    if not user: return "No active user context."
    return f"Forgot {name.strip()}." if await db.forget_person(user, name) \
        else f"Nothing recorded about {name.strip()}."

