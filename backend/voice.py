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