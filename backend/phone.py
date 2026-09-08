"""Phone calls, over Asterisk's AudioSocket.

Wednesday does not speak SIP, and shouldn't. Asterisk owns the telephony —
registration, RTP, NAT traversal, codec negotiation, jitter buffering, and the
cellular modem if the call is coming off a SIM via chan_quectel. What it hands
us is `AudioSocket`: a plain TCP connection carrying one frame per 20ms.

    3-byte header — 1 byte kind, 2 bytes length (big-endian) — then payload.
    Kind 0x10 is the audio: 8kHz, 16-bit signed linear, mono, little-endian.
    Which makes every audio payload exactly 320 bytes, and Asterisk means
    *exactly*: more or less per frame and the far end hears distortion.

That is the whole protocol. So this file is the same shape as
`wyoming_server.py` — a small socket server that maps a simple binary protocol
onto transcribe → agent → synthesize, sharing one memory and one persona with
every other surface. The dialplan side is one line:

    exten => s,1,AudioSocket(${UUID},127.0.0.1:8090)

Unauthenticated, exactly like Wyoming, and for the same reason: it is meant to
be reached from Asterisk on localhost. Keep the port off the internet.

Three things here are not plumbing, and they are the reason this is its own
module rather than another branch in main.py:

**Turn-taking has no client.** The browser runs a real VAD in
`frontend/src/hooks/useAssistant.js` and tells the backend when a turn ended. A
caller sends an unbroken stream of frames and nothing else, so the endpointing
happens here, on energy, at 50 decisions a second. It is deliberately crude:
its only job is deciding *when to cut*, and `voice.transcribe` passes
`vad_filter=True`, so faster-whisper re-trims the edges properly afterwards.
Two jobs, two accuracies — a real VAD here would be a torch dependency and a
model load to do work that is already being done downstream.

**Playback has to be paced, not written.** Writing a five-second reply in one
go hands Asterisk 250 frames at once. The clock is the protocol: one frame per
20ms, on a monotonic deadline that advances by a fixed 0.02 rather than
sleeping 0.02 per iteration, because the second form accumulates the scheduler's
lateness and the call drifts further behind real time the longer it runs.

**Latency stops being a preference and becomes the product.** `_speakable()`
cutting at the first sentence is what makes this feasible at all — first audio
lands after her first sentence, not her whole answer. But `route_latency_budget`
is 8.0s, which is fine when you are watching the orb think and fatal when you
are holding a phone. There is no policy here yet on purpose: every turn logs its
real first-audio latency, and the budget gets chosen from that distribution
rather than from a guess. See the note on `_LATENCY_LOG`.

What is deliberately *not* handled here: echo cancellation. If the far end's
audio leaks back into the inbound stream she can hear herself and barge in on
her own sentence. That belongs in Asterisk, which has the channel and the
hardware context to do it properly; the mitigation here is only that barge-in
needs sustained speech well above the noise floor, not a single loud frame.
"""
from __future__ import annotations

import asyncio
import io
import logging
import struct
import time
import wave
from collections import deque

from . import logstream, markers
from .config import settings

log = logging.getLogger(__name__)

# --- the wire format ---------------------------------------------------------
# Asterisk's app_audiosocket. Kinds we do not recognise are skipped rather than
# treated as an error: the protocol has grown kinds over releases (silence and
# DTMF among them) and an unknown 3-byte header is still perfectly framed, so
# there is nothing to resync and no reason to drop the call.
_KIND_TERMINATE = 0x00
_KIND_UUID = 0x01
_KIND_AUDIO = 0x10
_KIND_ERROR = 0xFF

_RATE = 8000              # telephony. Not negotiable — it is what SLIN means.
_WIDTH = 2                # 16-bit signed
_FRAME_MS = 20
_FRAME_SAMPLES = _RATE * _FRAME_MS // 1000          # 160
_FRAME_BYTES = _FRAME_SAMPLES * _WIDTH              # 320 — Asterisk wants this exactly
_BYTES_PER_SECOND = _RATE * _WIDTH                  # 16000
_SILENCE = b"\x00" * _FRAME_BYTES                   # keepalive; see Call.transmit

# Barge-in needs sustained speech, not one loud frame: a door closing or a click
# on the line is a single frame above the floor, and cutting her off mid-word
# for that is worse than not having barge-in at all.
_BARGE_FRAMES = 5                                   # 100ms
_BARGE_MARGIN = 2.0                                 # ...and twice the noise floor

# The endpointer calibrates against the start of the call rather than trusting a
# configured number, because line noise differs by an order of magnitude between
# a VoLTE modem and a SIP softphone on wifi.
_CALIBRATION_FRAMES = 15                            # 300ms


def frame(kind: int, payload: bytes = b"") -> bytes:
    """One AudioSocket frame. Length is big-endian — network order, not the
    little-endian the *payload* uses. Getting these two the same way round is
    the classic way to make this protocol produce silence instead of an error."""
    return struct.pack(">BH", kind, len(payload)) + payload


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Next (kind, payload), or None when the far end has gone."""
    try:
        head = await reader.readexactly(3)
    except (asyncio.IncompleteReadError, ConnectionError):
        return None
    kind, length = struct.unpack(">BH", head)
    if not length:
        return kind, b""
    try:
        return kind, await reader.readexactly(length)
    except (asyncio.IncompleteReadError, ConnectionError):
        return None


def rms(pcm: bytes) -> float:
    """Root-mean-square of one frame of signed 16-bit LE samples.

    Hand-rolled rather than `audioop.rms`, which does this in C and is right
    there in 3.11 — but audioop was deprecated in 3.11 and deleted in 3.13, and
    a call dropping the day the box upgrades Python is a bad trade for a loop
    that runs over 160 samples 50 times a second.
    """
    count = len(pcm) // _WIDTH
    if not count:
        return 0.0
    total = 0
    for (sample,) in struct.iter_unpack("<h", pcm[:count * _WIDTH]):
        total += sample * sample
    return (total / count) ** 0.5


class Endpointer:
    """Decides when the caller has stopped talking.

    Energy plus a hangover timer. The noise floor is measured from the first
    300ms of the call and then only ever raised, never lowered, because the
    thing that lowers a measured floor is the caller happening to be silent
    during a fade in line noise — after which every frame reads as speech and
    her turn never ends.
    """

    def __init__(self, floor: int | None = None, silence_seconds: float | None = None):
        self._configured = float(settings.phone_noise_floor if floor is None else floor)
        self.floor = self._configured
        self._silence_frames = int(
            (settings.phone_silence_seconds if silence_seconds is None else silence_seconds)
            * 1000 / _FRAME_MS)
        self._calibration: list[float] = []
        self._quiet = 0
        self.started = False

    def _calibrate(self, level: float) -> None:
        self._calibration.append(level)
        if len(self._calibration) < _CALIBRATION_FRAMES:
            return
        ordered = sorted(self._calibration)
        median = ordered[len(ordered) // 2]
        # 3x the median of a quiet line, floored at the configured value. If the
        # caller was already talking during calibration this comes out high and
        # the first turn needs a louder start — recoverable. The reverse (a floor
        # under the real noise) is not: it never ends a turn.
        self.floor = max(self._configured, median * 3)

    def speech(self, level: float) -> bool:
        return level > self.floor

    def feed(self, pcm: bytes) -> bool:
        """Push one frame. True when the utterance is complete."""
        level = rms(pcm)
        if len(self._calibration) < _CALIBRATION_FRAMES:
            self._calibrate(level)
            return False
        if self.speech(level):
            self.started = True
            self._quiet = 0
            return False
        if not self.started:
            return False            # leading silence isn't a turn
        self._quiet += 1
        return self._quiet >= self._silence_frames


def to_telephony(wav: bytes) -> bytes:
    """WAV from any TTS engine → raw 8kHz 16-bit mono PCM.

    The engines disagree about rate — Piper 22050, Kokoro 24000, Fish whatever
    it feels like — so this is not optional. PyAV rather than `audioop.ratecv`
    for the reason in `rms()`, and because voice.py already resamples through
    PyAV for WhatsApp voice notes, so it is a dependency this repo has already
    accepted rather than a new one.
    """
    import av
    from av.audio.resampler import AudioResampler

    inp = av.open(io.BytesIO(wav))
    resampler = AudioResampler(format="s16", layout="mono", rate=_RATE)
    out = bytearray()
    for frm in inp.decode(audio=0):
        for rf in resampler.resample(frm):
            # planes[0] can be padded past the real sample count; trusting its
            # length appends whatever was in the buffer, which is audible.
            out += bytes(rf.planes[0])[: rf.samples * _WIDTH]
    for rf in resampler.resample(None):          # flush
        out += bytes(rf.planes[0])[: rf.samples * _WIDTH]
    inp.close()
    return bytes(out)


def pcm_to_wav(pcm: bytes) -> bytes:
    """Wrap raw telephony PCM so voice.transcribe can read it."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(_WIDTH)
        w.setframerate(_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


# Every turn's first-audio latency, so the phone latency budget is chosen from
# measurement rather than argument. Deliberately in memory and deliberately
# small: this is a number to read off /doctor after a dozen real calls and then
# act on, not a metrics pipeline.
_LATENCY_LOG: deque[float] = deque(maxlen=100)


def latency_stats() -> dict:
    """First-audio latency across recent turns, in seconds."""
    if not _LATENCY_LOG:
        return {"turns": 0}
    ordered = sorted(_LATENCY_LOG)
    return {
        "turns": len(ordered),
        "median": round(ordered[len(ordered) // 2], 2),
        "worst": round(ordered[-1], 2),
        "budget": settings.route_latency_budget,
    }


class Call:
    """One call. Reader, writer and turn loop, sharing an epoch counter.

    The epoch is lifted straight from `useAssistant.js`, which solved this
    problem first for the orb: barge-in cannot cancel audio that has already
    been handed to the output, so instead every piece of audio is stamped with
    the epoch it was produced in and anything stale is dropped on the way out.
    Bumping the counter invalidates a whole turn's queued speech in one
    assignment, with no task cancellation and no partial-write races.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.uuid = ""
        self.epoch = 0
        self.endpointer = Endpointer()
        self.utterances: asyncio.Queue[bytes] = asyncio.Queue()
        self.playback: asyncio.Queue[tuple[int, bytes]] = asyncio.Queue()
        self.speaking = False
        self.done = asyncio.Event()
        self._buffer = bytearray()
        self._barge_run = 0
        self._max_bytes = settings.phone_max_utterance_seconds * _BYTES_PER_SECOND

    # --- inbound -------------------------------------------------------------
    async def receive(self) -> None:
        """Read frames until the call ends. Never blocks on the turn loop: if
        the model is slow the socket still has to be drained, or Asterisk's
        write buffer fills and the *inbound* direction stalls too."""
        while not self.done.is_set():
            got = await read_frame(self.reader)
            if got is None:
                break
            kind, payload = got
            if kind == _KIND_TERMINATE:
                break
            if kind == _KIND_UUID:
                self.uuid = payload.hex()
                continue
            if kind == _KIND_ERROR:
                log.warning("phone: asterisk reported an error on call %s", self.uuid)
                continue
            if kind != _KIND_AUDIO:
                continue            # silence, DTMF, anything added later
            self._on_audio(payload)
        self.done.set()

    def _on_audio(self, pcm: bytes) -> None:
        if self.speaking:
            self._maybe_barge(pcm)
            # Frames arriving while she talks are her own voice echoing back as
            # often as they are his, so they are not part of the next utterance.
            return
        if len(self._buffer) < self._max_bytes:
            self._buffer += pcm
        if self.endpointer.feed(pcm):
            utterance, self._buffer = bytes(self._buffer), bytearray()
            self.endpointer = Endpointer(floor=int(self.endpointer.floor))
            self.utterances.put_nowait(utterance)

    def _maybe_barge(self, pcm: bytes) -> None:
        if not settings.phone_barge_in:
            return
        if rms(pcm) > self.endpointer.floor * _BARGE_MARGIN:
            self._barge_run += 1
        else:
            self._barge_run = 0
        if self._barge_run < _BARGE_FRAMES:
            return
        self._barge_run = 0
        self.interrupt()

    def interrupt(self) -> None:
        """Drop everything queued for playback. Cheap and idempotent."""
        self.epoch += 1
        while not self.playback.empty():
            self.playback.get_nowait()
        log.info("phone: barge-in on call %s", self.uuid or "?")

    # --- outbound ------------------------------------------------------------
    async def transmit(self) -> None:
        """One frame every 20ms for the life of the call — speech when there is
        speech, silence when there is not.

        The silence is not padding, it is the thing that keeps the call up.
        `app_audiosocket` gives up on a socket that sends it nothing:

            ERROR app_audiosocket.c: Reached timeout after 2000 ms of no
            activity on AudioSocket connection

        and hangs up. A turn takes longer than two seconds to produce its first
        sentence more or less always — transcribe, then the model, then TTS —
        so a writer that only writes when it has something to say drops every
        call before she answers. Found against a real Asterisk; a socket-level
        test cannot see it, because a test harness has no opinion about being
        idle. This is why a continuous media stream is the normal shape for
        telephony and an event-driven one is not.
        """
        deadline = time.monotonic()
        current, offset, epoch = b"", 0, self.epoch
        while not self.done.is_set():
            if current and epoch != self.epoch:
                current, offset = b"", 0       # barged in on mid-segment
            if offset >= len(current):
                current, offset = b"", 0
                try:
                    epoch, current = self.playback.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                if current and epoch != self.epoch:
                    current = b""              # stale: queued before an interrupt
            if current:
                chunk = current[offset:offset + _FRAME_BYTES]
                offset += _FRAME_BYTES
                if len(chunk) < _FRAME_BYTES:
                    chunk += b"\x00" * (_FRAME_BYTES - len(chunk))
                self.speaking = True
            else:
                chunk = _SILENCE
                self.speaking = False
            try:
                self.writer.write(frame(_KIND_AUDIO, chunk))
                await self.writer.drain()
            except (ConnectionError, RuntimeError):
                self.done.set()
                return
            # Advance the deadline by a fixed step instead of sleeping a fixed
            # step, so a late wake-up is absorbed rather than added to every
            # frame after it.
            deadline += _FRAME_MS / 1000
            delay = deadline - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                # Behind real time. Yield so the reader still gets scheduled,
                # but do not sleep the debt off — that would make it permanent.
                await asyncio.sleep(0)

    async def say(self, text: str) -> None:
        """Synthesize and queue one segment, stamped with the current epoch."""
        from . import voice
        clean = voice._tts_clean(text)
        if not clean:
            return
        epoch = self.epoch
        try:
            pcm = to_telephony(await voice.synthesize(clean))
        except ImportError:
            log.warning("phone: PyAV is missing, so nothing can be resampled to "
                        "8kHz — run: pip install av")
            return
        except Exception:
            log.exception("phone: synthesis failed on call %s", self.uuid or "?")
            return
        if epoch == self.epoch:
            self.playback.put_nowait((epoch, pcm))

    # --- the turn loop -------------------------------------------------------
    async def converse(self) -> None:
        from . import agent, voice

        channel = settings.phone_user or settings.default_user
        if settings.phone_greeting:
            await self.say(settings.phone_greeting)

        while not self.done.is_set():
            getter = asyncio.ensure_future(self.utterances.get())
            ender = asyncio.ensure_future(self.done.wait())
            finished, pending = await asyncio.wait(
                {getter, ender}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if getter not in finished:
                break
            utterance = getter.result()

            started = time.monotonic()
            text = (await voice.transcribe(pcm_to_wav(utterance), filename="call.wav")).strip()
            if not text:
                continue
            logstream.event(f"▶ turn [phone] 📞 {text[:90]}" + ("…" if len(text) > 90 else ""))

            epoch = self.epoch
            chunks: list[str] = []
            spoken = 0
            first_audio: float | None = None
            try:
                async for event in agent.stream_reply(channel, text, surface="phone"):
                    if self.epoch != epoch:
                        break                 # he talked over her; abandon the turn
                    if event["type"] != "delta":
                        continue
                    chunks.append(event["text"])
                    whole = "".join(chunks)
                    end = voice._speakable(whole, spoken)
                    if end > spoken:
                        segment, spoken = markers.strip(whole[spoken:end]), end
                        await self.say(segment)
                        if first_audio is None:
                            first_audio = time.monotonic() - started
                if self.epoch == epoch:
                    tail = markers.strip("".join(chunks)[spoken:])
                    if tail.strip():
                        await self.say(tail)
                        if first_audio is None:
                            first_audio = time.monotonic() - started
            except Exception:
                log.exception("phone: turn failed on call %s", self.uuid or "?")
                continue

            if first_audio is not None:
                _LATENCY_LOG.append(first_audio)
                logstream.event(f"■ done [phone] · first audio {first_audio:.1f}s")
                if first_audio > settings.route_latency_budget:
                    log.warning("phone: %.1fs to first audio — the caller heard "
                                "that as dead air", first_audio)


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    call = Call(reader, writer)
    peer = writer.get_extra_info("peername")
    log.info("phone: call from %s", peer)
    logstream.event("📞 call connected")
    tasks = [asyncio.ensure_future(coro) for coro in
             (call.receive(), call.transmit(), call.converse())]
    try:
        await tasks[0]                        # receive() ending means the call ended
    finally:
        call.done.set()
        for task in tasks[1:]:
            task.cancel()
        await asyncio.gather(*tasks[1:], return_exceptions=True)
        try:
            writer.write(frame(_KIND_TERMINATE))
            await writer.drain()
        except (ConnectionError, RuntimeError):
            pass
        writer.close()
        log.info("phone: call %s ended", call.uuid or "?")
        logstream.event("📴 call ended")


async def run() -> None:
    """Serve until cancelled. Safe to schedule unconditionally."""
    if not settings.enable_phone:
        return
    server = await asyncio.start_server(_handle, settings.phone_host, settings.phone_port)
    log.info("phone: audiosocket listening on %s:%s",
             settings.phone_host, settings.phone_port)
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("phone server stopped")
