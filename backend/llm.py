"""Model router: one streaming chat interface over Ollama or any
OpenAI-compatible endpoint.

Wednesday's ceiling has always been generation speed — a few tokens per second
on CPU makes an assistant that is *correct* but never feels *present*. A hosted
OpenAI-compatible endpoint (Groq, Cerebras, OpenRouter, Together, or a vLLM box
on the LAN) answers in well under a second.

Following the precedent already set by TTS (Fish Audio, else Piper) and web
search (Tavily/Brave, else DuckDuckGo): **hosted when configured, local always
works**. Set LLM_BASE_URL + LLM_API_KEY to go fast; with them unset nothing
changes and everything stays local and free. If a hosted call fails *before it
has streamed anything*, the turn silently falls back to Ollama — a dead API key
or a rate limit degrades to slow rather than to broken.

Background utility calls (memory extraction, summaries) deliberately stay on
Ollama: they're latency-insensitive, and keeping them local means a hosted chat
model and the local utility model stop competing for the same runner entirely.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from .config import settings

log = logging.getLogger(__name__)


def hosted() -> bool:
    """True when a hosted OpenAI-compatible backend is configured."""
    return bool(settings.llm_api_key and settings.llm_base_url)


def active_model() -> str:
    return (settings.llm_model or "(unset)") if hosted() else settings.ollama_model


def describe() -> str:
    return f"{'hosted' if hosted() else 'ollama'}:{active_model()}"


# --- OpenAI-compatible -------------------------------------------------------

def _sanitize(messages: list[dict]) -> list[dict]:
    """Make a history the OpenAI schema will accept.

    Two mismatches to repair. First, tool results are stored without the
    `tool_call_id` the API requires (db.messages has no column for it), so
    replayed history arrives as orphans. Second, an assistant message carrying
    `tool_calls` *must* be followed by a matching tool message, or the API 400s.

    So: keep a call/result pair only when the result still has a matching id;
    otherwise demote both sides to plain text, which preserves what happened
    without violating the schema.
    """
    answered: set[str] = set()
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id"):
            answered.add(m["tool_call_id"])

    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            kept = []
            described = []
            for i, c in enumerate(m["tool_calls"]):
                fn = c.get("function") or {}
                args = fn.get("arguments")
                if not isinstance(args, str):
                    args = json.dumps(args or {})
                cid = c.get("id")
                if cid and cid in answered:
                    kept.append({"id": cid, "type": "function",
                                 "function": {"name": fn.get("name", ""), "arguments": args}})
                else:
                    described.append(f"{fn.get('name', 'tool')}({args})")
            content = m.get("content") or ""
            if described:
                note = "[called " + "; ".join(described) + "]"
                content = f"{content}\n{note}".strip()
            if kept:
                out.append({"role": "assistant", "content": content, "tool_calls": kept})
            elif content:
                out.append({"role": "assistant", "content": content})
        elif role == "tool":
            cid = m.get("tool_call_id")
            if cid and cid in answered:
                out.append({"role": "tool", "tool_call_id": cid,
                            "content": m.get("content") or ""})
            elif m.get("content"):
                out.append({"role": "assistant",
                            "content": f"[result from {m.get('name') or 'a tool'}]\n"
                                       f"{m['content']}"})
        elif m.get("content"):
            out.append({"role": role, "content": m["content"]})
    return out


async def _stream_openai(messages, tools, transport) -> AsyncIterator[dict]:
    payload: dict = {"model": settings.llm_model, "messages": _sanitize(messages),
                     "stream": True, "temperature": settings.llm_temperature}
    if tools:
        payload["tools"] = tools
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    content: list[str] = []
    calls: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout, connect=15),
                                 transport=transport) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as r:
            r.raise_for_status()
            async for raw in r.aiter_lines():
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if text := delta.get("content"):
                    content.append(text)
                    yield {"type": "delta", "text": text}
                # Tool calls stream as fragments: the name arrives once and the
                # JSON arguments in pieces, keyed by index. Concatenate them.
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0),
                                            {"id": "", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
    yield {"type": "round_end",
           "message": {"role": "assistant", "content": "".join(content),
                       "tool_calls": [calls[i] for i in sorted(calls)]}}


# --- Ollama (unchanged wire format) ------------------------------------------

def _for_ollama(messages: list[dict]) -> list[dict]:
    """The mirror of _sanitize.

    Ollama wants tool-call arguments as an object; OpenAI-compatible backends
    emit them as a JSON *string*. Once a hosted turn has put one in the history,
    every later Ollama request 400s with "Value looks like object, but can't
    find closing '}' symbol" — which silently breaks the local fallback exactly
    when it's needed, since a hosted failure mid-conversation is the whole
    reason the fallback exists.
    """
    out: list[dict] = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                fn = dict(c.get("function") or {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                fn["arguments"] = args if isinstance(args, dict) else {}
                calls.append({**{k: v for k, v in c.items() if k != "function"},
                              "function": fn})
            out.append({**m, "tool_calls": calls})
        else:
            out.append(m)
    return out


async def _stream_ollama(messages, tools, transport) -> AsyncIterator[dict]:
    payload = {"model": settings.ollama_model, "messages": _for_ollama(messages),
               "tools": tools, "stream": True, "keep_alive": "2h",
               "options": {"temperature": 0.6, "num_ctx": settings.num_ctx}}
    content, tool_calls = [], []
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30),
                                 transport=transport) as client:
        async with client.stream("POST", f"{settings.ollama_host}/api/chat", json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                msg = json.loads(line).get("message", {})
                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])
                if msg.get("content"):
                    content.append(msg["content"])
                    yield {"type": "delta", "text": msg["content"]}
    yield {"type": "round_end",
           "message": {"role": "assistant", "content": "".join(content),
                       "tool_calls": tool_calls}}


async def stream_chat(messages, tools, *, transport=None) -> AsyncIterator[dict]:
    """Stream one model turn as {"type": "delta"} events then a final
    {"type": "round_end", "message": ...}, from whichever backend is active."""
    if hosted():
        emitted = False
        try:
            async for event in _stream_openai(messages, tools, transport):
                emitted = True
                yield event
            return
        except Exception:
            if emitted:
                raise  # mid-stream: the user already saw output, don't double-answer
            log.exception("hosted model failed before output; falling back to Ollama")
    async for event in _stream_ollama(messages, tools, transport):
        yield event
