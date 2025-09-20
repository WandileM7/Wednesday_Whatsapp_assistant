/**
 * Test version of Ultra-Minimal WhatsApp Service
 * For testing without Chrome/Puppeteer
 */

const express = require('express');

const app = express();
const PORT = process.env.PORT || 3000;

// Ultra-minimal configuration
app.use(express.json({ limit: '2mb' }));

// Mock state for testing
let isReady = true;
let qrCode = '';
let lastActivity = Date.now();

// Webhook configuration
const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;

// Memory cleanup every 5 minutes
setInterval(() => {
    if (global.gc) global.gc();
}, 300000);

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
        service: 'ultra-minimal-whatsapp-test'
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

// Send text message (mock)
app.post('/api/sendText', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp not ready' });
    }

    const { chatId, text } = req.body;
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text required' });
    }

    try {
        console.log(`📱 Mock sending text to ${chatId}: ${text}`);
        res.json({ success: true, mode: 'mock' });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Send media (mock)
app.post('/api/sendMedia', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ error: 'WhatsApp not ready' });
    }

    const { chatId, media, caption } = req.body;
    if (!chatId || !media) {
        return res.status(400).json({ error: 'chatId and media required' });
    }

    try {
        console.log(`📷 Mock sending media to ${chatId}: ${media.mimetype}`);
        res.json({ success: true, mode: 'mock' });
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
    isReady = true;
    res.json({ success: true });
});

// Start server
app.listen(PORT, () => {
    console.log(`🚀 Ultra-minimal WhatsApp service (TEST MODE) on port ${PORT}`);
    console.log('💾 Memory optimization: Maximum efficiency mode');
    console.log('🧪 Running in test mode - no real WhatsApp connection');
});

// Graceful shutdown
process.on('SIGTERM', () => {
    process.exit(0);
});