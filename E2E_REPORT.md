# Wednesday — end-to-end test report

**Date:** 2026-07-23 · **Branch:** `claude/refactor-cross-platform-app-JnoN1` @ `c511824`
**Result:** ~163 checks across 10 suites. Almost everything that could be tested without
outward-facing side effects works; one background feature (the rolling summary) is broken on
this hardware. **7 findings**, 4 of them worth acting on.

> **Update — all 7 findings fixed.** Changes applied across `backend/{markers,tools/builtin,
> config,agent,memory,main,voice}.py`, `frontend/src/components/Chat.jsx`, `.env`, and
> `.env.example`. Each fix was re-verified (marker strip, `web_search`→`fetch_page` chain live,
> WAV header, RAM-trim-on-summary-failure, WS survives a failed turn, refactored `/ws` happy-path
> stream). The existing 40-test suite and the frontend build both still pass. Details inline
> below (§3.1–§3.7). One follow-up for fresh clones: a new checkout should also `ollama pull
> llama3.2:3b` (the recommended utility model) — noted in the README quick-start otherwise.

---

## 1. How this was run — nothing destructive

Every suite ran against throwaway copies. The live system was never written to.

| Isolation | What it protected |
|---|---|
| `DATABASE_URL` → temp copy of `wednesday.db` | real DB — verified unchanged: 53,248 bytes, mtime still `2026-07-19 21:40:14` |
| `OKF_DIR` → temp copy of `okf/` | real persona + skills — `okf/skills/` still contains only `morning-briefing.md`, no `proposals/` written |
| Backend on `:8001` | anything on the normal `:8000` |
| Fake gateway on `:3999` + real gateway in **mock mode** on `:3998` | real WhatsApp — `ENABLE_REAL_WHATSAPP` unset means no Baileys socket is ever opened; `whatsapp-service/session/` unchanged (`Jul 19 17:50`) |
| Google + Spotify unlinked in the test DB | no mail sent, no calendar events, no playback changed |
| Approval-gated write tools were **denied**, never approved | same |
| `run_code` probed in a throwaway `--network none` container | the host |

`git status` was clean at the start and at the end. All test services have been shut
down; ports 8001/3998/3999 are free.

**Deliberately not tested** — would have required real outward-facing effects:

- sending a real WhatsApp message / linking a real device
- live IMAP + SMTP email (no credentials configured; routing logic tested instead)
- Gmail / Calendar / Tasks API calls (Google not linked; unlinked-error path tested)
- Spotify playback mutators `play/pause/next/queue` (would control real playback)
- browser-only features — orb rendering, hands-free VAD, wake word, gesture control,
  voice barge-in (build-verified and event-contract-verified only; these need a real
  browser with mic + camera)

---

## 2. Results

| Suite | Checks | Result |
|---|---|---|
| Existing `pytest` suite | 40 | **40 pass** |
| Voice pipeline — Fish TTS, Piper, ogg/opus, whisper | 7 | **7 pass** |
| Tools + modules, called directly | 55 | **54 pass, 1 fail** (§3.1) |
| HTTP surface — auth, doctor, voice, OAuth | 15 | **15 pass** |
| Sandboxed `run_code` | 4 | **4 pass** |
| WebSocket chat | 19 | **19 pass** ¹ |
| WhatsApp channel (fake gateway) | 10 | **10 pass** |
| WhatsApp real-gateway contract (mock mode) | 1 | **1 pass** (revealed §3.5) |
| Proactive heartbeat | 3 | **3 pass** |
| Rolling conversation summary | 6 | **2 pass, 4 fail** (§3.7) |
| Frontend build + asset serve | 3 | **3 pass** |

¹ `scheduler/proactive-push-to-whatsapp` first reported FAIL — that was my harness reading
the gateway's log file before the write landed. Verified directly afterwards: the backend
logged `POST /api/sendText 200` and the gateway recorded
`{"chatId":"27831234567@…","text":"⏰ Reminder: drink water"}`. Dual-channel delivery works.

### What was proven working, end to end

- **Web chat** — token auth (and rejection), streamed deltas, persistence, `reset`, empty input
- **Voice** — Fish Audio TTS, Piper fallback, whisper STT, WAV→ogg/opus, audio + transcript over the socket, `/voice/tts`, `/voice/stt`
- **Tools** — all 22 registered; time, web search, reminders (set/list/cancel/recurring/past-date/bad-ISO), skills, conversation search, sandboxed code execution with network isolation enforced
- **Approvals** — the model's `gmail_send` call paused for consent over the wire, the denial was passed back to the model as feedback, and no blanket grant was recorded
- **Memory** — background extraction pulled 2 durable facts from one exchange and recalled them in a later turn (the rolling *summary* is a separate story — §3.7)
- **Proactivity** — a due reminder reached both an open browser tab *and* the owner's WhatsApp; recurring jobs roll forward; undelivered one-shots stay pending; quiet hours and the daily cap both suppress the heartbeat
- **WhatsApp** — text round-trip, voice-note in → voice-note out (37 KB ogg/opus), dedupe, allowlist, rate limit, owner-identity sharing, per-sender history isolation, and the real gateway's `{event, payload}` contract
- **Security** — OAuth tokens encrypted at rest (verified the raw sqlite cell), one-time OAuth state rejects forged callbacks, tool output wrapped with an ignore-instructions preamble, skill proposals require a human to move the file

---

## 3. Findings

### 3.1 `fetch_page` cannot read anything `web_search` returns — BUG

`web_search` scrapes DuckDuckGo's HTML endpoint, which returns **protocol-relative redirect
wrappers**, not destination URLs:

```
//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FGaborone&rut=…
```

`fetch_page` rejects them outright:

```python
if not url.startswith(("http://", "https://")): return "Only http(s) URLs."
```

So the chain the tool description advertises — *"Use after web_search to read a promising
result"* — is broken for **every** result:

```
tool/web_search   -> 3 results (correct: Gaborone)
tool/fetch_page   -> 'Only http(s) URLs.'
```

Two defects in one: the scheme is missing, and even with `https:` prepended you'd fetch
DuckDuckGo's redirector rather than the page. **Fix:** unwrap the `uddg` query parameter in
`web_search` (`backend/tools/builtin.py`) so it emits real destination URLs.

### 3.2 Capitalised speech markers leak into user-visible text — BUG

`backend/markers.py` only matches **lowercase** tags:

```python
_MARKER = re.compile(r"\[[a-z][a-z \-]{1,30}\](?!\() ?")
```

`okf/style.md` asks for lowercase tags from a fixed list, but the model doesn't comply. A
real reply captured through the WhatsApp path this run:

```
[Hiss] Contracts befit a lawyer, not a housekeeper of the damned.
```

`[Hiss]` is both capitalised *and* an invented tag. Verified:

```
'[sighing] Fine.'  -> 'Fine.'
'[Sighing] Fine.'  -> '[Sighing] Fine.'   ← leaks
```

This hits every reader-facing surface — web chat, WhatsApp text — and Piper would read
"Hiss" aloud, since `voice.synthesize` strips with the same function. **Fix:** match the ten
allowed tags case-insensitively rather than by a lowercase character class (keeping the
`(?!\()` guard so markdown links survive).

### 3.3 A single slow turn kills the whole WebSocket — ROBUSTNESS

The WS suite died mid-run with `httpcore.ReadTimeout` from `backend/agent.py:128`. The
agent's httpx client allows a 300 s read timeout; on this hardware a cold-cache turn with a
long history exceeds it. The exception propagates out of `stream_reply`, and
`backend/main.py:162-166` closes the socket in its `finally`.

`frontend/src/components/Chat.jsx` handles `close` with `setConnected(false)` and has **no
reconnect logic** — the `useEffect` runs once. So one slow reply forces the user to reload
the page. A per-turn failure that leaves the socket open would be a much better behaviour.

### 3.4 Every interactive turn paid a ~170 s prompt re-evaluation — CONFIG (highest impact)

`OLLAMA_MODEL_UTILITY` is unset, so `memory.extract` (which runs after **every** turn) fires
a **differently-shaped** prompt at the **same** model. That evicts Ollama's KV cache for the
interactive prefix (system prompt + 22 tool schemas ≈ **2,200 tokens**), so the next user turn
re-evaluates all of it from scratch. (`_summarize` has the same shape and would compound the
effect, but it only fires occasionally — see §3.7 — so `extract` is the demonstrated culprit.)

| | latency |
|---|---|
| turn with a cold/evicted prefix | **177 s** |
| turn with the prefix cached | **15 s** |

Setting `OLLAMA_MODEL_UTILITY=llama3.2:3b` (already pulled) fixed it immediately —
background work moved to its own runner and stopped evicting the interactive cache:

| turn | before | after |
|---|---|---|
| 1 (cold) | 179 s | 252 s (one-off model load) |
| 2 | ~180 s | **54 s** |
| 3 | ~180 s | **2.7 s** |

`ollama ps` confirmed both models stay resident, so there's no reload thrash.
**Recommendation: set `OLLAMA_MODEL_UTILITY` in `.env`.** All later suites ran with it.

### 3.5 The model actually running is `qwen2.5:3b`, not the documented `llama3.1:8b` — CONFIG/DOC

`backend/config.py` defaults `ollama_model` to `qwen2.5:3b` and `.env` doesn't override it.
The README advertises `llama3.1:8b` throughout, and `.env.example` sets it.

This matters beyond documentation:

- `qwen2.5:3b` has a **4,096-token context**, against ~2,200 tokens of fixed prompt overhead
  plus `history_budget_tokens=2500` — the budget alone can over-subscribe the window.
- Quality at 3B is visibly poor. Verbatim from this run:
  - *"Hello there, grim spectre. How may I doobie you today?"*
  - "What is 2 plus 2?" → *"Twenty-four, if you're counting bunny holes."*

Tool *wiring* is proven correct, and the model did pick the right tool in all 6 tool-selection
turns — so this is model capability, not a code bug. But it's the difference between the
assistant working and being usable. Either align the README with the 3B default, or set
`OLLAMA_MODEL=llama3.1:8b` (already pulled).

### 3.7 The rolling conversation summary never completes on this hardware — BUG

`_summarize` folds messages that fall off the prompt slice into a running summary. It fires
only when ≥ `_SUMMARIZE_BATCH` (8) messages have dropped — which **never happened naturally**
across any E2E run (checked: zero `summaries` rows in every test DB, and no `summarize failed`
log line). So it was untested by the other suites; I exercised it directly.

The slice/no-op logic is correct:

```
summary/messages-fall-off-slice   PASS  40 msgs -> 14 kept, 26 dropped
summary/no-op-below-threshold     PASS  no model call when too little dropped
```

But **the summarization call itself times out** whenever it actually has work to do:

```
summary/persisted                 FAIL  httpx.ReadTimeout, 0-char summary
summary/history-truncated-in-ram  FAIL  cache not advanced (the except-branch swallows it)
```

Root cause is the same ~1 tok/s generation speed behind §3.3: the summarize prompt bundles up
to ~2,000 tokens of dropped messages, and the call exceeds the 300 s httpx read timeout in
`backend/agent.py`. The exception is caught and logged, so nothing crashes — but the summary
silently never updates, `_HISTORIES` is never truncated, and on a long conversation the RAM
cache grows unbounded (it's only ever trimmed inside the successful branch of `_summarize`).

On adequate hardware / a real utility model this likely works; on this CPU it is effectively
dead. Worth (a) a longer timeout for background calls, and (b) trimming `_HISTORIES` even when
the summary call fails, so memory doesn't grow without bound.

### 3.6 Fish Audio returns a WAV with a bogus duration header — MINOR

The WAV from Fish TTS declares a frame count implying **~48,695 seconds** for ~2 s of audio.
Playback and whisper both cope, so nothing is broken today, but anything that trusts the
header (a seek bar, a duration readout) will show nonsense.

---

## 4. Suggested order of work

1. **§3.4** — set `OLLAMA_MODEL_UTILITY`. One line, turns get ~60× faster.
2. **§3.5** — decide the model story; the 3B default is what makes replies nonsensical.
3. **§3.2** — marker leak; small regex fix, visible on every channel.
4. **§3.1** — `web_search` → `fetch_page` chain; the agent currently cannot read any page it finds.
5. **§3.3 / §3.7** — both are the same root cause (300 s timeout vs ~1 tok/s generation): don't tear down the socket on one slow turn, add frontend reconnect, lengthen the background-call timeout, and trim `_HISTORIES` even when a summary fails.
6. **§3.6** — cosmetic.

*Note: §3.3 and §3.7 largely dissolve once §3.4/§3.5 give the model a real chance to keep up; they surfaced because a 3B model with an evicted cache generates at ~1 tok/s on this CPU. Worth hardening the timeouts regardless.*
