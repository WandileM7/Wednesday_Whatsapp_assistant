"""Open Knowledge Format (OKF) bundle loader.

The system prompt is assembled from markdown concept files (YAML front
matter + body) linked from the bundle's index.md, in link order. Files
are re-read when their mtimes change, so persona/prompt edits land on
the next reply without a restart. Falls back to settings.system_prompt
if the bundle is missing or unreadable.
"""
from __future__ import annotations
import logging, re
from pathlib import Path
from .config import settings

log = logging.getLogger(__name__)
_LINK = re.compile(r"\[[^\]]*\]\(([^)#]+\.md)\)")
_FRONT = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

_cache: tuple[tuple, str] | None = None
_warned = False

def _bundle_dir() -> Path:
    p = Path(settings.okf_dir).expanduser()
    return p if p.is_absolute() else Path(__file__).resolve().parent.parent / p

def _body(path: Path) -> str:
    return _FRONT.sub("", path.read_text(encoding="utf-8")).strip()

def system_prompt() -> str:
    global _cache, _warned
    root = _bundle_dir()
    try:
        index = root / "index.md"
        concepts = [root / rel for rel in _LINK.findall(index.read_text(encoding="utf-8"))]
        stamp = tuple((str(p), p.stat().st_mtime) for p in concepts)
        if _cache is None or _cache[0] != stamp:
            prompt = "\n\n".join(_body(p) for p in concepts)
            if not prompt:
                raise ValueError(f"no concepts linked from {index}")
            _cache = (stamp, prompt)
            _warned = False
            log.info("OKF bundle loaded: %d concepts from %s", len(concepts), root)
        return _cache[1]
    except Exception:
        if not _warned:
            _warned = True
            log.exception("OKF bundle unavailable at %s; using fallback prompt", root)
        return settings.system_prompt
