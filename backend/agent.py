"""Custom Wednesday agent on Ollama with native tool calling.

Tools live in backend/tools/*. Each module calls `register(name, schema, fn)`
on import. The agent loops: chat -> if tool_calls, execute concurrently, feed
results back; stop when the model emits a plain assistant message.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncIterator

import httpx

from .config import settings
from .tools import REGISTRY

log = logging.getLogger(__name__)

_HISTORIES: dict[str, list[dict]] = {}
_MAX_TOOL_HOPS = 6


def reset(channel: str) -> None:
    _HISTORIES.pop(channel, None)


def _history(channel: str) -> list[dict]:
    return _HISTORIES.setdefault(channel, [])


def _tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["schema"],
            },
        }
        for name, spec in REGISTRY.items()
    ]


async def _ollama_chat(messages: list[dict]) -> dict:
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "tools": _tool_specs(),
        "stream": False,
        "options": {"temperature": 0.4},
    }
    if not messages or messages[0].get("role") != "system":
        payload["messages"] = [{"role": "system", "content": settings.system_prompt}, *messages]
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
        r = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


async def _exec_tool(call: dict) -> dict:
    name = call["function"]["name"]
    raw_args = call["function"].get("arguments")
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = raw_args or {}

    fn = REGISTRY.get(name, {}).get("fn")
    if fn is None:
        content = f"Tool '{name}' is not registered."
    else:
        try:
            result = await fn(**args)
            content = result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception as exc:
            log.exception("tool %s failed", name)
            content = f"Error from {name}: {exc}"
    return {"role": "tool", "name": name, "content": content}


async def _run_loop(messages: list[dict]) -> str:
    for _ in range(_MAX_TOOL_HOPS):
        response = await _ollama_chat(messages)
        msg = response.get("message", {})
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            messages.append(msg)
            return msg.get("content", "")

        messages.append(msg)
        results = await asyncio.gather(*(_exec_tool(c) for c in tool_calls))
        messages.extend(results)

    return "Sorry - I got stuck in a tool loop. Try rephrasing."


async def reply(channel: str, user_text: str) -> str:
    history = _history(channel)
    history.append({"role": "user", "content": user_text})
    text = await _run_loop(history)
    return text


async def stream_reply(channel: str, user_text: str) -> AsyncIterator[str]:
    """Yield word-sized chunks preserving whitespace for smooth UI animation."""
    text = await reply(channel, user_text)
    for token in re.findall(r'\S+\s*', text):
        yield token
