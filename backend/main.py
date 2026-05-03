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