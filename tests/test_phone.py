"""AudioSocket: the wire format, turn-taking, pacing and barge-in.

No Asterisk and no modem. Asterisk's side of AudioSocket is a TCP client that
writes 320-byte frames and reads them back, which is forty lines of test code —
so the whole call loop is exercised over a real socket with the model layers
faked, the same way tests/test_wyoming.py covers the Home Assistant path.

The one thing this cannot cover is whether Asterisk is happy with the pacing,
because "the far end hears distortion" is not observable from here. That is
what the first real call is for.
"""
import asyncio
import math
import socket
import struct
import wave
import io

import pytest

from backend import phone
from backend.config import settings

_FRAME = phone._FRAME_BYTES


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tone(frames: int, amplitude: int = 8000) -> bytes:
    """`frames` frames of a 440Hz sine — speech as far as an energy VAD cares."""
    samples = []
    for n in range(frames * phone._FRAME_SAMPLES):
        samples.append(int(amplitude * math.sin(2 * math.pi * 440 * n / phone._RATE)))
    return struct.pack(f"<{len(samples)}h", *samples)


def _silence(frames: int) -> bytes:
    return b"\x00" * (frames * _FRAME)


def _wav(seconds=0.5, rate=22050):
    """A TTS engine's output: not 8kHz, which is the point of to_telephony."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x01\x02" * int(rate * seconds))
    return buf.getvalue()


# --- wire format -------------------------------------------------------------

def test_frame_header_is_kind_then_big_endian_length():
    raw = phone.frame(0x10, b"\x00" * 320)
    assert raw[0] == 0x10
    # Big-endian: 320 is 0x0140, so the high byte comes first. Little-endian
    # here would announce 16385 bytes and the far end would wait forever.
    assert raw[1:3] == b"\x01\x40"
    assert len(raw) == 323


async def test_read_frame_returns_none_at_end_of_stream():
    reader = asyncio.StreamReader()
    reader.feed_data(phone.frame(0x01, b"abc"))
    reader.feed_eof()
    assert await phone.read_frame(reader) == (0x01, b"abc")
    assert await phone.read_frame(reader) is None


async def test_read_frame_survives_a_truncated_payload():
    """A dropped call mid-frame is a hang-up, not a crash."""
    reader = asyncio.StreamReader()
    reader.feed_data(phone.frame(0x10, b"\x00" * 320)[:100])
    reader.feed_eof()
    assert await phone.read_frame(reader) is None


# --- audio helpers -----------------------------------------------------------

def test_rms_separates_silence_from_a_tone():
    assert phone.rms(_silence(1)) == 0.0
    assert phone.rms(_tone(1)) > 1000


def test_to_telephony_resamples_to_exactly_8k_mono():
    pytest.importorskip("av")
    pcm = phone.to_telephony(_wav(seconds=1.0, rate=22050))
    # One second in, one second out — within a frame, since the resampler's
    # tail is allowed to round.
    assert abs(len(pcm) - phone._BYTES_PER_SECOND) < _FRAME


def test_pcm_to_wav_round_trips_at_telephony_rate():
    pcm = _tone(5)
    with wave.open(io.BytesIO(phone.pcm_to_wav(pcm)), "rb") as w:
        assert w.getframerate() == 8000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.readframes(w.getnframes()) == pcm


# --- endpointing -------------------------------------------------------------

def _feed(ep: phone.Endpointer, pcm: bytes) -> int | None:
    """Frame index at which the utterance ended, or None."""
    for i in range(0, len(pcm), _FRAME):
        if ep.feed(pcm[i:i + _FRAME]):
            return i // _FRAME
    return None


def test_endpointer_ends_a_turn_after_the_configured_silence():
    ep = phone.Endpointer(floor=100, silence_seconds=0.4)   # 20 frames
    # 15 frames of quiet calibration, speech, then silence.
    assert _feed(ep, _silence(15) + _tone(25) + _silence(19)) is None
    assert ep.feed(_silence(1)[:_FRAME]) is True


def test_endpointer_ignores_silence_before_anyone_speaks():
    """Otherwise the call opens by submitting an empty turn to the model."""
    ep = phone.Endpointer(floor=100, silence_seconds=0.2)
    assert _feed(ep, _silence(200)) is None


def test_endpointer_calibrates_its_floor_above_line_noise():
    """A noisy line must not read as continuous speech, which never ends a turn."""
    ep = phone.Endpointer(floor=10, silence_seconds=0.2)
    noise = _tone(15, amplitude=300)          # quiet hiss during calibration
    _feed(ep, noise)
    assert ep.floor > phone.rms(noise[:_FRAME])
    assert not ep.speech(phone.rms(noise[:_FRAME]))


# --- the call ----------------------------------------------------------------

class _Asterisk:
    """The other end of the socket: writes frames, collects what comes back."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.audio = bytearray()        # everything, keepalive silence included
        self.speech = bytearray()       # only frames that carry actual sound
        self._collector = asyncio.ensure_future(self._collect())

    async def _collect(self):
        while True:
            got = await phone.read_frame(self.reader)
            if got is None:
                return
            kind, payload = got
            if kind == phone._KIND_AUDIO:
                assert len(payload) == _FRAME, "Asterisk distorts anything but 320 bytes"
                self.audio += payload
                # The stream never stops, so "did she say anything" has to mean
                # something other than "did bytes arrive".
                if payload != phone._SILENCE:
                    self.speech += payload
            elif kind == phone._KIND_TERMINATE:
                return

    async def send(self, pcm: bytes):
        for i in range(0, len(pcm), _FRAME):
            self.writer.write(phone.frame(phone._KIND_AUDIO, pcm[i:i + _FRAME]))
        await self.writer.drain()

    async def hangup(self):
        self.writer.write(phone.frame(phone._KIND_TERMINATE))
        await self.writer.drain()
        self.writer.close()

    async def wait_for_speech(self, at_least: int, timeout: float = 5.0):
        for _ in range(int(timeout / 0.02)):
            if len(self.speech) >= at_least:
                return True
            await asyncio.sleep(0.02)
        return False


@pytest.fixture
async def call(monkeypatch):
    """A listening AudioSocket server with the model layers faked out."""
    from backend import agent, voice

    port = _free_port()
    monkeypatch.setattr(settings, "enable_phone", True)
    monkeypatch.setattr(settings, "phone_host", "127.0.0.1")
    monkeypatch.setattr(settings, "phone_port", port)
    monkeypatch.setattr(settings, "phone_user", "caller")
    monkeypatch.setattr(settings, "phone_greeting", "")
    monkeypatch.setattr(settings, "phone_silence_seconds", 0.1)
    monkeypatch.setattr(settings, "phone_noise_floor", 100)

    async def fake_transcribe(audio, filename="x.wav"): return "what time is it"

    async def fake_stream(channel, user_text, surface=None):
        assert surface == "phone"
        for word in ("It is ", "half four. ", "You are late. "):
            yield {"type": "delta", "text": word}

    # Long enough that pacing is observable: 2s is 100 frames, and a run
    # that fails to pace delivers all of them the moment they are queued.
    async def fake_synth(text): return _wav(seconds=2.0)

    monkeypatch.setattr(voice, "transcribe", fake_transcribe)
    monkeypatch.setattr(voice, "synthesize", fake_synth)
    monkeypatch.setattr(agent, "stream_reply", fake_stream)

    server = asyncio.ensure_future(phone.run())
    for _ in range(50):
        await asyncio.sleep(0.02)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            continue

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    client = _Asterisk(reader, writer)
    yield client

    await client.hangup()
    server.cancel()
    await asyncio.gather(server, return_exceptions=True)


async def test_a_spoken_turn_comes_back_as_paced_audio(call):
    pytest.importorskip("av")
    await call.send(_silence(15) + _tone(20) + _silence(10))
    assert await call.wait_for_speech(_FRAME * 10), "no audio came back"
    # Frame-aligned, because _Asterisk asserts every payload is exactly 320.
    assert len(call.speech) % _FRAME == 0


async def test_the_uuid_frame_is_recorded_not_treated_as_audio(call):
    call.writer.write(phone.frame(phone._KIND_UUID, b"\x11" * 16))
    await call.writer.drain()
    await call.send(_silence(15) + _tone(20) + _silence(10))
    assert await call.wait_for_speech(_FRAME)


async def test_unknown_frame_kinds_are_skipped_without_dropping_the_call(call):
    """DTMF and silence frames exist; an unrecognised kind is still framed."""
    call.writer.write(phone.frame(0x03, b"5"))
    await call.writer.drain()
    await call.send(_silence(15) + _tone(20) + _silence(10))
    assert await call.wait_for_speech(_FRAME)


async def test_playback_is_paced_at_real_time_not_dumped(call):
    """100 frames written at once is two seconds of audio in one syscall, and
    Asterisk does not want it that way.

    Timed as "how long to deliver a second of audio", not as a rate sampled
    part-way through: an unpaced run finishes before a sampling window even
    opens, so a windowed measurement reads zero and passes. This is the shape
    that fails when the sleep is removed.
    """
    pytest.importorskip("av")
    loop = asyncio.get_running_loop()
    await call.send(_silence(15) + _tone(20) + _silence(10))
    started = loop.time()
    assert await call.wait_for_speech(_FRAME * 50), "no audio came back"
    elapsed = loop.time() - started
    # 50 frames is one second of speech and cannot honestly arrive faster.
    # Half of that is generous room for the faked transcribe/synthesize hops.
    assert elapsed >= 0.5, f"a second of audio delivered in {elapsed:.2f}s"


# --- barge-in ----------------------------------------------------------------

def _talking_call() -> phone.Call:
    reader = asyncio.StreamReader()
    call = phone.Call(reader, None)
    call.endpointer = phone.Endpointer(floor=100)
    call.speaking = True
    call.playback.put_nowait((0, b"\x00" * _FRAME * 50))
    return call


def test_sustained_speech_over_her_drops_the_queued_audio(monkeypatch):
    monkeypatch.setattr(settings, "phone_barge_in", True)
    call = _talking_call()
    loud = _tone(1)[:_FRAME]
    for _ in range(phone._BARGE_FRAMES):
        call._on_audio(loud)
    assert call.epoch == 1
    assert call.playback.empty()


def test_one_loud_frame_is_a_click_not_an_interruption(monkeypatch):
    """A door closing must not cut her off mid-word."""
    monkeypatch.setattr(settings, "phone_barge_in", True)
    call = _talking_call()
    call._on_audio(_tone(1)[:_FRAME])
    call._on_audio(_silence(1)[:_FRAME])
    call._on_audio(_tone(1)[:_FRAME])
    assert call.epoch == 0
    assert not call.playback.empty()


def test_barge_in_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "phone_barge_in", False)
    call = _talking_call()
    for _ in range(phone._BARGE_FRAMES * 3):
        call._on_audio(_tone(1)[:_FRAME])
    assert call.epoch == 0


def test_audio_arriving_while_she_speaks_is_not_the_next_utterance(monkeypatch):
    """It is as likely to be her own voice echoing back as his."""
    monkeypatch.setattr(settings, "phone_barge_in", False)
    call = _talking_call()
    for _ in range(20):
        call._on_audio(_tone(1)[:_FRAME])
    assert call.utterances.empty()


class _Capture:
    """Collects written frames, split into speech and keepalive silence."""

    def __init__(self):
        self.speech, self.silence = [], []

    def write(self, data):
        payload = data[3:]
        (self.silence if payload == phone._SILENCE else self.speech).append(payload)

    async def drain(self):
        pass


async def test_stale_epoch_audio_is_never_written():
    """The core of barge-in: audio produced before the interruption is dropped
    on the way out rather than cancelled in flight."""
    call = phone.Call(asyncio.StreamReader(), None)
    call.playback.put_nowait((0, _tone(1)))        # audible, so it is countable
    call.epoch = 1                                 # interrupted since queueing

    cap = _Capture()
    call.writer = cap
    task = asyncio.ensure_future(call.transmit())
    await asyncio.sleep(0.1)
    call.done.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert cap.speech == []
    # ...but the line stayed up, which is the other half of the contract.
    assert cap.silence, "the socket went quiet, and Asterisk hangs up on that"


async def test_an_interrupt_mid_sentence_stops_the_write_there():
    """The case barge-in actually exists for: she is a second into a two-second
    sentence when he starts talking. Dropping the *queue* is not enough — the
    segment already being paced out has to stop mid-write."""
    call = phone.Call(asyncio.StreamReader(), None)
    call.playback.put_nowait((0, _tone(100)))               # 2 seconds of speech

    cap = _Capture()
    call.writer = cap
    task = asyncio.ensure_future(call.transmit())
    await asyncio.sleep(0.2)                                # ~10 frames in
    sent_before = len(cap.speech)
    call.interrupt()
    await asyncio.sleep(0.15)
    call.done.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert 0 < sent_before < 100, f"expected a partial segment, got {sent_before}"
    # A couple of frames of slack for the one already in flight; the point is
    # that the remaining ~90 were never spoken.
    assert len(cap.speech) <= sent_before + 2, (
        f"{len(cap.speech) - sent_before} speech frames written after the interrupt")
    # And she went back to keepalive rather than dropping the line.
    assert cap.silence


async def test_an_idle_call_keeps_sending_frames():
    """The regression a socket test could not have found on its own.

    app_audiosocket drops the call after 2000ms of receiving nothing:

        ERROR app_audiosocket.c: Reached timeout after 2000 ms of no activity

    Every turn takes longer than that to reach its first sentence, so a writer
    that stays quiet while it thinks hangs up on every caller before she
    answers. Idle has to be audible as silence, not as nothing.
    """
    call = phone.Call(asyncio.StreamReader(), None)
    cap = _Capture()
    call.writer = cap
    task = asyncio.ensure_future(call.transmit())
    await asyncio.sleep(0.5)                       # nothing queued the whole time
    call.done.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    # 0.5s at one frame per 20ms is ~25. Anything near that beats the timeout
    # with two orders of magnitude to spare; zero does not.
    assert len(cap.silence) >= 15, f"only {len(cap.silence)} frames in 0.5s idle"
    assert cap.speech == []


# --- latency -----------------------------------------------------------------

def test_latency_stats_reports_nothing_before_any_calls():
    phone._LATENCY_LOG.clear()
    assert phone.latency_stats() == {"turns": 0}


def test_latency_stats_summarises_recent_turns():
    phone._LATENCY_LOG.clear()
    for value in (0.9, 1.4, 3.2):
        phone._LATENCY_LOG.append(value)
    stats = phone.latency_stats()
    assert stats["turns"] == 3
    assert stats["median"] == 1.4
    assert stats["worst"] == 3.2


async def test_run_is_a_no_op_when_disabled(monkeypatch):
    """Startup schedules it unconditionally, like every other channel."""
    monkeypatch.setattr(settings, "enable_phone", False)
    await asyncio.wait_for(phone.run(), timeout=1)
