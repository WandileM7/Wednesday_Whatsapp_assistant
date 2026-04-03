# Wednesday WhatsApp Assistant

Thin Flask relay that forwards WhatsApp messages to a self-hosted n8n AI agent. n8n handles all AI processing, email, calendar, tasks, expenses, and contacts via MCP workflows.

## Working Effectively

### Run the Application
- `pip install -r requirements.txt` — 3 deps (Flask, dotenv, requests). Takes <3s.
- `python main.py` — starts in <1s on port 5000.
- No API keys needed for the relay itself — all credentials live in n8n.

### Docker (full stack)
- `docker compose up -d` — starts n8n (:5678), WAHA (:3000), relay (:5000).
- n8n dashboard: http://localhost:5678 (admin/wednesday123)

### Testing
- Health: `curl http://localhost:5000/health`
- n8n status: `curl http://localhost:5000/n8n-status`
- WhatsApp status: `curl http://localhost:5000/whatsapp-status`
- Webhook test: `curl -X POST http://localhost:5000/webhook -H "Content-Type: application/json" -d '{"payload":{"chatId":"test","body":"hello","id":"1"}}'`

## Validation

After making changes:
1. Run `python main.py` — confirm it starts without errors
2. `curl http://localhost:5000/health` — verify `"status": "healthy"`
3. POST to `/webhook` — verify it attempts to forward to n8n

## Repository Structure

```
├── main.py                 # Flask relay (~230 lines)
├── config.py               # N8N_WEBHOOK_URL, WAHA_URL
├── requirements.txt        # Flask, python-dotenv, requests
├── Dockerfile              # python:3.12-slim
├── docker-compose.yaml     # n8n + WAHA + relay
├── n8n/
│   └── workflow-jarvis-whatsapp.json
├── whatsapp-service/       # Baileys WhatsApp gateway
├── frontend/               # React dashboard (Vite + Tailwind)
│   └── src/
│       ├── pages/Dashboard.jsx, WhatsApp.jsx, Settings.jsx
│       └── components/Layout.jsx, UIComponents.jsx
└── docs/
    └── N8N_SETUP.md
```

## Key Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | System health |
| POST | `/webhook` | WhatsApp incoming → n8n |
| POST | `/send` | Manual message send |
| GET | `/whatsapp-status` | WAHA session status |
| GET | `/whatsapp-qr` | QR code for pairing |
| GET | `/n8n-status` | n8n health |

## Environment Variables

```bash
N8N_WEBHOOK_URL=http://n8n:5678
N8N_WEBHOOK_PATH=/webhook/whatsapp-webhook
N8N_TIMEOUT=120
WAHA_URL=http://whatsapp-service:3000/api/sendText
FLASK_DEBUG=false
```

## Time Expectations
- Dependency install: <3 seconds
- App startup: <1 second
- Docker build: <30 seconds (slim image)
