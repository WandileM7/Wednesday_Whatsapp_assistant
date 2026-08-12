"""Prompt-size guards: the history slice, the tool-result clamp, and routing."""
import json

import pytest

from backend import agent, toolrouter
from backend.config import settings
from backend.tools import REGISTRY


def _tool(name, chars):
    return {"role": "tool", "name": name, "content": "x" * chars}


# --- _slice ---------------------------------------------------------------

def test_slice_never_empties_on_an_oversized_tool_result():
    """The bug that made her look stupid: one fat web_search result blew the
    budget on the first comparison and the model got no conversation at all."""
    history = [
        {"role": "user", "content": "what's the load shedding schedule"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "web_search", "arguments": {}}}]},
        _tool("web_search", settings.history_budget_tokens * 8),  # ~2x the budget
    ]
    out = agent._slice(history)
    assert out, "slice returned nothing — the model cannot see the question"
    assert any(m["role"] == "user" for m in out), "the question itself must survive"


def test_slice_keeps_the_question_when_nothing_fits():
    history = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "older"},
        {"role": "user", "content": "y" * 40_000},
    ]
    out = agent._slice(history)
    assert out and out[-1]["content"].startswith("y")


def test_slice_still_trims_and_never_starts_on_an_orphan_tool_result():
    history = [{"role": "user", "content": "u" * 4000} for _ in range(12)]
    history.append(_tool("web_search", 100))
    out = agent._slice(history)
    assert len(out) < len(history), "budget is still enforced"
    assert out[0]["role"] != "tool", "must not start on an orphaned tool result"


def test_slice_of_empty_history_is_empty():
    assert agent._slice([]) == []


# --- tool result clamp ----------------------------------------------------

async def test_tool_result_is_clamped_before_it_reaches_the_prompt():
    async def huge(**kw):
        return [{"url": f"u{i}", "content": "z" * 2000} for i in range(5)]

    REGISTRY["_fat_tool"] = {"description": "d", "schema": {}, "fn": huge}
    try:
        out = await agent._exec_tool(
            {"function": {"name": "_fat_tool", "arguments": "{}"}})
    finally:
        REGISTRY.pop("_fat_tool", None)
    # Clamp plus the injection-guard prefix and the truncation marker.
    assert len(out["content"]) < settings.tool_result_chars + 200
    assert "[truncated]" in out["content"]
    # And the clamped result must still fit alongside a conversation.
    assert agent._est_tokens(out) < settings.history_budget_tokens


# --- routing --------------------------------------------------------------

def test_music_request_gets_music_tools_and_not_the_rest():
    picked = toolrouter.select("play some jazz", [])
    assert "spotify_play" in picked
    assert "gmail_send" not in picked and "calendar_create_event" not in picked


def test_routing_actually_shrinks_the_schema_block():
    """Measured saving is 47% on a music turn (the worst case — music is the
    biggest group, seven Spotify schemas) and ~78% on plain conversation."""
    full = len(json.dumps(agent._tool_specs("", None)))
    worst = len(json.dumps(agent._tool_specs("", toolrouter.select("play some jazz", []))))
    plain = len(json.dumps(agent._tool_specs("", toolrouter.select("tell me a joke", []))))
    assert worst < full * 0.65
    assert plain < full * 0.35


def test_core_tools_are_always_offered():
    for text in ("play some jazz", "check my email", "hello"):
        picked = toolrouter.select(text, [])
        assert toolrouter.CORE <= picked


def test_ungrouped_tools_are_never_routed_away():
    """A tool added later must not vanish because nobody wrote it a keyword."""
    REGISTRY["_brand_new_tool"] = {"description": "d", "schema": {}, "fn": None}
    try:
        assert "_brand_new_tool" in toolrouter.select("hello", [])
    finally:
        REGISTRY.pop("_brand_new_tool", None)


def test_followup_with_no_keyword_keeps_the_group():
    """'skip it' names nothing. Without stickiness the music tools disappear
    exactly when the follow-up needs them."""
    convo = [
        {"role": "user", "content": "play some jazz"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "spotify_play", "arguments": {}}}]},
        _tool("spotify_play", 50),
        {"role": "assistant", "content": "Miles Davis, then."},
    ]
    assert "spotify_play" in toolrouter.select("skip it", convo)


def test_stickiness_expires():
    convo = [{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "spotify_play", "arguments": {}}}]}]
    convo += [{"role": "user", "content": "unrelated"}
              for _ in range(toolrouter._STICKY_MESSAGES + 2)]
    assert "spotify_play" not in toolrouter.select("hello", convo)


@pytest.mark.parametrize("text,expected", [
    ("what's in my inbox", "gmail_search"),
    ("am I free on thursday", "calendar_list_events"),
    ("remind me in 20 minutes", "set_reminder"),
    ("search the web for the news", "web_search"),
    ("add milk to my todo list", "tasks_add"),
    ("what's in this picture", "see_image"),
])
def test_intent_reaches_its_tool(text, expected):
    assert expected in toolrouter.select(text, [])


# --- the poisoned rolling summary ----------------------------------------

def test_echoed_summary_is_rejected():
    """The real one, verbatim from wednesday.db: the utility model handed back
    _summarize's own prompt, transcript included, and it became a worked example
    of how to answer 'how are you' in every later prompt."""
    poisoned = (
        "Here is the updated summary:\n\nCurrent summary:\nWednesday is a "
        "personal AI designed for the quirky and dark, with a dry sense of "
        "humor.\n\nNew messages:\nuser: Hi Wednesday\nassistant: [sighing] Hi "
        "there. What can I assist you with today?\nuser: How are you\n"
        "assistant: Thriving in the dark, watching your calendar fill up like "
        "a graveyard. How do you need me to assist you further?"
    )
    assert agent._echoes_prompt(poisoned)
    assert not agent._degenerate(poisoned), "fluent text — entropy checks can't see it"


@pytest.mark.parametrize("bad", [
    "Here's the summary: he lives in Cape Town.",
    "Current summary:\nnothing yet.",
    "New messages:\nuser: hi",
    "user: Hi Wednesday\nassistant: Hello.",
    "assistant: Thriving in the dark.",
])
def test_echo_shapes_are_rejected(bad):
    assert agent._echoes_prompt(bad)


@pytest.mark.parametrize("good", [
    "Wandile lives in Cape Town and is building the backend's voice pipeline.",
    "He asked about the weather, then set a reminder for 06:00. Spotify is linked.",
    "Nothing much: small talk, and a question about his calendar he did not follow up.",
])
def test_real_summaries_survive(good):
    assert not agent._echoes_prompt(good)
