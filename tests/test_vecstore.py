"""Hybrid memory index: FTS5 + vector, and the fallbacks under each failure."""
import pytest

from backend import memory, vecstore
from backend.config import settings

ROWS = [(1, "Wandile is moving to Cape Town in March"),
        (2, "Prefers tea over coffee, milk no sugar"),
        (3, "Sister is called Naledi and lives in Durban"),
        (4, "Building a WhatsApp assistant named Wednesday")]


def _fake_embed(texts):
    """Bag-of-characters vectors: crude, but deterministic and offline, and
    close enough that a query shares direction with the row it came from."""
    async def _run():
        out = []
        for text in texts:
            vec = [0.0] * 26
            for ch in text.lower():
                if "a" <= ch <= "z":
                    vec[ord(ch) - 97] += 1.0
            out.append(vec)
        return out
    return _run()


@pytest.fixture
def store(monkeypatch, tmp_path):
    """A fresh index per test — module state is global by design."""
    monkeypatch.setattr(settings, "vector_db_path", str(tmp_path / "vec.db"))
    monkeypatch.setattr(settings, "enable_memory_embeddings", True)
    monkeypatch.setattr(vecstore, "_conn", None)
    monkeypatch.setattr(vecstore, "_dim", 0)
    monkeypatch.setattr(vecstore, "_embed_broken", False)
    monkeypatch.setattr(vecstore, "embed", _fake_embed)
    return vecstore


async def test_sync_indexes_once_and_is_idempotent(store):
    assert await store.sync("u", ROWS) == 4
    assert await store.sync("u", ROWS) == 0            # nothing new to embed
    assert await store.sync("u", ROWS + [(5, "Allergic to shellfish")]) == 1


async def test_sync_drops_memories_that_no_longer_exist(store):
    """`rows` is the whole truth, so anything indexed and absent from it is gone.

    sync() was add-only, and deleted facts stayed searchable forever: one
    account's memories table held a single row while recall kept returning four
    phantoms from a spell of degenerate output, injecting them into every prompt
    as things known about the user. Deleting a memory has to mean it stops
    coming back.
    """
    await store.sync("u", ROWS)
    await store.sync("u", [r for r in ROWS if r[0] != 3])          # Naledi deleted
    # search() takes the top k with no similarity floor, so it keeps returning
    # whatever is left; the property that matters is that the deleted fact is
    # not among them even for the query that targets it exactly.
    assert "Sister is called Naledi and lives in Durban" not in await store.search(
        "u", "sister Naledi Durban", 4)
    assert "Prefers tea over coffee, milk no sugar" in await store.search(
        "u", "does he drink tea", 4)


async def test_a_deleted_id_can_be_reindexed(store):
    """Stale rows leave all three tables, so a later memory reusing the id gets
    its own content rather than the ghost of the old one."""
    await store.sync("u", ROWS)
    await store.sync("u", ROWS[:3])
    await store.sync("u", ROWS[:3] + [(4, "Allergic to shellfish")])
    hits = await store.search("u", "shellfish allergy", 4)
    assert "Allergic to shellfish" in hits
    assert "Building a WhatsApp assistant named Wednesday" not in hits


async def test_search_finds_a_row_without_shared_terms(store):
    await store.sync("u", ROWS)
    hits = await store.search("u", "where is the flat he is moving to", 2)
    assert "Wandile is moving to Cape Town in March" in hits


async def test_search_is_scoped_per_user(store):
    await store.sync("u", ROWS)
    assert await store.search("someone-else", "Cape Town", 3) == []


async def test_forget_drops_the_user(store):
    await store.sync("u", ROWS)
    await store.forget("u")
    assert await store.search("u", "Cape Town", 3) == []


async def test_keyword_only_when_embeddings_are_unavailable(store, monkeypatch):
    """No embed model: rows still index, and FTS5 alone answers."""
    monkeypatch.setattr(store, "embed", lambda texts: _empty())
    assert await store.sync("u", ROWS) == 4
    assert await store.search("u", "Naledi", 2) == ["Sister is called Naledi and lives in Durban"]


async def _empty():
    return []


async def test_brute_force_cosine_matches_when_sqlite_vec_is_missing(store, monkeypatch):
    monkeypatch.setattr(store, "_vec_ok", False)
    await store.sync("u", ROWS)
    hits = await store.search("u", "milk no sugar please", 2)
    assert "Prefers tea over coffee, milk no sugar" in hits


def test_pronouns_are_kept_out_of_the_fts_expression():
    """Regression: an FTS MATCH is an OR, so "he" matched every memory about
    him and that noise outranked the vector half's real answer (4/8 → 8/8 on a
    10-fact benchmark once dropped)."""
    expr = vecstore._match_expr("does he exercise")
    assert expr == '"exercise"'
    assert "he" not in expr


def test_an_all_stopword_query_skips_the_keyword_half():
    assert vecstore._match_expr("what about them") == ""


def test_apostrophes_do_not_smuggle_stopwords_back_in():
    assert vecstore._match_expr("any food he can't eat") == '"food" OR "eat"'


async def test_stopword_only_query_still_answers_from_vectors(store):
    await store.sync("u", ROWS)
    assert await store.search("u", "what about them", 2)   # vector half alone


async def test_relevant_falls_back_to_lexical_on_a_cold_index(store, monkeypatch):
    """memory.relevant must answer from the DB even before anything is indexed."""
    monkeypatch.setattr(store, "search", lambda *a, **k: _empty())
    monkeypatch.setattr(memory.db, "all_memories", lambda user, limit=500: _rows())
    hits = await memory.relevant("u", "tell me about Naledi", k=2)
    assert hits and "Naledi" in hits[0]


async def _rows():
    return list(reversed(ROWS))
