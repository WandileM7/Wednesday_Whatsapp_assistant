"""Vision: describing an image, wherever it came from.

Two sources feed this, and they arrive in different shapes:

  - A picture *sent* to Wednesday — a WhatsApp or iMessage attachment, or a URL
    handed to the `see_image` tool. Raw bytes, one-off, may be large.
  - A frame from a camera the browser already has open for hand tracking. The
    newest frame per user is kept here in RAM and answered by the `look` tool.
    Never persisted: a camera frame is about as sensitive as data gets and has
    no reason to outlive the question it answers.

Both end up at ``describe``, which takes bytes or base64 either way.

The chat model stays text-only. Images are described by a vision model and the
*description* enters the conversation, so a photo costs one extra call rather
than a whole multimodal chat stack. Backend choice mirrors backend/llm.py: a
hosted OpenAI-compatible vision endpoint when one is configured, otherwise a
local Ollama VLM. Be honest about the local path — moondream (~2B, under 4GB
of VRAM) is quick enough, but a 7B VLM on CPU takes minutes per image. Local
is a correctness fallback, not always a usable experience.
"""
from __future__ import annotations

import base64
import binascii
import logging
import time

import httpx

from .config import settings

log = logging.getLogger(__name__)

DEFAULT_PROMPT = ("Describe this image. Be specific about people, places, objects "
                  "and mood. If it contains text, transcribe it verbatim.")
_MAX_BYTES = 12 * 1024 * 1024      # refuse absurd uploads before base64 tripling

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
    """The vision model to use. Explicit setting wins; otherwise the hosted
    chat model (most are multimodal) or a local VLM.

    The local fallback is moondream because that is the one the documentation
    tells you to install — the README's stack table, the architecture diagram,
    the quick-start `ollama pull`, and .env.example all name it. This used to
    fall back to llava:7b instead, which nothing anywhere asks you to pull, so
    anyone who did not copy .env.example got "model not found" on their first
    photo. A default that disagrees with the install instructions is a bug even
    when both models would work.
    """
    if settings.vision_model:
        return settings.vision_model
    from . import llm
    return settings.llm_model if llm.hosted() else "moondream"


async def _ask(image_b64: str, prompt: str, *, transport=None) -> str | None:
    """One vision call. None means the call failed; "" means it answered nothing."""
    from . import llm
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
            return (r.json()["choices"][0]["message"]["content"] or "").strip()

        payload = {"model": model(), "stream": False, "keep_alive": "5m",
                   "messages": [{"role": "user", "content": prompt,
                                 "images": [image_b64]}],
                   "options": {"temperature": 0.2, "num_predict": 400}}
        # Local VLMs on CPU are extremely slow; allow for it rather than timing
        # out halfway and reporting a false failure.
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30),
                                     transport=transport) as c:
            r = await c.post(f"{settings.ollama_host}/api/chat", json=payload)
            if r.status_code == 404:
                log.warning("vision: model %s not pulled — run: ollama pull %s",
                            model(), model())
                return None
            r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()
    except Exception as exc:
        log.warning("vision call failed: %s", exc)
        return None


async def describe(image: bytes | str, question: str = "", *, transport=None) -> str:
    """Describe an image — raw bytes or an already-base64 frame.

    Returns "" if vision is off, the image is unusable, or the model is missing;
    a caller that has nothing to say is better than one that invents something.
    """
    if not settings.enable_vision or not image:
        return ""
    if isinstance(image, bytes):
        if len(image) > _MAX_BYTES:
            log.warning("vision: image too large (%d bytes)", len(image))
            return ""
        image_b64 = base64.b64encode(image).decode()
    else:
        image_b64 = image

    answer = await _ask(image_b64, question or DEFAULT_PROMPT, transport=transport)
    if answer == "" and question:
        # moondream answers "Describe the square." but returns nothing at all
        # for "What colour is the square?" — same image, same model, empty
        # content with done_reason=stop. A caption reliably works and usually
        # contains the answer, so fall back to one rather than dead-ending.
        log.info("vision: %r returned nothing; falling back to a description",
                 question[:60])
        answer = await _ask(image_b64, DEFAULT_PROMPT, transport=transport)
    return answer or ""


async def describe_url(url: str, question: str = "") -> str:
    """Fetch an image by URL and describe it."""
    if not url.startswith(("http://", "https://")):
        return ""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0 Wednesday/1.0"}) as client:
        r = await client.get(url)
        r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        return ""
    return await describe(r.content, question)
