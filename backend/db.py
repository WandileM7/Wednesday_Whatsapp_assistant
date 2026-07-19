from __future__ import annotations
import datetime as _dt
import json
from typing import AsyncIterator
from sqlalchemy import DateTime, String, Text, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .config import settings

class Base(DeclarativeBase): pass

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

class Summary(Base):
    __tablename__ = "summaries"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[_dt.datetime] = mapped_column(DateTime, default=_dt.datetime.utcnow,
                                                     onupdate=_dt.datetime.utcnow)

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_token(service, access_token, refresh_token, expires_at, scope=None):
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
        return await s.get(OAuthToken, service)

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

async def clear_messages(user_key: str) -> None:
    async with SessionLocal() as s:
        await s.execute(delete(Message).where(Message.user_key == user_key))
        await s.execute(delete(Summary).where(Summary.user_key == user_key))
        await s.commit()

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