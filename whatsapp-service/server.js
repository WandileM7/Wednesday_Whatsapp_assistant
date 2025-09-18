const express = require('express');
const fs = require('fs-extra');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));

// Global state
let isClientReady = false;
let qrCodeData = null;
let lastQRTime = null;
let whatsappClient = null;

// Configuration
const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;
const WEBHOOK_EVENTS = (process.env.WHATSAPP_HOOK_EVENTS || 'message').split(',');
const SESSION_PATH = './session';

// Create session directory
fs.ensureDirSync(SESSION_PATH);

// Simulate WhatsApp client initialization (for testing without puppeteer)
function initializeClient() {
    console.log('🚀 Initializing WhatsApp client...');
    
    // Check if session exists
    const sessionFile = path.join(SESSION_PATH, 'session.json');
    
    if (fs.existsSync(sessionFile)) {
        console.log('✅ Found existing session, marking as ready');
        isClientReady = true;
        qrCodeData = null;
    } else {
        console.log('📱 No session found, generating QR code');
        // Generate a dummy QR code for testing
        qrCodeData = 'test-qr-code-data-' + Date.now();
        lastQRTime = new Date();
        isClientReady = false;
        
        // Auto-authenticate after 30 seconds for testing
        setTimeout(() => {
            console.log('🔐 Auto-authenticating for testing...');
            fs.writeJsonSync(sessionFile, { authenticated: true, timestamp: Date.now() });
            isClientReady = true;
            qrCodeData = null;
        }, 30000);
    }
}

// Forward message to webhook (simulation)
async function forwardToWebhook(message) {
    try {
        const webhookData = {
            event: 'message',
            session: 'default',
            payload: message
        };

        if (WEBHOOK_URL) {
            const response = await fetch(WEBHOOK_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(webhookData)
            });

            if (!response.ok) {
                console.warn(`⚠️ Webhook failed: ${response.status}`);
            }
        }
    } catch (error) {
        console.error('❌ Webhook error:', error.message);
    }
}

// API Routes

// Health check with memory monitoring
app.get('/health', (req, res) => {
    const memUsage = process.memoryUsage();
    const heapUsedMB = Math.round(memUsage.heapUsed / 1024 / 1024);
    const heapTotalMB = Math.round(memUsage.heapTotal / 1024 / 1024);
    
    res.json({
        status: 'healthy',
        mode: 'mock',
        whatsapp_ready: isClientReady,
        has_qr: !!qrCodeData,
        memory: {
            heap_used_mb: heapUsedMB,
            heap_total_mb: heapTotalMB,
            memory_efficient: heapUsedMB < 100 // Flag for memory efficiency
        },
        timestamp: new Date().toISOString(),
        service: 'lightweight-whatsapp-service'
    });
});

// Memory monitoring endpoint
app.get('/api/memory', (req, res) => {
    const memUsage = process.memoryUsage();
    res.json({
        memory: {
            rss_mb: Math.round(memUsage.rss / 1024 / 1024),
            heap_total_mb: Math.round(memUsage.heapTotal / 1024 / 1024),
            heap_used_mb: Math.round(memUsage.heapUsed / 1024 / 1024),
            external_mb: Math.round(memUsage.external / 1024 / 1024),
            array_buffers_mb: Math.round(memUsage.arrayBuffers / 1024 / 1024)
        },
        status: 'ok',
        timestamp: new Date().toISOString()
    });
});

// Session status (WAHA compatibility)
app.get('/api/sessions/:sessionName', (req, res) => {
    const status = isClientReady ? 'working' : 'starting';
    res.json({
        name: req.params.sessionName,
        status: status,
        me: isClientReady ? { id: 'test@c.us', name: 'Test User' } : null
    });
});

// Create session (WAHA compatibility)
app.post('/api/sessions/:sessionName', (req, res) => {
    initializeClient();
    res.json({ success: true, session: req.params.sessionName });
});

// Start session (WAHA compatibility)
app.post('/api/sessions/:sessionName/start', (req, res) => {
    initializeClient();
    res.json({ success: true, session: req.params.sessionName });
});

// Send text message (WAHA compatibility)
app.post('/api/sendText', async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ error: 'WhatsApp client not ready' });
    }

    const { chatId, text } = req.body;
    
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text are required' });
    }

    try {
        // Simulate message sending
        console.log(`📤 Sending message to ${chatId}: ${text}`);
        
        // For now, just log the message (in real implementation, this would send via WhatsApp)
        res.json({ 
            success: true, 
            message: 'Message sent successfully',
            chatId: chatId,
            text: text
        });
    } catch (error) {
        console.error('❌ Send message error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Alternative send message endpoint
app.post('/api/sessions/:sessionName/messages/text', async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ error: 'WhatsApp client not ready' });
    }

    const { chatId, text } = req.body;
    
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text are required' });
    }

    try {
        console.log(`📤 Sending message to ${chatId}: ${text}`);
        res.json({ 
            success: true, 
            message: 'Message sent successfully',
            chatId: chatId,
            text: text
        });
    } catch (error) {
        console.error('❌ Send message error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Get QR code
app.get('/api/qr', (req, res) => {
    if (qrCodeData) {
        res.json({ 
            qr: qrCodeData, 
            timestamp: lastQRTime.toISOString() 
        });
    } else if (isClientReady) {
        res.json({ 
            status: 'authenticated', 
            message: 'Client is ready' 
        });
    } else {
        res.json({ 
            status: 'waiting', 
            message: 'Waiting for QR code' 
        });
    }
});

// Screenshot endpoint (QR code image)
app.get('/api/screenshot', (req, res) => {
    if (qrCodeData) {
        res.json({ 
            qr: qrCodeData,
            format: 'text',
            timestamp: lastQRTime.toISOString()
        });
    } else {
        res.status(404).json({ error: 'No QR code available' });
    }
});

// Simulate webhook endpoint for testing
app.post('/test/simulate-message', async (req, res) => {
    const { from, text } = req.body;
    
    if (!from || !text) {
        return res.status(400).json({ error: 'from and text are required' });
    }
    
    const message = {
        id: 'msg_' + Date.now(),
        from: from,
        to: 'test@c.us',
        body: text,
        type: 'chat',
        timestamp: Date.now(),
        fromMe: false,
        hasMedia: false
    };
    
    await forwardToWebhook(message);
    res.json({ success: true, message: 'Message simulated and forwarded to webhook' });
});

// Service info endpoint
app.get('/api/info', (req, res) => {
    res.json({
        service: 'lightweight-whatsapp-service',
        version: '1.0.0',
        mode: 'mock',
        features: {
            real_whatsapp: false,
            webhook_forwarding: !!WEBHOOK_URL,
            qr_display: process.env.SHOW_QR !== 'false',
            test_simulation: true
        },
        memory_efficient: true,
        waha_compatible: true
    });
});

// Error handling middleware
app.use((error, req, res, next) => {
    console.error('❌ Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
});

// Start server
app.listen(PORT, () => {
    console.log(`🌐 Lightweight WhatsApp Service running on port ${PORT}`);
    console.log(`📋 Health check: http://localhost:${PORT}/health`);
    console.log(`📱 QR code: http://localhost:${PORT}/api/qr`);
    console.log(`ℹ️ Service info: http://localhost:${PORT}/api/info`);
    console.log(`🧪 Test message: POST http://localhost:${PORT}/test/simulate-message`);
    
    // Initialize WhatsApp client
    initializeClient();
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n🛑 Shutting down gracefully...');
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log('\n🛑 Shutting down gracefully...');
    process.exit(0);
});