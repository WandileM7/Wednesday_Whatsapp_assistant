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
    """Run background memory work — an index sync, a consolidation pass — one at
    a time per user, so two of them never rewrite the same store at once."""
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


# Shapes a small model returns when it was asked for {"facts": [...]}. Ollama's
# format:json constrains the reply to *valid* JSON, not to the right JSON, so
# what arrives is well-formed and the wrong shape: the list filed under a
# synonym, the facts wrapped one per object, or a lone fact as a bare string.
# Each of those parsed to nothing and threw away a whole extraction in silence.
_FACT_KEYS = ("facts", "memories", "user_facts", "items", "results", "list")
_FACT_FIELDS = ("fact", "text", "content", "memory", "statement", "value")


def _parse_facts(text: str) -> list[str]:
    """Facts from a model reply, tolerant of the shape it actually used.

    Tolerant, and not at all trusting: everything here recovers *candidates*.
    Both callers put them through _grounded afterwards, so a generous parse
    cannot let an invented fact through — it can only stop a badly shaped reply
    from discarding real ones.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(data, dict):
        for key in _FACT_KEYS:
            if key in data:
                data = data[key]
                break
        else:
            # An unrecognised key holding the whole payload — {"output": [...]}.
            # Only when there is exactly one, so a structured reply with several
            # fields isn't raided for whichever happens to come first.
            data = next(iter(data.values())) if len(data) == 1 else []
    if isinstance(data, str):
        data = [data]
    elif isinstance(data, dict):
        # {"0": "...", "1": "..."} — a list that came back keyed.
        data = list(data.values())
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if isinstance(item, dict):
            # [{"fact": "..."}] — right list, wrapped elements.
            item = next((item[f] for f in _FACT_FIELDS
                         if isinstance(item.get(f), str)), "")
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


# --- consolidation ----------------------------------------------------------
#
# The store is append-only, and over months that is a slow leak rather than a
# bug you can see: extraction dedupes only against the *exact* wording it
# already holds, so "Prefers tea to coffee" and "Drinks tea rather than coffee"
# both land. Worse, nothing ever supersedes — "Lives in Cape Town" and "Moved to
# Johannesburg in March" sit side by side and both get retrieved, so the prompt
# states two contradictory things about the user and the model picks one.
#
# Two designs were tried before this one and both were measured, because the
# obvious shapes of this task do not survive a small model:
#
#   1. "Here is the list, hand back a shorter one." Asked to shorten 32 facts,
#      qwen2.5:7b and llama3.2:3b both returned ~16, chosen on apparent
#      interest — a third of the subjects gone, including *both* halves of the
#      Cape Town / Johannesburg pair. `done_reason: stop`; not truncation. The
#      model reads "shorter" as "curate a shortlist", and no wording fixed it.
#   2. "Here is the numbered list, name the numbers to delete." Safer, since
#      keeping became the default and no new text could enter — but still 0/5 on
#      both models. The 3B asked to drop 13–23 of 32; the 7B deleted the newer
#      fact and kept the stale one. Thirty-two facts at once is the problem, not
#      the output format.
#
# So the model never sees the store. **Code finds candidate pairs, and the model
# only adjudicates one pair at a time** — the pattern guard.py and toolrouter
# already use, where a cheap deterministic pass narrows the question until it is
# small enough that a 3B answers it reliably.
#
# The property that buys: a fact with no near neighbour is never shown to the
# model, so it *cannot* be deleted. Neither earlier design could offer that. The
# blast radius of one bad answer is now one fact, not the store.
#
# Cost is bounded on purpose — at most _MAX_PAIRS_PER_PASS calls, each on a
# ~150-token prompt. Consolidation runs again as the store grows, so bounded
# work per pass still converges; it just takes several passes.

_MIN_TO_CONSOLIDATE = 30      # below this there is nothing worth merging
_PAIR_WINDOW = 40             # newest facts considered as candidates
_MAX_PAIRS_PER_PASS = 5       # model calls per pass, and so the damage ceiling
_MAX_DROP = 0.4               # share of the store one pass may delete
_CONSOLIDATE_EVERY = 15       # new facts between passes

# How alike two facts must be to be worth asking about. Both are deliberately
# loose: a false candidate costs one model call that answers "both", while a
# missed one means a duplicate lives forever.
_LEXICAL_MIN = 0.5            # shared stems, over the smaller fact
# Cosine, when embeddings exist. Measured on nomic-embed-text over the 496 pairs
# of a 32-fact store: unrelated pairs sit at median 0.376, p95 0.488, p99 0.553,
# while a restatement ("Prefers tea to coffee" / "Drinks tea rather than coffee")
# scores 0.931 and a supersession ("Lives in Cape Town" / "Moved to Johannesburg
# in March") scores 0.626. So the two real pairs rank #1 and #2, and the floor
# only has to clear the noise — it was 0.75 first, which missed every
# supersession in the suite while looking perfectly reasonable.
#
# Selection is by rank (best pairs first, capped at _MAX_PAIRS_PER_PASS), so this
# is a noise floor rather than a decision boundary. That matters if EMBED_MODEL
# changes: absolute cosine is not comparable across embedding models, but rank
# is, so a new model shifts which pairs clear the floor and not much else.
_COSINE_MIN = 0.60
# A ratio alone is not enough evidence on short facts: two facts of two content
# words each that share one word score 0.5, so "Has a dog called Rex" and "Has a
# cat called Mishka" would be offered up as possible duplicates. One coincidental
# word is not a signal — require a second.
_MIN_SHARED_STEMS = 2

# Facts that supersede each other are the same *attribute* with a different
# value, and that is exactly the case the other two detectors are worst at:
# "Lives in Cape Town" and "Moved to Johannesburg in March" share no content
# word, so lexical scores 0.0, and cosine only reaches 0.626 — real, but the
# weakest true signal in the set and unavailable at all when embeddings are off.
#
# The predicate, though, is right there in both. A person has one home, one
# employer, one phone number, so two facts asserting the same attribute are
# worth a question however differently they are worded. This is the detector
# that makes consolidation work with ENABLE_MEMORY_EMBEDDINGS=false.
#
# Over-matching is cheap and under-matching is not — a false candidate costs one
# call that answers "both", a missed one leaves a contradiction in the prompt
# forever — so these lean broad, exactly as toolrouter's groups do.
_TOPICS: tuple[tuple[str, re.Pattern], ...] = (
    ("home", re.compile(r"\b(?:lives?|living|based|resides?|moved|relocat\w*|"
                        r"settled|home is|address is|flat|apartment)\b", re.I)),
    ("employer", re.compile(r"\b(?:works? (?:at|for)|employed|employer|joined|"
                            r"job at|hired|resigned|quit|left (?:the )?(?:job|"
                            r"company)|promoted|redundan\w*)\b", re.I)),
    ("partner", re.compile(r"\b(?:married|marriage|engaged|fianc\w+|dating|"
                           r"partner|girlfriend|boyfriend|wife|husband|"
                           r"divorc\w+|separated|split up)\b", re.I)),
    ("contact", re.compile(r"\b(?:phone number|mobile number|number is|"
                           r"email(?: address)? is|reachable (?:at|on))\b", re.I)),
    ("vehicle", re.compile(r"\b(?:drives?|driving|car is|bakkie|sold the car|"
                           r"new car)\b", re.I)),
    ("study", re.compile(r"\b(?:stud(?:ies|ying|ied)|degree|enrolled|graduat\w+|"
                         r"university|course at)\b", re.I)),
)

# What a topic match is worth when neither other detector fires. Below a real
# restatement (0.67+) on purpose: same-attribute is a weaker signal than shared
# wording, and rank decides which pairs fit in the pass.
_TOPIC_SCORE = 0.55

_consolidating: set[str] = set()
_since_tidy: dict[str, int] = {}


# A fact about somebody else is not one of the user's attributes, and the
# predicate alone cannot tell the difference: "Sister is called Naledi and lives
# in Durban" matches `home` exactly as "Lives in Cape Town" does. Measured
# consequence of missing this — the pass paired the two, decided Johannesburg
# replaced Durban, and deleted the sister.
#
# Relations that name the *user's* own attributes are deliberately absent:
# wife/husband/partner belong to the `partner` topic and must keep matching it.
#
# The trade runs one way on purpose. A personal fact that happens to mention a
# relative ("Moved in with my sister in Durban") loses its topic and the pair
# goes unasked — a contradiction survives, which is the cost we already pay
# everywhere embeddings are off. The reverse error deletes a real memory.
_THIRD_PARTY = re.compile(
    r"\b(?:sister|brother|mum|mom|dad|father|mother|parents?|cousin|aunt|uncle|"
    r"nephew|niece|son|daughter|grandmother|grandfather|friend|colleague|"
    r"manager|boss|landlord|landlady|neighbou?r|doctor|dentist|barber|"
    r"godmother|godfather)\b", re.I)


def _topics(text: str) -> set[str]:
    """Attributes this fact asserts about *the user*. Empty for anyone else's."""
    text = text or ""
    if _THIRD_PARTY.search(text):
        return set()
    return {name for name, pattern in _TOPICS if pattern.search(text)}


def _stems(text: str) -> set[str]:
    """Content words clipped to five characters, so prefer/prefers still match."""
    return {w[:5] for w in _terms(text)}


def _lexical(a: str, b: str) -> float:
    """Shared stems as a fraction of the *smaller* fact.

    Over the smaller one rather than the union, because a short fact restated at
    length is still a duplicate: "Prefers tea to coffee" against "Drinks tea
    rather than coffee" scores 0.67 this way and 0.4 over the union, and only the
    first is worth asking about.
    """
    sa, sb = _stems(a), _stems(b)
    if not sa or not sb:
        return 0.0
    shared = sa & sb
    if len(shared) < _MIN_SHARED_STEMS:
        return 0.0
    return len(shared) / min(len(sa), len(sb))


def _candidates(rows: list[tuple[int, str]],
                vecs: dict[int, list[float]]) -> list[tuple[float, int, int]]:
    """(score, older_index, newer_index) pairs worth adjudicating, best first.

    Three detectors, because they fail in different places and only two of them
    are always available:

      - Lexical overlap finds restatements, and needs nothing.
      - Shared topic finds two facts asserting the same attribute — a home, an
        employer — however differently worded, and also needs nothing. This is
        what catches supersession without embeddings.
      - Cosine finds the rest: same subject, different words, no shared
        predicate. Strongest signal when it is available (a restatement scores
        0.931 against a 0.376 median) and simply absent when embeddings are off.

    Any one of them qualifies a pair; the score is the best of the three, and
    rank decides which qualified pairs actually fit in the pass.
    """
    scored: list[tuple[float, int, int]] = []
    for older in range(len(rows)):
        for newer in range(older + 1, len(rows)):
            a_id, a_text = rows[older]
            b_id, b_text = rows[newer]
            lex = _lexical(a_text, b_text)
            cos = 0.0
            if (va := vecs.get(a_id)) and (vb := vecs.get(b_id)):
                cos = vecstore.similarity(va, vb)
            topic = _TOPIC_SCORE if _topics(a_text) & _topics(b_text) else 0.0
            # Any one detector qualifies the pair; they have separate thresholds
            # because they are on unrelated scales.
            if lex >= _LEXICAL_MIN or cos >= _COSINE_MIN or topic:
                scored.append((max(lex, cos, topic), older, newer))
    scored.sort(reverse=True)

    # One fact per pass at most: adjudicating a row twice could delete it on the
    # first verdict and then compare a ghost on the second.
    chosen: list[tuple[float, int, int]] = []
    used: set[int] = set()
    for score, older, newer in scored:
        if older in used or newer in used:
            continue
        chosen.append((score, older, newer))
        used.update((older, newer))
        if len(chosen) >= _MAX_PAIRS_PER_PASS:
            break
    return chosen


_ADJUDICATE_PROMPT = (
    "Two facts remembered about the same person. Fact 2 was recorded later than "
    "fact 1.\n\n"
    "1. {older}\n"
    "2. {newer}\n\n"
    "Decide which of these is true, and reply with JSON:\n"
    '{{"verdict": "both"}} — both are true and each says something the other '
    "does not.\n"
    '{{"verdict": "same"}} — they say the same thing in different words.\n'
    '{{"verdict": "replaced"}} — fact 2 replaces fact 1, so fact 1 is no longer '
    "true (a move, a job change, something that ended).\n\n"
    'Answer "both" unless you are confident. Two facts about the same topic are '
    "usually both worth keeping — only say \"replaced\" when fact 2 genuinely "
    "makes fact 1 false, and \"same\" when the two really are one fact.\n")

_VERDICT_KEYS = ("verdict", "answer", "decision", "result", "choice")
_DROPS_THE_OLDER = ("same", "replaced")


def _parse_verdict(text: str) -> str:
    """The verdict, or "" when the reply made no sense.

    Unrecognised means "both" at the call site: the only actions are keep and
    delete, and a reply we could not read is never grounds for deleting.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ""
    if isinstance(data, dict):
        for key in _VERDICT_KEYS:
            if isinstance(data.get(key), str):
                data = data[key]
                break
        else:
            data = next((v for v in data.values() if isinstance(v, str)), "") \
                if len(data) == 1 else ""
    if not isinstance(data, str):
        return ""
    word = data.strip().strip(".").lower()
    return word if word in ("both", *_DROPS_THE_OLDER) else ""


async def _adjudicate(older: str, newer: str, *, transport=None) -> str:
    """Ask about one pair. Returns "both" for anything that fails to parse."""
    payload = {"model": settings.ollama_model_utility or settings.ollama_model,
               "stream": False, "format": "json", "keep_alive": "2h",
               "messages": [{"role": "user", "content": _ADJUDICATE_PROMPT.format(
                   older=older, newer=newer)}],
               "options": {"temperature": 0.0, "num_predict": 60}}
    body = await post_chat(payload, transport=transport)
    return _parse_verdict(body.get("message", {}).get("content", "")) or "both"


async def consolidate(user: str, *, transport=None) -> int:
    """Delete facts a later or clearer one has made redundant.

    Returns the number of rows removed (0 when it declined to act). Never
    raises, and every path that fails a check leaves the store untouched.
    """
    if user in _consolidating:
        return 0
    _consolidating.add(user)
    try:
        stored = await db.all_memories(user)
        if len(stored) < _MIN_TO_CONSOLIDATE:
            return 0
        # all_memories is newest first. Reverse to oldest-first, then keep the
        # newest slice: recent extraction is where duplicates come from, and a
        # window bounds the pair scan. Pairs older than the window go uncaught.
        rows = list(reversed(stored))[-_PAIR_WINDOW:]

        vecs = await vecstore.vectors(user, [mid for mid, _ in rows])
        pairs = _candidates(rows, vecs)
        if not pairs:
            return 0

        doomed: list[tuple[int, str, str]] = []
        for _score, older, newer in pairs:
            verdict = await _adjudicate(rows[older][1], rows[newer][1],
                                        transport=transport)
            if verdict in _DROPS_THE_OLDER:
                doomed.append((rows[older][0], rows[older][1], verdict))
        if not doomed:
            return 0

        # Cannot currently trigger — _MAX_PAIRS_PER_PASS drops at most 5 rows
        # from a store of at least 30. It stays so that raising the pair limit
        # later cannot quietly unbound how much one pass may delete.
        if len(doomed) > len(stored) * _MAX_DROP:
            log.warning("memory: consolidation for %s would drop %d of %d facts; "
                        "refusing", user, len(doomed), len(stored))
            return 0

        await db.replace_memories(user, [mid for mid, _, _ in doomed], [])
        for _mid, text, verdict in doomed:
            log.info("memory: dropped %r for %s (%s)", text, user, verdict)
        if settings.enable_memory_embeddings:
            # sync() reconciles against the whole truth, so handing it what is
            # left is what retires the deleted rows from both indexes.
            await vecstore.sync(user, await db.all_memories(user))
        return len(doomed)
    except Exception:
        log.exception("memory consolidation failed for %s", user)
        return 0
    finally:
        _consolidating.discard(user)


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
            # Tidy the store once enough has piled up to be worth a model call.
            # The counter is in RAM, so a restart only ever *delays* a pass —
            # the cost of forgetting it is one late consolidation, not a lost or
            # doubled one, and consolidate() is idempotent either way.
            _since_tidy[user] = _since_tidy.get(user, 0) + len(new)
            if _since_tidy[user] >= _CONSOLIDATE_EVERY:
                _since_tidy[user] = 0
                _kick(user, consolidate(user))
    except Exception:
        log.exception("memory extraction failed for %s", user)
    finally:
        _extracting.discard(user)
