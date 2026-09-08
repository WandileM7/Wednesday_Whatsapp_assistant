"""Hybrid memory index: FTS5 keyword search + sqlite-vec semantic search.

Lives in its own SQLite file rather than the main database, for two reasons:
compose runs Postgres (where neither FTS5 nor sqlite-vec exists), and an index
that can be deleted and rebuilt from `memories` at any time is one less thing
to migrate. Embeddings come from Ollama, so this stays local and free.

Degradation is layered, because none of this is worth a broken assistant:

    sqlite-vec loaded ────► KNN over a vec0 virtual table
    extension missing ────► brute-force cosine in Python (a few hundred rows)
    embeddings failing ───► FTS5 keyword hits only
    index empty/cold ─────► caller falls back to the lexical scan in memory.py

Keyword and vector ranks are fused with Reciprocal Rank Fusion: neither
retriever's scores are comparable to the other's, but their *ranks* are.
"""
from __future__ import annotations
import asyncio, logging, sqlite3, struct
from pathlib import Path

import httpx
from .config import settings

log = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None
_lock = asyncio.Lock()
_vec_ok = False          # sqlite-vec extension loaded?
_dim = 0                 # embedding width, learned from the first vector
_embed_broken = False    # stop retrying a model that isn't there
_RRF_K = 60              # standard RRF damping constant

# Words that carry no retrieval signal. This matters more than it looks: an
# FTS5 MATCH is an OR over the query's terms, so leaving "he" in means every
# memory mentioning him matches, and that noise enters the fusion at a good
# rank and outranks the vector half's actual answer. Measured on a 10-fact
# set, dropping these took hybrid top-1 from 4/8 to 8/8.
STOPWORDS = frozenset(
    "a about an and any are as at be been but by can cant could did didnt do "
    "does doesnt dont for from get got had has have he her hers him his how i "
    "if in into is it its me my no not of on or our should so some tell that "
    "the their them then there they this to us was we were what when where "
    "which who will with would you your".split())


# ---- connection -------------------------------------------------------------

def _open() -> sqlite3.Connection:
    global _vec_ok, _dim
    path = Path(settings.vector_db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        _vec_ok = True
    except Exception as exc:  # noqa: BLE001 — no extension support is survivable
        _vec_ok = False
        log.info("sqlite-vec unavailable (%s); using brute-force cosine instead", exc)
    conn.execute("""CREATE TABLE IF NOT EXISTS mem (
                      id INTEGER PRIMARY KEY, user_key TEXT, content TEXT, embedding BLOB)""")
    conn.execute("CREATE INDEX IF NOT EXISTS mem_user ON mem(user_key)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(content)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.commit()
    # vec_mem exists iff a width was recorded, so this tells a fresh process
    # whether it can KNN before the first sync of the run.
    if row := conn.execute("SELECT v FROM meta WHERE k='dim'").fetchone():
        _dim = int(row[0])
    return conn


async def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        async with _lock:
            if _conn is None:
                _conn = await asyncio.to_thread(_open)
    return _conn


async def close() -> None:
    """Checkpoint the WAL and close the index connection.

    Nothing used to close it, and a WAL sidecar does not tidy itself. SQLite's
    automatic checkpoint is *passive*: it copies committed pages back into the
    database and then leaves the -wal file sitting at its high-water mark, to be
    reused rather than shrunk. Only a TRUNCATE checkpoint — or the last
    connection closing cleanly — actually reclaims it.

    So with no clean shutdown the file survives every run and only ever ratchets
    upward. Observed here at 6.9 MB against a 3.2 MB database, with a modified
    time older than the process that was using it: recovered on open, never
    truncated, growing. Both costs are small and permanent — a longer open while
    it is replayed, and a bigger working set for every read.

    Safe to call when the index was never opened, and safe to call twice: the
    next _db() simply reopens. Failures are logged and swallowed, because this
    runs on the shutdown path where raising would mask whatever else is closing.
    """
    global _conn
    conn, _conn = _conn, None
    if conn is None:
        return

    def _shut() -> None:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_shut)
    except Exception:  # noqa: BLE001 — shutdown must not fail on its way out
        log.warning("memory index did not close cleanly", exc_info=True)


def _ensure_vec_table(conn: sqlite3.Connection, dim: int) -> None:
    """Create (or recreate, if the model's width changed) the vec0 table."""
    global _dim
    if not _vec_ok:
        _dim = dim
        return
    row = conn.execute("SELECT v FROM meta WHERE k='dim'").fetchone()
    stored = int(row[0]) if row else 0
    if stored != dim:
        conn.execute("DROP TABLE IF EXISTS vec_mem")
        conn.execute(f"CREATE VIRTUAL TABLE vec_mem USING vec0(embedding float[{dim}])")
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('dim', ?)", (str(dim),))
        # A width change means every stored vector is from a different model.
        conn.execute("UPDATE mem SET embedding = NULL")
        conn.commit()
    _dim = dim


# ---- embeddings -------------------------------------------------------------

async def embed(texts: list[str]) -> list[list[float]]:
    """Embed via Ollama. Returns [] if embeddings aren't usable — callers treat
    that as "keyword only", never as an error."""
    global _embed_broken
    if _embed_broken or not texts:
        return []
    payload = {"model": settings.embed_model, "input": texts}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
            r = await client.post(f"{settings.ollama_host}/api/embed", json=payload)
            if r.status_code == 404:  # older Ollama: one text per call
                out = []
                for text in texts:
                    er = await client.post(f"{settings.ollama_host}/api/embeddings",
                                           json={"model": settings.embed_model, "prompt": text})
                    er.raise_for_status()
                    out.append(er.json()["embedding"])
                return out
            r.raise_for_status()
            return r.json().get("embeddings", [])
    except Exception as exc:  # noqa: BLE001
        _embed_broken = True
        log.warning("embeddings unavailable (%s) — memory falls back to keyword "
                    "search. Pull the model with: ollama pull %s", exc, settings.embed_model)
        return []


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


# ---- indexing ---------------------------------------------------------------

def backend_name() -> str:
    """Which retrieval path is live, for /doctor. Only meaningful once the
    index has been opened (any search or sync does that)."""
    if not settings.enable_memory_embeddings:
        return "off — lexical scan only"
    if _conn is None:
        return "fts5 + sqlite-vec (not opened yet)"
    return "fts5 + sqlite-vec" if _vec_ok else "fts5 + brute-force cosine (sqlite-vec not loaded)"


def _drop(conn, ids) -> None:
    """Remove rows from all three tables that shadow a memory.

    A row lives in `mem`, in the `mem_fts` keyword index and in `vec_mem`, and a
    memory is only really gone when it is gone from all three — leaving it in
    either index keeps it searchable and so keeps it in the prompt.
    """
    for mid in ids:
        conn.execute("DELETE FROM mem WHERE id = ?", (mid,))
        conn.execute("DELETE FROM mem_fts WHERE rowid = ?", (mid,))
        if _vec_ok:
            conn.execute("DELETE FROM vec_mem WHERE rowid = ?", (mid,))
    conn.commit()


async def sync(user: str, rows: list[tuple[int, str]]) -> int:
    """Mirror this user's memories into the index — additions *and* deletions.

    `rows` is the (id, content) list the caller already has, so the common case
    (nothing new, nothing gone) costs one SELECT and no model call.

    This was add-only, and the omission was not benign. `rows` is the whole
    truth — every memory the user has — so anything indexed but absent from it
    has been deleted upstream. Skipping that half left deleted facts searchable
    forever: one account's memories table held a single row, "lives in Cape
    Town", while recall kept returning four phantoms from a period of degenerate
    output ("run system diagnostics", "Let's go back to Command Center") and
    injecting them into every prompt as things known about the user. Deleting a
    memory has to mean it stops coming back.
    """
    if not settings.enable_memory_embeddings or not rows:
        return 0
    conn = await _db()

    def _known() -> set[int]:
        return {r[0] for r in conn.execute(
            "SELECT id FROM mem WHERE user_key = ?", (user,)).fetchall()}

    known = await asyncio.to_thread(_known)
    missing = [(mid, content) for mid, content in rows if mid not in known]
    if (stale := known - {mid for mid, _ in rows}):
        await asyncio.to_thread(_drop, conn, stale)
        log.info("memory index: -%d stale row(s) for %s", len(stale), user)
    if not missing:
        return 0
    vectors = await embed([c for _, c in missing])

    def _write() -> None:
        if vectors:
            _ensure_vec_table(conn, len(vectors[0]))
        for i, (mid, content) in enumerate(missing):
            vec = vectors[i] if i < len(vectors) else None
            blob = _pack(vec) if vec else None
            conn.execute("INSERT OR REPLACE INTO mem VALUES (?,?,?,?)",
                         (mid, user, content, blob))
            conn.execute("DELETE FROM mem_fts WHERE rowid = ?", (mid,))
            conn.execute("INSERT INTO mem_fts(rowid, content) VALUES (?,?)", (mid, content))
            if vec and _vec_ok:
                conn.execute("DELETE FROM vec_mem WHERE rowid = ?", (mid,))
                conn.execute("INSERT INTO vec_mem(rowid, embedding) VALUES (?,?)", (mid, blob))
        conn.commit()

    await asyncio.to_thread(_write)
    log.info("memory index: +%d row(s) for %s%s", len(missing), user,
             "" if vectors else " (keyword only — no embeddings)")
    return len(missing)


async def forget(user: str) -> None:
    """Drop a user's rows; called when their conversation is reset."""
    conn = await _db()

    def _run() -> None:
        _drop(conn, [r[0] for r in conn.execute(
            "SELECT id FROM mem WHERE user_key = ?", (user,)).fetchall()])

    await asyncio.to_thread(_run)


# ---- retrieval --------------------------------------------------------------

def _match_expr(query: str) -> str:
    """FTS5 MATCH expression: OR over the query's content words, each quoted so
    punctuation can't be read as operator syntax. An all-stopword query yields
    "", which skips the keyword half and lets the vectors answer alone."""
    import re
    terms = [t for t in re.findall(r"[A-Za-z0-9']+", query.lower())
             if len(t) > 1 and t.replace("'", "") not in STOPWORDS]
    return " OR ".join(f'"{t}"' for t in terms)


async def vectors(user: str, ids: list[int]) -> dict[int, list[float]]:
    """Stored embeddings for these memory ids, for comparing facts to each other.

    `search` compares the *query* against the store; consolidation needs the
    store against itself, which nothing else asked for. Rows with no embedding
    yet are simply absent from the result — a caller has to cope with a partial
    answer anyway, since indexing is a background job and embeddings arrive
    late.

    Read-only and does no embedding of its own on purpose: consolidation runs on
    a slow box, and a pass that silently triggered thirty model calls to fill in
    what the indexer had not got to yet would cost more than it saves.
    """
    if not settings.enable_memory_embeddings or not ids:
        return {}
    conn = await _db()

    def _read() -> dict[int, list[float]]:
        out: dict[int, list[float]] = {}
        # Chunked so a large store cannot build a statement past SQLITE_MAX_VARS.
        for start in range(0, len(ids), 400):
            chunk = ids[start:start + 400]
            marks = ",".join("?" * len(chunk))
            for mid, blob in conn.execute(
                    f"SELECT id, embedding FROM mem WHERE user_key = ? "
                    f"AND embedding IS NOT NULL AND id IN ({marks})",
                    (user, *chunk)).fetchall():
                out[mid] = _unpack(blob)
        return out

    return await asyncio.to_thread(_read)


def similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two stored vectors. Public for consolidation."""
    return _cosine(a, b)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def search(user: str, query: str, k: int = 6) -> list[str]:
    """Top-k memory contents for this query, keyword and vector ranks fused."""
    if not settings.enable_memory_embeddings:
        return []
    conn = await _db()
    qvec = (await embed([query]) or [None])[0]

    def _run() -> list[str]:
        mine = {r[0]: r[1] for r in conn.execute(
            "SELECT id, content FROM mem WHERE user_key = ?", (user,)).fetchall()}
        if not mine:
            return []
        ranks: dict[int, float] = {}

        if expr := _match_expr(query):
            try:
                hits = conn.execute(
                    "SELECT rowid FROM mem_fts WHERE mem_fts MATCH ? ORDER BY rank LIMIT ?",
                    (expr, k * 4)).fetchall()
                for rank, (mid,) in enumerate(h for h in hits if h[0] in mine):
                    ranks[mid] = ranks.get(mid, 0) + 1 / (_RRF_K + rank)
            except sqlite3.OperationalError as exc:
                log.debug("fts query failed for %r: %s", query, exc)

        if qvec:
            ordered: list[int] = []
            if _vec_ok and _dim:
                # vec0 KNN has no user filter, so over-fetch and filter after.
                rows = conn.execute(
                    "SELECT rowid FROM vec_mem WHERE embedding MATCH ? AND k = ? "
                    "ORDER BY distance", (_pack(qvec), k * 4)).fetchall()
                ordered = [r[0] for r in rows if r[0] in mine]
            else:
                scored = [(mid, _cosine(qvec, _unpack(blob)))
                          for mid, blob in conn.execute(
                              "SELECT id, embedding FROM mem "
                              "WHERE user_key = ? AND embedding IS NOT NULL", (user,))]
                scored.sort(key=lambda t: t[1], reverse=True)
                ordered = [mid for mid, _ in scored[:k * 4]]
            for rank, mid in enumerate(ordered):
                ranks[mid] = ranks.get(mid, 0) + 1 / (_RRF_K + rank)

        best = sorted(ranks.items(), key=lambda t: t[1], reverse=True)[:k]
        return [mine[mid] for mid, _ in best]

    try:
        return await asyncio.to_thread(_run)
    except Exception:
        log.exception("hybrid memory search failed; falling back to lexical")
        return []
