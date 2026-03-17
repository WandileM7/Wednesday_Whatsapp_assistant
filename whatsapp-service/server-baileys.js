/**
 * Baileys-based WhatsApp Service
 * 
 * A lightweight, memory-efficient WhatsApp service using Baileys library.
 * Uses WebSocket connection directly - NO Chromium/Puppeteer required!
 * 
 * Memory usage: ~50-100MB (vs 400MB+ with whatsapp-web.js)
 * Perfect for Render free tier (512MB)
 */

const express = require('express');
const fs = require('fs-extra');
const path = require('path');
const multer = require('multer');
const pino = require('pino');
const QRCode = require('qrcode');
const { 
    default: makeWASocket,
    DisconnectReason,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    makeCacheableSignalKeyStore,
    downloadContentFromMessage
} = require('@whiskeysockets/baileys');

const app = express();
const PORT = process.env.PORT || 3000;
const ENABLE_REAL_WHATSAPP = process.env.ENABLE_REAL_WHATSAPP === 'true';

// Setup logging - minimal for production
const logger = pino({ 
    level: process.env.LOG_LEVEL || 'warn'
});

// Silent logger for Baileys (reduce noise)
const baileysLogger = pino({ level: 'silent' });

// Setup multer for file uploads
const uploadDir = path.join(__dirname, 'uploads');
fs.ensureDirSync(uploadDir);
const upload = multer({ dest: uploadDir });

// Express middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Global state
let sock = null;
let isClientReady = false;
let qrCodeData = null;
let lastQRTime = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 10;  // Increased from 5
let isReconnecting = false;
const mediaStore = new Map();
const MAX_MEDIA_CACHE = 200;

const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;
const SESSION_PATH = process.env.SESSION_PATH || './session';

// Ensure session directory exists
fs.ensureDirSync(SESSION_PATH);

// Log memory info
function logMemoryInfo() {
    const os = require('os');
    const totalMem = Math.round(os.totalmem() / 1024 / 1024);
    const freeMem = Math.round(os.freemem() / 1024 / 1024);
    const usedMem = totalMem - freeMem;
    
    console.log(`📊 System Memory: ${usedMem}MB used / ${totalMem}MB total (${freeMem}MB free)`);
    console.log(`🚀 Baileys WhatsApp Service - NO Chromium required!`);
    
    return { totalMem, freeMem, usedMem };
}

logMemoryInfo();
console.log(`🔧 WhatsApp Service Mode: ${ENABLE_REAL_WHATSAPP ? 'PRODUCTION (Real WhatsApp)' : 'MOCK (Testing)'}`);

// Initialize WhatsApp client with Baileys
async function initializeClient() {
    if (!ENABLE_REAL_WHATSAPP) {
        console.log('🧪 Mock mode enabled - skipping real WhatsApp connection');
        initializeMockClient();
        return;
    }

    console.log('🚀 Initializing Baileys WhatsApp client...');
    
    try {
        // Get latest Baileys version
        const { version, isLatest } = await fetchLatestBaileysVersion();
        console.log(`📱 Using WA v${version.join('.')}, isLatest: ${isLatest}`);

        // Load auth state
        const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

        // Create socket connection
        sock = makeWASocket({
            version,
            logger: baileysLogger,
            printQRInTerminal: process.env.SHOW_QR !== 'false',
            auth: {
                creds: state.creds,
                keys: makeCacheableSignalKeyStore(state.keys, baileysLogger)
            },
            browser: ['JARVIS Assistant', 'Chrome', '122.0.0'],
            generateHighQualityLinkPreview: false,
            syncFullHistory: false,
            markOnlineOnConnect: true,
            keepAliveIntervalMs: 25000,  // 25 seconds - more aggressive keepalive
            retryRequestDelayMs: 500,
            connectTimeoutMs: 60000,  // 60 second connection timeout
            defaultQueryTimeoutMs: 60000,
            emitOwnEvents: false,  // Don't emit events for own messages
            fireInitQueries: true,
            getMessage: async () => undefined  // Don't fetch old messages
        });

        // Handle connection updates
        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                qrCodeData = qr;
                lastQRTime = new Date();
                isClientReady = false;
                console.log('📱 QR Code received - scan with WhatsApp');
            }

            if (connection === 'close') {
                isClientReady = false;
                qrCodeData = null;
                
                const statusCode = lastDisconnect?.error?.output?.statusCode;
                const errorMessage = lastDisconnect?.error?.message || 'Unknown error';
                
                console.log(`⚠️ Connection closed. Status: ${statusCode}. Error: ${errorMessage}`);
                
                // Determine if we should reconnect based on status code
                // 401 = Unauthorized (logged out)
                // 408 = Connection timeout
                // 428 = Connection replaced (another device logged in)
                // 440 = Connection replaced
                // 515 = WhatsApp requires app restart
                const shouldReconnect = ![401, 428, 440].includes(statusCode);
                
                if (shouldReconnect && reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    const delay = Math.min(3000 * reconnectAttempts, 15000); // Exponential backoff, max 15s
                    console.log(`🔄 Reconnecting in ${delay/1000}s... Attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
                    setTimeout(() => initializeClient(), delay);
                } else if (statusCode === 401 || statusCode === 428 || statusCode === 440) {
                    console.log('🚪 Session invalidated - clearing and waiting for new QR scan');
                    await fs.remove(SESSION_PATH);
                    fs.ensureDirSync(SESSION_PATH);
                    reconnectAttempts = 0;
                    setTimeout(() => initializeClient(), 2000);
                } else {
                    console.log('🚫 Max reconnection attempts reached or unrecoverable error');
                    // Try one more time after a longer delay
                    setTimeout(() => {
                        reconnectAttempts = 0;
                        initializeClient();
                    }, 30000);
                }
            }

            if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully!');
                isClientReady = true;
                qrCodeData = null;
                reconnectAttempts = 0;
                
                // Log connection info
                if (sock.user) {
                    console.log(`📱 Connected as: ${sock.user.id.split(':')[0]}`);
                }
            }
        });

        // Handle credential updates
        sock.ev.on('creds.update', saveCreds);

        // Handle incoming messages
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return;

            for (const msg of messages) {
                // Skip messages from self
                if (msg.key.fromMe) continue;

                console.log(`📨 Received message from ${msg.key.remoteJid}`);
                
                // Forward to webhook
                await forwardToWebhook(msg);
            }
        });

    } catch (error) {
        console.error('❌ Failed to initialize Baileys client:', error.message);
        
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            console.log(`🔄 Retrying... Attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
            setTimeout(() => initializeClient(), 5000);
        } else {
            console.log('🚫 Falling back to mock mode');
            initializeMockClient();
        }
    }
}

// Mock client for testing
function initializeMockClient() {
    console.log('🧪 Initializing mock WhatsApp client...');
    
    const sessionFile = path.join(SESSION_PATH, 'session.json');
    
    if (fs.existsSync(sessionFile)) {
        console.log('✅ Found existing session, marking as ready');
        isClientReady = true;
        qrCodeData = null;
    } else {
        console.log('📱 No session found, generating QR code');
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
    if (ENABLE_REAL_WHATSAPP && sock && isClientReady) {
        try {
            // Ensure chatId is in correct format
            const jid = chatId.includes('@') ? chatId : `${chatId}@s.whatsapp.net`;
            
            await sock.sendMessage(jid, { text });
            console.log(`📤 Sent message to ${jid}: ${text.substring(0, 50)}...`);
            return true;
        } catch (error) {
            console.error('❌ Send error:', error.message);
            return false;
        }
    } else {
        console.log(`📤 Mock sending to ${chatId}: ${text.substring(0, 50)}...`);
        return true;
    }
}

// Forward message to webhook
async function forwardToWebhook(message) {
    if (!WEBHOOK_URL) return;

    try {
        // Extract message content
        const messageContent = message.message;
        let body = '';
        let hasMedia = false;
        let mediaType = null;
        const mediaId = message.key.id;

        if (messageContent?.conversation) {
            body = messageContent.conversation;
        } else if (messageContent?.extendedTextMessage?.text) {
            body = messageContent.extendedTextMessage.text;
        } else if (messageContent?.imageMessage) {
            body = messageContent.imageMessage.caption || '[Image]';
            hasMedia = true;
            mediaType = 'image';
        } else if (messageContent?.videoMessage) {
            body = messageContent.videoMessage.caption || '[Video]';
            hasMedia = true;
            mediaType = 'video';
        } else if (messageContent?.audioMessage) {
            body = '[Audio]';
            hasMedia = true;
            mediaType = 'audio';
        } else if (messageContent?.documentMessage) {
            body = messageContent.documentMessage.fileName || '[Document]';
            hasMedia = true;
            mediaType = 'document';
        }

        // Build media URL if available so downstream can fetch
        let mediaUrl = null;
        if (hasMedia) {
            const base = process.env.MEDIA_BASE_URL || process.env.PUBLIC_BASE_URL || `http://localhost:${PORT}`;
            mediaUrl = `${base.replace(/\/$/, '')}/api/media/${mediaId}`;
        }

        const webhookPayload = {
            payload: {
                id: mediaId,
                messageId: mediaId,  // Alias for deduplication
                chatId: message.key.remoteJid,  // For compatibility with main.py
                from: message.key.remoteJid,
                to: message.key.participant || message.key.remoteJid,
                body: body,
                type: hasMedia ? mediaType : 'text',
                timestamp: message.messageTimestamp,
                fromMe: message.key.fromMe || false,
                hasMedia: hasMedia,
                mediaUrl: mediaUrl,
                pushName: message.pushName || null
            }
        };

        if (hasMedia) {
            storeMediaMessage(message, mediaType);
        }

        const response = await fetch(WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(webhookPayload)
        });

        if (response.ok) {
            console.log(`✅ Message forwarded to webhook: ${message.key.id}`);
        } else {
            console.error(`❌ Webhook failed: ${response.status}`);
        }
    } catch (error) {
        console.error('❌ Webhook error:', error.message);
    }
}

function storeMediaMessage(message, mediaType) {
    mediaStore.set(message.key.id, { message, mediaType, savedAt: Date.now() });
    if (mediaStore.size > MAX_MEDIA_CACHE) {
        const oldestKey = mediaStore.keys().next().value;
        mediaStore.delete(oldestKey);
    }
}

// ==================== API ENDPOINTS ====================

// Health check
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        service: 'baileys-whatsapp-service',
        client_ready: isClientReady,
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        memory_mb: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
        uptime: process.uptime()
    });
});

// Root endpoint
app.get('/', (req, res) => {
    res.json({
        service: 'Baileys WhatsApp Service',
        status: isClientReady ? 'connected' : 'disconnected',
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        version: '2.0.0',
        engine: 'baileys',
        memory_efficient: true,
        endpoints: [
            'GET /health',
            'GET /api/qr',
            'GET /api/info',
            'POST /api/sendText',
            'POST /api/sendVoice',
            'POST /api/sendMedia',
            'GET /api/sessions/:sessionName',
            'POST /api/sessions/:sessionName/start'
        ]
    });
});

// Session status (WAHA compatibility)
app.get('/api/sessions/:sessionName', (req, res) => {
    res.json({
        name: req.params.sessionName,
        status: isClientReady ? 'working' : 'starting',
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        me: sock?.user || null
    });
});

// Create session (WAHA compatibility)
app.post('/api/sessions/:sessionName', (req, res) => {
    if (!sock && !isClientReady) {
        initializeClient();
    }
    res.json({ success: true, session: req.params.sessionName });
});

// Start session (WAHA compatibility)
app.post('/api/sessions/:sessionName/start', (req, res) => {
    if (!sock && !isClientReady) {
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
                chatId,
                text
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
                chatId,
                text
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
            timestamp: lastQRTime?.toISOString(),
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

// Get QR code as PNG image
app.get('/api/qr/image', async (req, res) => {
    if (!qrCodeData) {
        if (isClientReady) {
            return res.status(200).json({ status: 'authenticated', message: 'Already connected' });
        }
        return res.status(404).json({ error: 'No QR code available', status: 'waiting' });
    }
    
    try {
        const qrImage = await QRCode.toBuffer(qrCodeData, {
            type: 'png',
            width: 300,
            margin: 2,
            color: {
                dark: '#000000',
                light: '#FFFFFF'
            }
        });
        
        res.setHeader('Content-Type', 'image/png');
        res.setHeader('Cache-Control', 'no-store');
        res.send(qrImage);
    } catch (error) {
        console.error('Error generating QR image:', error);
        res.status(500).json({ error: 'Failed to generate QR image' });
    }
});

// Screenshot endpoint (QR code)
app.get('/api/screenshot', (req, res) => {
    if (qrCodeData) {
        res.json({ 
            qr: qrCodeData,
            format: 'text',
            timestamp: lastQRTime?.toISOString(),
            mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock'
        });
    } else {
        res.status(404).json({ error: 'No QR code available' });
    }
});

// Service info
app.get('/api/info', (req, res) => {
    res.json({
        service: 'baileys-whatsapp-service',
        version: '2.0.0',
        engine: 'baileys',
        mode: ENABLE_REAL_WHATSAPP ? 'production' : 'mock',
        features: {
            real_whatsapp: ENABLE_REAL_WHATSAPP,
            webhook_forwarding: !!WEBHOOK_URL,
            qr_display: process.env.SHOW_QR !== 'false',
            test_simulation: !ENABLE_REAL_WHATSAPP
        },
        memory_efficient: true,
        chromium_free: true,
        waha_compatible: true
    });
});

// Voice message endpoint
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
        if (ENABLE_REAL_WHATSAPP && sock) {
            const jid = chatId.includes('@') ? chatId : `${chatId}@s.whatsapp.net`;
            const audioBuffer = await fs.readFile(audioFile.path);
            
            await sock.sendMessage(jid, {
                audio: audioBuffer,
                mimetype: 'audio/ogg; codecs=opus',
                ptt: true // Send as voice note
            });
            
            console.log(`🎤 Voice message sent to ${jid}`);
            res.json({ success: true, message: 'Voice message sent successfully' });
        } else {
            console.log(`🎤 Mock sending voice to ${chatId}`);
            res.json({ success: true, message: 'Voice message simulated' });
        }
    } catch (error) {
        console.error('❌ Send voice error:', error);
        res.status(500).json({ error: error.message });
    } finally {
        if (audioFile?.path && fs.existsSync(audioFile.path)) {
            fs.unlinkSync(audioFile.path);
        }
    }
});

// Media download endpoint (needed by voice preprocessor)
app.get('/api/media/:messageId', async (req, res) => {
    const { messageId } = req.params;

    if (!ENABLE_REAL_WHATSAPP) {
        return res.status(200).json({ message: 'Mock media download - no actual file' });
    }

    const cached = mediaStore.get(messageId);
    if (!cached) {
        return res.status(404).json({ error: 'Media not found or expired' });
    }

    try {
        const messageContent = cached.message.message;
        let node = null;
        let mediaType = cached.mediaType;

        if (messageContent?.imageMessage) {
            node = messageContent.imageMessage;
            mediaType = 'image';
        } else if (messageContent?.videoMessage) {
            node = messageContent.videoMessage;
            mediaType = 'video';
        } else if (messageContent?.audioMessage) {
            node = messageContent.audioMessage;
            mediaType = 'audio';
        } else if (messageContent?.documentMessage) {
            node = messageContent.documentMessage;
            mediaType = 'document';
        }

        if (!node) {
            return res.status(404).json({ error: 'Media payload unavailable' });
        }

        const stream = await downloadContentFromMessage(node, mediaType || 'unknown');
        const chunks = [];
        for await (const chunk of stream) {
            chunks.push(chunk);
        }
        const buffer = Buffer.concat(chunks);

        const mime = node.mimetype || 'application/octet-stream';
        const filename = node.fileName || `${mediaType || 'media'}-${messageId}`;

        res.set({
            'Content-Type': mime,
            'Content-Disposition': `attachment; filename="${filename}"`
        });
        return res.send(buffer);
    } catch (error) {
        console.error('❌ Media download error:', error.message);
        return res.status(500).json({ error: 'Media download failed' });
    }
});

// Send media endpoint
app.post('/api/sendMedia', upload.single('media'), async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ error: 'WhatsApp client not ready' });
    }

    const { chatId, caption } = req.body;
    const mediaFile = req.file;

    if (!chatId || !mediaFile) {
        return res.status(400).json({ error: 'chatId and media file are required' });
    }

    try {
        if (ENABLE_REAL_WHATSAPP && sock) {
            const jid = chatId.includes('@') ? chatId : `${chatId}@s.whatsapp.net`;
            const mediaBuffer = await fs.readFile(mediaFile.path);
            
            let messageContent = {};
            
            if (mediaFile.mimetype.startsWith('image/')) {
                messageContent = {
                    image: mediaBuffer,
                    caption: caption || undefined
                };
            } else if (mediaFile.mimetype.startsWith('video/')) {
                messageContent = {
                    video: mediaBuffer,
                    caption: caption || undefined
                };
            } else {
                messageContent = {
                    document: mediaBuffer,
                    fileName: mediaFile.originalname,
                    mimetype: mediaFile.mimetype
                };
            }
            
            await sock.sendMessage(jid, messageContent);
            
            console.log(`📷 Media sent to ${jid}: ${mediaFile.originalname}`);
            res.json({ 
                success: true, 
                message: 'Media sent successfully',
                filename: mediaFile.originalname,
                type: mediaFile.mimetype
            });
        } else {
            console.log(`📷 Mock sending media to ${chatId}`);
            res.json({ 
                success: true, 
                message: 'Media simulated',
                filename: mediaFile.originalname,
                type: mediaFile.mimetype
            });
        }
    } catch (error) {
        console.error('❌ Send media error:', error);
        res.status(500).json({ error: error.message });
    } finally {
        if (mediaFile?.path && fs.existsSync(mediaFile.path)) {
            fs.unlinkSync(mediaFile.path);
        }
    }
});

// Simulate message for testing
app.post('/test/simulate-message', async (req, res) => {
    if (ENABLE_REAL_WHATSAPP) {
        return res.status(400).json({ error: 'Test simulation not available in production mode' });
    }
    
    const { from, text } = req.body;
    
    if (!from || !text) {
        return res.status(400).json({ error: 'from and text are required' });
    }
    
    const message = {
        key: {
            id: 'msg_' + Date.now(),
            remoteJid: from,
            fromMe: false
        },
        message: { conversation: text },
        messageTimestamp: Math.floor(Date.now() / 1000),
        pushName: 'Test User'
    };
    
    await forwardToWebhook(message);
    res.json({ success: true, message: 'Message simulated and forwarded to webhook' });
});

// Logout endpoint - clears session and disconnects
app.post('/api/sessions/:sessionName/logout', async (req, res) => {
    console.log('🚪 Logout requested...');
    
    try {
        if (sock) {
            await sock.logout().catch(() => {});
            sock = null;
        }
        
        // Clear session data
        await fs.remove(SESSION_PATH);
        fs.ensureDirSync(SESSION_PATH);
        
        isClientReady = false;
        qrCodeData = null;
        reconnectAttempts = 0;
        
        console.log('✅ Logged out and session cleared');
        res.json({ success: true, message: 'Logged out successfully' });
    } catch (error) {
        console.error('❌ Logout error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Restart/Reconnect endpoint
app.post('/api/sessions/:sessionName/restart', async (req, res) => {
    console.log('🔄 Restart requested...');
    
    try {
        // Close existing connection
        if (sock) {
            await sock.logout().catch(() => {});
            sock = null;
        }
        
        isClientReady = false;
        qrCodeData = null;
        reconnectAttempts = 0;
        
        // Reinitialize
        setTimeout(() => initializeClient(), 1000);
        
        res.json({ success: true, message: 'Restart initiated, check /api/qr for new QR code' });
    } catch (error) {
        console.error('❌ Restart error:', error);
        res.status(500).json({ error: error.message });
    }
});

// Error handling
app.use((error, req, res, next) => {
    console.error('❌ Server error:', error);
    res.status(500).json({ error: 'Internal server error' });
});

// Graceful shutdown
process.on('SIGTERM', async () => {
    console.log('🛑 Received SIGTERM, shutting down...');
    if (sock) {
        await sock.logout().catch(() => {});
    }
    process.exit(0);
});

process.on('SIGINT', async () => {
    console.log('🛑 Received SIGINT, shutting down...');
    if (sock) {
        await sock.logout().catch(() => {});
    }
    process.exit(0);
});

// Start server
app.listen(PORT, () => {
    console.log(`🌐 Baileys WhatsApp Service running on port ${PORT}`);
    console.log(`📋 Health check: http://localhost:${PORT}/health`);
    console.log(`📱 QR code: http://localhost:${PORT}/api/qr`);
    console.log(`ℹ️ Service info: http://localhost:${PORT}/api/info`);
    console.log(`🚀 NO Chromium required - Memory efficient!`);
    
    // Initialize client
    initializeClient();
});
