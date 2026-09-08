"""TTS engine selection: which engine runs, and what happens when it fails.

Piper must always be the last resort — losing the voice entirely is a worse
failure than speaking in a plainer one."""
import pytest

from backend import voice
from backend.config import settings


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "fish_api_key", "")
    monkeypatch.setattr(settings, "enable_kokoro", False)
    monkeypatch.setattr(settings, "tts_engine", "")


def test_piper_alone_by_default():
    assert voice._engines() == ["piper"]


def test_fish_first_when_keyed(monkeypatch):
    monkeypatch.setattr(settings, "fish_api_key", "fk-test")
    assert voice._engines() == ["fish", "piper"]


def test_kokoro_sits_between_fish_and_piper(monkeypatch):
    monkeypatch.setattr(settings, "fish_api_key", "fk-test")
    monkeypatch.setattr(settings, "enable_kokoro", True)
    assert voice._engines() == ["fish", "kokoro", "piper"]


def test_forcing_an_engine_keeps_piper_as_the_net(monkeypatch):
    monkeypatch.setattr(settings, "tts_engine", "kokoro")
    assert voice._engines() == ["kokoro", "piper"]


def test_forcing_piper_needs_no_fallback(monkeypatch):
    monkeypatch.setattr(settings, "tts_engine", "piper")
    assert voice._engines() == ["piper"]


# ---- the fallback chain in practice -----------------------------------------

async def test_kokoro_failure_falls_through_to_piper(monkeypatch):
    monkeypatch.setattr(settings, "enable_kokoro", True)
    async def boom(text): raise RuntimeError("model file truncated")
    async def piper(text): return b"RIFF-piper"
    monkeypatch.setattr(voice, "_synthesize_kokoro", boom)
    monkeypatch.setattr(voice, "_synthesize_piper", piper)
    assert await voice.synthesize("Evening.") == b"RIFF-piper"


async def test_a_missing_package_is_a_warning_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "enable_kokoro", True)
    async def missing(text): raise ImportError("No module named 'kokoro_onnx'")
    async def piper(text): return b"RIFF-piper"
    monkeypatch.setattr(voice, "_synthesize_kokoro", missing)
    monkeypatch.setattr(voice, "_synthesize_piper", piper)
    assert await voice.synthesize("Evening.") == b"RIFF-piper"


async def test_markers_reach_fish_but_never_the_local_engines(monkeypatch):
    """Fish performs "[sighing]"; Piper and Kokoro would read it aloud."""
    monkeypatch.setattr(settings, "fish_api_key", "fk-test")
    seen = {}
    async def fish(text): seen["fish"] = text; raise RuntimeError("fish down")
    async def piper(text): seen["piper"] = text; return b"RIFF"
    monkeypatch.setattr(voice, "_synthesize_fish", fish)
    monkeypatch.setattr(voice, "_synthesize_piper", piper)
    await voice.synthesize("[sighing] Fine.")
    assert seen["fish"] == "[sighing] Fine."
    assert seen["piper"] == "Fine."


async def test_every_engine_failing_raises(monkeypatch):
    async def boom(text): raise RuntimeError("no voice at all")
    monkeypatch.setattr(voice, "_synthesize_piper", boom)
    with pytest.raises(RuntimeError, match="no voice at all"):
        await voice.synthesize("Evening.")


# ---- PCM conversion ---------------------------------------------------------

def test_float_samples_become_a_16bit_wav():
    import io, wave
    data = voice._pcm_wav([0.0, 0.5, -0.5, 1.0, -1.0], 24000)
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getsampwidth() == 2 and wav.getnchannels() == 1
        assert wav.getnframes() == 5


def test_out_of_range_samples_are_clipped_not_wrapped():
    import io, struct, wave
    data = voice._pcm_wav([2.0, -2.0], 16000)
    with wave.open(io.BytesIO(data), "rb") as wav:
        frames = wav.readframes(2)
    assert struct.unpack("<2h", frames) == (32767, -32767)
