FROM node:24-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-common \
    chromium-driver \
    fonts-freefont-ttf \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Tell Puppeteer where Chromium is
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Copy package files
COPY whatsapp-service/package.json whatsapp-service/package-lock.json ./

# Install dependencies
ARG ENABLE_REAL_WHATSAPP=true
ENV ENABLE_REAL_WHATSAPP=${ENABLE_REAL_WHATSAPP}

RUN npm install

# Copy application files
COPY whatsapp-service/ .

# Create session directory
RUN mkdir -p session

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

CMD ["npm", "start"]
