"""The periodic history sweep.

Every case here is a shape that actually got persisted and then taught the next
turn to repeat it.
"""
import pytest

from backend import db, hygiene


def _rows(*specs):
    """(role, content, tool_calls?, name?) → stored message dicts with ids."""
    out = []
    for i, spec in enumerate(specs, start=1):
        role, content = spec[0], spec[1]
        out.append({"id": i, "role": role, "content": content,
                    "tool_calls": spec[2] if len(spec) > 2 else None,
                    "name": spec[3] if len(spec) > 3 else None})
    return out


def test_clean_history_is_left_alone():
    rows = _rows(
        ("user", "what's on my calendar?"),
        ("assistant", "Nothing today. Enjoy the silence."),
        ("user", "put on Africa by Toto"),
        ("tool", "Playing Africa by TOTO.", None, "spotify_play"),
        ("assistant", "Playing Africa by TOTO."),
    )
    assert hygiene.scan(rows) == []


def test_catches_an_unanswered_turn():
    """A turn that died mid-flight: the next reply answers the older question,
    which is how a stale 'run a system check' surfaced two hours later."""
    rows = _rows(
        ("user", "Run a system check"),
        ("user", "Hi Wednesday"),
        ("assistant", "Hello."),
    )
    found = hygiene.scan(rows)
    assert [f.message_id for f in found] == [1]
    assert found[0].reason == "unanswered turn"


def test_catches_a_trailing_unanswered_turn():
    rows = _rows(("user", "hello"), ("assistant", "Hi."), ("user", "still there?"))
    assert [f.message_id for f in hygiene.scan(rows)] == [3]


def test_catches_a_fabricated_action():
    """Claimed to play a song with no tool call behind it — persisted, it became
    the house style and Spotify stopped being called at all."""
    rows = _rows(
        ("user", "put on Africa by Toto"),
        ("assistant", '[voice] Playing "Africa" by Toto. Enjoy the music!'),
    )
    found = hygiene.scan(rows)
    assert len(found) == 1 and found[0].reason.startswith("fabricated")


def test_a_tool_call_in_the_same_turn_clears_the_claim():
    rows = _rows(
        ("user", "put on Africa by Toto"),
        ("tool", "Playing Africa by TOTO.", None, "spotify_play"),
        ("assistant", "Playing Africa by TOTO."),
    )
    assert hygiene.scan(rows) == []


def test_a_tool_call_from_an_earlier_turn_does_not_clear_it():
    """Tool credit does not carry across turns — otherwise one real play would
    excuse every fabrication after it."""
    rows = _rows(
        ("user", "put on Africa"),
        ("tool", "Playing Africa by TOTO.", None, "spotify_play"),
        ("assistant", "Playing Africa by TOTO."),
        ("user", "now put on Bohemian Rhapsody"),
        ("assistant", "Playing Bohemian Rhapsody by Queen."),
    )
    found = hygiene.scan(rows)
    assert [f.message_id for f in found] == [5]


def test_catches_a_fabricated_failure():
    """The half this scan missed.

    Eight "I couldn't find X" replies with no search behind them sat in a real
    history while sweep() reported it clean, because the scan only looked for
    fabricated *success*. Every song request after them was answered the same
    way — the model reading its own past refusals as house style.
    """
    rows = _rows(
        ("user", "Play eternity"),
        ("assistant", 'I couldn\'t find the song "eternity". Could you give me the artist?'),
    )
    found = hygiene.scan(rows)
    assert len(found) == 1 and found[0].reason.startswith("fabricated failure")


def test_a_real_search_makes_couldnt_find_honest():
    """After a search that ran and returned nothing, this is the true answer."""
    rows = _rows(
        ("user", "Play eternity"),
        ("tool", "No tracks matched.", None, "spotify_play"),
        ("assistant", "I couldn't find anything called that."),
    )
    assert hygiene.scan(rows) == []


def test_catches_the_invented_capability_limit():
    """'stored locally on your device' — untrue, and unknowable without looking.
    Persisted twice, it taught her she has no access to Spotify at all."""
    rows = _rows(
        ("user", "Can you list my playlists?"),
        ("assistant", "I don't have direct access to your Spotify playlists as "
                      "they are stored locally on your device."),
    )
    assert len(hygiene.scan(rows)) == 1


def test_catches_degenerate_output():
    rows = _rows(("user", "hi"), ("assistant", "G" * 60))
    found = hygiene.scan(rows)
    assert len(found) == 1 and found[0].reason == "degenerate output"


def test_reads_tool_names_from_the_assistant_tool_calls_blob():
    rows = _rows(
        ("user", "put on Africa"),
        ("assistant", "Playing Africa by TOTO.",
         '[{"function": {"name": "spotify_play"}}]'),
    )
    assert hygiene.scan(rows) == []


@pytest.mark.asyncio
async def test_sweep_deletes_and_settles():
    """Deleting a bad reply orphans the turn it answered, which is itself a
    finding — the sweep has to settle rather than leave a fresh problem."""
    await db.init()
    user = "hygiene-test-user"
    await db.clear_messages(user)
    await db.add_messages(user, [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "Hi."},
        {"role": "user", "content": "play something"},
        {"role": "assistant", "content": "G" * 60},
    ])
    found = await hygiene.sweep(user)
    reasons = sorted(f.reason for f in found)
    assert reasons == ["degenerate output", "unanswered turn"]
    assert await hygiene.sweep(user, dry_run=True) == []
    left = await db.raw_messages(user)
    assert [m["content"] for m in left] == ["hello", "Hi."]


@pytest.mark.asyncio
async def test_dry_run_reports_without_deleting():
    await db.init()
    user = "hygiene-dry-user"
    await db.clear_messages(user)
    await db.add_messages(user, [
        {"role": "user", "content": "play something"},
        {"role": "assistant", "content": "Playing Africa by TOTO."},
    ])
    assert len(await hygiene.sweep(user, dry_run=True)) == 1
    assert len(await db.raw_messages(user)) == 2


@pytest.mark.asyncio
async def test_a_guarded_turn_is_not_persisted_as_an_example():
    """The correction must not become the pattern.

    Four "I said I couldn't find that, but I never actually looked" turns landed
    back to back in real history and the model began answering every song
    request that way — the containment message teaching the failure it exists to
    stop. A turn that produced only a guard message is a non-event: nothing is
    stored, including the user message, whose orphan would send the next reply
    back to answer it.
    """
    from backend import agent
    await db.init()
    user = "guard-persist-user"
    await db.clear_messages(user)

    turn = [{"role": "user", "content": "play eternity"},
            {"role": "assistant", "content": "I couldn't find that song."}]   # no tool ran
    assert agent._persistable(user, turn) == []

    honest = [{"role": "user", "content": "play eternity"},
              {"role": "tool", "content": "Playing Eternity.", "name": "spotify_play"},
              {"role": "assistant", "content": "Playing Eternity."}]
    assert agent._persistable(user, honest) == honest


@pytest.mark.asyncio
async def test_sweep_trims_the_sign_off_without_dropping_the_reply():
    """The tic is not a lie, so the answer survives — but it does not stay in
    history teaching the next reply to end the same way."""
    await db.init()
    user = "hygiene-filler-user"
    await db.clear_messages(user)
    await db.add_messages(user, [
        {"role": "user", "content": "put on Africa"},
        {"role": "tool", "content": "Playing Africa by TOTO.", "name": "spotify_play"},
        {"role": "assistant",
         "content": "On it goes. How can I assist you further today, Wandile?"},
    ])
    await hygiene.sweep(user)
    left = [m["content"] for m in await db.raw_messages(user)]
    assert left == ["put on Africa", "Playing Africa by TOTO.", "On it goes."]


@pytest.mark.asyncio
async def test_dry_run_does_not_trim():
    await db.init()
    user = "hygiene-filler-dry"
    await db.clear_messages(user)
    await db.add_messages(user, [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Evening. Is there anything else you need?"},
    ])
    await hygiene.sweep(user, dry_run=True)
    assert (await db.raw_messages(user))[1]["content"].endswith("anything else you need?")
