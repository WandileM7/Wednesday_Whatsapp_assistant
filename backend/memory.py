"""Long-term memory: extraction, ranking, retrieval.

After each exchange a background pass asks the model for durable facts
(preferences, people, projects, commitments) and stores them one per row.

Retrieval prefers the hybrid index in `vecstore` (FTS5 keyword + sqlite-vec
semantic, fused by rank), which catches "what did I say about the flat?" →
"Wandile is moving to Cape Town in March" where term overlap finds nothing.

The BM25-lite rank below is the fallback for a cold index, a missing embedding
model, or embeddings switched off. It beats plain term-overlap on *relevance*:
idf weighting lets a rare, discriminating word ("passport", "falcon") outrank a
common one ("user", "project"). It is also deliberately db-agnostic — compose
runs Postgres, dev runs sqlite — so the fallback behaves identically on both
where FTS5 (sqlite-only) would fork. It earns its keep twice over: agent.py
ranks *tool descriptions* with the same function when capping the schema block.
"""
from __future__ import annotations
import asyncio, json, logging, math, re

import httpx
from . import db, vecstore
from .config import settings

log = logging.getLogger(__name__)


async def post_chat(payload: dict, *, transport=None, attempts: int = 3) -> dict:
    """POST to Ollama's /api/chat, retrying the 500s it returns under load.

    Background work (this module's extraction, agent's rolling summary) runs on
    a *second* model while the chat model is still resident. On a host that
    can't hold both, Ollama answers a perfectly valid request with a 500 rather
    than queueing it — reproducible here by firing chat + utility + embed at
    once. The request isn't wrong, the server is just out of room a moment, so
    back off and try again instead of dropping the facts on the floor.

    Retrying is safe: both callers are idempotent — extraction dedupes against
    stored memories, and the summary is a full rewrite, not an append.
    """
    delay = 2.0
    last: httpx.Response | None = None
    for attempt in range(attempts):
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30),
                                     transport=transport) as client:
            last = await client.post(f"{settings.ollama_host}/api/chat", json=payload)
        if last.status_code < 500:
            last.raise_for_status()
            return last.json()
        if attempt < attempts - 1:
            log.info("ollama %s on a background call (model contention); retrying in %.0fs",
                     last.status_code, delay)
            await asyncio.sleep(delay)
            delay *= 3
    assert last is not None
    last.raise_for_status()
    return {}


_extracting: set[str] = set()
_indexing: set[str] = set()
_tasks: set[asyncio.Task] = set()     # keeps background tasks from being GC'd


def _kick(user: str, coro) -> None:
    """Run an index sync in the background, one at a time per user."""
    if user in _indexing:
        coro.close(); return
    _indexing.add(user)

    async def _run():
        try: await coro
        finally: _indexing.discard(user)

    task = asyncio.create_task(_run())
    _tasks.add(task); task.add_done_callback(_tasks.discard)

# Shared with the FTS half of the hybrid index — "he" counting as term overlap
# was skewing this ranker exactly as it skewed that one.
_STOP = vecstore.STOPWORDS


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower())
            if w.replace("'", "") not in _STOP and len(w) > 1}


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower().replace("'", "")).strip()


def _grounded(fact: str, source: str, need: float = 0.6) -> bool:
    """Is this "fact" actually supported by what the user wrote?

    Small models don't just paraphrase badly, they invent. Asked to extract from
    "What reminders do I have?", llama3.2:1b returned "Enjoys hiking on
    weekends", "Has a pet dog" and "Lives in New York City" — none of which
    appear anywhere in the input. Fabrications are the one error a memory store
    must not accept, because they persist into every later prompt.

    So a candidate is kept only if most of its content words appear in the
    user's own text. Paraphrase survives ("I prefer tea to coffee" →
    "Prefers tea to coffee"); invention doesn't.
    """
    terms = _terms(fact)
    if not terms:
        return False
    haystack = _terms(source)
    # Stem crudely so prefer/prefers and allergy/allergic still match.
    def stems(words):
        return {w[:5] for w in words}
    overlap = len(stems(terms) & stems(haystack)) / len(stems(terms))
    return overlap >= need


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
    """Top-k memories for this query: hybrid retrieval when the index is warm,
    BM25 otherwise, topped up with recent facts either way."""
    rows = await db.all_memories(user)
    if not rows: return []
    hits: list[str] = []
    if settings.enable_memory_embeddings:
        # Index in the background so a reply never waits on embedding; a fact
        # saved seconds ago may miss this search but still arrives via the
        # recency top-up below.
        _kick(user, vecstore.sync(user, rows))
        hits = await vecstore.search(user, query, k)
    if not hits:
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
        # Only what the *user* said. Feeding the assistant's turns in as well
        # poisons the corpus on a small utility model: llama3.2:1b dutifully
        # stored "The reminder was set", "I seem to have encountered a glitch"
        # and a gloss on the word "evening", while missing the two facts the
        # user had just stated outright.
        lines = [m["content"][:400] for m in msgs
                 if m["role"] == "user" and m.get("content")]
        if not lines: return
        prompt = (
            "Extract durable facts the user stated about themselves or their "
            "world: preferences, people, places, projects, commitments, dates, "
            "health. Rules:\n"
            "- Only facts the user asserted. Never anything you or the assistant said.\n"
            "- Skip questions, requests, greetings and anything transient "
            "(the time, today's weather, what was just done).\n"
            "- Each fact a short standalone sentence that still makes sense "
            "alone in a year: 'Allergic to shellfish', not 'they said that'.\n"
            "- Prefer an empty list over a guess.\n\n"
            'Reply with JSON {"facts": ["...", ...]}.\n\n'
            "Example input: I'm allergic to shellfish, and I prefer tea to coffee.\n"
            'Example output: {"facts": ["Allergic to shellfish", '
            '"Prefers tea to coffee"]}\n\n'
            "Now the user's messages:\n" + "\n".join(f"- {line}" for line in lines))
        payload = {"model": settings.ollama_model_utility or settings.ollama_model,
                   "stream": False, "format": "json",
                   "keep_alive": "2h",
                   "messages": [{"role": "user", "content": prompt}],
                   "options": {"temperature": 0.1, "num_predict": 300}}
        # Background call — a slow extraction never blocks a reply, so give it
        # a generous read budget rather than dropping facts on a timeout.
        body = await post_chat(payload)
        facts = _parse_facts(body.get("message", {}).get("content", ""))
        source = " ".join(lines)
        kept, rejected = [], []
        seen = {_norm(c) for _, c in await db.all_memories(user)}
        for fact in facts:
            # Too thin to be a memory: "By the way" is perfectly grounded and
            # perfectly useless, so require at least two content words.
            if len(fact) <= 5 or len(_terms(fact)) < 2 or _norm(fact) in seen:
                continue
            if not _grounded(fact, source):
                rejected.append(fact)
                continue
            # Near-duplicate guard: "Allergic to shellfish" and "I'm allergic
            # to shellfish" both come back from the same exchange.
            norm = _norm(fact)
            if any(norm in s or s in norm for s in seen):
                continue
            seen.add(norm)
            kept.append(fact)
        new = kept[:5]
        if rejected:
            log.warning("memory: dropped %d ungrounded fact(s) for %s: %s",
                        len(rejected), user, "; ".join(rejected[:3]))
        if new:
            ids = await db.add_memories(user, new)
            log.info("remembered %d fact(s) for %s", len(new), user)
            if settings.enable_memory_embeddings:
                # Already on a background task, so index inline — the next
                # turn's search then sees these facts.
                await vecstore.sync(user, list(zip(ids, new)))
    except Exception:
        log.exception("memory extraction failed for %s", user)
    finally:
        _extracting.discard(user)
