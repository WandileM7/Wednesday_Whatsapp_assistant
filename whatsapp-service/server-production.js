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
let reconnectAttempts = 0;
let maxReconnectAttempts = parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 5;
let reconnectDelay = parseInt(process.env.INITIAL_RECONNECT_DELAY) || 1000; // Start with 1 second
let isReconnecting = false;
let connectionHealthCheck = null;

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
            await initializeRealClient();
        } catch (error) {
            console.error('❌ Failed to initialize WhatsApp client:', error.message);
            
            // Only fall back to mock if we've exhausted reconnection attempts
            if (reconnectAttempts >= maxReconnectAttempts) {
                console.log('🔄 Max reconnection attempts reached, falling back to mock mode...');
                whatsappClient = null; // Clear the failed client
                stopConnectionHealthCheck();
                initializeMockClient();
            } else {
                console.log('🔄 Will attempt reconnection...');
                scheduleReconnection();
            }
        }
    } else {
        // Mock mode for testing
        initializeMockClient();
    }
}

// Reconnection logic with exponential backoff
function scheduleReconnection() {
    if (isReconnecting || reconnectAttempts >= maxReconnectAttempts) {
        return;
    }
    
    isReconnecting = true;
    reconnectAttempts++;
    
    console.log(`🔄 Scheduling reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts} in ${reconnectDelay}ms...`);
    
    setTimeout(async () => {
        try {
            console.log(`🔄 Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
            
            // Cleanup existing client
            if (whatsappClient) {
                try {
                    await whatsappClient.destroy();
                } catch (destroyError) {
                    console.log('⚠️ Error destroying old client:', destroyError.message);
                }
            }
            whatsappClient = null;
            
            // Reinitialize
            await initializeRealClient();
            
        } catch (error) {
            console.error(`❌ Reconnection attempt ${reconnectAttempts} failed:`, error.message);
            isReconnecting = false;
            
            // Exponential backoff with jitter
            reconnectDelay = Math.min(reconnectDelay * 2 + Math.random() * 1000, 30000);
            
            // Schedule next attempt if within limits
            if (reconnectAttempts < maxReconnectAttempts) {
                scheduleReconnection();
            } else {
                console.log('🚫 Max reconnection attempts reached, falling back to mock mode');
                stopConnectionHealthCheck();
                initializeMockClient();
            }
        }
    }, reconnectDelay);
}

// Connection health monitoring
function startConnectionHealthCheck() {
    // Clear any existing health check
    if (connectionHealthCheck) {
        clearInterval(connectionHealthCheck);
    }
    
    connectionHealthCheck = setInterval(async () => {
        if (!whatsappClient || !isClientReady) {
            return;
        }
        
        try {
            // Simple health check - try to get client state
            const state = await whatsappClient.getState();
            if (state !== 'CONNECTED') {
                console.log(`⚠️ Client state changed to: ${state}`);
                if (state === 'UNPAIRED' || state === 'UNLAUNCHED') {
                    console.log('🔄 Triggering reconnection due to unhealthy state');
                    isClientReady = false;
                    scheduleReconnection();
                }
            }
        } catch (error) {
            console.log('⚠️ Health check failed:', error.message);
            // Don't trigger reconnection on health check failure alone
            // Let the disconnected event handle it
        }
    }, 30000); // Check every 30 seconds
}

function stopConnectionHealthCheck() {
    if (connectionHealthCheck) {
        clearInterval(connectionHealthCheck);
        connectionHealthCheck = null;
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
    if (ENABLE_REAL_WHATSAPP && whatsappClient && isClientReady) {
        // Production mode - real WhatsApp sending (only if client is ready)
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
    if (!WEBHOOK_URL) return;

    try {
        // Ensure message object has required properties with fallbacks
        const webhookPayload = {
            payload: {
                id: message.id || 'unknown',
                from: message.from || '',
                to: message.to || '',
                body: message.body || '',
                type: message.type || 'text',
                timestamp: message.timestamp || Date.now(),
                fromMe: message.fromMe || false,
                hasMedia: message.hasMedia || false,
                // Add media properties with safe defaults
                mediaKey: message.mediaKey || null,
                mimetype: message.mimetype || null,
                data: message.data || null,
                filename: message.filename || null,
                caption: message.caption || null
            }
        };

        const response = await fetch(WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(webhookPayload)
        });

        if (response.ok) {
            console.log(`✅ Message forwarded to webhook: ${message.id}`);
        } else {
            console.error(`❌ Webhook forward failed: ${response.status} ${response.statusText}`);
        }
    } catch (error) {
        console.error('❌ Webhook forward error:', error.message);
    }
}

// Initialize WhatsApp client with improved message handling and stability
async function initializeRealClient() {
    const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
    
    // Enhanced Puppeteer configuration for cloud environments
    whatsappClient = new Client({
        authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-background-networking',
                '--disable-default-apps',
                '--no-default-browser-check',
                '--single-process',
                '--disable-ipc-flooding-protection'
            ],
            handleSIGINT: false,
            handleSIGTERM: false,
            handleSIGHUP: false
        }
    });

    // Connection health monitoring
    startConnectionHealthCheck();

    whatsappClient.on('qr', (qr) => {
        qrCodeData = qr;
        lastQRTime = new Date();
        isClientReady = false;
        reconnectAttempts = 0; // Reset reconnect attempts on new QR
        console.log('📱 QR Code received');
        
        if (process.env.SHOW_QR !== 'false') {
            const qrTerminal = require('qrcode-terminal');
            qrTerminal.generate(qr, { small: true });
        }
    });

    whatsappClient.on('ready', () => {
        console.log('✅ WhatsApp client is ready!');
        isClientReady = true;
        qrCodeData = null;
        reconnectAttempts = 0; // Reset reconnect attempts on successful connection
        reconnectDelay = 1000; // Reset delay
        isReconnecting = false;
    });

    whatsappClient.on('authenticated', () => {
        console.log('🔐 WhatsApp client authenticated');
    });

    whatsappClient.on('auth_failure', (msg) => {
        console.error('❌ Authentication failed:', msg);
        isClientReady = false;
        // Don't trigger reconnection on auth failure - need new QR
        scheduleReconnection();
    });

    whatsappClient.on('disconnected', (reason) => {
        console.log('⚠️ WhatsApp client disconnected:', reason);
        isClientReady = false;
        qrCodeData = null;
        
        // Only attempt reconnection if not already reconnecting and within limits
        if (!isReconnecting && reason !== 'LOGOUT') {
            scheduleReconnection();
        }
    });

    // Enhanced message handler with proper error handling
    whatsappClient.on('message', async (message) => {
        try {
            // Skip messages from self
            if (message.fromMe) return;

            console.log(`📨 Received message from ${message.from}: ${message.body || '[Media]'}`);
            
            // Create safe message object for webhook
            const safeMessage = {
                id: message.id._serialized || message.id,
                from: message.from,
                to: message.to,
                body: message.body || '',
                type: message.type || 'text',
                timestamp: message.timestamp,
                fromMe: message.fromMe,
                hasMedia: message.hasMedia || false
            };

            // Add media properties safely
            if (message.hasMedia) {
                try {
                    safeMessage.mediaKey = message.mediaKey || null;
                    safeMessage.mimetype = message._data?.mimetype || null;
                    safeMessage.filename = message._data?.filename || null;
                    safeMessage.caption = message._data?.caption || message.body || null;
                } catch (mediaError) {
                    console.log('⚠️ Media property extraction failed:', mediaError.message);
                    // Continue without media properties
                }
            }

            await forwardToWebhook(safeMessage);
            
        } catch (error) {
            console.error('❌ Message handler error:', error);
        }
    });

    try {
        await whatsappClient.initialize();
    } catch (error) {
        console.error('❌ WhatsApp client initialization failed:', error.message);
        throw error;
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

// Global error handlers
process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error.message);
    console.log('🔄 Attempting graceful recovery...');
    
    // Only fall back if we're in production mode and haven't exhausted reconnects
    if (ENABLE_REAL_WHATSAPP && !isClientReady && reconnectAttempts < maxReconnectAttempts) {
        console.log('🔄 Scheduling reconnection after uncaught exception...');
        scheduleReconnection();
    } else if (ENABLE_REAL_WHATSAPP && reconnectAttempts >= maxReconnectAttempts) {
        console.log('🧪 Falling back to mock WhatsApp client after max retries...');
        stopConnectionHealthCheck();
        initializeMockClient();
    }
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
    console.log('🔄 Attempting graceful recovery...');
    
    // Only fall back if we're in production mode and haven't exhausted reconnects
    if (ENABLE_REAL_WHATSAPP && !isClientReady && reconnectAttempts < maxReconnectAttempts) {
        console.log('🔄 Scheduling reconnection after unhandled rejection...');
        scheduleReconnection();
    } else if (ENABLE_REAL_WHATSAPP && reconnectAttempts >= maxReconnectAttempts) {
        console.log('🧪 Falling back to mock WhatsApp client after max retries...');
        stopConnectionHealthCheck();
        initializeMockClient();
    }
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
    stopConnectionHealthCheck();
    if (whatsappClient && ENABLE_REAL_WHATSAPP) {
        try {
            await whatsappClient.destroy();
        } catch (error) {
            console.log('⚠️ Error during client cleanup:', error.message);
        }
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\n🛑 Shutting down gracefully...');
    stopConnectionHealthCheck();
    if (whatsappClient && ENABLE_REAL_WHATSAPP) {
        try {
            await whatsappClient.destroy();
        } catch (error) {
            console.log('⚠️ Error during client cleanup:', error.message);
        }
    }
    process.exit(0);
});

const { MessageMedia } = require('whatsapp-web.js');
const multer = require('multer');
const upload = multer({ dest: 'uploads/' });

app.post('/api/sendVoice', upload.single('audio'), async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ error: 'WhatsApp client not ready' });
    }

    const { chatId } = req.body;
    const audioFile = req.file;

    if (!chatId || !audioFile) {
        return res.status(400).json({ error: 'chatId and audio file are required' });
    }

    try {
        if (ENABLE_REAL_WHATSAPP && whatsappClient) {
            // Production mode - send real voice message
            const media = MessageMedia.fromFilePath(audioFile.path);
            media.mimetype = 'audio/ogg; codecs=opus';
            media.filename = null; // Remove filename to send as voice note
            
            await whatsappClient.sendMessage(chatId, media, { 
                sendAudioAsVoice: true 
            });
            
            console.log(`🎤 Voice message sent to ${chatId}`);
            res.json({ success: true, message: 'Voice message sent successfully' });
        } else {
            // Mock mode - simulate voice sending
            console.log(`🎤 Mock sending voice message to ${chatId}: ${audioFile.originalname} (${audioFile.size} bytes)`);
            res.json({ success: true, message: 'Voice message simulated' });
        }
    } catch (error) {
        console.error('❌ Send voice error:', error);
        res.status(500).json({ error: error.message });
    } finally {
        // Clean up uploaded file
        if (audioFile && audioFile.path && fs.existsSync(audioFile.path)) {
            fs.unlinkSync(audioFile.path);
        }
    }
});

// Add media download endpoint for voice messages
app.get('/api/media/:messageId', async (req, res) => {
    const { messageId } = req.params;
    
    try {
        if (ENABLE_REAL_WHATSAPP && whatsappClient) {
            // Find the message and download media
            const message = await whatsappClient.getMessageById(messageId);
            if (message && message.hasMedia) {
                const media = await message.downloadMedia();
                
                res.set({
                    'Content-Type': media.mimetype,
                    'Content-Disposition': 'attachment; filename="voice.ogg"'
                });
                
                const buffer = Buffer.from(media.data, 'base64');
                res.send(buffer);
            } else {
                res.status(404).json({ error: 'Media not found' });
            }
        } else {
            // Mock mode - return mock audio data
            res.status(200).json({ message: 'Mock media download - no actual file' });
        }
    } catch (error) {
        console.error('❌ Media download error:', error);
        res.status(500).json({ error: error.message });
    }
});
