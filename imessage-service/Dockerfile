FROM node:20-alpine
WORKDIR /app

# ffmpeg: ensureM4a transcodes the backend's ogg/opus TTS into the M4A that
# Messages requires for voice notes. Without it voice replies fall back to text.
RUN apk add --no-cache ca-certificates ffmpeg && rm -rf /var/cache/apk/*

COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY . .

ENV NODE_ENV=production PORT=3100

RUN addgroup -g 1001 -S nodejs && \
    adduser -S imessage -u 1001 -G nodejs && \
    chown -R imessage:nodejs /app
USER imessage

EXPOSE 3100

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3100/health', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["npm", "start"]
