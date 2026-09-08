#!/usr/bin/env python3
"""Pretend to be Asterisk, so a call can be tested with no Asterisk.

`backend/phone.py` does not know what is on the other end of its socket — it
reads AudioSocket frames and writes AudioSocket frames. So the cheapest honest
end-to-end test is a script that speaks the same protocol: connect, stream
audio in at 320 bytes per 20ms, write back whatever comes out.

    # talk to her with your own microphone
    python -m scripts.callsim --live

    # or send a wav and keep the reply
    python -m scripts.callsim --wav question.wav --out reply.wav

This exercises everything the real path does *except* Asterisk's opinion of the
pacing: framing, endpointing, transcription, the agent turn, TTS, the 8kHz
resample and barge-in. What it cannot tell you is whether the far end hears
distortion, because there is no far end. For that you need the Asterisk in
`docker-compose.yaml` under the `phone` profile and a softphone — still free,
still no hardware, and it puts real SIP and real RTP in the path.

It prints the number this whole exercise is about:

    first audio  1.9s   ← the caller heard nothing for this long

That figure is the one to collect across a dozen turns before choosing a phone
latency budget. `--live` reports it per turn; `--wav` reports it once.

Live mode needs sounddevice (`pip install sounddevice`), which is not a project
dependency — this is a dev tool, not part of the service.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import sys
import time
import wave

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from backend import phone  # noqa: E402

RATE = phone._RATE
FRAME = phone._FRAME_BYTES
FRAME_SECONDS = phone._FRAME_MS / 1000


def _read_wav(path: str) -> bytes:
    """Any WAV → the 8kHz mono PCM Asterisk would have sent."""
    with open(path, "rb") as fh:
        raw = fh.read()
    with wave.open(io.BytesIO(raw), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2):
            return w.readframes(w.getnframes())
    return phone.to_telephony(raw)          # resample through the same path she uses


def _write_wav(path: str, pcm: bytes) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


class Line:
    """One simulated call: frames out, frames in, timing kept."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.received = bytearray()
        self.first_audio_at: float | None = None
        self.turn_started: float | None = None
        self.on_audio = None                # optional callback for live playback
        self._task = asyncio.ensure_future(self._collect())

    async def _collect(self):
        while True:
            got = await phone.read_frame(self.reader)
            if got is None:
                return
            kind, payload = got
            if kind == phone._KIND_TERMINATE:
                return
            if kind != phone._KIND_AUDIO:
                continue
            if self.first_audio_at is None and self.turn_started is not None:
                self.first_audio_at = time.monotonic() - self.turn_started
                print(f"  first audio  {self.first_audio_at:.1f}s"
                      "   ← the caller heard nothing for this long")
            self.received += payload
            if self.on_audio:
                self.on_audio(payload)

    async def send(self, pcm: bytes, realtime: bool = True) -> None:
        """Stream PCM in. `realtime` paces it the way a live call would — which
        matters, because the endpointer measures silence in frames and a burst
        of 500 frames is not the same conversation as ten seconds of talking."""
        deadline = time.monotonic()
        for i in range(0, len(pcm), FRAME):
            chunk = pcm[i:i + FRAME].ljust(FRAME, b"\x00")
            self.writer.write(phone.frame(phone._KIND_AUDIO, chunk))
            if realtime:
                deadline += FRAME_SECONDS
                delay = deadline - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
        await self.writer.drain()

    async def silence(self, seconds: float) -> None:
        await self.send(b"\x00" * int(RATE * 2 * seconds))

    async def hangup(self) -> None:
        self.writer.write(phone.frame(phone._KIND_TERMINATE))
        await self.writer.drain()
        self.writer.close()
        self._task.cancel()


async def connect(host: str, port: int) -> Line:
    reader, writer = await asyncio.open_connection(host, port)
    # Asterisk identifies the channel first. phone.py logs it, so send one and
    # the server-side log lines can be matched to this call.
    writer.write(phone.frame(phone._KIND_UUID, bytes(range(16))))
    await writer.drain()
    return Line(reader, writer)


async def run_wav(args) -> int:
    pcm = _read_wav(args.wav)
    line = await connect(args.host, args.port)
    print(f"calling {args.host}:{args.port} with {len(pcm) / (RATE * 2):.1f}s of audio")
    # Lead-in silence gives the endpointer its 300ms calibration window on
    # something that is actually quiet.
    await line.silence(0.5)
    await line.send(pcm)
    # The clock starts here, not before the audio. Dead air is what the caller
    # experiences *after they stop talking*, and it includes the endpointer's
    # own silence window — that wait is part of what makes a call feel slow, so
    # measuring from the start of speech would flatter the number by however
    # long the question happened to be.
    line.turn_started = time.monotonic()
    await line.silence(args.silence + 0.5)          # let the turn end
    print("waiting for the reply...")
    quiet_since = time.monotonic()
    last = len(line.received)
    while time.monotonic() - quiet_since < args.wait:
        await asyncio.sleep(0.2)
        if len(line.received) != last:
            last, quiet_since = len(line.received), time.monotonic()
    await line.hangup()

    if not line.received:
        print("no audio came back. Is ENABLE_PHONE=true and the backend running?")
        return 1
    seconds = len(line.received) / (RATE * 2)
    print(f"got {seconds:.1f}s of speech back")
    if line.first_audio_at is not None:
        print(f"first audio: {line.first_audio_at:.1f}s")
    if args.out:
        _write_wav(args.out, bytes(line.received))
        print(f"wrote {args.out} — play it and listen for dropouts")
    return 0


async def run_live(args) -> int:
    try:
        import sounddevice as sd
    except ImportError:
        print("live mode needs: pip install sounddevice")
        return 1

    loop = asyncio.get_running_loop()
    line = await connect(args.host, args.port)
    outbound: asyncio.Queue[bytes] = asyncio.Queue()

    def on_mic(indata, frames, time_info, status):
        loop.call_soon_threadsafe(outbound.put_nowait, bytes(indata))

    speaker = sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16",
                                 blocksize=phone._FRAME_SAMPLES)
    speaker.start()
    line.on_audio = speaker.write

    mic = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                            blocksize=phone._FRAME_SAMPLES, callback=on_mic)
    mic.start()

    print(f"connected to {args.host}:{args.port} — talk. ctrl-c ends the call.")
    print("(headphones: without them she hears herself and barges in on herself,")
    print(" which is the echo problem that belongs in Asterisk, not in phone.py)")
    # Mirror of the server's endpointer, purely for the stopwatch: the moment
    # you stop talking is the moment the caller starts waiting.
    speaking, quiet = False, 0
    hangover = int(args.silence * 1000 / phone._FRAME_MS)
    try:
        while True:
            chunk = await outbound.get()
            if phone.rms(chunk) > args.floor:
                if not speaking:
                    speaking, line.first_audio_at = True, None
                quiet = 0
            elif speaking:
                quiet += 1
                if quiet >= hangover:
                    speaking, line.turn_started = False, time.monotonic()
            line.writer.write(phone.frame(phone._KIND_AUDIO, chunk.ljust(FRAME, b"\x00")))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        mic.stop(); speaker.stop()
        await line.hangup()
        print("\ncall ended")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--wav", help="speak this file down the line")
    ap.add_argument("--out", help="write her reply here as a wav")
    ap.add_argument("--live", action="store_true", help="use your microphone")
    ap.add_argument("--silence", type=float, default=1.0,
                    help="trailing silence that ends the turn (default: 1.0s)")
    ap.add_argument("--wait", type=float, default=6.0,
                    help="give up this long after her last frame (default: 6.0s)")
    ap.add_argument("--floor", type=int, default=500,
                    help="live mode: RMS above which you count as talking")
    args = ap.parse_args()

    if args.live:
        return asyncio.run(run_live(args))
    if not args.wav:
        ap.error("give it --wav FILE or --live")
    return asyncio.run(run_wav(args))


if __name__ == "__main__":
    raise SystemExit(main())
