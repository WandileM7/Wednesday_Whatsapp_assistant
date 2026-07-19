import datetime as dt

import pytest

from backend import db, scheduler
from backend.scheduler import in_quiet_hours
from backend.tools import CURRENT_USER, REGISTRY


def _at(hour): return dt.datetime(2026, 7, 19, hour, 30)


def test_quiet_hours_wrap_midnight():
    assert in_quiet_hours(_at(23), "22-07")
    assert in_quiet_hours(_at(3), "22-07")
    assert not in_quiet_hours(_at(12), "22-07")
    assert in_quiet_hours(_at(13), "12-14")
    assert not in_quiet_hours(_at(11), "12-14")
    assert not in_quiet_hours(_at(5), "garbage")  # unparseable = never quiet


async def test_due_jobs_and_completion():
    await db.init()
    now = dt.datetime.now()
    early = await db.add_job("s1", "past", now - dt.timedelta(minutes=5))
    await db.add_job("s1", "future", now + dt.timedelta(hours=1))
    due = [j.id for j in await db.due_jobs(now) if j.user_key == "s1"]
    assert due == [early]
    await db.complete_job(early)
    assert [j for j in await db.due_jobs(now) if j.user_key == "s1"] == []
    assert [j.text for j in await db.pending_jobs("s1")] == ["future"]


async def test_recurring_job_rolls_forward():
    await db.init()
    now = dt.datetime.now()
    jid = await db.add_job("s2", "standup", now - dt.timedelta(minutes=1), recur_minutes=60)
    await db.complete_job(jid, next_due=now + dt.timedelta(minutes=59))
    jobs = await db.pending_jobs("s2")
    assert len(jobs) == 1 and jobs[0].due_at > now
    await db.cancel_job("s2", jid)


async def test_tick_delivers_and_reschedules(monkeypatch):
    await db.init()
    sent = []

    async def fake_deliver(user, text): sent.append((user, text)); return True
    monkeypatch.setattr(scheduler, "deliver", fake_deliver)

    now = dt.datetime.now()
    once = await db.add_job("s3", "one-shot", now - dt.timedelta(minutes=1))
    recur = await db.add_job("s3", "hourly", now - dt.timedelta(minutes=1), recur_minutes=60)
    delivered = await scheduler.tick(now)
    assert sorted(delivered) == sorted([once, recur])
    assert any("one-shot" in t for _, t in sent)
    pending = await db.pending_jobs("s3")  # recurring survives, one-shot done
    assert [j.text for j in pending] == ["hourly"]
    await db.cancel_job("s3", recur)


async def test_undeliverable_oneshot_stays_pending(monkeypatch):
    await db.init()

    async def fake_deliver(user, text): return False
    monkeypatch.setattr(scheduler, "deliver", fake_deliver)

    now = dt.datetime.now()
    jid = await db.add_job("s4", "stuck", now - dt.timedelta(minutes=1))
    assert await scheduler.tick(now) == []
    assert [j.id for j in await db.pending_jobs("s4")] == [jid]
    await db.cancel_job("s4", jid)


async def test_reminder_tools_round_trip():
    await db.init()
    CURRENT_USER.set("s5")
    made = await REGISTRY["set_reminder"]["fn"](text="tea", in_minutes=30)
    assert made["repeats"] == "once"
    listed = await REGISTRY["list_reminders"]["fn"]()
    assert any(r["text"] == "tea" for r in listed)
    assert await REGISTRY["cancel_reminder"]["fn"](id=made["id"]) == "Cancelled."
    assert await REGISTRY["list_reminders"]["fn"]() == "No pending reminders."

    past = await REGISTRY["set_reminder"]["fn"](text="x", when_iso="2020-01-01T09:00")
    assert "past" in past
    bad = await REGISTRY["set_reminder"]["fn"](text="x", when_iso="not-a-date")
    assert "Could not parse" in bad
    assert await REGISTRY["set_reminder"]["fn"](text="x") == "Give when_iso or in_minutes."
    CURRENT_USER.set("")
