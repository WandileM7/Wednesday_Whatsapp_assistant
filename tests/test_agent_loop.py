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


# ---- argument coercion ------------------------------------------------------
# Small local models emit JSON scalars as strings. llama3.2:3b answered "remind
# me in 45 minutes" with in_minutes="45", timedelta raised TypeError, and the
# model then told the user the reminder was set. Silent wrongness, so these
# guard the coercion that prevents it.

_SCHEMA = {"type": "object", "properties": {
    "n": {"type": "integer"}, "x": {"type": "number"},
    "flag": {"type": "boolean"}, "text": {"type": "string"}}}


def test_stringified_integers_are_coerced():
    assert agent._coerce({"n": "45"}, _SCHEMA) == {"n": 45}


def test_integers_written_with_a_decimal_point_still_work():
    assert agent._coerce({"n": "45.0"}, _SCHEMA) == {"n": 45}


def test_negative_integers_survive():
    assert agent._coerce({"n": "-3"}, _SCHEMA) == {"n": -3}


def test_numbers_and_booleans_are_coerced():
    out = agent._coerce({"x": "1.5", "flag": "true"}, _SCHEMA)
    assert out == {"x": 1.5, "flag": True}


def test_falsey_boolean_spellings():
    assert agent._coerce({"flag": "false"}, _SCHEMA)["flag"] is False
    assert agent._coerce({"flag": "no"}, _SCHEMA)["flag"] is False


def test_strings_are_left_alone():
    assert agent._coerce({"text": "45"}, _SCHEMA) == {"text": "45"}


def test_correct_types_pass_through_untouched():
    assert agent._coerce({"n": 45, "flag": True}, _SCHEMA) == {"n": 45, "flag": True}


def test_ungarbled_nonsense_is_left_for_the_tool_to_complain_about():
    """Better a clear error from the tool than a silent wrong cast."""
    assert agent._coerce({"n": "soon"}, _SCHEMA) == {"n": "soon"}


def test_unknown_and_schemaless_args_are_passed_through():
    assert agent._coerce({"other": "1"}, _SCHEMA) == {"other": "1"}
    assert agent._coerce({"n": "1"}, None) == {"n": "1"}


async def test_set_reminder_accepts_a_stringified_in_minutes():
    """End to end through _exec_tool, the way the model actually calls it."""
    from backend.tools import CURRENT_USER
    CURRENT_USER.set("coerce-test")
    await db.init()
    result = await agent._exec_tool({"function": {
        "name": "set_reminder",
        "arguments": {"text": "call the landlord", "in_minutes": "45"}}})
    assert "Error" not in result["content"]
    jobs = await db.pending_jobs("coerce-test")
    assert any(j.text == "call the landlord" for j in jobs)


def test_the_history_budget_is_actually_applied():
    """_slice enforces history_budget_tokens and nothing called it — the budget
    was dead code, so the entire 100-message cache went into every prompt."""
    from backend import agent
    long_history = [{"role": "user" if i % 2 == 0 else "assistant",
                     "content": "x" * 400} for i in range(60)]
    sent = agent._context("u", long_history + [{"role": "user", "content": "now this"}], [])
    convo = [m for m in sent if m["role"] != "system"]
    assert len(convo) < len(long_history)
    assert convo[-1]["content"] == "now this"      # the live turn always survives
