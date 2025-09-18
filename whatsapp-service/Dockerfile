# Multi-stage build for memory optimization
FROM node:20-alpine AS base
WORKDIR /app

# Copy package files for dependency analysis
COPY whatsapp-service/package.json whatsapp-service/package-lock.json ./

# Production mode - includes browser dependencies
FROM base AS production
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

# Install all dependencies for production mode
RUN npm ci --only=production --silent

# Mock mode - minimal dependencies
FROM base AS mock
# Install only core dependencies, skip browser-related packages
RUN npm install --silent express fs-extra && npm cache clean --force

# Final stage - choose based on build argument
FROM ${DOCKER_MODE:-production} AS final

# Memory optimization environment variables
ENV NODE_ENV=production \
    NODE_OPTIONS="--max-old-space-size=256" \
    SESSION_PATH=/app/session \
    SHOW_QR=false \
    MAX_RECONNECT_ATTEMPTS=3 \
    INITIAL_RECONNECT_DELAY=5000

# App files
COPY whatsapp-service/ .
RUN mkdir -p session && chmod 755 session

# Set proper permissions for non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001 && \
    chown -R nextjs:nodejs /app
USER nextjs

EXPOSE 3000

# Memory-efficient health check
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=2 \
  CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

CMD ["npm", "run", "start:optimized"]
