"""Proactivity: due-job delivery loop and the opt-in heartbeat.

Jobs live in sqlite (db.Job) so they survive restarts. Delivery prefers an
open browser tab, then the user's WhatsApp. The heartbeat is a silent agent
turn that only reaches the user when the model decides something warrants it,
inside quiet-hours and daily-cap guardrails.
"""
from __future__ import annotations
import asyncio, datetime as _dt, logging

from . import db, live
from .config import settings

log = logging.getLogger(__name__)
_TICK_SECONDS = 15
_NOTHING = "NOTHING"
_pings_today: tuple[_dt.date, int] = (_dt.date.min, 0)

_HEARTBEAT_PROMPT = (
    "Silent periodic check-in — the user did not send a message. Using your "
    "tools, check for anything urgent: unread important email, calendar events "
    "in the next two hours, overdue tasks. If something genuinely needs the "
    f"user's attention right now, say so briefly. Otherwise reply exactly {_NOTHING}."
)


def in_quiet_hours(now: _dt.datetime, quiet: str | None = None) -> bool:
    quiet = quiet or settings.heartbeat_quiet
    try:
        start, end = (int(x) for x in quiet.split("-"))
    except ValueError:
        return False
    return start <= now.hour or now.hour < end if start > end else start <= now.hour < end


def _wa_target(user: str) -> str | None:
    if user.startswith("wa:"): return user[3:]
    if user == settings.default_user and settings.whatsapp_owner_jid:
        return settings.whatsapp_owner_jid
    return None


async def deliver(user: str, text: str) -> bool:
    """Open tab first, WhatsApp second. True if the user got it somewhere."""
    delivered = await live.push(user, text)
    target = _wa_target(user)
    if target and settings.whatsapp_enabled:
        from . import whatsapp
        await whatsapp._send(target, text)
        delivered = True
    if not delivered:
        log.warning("no channel to deliver to %s: %s", user, text)
    return delivered


async def tick(now: _dt.datetime | None = None) -> list[int]:
    """Deliver every due job; returns the delivered job ids."""
    now = now or _dt.datetime.now()
    delivered = []
    for job in await db.due_jobs(now):
        if job.kind == "curator":
            from . import skills
            report = skills.curator_report()
            ok = await deliver(job.user_key, report) if report else True
        elif job.kind == "hygiene":
            # Silent by design: a daily "I found nothing" message is noise, and
            # what it does find is already in the log stream and the HUD.
            from . import hygiene
            found = await hygiene.sweep_all()
            total = sum(len(v) for v in found.values())
            if total: log.info("hygiene: dropped %d poisoned message(s)", total)
            ok = True
        else:
            ok = await deliver(job.user_key, f"⏰ Reminder: {job.text}")
        next_due = (job.due_at + _dt.timedelta(minutes=job.recur_minutes)
                    if job.recur_minutes else None)
        # An undeliverable one-shot stays pending and retries next tick
        if ok or next_due: await db.complete_job(job.id, next_due)
        if ok: delivered.append(job.id)
    return delivered


async def ensure_curator() -> None:
    """One weekly curator job for the owner; created on first boot."""
    if any(j.kind == "curator" for j in await db.pending_jobs(settings.default_user)):
        return
    now = _dt.datetime.now()
    days_ahead = (6 - now.weekday()) % 7 or 7  # next Sunday
    due = (now + _dt.timedelta(days=days_ahead)).replace(hour=10, minute=0, second=0, microsecond=0)
    await db.add_job(settings.default_user, "weekly skill report", due,
                     recur_minutes=7 * 24 * 60, kind="curator")


async def ensure_hygiene() -> None:
    """One daily history sweep; created on first boot.

    Daily rather than weekly because a poisoned message is contagious — it
    becomes the pattern the next reply copies, so a week of it is a week of
    compounding, not a week of one bad line.
    """
    if any(j.kind == "hygiene" for j in await db.pending_jobs(settings.default_user)):
        return
    now = _dt.datetime.now()
    due = (now + _dt.timedelta(days=1)).replace(hour=4, minute=30, second=0, microsecond=0)
    await db.add_job(settings.default_user, "daily history sweep", due,
                     recur_minutes=24 * 60, kind="hygiene")


async def _heartbeat() -> None:
    global _pings_today
    now = _dt.datetime.now()
    if in_quiet_hours(now): return
    day, count = _pings_today
    if day == now.date() and count >= settings.heartbeat_daily_cap: return
    from . import agent, markers
    text = markers.strip(await agent.reply(settings.default_user, _HEARTBEAT_PROMPT)).strip()
    if not text or _NOTHING in text.upper()[:20]: return
    if await deliver(settings.default_user, text):
        _pings_today = (now.date(), count + 1 if day == now.date() else 1)


async def run() -> None:
    """Forever-loop started at app startup."""
    await ensure_curator()
    await ensure_hygiene()
    last_beat = _dt.datetime.now()
    log.info("scheduler running (heartbeat: %s)",
             f"every {settings.heartbeat_minutes}m" if settings.heartbeat_minutes else "off")
    while True:
        try:
            await tick()
            if settings.heartbeat_minutes and (
                    _dt.datetime.now() - last_beat).total_seconds() >= settings.heartbeat_minutes * 60:
                last_beat = _dt.datetime.now()
                await _heartbeat()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(_TICK_SECONDS)
