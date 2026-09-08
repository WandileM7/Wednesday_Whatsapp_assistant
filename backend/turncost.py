"""What this turn will cost locally, and therefore who should answer it.

With LLM_BASE_URL set, *every* turn currently goes hosted — including "thanks",
"ok" and "night". That is the wrong default in three directions at once: it
spends a metered tier (Groq free is 12k tokens/min) on messages a 8B model
answers instantly, it sends conversation off-box that never needed to leave,
and it gives up the local prefix cache that `_context` is carefully ordered to
protect. So the useful question is not "which model is smarter" — Wednesday has
two backends split by latency and cost, not by size — but **would local have
been fast enough here?**

That question is answerable in seconds, so the estimate is in seconds, and the
knob is a latency budget rather than a difficulty threshold: answer locally when
we think it lands inside ROUTE_LATENCY_BUDGET, otherwise spend the hosted call.

The estimate needs the box's real throughput, and that is exactly the number
nobody can state — `ollama ps` reports "100% CPU" even when all 29 layers are
on the Arc iGPU, and the SYCL backend can fail to load silently between one
restart and the next, moving prefill from ~75 tok/s to ~6 tok/s. Configuration
cannot know it. So we don't configure it: Ollama's final streaming chunk
carries its own counters, and `observe()` reads the rate back off every local
turn. `prompt_eval_count` is the tokens it actually evaluated — the ones the
prefix cache did not serve — so the same chunk also measures how well the cache
is holding, which is the other half of the cost and the thing route_tools
trades away.

Two decisions worth naming, because both are load-bearing:

  - The seed rates are optimistic. The router only learns the local rate from
    turns it sends local, so a pessimistic seed is self-fulfilling: assume the
    box is slow, route everything hosted, never sample, stay wrong forever. An
    optimistic seed is self-correcting — the first genuinely slow turn lands a
    real measurement and the estimate follows it down within a few turns.
  - The decision has hysteresis, not a threshold. The backends do not sound
    alike: hosted runs at llm_temperature with no min_p available, local runs
    hot with a probability floor (see config.py). Flipping per turn changes her
    voice between one message and the next, which is worse than being slow.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from collections import deque
from dataclasses import dataclass

from . import toolrouter
from .config import settings

log = logging.getLogger(__name__)

# --- measured throughput -----------------------------------------------------

_WINDOW = 12                       # turns kept per statistic

# Assumptions, replaced by measurement within a dozen local turns. Every one of
# them leans fast, which is the docstring's point and not an accident: a seed
# that guesses slow routes everything hosted, collects no samples, and never
# discovers it was wrong.
#
# Prefill is the figure config.py records for the Arc iGPU (71-86 tok/s). Decode
# is measured nowhere and is genuinely a guess — it is memory-bandwidth bound
# and lands well under prefill; the first real turn overwrites it. The miss
# fraction comes from the one real datapoint in _context's notes: a warm turn
# evaluated 36 tokens and reused 2781, so ~1%. It is seeded well above that
# because turns immediately after a restart are cold, and because route_tools
# makes a subject change invalidate the schema block near the front.
_SEED_PREFILL = 75.0               # tok/s evaluating the prompt
_SEED_DECODE = 18.0                # tok/s generating the reply
_SEED_MISS = 0.10                  # fraction of the prompt the cache misses

_PREFILL: deque[float] = deque(maxlen=_WINDOW)
_DECODE: deque[float] = deque(maxlen=_WINDOW)
_MISS: deque[float] = deque(maxlen=_WINDOW)


def observe(prompt_tokens: int, final: dict) -> None:
    """Record what a finished local turn actually cost, from Ollama's counters.

    Durations are nanoseconds. A fully cached prompt reports prompt_eval_count
    0 (or omits the duration), which is a real and useful miss-ratio sample even
    though it yields no rate — so the two are recorded independently.
    """
    evaluated = final.get("prompt_eval_count")
    prefill_ns = final.get("prompt_eval_duration")
    decoded = final.get("eval_count")
    decode_ns = final.get("eval_duration")
    if evaluated is not None and prompt_tokens > 0:
        _MISS.append(min(1.0, evaluated / prompt_tokens))
    if evaluated and prefill_ns:
        _PREFILL.append(evaluated / (prefill_ns / 1e9))
    if decoded and decode_ns:
        _DECODE.append(decoded / (decode_ns / 1e9))


def rates() -> tuple[float, float, float]:
    """Prefill tok/s, decode tok/s, prompt cache-miss fraction.

    Medians, not means: loading a cold model puts one enormous outlier in the
    window and a mean would carry it for a dozen turns after the box recovered.
    """
    return (statistics.median(_PREFILL) if _PREFILL else _SEED_PREFILL,
            statistics.median(_DECODE) if _DECODE else _SEED_DECODE,
            statistics.median(_MISS) if _MISS else _SEED_MISS)


def measured() -> bool:
    """True once the estimate rests on real samples rather than the seed."""
    return bool(_PREFILL or _DECODE)


# --- the estimate ------------------------------------------------------------

# Wednesday answers in one to three spoken-style sentences by default, so a
# short reply is the base case and only an explicit ask moves it. A keyword list
# earns its keep here and nowhere else in this module: reply length is the half
# of the cost that is invisible in the prompt, so it is the half that has to be
# guessed from the request.
_LONG_FORM = re.compile(
    r"\b(explain|walk me through|talk me through|summar\w+|rundown|brief me|"
    r"list (?:all|every|the)|write|draft|compose|compare|break down|"
    r"step by step|in detail|tell me (?:about|everything))\b", re.I)

_SHORT_REPLY = 70                  # tokens; the house style
_LONG_REPLY = 320                  # tokens; an explicit ask for more

# How far under budget a turn must land before she moves back to local. Below
# 1.0 by definition — the gap between the two is the hysteresis band that stops
# her voice flipping backend to backend mid-conversation.
_RETURN_RATIO = 0.5


@dataclass(frozen=True)
class Estimate:
    """What a local answer to this turn is expected to cost."""

    prompt_tokens: int             # everything we send: context + tool schemas
    prefill_tokens: int            # of those, what the cache will not serve
    decode_tokens: int             # expected reply length
    hops: int                      # model rounds, tool calls included
    seconds: float

    def __str__(self) -> str:
        hops = f"{self.hops} hop" + ("" if self.hops == 1 else "s")
        return (f"{self.seconds:.1f}s local "
                f"({self.prompt_tokens}t prompt, {self.prefill_tokens}t to evaluate, "
                f"{self.decode_tokens}t reply, {hops}"
                f"{'' if measured() else ', unmeasured'})")


def prompt_tokens(messages: list[dict], tools: list[dict] | None) -> int:
    """Tokens in one request. Mirrors agent._est_tokens' 4-chars-per-token rule,
    and counts the tool schemas — routed or not they are thousands of tokens of
    prompt, and leaving them out would understate every turn that carries them.
    """
    total = sum((len(m.get("content") or "")
                 + len(json.dumps(m.get("tool_calls") or []))) // 4 + 8
                for m in messages)
    return total + len(json.dumps(tools or [])) // 4


def estimate(messages: list[dict], tools: list[dict] | None, user_text: str) -> Estimate:
    """Predict the wall-clock cost of answering this turn on Ollama."""
    prefill_rate, decode_rate, miss = rates()
    prompt = prompt_tokens(messages, tools)

    # A matched intent group means a tool call is likely, and a tool call means
    # a second round: the result is appended and the whole thing goes back. Two
    # is the cap — deeper chains happen, but estimating their depth is guesswork
    # and over-predicting sends cheap turns hosted for no reason.
    hops = 2 if toolrouter.groups(user_text) else 1

    prefill = prompt * miss
    if hops > 1:
        # The second round re-sends everything plus the tool result. Ollama has
        # just evaluated the rest of it, so the cache serves that part and only
        # the result is new work — clamped to tool_result_chars by _exec_tool.
        # This is usually the single biggest term, and the honest reason a turn
        # that calls a tool is worth spending a hosted call on.
        prefill += settings.tool_result_chars / 4

    decode = _LONG_REPLY if _LONG_FORM.search(user_text or "") else _SHORT_REPLY
    seconds = prefill / prefill_rate + decode / decode_rate
    return Estimate(prompt_tokens=prompt, prefill_tokens=round(prefill),
                    decode_tokens=decode, hops=hops, seconds=round(seconds, 2))


# --- the decision ------------------------------------------------------------

_ON_HOSTED: dict[str, bool] = {}   # per channel, so one user's flip is their own


def prefer_hosted(channel: str, est: Estimate) -> bool:
    """Whether to spend a hosted call on this turn.

    Asymmetric on purpose: a turn has to be clearly *over* budget to move her
    off local, and clearly *under* it to bring her back. A single threshold
    would flap around the boundary and change her voice on every other message
    — the same stickiness toolrouter applies to tool groups, for the same
    reason and at a more audible cost.
    """
    budget = settings.route_latency_budget
    floor = budget * _RETURN_RATIO if _ON_HOSTED.get(channel) else budget
    on = est.seconds > floor
    _ON_HOSTED[channel] = on
    return on


def forget(channel: str) -> None:
    """Drop a channel's stickiness — a reset should not inherit a backend."""
    _ON_HOSTED.pop(channel, None)
