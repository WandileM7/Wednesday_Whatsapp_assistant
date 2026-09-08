from backend import db, memory
from backend.memory import _norm, _parse_facts, _terms


def test_terms_drops_stopwords_and_short_words():
    assert _terms("What is the codeword for our Project X?") == {"codeword", "project"}


def test_parse_facts_accepts_object_array_and_garbage():
    assert _parse_facts('{"facts": ["User likes tea", " ", 42]}') == ["User likes tea"]
    assert _parse_facts('["a fact here"]') == ["a fact here"]
    assert _parse_facts("not json at all") == []


def test_parse_facts_recovers_the_shapes_a_small_model_actually_returns():
    """format:json buys valid JSON, not correct JSON. Each of these used to
    parse to nothing and lose the whole extraction without a word in the log.

    Being generous here is safe because it is not the trust boundary: both
    callers put every candidate through _grounded, so the worst a wrong guess
    can do is offer up a string that then gets rejected.
    """
    # A lone fact, not wrapped in a list.
    assert _parse_facts('{"facts": "Allergic to shellfish"}') == ["Allergic to shellfish"]
    # The list under a synonym the prompt never asked for.
    assert _parse_facts('{"memories": ["Drinks rooibos"]}') == ["Drinks rooibos"]
    # Elements wrapped one per object.
    assert _parse_facts('{"facts": [{"fact": "Has a dog called Rex"}]}') == \
        ["Has a dog called Rex"]
    # A list that came back keyed.
    assert _parse_facts('{"facts": {"0": "Works at MTN", "1": "Lives in Cape Town"}}') == \
        ["Works at MTN", "Lives in Cape Town"]
    # A single unrecognised key holding the payload.
    assert _parse_facts('{"output": ["Prefers tea"]}') == ["Prefers tea"]


def test_parse_facts_does_not_raid_a_structured_reply_for_any_list_it_finds():
    """One unknown key is a rename; several fields is a different reply shape,
    and guessing which one holds the facts is how commentary becomes memory."""
    assert _parse_facts('{"reasoning": ["step one"], "confidence": "high"}') == []
    assert _parse_facts('{"facts": 42}') == []
    assert _parse_facts("[]") == []


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


# ---- grounding guard --------------------------------------------------------
# llama3.2:1b, asked to extract from "What reminders do I have?", returned
# "Enjoys hiking on weekends", "Has a pet dog" and "Lives in New York City".
# Fabrications are the one error a memory store must never accept, since they
# persist into every later prompt. These tests need no model.

_SRC = "I'm allergic to shellfish, by the way. And I prefer tea to coffee."


def test_paraphrase_of_what_the_user_said_is_grounded():
    assert memory._grounded("Allergic to shellfish", _SRC)
    assert memory._grounded("Prefers tea to coffee", _SRC)


def test_stemming_lets_inflections_match():
    assert memory._grounded("Prefers tea", "I prefer tea")


def test_invented_facts_are_rejected():
    for fabricated in ("Not a fan of spicy food", "Lives in New York City",
                       "Has a pet dog", "Enjoys hiking on weekends",
                       "Is 30 years old"):
        assert not memory._grounded(fabricated, _SRC), fabricated


def test_an_empty_or_stopword_only_fact_is_not_grounded():
    assert not memory._grounded("", _SRC)
    assert not memory._grounded("the and of", _SRC)


def test_partially_supported_facts_are_rejected():
    """Half-invented is still invented: shellfish is real, Thailand isn't."""
    assert not memory._grounded("Ate shellfish in Thailand last summer", _SRC)

async def test_relevant_prefers_rare_term_over_recency():
    # A rare, discriminating term must outrank a common one even when the
    # common-term match is newer — the whole point of BM25 idf over plain
    # overlap-count (which would tie at 1 and let recency win the wrong doc).
    await db.init()
    await db.add_memories("bm25", [
        "The vault code is 4471",     # oldest; 'vault' is rare (df 1)
        "User enjoys hiking",         # 'hiking' is common in this set (df 3)
        "User enjoys hiking trails",
        "User enjoys hiking daily",   # newest common-term match
    ])
    top = await memory.relevant("bm25", "hiking vault", k=1)
    assert top[0] == "The vault code is 4471"


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


async def test_search_messages_ties_resolve_newest_first():
    # equal score + equal length ⇒ a true tie; it must resolve to the newer
    # message (guards the id-polarity of the BM25 tiebreak).
    await db.init()
    await db.clear_messages("mtie")
    await db.add_messages("mtie", [
        {"role": "user", "content": "alpha beta"},    # older
        {"role": "user", "content": "alpha gamma"},   # newer
    ])
    hits = await memory.search_messages("mtie", "alpha", limit=2)
    assert hits[0]["text"] == "alpha gamma"
    await db.clear_messages("mtie")


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
