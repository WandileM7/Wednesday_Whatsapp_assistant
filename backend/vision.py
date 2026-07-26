"""Vision: "look at this".

The browser already holds a camera open for hand tracking, so it pushes the
occasional frame over the websocket; the newest one per user is kept here in
RAM (never persisted — a camera frame is about as sensitive as data gets, and
there is no reason for it to outlive the question it answers).

The `look` tool then asks a vision model about that frame. Backend choice
mirrors backend/llm.py: a hosted OpenAI-compatible vision endpoint when
configured, otherwise a local Ollama VLM. Be honest about the local path — a
7B VLM on CPU takes minutes per image, so `VISION_MODEL` local is a
correctness fallback, not a usable experience. This is the one capability that
genuinely wants the GPU box.
"""
from __future__ import annotations

import base64
import binascii
import logging
import time

import httpx

from .config import settings

log = logging.getLogger(__name__)

# user -> (unix_ts, base64 jpeg). One frame each; a new one replaces the old.
_FRAMES: dict[str, tuple[float, str]] = {}
_FRAME_TTL = 60.0          # a minute-old frame is no longer "what I'm looking at"
_MAX_FRAME_BYTES = 4_000_000


def set_frame(user: str, image_b64: str) -> bool:
    """Store the newest camera frame for a user. False if it isn't usable."""
    if not image_b64 or len(image_b64) > _MAX_FRAME_BYTES:
        return False
    payload = image_b64.split(",", 1)[-1] if image_b64.startswith("data:") else image_b64
    try:  # validate now, so a bad frame fails here and not mid-conversation
        base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return False
    _FRAMES[user] = (time.time(), payload)
    return True


def get_frame(user: str) -> str | None:
    got = _FRAMES.get(user)
    if not got:
        return None
    when, payload = got
    if time.time() - when > _FRAME_TTL:
        _FRAMES.pop(user, None)
        return None
    return payload


def clear_frame(user: str) -> None:
    _FRAMES.pop(user, None)


def model() -> str:
    if settings.vision_model:
        return settings.vision_model
    from . import llm
    return settings.llm_model if llm.hosted() else "llava:7b"


async def describe(image_b64: str, question: str, *, transport=None) -> str:
    """Ask the vision model about one image. Returns prose, or a plain error."""
    from . import llm
    prompt = question.strip() or "Describe what you see, briefly."
    try:
        if llm.hosted():
            payload = {
                "model": model(), "stream": False,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}],
            }
            url = settings.llm_base_url.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
            async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=15),
                                         transport=transport) as c:
                r = await c.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            return (data["choices"][0]["message"]["content"] or "").strip()
        payload = {"model": model(), "stream": False,
                   "messages": [{"role": "user", "content": prompt,
                                 "images": [image_b64]}]}
        # Local VLMs on CPU are extremely slow; allow for it rather than
        # timing out halfway and reporting a false failure.
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30),
                                     transport=transport) as c:
            r = await c.post(f"{settings.ollama_host}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        return (data.get("message", {}).get("content") or "").strip()
    except Exception as exc:
        log.warning("vision call failed: %s", exc)
        return ""
