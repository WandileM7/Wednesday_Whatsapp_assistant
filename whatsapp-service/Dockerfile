# Baileys WhatsApp Service - NO Chromium Required!
# Memory usage: ~50-100MB (perfect for Render free tier)
FROM node:20-alpine AS base
WORKDIR /app

# Minimal system dependencies for native modules
RUN apk add --no-cache \
    ca-certificates \
    python3 \
    make \
    g++ \
    git \
    && rm -rf /var/cache/apk/*

# Copy package files
COPY whatsapp-service/package.json ./

# Install dependencies
RUN npm install && npm cache clean --force

# Environment variables - keep simple, no experimental flags
ENV NODE_ENV=production \
    SESSION_PATH=/app/session \
    SHOW_QR=false \
    MAX_RECONNECT_ATTEMPTS=5 \
    ENABLE_REAL_WHATSAPP=true

# Copy application files
COPY whatsapp-service/ .

# Create session directory with proper permissions
RUN mkdir -p session uploads && chmod 755 session uploads

# Set up non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S whatsapp -u 1001 -G nodejs && \
    chown -R whatsapp:nodejs /app
USER whatsapp

EXPOSE 3000

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

# Start Baileys WhatsApp service
CMD ["npm", "start"]
