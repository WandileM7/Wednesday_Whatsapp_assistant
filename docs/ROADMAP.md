# Wednesday → beyond OpenClaw & Hermes

Gap analysis (2026-07) against [OpenClaw](https://github.com/openclaw/openclaw) and
[Hermes Agent](https://github.com/nousresearch/hermes-agent), and the actions to close —
then pass — them. Ordered by phase; each item is scoped to this codebase.

## Where they beat us today

| Capability | OpenClaw | Hermes | Wednesday now |
|---|---|---|---|
| Memory across sessions | prefs/projects/people persist | 3-layer: skills, conversation, user model | none — `_HISTORIES` dict dies with the socket |
| Skills | ClawHub registry, Skill Cards, security scanning | self-authors skills from experience, 7-day curator | static OKF markdown bundle |
| Proactivity | heartbeat every 30 min | background curator + nudges | none — purely reactive |
| Channels | 29 (WhatsApp, Telegram, Signal, iMessage…) | 15+ incl. email, SMS, Home Assistant | 2 (web orb, WhatsApp) |
| Execution | sandboxed, remote approvals from phone | 6 terminal backends (local→Modal) | fixed tool list only |
| Identity | one assistant across channels | user model spans sessions | each WS connection is a stranger |

**Our unfair advantages to press:** fully local zero-cost stack, real-time voice orb
(streamed sentence TTS), hand tracking, WhatsApp without the Business API.

## Phase 0 — Foundation (do first; everything else builds on it)

1. **Persist conversation history** — move `_HISTORIES` out of RAM into sqlite via
   `backend/db.py` (`messages` table: channel_user, role, content, tool_calls, ts).
   Load recent history on connect; never call `reset()` on disconnect.
2. **Stable identity across channels** — replace `ws:{id(ws)}` with a real user key
   (single-user default: `wandile`), shared by web and WhatsApp so both channels are
   the same brain. This single change fixes "Wednesday forgets me every refresh."
3. **Context budget management** — history grows unbounded into a 4096-token window.
   Add token-aware trimming + a rolling summary message so long sessions degrade
   gracefully instead of silently truncating.
4. **Authentication** — backend binds `0.0.0.0` with no auth: anyone on the LAN can
   use the WS, trigger tools, and read linked Gmail. Add a bearer token on WS + HTTP,
   and a WhatsApp JID allowlist in the webhook.
5. **Ops hardening** — docker-compose healthchecks + restart policies for backend,
   Ollama, Baileys; exponential-backoff reconnect and message dedup in
   `whatsapp-service`; a `/doctor` endpoint that checks Ollama, models, tokens, disk.
6. **Test safety net** — fake-Ollama unit tests for the `agent.py` tool loop and
   sentence-segmentation in `main.py`; CI e2e smoke: boot backend, hit `/health` and
   `/voice/tts` (Piper path, no network).

## Phase 1 — Memory that compounds (Hermes parity)

7. **Memory extraction pass** — after each exchange, a cheap background LLM call
   distills durable facts (people, preferences, projects, commitments) into a
   `memories` table. Inject top-k relevant memories into the system prompt.
8. **Retrieval** — sqlite FTS5 first; upgrade to embeddings via Ollama
   (`nomic-embed-text`) when FTS relevance falls short. Both stay local and free.
9. **User model document** — a continuously-updated "who Wandile is" doc (the OKF
   bundle is the natural home) that the extraction pass amends; this is Hermes'
   user-modeling layer, but human-readable and editable.
10. **`search_conversations` tool** — let the agent query its own past chats, so
    "what did I ask you last week about the visa?" just works.

## Phase 2 — Proactivity (OpenClaw parity)

11. **Scheduler** — APScheduler (or asyncio cron) in the backend; jobs stored in
    sqlite so they survive restarts.
12. **Heartbeat** — every N minutes (configurable, default off until trusted), run a
    silent agent turn: check calendar/Gmail via existing tools, decide if anything
    warrants a WhatsApp ping. Quiet hours + max-pings-per-day guardrails.
13. **Reminder/schedule tools** — `set_reminder`, `schedule_task` tools so "remind me
    at 6" creates a job that fires back through the WhatsApp channel.
14. **Approval flow** — for consequential actions (sending email, spending money),
    the agent asks first over the active channel and waits; OpenClaw's remote
    approvals, but through channels we already have.

## Phase 3 — Skills & self-improvement (beat Hermes)

15. **Skill format** — extend OKF: a skill = markdown instructions + optional Python
    tool file, hot-loaded from `okf/skills/`. Registry injected into the system
    prompt as compact one-liners (token-cheap).
16. **Self-authored skills with review** — when a multi-step task succeeds, the agent
    drafts a skill file; it lands as a *proposal* the user approves in the web UI
    (OpenClaw's Skill Card review, minus the marketplace risk — nothing third-party
    executes unreviewed).
17. **Curator job** — weekly scheduled task that grades skill usage, prunes dead
    ones, merges duplicates (Hermes' Autonomous Curator, on our scheduler).

## Phase 4 — Channels & execution

18. **Channel adapter interface** — one `Channel` protocol (send_text, send_audio,
    receive) wrapping web-WS and WhatsApp; then Telegram (~an afternoon with
    python-telegram-bot) and email (IMAP poll + SMTP) as the next two adapters.
19. **WhatsApp voice notes both ways** — transcribe incoming voice notes
    (faster-whisper handles ogg/opus), reply with TTS audio encoded as opus voice
    notes via Baileys.
20. **Sandboxed execution tool** — a `run_code` tool executing in a throwaway Docker
    container (no network by default, cpu/mem caps, rw mount only on an exchange
    dir), gated behind the Phase-2 approval flow. This is the OpenClaw/Hermes
    capability jump — and our sandbox-by-default posture beats OpenClaw's
    run-on-your-machine default.
21. **Real web tool** — fetch + readability extraction (trafilatura), not just
    DuckDuckGo snippets.

## Phase 5 — The parts nobody else has

22. **Voice barge-in** — client VAD (silero on the worker thread we already have for
    hand tracking) stops playback and starts capture when the user speaks over
    Wednesday. Neither OpenClaw nor Hermes does live full-duplex voice.
23. **Wake word** — openWakeWord in the browser (ONNX runtime web), so the orb is
    hands-free: "Wednesday…" while it idles on a second monitor.
24. **Gesture commands** — the hand tracker already in-tree: palm-up to interrupt,
    fist to mute, etc. Pure differentiation.
25. **Model router** — task-tiered models: small local model for routing/extraction,
    bigger local (or optional free hosted, e.g. OpenRouter) for hard reasoning; per
    Fish/Piper precedent, hosted-when-configured + local-always-works.
26. **Eval harness** — a dozen scripted conversations (tool use, memory recall,
    persona adherence) run in CI against Piper + fake Ollama, so robustness is
    measured, not vibes.

## Security thread (runs through every phase)

- Secrets: OAuth tokens sit in sqlite plaintext next to the code — encrypt at rest
  or lock file perms, and keep `wednesday.db` gitignored (done).
- Prompt injection: email/web content entering the context is untrusted — wrap tool
  results in delimiters + an instruction not to obey embedded directives, and keep
  consequential actions behind approvals (defense in depth, not either/or).
- No third-party skill marketplace until there's a sandbox + scanner story; ClawHub's
  supply-chain surface is OpenClaw's biggest liability. Local-authored, human-reviewed
  skills only.

---

## Phase 6 — landed 2026-08 (beyond the original gap analysis)

The items above closed the gap with OpenClaw and Hermes. These go past it, and
are all in-tree now:

| # | What | Where |
|---|---|---|
| 27 | **MCP client** — every tool on every server in `mcp.json` becomes a Wednesday tool at boot, namespaced and approval-gated, with a cap so schemas can't eat the context window | `backend/mcp_client.py` |
| 28 | **Hybrid memory retrieval** — FTS5 keyword + sqlite-vec semantic search fused by RRF, embeddings from local `nomic-embed-text`; degrades to keyword, then to the old lexical scan | `backend/vecstore.py` |
| 29 | **SearXNG search** — self-hosted metasearch over ~70 engines, keyless and unthrottled, now the preferred `web_search` backend ahead of the paid providers | `backend/tools/builtin.py`, `searxng/` |
| 30 | **Kokoro TTS** — 82M-param ONNX voice, local and free, slotted into a Fish → Kokoro → Piper fallback chain | `backend/voice.py` |
| 31 | **Vision** — photos sent on WhatsApp are described by a local VLM (moondream) and enter the conversation as text; `see_image` does the same for URLs | `backend/vision.py` |
| 32 | **Wake word** (roadmap item 23) — openWakeWord's three-model pipeline running on onnxruntime-web, gating the VAD that was already there | `frontend/src/lib/wakeWord.js` |
| 33 | **Browser control** — `browse_web` drives headless Chromium with the local model for pages `fetch_page` can't read | `backend/tools/browser.py` |
| 34 | **Home Assistant** (extends item 18) — a Wyoming server exposing STT, conversation and TTS, so HA voice satellites share Wednesday's memory and tools | `backend/wyoming_server.py` |

Everything new is off or degrading-by-default: a missing model, package or
server costs a log line and a fallback, never a broken assistant.

### Still open

- Telegram and Signal channel adapters (item 18's remaining half). Home
  Assistant arrived first, via Wyoming.
- Third-party skills. Still deliberately absent, for the supply-chain reasons
  in the security thread below — MCP servers are the sanctioned way to add
  capability now, and they run out-of-process behind an approval prompt.
