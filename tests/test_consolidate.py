"""Memory consolidation: code finds candidate pairs, the model judges one pair.

memory.py's block comment records the two whole-store designs this replaced and
why both were abandoned. What these tests pin is the property neither could
offer: a fact with no near neighbour is never shown to the model, so it cannot
be deleted, and one bad verdict costs one fact.
"""
import json

import httpx
import pytest

from backend import db, memory


def _fake_utility(verdicts):
    """Ollama /api/chat answering each adjudication in turn.

    `verdicts` is a list consumed in order, or a single string used for every
    call. Records the prompts so a test can assert what the model was shown.
    """
    seen = {"prompts": []}
    queue = list(verdicts) if isinstance(verdicts, (list, tuple)) else None

    def handler(request: httpx.Request) -> httpx.Response:
        seen["prompts"].append(json.loads(request.content)["messages"][0]["content"])
        verdict = queue.pop(0) if queue else verdicts
        body = verdict if isinstance(verdict, str) and verdict.startswith("{") \
            else json.dumps({"verdict": verdict})
        return httpx.Response(200, json={"message": {"content": body}})

    return httpx.MockTransport(handler), seen


def _word(i):
    """A nonsense word whose first five characters are unique to `i`."""
    return f"{chr(97 + i // 26)}{chr(97 + i % 26)}zulon"


def _filler(n):
    """n facts sharing no content word at all, so never candidates.

    No common prefix, deliberately. An earlier version of this fixture wrote
    them as "Remembers <word>", and that one shared word made every filler pair
    score 0.5 — which is how _MIN_SHARED_STEMS got added.
    """
    return [f"{_word(2 * i)} and {_word(2 * i + 1)}" for i in range(n)]


async def _seed(user, facts):
    await db.init()
    rows = await db.all_memories(user)
    if rows:
        await db.replace_memories(user, [mid for mid, _ in rows], [])
    await db.add_memories(user, facts)


# --- candidate selection (no model involved) -------------------------------

def test_lexical_overlap_scores_over_the_smaller_fact():
    """A short fact restated at length is still a duplicate. Over the union this
    pair scores 0.4 and falls below the threshold; over the smaller, 0.67."""
    assert memory._lexical("Prefers tea to coffee",
                           "Drinks tea rather than coffee") >= memory._LEXICAL_MIN
    assert memory._lexical("Has a dog called Rex",
                           "Studied electrical engineering at Wits") == 0.0


def test_unrelated_facts_are_never_offered_to_the_model():
    """The whole point of the redesign. Nothing without a near neighbour is a
    candidate, so nothing without one can be deleted."""
    rows = list(enumerate(_filler(30), start=1))
    assert memory._candidates([(i, t) for i, t in rows], {}) == []


def test_a_duplicate_pair_is_found_without_embeddings():
    rows = [(1, "Prefers tea to coffee"), (2, "Has a dog called Rex"),
            (3, "Drinks tea rather than coffee")]
    pairs = memory._candidates(rows, {})
    assert [(o, n) for _, o, n in pairs] == [(0, 2)], "the tea pair, oldest first"


def test_supersession_is_found_without_embeddings():
    """"Lives in Cape Town" and "Moved to Johannesburg in March" share no content
    word, so lexical scores 0.0 — and with ENABLE_MEMORY_EMBEDDINGS off there is
    no cosine either. The shared *predicate* is the whole signal: a person has
    one home, so two facts asserting where they live are worth a question however
    differently they are worded."""
    rows = [(1, "Lives in Cape Town"), (2, "Moved to Johannesburg in March")]
    assert memory._lexical(rows[0][1], rows[1][1]) == 0.0
    assert [(o, n) for _, o, n in memory._candidates(rows, {})] == [(0, 1)]


def test_the_topic_detector_covers_the_attributes_that_actually_change():
    """Each of these is a thing a person has exactly one of, so a second fact
    asserting it is either a restatement or a replacement."""
    for older, newer in [
        ("Lives in Cape Town", "Moved to Johannesburg in March"),
        ("Works at MTN as an engineer", "Joined Vodacom in June"),
        ("Married to Lerato", "Divorced last year"),
        ("Drives a silver Polo", "Sold the car in April"),
        ("Studies electrical engineering", "Graduated in November"),
    ]:
        assert memory._topics(older) & memory._topics(newer), (older, newer)


def test_unrelated_facts_share_no_topic():
    assert not memory._topics("Allergic to shellfish") & memory._topics("Supports Orlando Pirates")


def test_someone_elses_attribute_is_not_the_users():
    """The predicate alone cannot tell whose home it is. Left unchecked, this
    pass paired "Lives in Cape Town" with "Sister is called Naledi and lives in
    Durban", decided Johannesburg replaced Durban, and deleted the sister."""
    assert memory._topics("Lives in Cape Town") == {"home"}
    assert memory._topics("Sister is called Naledi and lives in Durban") == set()
    assert memory._topics("Manager at work is called Thabo") == set()
    assert memory._topics("Landlord is called Mrs Pillay") == set()


def test_the_users_own_partner_still_counts_as_their_attribute():
    """wife/husband/partner name the user's own status, so they must not be
    filtered out as third-party mentions the way sister/manager are."""
    assert "partner" in memory._topics("Married to Lerato")
    assert "partner" in memory._topics("Wife is called Lerato")


def test_cosine_still_qualifies_a_pair_with_no_shared_topic_or_wording():
    rows = [(1, "azzulon and bazulon"), (2, "bbzulon and bczulon")]
    assert memory._candidates(rows, {}) == []
    # Near-identical vectors stand in for "about the same subject".
    vecs = {1: [1.0, 0.0, 0.1], 2: [0.99, 0.05, 0.1]}
    assert [(o, n) for _, o, n in memory._candidates(rows, vecs)] == [(0, 1)]


def test_no_fact_is_adjudicated_twice_in_one_pass():
    """Deleting a row on one verdict and then comparing it on the next would be
    judging a ghost."""
    rows = [(1, "Prefers tea to coffee"), (2, "Drinks tea rather than coffee"),
            (3, "Enjoys tea over coffee")]
    pairs = memory._candidates(rows, {})
    touched = [i for _, o, n in pairs for i in (o, n)]
    assert len(touched) == len(set(touched))


def test_pairs_per_pass_are_capped():
    rows = [(i, f"Prefers tea to coffee variant {i}") for i in range(1, 30)]
    assert len(memory._candidates(rows, {})) <= memory._MAX_PAIRS_PER_PASS


# --- adjudication ----------------------------------------------------------

async def test_below_the_threshold_it_does_not_call_the_model_at_all():
    await _seed("c1", _filler(5))
    transport, seen = _fake_utility("same")
    assert await memory.consolidate("c1", transport=transport) == 0
    assert seen["prompts"] == []


async def test_a_store_with_no_candidates_never_calls_the_model():
    await _seed("c2", _filler(32))
    transport, seen = _fake_utility("same")
    assert await memory.consolidate("c2", transport=transport) == 0
    assert seen["prompts"] == [], "nothing was alike, so there was nothing to ask"


async def test_same_drops_the_older_of_the_pair():
    facts = ["Prefers tea to coffee", *_filler(30), "Drinks tea rather than coffee"]
    await _seed("c3", facts)
    transport, seen = _fake_utility("same")

    assert await memory.consolidate("c3", transport=transport) == 1
    kept = [c for _, c in await db.all_memories("c3")]
    assert "Prefers tea to coffee" not in kept
    assert "Drinks tea rather than coffee" in kept
    assert len(kept) == len(facts) - 1
    assert len(seen["prompts"]) == 1, "one pair, one call"


async def test_replaced_drops_the_older_of_the_pair():
    facts = ["Works at MTN as an engineer", *_filler(30),
             "Works at Vodacom as an engineer"]
    await _seed("c4", facts)
    transport, _ = _fake_utility("replaced")

    assert await memory.consolidate("c4", transport=transport) == 1
    kept = [c for _, c in await db.all_memories("c4")]
    assert "Works at MTN as an engineer" not in kept
    assert "Works at Vodacom as an engineer" in kept


async def test_both_keeps_everything():
    facts = ["Prefers tea to coffee", *_filler(30), "Drinks tea rather than coffee"]
    await _seed("c5", facts)
    transport, _ = _fake_utility("both")

    assert await memory.consolidate("c5", transport=transport) == 0
    assert len(await db.all_memories("c5")) == len(facts)


async def test_an_unreadable_verdict_keeps_both():
    """The only actions are keep and delete, so a reply nobody could parse is
    never grounds for deleting."""
    await _seed("c6", ["Prefers tea to coffee", *_filler(30),
                       "Drinks tea rather than coffee"])
    transport, _ = _fake_utility('{"verdict": "possibly the first one?"}')
    assert await memory.consolidate("c6", transport=transport) == 0
    assert len(await db.all_memories("c6")) == 32


async def test_one_bad_verdict_costs_one_fact():
    """The blast radius that justifies the design. Even told to delete on every
    pair, the pass can only reach the pairs code offered it."""
    facts = ["Prefers tea to coffee", "Enjoys tea over coffee",
             *_filler(30), "Drinks tea rather than coffee"]
    await _seed("c7", facts)
    transport, _ = _fake_utility("replaced")

    removed = await memory.consolidate("c7", transport=transport)
    assert removed <= memory._MAX_PAIRS_PER_PASS
    kept = [c for _, c in await db.all_memories("c7")]
    assert len(kept) == len(facts) - removed
    assert all(f in kept for f in _filler(30)), "the filler was never at risk"


async def test_a_model_failure_leaves_the_store_alone():
    await _seed("c8", ["Prefers tea to coffee", *_filler(30),
                       "Drinks tea rather than coffee"])

    def boom(request):
        return httpx.Response(400, json={"error": "nope"})

    assert await memory.consolidate("c8", transport=httpx.MockTransport(boom)) == 0
    assert len(await db.all_memories("c8")) == 32


async def test_the_pair_is_shown_oldest_first():
    """"Fact 2 was recorded later" is how supersession is decided, so the order
    is load-bearing: swapped, every replacement resolves backwards."""
    await _seed("c9", ["Lives in Cape Town", *_filler(30),
                       "Lives in Cape Town now, mostly"])
    transport, seen = _fake_utility("both")
    await memory.consolidate("c9", transport=transport)

    prompt = seen["prompts"][0]
    assert prompt.index("1. Lives in Cape Town\n") < prompt.index("2. Lives in Cape Town now")


# --- the parser ------------------------------------------------------------

@pytest.mark.parametrize("reply, expected", [
    ('{"verdict": "both"}', "both"),
    ('{"verdict": "Same"}', "same"),
    ('{"verdict": "replaced."}', "replaced"),
    ('{"decision": "same"}', "same"),          # a synonym key
    ('{"answer": "both"}', "both"),
    ('{"x": "same"}', "same"),                 # one unknown key holding it
    ('{"verdict": "neither"}', ""),            # not a verdict we know
    ('{"a": "same", "b": "both"}', ""),        # ambiguous, so refuse
    ('{"verdict": 2}', ""),
    ('not json', ""),
])
def test_parse_verdict(reply, expected):
    assert memory._parse_verdict(reply) == expected


# --- the atomic delete -----------------------------------------------------

async def test_replace_memories_scopes_to_the_user():
    await _seed("c10", ["mine"])
    await _seed("c11", ["theirs"])
    await db.replace_memories("c10", [mid for mid, _ in await db.all_memories("c10")], [])
    assert [c for _, c in await db.all_memories("c11")] == ["theirs"]
