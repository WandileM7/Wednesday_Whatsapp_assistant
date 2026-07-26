r"""Speech emotion/effect markers, e.g. "[sighing] Fine, I'll check."

okf/style.md tells the model to open the odd sentence with one; Fish
Audio performs them. Everything a human reads (web chat, WhatsApp) and
the Piper fallback (which would read them out literally) strips them.

Matching is case-insensitive: the model doesn't reliably honour the
lowercase rule (it emits "[Sighing]" and even invents tags like "[Hiss]"),
and any of those would otherwise leak into the chat or be read aloud. A
marker is a short all-letters bracketed word or phrase, so markdown links
([label](url), guarded by the (?!\() lookahead) and numeric citations
([1], [12] — they start with a digit) both survive.
"""
from __future__ import annotations
import re

_MARKER = re.compile(r"\[[A-Za-z][A-Za-z \-]{1,30}\](?!\() ?")

def strip(text: str) -> str:
    """Remove markers. No end-trimming, so streamed prefixes stay stable."""
    return _MARKER.sub("", text)

def safe_len(text: str) -> int:
    """Length of the prefix guaranteed not to end inside a half-received
    marker — hold back a trailing unclosed "[" while streaming."""
    i = text.rfind("[")
    if i != -1 and "]" not in text[i:] and len(text) - i <= 40:
        return i
    return len(text)
