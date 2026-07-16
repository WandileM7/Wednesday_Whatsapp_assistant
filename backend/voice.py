"""Fully local, free voice pipeline.

STT: faster-whisper (models auto-download from Hugging Face on first use).
TTS: Piper (voice model auto-downloads from Hugging Face on first use).
No API keys, no billing.
"""
from __future__ import annotations
import asyncio, io, logging, tempfile, wave
from pathlib import Path

import httpx
from .config import settings

log = logging.getLogger(__name__)

_whisper = None
_piper = None
_lock = asyncio.Lock()

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_files() -> tuple[Path, Path, str]:
    """Local paths + remote subdir for a Piper voice like en_US-lessac-medium."""
    name = settings.piper_voice
    locale, voice, quality = name.split("-", 2)
    family = locale.split("_")[0]
    subdir = f"{family}/{locale}/{voice}/{quality}"
    cache = Path(settings.voice_cache_dir).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    return cache / f"{name}.onnx", cache / f"{name}.onnx.json", subdir


async def _download(url: str, dest: Path):
    log.info("downloading %s", url)
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        dest.write_bytes(r.content)


async def _ensure_piper():
    global _piper
    if _piper is not None:
        return _piper
    async with _lock:
        if _piper is not None:
            return _piper
        try:
            from piper import PiperVoice  # piper-tts >= 1.3
        except ImportError:
            from piper.voice import PiperVoice  # piper-tts 1.2.x
        model, config, subdir = _voice_files()
        name = settings.piper_voice
        if not model.exists():
            await _download(f"{PIPER_BASE}/{subdir}/{name}.onnx", model)
        if not config.exists():
            await _download(f"{PIPER_BASE}/{subdir}/{name}.onnx.json", config)
        _piper = await asyncio.to_thread(PiperVoice.load, str(model), str(config))
        return _piper


async def _ensure_whisper():
    global _whisper
    if _whisper is not None:
        return _whisper
    async with _lock:
        if _whisper is not None:
            return _whisper
        from faster_whisper import WhisperModel
        _whisper = await asyncio.to_thread(
            WhisperModel, settings.whisper_model, device="auto", compute_type="int8")
        return _whisper


async def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    model = await _ensure_whisper()

    def _run() -> str:
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio)
            path = tmp.name
        try:
            segments, _info = model.transcribe(path, vad_filter=True)
            return " ".join(s.text.strip() for s in segments).strip()
        finally:
            Path(path).unlink(missing_ok=True)

    return await asyncio.to_thread(_run)


async def synthesize(text: str) -> bytes:
    """Returns WAV bytes."""
    voice = await _ensure_piper()

    def _run() -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            if hasattr(voice, "synthesize_wav"):  # piper-tts >= 1.3
                voice.synthesize_wav(text, wav)
            else:
                voice.synthesize(text, wav)
        return buf.getvalue()

    return await asyncio.to_thread(_run)
