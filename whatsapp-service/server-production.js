const express = require('express');
const fs = require('fs-extra');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const ENABLE_REAL_WHATSAPP = process.env.ENABLE_REAL_WHATSAPP === 'true';

// Middleware
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true }));

// Global state
let whatsappClient = null;
let isClientReady = false;
let qrCodeData = null;
let lastQRTime = null;

// Configuration
const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;
const WEBHOOK_EVENTS = (process.env.WHATSAPP_HOOK_EVENTS || 'message').split(',');
const SESSION_PATH = './session';

// Create session directory
fs.ensureDirSync(SESSION_PATH);

console.log(`🔧 WhatsApp Service Mode: ${ENABLE_REAL_WHATSAPP ? 'PRODUCTION (Real WhatsApp)' : 'MOCK (Testing)'}`);

// Initialize WhatsApp client
async function initializeClient() {
    console.log('🚀 Initializing WhatsApp client...');
    
    if (ENABLE_REAL_WHATSAPP) {
        // Production mode with real WhatsApp Web.js
        try {
            const { Client, LocalAuth } = require('whatsapp-web.js');
            const qrcode = require('qr-terminal');
            
            whatsappClient = new Client({
                authStrategy: new LocalAuth({
                    dataPath: SESSION_PATH
                }),
                puppeteer: {
                    headless: process.env.PUPPETEER_HEADLESS !== 'false',
                    args: (process.env.PUPPETEER_ARGS || '--no-sandbox,--disable-setuid-sandbox,--disable-dev-shm-usage').split(',')
                }
            });

            // QR Code generation
            whatsappClient.on('qr', (qr) => {
                console.log('📱 QR Code received for WhatsApp authentication');
                qrCodeData = qr;
                lastQRTime = new Date();
                
                if (process.env.SHOW_QR !== 'false') {
                    qrcode.generate(qr, { small: true });
                }
            });

            // Client ready
            whatsappClient.on('ready', () => {
                console.log('✅ WhatsApp client is ready!');
                isClientReady = true;
                qrCodeData = null;
            });

            // Authentication success
            whatsappClient.on('authenticated', () => {
                console.log('🔐 Authenticated successfully');
            });

            // Authentication failure
            whatsappClient.on('auth_failure', (msg) => {
                console.error('❌ Authentication failed:', msg);
                isClientReady = false;
            });

            // Client disconnected
            whatsappClient.on('disconnected', (reason) => {
                console.log('📴 Client disconnected:', reason);
                isClientReady = false;
                qrCodeData = null;
                
                // Restart client after disconnection
                setTimeout(() => {
                    console.log('🔄 Restarting client...');
                    initializeClient();
                }, 5000);
            });

            // Message received
            whatsappClient.on('message', async (message) => {
                if (WEBHOOK_EVENTS.includes('message') && WEBHOOK_URL) {
                    await forwardToWebhook({
                        id: message.id._serialized,
                        from: message.from,
                        to: message.to,
                        body: message.body,
                        type: message.type,
                        timestamp: message.timestamp,
                        fromMe: message.fromMe,
                        hasMedia: message.hasMedia
                    });
                }
            });

            // Initialize the client
            whatsappClient.initialize();
            
        } catch (error) {
            console.error('❌ Failed to initialize WhatsApp client:', error.message);
            console.log('🔄 Falling back to mock mode...');
            initializeMockClient();
        }
    } else {
        // Mock mode for testing
        initializeMockClient();
    }
}

function initializeMockClient() {
    console.log('🧪 Initializing mock WhatsApp client...');
    
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

// Send message function
async function sendMessage(chatId, text) {
    if (ENABLE_REAL_WHATSAPP && whatsappClient) {
        // Production mode - real WhatsApp sending
        try {
            await whatsappClient.sendMessage(chatId, text);
            console.log(`📤 Sent WhatsApp message to ${chatId}: ${text}`);
            return true;
        } catch (error) {
            console.error('❌ WhatsApp send error:', error);
            return false;
        }
    } else {
        // Mock mode - just log the message
        console.log(`📤 Mock sending to ${chatId}: ${text}`);
        return true;
    }
}

// Forward message to webhook
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

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        whatsapp_ready: isClientReady,
        has_qr: !!qrCodeData,
        timestamp: new Date().toISOString(),
        service: 'lightweight-whatsapp-service'
    });
});

// Session status (WAHA compatibility)
app.get('/api/sessions/:sessionName', (req, res) => {
    const status = isClientReady ? 'working' : 'starting';
    res.json({
        name: req.params.sessionName,
        status: status,
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        me: isClientReady ? { id: 'test@c.us', name: 'Test User' } : null
    });
});

// Create session (WAHA compatibility)
app.post('/api/sessions/:sessionName', (req, res) => {
    if (!whatsappClient && !isClientReady) {
        initializeClient();
    }
    res.json({ success: true, session: req.params.sessionName });
});

// Start session (WAHA compatibility)
app.post('/api/sessions/:sessionName/start', (req, res) => {
    if (!whatsappClient && !isClientReady) {
        initializeClient();
    }
    res.json({ success: true, session: req.params.sessionName });
});

// Send text message (WAHA compatibility)
app.post('/api/sendText', async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ 
            error: 'WhatsApp client not ready',
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    }

    const { chatId, text } = req.body;
    
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text are required' });
    }

    try {
        const success = await sendMessage(chatId, text);
        if (success) {
            res.json({ 
                success: true, 
                message: 'Message sent successfully',
                mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
                chatId: chatId,
                text: text
            });
        } else {
            res.status(500).json({ error: 'Failed to send message' });
        }
    } catch (error) {
        console.error('❌ Send message error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Alternative send message endpoint
app.post('/api/sessions/:sessionName/messages/text', async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ 
            error: 'WhatsApp client not ready',
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    }

    const { chatId, text } = req.body;
    
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text are required' });
    }

    try {
        const success = await sendMessage(chatId, text);
        if (success) {
            res.json({ 
                success: true, 
                message: 'Message sent successfully',
                mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
                chatId: chatId,
                text: text
            });
        } else {
            res.status(500).json({ error: 'Failed to send message' });
        }
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
            timestamp: lastQRTime.toISOString(),
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    } else if (isClientReady) {
        res.json({ 
            status: 'authenticated', 
            message: 'Client is ready',
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    } else {
        res.json({ 
            status: 'waiting', 
            message: 'Waiting for QR code',
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    }
});

// Screenshot endpoint (QR code image)
app.get('/api/screenshot', (req, res) => {
    if (qrCodeData) {
        res.json({ 
            qr: qrCodeData,
            format: 'text',
            timestamp: lastQRTime.toISOString(),
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    } else {
        res.status(404).json({ error: 'No QR code available' });
    }
});

// Simulate webhook endpoint for testing (mock mode only)
app.post('/test/simulate-message', async (req, res) => {
    if (ENABLE_REAL_WHATSAPP) {
        return res.status(400).json({ 
            error: 'Test simulation not available in production mode',
            mode: 'production'
        });
    }
    
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
    res.json({ 
        success: true, 
        message: 'Message simulated and forwarded to webhook',
        mode: 'mock'
    });
});

// Service info endpoint
app.get('/api/info', (req, res) => {
    res.json({
        service: 'lightweight-whatsapp-service',
        version: '1.0.0',
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        features: {
            real_whatsapp: ENABLE_REAL_WHATSAPP,
            webhook_forwarding: !!WEBHOOK_URL,
            qr_display: process.env.SHOW_QR !== 'false',
            test_simulation: !ENABLE_REAL_WHATSAPP
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
    
    if (!ENABLE_REAL_WHATSAPP) {
        console.log(`🧪 Test message: POST http://localhost:${PORT}/test/simulate-message`);
    }
    
    // Initialize WhatsApp client
    initializeClient();
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n🛑 Shutting down gracefully...');
    if (whatsappClient && ENABLE_REAL_WHATSAPP) {
        await whatsappClient.destroy();
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\n🛑 Shutting down gracefully...');
    if (whatsappClient && ENABLE_REAL_WHATSAPP) {
        await whatsappClient.destroy();
    }
    process.exit(0);
});