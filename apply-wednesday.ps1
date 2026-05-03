# Run from: C:\Users\632231\personal\Wednesday_Whatsapp_assistant
# On branch: claude/refactor-cross-platform-app-JnoN1

$ErrorActionPreference = "Stop"

function Write-F($path, $content) {
    $dir = Split-Path $path
    if ($dir -and !(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [IO.File]::WriteAllText((Resolve-Path .).Path + "\" + $path, $content, [Text.Encoding]::UTF8)
    Write-Host "wrote $path"
}

Write-F "requirements.txt" @'
fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx>=0.27.0
pydantic-settings>=2.5.0
python-multipart>=0.0.12
openai>=1.54.0
sqlalchemy[asyncio]>=2.0.36
asyncpg>=0.30.0
aiosqlite>=0.20.0
itsdangerous>=2.2.0
'@

Write-F "Dockerfile" @'
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
'@

Write-F "docker-compose.yaml" @'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://wednesday:wednesday@db:5432/wednesday
      WAHA_URL: http://whatsapp-service:3000
    depends_on:
      - db
      - whatsapp-service
    restart: unless-stopped

  whatsapp-service:
    build: ./whatsapp-service
    ports:
      - "3000:3000"
    environment:
      WHATSAPP_HOOK_URL: http://backend:8000/whatsapp/webhook
      ENABLE_REAL_WHATSAPP: "true"
    volumes:
      - whatsapp-auth:/app/auth_info_baileys
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: wednesday
      POSTGRES_PASSWORD: wednesday
      POSTGRES_DB: wednesday
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

volumes:
  whatsapp-auth:
  pgdata:
'@

Write-F ".env.example" @'
PUBLIC_URL=http://localhost:8000
SESSION_SECRET=please-change-me
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OPENAI_API_KEY=sk-...
TTS_VOICE=nova
DATABASE_URL=sqlite+aiosqlite:///./wednesday.db
WAHA_URL=http://whatsapp-service:3000
WHATSAPP_ENABLED=true
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
'@

Write-F "backend\__init__.py" ""

Write-F "backend\config.py" @'
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    public_url: str = "http://localhost:8000"
    session_secret: str = "change-me-in-production"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    openai_api_key: str = ""
    tts_voice: str = "nova"
    tts_model: str = "tts-1"
    stt_model: str = "whisper-1"
    database_url: str = "sqlite+aiosqlite:///./wednesday.db"
    waha_url: str = "http://whatsapp-service:3000"
    whatsapp_enabled: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    google_scopes: str = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.modify "
        "https://www.googleapis.com/auth/calendar "
        "https://www.googleapis.com/auth/tasks"
    )
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_scopes: str = (
        "user-read-playback-state user-modify-playback-state "
        "user-read-currently-playing user-read-private streaming"
    )
    cors_origins: list[str] = ["*"]
    system_prompt: str = (
        "You are Wednesday, a personal assistant for Wandile. "
        "Be concise, warm, direct. Reply in 1-3 sentences unless detail is "
        "requested. Use tools when they help. Don't ask for confirmation on "
        "read-only tools; do confirm before destructive actions."
    )

settings = Settings()
'@

Write-F "backend\db.py" @'
from __future__ import annotations
import datetime as _dt
from typing import AsyncIterator
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .config import settings

class Base(DeclarativeBase): pass

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[_dt.datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_token(service, access_token, refresh_token, expires_at, scope=None):
    async with SessionLocal() as s:
        existing = await s.get(OAuthToken, service)
        if existing:
            existing.access_token = access_token
            if refresh_token: existing.refresh_token = refresh_token
            existing.expires_at = expires_at
            existing.scope = scope
        else:
            s.add(OAuthToken(service=service, access_token=access_token,
                             refresh_token=refresh_token, expires_at=expires_at, scope=scope))
        await s.commit()

async def get_token(service: str) -> OAuthToken | None:
    async with SessionLocal() as s:
        return await s.get(OAuthToken, service)
'@

Write-F "backend\oauth.py" @'
from __future__ import annotations
import base64, datetime as _dt, logging
import httpx
from . import db
from .config import settings

log = logging.getLogger(__name__)
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTHZ_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_AUTHZ_URL = "https://accounts.spotify.com/authorize"

def _redirect(service): return f"{settings.public_url.rstrip('/')}/auth/{service}/callback"

def google_authz_url():
    from urllib.parse import urlencode
    return GOOGLE_AUTHZ_URL + "?" + urlencode({"client_id": settings.google_client_id,
        "redirect_uri": _redirect("google"), "response_type": "code",
        "scope": settings.google_scopes, "access_type": "offline", "prompt": "consent"})

def spotify_authz_url():
    from urllib.parse import urlencode
    return SPOTIFY_AUTHZ_URL + "?" + urlencode({"client_id": settings.spotify_client_id,
        "redirect_uri": _redirect("spotify"), "response_type": "code", "scope": settings.spotify_scopes})

async def exchange_google_code(code):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GOOGLE_TOKEN_URL, data={"code": code, "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "redirect_uri": _redirect("google"),
            "grant_type": "authorization_code"})
        r.raise_for_status(); data = r.json()
    expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token("google", data["access_token"], data.get("refresh_token"), expires, data.get("scope"))

async def exchange_spotify_code(code):
    auth = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(SPOTIFY_TOKEN_URL, headers={"Authorization": f"Basic {auth}"},
            data={"grant_type": "authorization_code", "code": code, "redirect_uri": _redirect("spotify")})
        r.raise_for_status(); data = r.json()
    expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token("spotify", data["access_token"], data.get("refresh_token"), expires, data.get("scope"))

async def access_token(service: str) -> str:
    token = await db.get_token(service)
    if token is None:
        raise RuntimeError(f"{service} not connected. Visit /auth/{service}")
    expired = token.expires_at and token.expires_at <= _dt.datetime.utcnow() + _dt.timedelta(seconds=30)
    if not expired: return token.access_token
    if not token.refresh_token:
        raise RuntimeError(f"{service} token expired, no refresh_token. Re-link.")
    if service == "google":
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(GOOGLE_TOKEN_URL, data={"refresh_token": token.refresh_token,
                "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token"})
            r.raise_for_status(); data = r.json()
    else:
        auth = base64.b64encode(f"{settings.spotify_client_id}:{settings.spotify_client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(SPOTIFY_TOKEN_URL, headers={"Authorization": f"Basic {auth}"},
                data={"grant_type": "refresh_token", "refresh_token": token.refresh_token})
            r.raise_for_status(); data = r.json()
    new_expires = _dt.datetime.utcnow() + _dt.timedelta(seconds=data.get("expires_in", 3600))
    await db.save_token(service, data["access_token"],
        data.get("refresh_token") or token.refresh_token, new_expires, data.get("scope") or token.scope)
    return data["access_token"]
'@

Write-F "backend\voice.py" @'
from __future__ import annotations
import io
from openai import AsyncOpenAI
from .config import settings

_client = None
def _openai():
    global _client
    if _client is None: _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client

async def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    buf = io.BytesIO(audio); buf.name = filename
    result = await _openai().audio.transcriptions.create(model=settings.stt_model, file=buf)
    return result.text

async def synthesize(text: str) -> bytes:
    response = await _openai().audio.speech.create(
        model=settings.tts_model, voice=settings.tts_voice, input=text, response_format="mp3")
    return response.read()
'@

Write-F "backend\whatsapp.py" @'
from __future__ import annotations
import logging, time
import httpx
from . import agent
from .config import settings

log = logging.getLogger(__name__)
_seen: dict[str, float] = {}
_rate: dict[str, list[float]] = {}
_DEDUPE_TTL = 300; _RATE_WINDOW = 60; _RATE_LIMIT = 30

def _allowed(sender):
    now = time.time()
    bucket = [t for t in _rate.get(sender, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT: _rate[sender] = bucket; return False
    bucket.append(now); _rate[sender] = bucket; return True

def _is_duplicate(message_id):
    now = time.time()
    for k, t in list(_seen.items()):
        if now - t > _DEDUPE_TTL: _seen.pop(k, None)
    if message_id in _seen: return True
    _seen[message_id] = now; return False

async def handle_webhook(payload: dict) -> dict:
    if not settings.whatsapp_enabled: return {"status": "disabled"}
    message_id = payload.get("id") or payload.get("messageId") or ""
    sender = payload.get("from") or payload.get("chatId") or "unknown"
    text = (payload.get("body") or payload.get("text") or "").strip()
    if not text or _is_duplicate(message_id) or not _allowed(sender): return {"status": "skipped"}
    reply_text = await agent.reply(channel=f"wa:{sender}", user_text=text)
    await _send(sender, reply_text)
    return {"status": "ok", "reply": reply_text}

async def _send(chat_id, text):
    url = f"{settings.waha_url.rstrip('/')}/api/sendText"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, json={"chatId": chat_id, "text": text})
    except Exception as exc:
        log.warning("whatsapp send failed: %s", exc)
'@

Write-F "backend\agent.py" @'
from __future__ import annotations
import asyncio, json, logging
from typing import AsyncIterator
import httpx
from .config import settings
from .tools import REGISTRY

log = logging.getLogger(__name__)
_HISTORIES: dict[str, list[dict]] = {}
_MAX_TOOL_HOPS = 6

def reset(channel): _HISTORIES.pop(channel, None)
def _history(channel): return _HISTORIES.setdefault(channel, [])

def _tool_specs():
    return [{"type": "function", "function": {"name": n, "description": s["description"],
             "parameters": s["schema"]}} for n, s in REGISTRY.items()]

async def _ollama_chat(messages):
    payload = {"model": settings.ollama_model, "messages": messages,
               "tools": _tool_specs(), "stream": False, "options": {"temperature": 0.4}}
    if not messages or messages[0].get("role") != "system":
        payload["messages"] = [{"role": "system", "content": settings.system_prompt}, *messages]
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
        r = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
        r.raise_for_status(); return r.json()

async def _exec_tool(call):
    name = call["function"]["name"]
    raw_args = call["function"].get("arguments")
    if isinstance(raw_args, str):
        try: args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError: args = {}
    else: args = raw_args or {}
    fn = REGISTRY.get(name, {}).get("fn")
    if fn is None: content = f"Tool '{name}' not registered."
    else:
        try:
            result = await fn(**args)
            content = result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as exc:
            log.exception("tool %s failed", name); content = f"Error from {name}: {exc}"
    return {"role": "tool", "name": name, "content": content}

async def _run_loop(messages):
    for _ in range(_MAX_TOOL_HOPS):
        response = await _ollama_chat(messages)
        msg = response.get("message", {}); tool_calls = msg.get("tool_calls") or []
        if not tool_calls: messages.append(msg); return msg.get("content", "")
        messages.append(msg)
        results = await asyncio.gather(*(_exec_tool(c) for c in tool_calls))
        messages.extend(results)
    return "Sorry — I got stuck in a tool loop. Try rephrasing."

async def reply(channel, user_text):
    history = _history(channel); history.append({"role": "user", "content": user_text})
    return await _run_loop(history)

async def stream_reply(channel, user_text) -> AsyncIterator[str]:
    text = await reply(channel, user_text)
    for word in text.split(" "): yield word + " "
'@

Write-F "backend\main.py" @'
from __future__ import annotations
import asyncio, base64, json, logging
import httpx
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from . import agent, db, oauth, voice, whatsapp
from .config import settings

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Wednesday")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def _startup(): await db.init()

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/auth/google")
async def auth_google(): return RedirectResponse(oauth.google_authz_url())

@app.get("/auth/google/callback")
async def auth_google_callback(code: str):
    await oauth.exchange_google_code(code); return {"status": "linked", "service": "google"}

@app.get("/auth/spotify")
async def auth_spotify(): return RedirectResponse(oauth.spotify_authz_url())

@app.get("/auth/spotify/callback")
async def auth_spotify_callback(code: str):
    await oauth.exchange_spotify_code(code); return {"status": "linked", "service": "spotify"}

@app.get("/auth/status")
async def auth_status():
    return {"google": (await db.get_token("google")) is not None,
            "spotify": (await db.get_token("spotify")) is not None}

@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept(); channel = f"ws:{id(ws)}"
    try:
        while True:
            raw = await ws.receive_text(); msg = json.loads(raw); kind = msg.get("type")
            if kind == "reset": agent.reset(channel); continue
            if kind == "audio":
                audio_bytes = base64.b64decode(msg["audio_b64"])
                user_text = await voice.transcribe(audio_bytes)
                await ws.send_json({"type": "transcript", "text": user_text})
            elif kind == "text": user_text = msg.get("text", "")
            else: continue
            if not user_text.strip(): await ws.send_json({"type": "done"}); continue
            chunks = []
            async for delta in agent.stream_reply(channel, user_text):
                chunks.append(delta); await ws.send_json({"type": "delta", "text": delta})
            full = "".join(chunks).strip()
            if msg.get("voice") and full:
                audio = await voice.synthesize(full)
                await ws.send_json({"type": "audio", "audio_b64": base64.b64encode(audio).decode()})
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect: agent.reset(channel)
    except Exception as exc:
        logging.exception("ws error")
        try: await ws.send_json({"type": "error", "message": str(exc)})
        finally: await ws.close()

@app.post("/voice/stt")
async def stt(file: UploadFile):
    return {"text": await voice.transcribe(await file.read(), filename=file.filename or "audio.webm")}

@app.post("/voice/tts")
async def tts(payload: dict):
    return Response(content=await voice.synthesize(payload["text"]), media_type="audio/mpeg")

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    asyncio.create_task(whatsapp.handle_webhook(payload))
    return JSONResponse({"status": "accepted"})

@app.get("/whatsapp/qr")
async def whatsapp_qr():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{settings.waha_url.rstrip('/')}/api/qr")
        return Response(content=r.content, media_type=r.headers.get("content-type","image/png"))

@app.get("/whatsapp/status")
async def whatsapp_status():
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{settings.waha_url.rstrip('/')}/api/sessions/default")
            return r.json()
        except Exception as exc: return {"status": "unreachable", "error": str(exc)}
'@

Write-F "backend\tools\__init__.py" @'
from __future__ import annotations
from typing import Any, Awaitable, Callable, TypedDict

ToolFn = Callable[..., Awaitable[Any]]
class ToolSpec(TypedDict):
    description: str; schema: dict; fn: ToolFn

REGISTRY: dict[str, ToolSpec] = {}

def register(name, description, schema):
    def decorator(fn):
        REGISTRY[name] = {"description": description, "schema": schema, "fn": fn}
        return fn
    return decorator

from . import builtin, google, spotify  # noqa
'@

Write-F "backend\tools\builtin.py" @'
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
'@

Write-F "backend\tools\google.py" @'
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
    return f"Created '{summary}' — {link}"

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
'@

Write-F "backend\tools\spotify.py" @'
from __future__ import annotations
import httpx
from .. import oauth
from . import register

API = "https://api.spotify.com/v1"
async def _headers(): return {"Authorization": f"Bearer {await oauth.access_token('spotify')}"}

@register("spotify_search","Search Spotify for tracks/albums/artists/playlists.",
    {"type":"object","properties":{"query":{"type":"string"},"kind":{"type":"string","enum":["track","album","artist","playlist"],"default":"track"},"limit":{"type":"integer","default":5}},"required":["query"]})
async def spotify_search(query, kind="track", limit=5):
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.get(f"{API}/search", params={"q":query,"type":kind,"limit":limit})
        r.raise_for_status(); items = r.json().get(f"{kind}s",{}).get("items",[])
    return [{"uri":it["uri"],"name":it.get("name"),"artists":", ".join(a["name"] for a in it.get("artists",[]))} for it in items]

@register("spotify_play","Start/resume Spotify playback. Pass URI to play specific item.",
    {"type":"object","properties":{"uri":{"type":"string"}}})
async def spotify_play(uri=None):
    body = {}
    if uri: body = {"uris":[uri]} if uri.startswith("spotify:track:") else {"context_uri":uri}
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c:
        r = await c.put(f"{API}/me/player/play", json=body or None)
    if r.status_code == 404: return "No active Spotify device. Open Spotify on a device first."
    r.raise_for_status(); return "Playing."

@register("spotify_pause","Pause Spotify.",{"type":"object","properties":{}})
async def spotify_pause():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.put(f"{API}/me/player/pause")
    r.raise_for_status(); return "Paused."

@register("spotify_next","Skip to next track.",{"type":"object","properties":{}})
async def spotify_next():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.post(f"{API}/me/player/next")
    r.raise_for_status(); return "Skipped."

@register("spotify_queue","Queue a track on Spotify.",
    {"type":"object","properties":{"uri":{"type":"string"}},"required":["uri"]})
async def spotify_queue(uri):
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.post(f"{API}/me/player/queue", params={"uri":uri})
    r.raise_for_status(); return "Queued."

@register("spotify_now_playing","Get current Spotify track.",{"type":"object","properties":{}})
async def spotify_now_playing():
    async with httpx.AsyncClient(timeout=20, headers=await _headers()) as c: r = await c.get(f"{API}/me/player/currently-playing")
    if r.status_code == 204: return "Nothing is playing."
    r.raise_for_status(); data = r.json(); item = data.get("item") or {}
    return {"name":item.get("name"),"artists":", ".join(a["name"] for a in item.get("artists",[])),"album":(item.get("album") or {}).get("name"),"is_playing":data.get("is_playing")}
'@

Write-F "frontend\src\App.jsx" @'
import Chat from "./components/Chat"
export default function App() {
  return <div className="mx-auto h-full max-w-2xl"><Chat /></div>
}
'@

Write-F "frontend\src\index.css" @'
@tailwind base;
@tailwind components;
@tailwind utilities;
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #root { height: 100%; }
body { font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #0a0a0f; color: #e6e8f0; -webkit-font-smoothing: antialiased; }
::selection { background: rgba(124,92,255,0.35); color: #fff; }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: rgba(124,92,255,0.3); border-radius: 3px; }
.pixelated { image-rendering: pixelated; image-rendering: crisp-edges; }
'@

Write-F "frontend\index.html" @'
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#0a0a0f" />
    <title>Wednesday</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
  </head>
  <body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>
</html>
'@

Write-F "frontend\vite.config.js" @'
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000"
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true,
    proxy: { "/ws": { target: BACKEND, ws: true, changeOrigin: true }, "/health": BACKEND, "/voice": BACKEND, "/whatsapp": BACKEND } },
  build: { outDir: "dist", emptyOutDir: true },
})
'@

Write-F "frontend\package.json" @'
{
  "name": "wednesday",
  "version": "4.0.0",
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview", "tauri": "tauri" },
  "dependencies": { "lucide-react": "^0.312.0", "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@tauri-apps/cli": "^2.0.0", "@types/react": "^18.2.0", "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0", "autoprefixer": "^10.4.0", "postcss": "^8.4.0", "tailwindcss": "^3.4.0", "vite": "^5.0.0" }
}
'@

Write-F "frontend\src\lib\ws.js" @'
const WS_URL = (() => {
  const env = import.meta.env.VITE_BACKEND_WS
  if (env) return env
  const proto = location.protocol === "https:" ? "wss" : "ws"
  return `${proto}://${location.host}/ws`
})()
export function connect(handlers) {
  const ws = new WebSocket(WS_URL)
  ws.onmessage = e => { let msg; try { msg = JSON.parse(e.data) } catch { return }; handlers[msg.type]?.(msg) }
  ws.onclose = () => handlers.close?.()
  ws.onerror = err => handlers.error?.(err)
  return {
    sendText: (text, voice) => ws.send(JSON.stringify({ type: "text", text, voice })),
    sendAudio: (audio_b64, voice) => ws.send(JSON.stringify({ type: "audio", audio_b64, voice })),
    reset: () => ws.send(JSON.stringify({ type: "reset" })),
    close: () => ws.close(), raw: ws,
  }
}
'@

Write-F "frontend\src\lib\audio.js" @'
const AC = window.AudioContext || window.webkitAudioContext
export function makeAnalyser() {
  let ctx=null,analyser=null,raf=0; const subs=new Set(); let level=0
  const tick=()=>{ if(!analyser)return; const data=new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteTimeDomainData(data); let sum=0
    for(let i=0;i<data.length;i++){const v=(data[i]-128)/128;sum+=v*v}
    level=Math.min(1,Math.sqrt(sum/data.length)*2.5); subs.forEach(cb=>cb(level)); raf=requestAnimationFrame(tick) }
  return {
    attach(src){ctx=src.context;analyser=ctx.createAnalyser();analyser.fftSize=512;src.connect(analyser);cancelAnimationFrame(raf);tick()},
    detach(){cancelAnimationFrame(raf);analyser=null;level=0;subs.forEach(cb=>cb(0))},
    subscribe(cb){subs.add(cb);return()=>subs.delete(cb)},
  }
}
export async function recordUntilStop(onStop) {
  const stream=await navigator.mediaDevices.getUserMedia({audio:true})
  const ctx=new AC(); const source=ctx.createMediaStreamSource(stream)
  const analyser=makeAnalyser(); analyser.attach(source)
  const mr=new MediaRecorder(stream,{mimeType:"audio/webm"}); const chunks=[]
  mr.ondataavailable=e=>e.data.size&&chunks.push(e.data)
  mr.onstop=async()=>{ analyser.detach(); stream.getTracks().forEach(t=>t.stop()); await ctx.close(); onStop(new Blob(chunks,{type:"audio/webm"})) }
  mr.start(); return {stop:()=>mr.state!=="inactive"&&mr.stop(),analyser}
}
export function playMp3(b64,analyser){
  return new Promise((resolve,reject)=>{
    const audio=new Audio("data:audio/mpeg;base64,"+b64)
    const ctx=new AC(); const source=ctx.createMediaElementSource(audio)
    source.connect(ctx.destination); if(analyser)analyser.attach(source)
    audio.onended=async()=>{if(analyser)analyser.detach();await ctx.close();resolve()}
    audio.onerror=reject; audio.play().catch(reject)
  })
}
export async function blobToBase64(blob){
  const buf=await blob.arrayBuffer(); const bytes=new Uint8Array(buf); let bin=""
  for(let i=0;i<bytes.length;i++)bin+=String.fromCharCode(bytes[i]); return btoa(bin)
}
'@

Write-F "frontend\src\components\PixelSprite.jsx" @'
import { useEffect, useRef } from "react"
const SPRITE = [
  [0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],
  [0,0,1,1,1,4,1,1,1,1,4,1,1,1,0,0],[0,1,1,1,4,4,1,1,1,1,4,4,1,1,1,0],
  [0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [1,1,2,2,1,1,1,1,1,1,1,1,2,2,1,1],[1,1,2,2,1,1,1,1,1,1,1,1,2,2,1,1],
  [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
  [0,1,1,1,1,1,3,3,3,3,1,1,1,1,1,0],[0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0],
  [0,0,1,1,1,1,1,1,1,1,1,1,1,1,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],
  [0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0],[0,0,0,0,0,0,1,1,1,1,0,0,0,0,0,0],
]
const SIZE=16,PX=16
function spriteFor(level){
  const open=Math.round(level*3); if(!open)return SPRITE
  const rows=SPRITE.map(r=>r.slice())
  for(let i=0;i<open;i++){const y=11+i;if(y>=SIZE)break;for(let x=6;x<=9;x++)rows[y][x]=3}
  return rows
}
export default function PixelSprite({analyser,speaking}){
  const canvasRef=useRef(null),levelRef=useRef(0),tRef=useRef(0)
  useEffect(()=>{ if(!analyser)return; return analyser.subscribe(l=>{levelRef.current=l}) },[analyser])
  useEffect(()=>{
    const canvas=canvasRef.current,ctx=canvas.getContext("2d"); ctx.imageSmoothingEnabled=false; let raf=0
    const colors={1:"#7c5cff",2:"#0a0a0f",3:"#ff6ad5",4:"#b8a3ff"}
    const draw=()=>{
      const t=(tRef.current+=1),level=levelRef.current,W=canvas.width,H=canvas.height
      ctx.clearRect(0,0,W,H)
      const bob=Math.sin(t*0.04)*6,scale=1+level*0.18,px=PX*scale
      const cx=W/2,cy=H/2+bob,radius=(SIZE*px)/2+18+level*30
      const grad=ctx.createRadialGradient(cx,cy,4,cx,cy,radius)
      grad.addColorStop(0,`rgba(124,92,255,${0.35+level*0.4})`); grad.addColorStop(1,"rgba(124,92,255,0)")
      ctx.fillStyle=grad; ctx.beginPath(); ctx.arc(cx,cy,radius,0,Math.PI*2); ctx.fill()
      const rows=spriteFor(speaking?level:0),ox=cx-(SIZE*px)/2,oy=cy-(SIZE*px)/2
      for(let y=0;y<SIZE;y++)for(let x=0;x<SIZE;x++){const v=rows[y][x];if(!v)continue
        ctx.fillStyle=colors[v]; ctx.fillRect(Math.round(ox+x*px),Math.round(oy+y*px),Math.ceil(px),Math.ceil(px))}
      raf=requestAnimationFrame(draw)
    }
    draw(); return()=>cancelAnimationFrame(raf)
  },[speaking])
  return <canvas ref={canvasRef} width={520} height={520} className="pixelated" style={{width:360,height:360}} />
}
'@

Write-F "frontend\src\components\Chat.jsx" @'
import { useEffect, useRef, useState } from "react"
import { Mic, Send, Square, Volume2, VolumeX, RotateCcw } from "lucide-react"
import PixelSprite from "./PixelSprite"
import { connect } from "../lib/ws"
import { recordUntilStop, blobToBase64, playMp3, makeAnalyser } from "../lib/audio"

export default function Chat() {
  const [messages,setMessages]=useState([]),[input,setInput]=useState(""),[voice,setVoice]=useState(true)
  const [recording,setRecording]=useState(false),[speaking,setSpeaking]=useState(false),[connected,setConnected]=useState(false)
  const [analyser]=useState(()=>makeAnalyser())
  const wsRef=useRef(null),recRef=useRef(null),pendingRef=useRef(""),scrollRef=useRef(null)

  useEffect(()=>{
    const ws=connect({
      transcript:m=>setMessages(xs=>[...xs,{role:"user",text:m.text}]),
      delta:m=>{ pendingRef.current+=m.text; setMessages(xs=>{ const last=xs[xs.length-1]
        if(last?.role==="assistant"&&last.streaming)return[...xs.slice(0,-1),{...last,text:pendingRef.current}]
        return[...xs,{role:"assistant",text:pendingRef.current,streaming:true}] }) },
      audio:async m=>{ setSpeaking(true); try{await playMp3(m.audio_b64,analyser)}finally{setSpeaking(false)} },
      done:()=>{ pendingRef.current=""; setMessages(xs=>xs.map(m=>({...m,streaming:false}))) },
      error:m=>setMessages(xs=>[...xs,{role:"system",text:m.message}]),
      close:()=>setConnected(false),
    })
    ws.raw.onopen=()=>setConnected(true); wsRef.current=ws; return()=>ws.close()
  },[analyser])

  useEffect(()=>{ scrollRef.current?.scrollTo({top:scrollRef.current.scrollHeight,behavior:"smooth"}) },[messages])

  const sendText=()=>{ const t=input.trim(); if(!t||!wsRef.current)return
    setMessages(xs=>[...xs,{role:"user",text:t}]); wsRef.current.sendText(t,voice); setInput("") }

  const toggleRecord=async()=>{
    if(recording){recRef.current?.stop();setRecording(false);return}
    const rec=await recordUntilStop(async blob=>{ const b64=await blobToBase64(blob); wsRef.current?.sendAudio(b64,voice) })
    recRef.current=rec; setRecording(true)
  }

  const reset=()=>{ wsRef.current?.reset(); setMessages([]); pendingRef.current="" }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected?"bg-emerald-400":"bg-red-400"}`}/>
          <span className="text-sm tracking-widest text-white/60">WEDNESDAY</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={()=>setVoice(v=>!v)} className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            {voice?<Volume2 size={16}/>:<VolumeX size={16}/>}
          </button>
          <button onClick={reset} className="rounded-md p-2 text-white/60 hover:bg-white/5 hover:text-white">
            <RotateCcw size={16}/>
          </button>
        </div>
      </header>
      <div className="flex flex-1 items-center justify-center">
        <PixelSprite analyser={analyser} speaking={speaking||recording}/>
      </div>
      <div ref={scrollRef} className="max-h-[36vh] overflow-y-auto px-4 pb-2">
        {messages.map((m,i)=>(
          <div key={i} className={`my-2 flex ${m.role==="user"?"justify-end":"justify-start"}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
              m.role==="user"?"bg-white/[0.06] text-white":m.role==="system"?"bg-red-500/10 text-red-300":"bg-purple-500/10 text-purple-100"}`}>
              {m.text}
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 border-t border-white/5 bg-black/20 p-3">
        <button onClick={toggleRecord}
          className={`rounded-full p-3 transition ${recording?"bg-red-500 text-white":"bg-white/[0.06] text-white/70 hover:bg-white/10"}`}>
          {recording?<Square size={18}/>:<Mic size={18}/>}
        </button>
        <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendText()}
          placeholder="Talk to Wednesday…"
          className="flex-1 rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-sm text-white placeholder-white/30 outline-none focus:border-purple-400/40"/>
        <button onClick={sendText} disabled={!input.trim()}
          className="rounded-full bg-purple-500 p-3 text-white disabled:opacity-30 hover:bg-purple-400">
          <Send size={18}/>
        </button>
      </div>
    </div>
  )
}
'@

Write-F ".github\workflows\ci.yml" @'
name: CI
on:
  pull_request:
  push:
    branches: [main, release]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12", cache: pip }
      - run: pip install -r requirements.txt
      - run: python -c "import backend.main; import backend.agent; import backend.tools"
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci || npm install
      - run: npm run build
'@

Write-F ".github\workflows\deploy.yml" @'
name: Deploy backend to AWS App Runner
on:
  push:
    branches: [release]
  workflow_dispatch:
env:
  AWS_REGION: ${{ secrets.AWS_REGION }}
  ECR_REPOSITORY: wednesday-backend
permissions:
  contents: read
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}
      - name: Login to Amazon ECR
        id: ecr
        uses: aws-actions/amazon-ecr-login@v2
      - name: Build, tag, and push image
        env:
          REGISTRY: ${{ steps.ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG -t $REGISTRY/$ECR_REPOSITORY:latest .
          docker push $REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $REGISTRY/$ECR_REPOSITORY:latest
      - name: Trigger App Runner deployment
        run: aws apprunner start-deployment --service-arn "${{ secrets.APP_RUNNER_SERVICE_ARN }}"
'@

Write-Host "`nAll files written. Now commit and push:" -ForegroundColor Green
Write-Host "  git add -A" -ForegroundColor Cyan
Write-Host "  git commit -m 'revamp: cross-platform Wednesday with Ollama, voice, OAuth tools, CI/CD'" -ForegroundColor Cyan
Write-Host "  git push -u origin claude/refactor-cross-platform-app-JnoN1" -ForegroundColor Cyan