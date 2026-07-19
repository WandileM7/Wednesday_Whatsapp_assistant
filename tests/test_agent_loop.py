"""Agent-loop evals against a scripted fake Ollama — no model, no network."""
import json

import httpx
import pytest

from backend import agent, db, memory


def _ndjson(*msgs):
    return "\n".join(json.dumps(m) for m in msgs).encode()


def _fake_ollama(script):
    """script: list of response bodies, one per /api/chat call, in order."""
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        body = script[min(len(calls) - 1, len(script) - 1)]
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler), calls


@pytest.fixture(autouse=True)
def _quiet_background(monkeypatch):
    async def noop(*a, **k): pass
    monkeypatch.setattr(agent, "_summarize", noop)
    monkeypatch.setattr(memory, "extract", noop)
    yield
    agent._transport = None


async def _run(user, text):
    events = []
    async for e in agent.stream_reply(user, text):
        events.append(e)
    return events


async def test_plain_reply_streams_and_persists():
    await db.init(); await db.clear_messages("e1")
    agent._HISTORIES.pop("e1", None)
    transport, calls = _fake_ollama([
        _ndjson({"message": {"content": "Hello "}}, {"message": {"content": "there."}}),
    ])
    agent._transport = transport
    events = await _run("e1", "hi")
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello there."
    saved = await db.recent_messages("e1")
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1]["content"] == "Hello there."
    # system prompt goes first, and history slice follows it
    assert calls[0]["messages"][0]["role"] == "system"


async def test_tool_round_trip_executes_and_feeds_back():
    await db.init(); await db.clear_messages("e2")
    agent._HISTORIES.pop("e2", None)
    transport, calls = _fake_ollama([
        _ndjson({"message": {"tool_calls": [
            {"function": {"name": "get_time", "arguments": {}}}]}}),
        _ndjson({"message": {"content": "Done."}}),
    ])
    agent._transport = transport
    events = await _run("e2", "what time is it?")
    assert {"type": "tool", "name": "get_time"} in events
    # second round must include the tool result message
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1 and "tool output" in tool_msgs[0]["content"]
    saved = await db.recent_messages("e2")
    assert [m["role"] for m in saved] == ["user", "assistant", "tool", "assistant"]


async def test_unknown_tool_reports_instead_of_crashing():
    await db.init(); await db.clear_messages("e3")
    agent._HISTORIES.pop("e3", None)
    transport, calls = _fake_ollama([
        _ndjson({"message": {"tool_calls": [
            {"function": {"name": "nonexistent_tool", "arguments": {}}}]}}),
        _ndjson({"message": {"content": "ok"}}),
    ])
    agent._transport = transport
    await _run("e3", "x")
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert "not registered" in tool_msgs[0]["content"]


async def test_tool_loop_bails_after_max_hops():
    await db.init(); await db.clear_messages("e4")
    agent._HISTORIES.pop("e4", None)
    transport, calls = _fake_ollama([
        _ndjson({"message": {"tool_calls": [
            {"function": {"name": "get_time", "arguments": {}}}]}}),
    ])  # same tool-call response forever
    agent._transport = transport
    events = await _run("e4", "loop forever")
    assert len(calls) == agent._MAX_TOOL_HOPS
    assert any("stuck in a tool loop" in e.get("text", "") for e in events)
