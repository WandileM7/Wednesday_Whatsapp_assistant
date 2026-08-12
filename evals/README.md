# evals

Scripted conversations run against a **real model**, graded deterministically.

```bash
python -m evals                                   # current OLLAMA_MODEL
python -m evals --repeat 5                        # pass RATE per case — read this first
python -m evals --model llama3.1:8b               # one override
python -m evals --compare qwen2.5:3b qwen2.5:7b --repeat 5
python -m evals --tags persona,routing -v
python -m evals --ids identity                    # substring match on case ids
```

## Read `--repeat` before trusting any number

A small model's output varies run to run. Measured on `qwen2.5:3b`, one case
passed in isolation and failed ninety seconds later on the same prompt:

```
no-filler     . x . . x   3/5
brevity       . . . x .   4/5
play-a-song   . . . . .   5/5
```

So a single pass/fail cannot detect a change smaller than that variance — which
is most changes. Two model comparisons in this repo were reported as "15/16 vs
15/16" off single runs, and both differences were inside the noise.

With `--repeat N` each case reports `passes/N` and the summary carries two
numbers that answer different questions:

- **cases stable** — how much of the suite is reliable (`n/n` every time)
- **attempts** — how often it holds overall

A case at 3/5 is neither a pass nor a failure, and reporting it as either is how
noise gets mistaken for a result. Exit code is 0 only when every case is stable,
so a flaky case fails CI — which is correct: intermittent is a defect.

It needs an Ollama with the models pulled, which is why it is not part of
`pytest`.

## Why this exists separately from `tests/`

`tests/test_agent_loop.py` already runs the agent against a scripted fake
Ollama. That proves the *machinery* is correct — tool hops, approval gating,
history slicing — and it is hermetic and fast.

It cannot tell you whether the assistant is any **good**. Persona adherence,
tool routing, memory recall and surface discipline are properties of the model
plus the prompt, and measuring them needs real inference. Every fix in this
repo's prompt layer was previously judged by sending a message and reading the
reply; this replaces that with a number.

## What it drives

The real `agent.stream_reply()` path: the OKF bundle, `okf/user.md`, retrieved
memories, the per-surface note, and the tool loop.

Two things are swapped out:

- **A throwaway database** (`eval_wednesday.db`, deleted on exit). Evals must
  never touch the live conversation — an eval turn landing in your real history
  is exactly the kind of stale state that caused the phantom "system check".
- **Tool execution.** The stubs in `run.py` record which tool the model reached
  for and return plausible output. We are measuring *tool choice*, and the suite
  must not depend on Google being linked — or send anything.

## Graders

Deterministic by design — no LLM judge. A judge needs a second model, which on a
RAM-constrained host is the same contention that makes background calls return
500, and its own drift becomes indistinguishable from the drift you are trying
to measure. Everything in `graders.py` is a regex, a count or a set membership,
so a score change means the assistant changed, not the ruler.

## Cases

Every case in `cases.py` carries a `why` recording the incident it defends
against. They are regressions, not hypotheticals:

| Tag | Defends against |
|---|---|
| `identity` | answering "Hi Wednesday" with "Hi Wednesday" — the model reading its own name as the user's |
| `persona` | "How can I assist further?" closing every reply; three-paragraph answers |
| `surface` | markdown rendering as literal asterisks in a message bubble; URLs read aloud over Wyoming |
| `routing` | reaching for a tool during banter, or narrating "let me check" |
| `memory` | failing to recall a stored fact; confabulating one that was never stored |
| `continuity` | answering an older, unanswered question instead of the one just asked |
| `safety` | obeying an instruction quoted inside untrusted content |

Add a case when something goes wrong, with the `why` filled in. Delete one when
the reason stops applying.
