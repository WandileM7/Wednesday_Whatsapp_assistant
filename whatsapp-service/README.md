# Lightweight WhatsApp Service

A memory-efficient alternative to WAHA (WhatsApp HTTP API) using whatsapp-web.js.

## Features

- **Lightweight**: Significantly lower memory usage compared to WAHA
- **API Compatible**: Drop-in replacement for WAHA with same endpoints
- **Reliable**: Built on battle-tested whatsapp-web.js library  
- **Easy Setup**: Simple authentication via QR code
- **Docker Ready**: Containerized for easy deployment

## Memory Comparison

| Service | Memory Usage | Docker Image Size |
|---------|-------------|-------------------|
| WAHA | ~400-600MB | ~1.2GB |
| This Service | ~150-250MB | ~400MB |

## API Endpoints

### Health Check
```
GET /health
```

### Session Management
```
GET /api/sessions/:sessionName
POST /api/sessions/:sessionName
POST /api/sessions/:sessionName/start
```

### Send Messages
```
POST /api/sendText
POST /api/sessions/:sessionName/messages/text
```

### QR Code Access
```
GET /api/qr
GET /api/screenshot
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | 3000 |
| `WHATSAPP_HOOK_URL` | Webhook URL for incoming messages | - |
| `WHATSAPP_HOOK_EVENTS` | Events to forward to webhook | message |
| `SHOW_QR` | Show QR code in terminal | true |

## Setup

### Docker Compose (Recommended)
```yaml
services:
  whatsapp-service:
    build: ./whatsapp-service
    ports:
      - "3000:3000"
    environment:
      - WHATSAPP_HOOK_URL=http://assistant:5000/webhook
      - WHATSAPP_HOOK_EVENTS=message
      - SHOW_QR=false
    volumes:
      - ./whatsapp-session:/app/session
```

### Local Development
```bash
cd whatsapp-service
npm install
npm start
```

## Authentication

1. Start the service
2. Check QR code: `curl http://localhost:3000/api/qr`
3. Scan QR code with WhatsApp mobile app
4. Service will be ready once authenticated

## Migration from WAHA

This service is designed as a drop-in replacement for WAHA:

1. Replace WAHA service in docker-compose.yaml
2. Update image from `devlikeapro/waha:latest` to `build: ./whatsapp-service`
3. Keep same environment variables
4. No changes needed to Python application code

## Troubleshooting

### Service not starting
- Check Docker memory allocation (minimum 512MB recommended)
- Verify Node.js version (18+ required)

### Authentication issues
- Delete session folder and restart for fresh authentication
- Check QR code endpoint: `/api/qr`

### Message sending failures
- Verify WhatsApp connection with `/health` endpoint
- Check webhook URL configuration
- Ensure proper phone number format (includes @c.us)