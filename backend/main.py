from __future__ import annotations
import asyncio, base64, json, logging, re
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from . import agent, db, markers, oauth, voice, whatsapp
from .config import settings

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Wednesday")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])

# /health for probes; /auth/* are browser redirects that can't carry headers —
# the OAuth callbacks are protected by one-time state tokens instead.
_OPEN_PATHS = ("/health", "/auth/")

@app.middleware("http")
async def _require_token(request: Request, call_next):
    if settings.api_token and not request.url.path.startswith(_OPEN_PATHS):
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() or request.query_params.get("token", "")
        if token != settings.api_token:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

@app.on_event("startup")
async def _startup():
    await db.init()
    asyncio.create_task(voice.preload())
    asyncio.create_task(agent.warmup())

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s")
_MIN_TTS_CHARS = 20       # first segment: speak as soon as possible
_MIN_TTS_CHARS_NEXT = 80  # later segments: batch sentences so prosody flows
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_MD_MARKS = re.compile(r"[*_#`~]+")
_BULLET = re.compile(r"^\s*(?:[-•+]|\d+[.)])\s+", re.MULTILINE)

def _tts_clean(text: str) -> str:
    """Make text speakable: keep link labels, drop URLs and markdown syntax."""
    text = _MD_LINK.sub(r"\1", text)
    text = _BARE_URL.sub("", text)
    text = _MD_MARKS.sub("", text)
    text = _BULLET.sub("", text)
    return re.sub(r"\s+", " ", text).strip()

def _speakable(text: str, spoken: int) -> int:
    """Index just past the last complete sentence after `spoken`, or `spoken`."""
    min_chars = _MIN_TTS_CHARS if spoken == 0 else _MIN_TTS_CHARS_NEXT
    matches = list(_SENTENCE_END.finditer(text, spoken))
    if not matches or matches[-1].end() - spoken < min_chars: return spoken
    return matches[-1].end()

async def _send_audio(ws: WebSocket, wav: bytes):
    await ws.send_json({"type": "audio", "audio_b64": base64.b64encode(wav).decode()})

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/auth/google")
async def auth_google(): return RedirectResponse(oauth.google_authz_url())

@app.get("/auth/google/callback")
async def auth_google_callback(code: str, state: str = ""):
    if not oauth.verify_state(state): raise HTTPException(400, "invalid OAuth state")
    await oauth.exchange_google_code(code); return {"status": "linked", "service": "google"}

@app.get("/auth/spotify")
async def auth_spotify(): return RedirectResponse(oauth.spotify_authz_url())

@app.get("/auth/spotify/callback")
async def auth_spotify_callback(code: str, state: str = ""):
    if not oauth.verify_state(state): raise HTTPException(400, "invalid OAuth state")
    await oauth.exchange_spotify_code(code); return {"status": "linked", "service": "spotify"}

@app.get("/auth/status")
async def auth_status():
    return {"google": (await db.get_token("google")) is not None,
            "spotify": (await db.get_token("spotify")) is not None}

@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    if settings.api_token and ws.query_params.get("token", "") != settings.api_token:
        await ws.close(code=4401); return
    await ws.accept(); channel = settings.default_user
    try:
        while True:
            raw = await ws.receive_text(); msg = json.loads(raw); kind = msg.get("type")
            if kind == "reset": await agent.reset(channel); continue
            if kind == "audio":
                audio_bytes = base64.b64decode(msg["audio_b64"])
                user_text = await voice.transcribe(audio_bytes)
                await ws.send_json({"type": "transcript", "text": user_text})
            elif kind == "text": user_text = msg.get("text", "")
            else: continue
            if not user_text.strip(): await ws.send_json({"type": "done"}); continue
            want_voice = bool(msg.get("voice"))
            chunks, tts_tasks, spoken, shown = [], [], 0, 0
            async for event in agent.stream_reply(channel, user_text):
                if event["type"] == "delta":
                    chunks.append(event["text"])
                    text = "".join(chunks)
                    if want_voice:
                        end = _speakable(text, spoken)
                        if end > spoken:
                            segment, spoken = _tts_clean(text[spoken:end]), end
                            if segment:
                                tts_tasks.append(asyncio.create_task(voice.synthesize(segment)))
                    # display text: markers are spoken, never shown
                    visible = markers.strip(text[:markers.safe_len(text)])
                    if len(visible) > shown:
                        await ws.send_json({"type": "delta", "text": visible[shown:]})
                        shown = len(visible)
                else:
                    await ws.send_json(event)
                while tts_tasks and tts_tasks[0].done():
                    await _send_audio(ws, tts_tasks.pop(0).result())
            full = "".join(chunks)
            visible = markers.strip(full)
            if len(visible) > shown:
                await ws.send_json({"type": "delta", "text": visible[shown:]})
            if want_voice:
                tail = _tts_clean(full[spoken:])
                if tail: tts_tasks.append(asyncio.create_task(voice.synthesize(tail)))
                for task in tts_tasks: await _send_audio(ws, await task)
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect: pass  # history persists; nothing to clean up
    except Exception as exc:
        logging.exception("ws error")
        try: await ws.send_json({"type": "error", "message": str(exc)})
        finally: await ws.close()

@app.post("/voice/stt")
async def stt(file: UploadFile):
    return {"text": await voice.transcribe(await file.read(), filename=file.filename or "audio.webm")}

@app.post("/voice/tts")
async def tts(payload: dict):
    return Response(content=await voice.synthesize(payload["text"]), media_type="audio/wav")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)