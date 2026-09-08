"""MCP bridge: config loading, tool registration, proxying, and the guarantee
that one broken server can't take the assistant down with it."""
import asyncio
import json

import pytest

from backend import agent, mcp_client
from backend.config import settings
from backend.tools import REGISTRY


_SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}}


class FakeTool:
    """mcp 2.x exposes `input_schema`; 1.x exposed `inputSchema`. Default to the
    modern name — a fake that only spoke the old one is exactly how the real
    SDK's rename slipped past this suite once already."""
    def __init__(self, name, description="does a thing", schema=None, legacy=False):
        self.name = name
        self.description = description
        setattr(self, "inputSchema" if legacy else "input_schema", schema or _SCHEMA)


class FakeSession:
    """Records calls and returns whatever content blocks the test wants."""
    def __init__(self, blocks=None, is_error=False, raises=None):
        self.blocks, self.is_error, self.raises = blocks or [], is_error, raises
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.raises:
            raise self.raises
        return type("Result", (), {"content": self.blocks, "isError": self.is_error})()


def _text(value):
    return type("TextBlock", (), {"type": "text", "text": value})()


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Registration mutates module-global state; snapshot and restore it."""
    before = dict(REGISTRY)
    mcp_client.CONNECTED.clear(); mcp_client.FAILED.clear()
    yield
    REGISTRY.clear(); REGISTRY.update(before)
    mcp_client._tasks.clear()
    mcp_client.CONNECTED.clear(); mcp_client.FAILED.clear()


def _serve_returning(mapping):
    """Fake _serve: resolves each server's future with (session, tools), or
    raises for names mapped to an exception."""
    async def _serve(name, spec, ready):
        outcome = mapping[name]
        if isinstance(outcome, Exception):
            ready.set_exception(outcome)
        else:
            ready.set_result(outcome)
            await asyncio.sleep(0)
    return _serve


# ---- config -----------------------------------------------------------------

def test_reads_claude_desktop_shape(tmp_path, monkeypatch):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {
        "fs": {"command": "npx", "args": ["-y", "server-filesystem"]},
        "off": {"url": "http://x", "disabled": True}}}))
    monkeypatch.setattr(settings, "mcp_config", str(path))
    servers = mcp_client._load_config()
    assert list(servers) == ["fs"]          # disabled entries are skipped


def test_missing_file_is_simply_off(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mcp_config", str(tmp_path / "nope.json"))
    assert mcp_client._load_config() == {}


def test_malformed_json_does_not_raise(monkeypatch, tmp_path):
    path = tmp_path / "mcp.json"; path.write_text("{not json")
    monkeypatch.setattr(settings, "mcp_config", str(path))
    assert mcp_client._load_config() == {}


# ---- schema reading across SDK generations ----------------------------------

@pytest.mark.parametrize("legacy", [False, True], ids=["mcp-2.x", "mcp-1.x"])
def test_reads_the_schema_from_either_sdk_generation(legacy):
    tool = FakeTool("cat", legacy=legacy)
    assert mcp_client._schema_of(tool) == _SCHEMA


def test_a_tool_with_no_schema_still_registers():
    class Bare:
        name, description = "ping", "no args"
    assert mcp_client._schema_of(Bare()) == {"type": "object", "properties": {}}


@pytest.mark.parametrize("legacy", [False, True], ids=["mcp-2.x", "mcp-1.x"])
async def test_registration_works_for_either_generation(monkeypatch, legacy):
    session = FakeSession([_text("ok")])
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"fs": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning(
        {"fs": (session, [FakeTool("cat", legacy=legacy)])}))
    await mcp_client.connect_all()
    assert REGISTRY["mcp_fs_cat"]["schema"] == _SCHEMA


# ---- registration -----------------------------------------------------------

async def test_registers_tools_namespaced_by_server(monkeypatch):
    session = FakeSession([_text("42")])
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"my server": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning(
        {"my server": (session, [FakeTool("read-file")])}))
    await mcp_client.connect_all()
    assert "mcp_my_server_read_file" in REGISTRY      # sanitised for the model
    assert mcp_client.CONNECTED["my server"] == 1


async def test_calls_are_proxied_and_flattened(monkeypatch):
    session = FakeSession([_text("line one"), _text("line two")])
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"fs": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning({"fs": (session, [FakeTool("cat")])}))
    await mcp_client.connect_all()
    out = await REGISTRY["mcp_fs_cat"]["fn"](q="hello")
    assert out == "line one\nline two"
    assert session.calls == [("cat", {"q": "hello"})]


async def test_tool_errors_come_back_as_text_not_exceptions(monkeypatch):
    session = FakeSession(raises=RuntimeError("socket closed"))
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"fs": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning({"fs": (session, [FakeTool("cat")])}))
    await mcp_client.connect_all()
    out = await REGISTRY["mcp_fs_cat"]["fn"](q="x")
    assert "socket closed" in out and "fs" in out


async def test_error_results_are_marked(monkeypatch):
    session = FakeSession([_text("no such path")], is_error=True)
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"fs": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning({"fs": (session, [FakeTool("cat")])}))
    await mcp_client.connect_all()
    assert (await REGISTRY["mcp_fs_cat"]["fn"]()).startswith("Error:")


async def test_a_dead_server_does_not_stop_the_others(monkeypatch):
    good = FakeSession([_text("ok")])
    monkeypatch.setattr(mcp_client, "_load_config",
                        lambda: {"dead": {"url": "http://x"}, "good": {"url": "http://y"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning({
        "dead": ConnectionRefusedError("nothing listening"),
        "good": (good, [FakeTool("ping")])}))
    await mcp_client.connect_all()
    assert "mcp_good_ping" in REGISTRY
    assert "nothing listening" in mcp_client.FAILED["dead"]
    assert "failed" in mcp_client.status()["dead"]


async def test_tool_budget_caps_prompt_growth(monkeypatch):
    """Schemas ride in every prompt, so an enthusiastic server gets truncated."""
    monkeypatch.setattr(settings, "mcp_max_tools", 2)
    session = FakeSession([_text("ok")])
    tools = [FakeTool(f"tool{i}") for i in range(5)]
    monkeypatch.setattr(mcp_client, "_load_config", lambda: {"big": {"url": "http://x"}})
    monkeypatch.setattr(mcp_client, "_serve", _serve_returning({"big": (session, tools)}))
    await mcp_client.connect_all()
    assert mcp_client.CONNECTED["big"] == 2


# ---- safety -----------------------------------------------------------------

def test_mcp_tools_require_approval_by_default(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_approval", True)
    assert agent._gated("mcp_fs_delete_file")
    assert not agent._gated("web_search")


def test_approval_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(settings, "mcp_require_approval", False)
    assert not agent._gated("mcp_fs_delete_file")
    assert agent._gated("run_code")          # the explicit list still applies
