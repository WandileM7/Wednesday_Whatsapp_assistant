from backend import db, memory
from backend.memory import _norm, _parse_facts, _terms


def test_terms_drops_stopwords_and_short_words():
    assert _terms("What is the codeword for our Project X?") == {"codeword", "project"}


def test_parse_facts_accepts_object_array_and_garbage():
    assert _parse_facts('{"facts": ["User likes tea", " ", 42]}') == ["User likes tea"]
    assert _parse_facts('["a fact here"]') == ["a fact here"]
    assert _parse_facts("not json at all") == []
    assert _parse_facts('{"facts": "not a list"}') == []


def test_norm_deduplicates_variants():
    assert _norm("User's dog is called Rex!") == _norm("users dog is called rex")


async def test_relevant_ranks_overlap_then_recency():
    await db.init()
    await db.add_memories("m1", [
        "User works at MTN as an engineer",
        "User's dog is called Rex",
        "The project codeword is falcon",
    ])
    top = await memory.relevant("m1", "what was the codeword again?", k=2)
    assert top[0] == "The project codeword is falcon"
    assert len(top) == 2  # padded with the freshest non-matching memory

    # no overlap at all: still returns the newest facts rather than nothing
    fallback = await memory.relevant("m1", "zzz qqq", k=2)
    assert fallback == ["The project codeword is falcon", "User's dog is called Rex"]


async def test_search_messages_scopes_to_user_and_ranks():
    await db.init()
    await db.clear_messages("m2")
    await db.add_messages("m2", [
        {"role": "user", "content": "let's discuss the visa application for Portugal"},
        {"role": "assistant", "content": "Portugal visa needs form D7"},
        {"role": "user", "content": "unrelated grocery list"},
    ])
    await db.add_messages("m3", [{"role": "user", "content": "visa visa visa"}])
    hits = await memory.search_messages("m2", "portugal visa", limit=2)
    assert len(hits) == 2
    assert all("visa" in h["text"].lower() for h in hits)

    nothing = await memory.search_messages("m2", "spaceship")
    assert nothing == [{"note": "nothing found in past conversations"}]
    await db.clear_messages("m2"); await db.clear_messages("m3")


async def test_search_conversations_tool_uses_context_user():
    from backend.tools import CURRENT_USER, REGISTRY
    await db.init()
    await db.clear_messages("m4")
    await db.add_messages("m4", [{"role": "user", "content": "the wifi password is hunter2"}])
    CURRENT_USER.set("m4")
    result = await REGISTRY["search_conversations"]["fn"](query="wifi password")
    assert "hunter2" in str(result)
    CURRENT_USER.set("")
    assert await REGISTRY["search_conversations"]["fn"](query="x") == "No active user context."
    await db.clear_messages("m4")
