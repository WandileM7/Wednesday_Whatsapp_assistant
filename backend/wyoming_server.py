"""Wyoming server: Wednesday as a Home Assistant voice assistant.

Home Assistant's Assist pipeline is speech-to-text → conversation agent →
text-to-speech, each reachable over the Wyoming protocol. Wednesday already
*is* those three things, so one small TCP server turns every HA voice
satellite in the house into a Wednesday endpoint — same memory, same tools,
same persona as the web orb and WhatsApp.

Three services on one port:

    asr     faster-whisper, the same model the orb uses
    tts     whatever `voice.synthesize` picks (Fish → Kokoro → Piper)
    handle  the agent itself: HA sends a transcript, we send back the reply

Wyoming has no authentication — HA assumes a trusted LAN — so this stays off
unless you turn it on, and it should never be exposed beyond your network.
Identity: turns arrive as WYOMING_USER (default: the same user as the web UI),
so asking the kitchen speaker about your calendar works exactly as it should.
"""
from __future__ import annotations
import asyncio, io, logging, wave

from .config import settings

log = logging.getLogger(__name__)

_CHUNK = 4096              # bytes of PCM per outbound audio chunk
_MAX_AUDIO_SECONDS = 60    # cap a runaway stream before it eats RAM


def _info():
    from wyoming.info import (AsrModel, AsrProgram, Attribution, HandleModel,
                              HandleProgram, Info, TtsProgram, TtsVoice)
    attribution = Attribution(name="Wednesday",
                              url="https://github.com/WandileM7/Wednesday_Whatsapp_assistant")
    languages = [settings.wyoming_language]
    return Info(
        asr=[AsrProgram(
            name="wednesday-whisper", attribution=attribution, installed=True,
            description="faster-whisper speech-to-text",
            version=None,
            models=[AsrModel(name=settings.whisper_model, attribution=attribution,
                             installed=True, description=None, version=None,
                             languages=languages)])],
        tts=[TtsProgram(
            name="wednesday-voice", attribution=attribution, installed=True,
            description="Wednesday's voice (Fish, Kokoro or Piper)",
            version=None,
            voices=[TtsVoice(name="wednesday", attribution=attribution, installed=True,
                             description=None, version=None, languages=languages,
                             speakers=None)])],
        handle=[HandleProgram(
            name="wednesday", attribution=attribution, installed=True,
            description="Wednesday — memory, tools and all",
            version=None,
            models=[HandleModel(name="wednesday", attribution=attribution,
                                installed=True, description=None, version=None,
                                languages=languages)])],
    )


def _wav_from_pcm(pcm: bytes, rate: int, width: int, channels: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels); wav.setsampwidth(width); wav.setframerate(rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def _wav_parts(data: bytes) -> tuple[bytes, int, int, int]:
    """(pcm, rate, width, channels) from WAV bytes."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        return (wav.readframes(wav.getnframes()), wav.getframerate(),
                wav.getsampwidth(), wav.getnchannels())


def _handler_class():
    """Built lazily so the module imports fine without the wyoming package."""
    from wyoming.asr import Transcribe, Transcript
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.event import Event
    from wyoming.handle import Handled
    from wyoming.info import Describe
    from wyoming.server import AsyncEventHandler
    from wyoming.tts import Synthesize

    from . import agent, markers, voice

    class WednesdayHandler(AsyncEventHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pcm = bytearray()
            self._format = (16000, 2, 1)   # rate, width, channels — until told otherwise

        async def handle_event(self, event: Event) -> bool:
            if Describe.is_type(event.type):
                await self.write_event(_info().event())
                return True

            # --- intent handling: HA's pipeline hands us the user's words ----
            if Transcript.is_type(event.type):
                text = (Transcript.from_event(event).text or "").strip()
                if not text:
                    await self.write_event(Handled(text="").event())
                    return True
                reply = await agent.reply(surface="wyoming",
                                      channel=settings.wyoming_user or settings.default_user,
                                          user_text=text)
                await self.write_event(Handled(text=markers.strip(reply).strip()).event())
                return True

            # --- speech to text ----------------------------------------------
            if Transcribe.is_type(event.type):
                self._pcm.clear()
                return True
            if AudioStart.is_type(event.type):
                start = AudioStart.from_event(event)
                self._format = (start.rate, start.width, start.channels)
                self._pcm.clear()
                return True
            if AudioChunk.is_type(event.type):
                chunk = AudioChunk.from_event(event)
                self._format = (chunk.rate, chunk.width, chunk.channels)
                cap = chunk.rate * chunk.width * chunk.channels * _MAX_AUDIO_SECONDS
                if len(self._pcm) < cap:
                    self._pcm.extend(chunk.audio)
                return True
            if AudioStop.is_type(event.type):
                rate, width, channels = self._format
                wav = _wav_from_pcm(bytes(self._pcm), rate, width, channels)
                self._pcm.clear()
                text = await voice.transcribe(wav, filename="wyoming.wav") if len(wav) > 44 else ""
                await self.write_event(Transcript(text=text).event())
                return True

            # --- text to speech ----------------------------------------------
            if Synthesize.is_type(event.type):
                text = (Synthesize.from_event(event).text or "").strip()
                if not text:
                    return True
                pcm, rate, width, channels = _wav_parts(await voice.synthesize(text))
                await self.write_event(AudioStart(rate=rate, width=width,
                                                  channels=channels).event())
                for i in range(0, len(pcm), _CHUNK):
                    await self.write_event(AudioChunk(
                        rate=rate, width=width, channels=channels,
                        audio=pcm[i:i + _CHUNK]).event())
                await self.write_event(AudioStop().event())
                return True

            return True

    return WednesdayHandler


async def run() -> None:
    """Serve until cancelled. Safe to schedule unconditionally."""
    if not settings.enable_wyoming:
        return
    try:
        from wyoming.server import AsyncServer
    except ImportError:
        log.warning("ENABLE_WYOMING is set but the wyoming package isn't installed — "
                    "run: pip install wyoming")
        return
    handler = _handler_class()
    server = AsyncServer.from_uri(settings.wyoming_uri)
    log.info("wyoming server listening on %s (asr + tts + handle)", settings.wyoming_uri)
    try:
        await server.run(lambda reader, writer: handler(reader, writer))
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("wyoming server stopped")
