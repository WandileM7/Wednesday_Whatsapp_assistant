"""Scheduled daily briefing: opt-in job creation and the scheduler dispatch.

The briefing must never appear on its own — it's created only when the user
asks (unlike the curator, which is seeded at boot, and unlike the heartbeat,
which stays off by standing decision).
"""
import datetime as _dt

import pytest

from backend import db, scheduler
from backend.config import settings
from backend.tools import CURRENT_USER, REGISTRY


@pytest.fixture(autouse=True)
async def _clean():
    await db.init()
    for u in ("b1",):
        for j in await db.pending_jobs(u):
            await db.cancel_job(u, j.id)
    CURRENT_USER.set("b1")
    yield
    CURRENT_USER.set("")


async def _call(tool, **kw):
    return await REGISTRY[tool]["fn"](**kw)


async def test_set_creates_a_daily_recurring_job():
    out = await _call("set_daily_briefing", time="07:30")
    assert out["repeats"] == "daily"
    jobs = [j for j in await db.pending_jobs("b1") if j.kind == "briefing"]
    assert len(jobs) == 1
    assert jobs[0].recur_minutes == 24 * 60
    assert jobs[0].due_at.hour == 7 and jobs[0].due_at.minute == 30


async def test_first_run_is_in_the_future():
    out = await _call("set_daily_briefing", time="07:30")
    assert _dt.datetime.fromisoformat(out["first"]) > _dt.datetime.now()


async def test_setting_twice_replaces_rather_than_duplicates():
    await _call("set_daily_briefing", time="07:30")
    await _call("set_daily_briefing", time="08:15")
    jobs = [j for j in await db.pending_jobs("b1") if j.kind == "briefing"]
    assert len(jobs) == 1 and jobs[0].due_at.hour == 8


async def test_bad_time_is_rejected():
    out = await _call("set_daily_briefing", time="half past seven")
    assert "Couldn't read" in out
    assert not [j for j in await db.pending_jobs("b1") if j.kind == "briefing"]


async def test_cancel():
    await _call("set_daily_briefing", time="07:30")
    assert await _call("cancel_daily_briefing") == "Daily briefing off."
    assert not [j for j in await db.pending_jobs("b1") if j.kind == "briefing"]
    assert await _call("cancel_daily_briefing") == "There wasn't one set."


async def test_briefing_is_not_listed_as_a_reminder():
    await _call("set_daily_briefing", time="07:30")
    assert await _call("list_reminders") == "No pending reminders."
    await _call("set_reminder", text="drink water", in_minutes=30)
    listed = await _call("list_reminders")
    assert [r["text"] for r in listed] == ["drink water"]


async def test_scheduler_runs_the_agent_and_delivers(monkeypatch):
    """A due briefing job triggers an agent turn and pushes the reply."""
    sent = []

    async def fake_reply(channel, user_text):
        assert "daily briefing" in user_text.lower()
        return "[calm] Three meetings, then silence."

    async def fake_deliver(user, text):
        sent.append((user, text)); return True

    monkeypatch.setattr("backend.agent.reply", fake_reply)
    monkeypatch.setattr(scheduler, "deliver", fake_deliver)

    due = _dt.datetime.now() - _dt.timedelta(minutes=1)
    await db.add_job("b1", "daily briefing", due, 24 * 60, kind="briefing")
    await scheduler.tick()

    assert len(sent) == 1
    user, text = sent[0]
    assert user == "b1"
    assert text == "Three meetings, then silence."  # speech marker stripped


async def test_due_briefing_rolls_forward_a_day(monkeypatch):
    async def fake_reply(*a, **k): return "brief"
    async def fake_deliver(*a, **k): return True
    monkeypatch.setattr("backend.agent.reply", fake_reply)
    monkeypatch.setattr(scheduler, "deliver", fake_deliver)

    due = _dt.datetime.now() - _dt.timedelta(minutes=1)
    job_id = await db.add_job("b1", "daily briefing", due, 24 * 60, kind="briefing")
    await scheduler.tick()
    jobs = {j.id: j for j in await db.pending_jobs("b1")}
    assert jobs[job_id].due_at > _dt.datetime.now()


async def test_nothing_creates_a_briefing_on_boot():
    # ensure_curator seeds the curator job; it must not seed a briefing
    await scheduler.ensure_curator()
    kinds = {j.kind for j in await db.pending_jobs(settings.default_user)}
    assert "briefing" not in kinds
