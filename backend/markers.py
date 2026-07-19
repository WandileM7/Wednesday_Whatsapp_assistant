"""Speech emotion/effect markers, e.g. "[sighing] Fine, I'll check."

okf/style.md tells the model to open the odd sentence with one; Fish
Audio performs them. Everything a human reads (web chat, WhatsApp) and
the Piper fallback (which would read them out literally) strips them.

Only lowercase words qualify, so markdown links and citations survive.
"""
from __future__ import annotations
import re

_MARKER = re.compile(r"\[[a-z][a-z \-]{1,30}\](?!\() ?")

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
