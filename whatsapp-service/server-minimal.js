/**
 * Ultra-Minimal WhatsApp Service
 * Absolute minimum code for maximum memory efficiency
 * Full media support with minimal overhead
 */

const express = require('express');
const { Client, MessageMedia, LocalAuth } = require('whatsapp-web.js');

const app = express();
const PORT = process.env.PORT || 3000;

// Ultra-minimal configuration
app.use(express.json({ limit: '2mb' }));

// Global state
let client = null;
let isReady = false;
let qrCode = '';
let lastActivity = Date.now();

// Webhook configuration
const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;

// Memory cleanup every 5 minutes
setInterval(() => {
    if (global.gc) global.gc();
}, 300000);

// Initialize WhatsApp client with minimal settings
function initClient() {
    client = new Client({
        authStrategy: new LocalAuth({
            dataPath: process.env.SESSION_PATH || './session'
        }),
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--memory-pressure-off',
                '--max_old_space_size=128'
            ]
        }
    });

    client.on('qr', (qr) => {
        qrCode = qr;
        console.log('QR code received, scan to authenticate');
    });

    client.on('ready', () => {
        isReady = true;
        qrCode = '';
        console.log('✅ WhatsApp client ready');
    });

    client.on('message', async (message) => {
        lastActivity = Date.now();
        if (WEBHOOK_URL && !message.fromMe) {
            try {
                // Prepare message data
                const messageData = {
                    payload: {
                        id: message.id._serialized,
                        from: message.from,
                        to: message.to,
                        body: message.body,
                        type: message.type,
                        timestamp: message.timestamp,
                        fromMe: message.fromMe,
                        hasMedia: message.hasMedia
                    }
                };

                // Handle media messages
                if (message.hasMedia) {
                    messageData.payload.mediaKey = message.id._serialized;
                    messageData.payload.mimetype = message._data.mimetype;
                    messageData.payload.filename = message._data.filename;
                    if (message._data.caption) {
                        messageData.payload.caption = message._data.caption;
                    }
                }

                // Forward to webhook
                await fetch(WEBHOOK_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(messageData)
                });
            } catch (error) {
                console.error('Webhook error:', error.message);
            }
        }
    });

    client.on('disconnected', () => {
        isReady = false;
        console.log('❌ WhatsApp disconnected');
    });

    client.initialize();
}

// API Routes

// Health check
app.get('/health', (req, res) => {
    const memory = process.memoryUsage();
    res.json({
        status: 'healthy',
        whatsapp_ready: isReady,
        has_qr: !!qrCode,
        memory: {
            heap_used_mb: Math.round(memory.heapUsed / 1024 / 1024),
            heap_total_mb: Math.round(memory.heapTotal / 1024 / 1024)
        },
        last_activity: new Date(lastActivity).toISOString(),
        service: 'ultra-minimal-whatsapp'
    });
});

// Get QR code
app.get('/api/qr', (req, res) => {
    if (qrCode) {
        res.json({ qr: qrCode });
    } else if (isReady) {
        res.json({ status: 'authenticated' });
    } else {
        res.json({ status: 'initializing' });
    }
});

// Send text message
app.post('/api/sendText', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp not ready' });
    }

    const { chatId, text } = req.body;
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text required' });
    }

    try {
        await client.sendMessage(chatId, text);
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Send media
app.post('/api/sendMedia', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp not ready' });
    }

    const { chatId, media, caption } = req.body;
    if (!chatId || !media) {
        return res.status(400).json({ error: 'chatId and media required' });
    }

    try {
        const messageMedia = new MessageMedia(media.mimetype, media.data, media.filename);
        const options = caption ? { caption } : {};
        await client.sendMessage(chatId, messageMedia, options);
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Download media
app.get('/api/media/:messageId', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp not ready' });
    }

    try {
        const message = await client.getMessageById(req.params.messageId);
        if (message && message.hasMedia) {
            const media = await message.downloadMedia();
            res.set({
                'Content-Type': media.mimetype,
                'Content-Disposition': `attachment; filename="${media.filename || 'media'}"`
            });
            res.send(Buffer.from(media.data, 'base64'));
        } else {
            res.status(404).json({ error: 'Media not found' });
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Session management
app.get('/api/sessions/default', (req, res) => {
    res.json({
        name: 'default',
        status: isReady ? 'WORKING' : 'STOPPED',
        config: { webhooks: [{ url: WEBHOOK_URL }] }
    });
});

app.post('/api/sessions/default/start', (req, res) => {
    if (!client) {
        initClient();
    }
    res.json({ success: true });
});

// Start server
app.listen(PORT, () => {
    console.log(`🚀 Ultra-minimal WhatsApp service on port ${PORT}`);
    console.log('💾 Memory optimization: Maximum efficiency mode');
    initClient();
});

// Graceful shutdown
process.on('SIGTERM', () => {
    if (client) client.destroy();
    process.exit(0);
});