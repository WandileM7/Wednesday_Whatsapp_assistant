from backend import db, oauth, whatsapp
from backend.agent import _slice, _est_tokens
from backend.config import settings
from backend.main import _speakable, _tts_clean


async def test_message_persistence_round_trip():
    await db.init()
    await db.clear_messages("t1")
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "web_search", "arguments": {}}}]},
        {"role": "tool", "name": "web_search", "content": "results"},
        {"role": "assistant", "content": "hello"},
    ]
    await db.add_messages("t1", msgs)
    loaded = await db.recent_messages("t1")
    assert loaded == msgs
    await db.clear_messages("t1")
    assert await db.recent_messages("t1") == []


async def test_recent_messages_respects_limit_and_order():
    await db.init()
    await db.clear_messages("t2")
    await db.add_messages("t2", [{"role": "user", "content": f"m{i}"} for i in range(10)])
    loaded = await db.recent_messages("t2", limit=3)
    assert [m["content"] for m in loaded] == ["m7", "m8", "m9"]
    await db.clear_messages("t2")


async def test_summary_round_trip():
    await db.init()
    assert await db.get_summary("t3") is None
    await db.save_summary("t3", "first")
    await db.save_summary("t3", "second")
    assert await db.get_summary("t3") == "second"
    await db.clear_messages("t3")
    assert await db.get_summary("t3") is None


def test_slice_keeps_newest_within_budget():
    history = [{"role": "user", "content": "x" * 400}] * 50  # ~108 tokens each
    kept = _slice(history, budget=500)
    assert 0 < len(kept) < len(history)
    assert sum(_est_tokens(m) for m in kept) <= 500


def test_slice_never_starts_on_orphan_tool_result():
    history = [
        {"role": "user", "content": "x" * 400},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "f", "arguments": {}}}]},
        {"role": "tool", "name": "f", "content": "y" * 400},
        {"role": "assistant", "content": "done"},
    ]
    kept = _slice(history, budget=120)  # enough for the tail, not the tool call
    assert kept and kept[0]["role"] != "tool"


def test_speakable_waits_for_min_chars_then_takes_full_sentences():
    assert _speakable("Hi. ", 0) == 0  # under the 20-char minimum
    text = "This is a full sentence. And another one follows here. Trailing frag"
    end = _speakable(text, 0)
    assert text[:end].rstrip().endswith("here.")


def test_tts_clean_strips_markdown_and_urls():
    cleaned = _tts_clean("See [the docs](https://x.com/a) or https://y.com **now**\n- item one")
    assert "http" not in cleaned and "*" not in cleaned and "[" not in cleaned
    assert "the docs" in cleaned and "item one" in cleaned


def test_oauth_state_is_one_time_use():
    url = oauth.google_authz_url()
    state = url.split("state=")[1].split("&")[0]
    assert oauth.verify_state(state) is True
    assert oauth.verify_state(state) is False  # consumed
    assert oauth.verify_state("") is False
    assert oauth.verify_state("forged") is False


def test_jid_allowlist_and_owner_identity(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_allowed_jids", "")
    assert whatsapp._jid_allowed("anyone@s.whatsapp.net")
    monkeypatch.setattr(settings, "whatsapp_allowed_jids", "a@s.whatsapp.net, b@s.whatsapp.net")
    assert whatsapp._jid_allowed("a@s.whatsapp.net")
    assert not whatsapp._jid_allowed("c@s.whatsapp.net")

    monkeypatch.setattr(settings, "whatsapp_owner_jid", "a@s.whatsapp.net")
    assert whatsapp._user_key("a@s.whatsapp.net") == settings.default_user
    assert whatsapp._user_key("b@s.whatsapp.net") == "wa:b@s.whatsapp.net"
