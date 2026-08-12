"""Markdown → plain text, for surfaces that render neither.

Both qwen2.5:3b and llama3.1:8b fail the same eval case: asked for three dinner
ideas over iMessage they answer with `**Baked Salmon**` and `* Pan-seared
salmon`, despite a system note saying no markdown and no lists. That is not a
capability gap either model can be talked out of — asked for a list, a model
writes a list, and the format prior beats the instruction.

So stop asking. `main._tts_clean` already does this for speech; this is the
same idea for message bubbles, with one difference: speech drops URLs because
they are unreadable aloud, and a bubble should keep them because they are
tappable.

Structure is preserved rather than flattened away — a bullet becomes "•", a
numbered list stays numbered. The goal is text that reads correctly where
asterisks would otherwise show up literally, not text with the shape removed.
"""
from __future__ import annotations

import re

_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```\s*$", re.M | re.S)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_BULLET = re.compile(r"^(\s*)[-*+]\s+", re.M)
_QUOTE = re.compile(r"^\s{0,3}>\s?", re.M)
_RULE = re.compile(r"^\s{0,3}(?:[-*_]\s*){3,}$", re.M)
# [label](url) → "label (url)", or just the url when the label repeats it.
_LINK = re.compile(r"\[([^\]]+)\]\(\s*(<)?([^)\s]+)(?(2)>)\s*(?:\"[^\"]*\")?\)")
_BOLD_STAR = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1", re.S)
# Underscore emphasis needs word boundaries, per CommonMark — without that guard
# `snake_case_name` unwraps to `snakecasename`, and mangling an identifier or a
# filename is worse than the asterisks ever were.
_BOLD_UNDERSCORE = re.compile(r"(?<![\w_])(_{1,3})(?=\S)(.+?)(?<=\S)\1(?![\w_])", re.S)
_CODE = re.compile(r"`([^`\n]+)`")


def flatten(text: str) -> str:
    """Plain text suitable for a message bubble."""
    if not text or not any(c in text for c in "*_`#[>"):
        return text                        # nothing to do, and most replies are this

    text = _FENCE.sub(lambda m: m.group(1).rstrip(), text)
    text = _RULE.sub("", text)
    text = _HEADING.sub("", text)
    text = _QUOTE.sub("", text)
    text = _LINK.sub(lambda m: m.group(3) if m.group(1).strip() == m.group(3)
                     else f"{m.group(1)} ({m.group(3)})", text)
    text = _CODE.sub(r"\1", text)
    # Emphasis last: link targets and code spans may legitimately contain
    # underscores, and unwrapping those first would corrupt them.
    for _ in range(2):                     # nested **_bold italic_**
        text = _BOLD_STAR.sub(r"\2", text)
        text = _BOLD_UNDERSCORE.sub(r"\2", text)
    text = _BULLET.sub(r"\1• ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
