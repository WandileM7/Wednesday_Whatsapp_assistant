"""The /ws handler is the app's primary path and had zero integration coverage.
Drive it with a fake WebSocket + the fake-Ollama seam: prove the happy path
streams deltas (markers stripped inline) and ends with done, and that ONE bad
turn reports an error but keeps the socket serving instead of dropping it."""
import json

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

import backend.main as main
from backend import agent, db, memory


def _ndjson(*msgs):
    return "\n".join(json.dumps(m) for m in msgs).encode()


@pytest.fixture(autouse=True)
def _quiet_background(monkeypatch):
    async def noop(*a, **k): pass
    monkeypatch.setattr(agent, "_summarize", noop)
    monkeypatch.setattr(memory, "extract", noop)
    yield
    agent._transport = None


class FakeWS:
    """Replays queued client messages, then behaves like a disconnect."""
    def __init__(self, messages, subprotocols=()):
        self._messages = list(messages)
        self.sent = []
        self.query_params = {}
        self.closed = False
        # chat_ws reads scope["subprotocols"] to negotiate the bearer/marker
        # protocols before accepting.
        self.scope = {"subprotocols": list(subprotocols)}

    async def accept(self, **kwargs): self.accepted_with = kwargs

    async def receive_text(self):
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect(1000)

    async def send_json(self, data): self.sent.append(data)

    async def close(self, code=1000): self.closed = True


def _fake_ollama(*bodies):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=bodies[min(len(calls) - 1, len(bodies) - 1)])
    return httpx.MockTransport(handler)


async def test_happy_path_streams_and_strips_markers_inline():
    await db.init(); await db.clear_messages(main.settings.default_user)
    agent._HISTORIES.pop(main.settings.default_user, None)
    agent._transport = _fake_ollama(
        _ndjson({"message": {"content": "[Sighing] I am "}},
                {"message": {"content": "alive and streaming."}}))

    ws = FakeWS([json.dumps({"type": "text", "text": "are you there?"})])
    await main.chat_ws(ws)

    kinds = [e["type"] for e in ws.sent]
    text = "".join(e["text"] for e in ws.sent if e["type"] == "delta")
    assert "delta" in kinds and kinds[-1] == "done"
    assert "[" not in text and "Sighing" not in text     # marker stripped inline
    assert text == "I am alive and streaming."
    assert not any(e["type"] == "error" for e in ws.sent)


async def test_one_failed_turn_keeps_the_socket_serving():
    await db.init(); await db.clear_messages(main.settings.default_user)
    agent._HISTORIES.pop(main.settings.default_user, None)
    agent._transport = _fake_ollama(_ndjson({"message": {"content": "second turn ok"}}))

    ws = FakeWS([
        json.dumps({"type": "audio", "audio_b64": "!!!not-valid-base64!!!"}),  # fails in-handler
        json.dumps({"type": "text", "text": "still there?"}),                  # must still work
    ])
    await main.chat_ws(ws)

    # first turn: an error event, but NO socket close
    assert any(e["type"] == "error" for e in ws.sent)
    assert not ws.closed
    # second turn streamed normally after the failure
    assert any(e["type"] == "delta" and "second turn ok" in e["text"] for e in ws.sent)
    assert [e["type"] for e in ws.sent].count("done") == 2
