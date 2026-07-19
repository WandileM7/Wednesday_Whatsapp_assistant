from __future__ import annotations
import asyncio, json, logging
from typing import AsyncIterator
import httpx
from . import okf
from .config import settings
from .tools import REGISTRY

log = logging.getLogger(__name__)
_HISTORIES: dict[str, list[dict]] = {}
_MAX_TOOL_HOPS = 6

def reset(channel): _HISTORIES.pop(channel, None)
def _history(channel): return _HISTORIES.setdefault(channel, [])

def _tool_specs():
    return [{"type": "function", "function": {"name": n, "description": s["description"],
             "parameters": s["schema"]}} for n, s in REGISTRY.items()]

async def _stream_round(messages) -> AsyncIterator[dict]:
    """Stream one model turn. Yields {"type": "delta"} events for content tokens,
    then a final {"type": "round_end", "message": ...} with the assembled message."""
    payload = {"model": settings.ollama_model, "messages": messages,
               "tools": _tool_specs(), "stream": True, "keep_alive": "2h",
               "options": {"temperature": 0.6}}
    if not messages or messages[0].get("role") != "system":
        payload["messages"] = [{"role": "system", "content": okf.system_prompt()}, *messages]
    content, tool_calls = [], []
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
        async with client.stream("POST", f"{settings.ollama_host}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip(): continue
                msg = json.loads(line).get("message", {})
                if msg.get("tool_calls"): tool_calls.extend(msg["tool_calls"])
                if msg.get("content"):
                    content.append(msg["content"])
                    yield {"type": "delta", "text": msg["content"]}
    yield {"type": "round_end", "message": {"role": "assistant",
           "content": "".join(content), "tool_calls": tool_calls}}

async def _exec_tool(call):
    name = call["function"]["name"]
    raw_args = call["function"].get("arguments")
    if isinstance(raw_args, str):
        try: args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError: args = {}
    else: args = raw_args or {}
    fn = REGISTRY.get(name, {}).get("fn")
    if fn is None: content = f"Tool '{name}' not registered."
    else:
        try:
            result = await fn(**args)
            content = result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as exc:
            log.exception("tool %s failed", name); content = f"Error from {name}: {exc}"
    return {"role": "tool", "name": name, "content": content}

async def stream_reply(channel, user_text) -> AsyncIterator[dict]:
    """Yields {"type": "delta", "text"} for answer tokens as the model generates
    them and {"type": "tool", "name"} whenever a tool round starts."""
    history = _history(channel); history.append({"role": "user", "content": user_text})
    for _ in range(_MAX_TOOL_HOPS):
        message = None
        async for event in _stream_round(history):
            if event["type"] == "round_end": message = event["message"]; continue
            yield event
        tool_calls = message.pop("tool_calls")
        if not tool_calls:
            history.append(message); return
        history.append({**message, "tool_calls": tool_calls})
        for call in tool_calls:
            yield {"type": "tool", "name": call["function"]["name"]}
        results = await asyncio.gather(*(_exec_tool(c) for c in tool_calls))
        history.extend(results)
    yield {"type": "delta", "text": "Sorry — I got stuck in a tool loop. Try rephrasing."}

async def warmup():
    """Load the model and prefill the system prompt + tool schemas so
    Ollama's prefix cache is primed before the first real message."""
    payload = {"model": settings.ollama_model,
               "messages": [{"role": "system", "content": okf.system_prompt()}],
               "tools": _tool_specs(), "stream": False, "keep_alive": "2h",
               "options": {"num_predict": 1}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
            await client.post(f"{settings.ollama_host}/api/chat", json=payload)
        log.info("model warmed up: %s", settings.ollama_model)
    except Exception:
        log.exception("model warmup failed; first reply will be slow")

async def reply(channel, user_text):
    parts = [e["text"] async for e in stream_reply(channel, user_text) if e["type"] == "delta"]
    return "".join(parts).strip()
