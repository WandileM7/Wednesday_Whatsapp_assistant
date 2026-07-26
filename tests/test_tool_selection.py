"""Per-request tool selection.

The full registry is ~3.6k tokens on every request — enough to exhaust a
rate-limited hosted tier in a single turn. Capping keeps the core tools plus
the most query-relevant ones.
"""
import pytest

from backend import agent
from backend.config import settings
from backend.tools import REGISTRY


def _names(specs):
    return [s["function"]["name"] for s in specs]


def test_uncapped_by_default_offers_everything():
    assert settings.max_tools_per_request == 0
    assert len(agent._tool_specs("anything")) == len(REGISTRY)


def test_cap_limits_the_count(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 12)
    assert len(agent._tool_specs("what's the weather in Oslo")) <= 12


def test_core_tools_are_always_offered(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 8)
    names = _names(agent._tool_specs("play some music"))
    for core in agent._CORE_TOOLS:
        assert core in names, core


def test_relevant_tool_is_selected(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 12)
    assert "get_weather" in _names(agent._tool_specs("what's the weather in Cape Town"))


def test_cap_is_always_filled_even_when_nothing_matches(monkeypatch):
    """Known limitation, pinned deliberately: matching a user's words against
    tool descriptions is weak — "will it rain" shares no term with the weather
    tool's text. A miss must still hand over a full complement of tools rather
    than collapsing to the core four, so the model keeps a chance of finding
    what it needs."""
    monkeypatch.setattr(settings, "max_tools_per_request", 12)
    assert len(agent._tool_specs("zzzz qqqq no words match this")) == 12
    assert len(agent._tool_specs("will it rain in Cape Town today")) == 12


def test_selection_follows_the_query(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 12)
    lights = _names(agent._tool_specs("turn the kitchen lights off"))
    mail = _names(agent._tool_specs("draft a reply to that email thread"))
    assert any(n.startswith("home_") for n in lights)
    assert any(n.startswith("gmail_") for n in mail)
    assert lights != mail


def test_cap_above_registry_size_is_a_no_op(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", len(REGISTRY) + 50)
    assert len(agent._tool_specs("x")) == len(REGISTRY)


def test_no_duplicates_and_all_valid(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 15)
    names = _names(agent._tool_specs("remind me to call Thabo about the lease"))
    assert len(names) == len(set(names))
    assert all(n in REGISTRY for n in names)


def test_empty_query_still_returns_core(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 6)
    names = _names(agent._tool_specs(""))
    assert set(agent._CORE_TOOLS) <= set(names)


def test_specs_have_the_wire_shape(monkeypatch):
    monkeypatch.setattr(settings, "max_tools_per_request", 10)
    for s in agent._tool_specs("weather"):
        assert s["type"] == "function"
        assert {"name", "description", "parameters"} <= set(s["function"])
