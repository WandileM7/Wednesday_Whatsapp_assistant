"""MCP bridge: every tool on every configured MCP server becomes a Wednesday tool.

Servers are declared in `mcp.json` (Claude-Desktop shape, so configs paste
across):

    {"mcpServers": {
       "filesystem": {"command": "npx",
                      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]},
       "playwright":  {"url": "http://localhost:8931/mcp"}}}

Design notes:

* Each server gets its own long-lived task that opens the session and then
  parks on an event. The MCP client's transports are anyio context managers,
  and exiting one from a different task than entered it raises cancel-scope
  errors — keeping enter and exit inside one task sidesteps that entirely.
  Tool calls come from other tasks, which `ClientSession` supports.
* One unreachable server must never stop the assistant booting, so connects
  are per-server best-effort with a timeout, and failures are logged and
  skipped.
* Tool schemas ride in *every* prompt, so an enthusiastic server can eat the
  context window. `mcp_max_tools` caps how many get registered.
* MCP tools are third-party code with real side effects, so they default to
  the same approval gate as run_code (see `agent._gated`).
"""
from __future__ import annotations
import asyncio, json, logging, os, re
from pathlib import Path
from typing import Any

from .config import settings
from .tools import REGISTRY, register

log = logging.getLogger(__name__)

_tasks: list[asyncio.Task] = []
_stop = asyncio.Event()
CONNECTED: dict[str, int] = {}          # server name -> tools registered
FAILED: dict[str, str] = {}             # server name -> why


def _load_config() -> dict[str, dict]:
    path = Path(settings.mcp_config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("mcp: could not read %s: %s", path, exc)
        return {}
    servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
    return {k: v for k, v in servers.items()
            if isinstance(v, dict) and not v.get("disabled")}


def _safe(name: str) -> str:
    """Tool names reach the model and Ollama's function-call parser; keep them
    to the conservative [A-Za-z0-9_] set."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_")


def _flatten(result: Any) -> str:
    """MCP returns a list of typed content blocks; the model wants text."""
    parts = []
    for block in getattr(result, "content", []) or []:
        kind = getattr(block, "type", "")
        if kind == "text":
            parts.append(block.text)
        elif kind == "resource":                       # embedded resource
            res = getattr(block, "resource", None)
            parts.append(getattr(res, "text", None) or f"[resource {getattr(res, 'uri', '')}]")
        else:
            parts.append(f"[{kind or 'content'} omitted]")
    text = "\n".join(p for p in parts if p).strip() or "(no output)"
    if getattr(result, "isError", False):
        text = f"Error: {text}"
    return text[:4000] + ("\n[truncated]" if len(text) > 4000 else "")


def _schema_of(tool) -> dict:
    """The tool's JSON schema, whichever SDK generation produced it.

    mcp 2.x names the attribute `input_schema` and keeps `inputSchema` only as
    the wire alias; 1.x exposed the camelCase name directly. Reading both means
    a dependency bump can't silently un-register every MCP tool.
    """
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    return schema if isinstance(schema, dict) else {"type": "object", "properties": {}}


def _transport(spec: dict):
    """Context manager yielding (read, write[, ...]) streams for a server spec."""
    if url := spec.get("url"):
        from mcp.client.streamable_http import streamablehttp_client
        return streamablehttp_client(url, headers=spec.get("headers") or None)
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    # Inherit the parent environment (PATH, HOME) and layer the spec's env on
    # top; a bare env would break `npx`/`uvx` launchers.
    env = {**os.environ, **(spec.get("env") or {})}
    return stdio_client(StdioServerParameters(
        command=spec["command"], args=spec.get("args") or [], env=env))


async def _serve(name: str, spec: dict, ready: asyncio.Future) -> None:
    """Own one server's session for the process lifetime."""
    from mcp import ClientSession
    try:
        async with _transport(spec) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                if not ready.done():
                    ready.set_result((session, tools))
                await _stop.wait()
    except asyncio.CancelledError:
        raise
    except Exception as exc:                      # noqa: BLE001 — reported, not raised
        if not ready.done():
            ready.set_exception(exc)
        else:
            log.warning("mcp: server %s dropped: %s", name, exc)


def _make_fn(name: str, session, tool_name: str):
    async def call(**kwargs):
        try:
            return _flatten(await session.call_tool(tool_name, kwargs))
        except Exception as exc:                  # noqa: BLE001 — the model reads this
            log.warning("mcp: %s.%s failed: %s", name, tool_name, exc)
            return f"MCP server {name!r} failed to run {tool_name}: {exc}"
    return call


async def connect_all() -> None:
    """Connect every configured server and register its tools. Best-effort."""
    servers = _load_config()
    if not servers:
        return
    try:
        import mcp  # noqa: F401
    except ImportError:
        log.warning("mcp: %s lists %d server(s) but the `mcp` package isn't "
                    "installed — run: pip install mcp", settings.mcp_config, len(servers))
        return

    budget = settings.mcp_max_tools
    loop = asyncio.get_running_loop()
    for name, spec in servers.items():
        ready: asyncio.Future = loop.create_future()
        _tasks.append(asyncio.create_task(_serve(name, spec, ready), name=f"mcp:{name}"))
        try:
            session, tools = await asyncio.wait_for(ready, timeout=settings.mcp_connect_timeout)
        except Exception as exc:                  # noqa: BLE001 — one bad server, carry on
            FAILED[name] = str(exc) or exc.__class__.__name__
            log.warning("mcp: server %s unavailable: %s", name, FAILED[name])
            continue
        registered = 0
        for tool in tools:
            if budget <= 0:
                log.warning("mcp: tool budget (%d) reached — skipping the rest of %s. "
                            "Raise MCP_MAX_TOOLS or trim the server list.",
                            settings.mcp_max_tools, name)
                break
            key = f"mcp_{_safe(name)}_{_safe(tool.name)}"
            if key in REGISTRY:
                continue
            schema = _schema_of(tool)
            description = (tool.description or f"{tool.name} via the {name} MCP server").strip()
            register(key, description[:400], schema)(_make_fn(name, session, tool.name))
            registered += 1
            budget -= 1
        CONNECTED[name] = registered
        log.info("mcp: %s → %d tool(s)", name, registered)


async def shutdown() -> None:
    _stop.set()
    for task in _tasks:
        try:  # give each session a moment to close its transport cleanly
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except Exception:                          # noqa: BLE001 — shutting down regardless
            task.cancel()
    _tasks.clear()


def status() -> dict:
    """For /doctor: what connected, what didn't, and what it cost."""
    if not _load_config():
        return {"servers": "none configured"}
    out: dict[str, Any] = {name: f"{n} tool(s)" for name, n in CONNECTED.items()}
    out.update({name: f"failed: {why}" for name, why in FAILED.items()})
    return out
