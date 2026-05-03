"""Wednesday backend: FastAPI app exposing the chat WebSocket, voice
endpoints, and the WhatsApp webhook."""
from __future__ import annotations

import asyncio
import base64
import json
import logging

import httpx
from fastapi import FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

from . import agent, db, oauth, voice, whatsapp
from .config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Wednesday")

if settings.cors_origins == ["*"]:
    logging.warning(
        "CORS is configured with a wildcard origin. "
        "Set CORS_ORIGINS to your frontend domain in production."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    await db.init()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ----- OAuth: Google + Spotify -------------------------------------------

@app.get("/auth/google")
async def auth_google() -> RedirectResponse:
    return RedirectResponse(oauth.google_authz_url())


@app.get("/auth/google/callback")
async def auth_google_callback(code: str, state: str = "") -> dict:
    if not oauth.verify_state(state):
        return JSONResponse({"error": "invalid state"}, status_code=400)
    await oauth.exchange_google_code(code)
    return {"status": "linked", "service": "google"}


@app.get("/auth/spotify")
async def auth_spotify() -> RedirectResponse:
    return RedirectResponse(oauth.spotify_authz_url())


@app.get("/auth/spotify/callback")
async def auth_spotify_callback(code: str, state: str = "") -> dict:
    if not oauth.verify_state(state):
        return JSONResponse({"error": "invalid state"}, status_code=400)
    await oauth.exchange_spotify_code(code)
    return {"status": "linked", "service": "spotify"}


@app.get("/auth/status")
async def auth_status() -> dict:
    return {
        "google": (await db.get_token("google")) is not None,
        "spotify": (await db.get_token("spotify")) is not None,
    }


# ----- Chat WebSocket -----------------------------------------------------

@app.websocket("/ws")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    channel = f"ws:{id(ws)}"
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")

            if kind == "reset":
                agent.reset(channel)
                continue

            if kind == "audio":
                audio_bytes = base64.b64decode(msg["audio_b64"])
                user_text = await voice.transcribe(audio_bytes)
                await ws.send_json({"type": "transcript", "text": user_text})
            elif kind == "text":
                user_text = msg.get("text", "")
            else:
                continue

            if not user_text.strip():
                await ws.send_json({"type": "done"})
                continue

            chunks: list[str] = []
            async for delta in agent.stream_reply(channel, user_text):
                chunks.append(delta)
                await ws.send_json({"type": "delta", "text": delta})

            full = "".join(chunks).strip()
            if msg.get("voice") and full:
                audio = await voice.synthesize(full)
                await ws.send_json(
                    {"type": "audio", "audio_b64": base64.b64encode(audio).decode()}
                )
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        agent.reset(channel)
    except Exception as exc:
        logging.exception("ws error")
        agent.reset(channel)
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        finally:
            await ws.close()


# ----- REST: voice helpers ------------------------------------------------

@app.post("/voice/stt")
async def stt(file: UploadFile) -> dict:
    return {"text": await voice.transcribe(await file.read(), filename=file.filename or "audio.webm")}


@app.post("/voice/tts")
async def tts(payload: dict) -> Response:
    audio = await voice.synthesize(payload["text"])
    return Response(content=audio, media_type="audio/mpeg")


# ----- WhatsApp ----------------------------------------------------------

@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> JSONResponse:
    body = await request.json()
    # Baileys gateway wraps the message under a 'payload' key.
    payload = body.get("payload", body)
    asyncio.create_task(whatsapp.handle_webhook(payload))
    return JSONResponse({"status": "accepted"})


@app.get("/whatsapp/qr")
async def whatsapp_qr() -> Response:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{settings.waha_url.rstrip('/')}/api/qr")
        return Response(content=r.content, media_type=r.headers.get("content-type", "image/png"))


@app.get("/whatsapp/status")
async def whatsapp_status() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{settings.waha_url.rstrip('/')}/api/sessions/default")
            return r.json()
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}
