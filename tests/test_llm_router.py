"""Model router: OpenAI-compatible streaming, tool-call fragment assembly,
history sanitising, and the fall-back-to-local promise.

No network: httpx.MockTransport serves both backends, dispatching on URL so a
single handler can fail the hosted call and still serve Ollama.
"""
import json

import httpx
import pytest

from backend import agent, db, llm, memory
from backend.config import settings


@pytest.fixture
def as_hosted(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://fast.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "k-test")
    monkeypatch.setattr(settings, "llm_model", "fast-70b")


def _sse(*objs, done=True):
    body = "".join(f"data: {json.dumps(o)}\n\n" for o in objs)
    return (body + ("data: [DONE]\n\n" if done else "")).encode()


def _ndjson(*msgs):
    return "\n".join(json.dumps(m) for m in msgs).encode()


def _delta(**d):
    return {"choices": [{"delta": d}]}


async def _drain(messages, tools=None, transport=None):
    return [e async for e in llm.stream_chat(messages, tools or [], transport=transport)]


# ---- provider selection -----------------------------------------------------

def test_local_by_default():
    assert llm.hosted() is False
    assert llm.describe().startswith("ollama:")


def test_hosted_when_configured(as_hosted):
    assert llm.hosted() is True
    assert llm.describe() == "hosted:fast-70b"


def test_key_without_url_stays_local(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "k")
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert llm.hosted() is False


# ---- OpenAI streaming -------------------------------------------------------

async def test_streams_content_deltas(as_hosted):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=_sse(_delta(content="Twenty-"),
                                                _delta(content="three.")))

    events = await _drain([{"role": "user", "content": "weather?"}],
                          transport=httpx.MockTransport(handler))
    assert seen["url"] == "https://fast.test/v1/chat/completions"
    assert seen["auth"] == "Bearer k-test"
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Twenty-", "three."]
    assert events[-1]["message"]["content"] == "Twenty-three."


async def test_assembles_fragmented_tool_call(as_hosted):
    """Name arrives once, JSON arguments in pieces — they must concatenate."""
    def handler(request):
        return httpx.Response(200, content=_sse(
            _delta(tool_calls=[{"index": 0, "id": "call_1",
                                "function": {"name": "get_weather", "arguments": ""}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": '{"loc'}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": 'ation": "Oslo"}'}}]),
        ))

    events = await _drain([{"role": "user", "content": "weather in Oslo?"}],
                          transport=httpx.MockTransport(handler))
    calls = events[-1]["message"]["tool_calls"]
    assert len(calls) == 1
    assert calls[0]["id"] == "call_1"
    assert calls[0]["function"]["name"] == "get_weather"
    assert json.loads(calls[0]["function"]["arguments"]) == {"location": "Oslo"}


async def test_parallel_tool_calls_keep_their_slots(as_hosted):
    def handler(request):
        return httpx.Response(200, content=_sse(
            _delta(tool_calls=[{"index": 0, "id": "a",
                                "function": {"name": "get_time", "arguments": "{}"}},
                               {"index": 1, "id": "b",
                                "function": {"name": "list_people", "arguments": "{}"}}]),
        ))

    events = await _drain([{"role": "user", "content": "hi"}],
                          transport=httpx.MockTransport(handler))
    names = [c["function"]["name"] for c in events[-1]["message"]["tool_calls"]]
    assert names == ["get_time", "list_people"]


async def test_ignores_keepalive_and_malformed_lines(as_hosted):
    def handler(request):
        body = (b": keep-alive\n\n"
                + b"data: not-json\n\n"
                + _sse(_delta(content="ok")))
        return httpx.Response(200, content=body)

    events = await _drain([{"role": "user", "content": "x"}],
                          transport=httpx.MockTransport(handler))
    assert events[-1]["message"]["content"] == "ok"


# ---- fallback ---------------------------------------------------------------

async def test_falls_back_to_ollama_when_hosted_fails_cold(as_hosted):
    def handler(request):
        if "chat/completions" in str(request.url):
            return httpx.Response(500, content=b"nope")
        return httpx.Response(200, content=_ndjson(
            {"message": {"content": "local answer"}, "done": True}))

    events = await _drain([{"role": "user", "content": "x"}],
                          transport=httpx.MockTransport(handler))
    assert events[-1]["message"]["content"] == "local answer"


class _DropsMidStream(httpx.AsyncByteStream):
    """Yields real SSE bytes, then the connection dies."""
    def __init__(self, *chunks): self._chunks = chunks
    async def __aiter__(self):
        for c in self._chunks:
            yield c
        raise httpx.ReadError("connection dropped")


async def test_no_fallback_after_output_already_streamed(as_hosted):
    """Mid-stream failure must propagate: the user has already seen tokens, so
    silently restarting on another backend would duplicate the answer."""
    hits = []

    def handler(request):
        hits.append(str(request.url))
        if "chat/completions" in str(request.url):
            return httpx.Response(200, stream=_DropsMidStream(
                b"data: " + json.dumps(_delta(content="partial")).encode() + b"\n\n"))
        return httpx.Response(200, content=_ndjson({"message": {"content": "local"}}))

    got = []
    with pytest.raises(httpx.ReadError):
        async for e in llm.stream_chat([{"role": "user", "content": "x"}], [],
                                       transport=httpx.MockTransport(handler)):
            got.append(e)

    assert [e["text"] for e in got if e["type"] == "delta"] == ["partial"]
    assert not any("api/chat" in u for u in hits)  # never fell back to Ollama


# ---- history sanitising -----------------------------------------------------

def test_sanitize_keeps_matched_call_and_result():
    msgs = [
        {"role": "user", "content": "weather?"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "get_weather",
                                                  "arguments": '{"location":"Oslo"}'}}]},
        {"role": "tool", "name": "get_weather", "tool_call_id": "c1", "content": "3C"},
    ]
    out = llm._sanitize(msgs)
    assert out[1]["tool_calls"][0]["id"] == "c1"
    assert out[1]["tool_calls"][0]["type"] == "function"
    assert out[2] == {"role": "tool", "tool_call_id": "c1", "content": "3C"}


def test_sanitize_demotes_orphaned_history():
    """Replayed from the db, tool results have lost their id — the pair must be
    demoted to text rather than sent as a schema violation."""
    msgs = [
        {"role": "assistant", "content": "",
         "tool_calls": [{"function": {"name": "get_weather", "arguments": "{}"}}]},
        {"role": "tool", "name": "get_weather", "content": "3C"},
        {"role": "user", "content": "and tomorrow?"},
    ]
    out = llm._sanitize(msgs)
    assert all("tool_calls" not in m for m in out)
    assert all(m["role"] != "tool" for m in out)
    assert "get_weather" in out[0]["content"]
    assert "3C" in out[1]["content"]
    assert out[-1] == {"role": "user", "content": "and tomorrow?"}


def test_sanitize_serialises_dict_arguments():
    # Ollama hands back dict arguments; OpenAI requires a JSON string
    msgs = [
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": {"a": 1}}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    out = llm._sanitize(msgs)
    assert out[0]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'


def test_sanitize_drops_empty_assistant_noise():
    out = llm._sanitize([{"role": "assistant", "content": ""},
                         {"role": "user", "content": "hi"}])
    assert out == [{"role": "user", "content": "hi"}]


# ---- end to end through the agent ------------------------------------------

async def test_agent_turn_runs_over_the_hosted_backend(as_hosted, monkeypatch):
    async def noop(*a, **k): pass
    monkeypatch.setattr(agent, "_summarize", noop)
    monkeypatch.setattr(memory, "extract", noop)
    await db.init()
    await db.clear_messages("h1")
    agent._HISTORIES.pop("h1", None)

    def handler(request):
        assert "chat/completions" in str(request.url)
        return httpx.Response(200, content=_sse(_delta(content="[calm] Fine.")))

    agent._transport = httpx.MockTransport(handler)
    try:
        out = [e async for e in agent.stream_reply("h1", "hello")]
    finally:
        agent._transport = None
    assert "".join(e["text"] for e in out if e["type"] == "delta") == "[calm] Fine."
