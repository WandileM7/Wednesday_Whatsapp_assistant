"""Voice pipeline.

STT: faster-whisper (models auto-download from Hugging Face on first use).
TTS: Fish Audio hosted voice when FISH_API_KEY is set, otherwise Piper
(local, free, auto-downloads from Hugging Face on first use). Piper also
serves as the fallback if a Fish request fails.
"""
from __future__ import annotations
import asyncio, io, logging, tempfile, wave
from pathlib import Path

import httpx
from . import markers
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


async def preload():
    """Load STT + TTS models ahead of the first request."""
    if settings.fish_api_key:
        try:  # open the TLS connection early so the first segment reuses it
            await _fish().get("/v1/tts")
        except Exception as exc:
            log.warning("Fish Audio warm-up connect failed: %s", exc)
    try:
        await _ensure_whisper()
        await _ensure_piper()
        log.info("voice models preloaded")
    except Exception:
        log.exception("voice preload failed; will retry lazily on first use")


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


_fish_client: httpx.AsyncClient | None = None


def _fish() -> httpx.AsyncClient:
    """Shared keep-alive client: the network path to Fish is flaky, so reuse
    connections instead of a TLS handshake per segment, and retry connects."""
    global _fish_client
    if _fish_client is None:
        _fish_client = httpx.AsyncClient(
            base_url="https://api.fish.audio",
            headers={
                "Authorization": f"Bearer {settings.fish_api_key}",
                "model": settings.fish_tts_model,
            },
            timeout=httpx.Timeout(60, connect=10),
            limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120),
            transport=httpx.AsyncHTTPTransport(retries=2),
        )
    return _fish_client


def _fix_wav_sizes(wav: bytes) -> bytes:
    """Correct RIFF/data chunk sizes to the actual byte count.

    Fish streams the WAV with placeholder 0xFFFFFFFF size fields, so the header
    declares a ~48,000-second duration for a two-second clip. Playback copes,
    but anything that trusts the header (a seek bar, a duration readout) shows
    nonsense. `data` is the final chunk, so rewriting both size fields to the
    real length is safe; if the layout isn't the expected RIFF/WAVE, leave it.
    """
    import struct
    if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        return wav
    data = wav.find(b"data", 12)
    if data == -1 or data + 8 > len(wav):
        return wav
    actual = len(wav) - (data + 8)
    if struct.unpack_from("<I", wav, data + 4)[0] == actual:
        return wav                               # already correct
    b = bytearray(wav)
    struct.pack_into("<I", b, 4, len(wav) - 8)   # RIFF ChunkSize
    struct.pack_into("<I", b, data + 4, actual)  # data Subchunk2Size
    return bytes(b)


async def _synthesize_fish(text: str) -> bytes:
    """Returns WAV bytes from the Fish Audio TTS API."""
    r = await _fish().post(
        "/v1/tts",
        json={
            "text": text,
            "reference_id": settings.fish_voice_id,
            "format": "wav",
            "normalize": True,           # smoother numbers, dates, abbreviations
            "latency": "normal",         # quality over first-byte latency
            "prosody": {"speed": settings.fish_speed},
        },
    )
    r.raise_for_status()
    return _fix_wav_sizes(r.content)


def _wav_to_opus_ogg(wav: bytes) -> bytes:
    """WhatsApp voice notes are ogg/opus; encode via PyAV (bundled ffmpeg)."""
    import av
    from av.audio.resampler import AudioResampler
    inp = av.open(io.BytesIO(wav))
    buf = io.BytesIO()
    out = av.open(buf, "w", format="ogg")
    stream = out.add_stream("libopus", rate=48000)
    resampler = AudioResampler(format="s16", layout="mono", rate=48000)
    for frame in inp.decode(audio=0):
        for rf in resampler.resample(frame):
            for pkt in stream.encode(rf):
                out.mux(pkt)
    for pkt in stream.encode(None):
        out.mux(pkt)
    out.close(); inp.close()
    return buf.getvalue()


async def synthesize_voice_note(text: str) -> bytes:
    """Ogg/opus audio suitable for a WhatsApp voice note."""
    wav = await synthesize(text)
    return await asyncio.to_thread(_wav_to_opus_ogg, wav)


async def synthesize(text: str) -> bytes:
    """Returns WAV bytes."""
    if settings.fish_api_key:
        try:
            return await _synthesize_fish(text)
        except Exception:
            log.exception("Fish Audio TTS failed; falling back to Piper")
    text = markers.strip(text).strip()  # Piper would read "[sighing]" out loud
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
