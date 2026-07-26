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

# Any short bracketed run that starts with a letter and isn't a markdown link.
# Deliberately not an allow-list of characters: the model invents
# content-bearing pseudo-tags — real captures include "[it's seventeen
# seventeen]" and "[time is 17:17]" — and each new punctuation mark would
# otherwise be another leak into the chat and the TTS. Numeric citations ([1],
# [12]) start with a digit and survive; links are guarded by the (?!\().
_MARKER = re.compile(r"\[[A-Za-z][^\]\n]{1,40}\](?!\() ?")

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
