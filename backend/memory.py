"""Long-term memory: extraction, ranking, retrieval.

After each exchange a background pass asks the model for durable facts
(preferences, people, projects, commitments) and stores them one per row.
Retrieval is a lexical rank over the user's facts — personal scale, a few
hundred rows, so no index needed yet (FTS5/embeddings are the upgrade path).
"""
from __future__ import annotations
import json, logging, re

import httpx
from . import db
from .config import settings

log = logging.getLogger(__name__)
_extracting: set[str] = set()

_STOP = frozenset(
    "a an and are as at be but by did do for from had has have how i in is it "
    "me my of on or our so that the their them they this to was we were what "
    "when where which who will with you your".split())


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower())
            if w not in _STOP and len(w) > 1}


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower().replace("'", "")).strip()


def _parse_facts(text: str) -> list[str]:
    try: data = json.loads(text)
    except (json.JSONDecodeError, TypeError): return []
    if isinstance(data, dict): data = data.get("facts", [])
    if not isinstance(data, list): return []
    return [str(f).strip() for f in data if isinstance(f, str) and f.strip()]


async def relevant(user: str, query: str, k: int = 6) -> list[str]:
    """Top-k memories for this query: term overlap first, recency as tiebreak
    and filler."""
    rows = await db.all_memories(user)
    if not rows: return []
    q = _terms(query)
    scored = sorted(((len(q & _terms(content)), mid, content) for mid, content in rows),
                    key=lambda t: (t[0], t[1]), reverse=True)
    hits = [c for s, _, c in scored if s > 0][:k]
    fresh = [c for _, c in rows if c not in hits]
    return (hits + fresh)[:k]


async def search_messages(user: str, query: str, limit: int = 5) -> list[dict]:
    """Past conversation lines matching the query, best first."""
    q = _terms(query)
    rows = await db.search_messages(user, sorted(q))
    ranked = sorted(rows, key=lambda r: len(q & _terms(r["text"])), reverse=True)
    return ranked[:limit] or [{"note": "nothing found in past conversations"}]


async def extract(user: str, msgs: list[dict]) -> None:
    """Distill durable facts from an exchange into the memories table."""
    if user in _extracting: return
    _extracting.add(user)
    try:
        lines = [f"{m['role']}: {m['content'][:400]}" for m in msgs
                 if m["role"] in ("user", "assistant") and m.get("content")]
        if not lines: return
        prompt = (
            "From this exchange, extract durable facts worth remembering about "
            "the user or their world: preferences, people, projects, commitments, "
            "dates. Ignore small talk and anything transient. Reply with JSON "
            '{"facts": ["...", ...]} — short standalone sentences, or an empty '
            "list if nothing qualifies.\n\n" + "\n".join(lines))
        payload = {"model": settings.ollama_model, "stream": False, "format": "json",
                   "keep_alive": "2h",
                   "messages": [{"role": "user", "content": prompt}],
                   "options": {"temperature": 0.1, "num_predict": 300}}
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30)) as client:
            r = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
            r.raise_for_status()
        facts = _parse_facts(r.json().get("message", {}).get("content", ""))
        seen = {_norm(c) for _, c in await db.all_memories(user)}
        new = [f for f in facts if len(f) > 5 and _norm(f) not in seen][:5]
        if new:
            await db.add_memories(user, new)
            log.info("remembered %d fact(s) for %s", len(new), user)
    except Exception:
        log.exception("memory extraction failed for %s", user)
    finally:
        _extracting.discard(user)
