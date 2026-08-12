"""Periodic sanity pass over stored conversation history.

Three times a bad reply has been persisted and then become the template the next
turn copied:

  - "How can I assist further?" closed almost every reply for days, and appears
    nowhere in the OKF bundle — the model learned it from watching itself
  - a turn that died mid-flight left a user message with no answer, and the next
    reply answered *that* question instead of the one just asked
  - three fabricated "Playing X. Enjoy!" replies taught the model that song
    requests are answered with a sentence rather than a tool call, and Spotify
    stopped being called at all
  - then the same thing inverted: "I couldn't find that song" replies where no
    search had run, which this scan did not detect at all and so declared clean

The guards in `agent.reply()` stop new ones being written. This removes the ones
already there — including whatever a future failure mode writes before anyone
knows to guard against it. History is the one part of the system that compounds:
everything else fails a turn at a time, this fails forever.

Conservative by construction. Every finding names a message id and a reason, and
`sweep(dry_run=True)` reports without deleting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from . import db, guard
from .agent import _degenerate

log = logging.getLogger(__name__)


@dataclass
class Finding:
    message_id: int
    reason: str
    excerpt: str

    def __str__(self) -> str:
        return f"#{self.message_id} {self.reason}: {self.excerpt[:70]!r}"


def scan(rows: list[dict]) -> list[Finding]:
    """Rows that should not survive into a future prompt.

    `rows` are message dicts in id order, as stored: id, role, content,
    tool_calls, name.
    """
    findings: list[Finding] = []
    tools_this_turn: list[str] = []

    for i, row in enumerate(rows):
        role, content = row.get("role"), (row.get("content") or "")

        if role == "user":
            tools_this_turn = []
            # A user turn with no assistant answer after it means the turn died
            # before the reply was persisted. Left in place, the next turn sees
            # two user messages in a row and answers the older one.
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            if nxt is None or nxt.get("role") == "user":
                findings.append(Finding(row["id"], "unanswered turn", content))
            continue

        if role == "tool":
            if row.get("name"): tools_this_turn.append(row["name"])
            continue

        # assistant
        if row.get("tool_calls"):
            tools_this_turn.extend(_names(row["tool_calls"]))
        if not content.strip():
            continue
        if _degenerate(content):
            findings.append(Finding(row["id"], "degenerate output", content))
        elif (claim := guard.fabricated_action(content, tools_this_turn)):
            findings.append(Finding(row["id"], f"fabricated {claim!r}", content))
        # The mirror case, and the one this scan missed for a day: claiming to
        # have looked and found nothing, having never looked. `agent.reply()`
        # has blocked these at write time since the guard landed, but everything
        # written *before* that stayed — eight "I couldn't find X" replies sat in
        # one history and answered every song request that way, while a sweep
        # reported the history clean because it only looked for the success
        # shape. A detector that catches half a failure mode reports the other
        # half as healthy.
        elif (claim := guard.fabricated_failure(content, tools_this_turn)):
            findings.append(Finding(row["id"], f"fabricated failure {claim!r}", content))

    return findings


def _names(tool_calls) -> list[str]:
    """Tool names out of the stored tool_calls blob, whatever shape it took."""
    import json
    if isinstance(tool_calls, str):
        try: tool_calls = json.loads(tool_calls)
        except (ValueError, TypeError): return []
    if not isinstance(tool_calls, list): return []
    out = []
    for call in tool_calls:
        if isinstance(call, dict):
            fn = call.get("function") or {}
            name = fn.get("name") if isinstance(fn, dict) else None
            if name or call.get("name"): out.append(name or call["name"])
    return out


def trim(rows: list[dict]) -> dict[int, str]:
    """Stored replies whose learned sign-off should be cut, id → new content.

    Separate from `scan` because the verdict is different: these messages are
    true and worth keeping, they just end in a tic that teaches the next reply
    to end the same way. "How can I assist you further today, Wandile?" closed
    three consecutive replies — a banned phrase and the wrong form of address,
    reinforcing itself out of history while the rule sat unread in the bundle.
    """
    edits: dict[int, str] = {}
    for row in rows:
        if row.get("role") != "assistant":
            continue
        content = row.get("content") or ""
        cut = guard.strip_filler(content)
        if cut != content:
            edits[row["id"]] = cut
    return edits


async def sweep(user: str, dry_run: bool = False) -> list[Finding]:
    """Scan one user's history; delete what it finds unless dry_run."""
    rows = await db.raw_messages(user)
    findings = scan(rows)
    if (edits := trim(rows)) and not dry_run:
        # Trim before deleting: the ids came from `rows`, and deleting first
        # would leave this writing to rows that are no longer there.
        await db.rewrite_messages({k: v for k, v in edits.items()
                                   if k not in {f.message_id for f in findings}})
        log.info("hygiene[%s] trimmed the sign-off from %d reply/replies",
                 user, len(edits))
        from . import agent
        agent._HISTORIES.pop(user, None)
    if findings and not dry_run:
        await db.delete_messages([f.message_id for f in findings])
        # Deleting an assistant reply can orphan the user turn it answered, which
        # is itself a finding — so settle, rather than leaving a fresh problem.
        again = scan(await db.raw_messages(user))
        if again:
            await db.delete_messages([f.message_id for f in again])
            findings += again
        # The RAM cache is a write-through copy of these rows; leaving it alone
        # would keep every deleted message in the prompt until the process
        # restarts, which is the whole problem this exists to solve.
        from . import agent
        agent._HISTORIES.pop(user, None)
    for f in findings:
        log.info("hygiene[%s] %s%s", user, "would drop " if dry_run else "dropped ", f)
    return findings


async def sweep_all(dry_run: bool = False) -> dict[str, list[Finding]]:
    return {user: found for user in await db.all_user_keys()
            if (found := await sweep(user, dry_run))}
