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
COPY whatsapp-servicepackage.json whatsapp-servicepackage-lock.json ./

# Install dependencies conditionally
ARG ENABLE_REAL_WHATSAPP=true
ENV ENABLE_REAL_WHATSAPP=${ENABLE_REAL_WHATSAPP}

# Verify package.json exists before npm install
RUN test -f package.json || (echo "Error: package.json not found" && exit 1)

# Install all dependencies (now that qrcode-terminal and whatsapp-web.js are regular dependencies)
# Set PUPPETEER_SKIP_CHROMIUM_DOWNLOAD to skip downloading Chrome (will use system Chrome)
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

RUN npm install

# Copy application files
COPY whatsapp-service/ .

# Create session directory
RUN mkdir -p session

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

# Start the application
CMD ["npm", "start"]
