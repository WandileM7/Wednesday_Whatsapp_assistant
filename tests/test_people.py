"""Structured people memory: upsert/append, case-insensitive and first-name
recall, per-user scoping, forget."""
import pytest

from backend import db
from backend.tools import CURRENT_USER, REGISTRY


@pytest.fixture(autouse=True)
async def _clean_user():
    await db.init()
    for u in ("p1", "p2"):
        for p in await db.list_people(u):
            await db.forget_person(u, p.name)
    CURRENT_USER.set("p1")
    yield
    CURRENT_USER.set("")


async def _call(tool, **kw):
    return await REGISTRY[tool]["fn"](**kw)


async def test_remember_then_recall():
    assert "Added" in await _call("remember_person", name="Thabo Nkosi",
                                  note="colleague at MTN")
    out = await _call("recall_person", name="Thabo Nkosi")
    assert out["name"] == "Thabo Nkosi"
    assert out["notes"] == ["colleague at MTN"]


async def test_facts_accumulate_without_duplicates():
    await _call("remember_person", name="Thabo", note="colleague at MTN")
    await _call("remember_person", name="Thabo", note="allergic to peanuts")
    await _call("remember_person", name="Thabo", note="colleague at MTN")  # repeat
    out = await _call("recall_person", name="Thabo")
    assert out["notes"] == ["colleague at MTN", "allergic to peanuts"]


async def test_recall_is_case_insensitive():
    await _call("remember_person", name="Thabo", note="colleague")
    assert (await _call("recall_person", name="THABO"))["name"] == "Thabo"


async def test_recall_by_first_name_when_unambiguous():
    await _call("remember_person", name="Thabo Nkosi", note="colleague")
    out = await _call("recall_person", name="Thabo")
    assert out["name"] == "Thabo Nkosi"


async def test_ambiguous_partial_does_not_guess():
    await _call("remember_person", name="Thabo Nkosi", note="colleague")
    await _call("remember_person", name="Thabo Dlamini", note="neighbour")
    out = await _call("recall_person", name="Thabo")
    assert isinstance(out, str) and "Nothing recorded" in out


async def test_unknown_person():
    out = await _call("recall_person", name="Nobody")
    assert isinstance(out, str) and "Nothing recorded about Nobody" in out


async def test_people_are_scoped_per_user():
    await _call("remember_person", name="Thabo", note="colleague")
    CURRENT_USER.set("p2")
    assert isinstance(await _call("recall_person", name="Thabo"), str)
    assert await _call("list_people") == "No people recorded yet."
    CURRENT_USER.set("p1")
    assert (await _call("list_people"))[0]["name"] == "Thabo"


async def test_list_counts_notes():
    await _call("remember_person", name="Thabo", note="a")
    await _call("remember_person", name="Thabo", note="b")
    assert await _call("list_people") == [{"name": "Thabo", "notes": 2}]


async def test_forget_removes_the_person():
    await _call("remember_person", name="Thabo", note="colleague")
    assert "Forgot" in await _call("forget_person", name="Thabo")
    assert isinstance(await _call("recall_person", name="Thabo"), str)
    assert "Nothing recorded" in await _call("forget_person", name="Thabo")


async def test_requires_user_context():
    CURRENT_USER.set("")
    assert await _call("recall_person", name="x") == "No active user context."
    assert await _call("remember_person", name="x", note="y") == "No active user context."


async def test_blank_input_rejected():
    assert "Need both" in await _call("remember_person", name="  ", note="x")
