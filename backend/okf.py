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

_EXAMPLE = re.compile(r"^User:\s*(.+?)\n^You:\s*(.+?)(?=\n\s*\n|\n^User:|\Z)",
                      re.M | re.S)
_examples_cache: tuple[float, list[tuple[str, str]]] | None = None


def examples() -> list[tuple[str, str]]:
    """The (user, reply) register examples from persona.md, as pairs.

    Read from the bundle rather than copied into the code, so persona.md stays
    the single place the character is defined — editing it changes what she
    imitates on the next reply, with no restart and no second copy to drift.

    Only the plain conversational pairs. The "once a tool has actually run"
    examples below them are deliberately excluded: they describe what to say
    *after* a tool returned a value, and lifting one into a prompt where no tool
    ran is how she learns to announce things she never did.
    """
    global _examples_cache
    path = _bundle_dir() / "persona.md"
    try:
        stamp = path.stat().st_mtime
        if _examples_cache is None or _examples_cache[0] != stamp:
            body = path.read_text(encoding="utf-8")
            body = body.split("## The voice, once a tool has actually run")[0]
            pairs = [(u.strip(), r.strip().replace("\n", " "))
                     for u, r in _EXAMPLE.findall(body)]
            _examples_cache = (stamp, pairs)
        return _examples_cache[1]
    except Exception:
        log.exception("could not read register examples from %s", path)
        return []


def system_prompt() -> str:
    global _cache, _warned
    root = _bundle_dir()
    try:
        index = root / "index.md"
        concepts = [root / rel for rel in _LINK.findall(index.read_text(encoding="utf-8"))]
        # user.md is the living "who this user is" doc — personal, gitignored,
        # human-editable; included automatically when present.
        user_doc = root / "user.md"
        if user_doc.exists() and user_doc not in concepts:
            concepts.append(user_doc)
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
