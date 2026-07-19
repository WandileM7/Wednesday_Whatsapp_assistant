# 🔮 Wednesday

**A fully open-source, self-hosted personal AI assistant — on the web and on WhatsApp. Zero API bills.**

Wednesday talks to you through a Jarvis-style holographic orb in your browser (voice or text) and through WhatsApp. Everything — the LLM, speech-to-text, text-to-speech, the WhatsApp gateway — runs on your own machine with free, open-source components. No OpenAI key, no cloud subscription, no billing anywhere.

---

## The free stack

| Capability | Powered by | Cost |
|------------|-----------|------|
| LLM + tool calling | [Ollama](https://ollama.com) (`llama3.1:8b` by default) | Free, local |
| Speech-to-text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Free, local |
| Text-to-speech | [Piper](https://github.com/rhasspy/piper) (local), or [Fish Audio](https://fish.audio) hosted voice when `FISH_API_KEY` is set | Free, local (Fish free tier optional) |
| WhatsApp | [Baileys](https://github.com/WhiskeySockets/Baileys) (no business API) | Free |
| Orb visuals | Three.js, adapted from [ULTRON Orb UI](https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds) | Free (MIT) |
| Tools | Gmail / Calendar / Tasks (Google OAuth), Spotify, DuckDuckGo search | Free tiers |

Voice and STT models auto-download from Hugging Face on first use.

## Architecture

```
 Browser (orb UI) ──ws──►                    ┌─► Ollama (chat + tools)
                          FastAPI backend ───┼─► faster-whisper (STT)
 WhatsApp ──► Baileys ──►     (:8000)        ├─► Fish Audio / Piper (TTS)
              (:3000)                        └─► Gmail / Calendar / Tasks /
                                                 Spotify / web search
```

## Quick start

```bash
git clone https://github.com/WandileM7/Wednesday_Whatsapp_assistant.git
cd Wednesday_Whatsapp_assistant
cp .env.example .env        # defaults work out of the box

docker compose up -d        # backend + ollama + whatsapp + postgres

# Pull the model (first time only)
docker compose exec ollama ollama pull llama3.1:8b
```

Then:

1. Open the web UI — `cd frontend && npm install && npm run dev` → http://localhost:1420
2. **WhatsApp (optional):** fetch the QR from http://localhost:8000/whatsapp/qr and scan it via WhatsApp → Linked Devices
3. **Google / Spotify tools (optional):** create free OAuth apps, put the client ID/secret in `.env`, then visit `/auth/google` and `/auth/spotify` to link

### Without Docker

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload        # backend on :8000
ollama serve && ollama pull llama3.1:8b  # in another shell
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

## Orb controls

Drag to spin, scroll to zoom, `R` to reset, `+`/`−` to zoom. The orb's bloom pulses with Wednesday's voice.

## Project structure

```
├── backend/              # FastAPI: agent loop, voice, OAuth, WhatsApp webhook
│   ├── agent.py          # Ollama tool-calling loop
│   ├── voice.py          # faster-whisper STT + Fish Audio/Piper TTS
│   └── tools/            # Gmail, Calendar, Tasks, Spotify, search…
├── frontend/             # Vite + React + Tailwind + Three.js orb
│   └── src/lib/orbScene.ts   # holographic orb (adapted from ULTRON Orb UI)
├── whatsapp-service/     # Baileys WhatsApp gateway
└── docker-compose.yaml   # one-command full stack
```

## Contributing

PRs and issues welcome. CI runs backend import checks and the frontend build on every PR.

## Credits

- Holographic orb visuals adapted from [ULTRON Orb UI](https://github.com/SAGAR-TAMANG/ultron-by-sagar-builds) by [Sagar Tamang](https://github.com/SAGAR-TAMANG) (MIT).
- [Ollama](https://ollama.com), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Piper](https://github.com/rhasspy/piper), [Baileys](https://github.com/WhiskeySockets/Baileys).

## License

[MIT](LICENSE)



