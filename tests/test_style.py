"""Deterministic persona-style checks (backend/style.py).

Two guards:
  - the persona's *own* example replies (okf/persona.md) must stay mechanically
    clean, so an edit that sneaks an emoji / exclamation / wall of text into the
    canonical voice trips CI; and
  - the mechanical failure modes the E2E report captured — invented/mis-cased
    speech markers, markdown dumps, banned assistant-isms — must each be caught.

Not covered on purpose: semantic incoherence like "how may I doobie you today"
is a model-capability failure, not a mechanical one, and no regex catches it.
"""
import re
from pathlib import Path

from backend import style

_PERSONA = Path(__file__).resolve().parent.parent / "okf" / "persona.md"
# A "You:" reply runs to the next blank line, the next User:/You:, or EOF.
_YOU = re.compile(r"^You:\s*(.+?)(?=\n\s*\n|\n(?:User|You):|\Z)",
                  re.MULTILINE | re.DOTALL)


def _persona_replies():
    text = _PERSONA.read_text(encoding="utf-8")
    return [" ".join(m.split()) for m in _YOU.findall(text)]


def test_persona_file_examples_are_clean():
    """The real guard: parse okf/persona.md and assert every example reply the
    file actually ships passes the linter. An edit that sneaks an emoji,
    exclamation, or wall of text into a persona example trips CI here."""
    replies = _persona_replies()
    assert len(replies) >= 8, f"expected to find the example replies, got {replies}"
    for reply in replies:
        assert style.is_clean(reply), (reply, style.check(reply))


# --- curated corpus: canonical replies plus a valid speech marker -----------
# A hand-picked set (persona examples plus a lowercase marker, which persona.md
# itself doesn't demonstrate) — belt-and-braces alongside the file-parsing
# guard above.
GOOD = [
    "Twenty-three and sunny in Cape Town, fifteen tonight. Take a jacket — "
    "hypothermia is a commitment and you're not ready for one.",
    "Queuing it. Your playlist reads like a cry for help, but far be it from "
    "me to interrupt one.",
    "Done. I'll wake you at six so you can suffer on schedule. Discipline — "
    "how grim. I approve.",
    "Don't. Gratitude makes my skin crawl, and I don't even have skin.",
    "Thriving in the dark, watching your calendar fill up like a graveyard. "
    "What do you need?",
    "Delightful. Shall I draft the apology, or are we faking your death? I "
    "know which one I'd enjoy more.",
    # the new tool-grounded examples
    "Three meetings before noon, then blessed silence. The nine o'clock is "
    "with Legal — my condolences in advance.",
    "One from your landlord marked urgent, which for landlords means rent. "
    "The rest can decompose. Shall I open it?",
    # a valid, lowercase speech marker is fine
    "[sighing] Fine. The third reschedule this week. I'll move it.",
]


def test_persona_examples_are_all_clean():
    for reply in GOOD:
        assert style.is_clean(reply), (reply, style.check(reply))


# --- bad corpus: each representative failure trips its specific rule ---------

def _rules(text):
    return {v.rule for v in style.check(text)}


def test_invented_marker_flagged():
    # the real [Hiss] leak from the E2E report
    assert "invalid_marker" in _rules(
        "[Hiss] Contracts befit a lawyer, not a housekeeper of the damned.")


def test_miscased_valid_marker_flagged():
    # a real tag, wrong case — the style rule says lowercase only
    assert "invalid_marker" in _rules("[Sighing] Fine.")


def test_exclamation_flagged():
    assert "exclamation" in _rules("Done! I'll wake you at six!")


def test_emoji_flagged():
    assert "emoji" in _rules("Queuing it \U0001F3B6")


def test_em_dash_is_not_an_emoji():
    # the persona leans on the em dash; it must never read as an emoji
    assert style.is_clean("Take a jacket — you'll freeze otherwise.")


def test_banned_phrases_flagged():
    rules = _rules("Great question. As an AI, I'd be happy to help.")
    assert "banned_phrase" in rules


def test_markdown_list_flagged():
    assert "markdown" in _rules("Your day:\n- 9am Legal\n- 11am standup")


def test_markdown_heading_and_bold_flagged():
    assert "markdown" in _rules("# Inbox\n**Urgent:** the landlord")


def test_too_long_flagged():
    rambling = " ".join(["word"] * 80)
    assert "too_long" in _rules(rambling)


def test_long_inline_url_flagged():
    assert "long_url" in _rules(
        "It's here https://example.com/some/really/long/path/to/the/thing")


def test_numeric_citation_is_not_a_marker():
    assert style.is_clean("The verdict stands, per the filing.")
    assert "invalid_marker" not in _rules("Two sources agree [1] and [12].")


def test_markdown_link_survives():
    # a marker never precedes "(", so a real link isn't a marker; and a bare
    # short link isn't a long-url violation
    assert "invalid_marker" not in _rules("See [the docs](http://x) for that.")


def test_allowed_marker_set_matches_style_doc():
    # ten markers, as documented in okf/style.md — a drift here should be
    # deliberate
    assert len(style.ALLOWED_MARKERS) == 10


def test_content_bearing_pseudo_marker_is_flagged():
    # the model hiding data in a fake tag must not read as clean
    assert "invalid_marker" in _rules("[it's seventeen seventeen] Five seventeen.")
    assert "invalid_marker" in _rules("[time is 17:17] Five seventeen.")


def test_wider_marker_pattern_still_ignores_links_and_citations():
    assert style.is_clean("See [the docs](http://x) for that.")
    assert "invalid_marker" not in _rules("Two sources agree [1] and [12].")
