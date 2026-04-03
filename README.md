# 🤖 Wednesday WhatsApp AI Assistant

**WhatsApp AI assistant powered by self-hosted n8n workflows.**

Wednesday receives WhatsApp messages and forwards them to an n8n AI agent that orchestrates Gmail, Google Calendar, Tasks, Sheets, and Contacts via MCP tools.

---

## Architecture

```
WhatsApp ──► WAHA Service ──► Flask Relay ──► n8n AI Agent
  (user)       (:3000)          (:5000)         (:5678)
                                                   │
                                    ┌──────────────┤
                                    ▼              ▼
                               OpenAI/Gemini   MCP Tools
                                               (Gmail, Calendar,
                                                Tasks, Sheets,
                                                Contacts)
```

| Service | Port | Role |
|---------|------|------|
| **n8n** | 5678 | AI agent + workflow automation |
| **WAHA** | 3000 | Baileys-based WhatsApp gateway |
| **Relay** | 5000 | Thin Flask proxy (webhook forwarding) |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/WandileM7/Wednesday_Whatsapp_assistant.git
cd Wednesday_Whatsapp_assistant

# 2. Start everything
docker compose up -d

# 3. Set up n8n (http://localhost:5678, admin/wednesday123)
#    - Import n8n/workflow-jarvis-whatsapp.json
#    - Add OpenAI API key credential
#    - Add Google OAuth credentials (Gmail, Calendar, Tasks, Sheets, Contacts)
#    - Activate the workflow

# 4. Connect WhatsApp
#    - Open http://localhost:5000 → WhatsApp page
#    - Scan QR code with WhatsApp → Linked Devices
```

---

## Project Structure

```
├── main.py                 # Flask relay (webhook → n8n)
├── config.py               # Environment configuration
├── requirements.txt        # Flask, requests, python-dotenv
├── Dockerfile              # python:3.12-slim image
├── docker-compose.yaml     # n8n + WAHA + relay
├── n8n/
│   └── workflow-jarvis-whatsapp.json   # AI agent workflow
├── whatsapp-service/       # Baileys WhatsApp gateway
├── frontend/               # React dashboard (Vite + Tailwind)
└── docs/
    └── N8N_SETUP.md        # Detailed n8n setup guide
```

---

## Environment Variables

The relay itself only needs:

```bash
N8N_WEBHOOK_URL=http://n8n:5678
N8N_WEBHOOK_PATH=/webhook/whatsapp-webhook
WAHA_URL=http://whatsapp-service:3000/api/sendText
```

All API keys and OAuth credentials are configured **inside n8n** (not in .env).

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check (relay + n8n + WhatsApp) |
| POST | `/webhook` | WhatsApp webhook (forwards to n8n) |
| POST | `/send` | Manual send message |
| GET | `/whatsapp-status` | WhatsApp connection status |
| GET | `/whatsapp-qr` | QR code for pairing |
| GET | `/n8n-status` | n8n availability |

---

## n8n Workflow Capabilities

The imported workflow provides an AI agent with:

- **Email** — Send, reply, draft, search, label emails
- **Calendar** — Create events, check availability, reschedule
- **Tasks** — Create, complete, delete to-dos
- **Expenses** — Log and query via Google Sheets
- **Contacts** — Look up names and emails
- **Memory** — Per-user conversation context

See [docs/N8N_SETUP.md](docs/N8N_SETUP.md) for detailed configuration.

---

## Development

```bash
# Run relay locally (without Docker)
pip install -r requirements.txt
python main.py

# Run frontend dev server
cd frontend && npm install && npm run dev
# → http://localhost:3001 (proxies to Flask on 5000)
```

---

## License

MIT
