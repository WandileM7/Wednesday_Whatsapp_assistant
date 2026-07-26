"""Long-term memory: extraction, ranking, retrieval.

After each exchange a background pass asks the model for durable facts
(preferences, people, projects, commitments) and stores them one per row.

Retrieval is a BM25-lite rank in Python over the user's facts. At personal
scale (a few hundred short rows) retrieval already loads-all-then-ranks, so an
index buys nothing structurally — the win over plain term-overlap is *relevance*:
BM25's idf weighting lets a rare, discriminating word ("passport", "falcon")
outrank a common one ("user", "project"). It stays deliberately db-agnostic —
compose runs Postgres, dev runs sqlite — so it behaves identically on both, and
FTS5 (sqlite-only) would fork that. Embeddings via Ollama are the next step.
"""
from __future__ import annotations
import json, logging, math, re

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


def _bm25(query: set[str], docs: list[tuple[int, str]],
          k1: float = 1.5, b: float = 0.75) -> list[tuple[float, int, str]]:
    """Rank (id, content) docs against the query terms with a BM25-lite score,
    best first (id breaks ties, so a tie keeps newest-first order). Idf is
    computed over `docs`, so rarer terms in this set weigh more. Pure Python,
    db-agnostic — the whole point (see module docstring)."""
    doc_terms = [(mid, content, _terms(content)) for mid, content in docs]
    n = len(doc_terms) or 1
    avgdl = (sum(len(t) for _, _, t in doc_terms) / n) or 1.0
    df = {t: sum(1 for _, _, td in doc_terms if t in td) for t in query}
    idf = {t: max(0.0, math.log(1 + (n - d + 0.5) / (d + 0.5)))
           for t, d in df.items() if d}
    scored = []
    for mid, content, td in doc_terms:
        dl = len(td) or 1
        # short facts ⇒ term frequency is effectively binary (present or not)
        score = sum(idf[t] * (k1 + 1) / (1 + k1 * (1 - b + b * dl / avgdl))
                    for t in query if t in td and t in idf)
        scored.append((score, mid, content))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored


async def relevant(user: str, query: str, k: int = 6) -> list[str]:
    """Top-k memories for this query: BM25 relevance first, recency as tiebreak
    and filler for the remaining slots."""
    rows = await db.all_memories(user)
    if not rows: return []
    hits = [c for s, _, c in _bm25(_terms(query), rows) if s > 0][:k]
    fresh = [c for _, c in rows if c not in hits]
    return (hits + fresh)[:k]


async def search_messages(user: str, query: str, limit: int = 5) -> list[dict]:
    """Past conversation lines matching the query, best first (BM25 over the
    candidate rows the db returned for any query term)."""
    q = _terms(query)
    rows = await db.search_messages(user, sorted(q))
    if not rows: return [{"note": "nothing found in past conversations"}]
    # rows are newest-first; give newer rows the higher id so a BM25 score tie
    # keeps newest-first (the id tiebreak sorts descending).
    by_id = {len(rows) - i: r for i, r in enumerate(rows)}
    ranked = [by_id[i] for s, i, _ in _bm25(q, [(i, r["text"]) for i, r in by_id.items()])
              if s > 0][:limit]
    return ranked or [{"note": "nothing found in past conversations"}]


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
        payload = {"model": settings.ollama_model_utility or settings.ollama_model,
                   "stream": False, "format": "json",
                   "keep_alive": "2h",
                   "messages": [{"role": "user", "content": prompt}],
                   "options": {"temperature": 0.1, "num_predict": 300}}
        # Background call — a slow extraction never blocks a reply, so give it
        # a generous read budget rather than dropping facts on a timeout.
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
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
