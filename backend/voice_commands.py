"""Voice-driven UI commands intercepted *before* the LLM.

The frontend runs hands-free: every spoken utterance is transcribed and would
normally become a chat turn. A handful of phrases, though, are meant to drive
the HUD itself — "run system diagnostics", "show the logs", "close the mic" —
and should navigate silently instead of provoking a confused model reply.

`match(text)` runs on the transcript the instant STT finishes. When it matches,
the socket emits the returned event to the client and skips the model turn
entirely, so the tab switches (or the mic closes) with no spoken answer.
"""
from __future__ import annotations

import re

# Order matters — first match wins. Each entry is (compiled regex, event dict).
_RULES: list[tuple[re.Pattern[str], dict]] = [
    # Stand down / close the mic — ends the persistent audio session.
    (re.compile(
        r"\b(?:close|shut|kill|cut|mute|stop|end|drop)\s+(?:the\s+|your\s+)?"
        r"(?:mic|microphone|audio|session|listening)\b"
        r"|\b(?:go\s+to\s+sleep|stand\s+down|stop\s+listening|power\s+down|"
        r"that'?s\s+all|that\s+is\s+all|dismissed|nap\s+time)\b", re.I),
     {"type": "command", "action": "close_mic"}),
    # Diagnostics screen + spoken read-out.
    (re.compile(
        r"\b(?:run(?:\s+a)?(?:\s+system)?\s+diagnostics?|system\s+diagnostics?"
        r"|(?:show|open|go\s+to|pull\s+up)\s+(?:me\s+)?(?:the\s+)?diagnostics?"
        r"|diagnostics?\s+(?:screen|panel)|system\s+status|status\s+report)\b", re.I),
     {"type": "nav", "target": "diagnostics"}),
    # Logs screen.
    (re.compile(
        r"\b(?:(?:show|open|go\s+to|pull\s+up|check|see|view)\s+(?:me\s+)?(?:the\s+)?logs?"
        r"|log\s+stream|system\s+logs?)\b", re.I),
     {"type": "nav", "target": "logs"}),
    # Command deck / home.
    (re.compile(
        r"\b(?:command\s+(?:deck|cent(?:er|re))|(?:go|back)\s+(?:to\s+)?home"
        r"|home\s+screen|main\s+screen"
        r"|(?:show|open|back\s+to|go\s+to|return\s+to)\s+(?:the\s+)?command)\b", re.I),
     {"type": "nav", "target": "command"}),
]


def match(text: str) -> dict | None:
    """Return the UI event for a recognised command phrase, else None."""
    if not text:
        return None
    for pattern, event in _RULES:
        if pattern.search(text):
            return dict(event)
    return None
