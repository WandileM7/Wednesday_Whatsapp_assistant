"""Wyoming server: the three services Home Assistant's Assist pipeline needs,
exercised over a real socket with a real Wyoming client."""
import asyncio
import io
import socket
import wave

import pytest

from backend import wyoming_server
from backend.config import settings

pytest.importorskip("wyoming")

from wyoming.asr import Transcript                                    # noqa: E402
from wyoming.audio import AudioChunk, AudioStart, AudioStop           # noqa: E402
from wyoming.client import AsyncTcpClient                             # noqa: E402
from wyoming.handle import Handled                                    # noqa: E402
from wyoming.info import Describe, Info                               # noqa: E402
from wyoming.tts import Synthesize                                    # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wav(seconds=0.1, rate=22050):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"\x01\x02" * int(rate * seconds))
    return buf.getvalue()


@pytest.fixture
async def server(monkeypatch):
    """A running server with the model layers faked out."""
    from backend import agent, voice
    port = _free_port()
    monkeypatch.setattr(settings, "enable_wyoming", True)
    monkeypatch.setattr(settings, "wyoming_uri", f"tcp://127.0.0.1:{port}")
    monkeypatch.setattr(settings, "wyoming_user", "kitchen")

    async def fake_reply(channel, user_text, surface=None): return f"{channel} heard {user_text}"
    async def fake_synth(text): return _wav()
    async def fake_transcribe(audio, filename="x.wav"): return f"{len(audio)} bytes of audio"
    monkeypatch.setattr(agent, "reply", fake_reply)
    monkeypatch.setattr(voice, "synthesize", fake_synth)
    monkeypatch.setattr(voice, "transcribe", fake_transcribe)

    task = asyncio.create_task(wyoming_server.run())
    for _ in range(50):                      # wait for the listener to bind
        await asyncio.sleep(0.02)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            continue
    yield f"tcp://127.0.0.1:{port}"
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_describe_advertises_all_three_services(server):
    async with AsyncTcpClient.from_uri(server) as client:
        await client.write_event(Describe().event())
        info = Info.from_event(await client.read_event())
    assert info.asr and info.tts and info.handle
    assert info.handle[0].name == "wednesday"


async def test_a_transcript_is_answered_by_the_agent(server):
    async with AsyncTcpClient.from_uri(server) as client:
        await client.write_event(Transcript(text="what's on my calendar").event())
        handled = Handled.from_event(await client.read_event())
    # WYOMING_USER routes the turn, so the kitchen speaker shares one brain.
    assert handled.text == "kitchen heard what's on my calendar"


async def test_empty_transcripts_are_answered_without_bothering_the_model(server):
    async with AsyncTcpClient.from_uri(server) as client:
        await client.write_event(Transcript(text="   ").event())
        assert Handled.from_event(await client.read_event()).text == ""


async def test_streamed_audio_comes_back_as_a_transcript(server):
    async with AsyncTcpClient.from_uri(server) as client:
        await client.write_event(AudioStart(rate=16000, width=2, channels=1).event())
        for _ in range(3):
            await client.write_event(AudioChunk(rate=16000, width=2, channels=1,
                                                audio=b"\x00\x01" * 800).event())
        await client.write_event(AudioStop().event())
        transcript = Transcript.from_event(await client.read_event())
    assert transcript.text.endswith("bytes of audio")


async def test_synthesize_streams_a_wav_back(server):
    async with AsyncTcpClient.from_uri(server) as client:
        await client.write_event(Synthesize(text="Evening.").event())
        start = AudioStart.from_event(await client.read_event())
        total = 0
        while True:
            event = await client.read_event()
            if AudioStop.is_type(event.type):
                break
            total += len(AudioChunk.from_event(event).audio)
    assert (start.rate, start.width, start.channels) == (22050, 2, 1)
    assert total == len(_wav()) - 44          # every PCM byte, header excluded


async def test_disabled_server_never_binds(monkeypatch):
    monkeypatch.setattr(settings, "enable_wyoming", False)
    await asyncio.wait_for(wyoming_server.run(), timeout=1)   # returns immediately
