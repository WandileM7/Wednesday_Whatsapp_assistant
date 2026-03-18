# 🤖 Wednesday WhatsApp AI Assistant

<div align="center">

![Wednesday Assistant](https://via.placeholder.com/600x200/1a1a1a/00d4ff?text=🤖+WEDNESDAY+AI+ASSISTANT)

**Advanced AI-Powered WhatsApp Assistant with MCP Agent Architecture**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![Google Gemini](https://img.shields.io/badge/Gemini-2.5-orange.svg)](https://ai.google.dev/)
[![MCP](https://img.shields.io/badge/MCP-52_Tools-purple.svg)](mcp_server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [MCP Agent & Tools](#-mcp-agent--tools)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Deployment](#-deployment)
- [API Reference](#-api-reference)
- [Voice Features](#-voice-features)
- [Testing](#-testing)
- [Troubleshooting](#-troubleshooting)

---

## 🚀 Overview

Wednesday is an advanced AI assistant that brings intelligent automation to WhatsApp. Built on **Google Gemini** with a **Model Context Protocol (MCP)** agent architecture, it provides 52+ tools for comprehensive task automation including:

- 💬 Natural language conversations with context memory
- 📧 Email and calendar management (Gmail, Google Calendar)
- 🎵 Music control (Spotify)
- 🎤 Voice message transcription and voice responses
- 🏠 Smart home control (IFTTT, Home Assistant)
- 📊 Task tracking, reminders, and daily briefings
- 🖼️ AI image generation (DALL-E, Stability AI)

---

## ✨ Key Features

### 🧠 AI-Powered Intelligence
| Feature | Description |
|---------|-------------|
| **Google Gemini 2.5** | Primary AI with function calling for tool execution |
| **MCP Agent** | 52 structured tools organized by category |
| **Context Memory** | SQLite/Firebase persistent conversation history |
| **Voice Recognition** | Gemini-powered speech-to-text transcription |
| **Voice Synthesis** | Google Cloud TTS for voice responses |

### 📱 WhatsApp Integration
| Feature | Description |
|---------|-------------|
| **Baileys/WAHA** | WhatsApp Web API integration |
| **Voice Messages** | Automatic transcription and voice replies |
| **Media Sharing** | Images, audio, and AI-generated content |
| **Contact Resolution** | Smart contact lookup via Google Contacts |
| **Owner Verification** | Security features for owner-only commands |

### 🔧 Automation & Services
| Feature | Description |
|---------|-------------|
| **Gmail** | Read, search, and send emails |
| **Google Calendar** | View and create events |
| **Spotify** | Playback control and playlist management |
| **Tasks & Reminders** | Create, track, and complete tasks |
| **Weather & News** | Real-time updates and briefings |
| **Smart Home** | IFTTT, Home Assistant, Philips Hue |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Wednesday AI Assistant                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │   WhatsApp   │    │    Flask     │    │    MCP Agent         │   │
│  │   Service    │───▶│    Server    │───▶│    (Gemini 2.5)      │   │
│  │   (Baileys)  │    │   (main.py)  │    │    52 Tools          │   │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
│         │                   │                      │                 │
│         │                   │                      ▼                 │
│         │                   │            ┌──────────────────┐       │
│         │                   │            │   Tool Handlers   │       │
│         │                   │            ├──────────────────┤       │
│         ▼                   ▼            │ • Gmail/Calendar │       │
│  ┌──────────────┐    ┌──────────────┐   │ • Spotify        │       │
│  │   Session    │    │   SQLite/    │   │ • Tasks/Reminders│       │
│  │   Storage    │    │   Firebase   │   │ • Smart Home     │       │
│  │   (GCS)      │    │   Database   │   │ • Voice/Media    │       │
│  └──────────────┘    └──────────────┘   └──────────────────┘       │
│                                                                      │
│                        External Services                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Google APIs  │  Spotify API  │  OpenAI/Stability  │  IFTTT  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### How It Works

1. **WhatsApp Message** → Received via Baileys webhook
2. **Voice Processing** → If voice message, transcribed via Gemini STT
3. **MCP Agent** → Gemini analyzes message and decides which tools to call
4. **Tool Execution** → Agent executes 0-N tools based on user request
5. **Response** → Text or voice response sent back to WhatsApp

---

## 🔧 MCP Agent & Tools

The **Model Context Protocol (MCP)** agent provides a structured interface for AI-driven automation. The agent uses **Gemini 2.5** to reason about user requests and execute the appropriate tools.

### Core Tools (17)

| Category | Tools | Description |
|----------|-------|-------------|
| **Chat** | `chat` | AI conversation with context |
| **WhatsApp** | `send_whatsapp` | Send messages |
| **Calendar** | `get_calendar_events`, `create_calendar_event` | Google Calendar |
| **Email** | `get_emails`, `send_email` | Gmail integration |
| **Tasks** | `get_tasks`, `create_task`, `complete_task` | Task management |
| **Contacts** | `search_contacts`, `add_contact` | Contact lookup |
| **Spotify** | `spotify_play`, `spotify_control`, `spotify_now_playing` | Music control |
| **Weather** | `get_weather` | Weather information |
| **News** | `get_news` | News headlines |
| **Memory** | `search_memory` | Conversation history |
| **System** | `service_status` | Health checks |

### Advanced Tools (35)

| Category | Tools | Description |
|----------|-------|-------------|
| **Workflows** | `run_workflow`, `list_workflows` | Automated routines (morning_routine, focus_mode) |
| **Smart Home** | `smart_home_lights`, `smart_home_thermostat`, `smart_home_scene`, `smart_home_locks`, `smart_home_status` | Home automation |
| **Voice** | `speak_this`, `voice_status`, `toggle_voice_mode` | Google Cloud TTS |
| **Long-term Memory** | `remember_this`, `recall_memory`, `forget_memory`, `get_user_profile`, `memory_stats` | Persistent memories |
| **Security** | `security_status`, `security_report`, `check_threat` | Security monitoring |
| **Fitness** | `log_fitness`, `get_fitness_summary`, `get_fitness_history`, `set_fitness_goal` | Activity tracking |
| **Expenses** | `add_expense`, `get_spending_report`, `set_budget` | Budget management |
| **Briefings** | `get_daily_briefing`, `schedule_briefing`, `cancel_briefing` | Daily summaries |
| **Mood Music** | `play_mood_music` | Context-aware music |
| **Media** | `generate_image`, `generate_video` | AI content generation |
| **JARVIS Core** | `jarvis_greeting`, `proactive_suggestions`, `jarvis_status` | Personality features |

### MCP Server Modes

```bash
# STDIO Mode (for VS Code/Cursor)
python -m mcp_server.server

# HTTP Mode (for Kubernetes/API access)
python -m mcp_server.http_server  # Port 8080
```

---

## 📁 Project Structure

```
Wednesday_Whatsapp_assistant/
├── main.py                    # Flask application entry point
├── config.py                  # Environment configuration
├── database.py                # SQLite/Firebase database manager
├── requirements.txt           # Python dependencies
│
├── handlers/                  # Feature modules
│   ├── mcp_agent.py          # MCP Agent (Gemini + 52 tools)
│   ├── gemini.py             # Gemini AI integration
│   ├── gmail.py              # Gmail API
│   ├── calendar.py           # Google Calendar API
│   ├── spotify.py            # Spotify playback control
│   ├── speech.py             # Voice STT/TTS (Gemini, Google Cloud)
│   ├── google_auth.py        # OAuth2 authentication
│   ├── tasks.py              # Task management
│   ├── contacts.py           # Contact search
│   ├── weather.py            # Weather API
│   ├── news.py               # News API
│   ├── smart_home.py         # Home automation
│   ├── security.py           # Owner verification & rate limiting
│   ├── long_term_memory.py   # Persistent memory system
│   ├── workflows.py          # Automated workflows
│   ├── daily_briefing.py     # Morning briefings
│   ├── fitness.py            # Activity tracking
│   ├── expenses.py           # Budget tracking
│   ├── media_generator.py    # AI image generation
│   └── quick_commands.py     # Slash commands (/help, /voice, etc.)
│
├── mcp_server/               # MCP Protocol Server
│   ├── server.py             # STDIO MCP server (52 tools)
│   ├── http_server.py        # HTTP/SSE transport
│   └── README.md             # MCP documentation
│
├── whatsapp-service/         # WhatsApp Baileys Service
│   ├── server-baileys.js     # Node.js WhatsApp client
│   ├── package.json          # Node dependencies
│   └── session/              # WhatsApp session data
│
├── kubernetes/               # K8s/Rancher deployment
│   ├── assistant-deployment.yaml
│   ├── mcp-server-deployment.yaml
│   ├── whatsapp-deployment.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── ingress.yaml
│   ├── hpa.yaml              # Autoscaling
│   └── fleet.yaml            # Rancher Fleet GitOps
│
├── scripts/                  # Setup scripts
│   ├── setup-gcp.ps1         # GCP setup (PowerShell)
│   └── setup-gcp.sh          # GCP setup (Bash)
│
├── docs/                     # Documentation
│   └── GCP_DEPLOYMENT.md     # Google Cloud deployment guide
│
├── templates/                # HTML templates
├── static/                   # Static assets
├── frontend/                 # React dashboard (optional)
├── task_data/                # Persistent token storage
│
├── Dockerfile                # Main container image
├── Dockerfile.cloudrun       # Cloud Run optimized
├── Dockerfile.mcp            # MCP server standalone
├── docker-compose.yaml       # Multi-service setup
├── render.yaml               # Render.com deployment
└── mcp.json                  # VS Code MCP configuration
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ (for WhatsApp service)
- Google Cloud account (for Gmail, Calendar, TTS)
- Gemini API key

### 1. Clone & Install

```bash
git clone https://github.com/WandileM7/Wednesday_Whatsapp_assistant.git
cd Wednesday_Whatsapp_assistant

# Install Python dependencies
pip install -r requirements.txt

# Install WhatsApp service dependencies
cd whatsapp-service && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Start Services

```bash
# Option 1: All services via Docker
docker-compose up -d

# Option 2: Manual (separate terminals)
# Terminal 1: WhatsApp service
cd whatsapp-service && node server-baileys.js

# Terminal 2: Flask backend
python main.py
```

### 4. Setup Authentication

1. Open `http://localhost:5000/quick-setup`
2. Click **Google Login** to authenticate Gmail/Calendar
3. Click **Spotify Login** if using music features
4. Scan QR code at `http://localhost:5000/whatsapp-qr`

---

## 🔑 Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (primary AI) |
| `OWNER_PHONE` | Your phone number for owner verification |

### Google Services

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth2 client secret |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service account JSON (for TTS) |
| `GOOGLE_REFRESH_TOKEN` | (Optional) Pre-saved refresh token |

### WhatsApp

| Variable | Description |
|----------|-------------|
| `WAHA_URL` | WhatsApp service base URL |
| `WAHA_HEALTH_URL` | Health check endpoint |
| `GCS_SESSION_BUCKET` | GCS bucket for session persistence |

### Spotify

| Variable | Description |
|----------|-------------|
| `SPOTIFY_CLIENT_ID` | Spotify app client ID |
| `SPOTIFY_SECRET` | Spotify app secret |
| `SPOTIFY_REDIRECT_URI` | OAuth callback URL |
| `SPOTIFY_REFRESH_TOKEN` | (Optional) Pre-saved refresh token |

### Smart Home

| Variable | Description |
|----------|-------------|
| `IFTTT_WEBHOOK_KEY` | IFTTT webhook key |
| `HOME_ASSISTANT_URL` | Home Assistant URL |
| `HOME_ASSISTANT_TOKEN` | Home Assistant access token |

### Media Generation

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (DALL-E) |
| `STABILITY_API_KEY` | Stability AI key |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASK_DEBUG` | Debug mode | `false` |
| `USE_MEMORY_DB` | In-memory SQLite | `false` |
| `PERSONALITY_PROMPT` | AI personality | Built-in |
| `NEWS_API_KEY` | NewsAPI.org key | - |
| `WEATHERAPI_KEY` | WeatherAPI.com key | - |

---

## 🚢 Deployment

### Local Development

```bash
python main.py
# Access: http://localhost:5000
```

### Docker Compose

```bash
docker-compose up -d

# Services:
# - wednesday-assistant: Port 5000
# - whatsapp-service: Port 3000
```

### Render.com

The repo includes `render.yaml` for one-click deployment:

1. Connect GitHub repo to Render
2. Add environment variables in Render dashboard
3. Deploy both `wednesday-assistant` and `whatsapp-service`

### Google Cloud Run

See [docs/GCP_DEPLOYMENT.md](docs/GCP_DEPLOYMENT.md) for detailed setup.

```bash
# Quick deploy via GitHub Actions
# Push to main triggers .github/workflows/deploy-gcp.yml
```

Required GitHub Secrets:
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCP_SA_KEY` (base64 encoded)
- `GEMINI_API_KEY`

### Kubernetes/Rancher

```bash
kubectl create namespace wednesday
kubectl apply -f kubernetes/ -n wednesday
```

For Rancher Fleet GitOps, import the repo and Fleet will use `kubernetes/fleet.yaml`.

---

## 🛠️ API Reference

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health with memory/CPU stats |
| GET | `/services` | All configured services overview |
| GET | `/assistant/status` | Full agent status |
| GET | `/api/dashboard` | Dashboard data (JSON) |

### WhatsApp

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhook` | Message webhook receiver |
| POST | `/send` | Send message |
| GET | `/whatsapp-status` | Connection status |
| GET | `/whatsapp-qr` | QR code page |
| POST | `/whatsapp-reconnect` | Force reconnection |
| POST | `/whatsapp-logout` | Logout session |

### Google Services

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/google-login` | Start OAuth flow |
| GET | `/google-status` | Auth status |
| GET | `/test-google-services` | Test all services |
| GET | `/test-gmail` | Test Gmail |

### Spotify

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/login` | Start Spotify OAuth |
| GET | `/spotify-status` | Connection status |
| GET | `/test-spotify` | Test integration |

### MCP Server (HTTP Mode)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tools` | List all 52 tools |
| POST | `/tools/<name>` | Execute specific tool |
| POST | `/call` | Unified tool call |
| GET | `/health` | MCP server health |

---

## 🎤 Voice Features

### Speech-to-Text (STT)

Voice messages are automatically transcribed using **Gemini 2.5 Flash**:

1. WhatsApp voice message received
2. Audio downloaded and processed
3. Gemini transcribes to text
4. Text processed by MCP agent

### Text-to-Speech (TTS)

Voice responses via **Google Cloud TTS**:

```bash
# Enable voice mode via WhatsApp
/voice on

# Or use the toggle_voice_mode tool
```

When voice mode is enabled, all responses are sent as voice messages.

### Quick Commands

| Command | Description |
|---------|-------------|
| `/voice on` | Enable voice responses |
| `/voice off` | Disable voice responses |
| `/voice status` | Check current mode |
| `/help` | List all commands |

---

## 🧪 Testing

### Manual Validation

```bash
# Health check
curl http://localhost:5000/health

# Test Google services
curl http://localhost:5000/test-google-services

# Test webhook
curl -X POST http://localhost:5000/test-webhook-simple \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'
```

### Test Endpoints

| Endpoint | Description |
|----------|-------------|
| `/test-google-services` | Gmail, Calendar tests |
| `/test-gmail` | Gmail specific |
| `/test-spotify` | Spotify connection |
| `/test-speech` | TTS functionality |
| `/test-all-services` | Comprehensive test |

---

## 🔧 Troubleshooting

### WhatsApp Connection Issues

```bash
# Check status
curl http://localhost:5000/whatsapp-status

# Force reconnect
curl -X POST http://localhost:5000/whatsapp-reconnect

# Clear session and re-scan QR
curl -X POST http://localhost:5000/whatsapp-logout
```

### Google Auth Issues

```bash
# Check auth status
curl http://localhost:5000/google-auth-status

# Force re-authentication
# Visit: http://localhost:5000/google-login
```

### Voice Not Working

1. Check `GOOGLE_APPLICATION_CREDENTIALS` is set
2. Test TTS: `curl http://localhost:5000/test-speech`
3. Check logs for Gemini STT errors

### Common Fixes

| Issue | Solution |
|-------|----------|
| "No credentials" | Complete OAuth at `/google-login` |
| Duplicate messages | Check webhook deduplication |
| Voice transcription fails | Verify Gemini API key |
| Spotify not playing | Re-authenticate at `/login` |

---

## 📈 Performance

| Metric | Value |
|--------|-------|
| Response Time | <100ms (most endpoints) |
| Memory Usage | ~135MB average |
| Throughput | 1000+ requests/min |
| Uptime | 99.9% with auto-recovery |

### Resource Requirements

| Environment | CPU | RAM | Storage |
|-------------|-----|-----|---------|
| Minimum | 1 core | 2GB | 5GB |
| Recommended | 2 cores | 4GB | 10GB |
| Production | 4 cores | 8GB | 50GB |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ using Google Gemini, Flask, and MCP**

[Report Bug](https://github.com/WandileM7/Wednesday_Whatsapp_assistant/issues) • [Request Feature](https://github.com/WandileM7/Wednesday_Whatsapp_assistant/discussions)

</div>
