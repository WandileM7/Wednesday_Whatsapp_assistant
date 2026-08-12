# 🔮 Wednesday

**A fully open-source, self-hosted personal AI assistant — on the web and on WhatsApp. Zero API bills.**

Wednesday talks to you through a Jarvis-style holographic orb in your browser (voice or text) and through WhatsApp. Everything — the LLM, speech-to-text, text-to-speech, the WhatsApp gateway — runs on your own machine with free, open-source components. No OpenAI key, no cloud subscription, no billing anywhere.

---

## The free stack

| Capability | Powered by | Cost |
|------------|-----------|------|
| LLM + tool calling | [Ollama](https://ollama.com) (`llama3.1:8b` by default) | Free, local |
| Speech-to-text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Free, local |
| Text-to-speech | [Kokoro](https://github.com/hexgrad/kokoro) or [Piper](https://github.com/rhasspy/piper) (local), or [Fish Audio](https://fish.audio) hosted voice when `FISH_API_KEY` is set | Free, local (Fish free tier optional) |
| Vision | [moondream](https://github.com/m87-labs/moondream) via Ollama — reads photos sent on WhatsApp | Free, local |
| Memory | SQLite FTS5 + [sqlite-vec](https://github.com/asg017/sqlite-vec), embeddings from `nomic-embed-text` | Free, local |
| Web search | [SearXNG](https://github.com/searxng/searxng) (self-hosted, ~70 engines), DuckDuckGo fallback | Free, no API key |
| Extra tools | Any [MCP](https://github.com/modelcontextprotocol/python-sdk) server listed in `mcp.json` | Free |
| Wake word | [openWakeWord](https://github.com/dscripka/openWakeWord) in the browser (ONNX) | Free, local |
| WhatsApp | [Baileys](https://github.com/WhiskeySockets/Baileys) (no business API) | Free |
| Home Assistant | [Wyoming](https://www.home-assistant.io/integrations/wyoming/) server — STT + conversation + TTS | Free, local |
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
docker compose exec ollama ollama pull llama3.1:8b
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
ollama serve && ollama pull llama3.1:8b && ollama pull llama3.2:3b  # in another shell
cd frontend && npm install && npm run dev
```

## Configuration

Everything lives in `.env` (see `.env.example`). Highlights:

| Variable | Default | Notes |
|----------|---------|-------|
| `OLLAMA_MODEL` | `llama3.1:8b` | Any Ollama model with tool support |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium` — bigger = better + slower |
| `PIPER_VOICE` | `en_GB-alba-medium` | Any voice from [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) |
| `FISH_API_KEY` | _(empty)_ | Set to use a [Fish Audio](https://fish.audio) hosted voice for TTS; Piper stays as the fallback |
| `WHATSAPP_ENABLED` | `true` | Set `false` for web-only mode |
| `SEARXNG_URL` | set by compose | Keyless metasearch; falls back to DuckDuckGo |
| `ENABLE_KOKORO` | `false` | Local Kokoro voice (`pip install kokoro-onnx`, ~310MB model) |
| `VISION_MODEL` | `moondream` | Any Ollama vision model |
| `EMBED_MODEL` | `nomic-embed-text` | Powers semantic memory; falls back to keyword search |

Run `/doctor` to see which of these are actually live.

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
│   ├── memory.py         # fact extraction + retrieval
│   ├── vecstore.py       # FTS5 + sqlite-vec hybrid index
│   ├── mcp_client.py     # MCP servers → tools
│   ├── wyoming_server.py # Home Assistant voice endpoint
│   └── tools/            # Gmail, Calendar, Tasks, Spotify, search, browser…
├── frontend/             # Vite + React + Tailwind + Three.js orb
│   ├── src/lib/orbScene.ts   # holographic orb (adapted from ULTRON Orb UI)
│   └── src/lib/wakeWord.js   # openWakeWord pipeline (onnxruntime-web)
├── whatsapp-service/     # Baileys WhatsApp gateway
├── searxng/              # self-hosted metasearch config
├── mcp.json.example      # MCP server list (copy to mcp.json)
└── docker-compose.yaml   # one-command full stack
```

## Contributing

PRs and issues welcome. CI runs backend import checks and the frontend build on every PR.

## Credits

- Holographic orb visuals adapted from [ULTRON Orb UI](https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds) by [Sagar Tamang](https://github.com/SAGAR-TAMANG) (MIT).
- [Ollama](https://ollama.com), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/rhasspy/piper), [Baileys](https://github.com/WhiskeySockets/Baileys).
- [Kokoro](https://github.com/hexgrad/kokoro) and [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), [moondream](https://github.com/m87-labs/moondream), [sqlite-vec](https://github.com/asg017/sqlite-vec), [SearXNG](https://github.com/searxng/searxng), [openWakeWord](https://github.com/dscripka/openWakeWord), [browser-use](https://github.com/browser-use/browser-use), [Wyoming](https://github.com/rhasspy/wyoming) and the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## License

[MIT](LICENSE)



