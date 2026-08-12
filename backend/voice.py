"""Voice pipeline.

STT: faster-whisper (models auto-download from Hugging Face on first use).

TTS engines, tried in order (see `_engines`):

    fish    hosted, used when FISH_API_KEY is set
    kokoro  local, 82M params, ONNX — natural prosody, no key, no torch.
            Opt-in (ENABLE_KOKORO) because the model is a ~310MB download.
    piper   local, tiny, always the last resort so voice never hard-fails

Every engine falls through to the next on error, so a flaky network or a
half-downloaded model degrades the voice instead of losing it.
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
_kokoro = None
_lock = asyncio.Lock()

PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
KOKORO_BASE = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
               "model-files-v1.0")


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
    """Stream to a temp file, then rename: Kokoro's model is ~310MB, too big to
    hold in memory, and an interrupted download must not leave a corrupt file
    that looks cached."""
    log.info("downloading %s", url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    async with httpx.AsyncClient(timeout=httpx.Timeout(1800, connect=15),
                                 follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with tmp.open("wb") as fh:
                async for chunk in r.aiter_bytes(1 << 20):
                    fh.write(chunk)
    tmp.replace(dest)


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


async def _ensure_kokoro():
    """Load kokoro-onnx, fetching the model + voice pack on first use.

    kokoro-onnx (not the torch `kokoro` package) keeps this in the same shape
    as Piper: an ONNX file on disk, onnxruntime — which piper-tts already
    pulls in — doing the inference, and no GPU or API key involved.
    """
    global _kokoro
    if _kokoro is not None:
        return _kokoro
    async with _lock:
        if _kokoro is not None:
            return _kokoro
        from kokoro_onnx import Kokoro
        cache = Path(settings.voice_cache_dir).expanduser()
        cache.mkdir(parents=True, exist_ok=True)
        model, voices = cache / "kokoro-v1.0.onnx", cache / "voices-v1.0.bin"
        if not model.exists():
            await _download(f"{KOKORO_BASE}/kokoro-v1.0.onnx", model)
        if not voices.exists():
            await _download(f"{KOKORO_BASE}/voices-v1.0.bin", voices)
        _kokoro = await asyncio.to_thread(Kokoro, str(model), str(voices))
        log.info("kokoro loaded: voice=%s lang=%s", settings.kokoro_voice, settings.kokoro_lang)
        return _kokoro


def _pcm_wav(samples, rate: int) -> bytes:
    """Float samples in [-1, 1] → a 16-bit mono WAV, the format the WS channel
    and the opus encoder both already expect."""
    try:
        import numpy as np
        pcm = (np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
               * 32767).astype("<i2").tobytes()
    except ImportError:
        import array
        pcm = array.array("h", (max(-32768, min(32767, int(s * 32767)))
                                for s in samples)).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(int(rate))
        wav.writeframes(pcm)
    return buf.getvalue()


async def _synthesize_kokoro(text: str) -> bytes:
    kokoro = await _ensure_kokoro()

    def _run() -> bytes:
        samples, rate = kokoro.create(text, voice=settings.kokoro_voice,
                                      speed=settings.kokoro_speed, lang=settings.kokoro_lang)
        return _pcm_wav(samples, rate)

    return await asyncio.to_thread(_run)


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
        await _ensure_piper()      # the fallback, so always warm
        if settings.enable_kokoro:
            try:  # first call pulls ~310MB; better now than mid-sentence
                await _ensure_kokoro()
            except Exception:
                log.exception("kokoro preload failed; Piper will cover for it")
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


async def _synthesize_piper(text: str) -> bytes:
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


def _engines() -> list[str]:
    """Engines to try, best first. Piper is always appended: it's local, tiny
    and already on disk, so there's always something left to speak with."""
    if forced := settings.tts_engine.strip().lower():
        return [forced] if forced == "piper" else [forced, "piper"]
    order = []
    if settings.fish_api_key: order.append("fish")
    if settings.enable_kokoro: order.append("kokoro")
    return order + ["piper"]


async def synthesize(text: str) -> bytes:
    """Returns WAV bytes."""
    # Fish interprets emotion markers like "[sighing]"; the local engines would
    # read them out loud, so they get the stripped text.
    clean = markers.strip(text).strip()
    last: Exception | None = None
    for engine in _engines():
        try:
            if engine == "fish":
                return await _synthesize_fish(text)
            if engine == "kokoro":
                return await _synthesize_kokoro(clean)
            return await _synthesize_piper(clean)
        except ImportError as exc:  # engine enabled but its package isn't installed
            last = exc
            log.warning("%s TTS unavailable (%s) — falling back. Install it with: "
                        "pip install kokoro-onnx", engine, exc)
        except Exception as exc:  # noqa: BLE001 — try the next engine
            last = exc
            log.exception("%s TTS failed; falling back", engine)
    raise last or RuntimeError("no TTS engine configured")
