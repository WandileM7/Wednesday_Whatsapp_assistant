from __future__ import annotations
import base64 as _b64
import datetime as _dt
import hashlib as _hl
import json
from typing import AsyncIterator
from sqlalchemy import DateTime, String, Text, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .config import settings

class Base(DeclarativeBase): pass

# OAuth tokens are encrypted at rest with a key derived from SESSION_SECRET.
# Changing the secret orphans stored tokens (relink via /auth/*).
def _fernet():
    from cryptography.fernet import Fernet
    key = _b64.urlsafe_b64encode(_hl.sha256(settings.session_secret.encode()).digest())
    return Fernet(key)

def _enc(value: str | None) -> str | None:
    return _fernet().encrypt(value.encode()).decode() if value else value

def _dec(value: str | None) -> str | None:
    if not value: return value
    from cryptography.fernet import InvalidToken
    try: return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError): return value  # legacy plaintext row

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[_dt.datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # tool name
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.utcnow)

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.utcnow)

class Person(Base):
    """Someone in the user's world. name_key is the lowercased name so recall is
    case-insensitive; notes accumulate one fact per line."""
    __tablename__ = "people"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.utcnow,
                                                     onupdate=_dt.datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="reminder")
    text: Mapped[str] = mapped_column(Text)
    due_at: Mapped[_dt.datetime] = mapped_column(DateTime)  # local time
    recur_minutes: Mapped[int | None] = mapped_column(nullable=True)
    done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.now)

class ToolApproval(Base):
    __tablename__ = "tool_approvals"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(64), primary_key=True)

class Summary(Base):
    __tablename__ = "summaries"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.utcnow,
                                                     onupdate=_dt.datetime.utcnow)

class Pref(Base):
    """Per-user settings Wednesday can change about herself, at the user's ask.

    Distinct from `memories`, which are facts about the user: these are knobs.
    "Stop sending voice notes" has to survive a restart, and it is not a fact
    worth recalling in a prompt.
    """
    __tablename__ = "prefs"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_pref(user_key: str, name: str) -> str | None:
    async with SessionLocal() as s:
        row = await s.get(Pref, (user_key, name))
    return row.value if row else None


async def set_pref(user_key: str, name: str, value: str) -> None:
    async with SessionLocal() as s:
        row = await s.get(Pref, (user_key, name))
        if row: row.value = value
        else: s.add(Pref(user_key=user_key, name=name, value=value))
        await s.commit()


async def save_token(service, access_token, refresh_token, expires_at, scope=None):
    access_token, refresh_token = _enc(access_token), _enc(refresh_token)
    async with SessionLocal() as s:
        existing = await s.get(OAuthToken, service)
        if existing:
            existing.access_token = access_token
            if refresh_token: existing.refresh_token = refresh_token
            existing.expires_at = expires_at
            existing.scope = scope
        else:
            s.add(OAuthToken(service=service, access_token=access_token,
                             refresh_token=refresh_token, expires_at=expires_at, scope=scope))
        await s.commit()

async def get_token(service: str) -> OAuthToken | None:
    async with SessionLocal() as s:
        token = await s.get(OAuthToken, service)
    if token is not None:  # decrypt on the detached instance only
        token.access_token = _dec(token.access_token)
        token.refresh_token = _dec(token.refresh_token)
    return token

async def add_messages(user_key: str, msgs: list[dict]) -> None:
    async with SessionLocal() as s:
        for m in msgs:
            s.add(Message(user_key=user_key, role=m["role"], content=m.get("content") or "",
                          tool_calls=json.dumps(m["tool_calls"]) if m.get("tool_calls") else None,
                          name=m.get("name")))
        await s.commit()

async def recent_messages(user_key: str, limit: int = 100) -> list[dict]:
    """Last `limit` messages, oldest first, in Ollama chat format."""
    async with SessionLocal() as s:
        rows = (await s.execute(select(Message).where(Message.user_key == user_key)
                                .order_by(Message.id.desc()).limit(limit))).scalars().all()
    out = []
    for r in reversed(rows):
        m: dict = {"role": r.role, "content": r.content}
        if r.tool_calls: m["tool_calls"] = json.loads(r.tool_calls)
        if r.name: m["name"] = r.name
        out.append(m)
    return out

async def raw_messages(user_key: str) -> list[dict]:
    """Every stored message with its id, oldest first — for the hygiene sweep,
    which needs to identify individual rows rather than build a prompt."""
    async with SessionLocal() as s:
        rows = (await s.execute(select(Message).where(Message.user_key == user_key)
                                .order_by(Message.id))).scalars().all()
    return [{"id": m.id, "role": m.role, "content": m.content,
             "tool_calls": m.tool_calls, "name": m.name} for m in rows]


async def rewrite_messages(edits: dict[int, str]) -> int:
    """Replace the content of specific messages, leaving role and ordering alone.

    The hygiene sweep deletes messages that are false. A learned verbal tic is
    not false — the reply around it is worth keeping — but left in place it is
    still the example the next turn copies, so it needs cutting out rather than
    the whole row dropping.
    """
    if not edits: return 0
    async with SessionLocal() as s:
        for mid, content in edits.items():
            await s.execute(update(Message).where(Message.id == mid)
                            .values(content=content))
        await s.commit()
    return len(edits)


async def delete_messages(ids: list[int]) -> int:
    if not ids: return 0
    async with SessionLocal() as s:
        await s.execute(delete(Message).where(Message.id.in_(ids)))
        await s.commit()
    return len(ids)


async def all_user_keys() -> list[str]:
    async with SessionLocal() as s:
        rows = (await s.execute(select(Message.user_key).distinct())).scalars().all()
    return list(rows)


async def clear_messages(user_key: str) -> None:
    async with SessionLocal() as s:
        await s.execute(delete(Message).where(Message.user_key == user_key))
        await s.execute(delete(Summary).where(Summary.user_key == user_key))
        await s.commit()

async def add_memories(user_key: str, facts: list[str]) -> list[int]:
    """Returns the new rows' ids so they can be fed to the hybrid index."""
    rows = [Memory(user_key=user_key, content=f) for f in facts]
    async with SessionLocal() as s:
        s.add_all(rows)
        await s.commit()          # expire_on_commit=False, so .id survives
    return [r.id for r in rows]

async def replace_memories(user_key: str, old_ids: list[int], facts: list[str]) -> list[int]:
    """Swap a set of memories for a rewritten set, in one transaction.

    Consolidation rewrites the store, and doing that as add-then-delete across
    two commits has one unacceptable ordering: a crash between them, with the
    delete already committed, loses memory permanently. One transaction removes
    the question. Returns the new rows' ids for the index sync.
    """
    rows = [Memory(user_key=user_key, content=f) for f in facts]
    async with SessionLocal() as s:
        s.add_all(rows)
        await s.flush()               # ids assigned, nothing committed yet
        if old_ids:
            await s.execute(delete(Memory).where(Memory.user_key == user_key,
                                                 Memory.id.in_(old_ids)))
        await s.commit()
    return [r.id for r in rows]

async def all_memories(user_key: str, limit: int = 500) -> list[tuple[int, str]]:
    """(id, content) pairs, newest first."""
    async with SessionLocal() as s:
        rows = (await s.execute(select(Memory).where(Memory.user_key == user_key)
                                .order_by(Memory.id.desc()).limit(limit))).scalars().all()
    return [(r.id, r.content) for r in rows]

async def search_messages(user_key: str, terms: list[str], limit: int = 200) -> list[dict]:
    """Messages containing any term (case-insensitive), newest first."""
    if not terms: return []
    cond = or_(*(Message.content.ilike(f"%{t}%") for t in terms))
    async with SessionLocal() as s:
        rows = (await s.execute(select(Message)
                                .where(Message.user_key == user_key, Message.role != "tool", cond)
                                .order_by(Message.id.desc()).limit(limit))).scalars().all()
    return [{"when": r.created_at.isoformat(timespec="minutes"), "role": r.role,
             "text": r.content} for r in rows]

async def upsert_person(user_key: str, name: str, note: str) -> str:
    """Add a person or append a fact to one. Returns "added" or "updated"; an
    identical note is not duplicated."""
    key = name.strip().lower()
    async with SessionLocal() as s:
        row = await s.get(Person, (user_key, key))
        if row is None:
            s.add(Person(user_key=user_key, name_key=key, name=name.strip(), notes=note.strip()))
            await s.commit(); return "added"
        lines = [ln for ln in row.notes.splitlines() if ln.strip()]
        if note.strip() and note.strip() not in lines:
            lines.append(note.strip())
            row.notes = "\n".join(lines)
            await s.commit()
        return "updated"

async def get_person(user_key: str, name: str) -> Person | None:
    async with SessionLocal() as s:
        return await s.get(Person, (user_key, name.strip().lower()))

async def list_people(user_key: str) -> list[Person]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Person).where(Person.user_key == user_key)
                                     .order_by(Person.name))).scalars().all())

async def forget_person(user_key: str, name: str) -> bool:
    async with SessionLocal() as s:
        row = await s.get(Person, (user_key, name.strip().lower()))
        if row is None: return False
        await s.delete(row); await s.commit(); return True

async def add_job(user_key: str, text: str, due_at: _dt.datetime,
                  recur_minutes: int | None = None, kind: str = "reminder") -> int:
    async with SessionLocal() as s:
        job = Job(user_key=user_key, kind=kind, text=text, due_at=due_at,
                  recur_minutes=recur_minutes)
        s.add(job); await s.commit(); return job.id

async def due_jobs(now: _dt.datetime) -> list[Job]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Job).where(Job.done == False, Job.due_at <= now)  # noqa: E712
                                     .order_by(Job.due_at))).scalars().all())

async def complete_job(job_id: int, next_due: _dt.datetime | None = None) -> None:
    """Mark done, or roll a recurring job forward to next_due."""
    async with SessionLocal() as s:
        job = await s.get(Job, job_id)
        if job is None: return
        if next_due is not None: job.due_at = next_due
        else: job.done = True
        await s.commit()

async def pending_jobs(user_key: str) -> list[Job]:
    async with SessionLocal() as s:
        return list((await s.execute(select(Job).where(Job.user_key == user_key,
                                     Job.done == False)  # noqa: E712
                                     .order_by(Job.due_at))).scalars().all())

async def cancel_job(user_key: str, job_id: int) -> bool:
    async with SessionLocal() as s:
        job = await s.get(Job, job_id)
        if job is None or job.user_key != user_key or job.done: return False
        job.done = True; await s.commit(); return True

async def approve_tool(user_key: str, tool_name: str) -> None:
    async with SessionLocal() as s:
        if await s.get(ToolApproval, (user_key, tool_name)) is None:
            s.add(ToolApproval(user_key=user_key, tool_name=tool_name))
            await s.commit()

async def is_tool_approved(user_key: str, tool_name: str) -> bool:
    async with SessionLocal() as s:
        return await s.get(ToolApproval, (user_key, tool_name)) is not None

async def get_summary(user_key: str) -> str | None:
    async with SessionLocal() as s:
        row = await s.get(Summary, user_key)
        return row.content if row else None

async def save_summary(user_key: str, content: str) -> None:
    async with SessionLocal() as s:
        row = await s.get(Summary, user_key)
        if row: row.content = content
        else: s.add(Summary(user_key=user_key, content=content))
        await s.commit()