from __future__ import annotations
import asyncio, json, logging
from typing import AsyncIterator
import httpx
from . import db, memory, okf
from .config import settings
from .tools import CURRENT_USER, REGISTRY

log = logging.getLogger(__name__)
_HISTORIES: dict[str, list[dict]] = {}   # write-through cache over db.messages
_SUMMARIES: dict[str, str] = {}
_summarizing: set[str] = set()
_MAX_TOOL_HOPS = 6
_CACHE_LIMIT = 100        # in-RAM tail; older context lives in the summary
_SUMMARIZE_BATCH = 8      # summarize once this many messages fall off the slice

async def reset(user: str) -> None:
    """Forget this user's conversation, in RAM and on disk."""
    _HISTORIES.pop(user, None); _SUMMARIES.pop(user, None)
    await db.clear_messages(user)

async def _history(user: str) -> list[dict]:
    if user not in _HISTORIES:
        _HISTORIES[user] = await db.recent_messages(user, limit=_CACHE_LIMIT)
        _SUMMARIES[user] = await db.get_summary(user) or ""
    return _HISTORIES[user]

def _est_tokens(m: dict) -> int:
    size = len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or []))
    return size // 4 + 8

def _slice(history: list[dict], budget: int | None = None) -> list[dict]:
    """Newest messages that fit the token budget, never starting on a tool
    result whose call was cut off."""
    budget = budget or settings.history_budget_tokens
    total, start = 0, len(history)
    while start > 0 and total + _est_tokens(history[start - 1]) <= budget:
        total += _est_tokens(history[start - 1]); start -= 1
    while start < len(history) and history[start]["role"] == "tool":
        start += 1
    return history[start:]

def _context(user: str, convo: list[dict], memories: list[str]) -> list[dict]:
    msgs = [{"role": "system", "content": okf.system_prompt()}]
    if memories:
        msgs.append({"role": "system", "content":
                     "Things you remember about this user:\n- " + "\n- ".join(memories)})
    if _SUMMARIES.get(user):
        msgs.append({"role": "system",
                     "content": f"Summary of earlier conversation:\n{_SUMMARIES[user]}"})
    return msgs + convo

async def _summarize(user: str) -> None:
    """Fold messages that fell off the prompt slice into the rolling summary."""
    if user in _summarizing: return
    _summarizing.add(user)
    try:
        history = _HISTORIES.get(user, [])
        dropped = history[:len(history) - len(_slice(history))]
        if len(dropped) < _SUMMARIZE_BATCH: return
        lines = [f"{m['role']}: {(m.get('content') or '')[:500]}"
                 for m in dropped if m["role"] in ("user", "assistant") and m.get("content")]
        prompt = ("Update this running summary of a conversation. Keep facts, "
                  "decisions, names and open threads; max 150 words.\n\n"
                  f"Current summary:\n{_SUMMARIES.get(user) or '(none)'}\n\n"
                  "New messages:\n" + "\n".join(lines))
        payload = {"model": settings.ollama_model, "stream": False, "keep_alive": "2h",
                   "messages": [{"role": "user", "content": prompt}],
                   "options": {"temperature": 0.2, "num_predict": 250}}
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
            r.raise_for_status()
        summary = r.json().get("message", {}).get("content", "").strip()
        if summary:
            _SUMMARIES[user] = summary
            await db.save_summary(user, summary)
            _HISTORIES[user] = history[len(dropped):]
    except Exception:
        log.exception("summarize failed for %s", user)
    finally:
        _summarizing.discard(user)

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
    CURRENT_USER.set(channel)
    history = await _history(channel)
    memories = await memory.relevant(channel, user_text)
    new = [{"role": "user", "content": user_text}]
    history.extend(new)
    convo = _slice(history)
    try:
        for _ in range(_MAX_TOOL_HOPS):
            message = None
            async for event in _stream_round(_context(channel, convo, memories)):
                if event["type"] == "round_end": message = event["message"]; continue
                yield event
            tool_calls = message.pop("tool_calls")
            if not tool_calls:
                history.append(message); convo.append(message); new.append(message); return
            with_calls = {**message, "tool_calls": tool_calls}
            history.append(with_calls); convo.append(with_calls); new.append(with_calls)
            for call in tool_calls:
                yield {"type": "tool", "name": call["function"]["name"]}
            results = await asyncio.gather(*(_exec_tool(c) for c in tool_calls))
            history.extend(results); convo.extend(results); new.extend(results)
        yield {"type": "delta", "text": "Sorry — I got stuck in a tool loop. Try rephrasing."}
    finally:
        await db.add_messages(channel, new)
        asyncio.create_task(_summarize(channel))
        asyncio.create_task(memory.extract(channel, new))

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
