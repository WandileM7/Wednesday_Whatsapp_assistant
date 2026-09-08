"""Skills: reusable how-to instructions the agent loads on demand.

A skill is a markdown file in okf/skills/ with `name:` and `description:`
frontmatter. The catalog (one line per skill) is injected into the system
prompt; the agent fetches a skill's full body with the use_skill tool only
when needed, keeping the prompt token-cheap.

Self-improvement with a human gate: the agent drafts skills into
okf/skills/proposals/ via propose_skill; nothing takes effect until the
user reviews the file and moves it up into okf/skills/.
"""
from __future__ import annotations
import json, logging, re
from pathlib import Path

from .config import settings

log = logging.getLogger(__name__)
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_cache: tuple[tuple, list[dict]] | None = None


def _dir() -> Path:
    p = Path(settings.okf_dir).expanduser()
    root = p if p.is_absolute() else Path(__file__).resolve().parent.parent / p
    return root / "skills"


def _proposals_dir() -> Path:
    return _dir() / "proposals"


def _parse(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = _FRONT.match(text)
    if not m: return None
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.MULTILINE))
    if "name" not in meta or "description" not in meta: return None
    return {"name": meta["name"].strip(), "description": meta["description"].strip(),
            "body": text[m.end():].strip(), "path": path}


def catalog() -> list[dict]:
    """Approved skills, mtime-cached like the OKF bundle."""
    global _cache
    d = _dir()
    if not d.is_dir(): return []
    files = sorted(p for p in d.glob("*.md"))
    stamp = tuple((str(p), p.stat().st_mtime) for p in files)
    if _cache is None or _cache[0] != stamp:
        skills = [s for p in files if (s := _parse(p)) is not None]
        _cache = (stamp, skills)
        if skills: log.info("skill catalog: %s", [s["name"] for s in skills])
    return _cache[1]


def catalog_lines() -> str:
    lines = [f"- {s['name']}: {s['description']}" for s in catalog()]
    return "\n".join(lines)


def body(name: str) -> str | None:
    for s in catalog():
        if s["name"] == name:
            _bump_usage(name)
            return s["body"]
    return None


def propose(name: str, description: str, content: str) -> Path:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "skill"
    d = _proposals_dir(); d.mkdir(parents=True, exist_ok=True)
    path = d / f"{slug}.md"
    path.write_text(f"---\nname: {slug}\ndescription: {description.strip()}\n---\n\n"
                    f"{content.strip()}\n", encoding="utf-8")
    return path


# -- usage tracking (json sidecar; feeds the weekly curator report) ----------

def _usage_path() -> Path:
    return _dir() / ".usage.json"


def _load_usage() -> dict[str, int]:
    try: return json.loads(_usage_path().read_text())
    except (OSError, json.JSONDecodeError): return {}


def _bump_usage(name: str) -> None:
    try:
        d = _dir()
        if not d.is_dir(): return
        usage = _load_usage(); usage[name] = usage.get(name, 0) + 1
        _usage_path().write_text(json.dumps(usage, indent=1))
    except OSError:
        log.debug("could not record skill usage for %s", name)


def curator_report() -> str | None:
    """Weekly health check: what exists, what gets used, what's waiting."""
    skills, usage = catalog(), _load_usage()
    proposals = sorted(p.name for p in _proposals_dir().glob("*.md")) \
        if _proposals_dir().is_dir() else []
    if not skills and not proposals: return None
    lines = ["📚 Weekly skill report:"]
    for s in skills:
        lines.append(f"- {s['name']}: used {usage.get(s['name'], 0)}x")
    unused = [s["name"] for s in skills if not usage.get(s["name"])]
    if unused: lines.append(f"Consider pruning (never used): {', '.join(unused)}")
    if proposals: lines.append(f"Awaiting your review in okf/skills/proposals/: {', '.join(proposals)}")
    return "\n".join(lines)
