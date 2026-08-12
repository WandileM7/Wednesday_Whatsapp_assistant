"""Fish Audio streams WAV with placeholder 0xFFFFFFFF size fields, so the
header claims a ~48,000-second duration. _fix_wav_sizes rewrites the RIFF and
data chunk sizes to the real byte count without touching the audio payload."""
import io
import struct
import wave

from backend import voice


def _wav(n_frames: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x01" * n_frames)
    return buf.getvalue()


def _corrupt_sizes(wav: bytes) -> bytes:
    b = bytearray(wav)
    struct.pack_into("<I", b, 4, 0xFFFFFFFF)          # RIFF ChunkSize
    data = wav.find(b"data", 12)
    struct.pack_into("<I", b, data + 4, 0xFFFFFF00)   # data Subchunk2Size
    return bytes(b)


def test_fixes_bogus_sizes_without_touching_audio():
    good = _wav(1000)
    data = good.find(b"data", 12)
    audio = good[data + 8:]

    fixed = voice._fix_wav_sizes(_corrupt_sizes(good))

    assert struct.unpack_from("<I", fixed, 4)[0] == len(fixed) - 8
    assert struct.unpack_from("<I", fixed, data + 4)[0] == len(fixed) - (data + 8)
    assert fixed[data + 8:] == audio                  # payload untouched
    with wave.open(io.BytesIO(fixed)) as w:
        assert abs(w.getnframes() / w.getframerate() - 1000 / 44100) < 0.01


def test_leaves_a_correct_wav_unchanged():
    good = _wav(500)
    assert voice._fix_wav_sizes(good) == good


def test_ignores_non_riff_bytes():
    junk = b"not a wav at all, just bytes"
    assert voice._fix_wav_sizes(junk) == junk
