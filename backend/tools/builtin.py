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
    try:
        description = await vision.describe_url(url, question)
    except Exception as exc:
        return f"Could not fetch that image: {exc}"
    return description or ("Nothing came back — the URL may not be an image, or the "
                           f"vision model ({settings.vision_model}) isn't pulled.")

# Only advertised when vision is on; every schema costs prompt tokens.
if _settings.enable_vision:
    register("see_image",
        "Look at an image on the web and answer a question about it (or describe it). "
        "Use for image URLs found by web_search, charts, screenshots, photos.",
        {"type":"object","properties":{"url":{"type":"string"},
            "question":{"type":"string","description":"What to look for; omit for a general description"}},
         "required":["url"]})(see_image)

# Only advertised to the model when code execution is actually enabled —
# otherwise a small model sees a tool it can never run and hallucinates calls
# to it (even for "Hi"), triggering a pointless approval prompt.
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

if _settings.enable_code_execution:
    register("run_code",
        "Run a short Python snippet in a disposable sandbox (no network, 30s limit) "
        "and return its output. For calculations and data wrangling.",
        {"type":"object","properties":{"code":{"type":"string"}},"required":["code"]})(run_code)

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

@register("get_time","Get current local date/time as ISO-8601.",
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
    "Get the current weather and a short forecast for a place. Give a city or "
    "'City, Country'. Returns current conditions plus today/tomorrow highs, lows "
    "and rain chance. Use this for any weather question instead of web_search.",
    {"type":"object","properties":{
        "location":{"type":"string","description":"City name, e.g. 'Johannesburg' or 'Paris, France'."},
        "units":{"type":"string","enum":["metric","imperial"],"default":"metric"}},
     "required":["location"]})
async def get_weather(location: str, units: str = "metric"):
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
