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

# Delivery intent, chosen per reply. These ride in the same bracket syntax as the
# emotion markers — and are removed by the same strip() — so nothing new leaks to
# the user, and choosing costs no extra model round trip.
_VOICE_INTENT = {"voice": "voice", "speak": "voice", "aloud": "voice",
                 "text": "text", "silent": "text", "written": "text"}
_INTENT_RE = re.compile(r"\[([A-Za-z]+)\]")


def voice_intent(text: str) -> str | None:
    """"voice", "text", or None if the reply expressed no preference.

    Only the first few markers are considered: a tag buried in the third
    paragraph is the model narrating, not deciding.
    """
    for match in list(_INTENT_RE.finditer(text or ""))[:3]:
        if (intent := _VOICE_INTENT.get(match.group(1).lower())):
            return intent
    return None

# A direct instruction about how she should talk back. Kept separate from
# _VOICE_INTENT above, which reads *her* markers: this reads the user's words.
#
# There is a set_reply_mode tool for exactly this and the model did not call it.
# Asked "Use text now please" it answered "Got it. I'll be sending replies as
# plain text from now on", ran nothing, stored nothing, and sent the next reply
# as a voice note — a fabricated action indistinguishable, from the outside,
# from being ignored. A plain instruction about the channel itself is too small
# and too obviously-honoured to be left to a 7B model's tool choice, so it is
# resolved here before the model ever sees the turn.
_MODE_REQUEST = re.compile(
    r"\b(?:"
    r"(?:use|send|reply|respond|answer|talk|speak|write|switch\s+to|go)\s+"
    r"(?:with\s+|in\s+|to\s+|me\s+|back\s+)*"
    r"(?P<a>text|texts?|typing|written|writing|voice|audio|speech|voice\s*notes?|aloud)"
    r"|(?P<b>text|voice|audio)\s+(?:me\s+)?(?:only|from\s+now\s+on|please)"
    r"|(?:stop|no\s+more|quit)\s+(?:sending\s+)?(?:the\s+|your\s+)?"
    r"(?P<c>voice\s*notes?|audio|voice|texting|texts?)"
    r")\b", re.I)

_MODE_WORDS = {"text": "text", "texts": "text", "texting": "text", "typing": "text",
               "written": "text", "writing": "text",
               "voice": "voice", "audio": "voice", "speech": "voice", "aloud": "voice",
               "voice note": "voice", "voice notes": "voice",
               "voicenote": "voice", "voicenotes": "voice"}


def reply_mode_request(text: str) -> str | None:
    """"text", "voice", or None — a user asking to change how replies arrive.

    "stop sending voice notes" and "use text" mean the same thing, so the
    negated group inverts: stopping one mode selects the other.
    """
    m = _MODE_REQUEST.search(text or "")
    if not m:
        return None
    word = (m.group("a") or m.group("b") or m.group("c") or "").lower()
    word = re.sub(r"\s+", " ", word).strip()
    mode = _MODE_WORDS.get(word)
    if mode and m.group("c"):
        mode = "text" if mode == "voice" else "voice"      # "stop the voice notes"
    return mode


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
