from __future__ import annotations
import logging, time
import httpx
from . import agent, markers
from .config import settings

log = logging.getLogger(__name__)
_seen: dict[str, float] = {}
_rate: dict[str, list[float]] = {}
_DEDUPE_TTL = 300; _RATE_WINDOW = 60; _RATE_LIMIT = 30

def _jid_allowed(sender):
    allowed = {j.strip() for j in settings.whatsapp_allowed_jids.split(",") if j.strip()}
    return not allowed or sender in allowed

def _user_key(sender):
    """The owner's WhatsApp shares the web identity; other senders get their own."""
    return settings.default_user if sender == settings.whatsapp_owner_jid else f"wa:{sender}"

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
    if "payload" in payload: payload = payload["payload"]  # Baileys wraps in {event, payload}
    message_id = payload.get("id") or payload.get("messageId") or ""
    sender = payload.get("from") or payload.get("chatId") or "unknown"
    text = (payload.get("body") or payload.get("text") or "").strip()
    if not _jid_allowed(sender):
        log.warning("blocked message from non-allowlisted sender %s", sender)
        return {"status": "forbidden"}
    if _is_duplicate(message_id) or not _allowed(sender): return {"status": "skipped"}

    is_voice = payload.get("type") == "voice" and message_id
    if is_voice:
        text = await _transcribe_note(message_id, payload.get("mimetype") or "audio/ogg")
    if not text: return {"status": "skipped"}

    reply_text = markers.strip(await agent.reply(channel=_user_key(sender), user_text=text)).strip()
    if is_voice and not await _send_voice(sender, reply_text):
        await _send(sender, reply_text)  # voice in, voice out — text as fallback
    elif not is_voice:
        await _send(sender, reply_text)
    return {"status": "ok", "reply": reply_text}

async def _transcribe_note(message_id: str, mimetype: str) -> str:
    from . import voice
    url = f"{settings.waha_url.rstrip('/')}/api/media/{message_id}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url); r.raise_for_status()
    except Exception as exc:
        log.warning("voice note fetch failed: %s", exc); return ""
    ext = "ogg" if "ogg" in mimetype else mimetype.rsplit("/", 1)[-1].split(";")[0] or "ogg"
    return await voice.transcribe(r.content, filename=f"note.{ext}")

async def _send_voice(chat_id: str, text: str) -> bool:
    import base64
    from . import voice
    try:
        audio = await voice.synthesize_voice_note(text)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{settings.waha_url.rstrip('/')}/api/sendAudio",
                json={"chatId": chat_id, "audio_b64": base64.b64encode(audio).decode()})
            r.raise_for_status()
        return True
    except Exception as exc:
        log.warning("voice note send failed, falling back to text: %s", exc)
        return False

async def _send(chat_id, text):
    url = f"{settings.waha_url.rstrip('/')}/api/sendText"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, json={"chatId": chat_id, "text": text})
    except Exception as exc:
        log.warning("whatsapp send failed: %s", exc)