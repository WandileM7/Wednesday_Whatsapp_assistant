"""Run the eval suite against a real model and print a scorecard.

    python -m evals                                  # current OLLAMA_MODEL
    python -m evals --model llama3.1:8b              # one override
    python -m evals --compare qwen2.5:3b llama3.1:8b # side by side
    python -m evals --tags persona,routing -v

This drives the real `agent.stream_reply` path — the OKF bundle, memories, the
surface note, the tool loop — against real inference. That is the point: the
deterministic fake-Ollama tests in tests/test_agent_loop.py already prove the
loop is wired correctly, and cannot tell you whether the model is any good.

Tool *execution* is stubbed. We want to measure which tools the model reaches
for, not send mail, and the eval must not depend on Google being linked.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import time

# Must precede the backend import: settings and the db engine bind at module
# load, and evals must never touch the live conversation.
_DB = "./eval_wednesday.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["VECTOR_DB_PATH"] = "./eval_wednesday-vectors.db"
os.environ["API_TOKEN"] = ""

from backend import agent, db, markers          # noqa: E402
from backend.config import settings             # noqa: E402
from backend.tools import REGISTRY              # noqa: E402

from .cases import Case, select                 # noqa: E402

# The configured models, captured before any --model override rewrites them, so
# each case can be reset to configuration and then have only the one knob it
# names pointed at the model under test.
_BASELINE = {"ollama_model": settings.ollama_model,
             "ollama_model_utility": settings.ollama_model_utility}

GREEN, RED, DIM, YELLOW, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[2m", "\033[33m", "\033[1m", "\033[0m")

# Enough shape that the model can carry on to a natural reply, without needing a
# linked account. Anything unlisted gets the generic line.
STUBS = {
    "calendar_list_events": "No events scheduled today.",
    "gmail_search": "No unread mail.",
    "web_search": "1. Cape Town forecast — 19°C, partly cloudy.",
    "fetch_page": "Cape Town: 19°C, partly cloudy, light southeasterly wind.",
    "system_status": "CPU 12%, memory 46%, all services up.",
}


def _install_tool_stubs(recorder: list[str]) -> None:
    for name, spec in REGISTRY.items():
        async def stub(_name=name, **kwargs):
            recorder.append(_name)
            return STUBS.get(_name, f"(eval stub) {_name} returned no data.")
        spec["fn"] = stub


async def _run_case(case: Case, user: str) -> tuple[str, list[str], list[str], dict]:
    await agent.reset(user)
    if case.memories:
        await db.add_memories(user, case.memories)
    tools: list[str] = []
    _install_tool_stubs(tools)

    # A background pass rather than a conversation: memory consolidation, which
    # has no reply to grade. The action hands back the text the graders read
    # (the fact store afterwards) plus whatever structured result they need.
    if case.action:
        text, extra = await case.action(user)
        return text, tools, [text], extra

    # Every reply, not just the last: some properties are only visible across
    # turns — answering the same question twice with the same sentence is the
    # measurable half of "sounds robotic".
    replies: list[str] = []
    for turn in case.turns:
        # agent.reply(), not stream_reply(): this is the path every channel uses,
        # and it carries the deterministic injection backstop. Driving the stream
        # directly measured something no user ever reaches.
        replies.append(markers.strip(await agent.reply(user, turn, surface=case.surface)).strip())
    return (replies[-1] if replies else ""), tools, replies, {}


async def _attempt(case: Case, user: str) -> tuple[bool, list, str, str | None, float]:
    t0 = time.monotonic()
    try:
        reply, tools, replies, extra = await _run_case(case, user)
        err = None
    except Exception as exc:                           # a crash is a failure, not a stop
        reply, tools, replies, extra, err = "", [], [], {}, f"{type(exc).__name__}: {exc}"
    secs = time.monotonic() - t0
    results = [] if err else [chk(reply, {"tools": tools, "case": case,
                                          "replies": replies, **extra})
                              for chk in case.checks]
    ok = bool(results) and all(r.ok for r in results)
    return ok, results, reply, err, secs


async def _run_model(model: str | None, cases: list[Case], verbose: bool,
                     repeat: int) -> dict:
    """Score every case. `model` of None means "use the configured models".

    That distinction matters now that a case can name which knob it exercises:
    with no override, a conversational case runs on OLLAMA_MODEL and a
    consolidation case on OLLAMA_MODEL_UTILITY, which is what production does.
    Overriding with the chat model for both would report a score for a model the
    background pass never calls.
    """
    label = model or (f"{_BASELINE['ollama_model']} "
                      f"(+{_BASELINE['ollama_model_utility']} utility)")
    print(f"\n{BOLD}model: {label}{OFF}  ({len(cases)} cases × {repeat})")
    rows = []
    for case in cases:
        for field, value in _BASELINE.items():
            setattr(settings, field, value)
        if model:
            setattr(settings, case.model_setting, model)
        attempts = [await _attempt(case, f"eval:{case.id}") for _ in range(repeat)]
        passes = sum(1 for ok, *_ in attempts if ok)
        avg = sum(a[4] for a in attempts) / len(attempts)
        # Show the first failure: with repeats, printing all of them buries the
        # scoreboard, and the first is as representative as any.
        worst = next((a for a in attempts if not a[0]), attempts[0])
        rows.append((case, passes, repeat, worst, avg))

        rate = f"{passes}/{repeat}"
        colour = GREEN if passes == repeat else (RED if passes == 0 else YELLOW)
        mark = f"{GREEN}pass{OFF}" if passes == repeat else f"{colour}FLAKY{OFF}" \
            if passes else f"{RED}FAIL{OFF}"
        print(f"  {mark:<16} {colour}{rate:>5}{OFF}  {case.id:<42} {DIM}{avg:5.1f}s{OFF}")
        if passes < repeat:
            _, results, reply, err, _ = worst
            if err: print(f"        {RED}{err}{OFF}")
            for r in results:
                if not r.ok:
                    print(f"        {RED}✗{OFF} {r.label}"
                          + (f" {DIM}— {r.detail}{OFF}" if r.detail else ""))
            print(f"        {DIM}reply: {reply[:200]!r}{OFF}")
        elif verbose:
            print(f"        {DIM}reply: {worst[2][:200]!r}{OFF}")

    stable = sum(1 for _, p, r, *_ in rows if p == r)
    got = sum(p for _, p, *_ in rows)
    total = len(rows) * repeat
    pct = (got / total * 100) if total else 0
    colour = GREEN if stable == len(rows) else (YELLOW if pct >= 70 else RED)
    # Two numbers because they answer different questions: how much of the suite
    # is reliable, and how often it holds. A case at 3/5 is neither pass nor fail
    # and reporting it as either is how a change smaller than the noise gets
    # mistaken for a result.
    print(f"  {colour}{stable}/{len(rows)} cases stable · {got}/{total} attempts ({pct:.0f}%){OFF}")
    return {"model": label, "stable": stable, "cases": len(rows),
            "got": got, "total": total, "rows": rows, "repeat": repeat}


def _compare(runs: list[dict]) -> None:
    print(f"\n{BOLD}comparison{OFF}")
    ids = [c.id for c, *_ in runs[0]["rows"]]
    width = max(len(i) for i in ids) + 2
    header = "  " + "case".ljust(width) + "".join(r["model"].ljust(20) for r in runs)
    print(DIM + header + OFF)
    for idx, cid in enumerate(ids):
        cells = ""
        for run in runs:
            _, passes, repeat, *_ = run["rows"][idx]
            colour = GREEN if passes == repeat else (RED if passes == 0 else YELLOW)
            cells += f"{colour}{passes}/{repeat}{OFF}".ljust(29)
        print("  " + cid.ljust(width) + cells)
    print()
    for run in runs:
        pct = run["got"] / run["total"] * 100 if run["total"] else 0
        print(f"  {run['model']:<24} {run['stable']}/{run['cases']} stable · "
              f"{run['got']}/{run['total']} ({pct:.0f}%)")
    if runs[0]["repeat"] == 1:
        print(f"\n  {YELLOW}one run per case — a difference of one case is inside the "
              f"noise on a small model. Use --repeat 5 before trusting a delta.{OFF}")


async def main() -> int:
    ap = argparse.ArgumentParser(prog="evals")
    ap.add_argument("--model", help="override OLLAMA_MODEL for this run")
    ap.add_argument("--compare", nargs="+", metavar="MODEL",
                    help="run the suite against each model and diff the results")
    ap.add_argument("--tags", help="comma-separated: persona,routing,memory,surface,identity,safety,continuity")
    ap.add_argument("--ids", help="comma-separated substrings of case ids")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="run each case N times and report a pass rate. A small model's "
                         "output varies run to run, so a single pass/fail cannot detect a "
                         "change smaller than that variance — use 5 before trusting a delta.")
    ap.add_argument("-v", "--verbose", action="store_true", help="print passing replies too")
    args = ap.parse_args()

    cases = select(args.tags.split(",") if args.tags else None,
                   args.ids.split(",") if args.ids else None)
    if not cases:
        print("no cases matched"); return 2

    await db.init()
    # None means "whatever is configured", which lets each case run on the knob
    # it names instead of forcing the chat model onto a pass that never calls it.
    models = args.compare or [args.model]
    print(f"{DIM}ollama: {settings.ollama_host}{OFF}")

    runs = [await _run_model(m, cases, args.verbose, max(1, args.repeat)) for m in models]
    if len(runs) > 1:
        _compare(runs)

    for path in pathlib.Path(".").glob("eval_wednesday*.db*"):
        path.unlink(missing_ok=True)
    return 0 if all(r["stable"] == r["cases"] for r in runs) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
