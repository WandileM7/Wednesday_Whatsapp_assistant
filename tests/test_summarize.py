"""Rolling summary: it folds dropped messages into a running summary, but must
also trim the in-RAM history tail EVEN WHEN the model call fails — otherwise a
slow/failing summariser lets the cache grow without bound."""
import json

import httpx
import pytest

from backend import agent, db


def _long(role, i):
    # long enough that a handful of these overflow the token slice
    return {"role": role, "content": f"{role} {i}: " + "pad " * 120}


def _conversation(n_pairs=20):
    convo = []
    for i in range(n_pairs):
        convo.append(_long("user", i)); convo.append(_long("assistant", i))
    return convo


@pytest.fixture(autouse=True)
def _reset_transport():
    yield
    agent._transport = None


async def test_success_updates_summary_and_trims(monkeypatch):
    await db.init()
    user = "sum-ok"
    def handler(_req):
        return httpx.Response(200, content=json.dumps(
            {"message": {"content": "They are planning an October trip to Cape Town."}}).encode())
    agent._transport = httpx.MockTransport(handler)

    convo = _conversation()
    agent._HISTORIES[user] = convo; agent._SUMMARIES[user] = ""
    dropped = len(convo) - len(agent._slice(convo))
    assert dropped >= agent._SUMMARIZE_BATCH          # precondition: enough fell off

    await agent._summarize(user)

    assert "Cape Town" in agent._SUMMARIES[user]
    assert await db.get_summary(user) == agent._SUMMARIES[user]
    assert len(agent._HISTORIES[user]) == len(convo) - dropped


async def test_failure_still_trims_and_saves_no_garbage(monkeypatch):
    await db.init()
    user = "sum-fail"
    def boom(request):
        raise httpx.ReadTimeout("simulated slow summary", request=request)
    agent._transport = httpx.MockTransport(boom)

    convo = _conversation()
    agent._HISTORIES[user] = convo; agent._SUMMARIES[user] = ""
    dropped = len(convo) - len(agent._slice(convo))

    await agent._summarize(user)                       # must not raise

    # cache trimmed despite the failure — memory can't grow unbounded
    assert len(agent._HISTORIES[user]) == len(convo) - dropped
    # no half-baked summary persisted
    assert not agent._SUMMARIES[user]
    assert await db.get_summary(user) is None


async def test_noop_below_threshold(monkeypatch):
    await db.init()
    user = "sum-small"
    called = False
    def handler(_req):
        nonlocal called; called = True
        return httpx.Response(200, content=b'{"message":{"content":"x"}}')
    agent._transport = httpx.MockTransport(handler)

    convo = _conversation(1)                            # nothing drops off
    agent._HISTORIES[user] = convo; agent._SUMMARIES[user] = ""
    await agent._summarize(user)

    assert not called                                  # no model call burned
    assert len(agent._HISTORIES[user]) == len(convo)   # untouched
