from __future__ import annotations
import asyncio, base64, json, logging, os, re, time
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from . import (agent, db, email_channel, guard, imessage, live, llm, logstream,
               markers, mcp_client, oauth, scheduler, vecstore, vision, voice,
               voice_commands, wakeword, whatsapp, wyoming_server)
from .config import settings

logging.basicConfig(level=logging.INFO)
logstream.install()  # fan backend logs out to the HUD over SSE
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

async def _boot_tools():
    """MCP first, then warm up: warmup primes Ollama's prefix cache with the
    tool schemas, so it has to run once the MCP tools are registered — priming
    on a shorter list makes the first real turn re-evaluate the whole prompt."""
    await mcp_client.connect_all()
    await agent.warmup()

@app.on_event("startup")
async def _startup():
    logstream.bind_loop(asyncio.get_running_loop())
    await db.init()
    asyncio.create_task(voice.preload())
    asyncio.create_task(_boot_tools())
    asyncio.create_task(scheduler.run())
    asyncio.create_task(email_channel.run())
    asyncio.create_task(wyoming_server.run())

@app.on_event("shutdown")
async def _shutdown():
    await mcp_client.shutdown()

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


_BOOT_TS = time.time()


@app.get("/logs/stream")
async def logs_stream(request: Request):
    """Server-Sent Events tail of the backend logs for the HUD.

    Replays a buffer of recent records so a new tab has immediate context, then
    streams live records as they happen. A periodic ping keeps the connection
    open through proxies that time out idle streams.
    """
    async def gen():
        q = logstream.subscribe()
        try:
            for entry in logstream.recent(150):
                yield f"data: {json.dumps(entry)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            logstream.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _cpu_percent(sample: float = 0.12) -> float:
    """Whole-machine CPU% from two /proc/stat samples, no psutil dependency."""
    def snap():
        with open("/proc/stat") as f:
            parts = [float(x) for x in f.readline().split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return sum(parts), idle
    try:
        t0, i0 = snap(); time.sleep(sample); t1, i1 = snap()
        dt = t1 - t0
        return round((1 - (i1 - i0) / dt) * 100, 1) if dt > 0 else 0.0
    except Exception:
        return 0.0


def _mem() -> dict:
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = float(v.strip().split()[0]) * 1024  # kB → bytes
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        used = total - avail
        return {"total": total, "used": used,
                "percent": round(used / total * 100, 1) if total else 0.0}
    except Exception:
        return {"total": 0, "used": 0, "percent": 0.0}


@app.get("/telemetry")
async def telemetry():
    """Live host + service vitals for the Diagnostics gauges."""
    try:
        load = os.getloadavg()
    except Exception:
        load = (0, 0, 0)
    clients = sum(len(v) for v in getattr(live, "_clients", {}).values()) \
        if hasattr(live, "_clients") else 0
    return {
        "cpu_percent": _cpu_percent(),
        "memory": _mem(),
        "load": [round(x, 2) for x in load],
        "cores": os.cpu_count(),
        "uptime_s": round(time.time() - _BOOT_TS, 1),
        "clients": clients,
        "ollama": {"host": settings.ollama_host, "model": settings.ollama_model},
        "tts": " → ".join(voice._engines()),
    }

_DEFAULT_SECRETS = {"", "change-me-in-production", "please-change-me"}


def _config_warnings(pulled_models: list[str]) -> list[str]:
    """Advisory config problems that work but bite you: the cache-eviction
    trap, a missing utility model, and a default token-encryption secret."""
    warns: list[str] = []
    utility = settings.ollama_model_utility.strip()
    if not utility:
        warns.append(
            "OLLAMA_MODEL_UTILITY is unset — background calls (summaries, memory) "
            "reuse the chat model and evict its prompt cache, making every reply "
            "re-evaluate the full prompt. Set a small, separate model.")
    elif utility == settings.ollama_model:
        warns.append(
            "OLLAMA_MODEL_UTILITY equals OLLAMA_MODEL — same cache-eviction cost as "
            "leaving it unset. Use a different (smaller) model.")
    elif pulled_models and not any(utility in m for m in pulled_models):
        warns.append(f"utility model {utility} not pulled — background calls will "
                     f"fail. Run: ollama pull {utility}")
    if settings.session_secret in _DEFAULT_SECRETS:
        warns.append(
            "SESSION_SECRET is the default — it's the key that encrypts stored OAuth "
            "tokens at rest. Set a strong, unique value (existing tokens will need relinking).")
    return warns


@app.get("/doctor")
async def doctor():
    """One-stop diagnosis of every moving part."""
    checks: dict[str, str] = {}
    models: list[str] = []
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.get(f"{settings.ollama_host}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            checks["ollama"] = "ok" if any(settings.ollama_model in m for m in models) \
                else f"up, but model {settings.ollama_model} not pulled"
        except Exception as exc: checks["ollama"] = f"unreachable: {exc}"
        if settings.whatsapp_enabled:
            try:
                await client.get(f"{settings.waha_url.rstrip('/')}/api/sessions/default")
                checks["whatsapp_service"] = "ok"
            except Exception as exc: checks["whatsapp_service"] = f"unreachable: {exc}"
        if settings.imessage_enabled:
            try:
                r = await client.get(f"{settings.imessage_service_url.rstrip('/')}/health")
                h = r.json()
                if not h.get("configured"):
                    checks["imessage"] = "up, but PHOTON_PROJECT_ID/SECRET not set"
                elif not h.get("ready"):
                    checks["imessage"] = f"up, but not connected: {h.get('error') or 'connecting'}"
                elif not settings.imessage_allowed_handles.strip():
                    checks["imessage"] = "connected, but IMESSAGE_ALLOWED_HANDLES is empty — all senders blocked"
                else:
                    checks["imessage"] = "ok"
            except Exception as exc: checks["imessage"] = f"unreachable: {exc}"
        if settings.searxng_url:
            try:
                r = await client.get(f"{settings.searxng_url.rstrip('/')}/search",
                                     params={"q": "ping", "format": "json"})
                checks["search"] = "searxng" if r.status_code == 200 else (
                    f"searxng up but returned {r.status_code} — is `json` in its search.formats?")
            except Exception as exc: checks["search"] = f"searxng unreachable: {exc}"
        elif settings.tavily_api_key: checks["search"] = "tavily"
        elif settings.brave_api_key: checks["search"] = "brave"
        else: checks["search"] = "duckduckgo scrape (set SEARXNG_URL for a keyless upgrade)"
    try:
        await db.get_token("google"); checks["database"] = "ok"
    except Exception as exc: checks["database"] = f"error: {exc}"
    checks["tts"] = " → ".join(voice._engines())
    checks["chat_model"] = (f"hosted {settings.llm_model} at "
                            f"{settings.llm_base_url} (ollama fallback)") if llm.hosted() \
        else f"ollama {settings.ollama_model} (local)"
    checks["auth"] = "token required" if settings.api_token else "OPEN — set API_TOKEN"
    checks["heartbeat"] = f"every {settings.heartbeat_minutes}m" if settings.heartbeat_minutes else "off"
    checks["code_execution"] = "enabled (docker sandbox)" if settings.enable_code_execution else "off"
    checks["browser"] = "enabled (browser-use)" if settings.enable_browser_use else "off"
    checks["wyoming"] = settings.wyoming_uri if settings.enable_wyoming else "off"
    if settings.enable_memory_embeddings and models and \
            not any(settings.embed_model in m for m in models):
        checks["memory_index"] = (f"embed model {settings.embed_model} not pulled — "
                                  f"run: ollama pull {settings.embed_model}")
    else:
        checks["memory_index"] = vecstore.backend_name()
    if not settings.enable_vision:
        checks["vision"] = "off"
    elif models and not any(settings.vision_model in m for m in models):
        checks["vision"] = (f"{settings.vision_model} not pulled — "
                            f"run: ollama pull {settings.vision_model}")
    else:
        checks["vision"] = settings.vision_model
    checks["mcp"] = mcp_client.status()
    checks["google_linked"] = "yes" if await db.get_token("google") else "no — visit /auth/google"
    checks["spotify_linked"] = "yes" if await db.get_token("spotify") else "no — visit /auth/spotify"
    warnings = _config_warnings(models)
    ok = all(not v.startswith(("unreachable", "error"))
             for v in checks.values() if isinstance(v, str))
    return {"status": "ok" if ok else "degraded", "checks": checks, "warnings": warnings}

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

def _ws_token(ws: WebSocket) -> str:
    """Prefer the token in the Sec-WebSocket-Protocol header ("bearer.<token>")
    — it stays out of the URL and access logs — falling back to ?token= for
    older clients."""
    for proto in ws.scope.get("subprotocols", []):
        if proto.startswith("bearer."):
            return proto[len("bearer."):]
    return ws.query_params.get("token", "")


@app.websocket("/ws")
async def chat_ws(ws: WebSocket):
    protocols = ws.scope.get("subprotocols", [])
    if settings.api_token and _ws_token(ws) != settings.api_token:
        await ws.close(code=4401); return
    # Echo the non-secret marker protocol so a browser that offered one gets a
    # valid negotiated subprotocol back (never echo the bearer token itself).
    accept_kw = {"subprotocol": "wednesday"} if "wednesday" in protocols else {}
    await ws.accept(**accept_kw); channel = settings.default_user
    live.register(channel, ws)
    try:
        while True:
            raw = await ws.receive_text(); msg = json.loads(raw); kind = msg.get("type")
            if kind == "reset": await agent.reset(channel); continue
            # A camera frame, not a turn: stash it for the `look` tool and wait
            # for the next message. Frames are RAM-only and expire (vision.py).
            if kind == "frame":
                vision.set_frame(channel, msg.get("image_b64", "")); continue
            # One turn failing (a model timeout, a tool blowing up) shouldn't
            # drop the socket and force a page reload — report it and keep going.
            try:
                if kind == "audio":
                    audio_bytes = base64.b64decode(msg["audio_b64"])
                    user_text = await voice.transcribe(audio_bytes)
                    # Ambient audio: ignore anything not addressed to her, so
                    # hands-free doesn't answer the room. Silent by design —
                    # an "I wasn't spoken to" reply defeats the purpose.
                    addressed, user_text = wakeword.gate(
                        user_text, hands_free=bool(msg.get("hands_free")))
                    if not addressed:
                        continue
                    await ws.send_json({"type": "transcript", "text": user_text})
                elif kind == "text": user_text = msg.get("text", "")
                else: continue
                if not user_text.strip(): await ws.send_json({"type": "done"}); continue
                # Voice-driven HUD commands ("run diagnostics", "show logs",
                # "close the mic") navigate the client silently — never let them
                # fall through to the model, which would just apologise.
                ui_cmd = voice_commands.match(user_text)
                if ui_cmd is not None:
                    logstream.event(f"▶ turn [{channel}] {'🎙 ' if kind=='audio' else ''}"
                                    f"{user_text[:90]} → ui:{ui_cmd.get('target') or ui_cmd.get('action')}")
                    await ws.send_json(ui_cmd)
                    await ws.send_json({"type": "done"})
                    continue
                want_voice = bool(msg.get("voice"))
                logstream.event(f"▶ turn [{channel}] {'🎙 ' if kind=='audio' else ''}"
                                f"{user_text[:90]}" + ("…" if len(user_text) > 90 else ""))
                chunks, tts_tasks, spoken, shown_text = [], [], 0, ""
                async for event in agent.stream_reply(channel, user_text, surface="web"):
                    if event["type"] == "delta":
                        chunks.append(event["text"])
                        text = "".join(chunks)
                        if want_voice:
                            end = _speakable(text, spoken)
                            if end > spoken:
                                segment, spoken = _tts_clean(text[spoken:end]), end
                                if segment:
                                    tts_tasks.append(asyncio.create_task(voice.synthesize(segment)))
                        # display text: markers are spoken, never shown, and a
                        # sign-off is held back until it is provably not one.
                        # reply() cleans the finished text for WhatsApp and
                        # email; this path streams, so it could not clean
                        # anything afterwards and "How do you need me to assist
                        # you further?" reached the browser intact.
                        visible = guard.streamable(
                            markers.strip(text[:markers.safe_len(text)]))
                        if visible.startswith(shown_text) and len(visible) > len(shown_text):
                            await ws.send_json({"type": "delta",
                                                "text": visible[len(shown_text):]})
                            shown_text = visible
                    else:
                        if event["type"] == "tool":
                            logstream.event(f"🔧 tool · {event.get('name','?')}")
                        await ws.send_json(event)
                    while tts_tasks and tts_tasks[0].done():
                        await _send_audio(ws, tts_tasks.pop(0).result())
                full = "".join(chunks)
                # The turn is over, so the sign-off is now decidable: clean the
                # whole thing and release whatever the holdback was still
                # sitting on.
                visible = guard.strip_filler(markers.strip(full))
                if visible.startswith(shown_text) and len(visible) > len(shown_text):
                    await ws.send_json({"type": "delta", "text": visible[len(shown_text):]})
                elif not visible.startswith(shown_text):
                    # Only reachable if cleaning rewrote text already on screen,
                    # which the holdback is designed to prevent. Nothing can be
                    # unsaid, so say so rather than leave a silent discrepancy.
                    logging.warning("guarded text diverged from what was streamed on %s", channel)
                if want_voice:
                    tail = _tts_clean(full[spoken:])
                    if tail: tts_tasks.append(asyncio.create_task(voice.synthesize(tail)))
                    for task in tts_tasks: await _send_audio(ws, await task)
                logstream.event(f"■ done [{channel}] · {len(visible)} chars"
                                + (" · 🔊 voiced" if want_voice else ""))
                await ws.send_json({"type": "done"})
            except WebSocketDisconnect: raise  # client's gone — let the outer handler clean up
            except Exception:
                logging.exception("turn failed")  # details stay server-side
                await ws.send_json({"type": "error",
                    "message": "That one tripped me up — the rest of our chat is intact, try again."})
                await ws.send_json({"type": "done"})
    except WebSocketDisconnect: pass  # history persists; nothing to clean up
    except Exception:
        logging.exception("ws error")  # details stay server-side
        try: await ws.send_json({"type": "error", "message": "Something went wrong on my end — check the backend logs."})
        finally: await ws.close()
    finally: live.unregister(channel, ws)

@app.post("/voice/stt")
async def stt(file: UploadFile):
    return {"text": await voice.transcribe(await file.read(), filename=file.filename or "audio.webm")}

@app.post("/voice/tts")
async def tts(payload: dict):
    return Response(content=await voice.synthesize(payload["text"]), media_type="audio/wav")

OWW_BASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
# Allowlisted so a path can't be smuggled through the name, and so the cache
# only ever holds files we meant to fetch. melspectrogram + embedding_model are
# the shared front end of the pipeline; the rest are the wake words themselves.
OWW_MODELS = {"melspectrogram", "embedding_model", "alexa_v0.1", "hey_jarvis_v0.1",
              "hey_mycroft_v0.1", "hey_rhasspy_v0.1", "timer_v0.1", "weather_v0.1"}
# Custom wake words trained locally (openWakeWord's own training pipeline). These
# never exist on GitHub, so they're served straight from the cache and never
# fetched — a missing file means "not trained yet", not "download it".
OWW_CUSTOM_MODELS = {"hey_wednesday"}


@app.get("/voice/wakeword/{name}.onnx")
async def wakeword_model(name: str):
    """Serve an openWakeWord ONNX model, downloading it once on first request.

    The browser could fetch these from GitHub itself, but proxying keeps the
    page from talking to third parties, survives being offline after the first
    run, and matches how Piper and Kokoro voices already work.
    """
    from pathlib import Path
    from fastapi.responses import FileResponse
    if name not in OWW_MODELS and name not in OWW_CUSTOM_MODELS:
        raise HTTPException(404, f"unknown wake word model {name!r}")
    cache = Path(settings.voice_cache_dir).expanduser() / "wakeword"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{name}.onnx"
    if not path.exists():
        if name in OWW_CUSTOM_MODELS:
            raise HTTPException(404, f"{name}.onnx not trained yet")
        try:
            await voice._download(f"{OWW_BASE}/{name}.onnx", path)
        except Exception as exc:
            logging.warning("wake word model %s download failed: %s", name, exc)
            raise HTTPException(502, f"could not fetch {name}.onnx: {exc}") from exc
    return FileResponse(path, media_type="application/octet-stream")


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    asyncio.create_task(whatsapp.handle_webhook(payload))
    return JSONResponse({"status": "accepted"})

@app.post("/imessage/webhook")
async def imessage_webhook(request: Request):
    payload = await request.json()
    asyncio.create_task(imessage.handle_webhook(payload))
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
        except Exception:
            logging.exception("whatsapp status check failed")
            return {"status": "unreachable"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
