"""Local document Q&A: index a folder of notes and rank passages for a query.

Drop .md/.txt files in `DOCUMENTS_DIR` (default `documents/`) and Wednesday can
quote them back — lease agreements, meeting notes, a CV, anything. Files are
chunked into passages and ranked with the same BM25 scorer memory retrieval
uses (`memory._bm25`).

Why BM25 and not embeddings: no embedding model is pulled locally, embedding on
this CPU costs real seconds per query, and vector rows would fork the sqlite/
Postgres story the way FTS5 would. BM25 is instant, dependency-free and
identical on both backends. Embeddings via Ollama (`nomic-embed-text`) remain
the upgrade path if lexical relevance ever falls short.

The index is rebuilt when any file's mtime changes, mirroring okf.py — edit a
note and the next question sees it, no restart.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)

SUFFIXES = {".md", ".txt", ".markdown", ".rst"}
_MAX_BYTES = 2_000_000        # skip anything pathological
_CHUNK_CHARS = 800            # passage size; a few paragraphs
_cache: tuple[tuple, list[dict]] | None = None


def _dir() -> Path:
    p = Path(settings.documents_dir).expanduser()
    return p if p.is_absolute() else Path(__file__).resolve().parent.parent / p


def _files() -> list[Path]:
    root = _dir()
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in SUFFIXES
                  and p.stat().st_size <= _MAX_BYTES)


def _chunk(text: str) -> list[str]:
    """Split on blank lines, then pack paragraphs into ~_CHUNK_CHARS passages so
    a passage keeps enough context to answer from."""
    out: list[str] = []
    buf = ""
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if buf and len(buf) + len(para) + 2 > _CHUNK_CHARS:
            out.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        out.append(buf)
    return out


def index() -> list[dict]:
    """All passages across the folder, rebuilt when any file changes."""
    global _cache
    files = _files()
    root = _dir()
    # Absolute paths already make the stamp folder-specific; the root is included
    # so the key stays correct if the folder itself changes (defensive, not a fix).
    stamp = (str(root), tuple((str(p), p.stat().st_mtime) for p in files))
    if _cache is not None and _cache[0] == stamp:
        return _cache[1]
    passages: list[dict] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log.warning("could not read %s", path)
            continue
        rel = str(path.relative_to(root))
        for i, chunk in enumerate(_chunk(text)):
            passages.append({"source": rel, "chunk": i, "text": chunk})
    _cache = (stamp, passages)
    log.info("documents indexed: %d passage(s) from %d file(s)", len(passages), len(files))
    return passages


def search(query: str, limit: int = 3) -> list[dict] | str:
    """Best-matching passages for the query, or a plain message when there's
    nothing to search / nothing matched."""
    from .memory import _bm25, _terms
    passages = index()
    if not passages:
        return (f"No documents indexed. Put .md or .txt files in "
                f"{settings.documents_dir}/ for me to read.")
    # _bm25 breaks score ties by descending id, so invert the index: earlier
    # passages win a tie, which reads as "first mention in the document".
    n = len(passages)
    ranked = _bm25(_terms(query), [(n - i, p["text"]) for i, p in enumerate(passages)])
    hits = [passages[n - i] for score, i, _ in ranked if score > 0][:limit]
    if not hits:
        return "Nothing in your documents matches that."
    return hits
