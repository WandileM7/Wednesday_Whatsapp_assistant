# Memory-Optimized Production WhatsApp Service
FROM node:20-alpine AS base
WORKDIR /app

# Install system dependencies for WhatsApp Web.js (production-only)
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    && rm -rf /var/cache/apk/*

# Set Puppeteer to use system Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Copy package files
COPY whatsapp-service/package.json whatsapp-service/package-lock.json ./

# Install dependencies - production only
RUN npm ci --only=production --silent && npm cache clean --force

# Memory optimization environment variables
ENV NODE_ENV=production \
    NODE_OPTIONS="--max-old-space-size=256 --expose-gc" \
    SESSION_PATH=/app/session \
    SHOW_QR=false \
    MAX_RECONNECT_ATTEMPTS=2 \
    INITIAL_RECONNECT_DELAY=10000 \
    MEMORY_THRESHOLD_MB=300 \
    MAX_HEAP_SIZE_MB=256 \
    GC_INTERVAL_MS=15000 \
    ENABLE_REAL_WHATSAPP=true

# Copy application files
COPY whatsapp-service/ .

# Create session directory with proper permissions
RUN mkdir -p session && chmod 755 session

# Set up non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S whatsapp -u 1001 -G nodejs && \
    chown -R whatsapp:nodejs /app
USER whatsapp

EXPOSE 3000

# Optimized health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

# Start WhatsApp service
CMD ["npm", "start"]
