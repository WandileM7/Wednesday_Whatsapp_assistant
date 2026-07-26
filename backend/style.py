"""Deterministic style checks for Wednesday's persona rules.

The persona (``okf/persona.md``) and delivery (``okf/style.md``) prescribe a
handful of *mechanical* rules — no exclamation marks, no emojis, no markdown
structure, keep it short, a fixed set of speech markers, and a short list of
banned assistant-isms. None of these need a model to judge; they're
regex-checkable, so this module catches them cheaply.

Two uses:
  - a regression test (``tests/test_style.py``) that pins the persona's own
    example replies as clean and real captured failures as violations, so an
    edit that drifts the voice out of character trips CI; and
  - a runtime observability hook: ``agent.stream_reply`` logs any violation in
    a finished reply, so drift in the live model is visible in the logs.

Detection only — nothing here rewrites a reply. A deterministic pass can spot
an out-of-character line but can't put it *back* in character, and silently
mangling the model's words is worse than a logged warning. It also can't judge
*incoherence* ("how may I doobie you today") — that's a model-capability
problem, not a mechanical one, and out of scope here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The ten speech markers okf/style.md permits. A tag outside this set — or one
# that isn't lowercase — is the model inventing/mis-casing (e.g. "[Hiss]",
# "[Sighing]"), which markers.strip() removes but the voice never should have
# emitted. Kept in sync with okf/style.md by hand; the test asserts the count.
ALLOWED_MARKERS = frozenset({
    "sighing", "chuckling", "whispering", "calm", "serious",
    "curious", "surprised", "excited", "laughing", "break",
})

# persona.md's explicit ban list, plus the obvious variants.
BANNED_PHRASES = (
    "how can i assist", "how may i assist", "i'd be happy to",
    "i would be happy to", "great question", "as an ai", "no problem at all",
)
# Word-boundary anchored so "as an ai" doesn't fire on "as an aid"/"as an air".
_BANNED = tuple((p, re.compile(r"\b" + re.escape(p) + r"\b")) for p in BANNED_PHRASES)

# Roughly "short". persona.md's longest example reply is ~20 words; a reply is
# allowed to run longer when detail is explicitly asked for, so this is a soft
# ceiling meant to catch a rambling wall of text, not to police every reply.
_WORD_CAP = 60

# Same shape markers.py uses: a bracketed all-letters word/phrase, not followed
# by "(" (so markdown links survive) and not starting on a digit (so numeric
# citations like [1] survive — the [A-Za-z] first char handles that).
_MARKER = re.compile(r"\[([A-Za-z][A-Za-z \-]{1,30})\](?!\()")

# Clear emoji blocks: misc symbols & dingbats, misc symbols & arrows, the main
# emoji planes, regional-indicator flags, plus the ZWJ and variation selector
# used to join them. Deliberately excludes U+2014 (—), the em dash the persona
# leans on, and other general punctuation.
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D]"
)

# Markdown structure the delivery rules forbid: headings, bullet/numbered
# lists, fenced code, bold. Anchored to line starts so an em-dash aside
# ("a jacket — hypothermia") and inline hyphenation don't false-positive.
_MARKDOWN = (
    (re.compile(r"(?m)^\s{0,3}#{1,6}\s"), "heading"),
    (re.compile(r"(?m)^\s{0,3}[-*+]\s"), "bullet list"),
    (re.compile(r"(?m)^\s{0,3}\d+[.)]\s"), "numbered list"),
    (re.compile(r"```"), "code fence"),
    (re.compile(r"\*\*\S"), "bold"),
)

# A long http(s) URL pasted inline. style.md: only include a full link when
# asked, and then on its own line — a long URL glued into prose breaks that.
_LONG_URL = re.compile(r"https?://\S{25,}")


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:  # for log lines and test messages
        return f"{self.rule}: {self.detail}"


def check(text: str) -> list[Violation]:
    """Return every persona rule ``text`` breaks, in a stable order. Empty list
    means the reply is mechanically in character."""
    out: list[Violation] = []
    low = text.lower()

    for phrase, pat in _BANNED:
        if pat.search(low):
            out.append(Violation("banned_phrase", phrase))

    if "!" in text:
        out.append(Violation("exclamation", "no exclamation marks"))

    if m := _EMOJI.search(text):
        out.append(Violation("emoji", repr(m.group())))

    for pat, label in _MARKDOWN:
        if pat.search(text):
            out.append(Violation("markdown", label))

    for tag in _MARKER.findall(text):
        if tag != tag.lower() or tag.lower() not in ALLOWED_MARKERS:
            out.append(Violation("invalid_marker", f"[{tag}]"))

    if (n := len(text.split())) > _WORD_CAP:
        out.append(Violation("too_long", f"{n} words"))

    if m := _LONG_URL.search(text):
        out.append(Violation("long_url", m.group()[:60]))

    return out


def is_clean(text: str) -> bool:
    return not check(text)
