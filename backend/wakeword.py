"""Wake-word gating for ambient listening.

Hands-free mode already runs continuous VAD, but VAD only knows *someone is
talking* — not whether they're talking to Wednesday. Leaving that ungated means
she answers your phone calls. This module decides whether a transcript was
addressed to her, and strips the address off before it reaches the agent.

It gates on the *transcript*, after STT, which is the pragmatic choice here: it
needs no new model or dependency and it is exact about phrasing. The efficient
alternative is an always-on ONNX keyword spotter in the browser (openWakeWord),
which avoids running STT over every stray utterance — worth adding when the
CPU cost of transcribing background chatter starts to bite, since it needs a
bundled model asset.

Whisper is loose with an unusual proper noun, so the matcher accepts the
mishearings it actually produces ("Wednesdays", "when's day", "wensday") rather
than trusting a single exact spelling.
"""
from __future__ import annotations

import re

from .config import settings

# Filler that can precede the name: "hey Wednesday", "ok Wednesday, ...".
_PREFIXES = r"(?:hey|hi|hello|ok|okay|yo|um|uh)"

# Common whisper renderings of "wednesday". Extended from the configured wake
# word: if the user picks another name, we still match it exactly.
_VARIANTS = ("wednesday", "wednesdays", "wensday", "wensdays", "wednes day",
             "when's day", "whens day", "wendsday", "wednesday's")


def _pattern() -> re.Pattern:
    words = {settings.wake_word.strip().lower()} | set(_VARIANTS)
    alts = "|".join(sorted((re.escape(w) for w in words if w), key=len, reverse=True))
    # optional filler, the name, then optional punctuation — anchored at the start
    return re.compile(rf"^\W*(?:{_PREFIXES}\s+)?(?:{alts})\b[\s,.!?:;-]*", re.IGNORECASE)


def split(text: str) -> tuple[bool, str]:
    """(was_addressed, remaining_text).

    The remainder is what the user actually asked. A bare "Wednesday?" is
    addressed but empty — the caller decides whether that deserves a prompt.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False, ""
    m = _pattern().match(stripped)
    if not m:
        return False, stripped
    return True, stripped[m.end():].strip()


def gate(text: str, *, hands_free: bool) -> tuple[bool, str]:
    """Decide whether to act on an utterance.

    Only ambient (hands-free) audio is gated: if the user deliberately pressed
    the mic button or typed, they're plainly addressing her and demanding the
    name would be obnoxious. Gating is also off entirely unless
    WAKE_WORD_REQUIRED is set, so nothing changes for existing setups.
    """
    if not hands_free or not settings.wake_word_required:
        return True, (text or "").strip()
    addressed, rest = split(text)
    return addressed, rest
