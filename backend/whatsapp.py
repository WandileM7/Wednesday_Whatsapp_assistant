"""WhatsApp channel: receives webhooks from the Baileys service, routes them
through the agent, and sends a reply back."""
from __future__ import annotations

import logging
import time

import httpx

from . import agent
from .config import settings

log = logging.getLogger(__name__)

_seen: dict[str, float] = {}
_rate: dict[str, list[float]] = {}
_DEDUPE_TTL = 300
_RATE_WINDOW = 60
_RATE_LIMIT = 30


def _allowed(sender: str) -> bool:
    now = time.time()
    bucket = [t for t in _rate.get(sender, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        _rate[sender] = bucket
        return False
    bucket.append(now)
    _rate[sender] = bucket
    return True


def _is_duplicate(message_id: str) -> bool:
    if not message_id:
        return False  # skip dedup for messages without an ID
    now = time.time()
    for k, t in list(_seen.items()):
        if now - t > _DEDUPE_TTL:
            _seen.pop(k, None)
    if message_id in _seen:
        return True
    _seen[message_id] = now
    return False


async def handle_webhook(payload: dict) -> dict:
    """Entry point called by FastAPI webhook handler."""
    if not settings.whatsapp_enabled:
        return {"status": "disabled"}

    message_id = payload.get("id") or payload.get("messageId") or ""
    sender = payload.get("from") or payload.get("chatId") or "unknown"
    text = (payload.get("body") or payload.get("text") or "").strip()

    if not text or _is_duplicate(message_id) or not _allowed(sender):
        return {"status": "skipped"}

    reply_text = await agent.reply(channel=f"wa:{sender}", user_text=text)
    await _send(sender, reply_text)
    return {"status": "ok", "reply": reply_text}


async def _send(chat_id: str, text: str) -> None:
    url = f"{settings.waha_url.rstrip('/')}/api/sendText"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, json={"chatId": chat_id, "text": text})
    except Exception as exc:
        log.warning("whatsapp send failed: %s", exc)
