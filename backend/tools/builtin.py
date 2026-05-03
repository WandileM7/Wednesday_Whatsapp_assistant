from __future__ import annotations
import datetime as _dt, html, re
import httpx
from . import register

@register("get_time","Get current local date/time as ISO-8601.",
    {"type":"object","properties":{},"additionalProperties":False})
async def get_time(): return _dt.datetime.now().isoformat(timespec="seconds")

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