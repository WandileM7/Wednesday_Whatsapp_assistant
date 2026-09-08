# 🔮 Wednesday

**A fully open-source, self-hosted personal AI assistant — on the web and on WhatsApp. Zero API bills.**

Wednesday talks to you through a Jarvis-style holographic orb in your browser (voice or text) and through WhatsApp. Everything — the LLM, speech-to-text, text-to-speech, the WhatsApp gateway — runs on your own machine with free, open-source components. No OpenAI key, no cloud subscription, no billing anywhere.

---

## The free stack

| Capability | Powered by | Cost |
|------------|-----------|------|
| LLM + tool calling | [Ollama](https://ollama.com) (`qwen2.5:7b` by default) | Free, local |
| Speech-to-text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Free, local |
| Text-to-speech | [Kokoro](https://github.com/hexgrad/kokoro) or [Piper](https://github.com/rhasspy/piper) (local), or [Fish Audio](https://fish.audio) hosted voice when `FISH_API_KEY` is set | Free, local (Fish free tier optional) |
| Vision | [moondream](https://github.com/m87-labs/moondream) via Ollama — reads photos sent on WhatsApp | Free, local |
| Memory | SQLite FTS5 + [sqlite-vec](https://github.com/asg017/sqlite-vec), embeddings from `nomic-embed-text`; self-consolidating | Free, local |
| Web search | [SearXNG](https://github.com/searxng/searxng) (self-hosted, ~70 engines), DuckDuckGo fallback | Free, no API key |
| Extra tools | Any [MCP](https://github.com/modelcontextprotocol/python-sdk) server listed in `mcp.json` | Free |
| Wake word | [openWakeWord](https://github.com/dscripka/openWakeWord) in the browser (ONNX) | Free, local |
| WhatsApp | [Baileys](https://github.com/WhiskeySockets/Baileys) (no business API) | Free |
| Home Assistant | [Wyoming](https://www.home-assistant.io/integrations/wyoming/) server — STT + conversation + TTS | Free, local |
| Phone calls | [Asterisk](https://www.asterisk.org/) AudioSocket — SIP, or a SIM via [chan_quectel](https://github.com/RoEdAl/asterisk-chan-quectel) | Free, local |
| Orb visuals | Three.js, adapted from [ULTRON Orb UI](https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds) | Free (MIT) |
| Tools | Gmail / Calendar / Tasks (Google OAuth), Spotify, web search, browser control | Free tiers |

Voice, STT and wake-word models auto-download on first use.

## Architecture

```
 Browser (orb UI) ──ws──►                    ┌─► Ollama ─┬─ chat + tools
   └ wake word (ONNX)                        │           ├─ vision (moondream)
                          FastAPI backend ───┤           └─ embeddings
 WhatsApp ──► Baileys ──►     (:8000)        ├─► faster-whisper (STT)
              (:3000)                        ├─► Fish / Kokoro / Piper (TTS)
 Email ──► IMAP ─────────►                   ├─► SearXNG (:8080) + web fetch
                                             ├─► Gmail / Calendar / Tasks /
 Home Assistant ──wyoming──► (:10700)        │   Spotify
                                             └─► MCP servers (mcp.json)
 Phone ──► Asterisk ──audiosocket──► (:8090)
           (SIP or SIM)
```

## Quick start

```bash
git clone https://github.com/WandileM7/Wednesday_Whatsapp_assistant.git
cd Wednesday_Whatsapp_assistant
cp .env.example .env        # defaults work out of the box

docker compose up -d        # backend + ollama + whatsapp + searxng + postgres

# Pull the models (first time only): the main chat model + a small
# utility model for background work (summaries, memory). Keeping them
# separate stops background calls from evicting the chat model's cache.
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull llama3.2:3b

# Optional but recommended:
docker compose exec ollama ollama pull nomic-embed-text   # semantic memory
docker compose exec ollama ollama pull moondream          # reads your photos
```

Then:

1. Open the web UI — `cd frontend && npm install && npm run dev` → http://localhost:1420
2. **WhatsApp (optional):** fetch the QR from http://localhost:8000/whatsapp/qr and scan it via WhatsApp → Linked Devices
3. **Google / Spotify tools (optional):** create free OAuth apps, put the client ID/secret in `.env`, then visit `/auth/google` and `/auth/spotify` to link

### Without Docker

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload        # backend on :8000
ollama serve && ollama pull qwen2.5:7b && ollama pull llama3.2:3b  # in another shell
cd frontend && npm install && npm run dev
```

## Configuration

Everything lives in `.env` (see `.env.example`). Highlights:

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `qwen2.5:7b` | Any Ollama model with tool support; the sampling defaults are tuned for this one |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium` — bigger = better + slower |
| `PIPER_VOICE` | `en_GB-alba-medium` | Any voice from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) |
| `FISH_API_KEY` | _(empty)_ | Set to use a [Fish Audio](https://fish.audio) hosted voice for TTS; Piper stays as the fallback |
| `WHATSAPP_ENABLED` | `true` | Set `false` for web-only mode |
| `SEARXNG_URL` | set by compose | Keyless metasearch; falls back to DuckDuckGo |
| `ENABLE_KOKORO` | `false` | Local Kokoro voice (`pip install kokoro-onnx`, ~310MB model) |
| `VISION_MODEL` | `moondream` | Any Ollama vision model |
| `EMBED_MODEL` | `nomic-embed-text` | Powers semantic memory; falls back to keyword search |
| `ROUTE_BACKEND` | `false` | With a hosted key set, send a turn hosted only when Ollama would be slow at it |
| `ROUTE_LATENCY_BUDGET` | `8` | Seconds. The estimate above which a turn goes hosted |

Run `/doctor` to see which of these are actually live.

### Keeping turns on the box

Setting `LLM_BASE_URL` sends *every* turn to the hosted endpoint, including
"thanks" and "night". `ROUTE_BACKEND=true` makes that decision per turn instead:
Wednesday estimates what the turn would cost locally and only spends the hosted
call when local would be slow — a tool hop, or an explicit ask for long-form.
Chatter stays on the box, which is both cheaper on a metered tier and less of
your conversation leaving the machine.

The estimate needs the box's real throughput, and that is the number nothing can
tell you: `ollama ps` reports "100% CPU" even when every layer is on the GPU. So
it isn't configured — Wednesday reads it back off Ollama's own counters each
local turn. If the SYCL backend stops loading and prefill drops from ~70 tok/s
to ~6, routing notices within a few turns and moves more traffic hosted on its
own. `/doctor` reports the measured rate under `local_speed`.

The estimate is logged whether or not routing is acting on it, so the honest
order is: leave it off, `grep "would route"` a day of logs, then turn it on.

## Extending it

### MCP servers

`cp mcp.json.example mcp.json` and list any [MCP](https://modelcontextprotocol.io)
servers — the file uses Claude Desktop's shape, so existing configs paste
straight in. Every tool on every server becomes a Wednesday tool at boot,
namespaced `mcp_<server>_<tool>`. They ask before running (`MCP_REQUIRE_APPROVAL`),
and `MCP_MAX_TOOLS` caps how much of the context window their schemas can eat.

### Wake word

Set `VITE_WAKE_WORD` (see `frontend/.env.example`) to an openWakeWord model —
`hey_jarvis_v0.1`, `alexa_v0.1`, `hey_mycroft_v0.1` — and hands-free mode stays
silent until it hears the word. The backend downloads and caches the ONNX models;
leaving the variable empty keeps the runtime out of the bundle entirely.

### Home Assistant

`ENABLE_WYOMING=true` exposes Wednesday on port 10700 as a Wyoming speech-to-text,
conversation and text-to-speech service. Add it in HA under *Settings → Devices →
Add integration → Wyoming Protocol* and every voice satellite in the house talks
to the same brain. Wyoming is unauthenticated — keep the port on your LAN.

### Phone calls

`ENABLE_PHONE=true` opens an [AudioSocket](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/Dialplan_Applications/AudioSocket/)
server on port 8090. Asterisk does the telephony and hands over a TCP socket of
8kHz PCM, so the backend never learns SIP:

```
exten => s,1,Answer()
 same =>   n,AudioSocket(${UUID},127.0.0.1:8090)
 same =>   n,Hangup()
```

Where the call itself comes from is Asterisk's problem, and there are two
answers. A **SIP trunk** is a config file. A **SIM in a USB LTE modem** —
Quectel EC25/EG9x or SIMCom SIM7600, driven by
[chan_quectel](https://github.com/RoEdAl/asterisk-chan-quectel) — is the fully
off-grid one: real calls on a number you already own, over the cellular voice
network, with no VoIP provider in the path. It also means she can ring a phone
that has nothing installed on it, which no SIP softphone can do without push
notification infrastructure behind it.

Like Wyoming, AudioSocket has no authentication. Bind it where only Asterisk
can reach it.

**Testing it without buying anything.** Two tiers, both free:

```bash
# 1. no Asterisk at all — pretend to be it
python -m scripts.callsim --wav question.wav --out reply.wav
python -m scripts.callsim --live        # talk to her; needs `pip install sounddevice`

# 2. real SIP: Asterisk in a container, a free softphone, no number
HOST_LAN_IP=192.168.1.x SIP_PASSWORD=pick-one \
  docker compose --profile phone up asterisk
```

Then point [Linphone](https://www.linphone.org/) (free, open source, desktop or
mobile) at `HOST_LAN_IP`, username `softphone`, and dial **100**. That is a real
call — real SIP signalling, real RTP, real jitter — with no carrier, no number
and no hardware.

Two addresses have to be right, and both fail quietly:

- **`HOST_LAN_IP`** is what Asterisk advertises in SDP, so it must be the
  address *the phone* can reach — the Windows machine's LAN address on WSL2,
  not the WSL distro's `172.x` NAT address. Wrong here and the call connects,
  both ends ring, and nobody hears anything.
- **`WEDNESDAY_ADDR`** is where Asterisk finds the backend. `host.docker.internal`
  is right on plain Docker and Docker Desktop, but under Rancher Desktop the
  container and a WSL-hosted backend sit in different namespaces and it does not
  resolve to anything useful. Find one that works:

  ```bash
  docker compose --profile phone exec asterisk \
    sh -c 'nc -z -w2 <candidate> 8090 && echo reachable'
  ```

On WSL2 the phone also cannot reach the backend at all until either WSL is in
mirrored networking mode (`networkingMode=mirrored` in `.wslconfig`) or there is
a tailnet spanning both. And Windows Firewall has to allow 5060/udp and
10000-10099/udp inbound.

**A real number, via Telnyx.** Set the credentials from a Telnyx
*Credentials* SIP connection and the trunk appears; leave them unset and the
rig stays softphone-only:

```bash
TELNYX_SIP_USER=... TELNYX_SIP_PASSWORD=... HOST_LAN_IP=192.168.1.x \
  SIP_PASSWORD=pick-one docker compose --profile phone up asterisk
```

Inbound goes to Wednesday automatically (`from-telnyx` → extension 100). For
outbound — her ringing you — originate into the trunk and hand the answered
call to the same extension:

```bash
docker compose --profile phone exec asterisk asterisk -rx \
  "channel originate PJSIP/+27XXXXXXXXX@telnyx extension 100@wednesday"
```

Check it came up with `pjsip show registrations`: `Registered` is good,
`Rejected` is the credentials.

`scripts/callsim.py` covers everything up to the socket; the softphone covers
what only a real Asterisk can tell you. Both were needed — the keepalive
silence in `Call.transmit` exists because `app_audiosocket` hangs up after
2000ms of receiving nothing, and no socket-level test would ever have noticed.

Call quality is a latency problem, not an audio problem: she starts speaking at
her first sentence rather than her last token, but a turn still has to reach
first audio in about a second or the caller hears dead air. Every turn logs
what it actually took — read it off `/doctor` under `phone` before deciding
whether calls need their own routing budget.

### Browser control

`ENABLE_BROWSER_USE=true` (plus `pip install browser-use && playwright install
chromium`) adds a `browse_web` tool that drives a real headless browser with the
local model, for pages `fetch_page` can't read. It asks before every run.

## Orb controls

Drag to spin, scroll to zoom, `R` to reset, `+`/`−` to zoom. The orb's bloom pulses with Wednesday's voice.

## Project structure

```
├── backend/              # FastAPI: agent loop, voice, OAuth, WhatsApp webhook
│   ├── agent.py          # Ollama tool-calling loop
│   ├── voice.py          # faster-whisper STT + Fish/Kokoro/Piper TTS
│   ├── vision.py         # local VLM: describes images for the text model
│   ├── memory.py         # fact extraction, consolidation + retrieval
│   ├── vecstore.py       # FTS5 + sqlite-vec hybrid index
│   ├── mcp_client.py     # MCP servers → tools
│   ├── wyoming_server.py # Home Assistant voice endpoint
│   ├── phone.py         # phone calls over Asterisk AudioSocket
│   └── tools/            # Gmail, Calendar, Tasks, Spotify, search, browser…
├── frontend/             # Vite + React + Tailwind + Three.js orb
│   ├── src/lib/orbScene.ts   # holographic orb (adapted from ULTRON Orb UI)
│   └── src/lib/wakeWord.js   # openWakeWord pipeline (onnxruntime-web)
├── whatsapp-service/     # Baileys WhatsApp gateway
├── asterisk/             # test-rig dialplan + SIP config (profile: phone)
├── scripts/callsim.py    # place a call with no Asterisk and no hardware
├── searxng/              # self-hosted metasearch config
├── mcp.json.example      # MCP server list (copy to mcp.json)
└── docker-compose.yaml   # one-command full stack
```

## Contributing

PRs and issues welcome. CI runs backend import checks and the frontend build on every PR.

## Credits

- Holographic orb visuals adapted from [ULTRON Orb UI](https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds) by [Sagar Tamang](https://github.com/SAGAR-TAMANG) (MIT).
- [Ollama](https://ollama.com), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/rhasspy/piper), [Baileys](https://github.com/WhiskeySockets/Baileys).
- [Kokoro](https://github.com/hexgrad/kokoro) and [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), [moondream](https://github.com/m87-labs/moondream), [sqlite-vec](https://github.com/asg017/sqlite-vec), [SearXNG](https://github.com/searxng/searxng), [openWakeWord](https://github.com/dscripka/openWakeWord), [browser-use](https://github.com/browser-use/browser-use), [Wyoming](https://github.com/rhasspy/wyoming), [Asterisk](https://github.com/asterisk/asterisk) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## License

[MIT](LICENSE)



