# Lightweight WhatsApp Service - Production Setup

## Overview

This service provides a memory-efficient alternative to WAHA using whatsapp-web.js. It offers both:
1. **Mock Mode** (current): For testing and development
2. **Production Mode**: With real WhatsApp Web integration

## Production Setup

### 1. Enable Real WhatsApp Integration

Set the environment variable to enable production mode:
```bash
ENABLE_REAL_WHATSAPP=true
```

### 2. Install Additional Dependencies

For production mode, install whatsapp-web.js:
```bash
cd whatsapp-service
npm install whatsapp-web.js qr-terminal
```

### 3. Docker Production Build

The service detects the mode automatically and installs dependencies accordingly:

```dockerfile
# Production Dockerfile includes conditional dependency installation
# Set ENABLE_REAL_WHATSAPP=true to enable real WhatsApp integration
```

### 4. Memory Requirements

| Mode | Memory Usage | Chrome Required |
|------|-------------|-----------------|
| Mock | ~50MB | No |
| Production | ~150-250MB | Yes |

### 5. Authentication Process

**Mock Mode:**
- Auto-authenticates after 30 seconds
- No QR scanning required
- Ideal for testing

**Production Mode:**
- Generates real QR code for WhatsApp Web
- Requires scanning with WhatsApp mobile app
- Persists session for reconnection

### 6. Environment Variables

```bash
# Service Configuration
PORT=3000
ENABLE_REAL_WHATSAPP=false  # Set to 'true' for production

# WhatsApp Integration
WHATSAPP_HOOK_URL=http://assistant:5000/webhook
WHATSAPP_HOOK_EVENTS=message
SHOW_QR=false

# Production Mode Settings (when ENABLE_REAL_WHATSAPP=true)
PUPPETEER_HEADLESS=true
PUPPETEER_ARGS="--no-sandbox,--disable-setuid-sandbox"
```

### 7. Deployment Modes

#### Development (Docker Compose)
```yaml
services:
  whatsapp-service:
    build: ./whatsapp-service
    environment:
      - ENABLE_REAL_WHATSAPP=false  # Mock mode
      - WHATSAPP_HOOK_URL=http://assistant:5000/webhook
```

#### Production (Render)
```yaml
envVars:
  - key: ENABLE_REAL_WHATSAPP
    value: "true"  # Enable real WhatsApp
  - key: WHATSAPP_HOOK_URL
    value: https://waha-gemini-assistant.onrender.com/webhook
```

## Memory Optimization Benefits

### WAHA vs Lightweight Service

| Metric | WAHA | Lightweight (Mock) | Lightweight (Production) |
|--------|------|-------------------|-------------------------|
| Docker Image | ~1.2GB | ~200MB | ~400MB |
| Runtime Memory | 400-600MB | ~50MB | 150-250MB |
| Dependencies | Redis, Complex | None | Chrome only |
| Startup Time | 2-3 mins | 5-10 secs | 30-60 secs |

### Why This Approach

1. **Gradual Migration**: Start with mock mode, upgrade to production
2. **Resource Efficiency**: Use mock mode for testing, production for real use
3. **Cost Optimization**: Mock mode stays within free tier limits
4. **Development Speed**: Faster iteration without WhatsApp dependencies

## API Compatibility

Both modes provide identical APIs:

| Endpoint | Mock Response | Production Response |
|----------|-------------|-------------------|
| `GET /health` | ✅ Ready after 30s | ✅ Ready after QR scan |
| `POST /api/sendText` | ✅ Logs message | ✅ Sends via WhatsApp |
| `GET /api/qr` | ✅ Test QR data | ✅ Real WhatsApp QR |
| `POST /api/sessions/*` | ✅ Mock session | ✅ Real session |

## Migration Path

1. **Phase 1**: Deploy mock mode (current implementation)
   - Test integration without WhatsApp dependencies
   - Verify memory improvements
   - Validate API compatibility

2. **Phase 2**: Enable production mode
   - Set `ENABLE_REAL_WHATSAPP=true`
   - Authenticate via QR code
   - Full WhatsApp functionality

3. **Phase 3**: Monitor and optimize
   - Track memory usage
   - Monitor uptime improvements
   - Fine-tune performance

## Troubleshooting

### Mock Mode Issues
- Check health endpoint: `curl /health`
- Verify logs for auto-authentication message
- Ensure webhook URL is accessible

### Production Mode Issues
- Check QR code generation: `curl /api/qr`
- Verify Chrome installation in container
- Monitor memory usage and limits
- Check session persistence in `/app/session`

## Additional Resources

- [WhatsApp Web.js Documentation](https://github.com/pedroslopez/whatsapp-web.js)
- [Puppeteer Performance Tips](https://developers.google.com/web/tools/puppeteer/troubleshooting)
- [Memory Optimization Guide](./WHATSAPP_SERVICE_MIGRATION.md)