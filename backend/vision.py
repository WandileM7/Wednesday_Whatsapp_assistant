"""Vision: describe images with a local VLM through Ollama.

Moondream is the default — ~2B params, runs in under 4GB of VRAM (and on CPU,
slowly), which keeps the zero-cost, runs-on-your-machine promise intact. Any
Ollama vision model works: `VISION_MODEL=qwen3-vl` or `llama3.2-vision` if you
have the headroom.

The chat model stays text-only. Images are described by the VLM and the
*description* enters the conversation, so a photo sent on WhatsApp costs one
extra local call rather than a whole multimodal chat stack.
"""
from __future__ import annotations
import base64, logging

import httpx
from .config import settings

log = logging.getLogger(__name__)

DEFAULT_PROMPT = ("Describe this image. Be specific about people, places, objects "
                  "and mood. If it contains text, transcribe it verbatim.")
_MAX_BYTES = 12 * 1024 * 1024      # refuse absurd uploads before base64 tripling


async def _ask(image_b64: str, prompt: str) -> str | None:
    """One VLM call. None means the call failed; "" means it answered nothing."""
    payload = {"model": settings.vision_model, "stream": False, "keep_alive": "5m",
               "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
               "options": {"temperature": 0.2, "num_predict": 400}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15)) as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
            if r.status_code == 404:
                log.warning("vision: model %s not pulled — run: ollama pull %s",
                            settings.vision_model, settings.vision_model)
                return None
            r.raise_for_status()
        return (r.json().get("message", {}).get("content") or "").strip()
    except Exception:
        log.exception("vision: describe failed")
        return None


async def describe(image: bytes, question: str = "") -> str:
    """Returns a description, or "" if vision is off or the model is missing."""
    if not settings.enable_vision or not image:
        return ""
    if len(image) > _MAX_BYTES:
        log.warning("vision: image too large (%d bytes)", len(image))
        return ""
    image_b64 = base64.b64encode(image).decode()
    answer = await _ask(image_b64, question or DEFAULT_PROMPT)
    if answer == "" and question:
        # moondream answers "Describe the square." but returns nothing at all
        # for "What colour is the square?" — same image, same model, empty
        # content with done_reason=stop. A caption reliably works and usually
        # contains the answer, so fall back to one rather than dead-ending.
        log.info("vision: %r returned nothing; falling back to a description",
                 question[:60])
        answer = await _ask(image_b64, DEFAULT_PROMPT)
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
