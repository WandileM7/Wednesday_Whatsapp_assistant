FROM node:18-alpine

# Install Chrome dependencies if production mode
ARG ENABLE_REAL_WHATSAPP=false
RUN if [ "$ENABLE_REAL_WHATSAPP" = "true" ]; then \
    apk add --no-cache chromium nss freetype freetype-dev harfbuzz ca-certificates ttf-freefont; \
    fi

# Set Puppeteer to use installed Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies conditionally
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