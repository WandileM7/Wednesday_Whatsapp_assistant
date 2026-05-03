from __future__ import annotations
import datetime as _dt
from typing import AsyncIterator
from sqlalchemy import DateTime, String, Text, select
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