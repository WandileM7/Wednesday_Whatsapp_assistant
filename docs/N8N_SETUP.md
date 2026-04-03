# n8n Self-Hosted Setup Guide

This guide covers setting up the self-hosted n8n workflow automation platform for Wednesday WhatsApp Assistant.

## Why n8n?

n8n provides:
- **Free self-hosting** - No usage limits when self-hosted
- **MCP (Model Context Protocol)** - AI agents with tool access
- **Pre-built integrations** - Gmail, Calendar, Tasks, Sheets, Contacts
- **Visual workflow builder** - Easy to customize and extend
- **Memory/conversation history** - Per-user conversation context

## Quick Start

### 1. Start Services

```bash
docker compose up -d
```

This starts:
- **n8n** on port 5678 (workflow automation)
- **WhatsApp Service** on port 3000 (WAHA)
- **Assistant** on port 5000 (Flask app)

### 2. Access n8n Dashboard

Open http://localhost:5678

Default credentials:
- Username: `admin`
- Password: `wednesday123`

### 3. Import the Workflow

1. Go to **Workflows** → **Import from File**
2. Select `n8n/workflow-jarvis-whatsapp.json`
3. The workflow will load with all nodes configured

### 4. Configure Credentials

You need to set up credentials for each service:

#### OpenAI (Required for AI Agent)
1. Click **Credentials** → **New Credential**
2. Select **OpenAI API**
3. Enter your API key from https://platform.openai.com/api-keys

#### Gmail (Email Management)
1. Click **Credentials** → **New Credential**
2. Select **Gmail OAuth2 API**
3. Follow OAuth setup instructions
4. Required scopes: `gmail.send`, `gmail.readonly`, `gmail.modify`

#### Google Calendar
1. Click **Credentials** → **New Credential**
2. Select **Google Calendar OAuth2 API**
3. Follow OAuth setup instructions

#### Google Tasks
1. Click **Credentials** → **New Credential**
2. Select **Google Tasks OAuth2 API**
3. Follow OAuth setup instructions

#### Google Sheets (Expense Tracking)
1. Click **Credentials** → **New Credential**
2. Select **Google Sheets OAuth2 API**
3. Follow OAuth setup instructions
4. Create a spreadsheet for expenses and note the ID

#### Google Contacts
1. Click **Credentials** → **New Credential**
2. Select **Google Contacts OAuth2 API**
3. Follow OAuth setup instructions

### 5. Configure Workflow Settings

Edit these nodes with your specific settings:

1. **Filter Allowed Users** - Add your WhatsApp number to restrict access
2. **Google Calendar nodes** - Select your calendar
3. **Google Sheets nodes** - Select your expense spreadsheet
4. **Google Tasks nodes** - Select your task list

### 6. Activate the Workflow

1. Click the **Active** toggle in the top-right
2. The webhook URL will be shown: `http://localhost:5678/webhook/whatsapp-webhook`

### 7. Configure WhatsApp to Use n8n

Option A: Direct webhook (n8n handles everything)
```bash
# In docker-compose.yaml
WHATSAPP_HOOK_URL=http://n8n:5678/webhook/whatsapp-webhook
```

Option B: Hybrid mode (assistant routes to n8n when needed)
```bash
# In .env
N8N_ENABLED=true
N8N_WEBHOOK_URL=http://n8n:5678
```

## Environment Variables

Add these to your `.env` file:

```bash
# n8n Configuration
N8N_ENABLED=true
N8N_WEBHOOK_URL=http://n8n:5678
N8N_WEBHOOK_PATH=/webhook/whatsapp-webhook
N8N_USER=admin
N8N_PASSWORD=your-secure-password
N8N_ENCRYPTION_KEY=your-encryption-key-32-chars-min

# For production, use a proper webhook URL
# N8N_WEBHOOK_URL=https://your-domain.com

# OpenAI for n8n AI Agent
OPENAI_API_KEY=sk-your-openai-key

# Optional: Allowed WhatsApp numbers (comma-separated)
ALLOWED_WHATSAPP_NUMBERS=27123456789,27987654321
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    WhatsApp     │────▶│  WhatsApp Svc   │────▶│    n8n         │
│    (User)       │     │  (WAHA:3000)    │     │  (Port 5678)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                              ┌──────────────────────────┴──────────────────────────┐
                              │                                                      │
                    ┌─────────▼─────────┐  ┌─────────────────┐  ┌─────────────────┐
                    │   AI Agent        │  │   MCP Servers   │  │  Google APIs    │
                    │   (OpenAI/Gemini) │  │   (gmail/cal)   │  │  (OAuth2)       │
                    └───────────────────┘  └─────────────────┘  └─────────────────┘
```

## Workflow Features

### AI Agent Capabilities

The Wednesday AI Agent can:
- **Email**: Send, reply, draft, search emails
- **Calendar**: Create events, check availability, reschedule
- **Tasks**: Create, complete, delete to-dos
- **Expenses**: Log and query expenses via Google Sheets
- **Contacts**: Look up contact information

### Message Flow

1. WhatsApp message arrives at WAHA service
2. WAHA forwards to n8n webhook
3. n8n filters authorized users
4. AI Agent processes request with available tools
5. Response sent back to WhatsApp via HTTP request

### Conversation Memory

The workflow maintains per-user conversation memory using:
- Session key based on WhatsApp chat ID
- Buffer window for context (last N messages)
- Automatic cleanup of old sessions

## Customization

### Adding New Tools

1. Add a new node (e.g., HTTP Request, database, etc.)
2. Connect it to the appropriate MCP Trigger
3. Configure AI description for the agent to understand its purpose

### Changing the AI Model

1. Click on **OpenAI Chat Model** node
2. Change model to `gpt-4o`, `gpt-4-turbo`, or `gpt-3.5-turbo`
3. Alternatively, swap for Gemini using **Google Gemini Chat Model** node

### Adding Voice Support

The workflow includes a Voice branch (currently empty). To enable:
1. Add ElevenLabs nodes for transcription
2. Connect to AI agent
3. Add text-to-speech for responses

## Troubleshooting

### n8n not starting
```bash
docker logs n8n
```
Check for port conflicts (5678) or memory issues.

### Webhook not receiving messages
1. Verify WAHA webhook URL is correct
2. Check n8n workflow is activated
3. Look at n8n Executions for errors

### OAuth credential issues
1. Ensure Google Cloud Console has correct redirect URIs
2. Add `http://localhost:5678/rest/oauth2-credential/callback`

### AI Agent not responding
1. Check OpenAI API key is valid
2. Verify model has sufficient quota
3. Review execution logs in n8n

## Production Deployment

For production:

1. **Use HTTPS** - Set `WEBHOOK_URL` to your domain
2. **Secure credentials** - Use n8n's credential encryption
3. **Rate limiting** - Configure in the workflow
4. **Monitoring** - Enable execution logging
5. **Backup** - Persist n8n_data volume

```yaml
# docker-compose.prod.yaml
n8n:
  environment:
    - WEBHOOK_URL=https://n8n.yourdomain.com
    - N8N_PROTOCOL=https
    - N8N_SSL_KEY=/certs/privkey.pem
    - N8N_SSL_CERT=/certs/fullchain.pem
```

## Resources

- [n8n Documentation](https://docs.n8n.io/)
- [n8n AI Agents Guide](https://docs.n8n.io/langchain/)
- [MCP Integration](https://docs.n8n.io/integrations/builtin/cluster-nodes/sub-nodes/n8n-nodes-langchain.mcpclienttool/)
- [Google OAuth Setup](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-generic/)
