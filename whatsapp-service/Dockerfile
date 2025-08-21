FROM node:22-alpine

WORKDIR /app

# Install system dependencies for optional packages
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    freetype-dev \
    harfbuzz \
    ca-certificates \
    ttf-freefont

# Tell Puppeteer to skip installing Chromium (we installed it above)
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Copy package files
COPY package*.json ./

# Install dependencies conditionally
ARG ENABLE_REAL_WHATSAPP=false
ENV ENABLE_REAL_WHATSAPP=${ENABLE_REAL_WHATSAPP}

RUN if [ "$ENABLE_REAL_WHATSAPP" = "true" ]; then \
        npm install; \
    else \
        npm install --omit=optional; \
    fi

# Copy application files
COPY . .

# Create session directory
RUN mkdir -p session

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

# Start the application
CMD ["npm", "start"]