"""Approval flow: gated tools pause the turn and resume on the user's verdict."""
import json

import httpx
import pytest

from backend import agent, db, memory
from backend.agent import _decision


def _ndjson(*msgs):
    return "\n".join(json.dumps(m) for m in msgs).encode()


def _fake_ollama(script):
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, content=script[min(len(calls) - 1, len(script) - 1)])

    return httpx.MockTransport(handler), calls


@pytest.fixture(autouse=True)
def _quiet_background(monkeypatch):
    async def noop(*a, **k): pass
    monkeypatch.setattr(agent, "_summarize", noop)
    monkeypatch.setattr(memory, "extract", noop)
    yield
    agent._transport = None
    agent._PENDING.clear()


async def _run(user, text):
    return [e async for e in agent.stream_reply(user, text)]


def test_decision_words():
    assert _decision("yes") == "approve"
    assert _decision("Go ahead!") == "approve"
    assert _decision("always allow") == "always"
    assert _decision("no") == "deny"
    assert _decision("wait, use my work address instead") == "deny"


_RUN_CODE_CALL = _ndjson({"message": {"tool_calls": [
    {"function": {"name": "run_code", "arguments": {"code": "print(1)"}}}]}})


async def _fresh(user):
    await db.init(); await db.clear_messages(user)
    agent._HISTORIES.pop(user, None); agent._PENDING.pop(user, None)


async def test_gated_tool_pauses_and_approval_resumes():
    await _fresh("a1")
    transport, calls = _fake_ollama([_RUN_CODE_CALL, _ndjson({"message": {"content": "Ran it."}})])
    agent._transport = transport
    events = await _run("a1", "run some code")
    text = "".join(e.get("text", "") for e in events if e["type"] == "delta")
    assert "go-ahead" in text and "run_code" in text
    assert "a1" in agent._PENDING and len(calls) == 1  # paused before executing

    events = await _run("a1", "yes")
    assert "a1" not in agent._PENDING
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert "disabled" in tool_msgs[0]["content"]  # run_code executed (flag off)
    saved = await db.recent_messages("a1")
    assert saved[-1]["content"] == "Ran it."


async def test_deny_with_feedback_reaches_the_model():
    await _fresh("a2")
    transport, calls = _fake_ollama([_RUN_CODE_CALL, _ndjson({"message": {"content": "Fair enough."}})])
    agent._transport = transport
    await _run("a2", "run some code")
    await _run("a2", "no, that snippet looks wrong")
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert "declined" in tool_msgs[0]["content"]
    assert "snippet looks wrong" in tool_msgs[0]["content"]


async def test_always_allow_persists_and_skips_future_prompts():
    await _fresh("a3")
    transport, _ = _fake_ollama([_RUN_CODE_CALL, _ndjson({"message": {"content": "Done."}})])
    agent._transport = transport
    await _run("a3", "run some code")
    await _run("a3", "always allow")
    assert await db.is_tool_approved("a3", "run_code")

    # same gated call again: no pause this time
    transport2, calls2 = _fake_ollama([_RUN_CODE_CALL, _ndjson({"message": {"content": "Again."}})])
    agent._transport = transport2
    await _run("a3", "run it again")
    assert "a3" not in agent._PENDING
    assert len(calls2) == 2  # tool executed and second round happened


async def test_ungated_tools_never_pause():
    await _fresh("a4")
    transport, calls = _fake_ollama([
        _ndjson({"message": {"tool_calls": [{"function": {"name": "get_time", "arguments": {}}}]}}),
        _ndjson({"message": {"content": "It's now."}}),
    ])
    agent._transport = transport
    await _run("a4", "time?")
    assert "a4" not in agent._PENDING and len(calls) == 2
