# Working on Wednesday

A self-hosted personal assistant (FastAPI + Ollama) reachable from a browser orb,
WhatsApp, iMessage, email and Home Assistant. One persona, one memory, many
surfaces. Everything runs locally by default; a hosted OpenAI-compatible endpoint
is optional and local is always the fallback.

The single most important thing to understand: **this codebase is tuned for a 7B
model running on a slow box.** Most of what looks like over-engineering is a
countermeasure for one of those two facts, and the reasoning is written down next
to the code. Read the docstring before changing the function.

## Commands

```bash
.venv/bin/python -m pytest -q          # 600+ tests, ~10s. Run before every handoff.
.venv/bin/python -m pytest tests/test_guard.py -q
python -m evals                        # real model, deterministic grading
python -m evals --repeat 5 --tags persona
python -m evals --compare qwen2.5:3b qwen2.5:7b --repeat 5
uvicorn backend.main:app --reload      # :8000
cd frontend && npm run dev             # :1420
```

`pytest` is `asyncio_mode = auto` — async tests need no decorator. There is no
linter or formatter configured; match the surrounding style by hand.

**Evals are not the test suite.** They call a real model, so a single pass/fail
cannot detect a change smaller than run-to-run variance. Any claim about persona,
routing or safety behaviour needs `--repeat` and a rate, not one run. Unit tests
cover the deterministic half; evals cover whether the model actually complies.

## House style

Docstrings and comments carry the *reasoning*, not the mechanics — what was
measured, what was tried and rejected, and what breaks if you undo it. Numbers
are real and taken on this hardware. This is the repo's most distinctive quality
and the reason it is maintainable at all, so:

- Explain **why**, with the measurement or the observed failure that motivated it.
- Name the alternative you rejected and why, when one exists.
- Do not rewrap, condense or "clean up" existing prose docstrings. They are the
  design record; a shorter version is a worse one.
- Prefer a comment that says what went wrong last time over one that restates the
  code.

## Invariants that break silently

These have all cost real debugging time. None of them fail loudly.

1. **Prompt block order in `agent._context()` is load-bearing.** Ollama caches
   the prefix and re-evaluates from the first differing token. Stable blocks
   first, volatile last. Prefill measures 71–86 tok/s on the iGPU and 6.2 tok/s
   on the CPU fallback, so moving a per-channel block up the prompt threw away
   ~2800 cached tokens on every turn. Do not reorder.
2. **The two backends encode tool calls incompatibly.** OpenAI-compatible sends
   `arguments` as a JSON *string*; Ollama wants an object. `llm._sanitize` and
   `llm._for_ollama` are mirrors of each other. A hosted turn writes history that
   the local fallback 400s on — which breaks the fallback exactly when it is
   needed. Touch history shape and you must touch both.
3. **Sanitise before persisting, not after.** `agent._persistable` runs on the
   way to the database. Cleaning only what the user sees leaves the fabrication
   on disk, where the next turn reads it as house style and repeats it. History
   is the part that compounds.
4. **`ollama ps` lies about the backend.** It reports "100% CPU" even when all
   layers are on the GPU. Use `/doctor` → `local_speed` (measured from Ollama's
   own counters via `turncost`), or grep the server log for "offloaded N/N".
   ~70 tok/s prefill is the iGPU, ~6 is the CPU fallback.
5. **`OLLAMA_MODEL_UTILITY` must differ from `OLLAMA_MODEL`.** Sharing one model
   makes every background call evict the interactive prompt's KV cache, costing
   ~170s of re-prefill per turn. This was the highest-impact finding in
   `E2E_REPORT.md` and it is now a populated default — keep it populated.
6. **Markers are spoken, never shown.** `markers.strip()` for display. The
   WebSocket path streams, so it cannot clean text after the fact — hence
   `guard.streamable()`, which holds back any trailing fragment that could still
   become a service-desk sign-off.
7. **`okf/persona.md` examples are parsed, not just read.** `okf._EXAMPLE`
   extracts `User:` / `You:` pairs into the rotating register block and strips
   them from the prose. Write them in that exact form or they silently become
   narration — which teaches the model to fabricate rather than to sound right.
8. **Tests read your real `.env`.** So the defaults a fresh install gets are the
   one configuration nothing exercises; four real bugs lived there. When adding a
   setting that names a model, a voice or anything installable, add it to
   `tests/test_config_truth.py`.

## Small-model realities

A 7B model does things a frontier model does not, and the defence is always code,
never a better prompt:

- **It fabricates completed actions.** "Playing Africa by Toto" with no Spotify
  call. `guard.fabricated_action` cross-checks claims against tools that actually
  ran; `guard.fabricated_failure` catches the mirror image ("I couldn't find it",
  having never looked).
- **It invents memories.** `memory._grounded` requires a fact's content words to
  appear in the user's own text.
- **It "curates" when asked to edit.** `memory.consolidate` originally asked for
  a rewritten fact list and got back half the store — the model read "shorter"
  as "pick the interesting ones", losing a third of the subjects. It now asks
  only for the *numbers to delete*, so keeping is structural and no new text can
  enter. Measured, not guessed: the block comment records both designs. When a
  small model has to edit a structure, give it the narrowest possible output.
- **It recites examples.** A worked example in a safety prompt got answered
  *about* instead of applied. `guard.note()` describes, never demonstrates.
- **Instructions in the bundle are diluted.** A static rule 2000 tokens up the
  prompt scored 0/3 on safety evals; the same rule as a system message sitting
  against the offending turn worked. Proximity beats phrasing.

So: if a behaviour matters, assert it in code and test it. A prompt line is a
hint, not a guarantee.

## Layout

Only the parts that aren't obvious from the filename:

- `backend/agent.py` — the turn loop: history slice, context assembly, tool hops,
  approval gating, persistence. The biggest and most careful file here.
- `backend/okf.py` — the system prompt is assembled from `okf/*.md` in index link
  order, hot-reloaded on mtime change. Persona edits land without a restart.
- `backend/toolrouter.py` — which tool schemas this turn gets. Schemas are prompt
  tokens on every call, so adding a tool is not free.
- `backend/turncost.py` — measures local throughput, estimates a turn's cost,
  decides hosted vs local per turn.
- `backend/guard.py` — injection detection *and* output containment (fabrication,
  sign-offs, streaming holdback).
- `backend/vecstore.py` — the hybrid index is a disposable sidecar file, rebuilt
  from the `memories` table on demand.
- `okf/` — persona, style, routing, trust. Editing these changes her behaviour
  more than editing Python will.
- `docs/ROADMAP.md` — what's deliberately absent and why (e.g. third-party
  skills, for supply-chain reasons; MCP is the sanctioned extension point).

## Don'ts

- Don't vendor third-party code. This repo is MIT; take the idea and reimplement
  it in this codebase's idiom, with its reasoning written down.
- Don't add a tool without checking what its schema costs the prompt.
- Don't loosen a guard because it looks paranoid. Each pattern has an observed
  failure behind it; find it before deciding it's dead weight.
- Don't commit or push unless asked.
