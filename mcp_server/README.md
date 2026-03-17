# Wednesday MCP Server (JARVIS Edition)

Model Context Protocol (MCP) server for the Wednesday WhatsApp Assistant. This provides a clean, structured API for AI models to interact with all of Wednesday's capabilities including **JARVIS-style advanced features**.

## 🎯 Why MCP?

The Wednesday WhatsApp Assistant has many features spread across multiple handlers. MCP organizes everything into structured **tools** (52 total) that AI models can easily call:

### Core Tools (17)
| Tool Category | Tools | Description |
|--------------|-------|-------------|
| **AI/Chat** | `chat` | Converse with the AI |
| **WhatsApp** | `send_whatsapp` | Send messages via WhatsApp |
| **Calendar** | `get_calendar_events`, `create_calendar_event` | Google Calendar integration |
| **Email** | `get_emails`, `send_email` | Gmail integration |
| **Tasks** | `get_tasks`, `create_task`, `complete_task` | Task management |
| **Contacts** | `search_contacts`, `add_contact` | Contact lookup |
| **Spotify** | `spotify_play`, `spotify_control`, `spotify_now_playing` | Music control |
| **Weather** | `get_weather` | Weather info |
| **News** | `get_news` | News headlines |
| **Memory** | `search_memory` | Search conversation history |
| **System** | `service_status` | Check service health |

### JARVIS Advanced Tools (35)
| Tool Category | Tools | Description |
|--------------|-------|-------------|
| **Workflows** | `run_workflow`, `list_workflows` | Automated multi-step workflows (morning_routine, focus_mode, etc.) |
| **Smart Home** | `smart_home_lights`, `smart_home_thermostat`, `smart_home_scene`, `smart_home_locks`, `smart_home_status` | Control lights, temperature, scenes, locks |
| **Voice** | `speak_this`, `change_voice`, `voice_status` | ElevenLabs premium voice synthesis |
| **Memory** | `remember_this`, `recall_memory`, `forget_memory`, `get_user_profile`, `memory_stats` | Long-term memory system |
| **Security** | `security_status`, `security_report`, `check_threat` | Security monitoring and threat detection |
| **Fitness** | `log_fitness`, `get_fitness_summary`, `get_fitness_history`, `set_fitness_goal` | Fitness tracking |
| **Expenses** | `add_expense`, `get_spending_report`, `set_budget` | Expense tracking and budgeting |
| **Briefings** | `get_daily_briefing`, `schedule_briefing`, `cancel_briefing` | Daily briefings |
| **Mood Music** | `play_mood_music` | Music based on mood |
| **Media** | `generate_image`, `generate_video` | AI media generation |
| **JARVIS Core** | `jarvis_greeting`, `proactive_suggestions`, `jarvis_status` | JARVIS personality and proactive intelligence |

## 🚀 Quick Start

### Option 1: STDIO Mode (for local AI clients)

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server
python -m mcp_server.server
```

### Option 2: HTTP Mode (for Kubernetes/Rancher)

```bash
# Run HTTP server
python -m mcp_server.http_server
```

Server starts on `http://localhost:8080`

### Option 3: Docker

```bash
# Build MCP image
docker build -f Dockerfile.mcp -t wednesday-mcp .

# Run container
docker run -p 8080:8080 \
  -e BYTEZ_API_KEY=your_key \
  wednesday-mcp
```

## 📡 API Endpoints (HTTP Mode)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API documentation |
| `/health` | GET | Health check for Kubernetes |
| `/status` | GET | Service availability |
| `/tools` | GET | List all available tools |
| `/tools/<name>` | POST | Call a specific tool |
| `/call` | POST | Unified tool call |
| `/events` | GET | Server-Sent Events |

### Example API Calls

```bash
# List tools
curl http://localhost:8080/tools

# Chat with AI
curl -X POST http://localhost:8080/tools/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it?"}'

# Get calendar events
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "get_calendar_events", "arguments": {"days": 7}}'

# Send WhatsApp message
curl -X POST http://localhost:8080/tools/send_whatsapp \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Hello from MCP!"}'
```

## ☸️ Kubernetes/Rancher Deployment

See the `kubernetes/` directory for full deployment manifests:

```bash
# Create namespace and deploy
kubectl create namespace wednesday
kubectl apply -f kubernetes/ -n wednesday
```

For Rancher Fleet (GitOps):
1. Import this repo in Rancher Fleet
2. Fleet uses `kubernetes/fleet.yaml` for configuration
3. Changes auto-deploy on git push

## 🔧 Configuration

### Environment Variables

#### Core Services
| Variable | Required | Description |
|----------|----------|-------------|
| `BYTEZ_API_KEY` | Yes* | Bytez AI API key |
| `GEMINI_API_KEY` | No | Google Gemini fallback |
| `SPOTIFY_CLIENT_ID` | No | Spotify integration |
| `SPOTIFY_SECRET` | No | Spotify integration |
| `WAHA_URL` | No | WhatsApp service URL |
| `MCP_PORT` | No | HTTP server port (default: 8080) |
| `MCP_HOST` | No | HTTP server host (default: 0.0.0.0) |

#### JARVIS Advanced Features
| Variable | Required | Description |
|----------|----------|-------------|
| `ELEVENLABS_API_KEY` | No | ElevenLabs premium voice synthesis |
| `ELEVENLABS_JARVIS_VOICE_ID` | No | JARVIS voice ID |
| `ELEVENLABS_FRIDAY_VOICE_ID` | No | FRIDAY voice ID |
| `IFTTT_WEBHOOK_KEY` | No | IFTTT smart home triggers |
| `HOME_ASSISTANT_URL` | No | Home Assistant API URL |
| `HOME_ASSISTANT_TOKEN` | No | Home Assistant long-lived access token |
| `PHILIPS_HUE_BRIDGE_IP` | No | Philips Hue Bridge IP |
| `PHILIPS_HUE_USERNAME` | No | Philips Hue username |
| `SMARTTHINGS_TOKEN` | No | SmartThings API token |
| `SECURITY_RATE_LIMIT` | No | Rate limit per minute (default: 30) |
| `WHITELISTED_PHONES` | No | Comma-separated trusted phone numbers |

*At least one AI key required for chat functionality

### VS Code / Cursor Integration

Add to your MCP settings:

```json
{
  "mcpServers": {
    "wednesday": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/Wednesday_Whatsapp_assistant",
      "env": {
        "BYTEZ_API_KEY": "your_key"
      }
    }
  }
}
```

## 📁 Project Structure

```
mcp_server/
├── __init__.py           # Package info
├── server.py             # Main MCP server (STDIO)
└── http_server.py        # HTTP/SSE transport

kubernetes/
├── README.md             # Deployment guide
├── configmap.yaml        # Configuration
├── secrets.yaml          # API keys (template)
├── mcp-server-deployment.yaml
├── assistant-deployment.yaml
├── whatsapp-deployment.yaml
├── pvc.yaml              # Persistent storage
├── ingress.yaml          # External access
├── hpa.yaml              # Autoscaling
└── fleet.yaml            # Rancher Fleet config
```

## 🛠️ Available Tools

### chat
Send a message to the AI assistant.
```json
{
  "message": "What's the weather in New York?",
  "phone": "optional_user_id",
  "include_history": true
}
```

### send_whatsapp
Send a WhatsApp message.
```json
{
  "to": "+1234567890",
  "message": "Hello!"
}
```

### get_calendar_events
Get upcoming calendar events.
```json
{
  "days": 7,
  "max_results": 10
}
```

### create_calendar_event
Create a new calendar event.
```json
{
  "title": "Team Meeting",
  "start_time": "2024-01-15T10:00:00",
  "end_time": "2024-01-15T11:00:00",
  "description": "Weekly sync",
  "location": "Conference Room A"
}
```

### get_emails
Fetch emails from Gmail.
```json
{
  "max_results": 10,
  "query": "from:boss@company.com",
  "unread_only": true
}
```

### send_email
Send an email via Gmail.
```json
{
  "to": "recipient@example.com",
  "subject": "Meeting Notes",
  "body": "Here are the notes from today's meeting..."
}
```

### spotify_play
Search and play music on Spotify.
```json
{
  "query": "Bohemian Rhapsody",
  "type": "track"
}
```

### spotify_control
Control Spotify playback.
```json
{
  "action": "next"
}
```
Actions: `play`, `pause`, `next`, `previous`, `shuffle_on`, `shuffle_off`, `repeat_track`, `repeat_off`

### get_weather
Get weather information.
```json
{
  "location": "New York",
  "days": 3
}
```

### get_news
Get news headlines.
```json
{
  "category": "technology",
  "query": "AI",
  "count": 5
}
```

### service_status
Check all service statuses.
```json
{}
```

## 🔐 Security Notes

1. **Never commit secrets** - Use Kubernetes secrets or environment variables
2. **Network policies** - Restrict MCP server access to internal services
3. **Authentication** - Add API key auth for production HTTP endpoints
4. **TLS** - Use HTTPS via ingress controller

## 📝 License

MIT License - See main project LICENSE file.
