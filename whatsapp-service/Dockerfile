FROM node:24-slim
WORKDIR /app

# 1) Install Chromium and needed system libs (headless essentials)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-common \
    chromium-driver \
    fonts-freefont-ttf \
    fonts-liberation \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libxss1 \
    libxtst6 \
    libgbm1 \
    xdg-utils \
    && ln -s /usr/bin/chromium /usr/bin/chromium-browser \
    && rm -rf /var/lib/apt/lists/*

# 2) Sanity check: both names should resolve
RUN which chromium && which chromium-browser

# 3) Tell puppeteer where the browser is
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# App install
COPY whatsapp-service/package.json whatsapp-service/package-lock.json ./
ARG ENABLE_REAL_WHATSAPP=true
ENV ENABLE_REAL_WHATSAPP=${ENABLE_REAL_WHATSAPP}
RUN npm install

# App files
COPY whatsapp-service/ .
RUN mkdir -p session

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health', (res) => { process.exit(res.statusCode === 200 ? 0 : 1) }).on('error', () => process.exit(1))"

CMD ["npm", "start"]
