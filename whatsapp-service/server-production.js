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

const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;
const WEBHOOK_EVENTS = (process.env.WHATSAPP_HOOK_EVENTS || 'message').split(',');
const SESSION_PATH = process.env.SESSION_PATH || '/data/session';

fs.ensureDirSync(SESSION_PATH);

console.log(`🔧 WhatsApp Service Mode: ${ENABLE_REAL_WHATSAPP ? 'PRODUCTION (Real WhatsApp)' : 'MOCK (Testing)'}`);

// Initialize WhatsApp client
async function initializeClient() {
    console.log('🚀 Initializing WhatsApp client...');
      const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium-browser";

    if (ENABLE_REAL_WHATSAPP) {
        // Production mode with real WhatsApp Web.js
        try {
            await initializeRealClient();
        } catch (error) {
            console.error('❌ Failed to initialize WhatsApp client:', error.message);
            
            // Enhanced error handling with specific recovery strategies
            if (error.message.includes('Protocol error') || error.message.includes('Session closed')) {
                console.log('🔍 Browser initialization failed - this may be due to resource constraints');
                console.log('💡 Suggestion: Check available memory and browser executable path');
                
                // If this is the first attempt and we have a browser-specific error,
                // try once more with different settings before falling back
                if (reconnectAttempts === 0) {
                    console.log('🔄 Attempting initialization retry with fallback browser settings...');
                    reconnectAttempts++; // Increment to avoid infinite loop
                    try {
                        await initializeRealClientWithFallback();
                        return; // Success with fallback
                    } catch (fallbackError) {
                        console.error('❌ Fallback initialization also failed:', fallbackError.message);
                    }
                }
            }
            
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

// Reconnection logic with exponential backoff and improved error handling
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
            
            // Enhanced cleanup of existing client
            if (whatsappClient) {
                try {
                    // Stop health check before destroying client
                    stopConnectionHealthCheck();
                    
                    // Give more time for graceful shutdown
                    await Promise.race([
                        whatsappClient.destroy(),
                        new Promise((_, reject) => setTimeout(() => reject(new Error('Destroy timeout')), 10000))
                    ]);
                } catch (destroyError) {
                    console.log('⚠️ Error destroying old client:', destroyError.message);
                    // Continue with cleanup even if destroy fails
                }
            }
            whatsappClient = null;
            isClientReady = false;
            qrCodeData = null;
            
            // Add a brief delay before reinitializing to let resources settle
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            // Reinitialize with enhanced error handling
            await initializeRealClient();
            
        } catch (error) {
            console.error(`❌ Reconnection attempt ${reconnectAttempts} failed:`, error.message);
            
            // Log specific error patterns for debugging
            if (error.message.includes('Protocol error')) {
                console.log('🔍 Reconnection failed due to Protocol error - likely browser instability');
            }
            
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
    
    // Enhanced Puppeteer configuration for cloud environments with better error handling
    const executablePath = process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium-browser";

  const puppeteerOptions = {
    headless: true,
    timeout: 60000,
    executablePath,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--no-zygote',
      '--disable-gpu',
      '--disable-software-rasterizer',
      '--mute-audio'
    ],
    handleSIGINT: false,
    handleSIGTERM: false,
    handleSIGHUP: false
  };

  whatsappClient = new Client({
    authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
    puppeteer: puppeteerOptions,
    webVersionCache: {
      type: 'remote',
      remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html',
    }
  });

    // Add executablePath if available in environment
    

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

    // Add initialization timeout and enhanced error handling
    try {
        // Set a timeout for initialization
        const initTimeout = setTimeout(() => {
            console.error('❌ WhatsApp client initialization timeout (60s)');
            if (whatsappClient) {
                whatsappClient.destroy().catch(() => {});
            }
        }, 60000);

        await whatsappClient.initialize();
        clearTimeout(initTimeout);
        
    } catch (error) {
        console.error('❌ WhatsApp client initialization failed:', error.message);
        
        // Enhanced error categorization
        if (error.message.includes('Protocol error')) {
            console.error('🔍 Detected Puppeteer Protocol error - browser session closed unexpectedly');
            console.error('💡 This is typically caused by browser crashes or resource constraints');
        } else if (error.message.includes('Target closed') || error.message.includes('Session closed')) {
            console.error('🔍 Detected browser target/session closure');
            console.error('💡 Browser was closed before initialization completed');
        } else if (error.message.includes('timeout') || error.message.includes('Timeout')) {
            console.error('🔍 Detected timeout during initialization');
            console.error('💡 Browser took too long to start or respond');
        }
        
        // Ensure client is properly cleaned up on error
        if (whatsappClient) {
            try {
                await whatsappClient.destroy();
            } catch (destroyError) {
                console.log('⚠️ Error during cleanup:', destroyError.message);
            }
            whatsappClient = null;
        }
        
        throw error;
    }
}

// Fallback initialization with more conservative browser settings
async function initializeRealClientWithFallback() {
    const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
    
    console.log('🔄 Attempting WhatsApp client initialization with fallback settings...');
    
    // More conservative Puppeteer configuration for problematic environments
    const fallbackPuppeteerOptions = {
        headless: true,
        timeout: 120000, // Extended timeout for resource-constrained environments
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--disable-extensions',
            '--disable-plugins',
            '--disable-default-apps',
            '--no-default-browser-check',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
            '--disable-software-rasterizer',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--memory-pressure-off',
            '--max_old_space_size=4096',
            '--disable-ipc-flooding-protection'
        ],
        handleSIGINT: false,
        handleSIGTERM: false,
        handleSIGHUP: false,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium-browser"
    };

    // Add executablePath if available in environment
    if (process.env.PUPPETEER_EXECUTABLE_PATH) {
        fallbackPuppeteerOptions.executablePath = process.env.PUPPETEER_EXECUTABLE_PATH;
    }

    whatsappClient = new Client({
        authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
        puppeteer: fallbackPuppeteerOptions
        // Note: Removing webVersionCache for fallback to use default behavior
    });

    // Connection health monitoring
    startConnectionHealthCheck();

    whatsappClient.on('qr', (qr) => {
        qrCodeData = qr;
        lastQRTime = new Date();
        isClientReady = false;
        reconnectAttempts = 0; // Reset reconnect attempts on new QR
        console.log('📱 QR Code received (fallback mode)');
        
        if (process.env.SHOW_QR !== 'false') {
            const qrTerminal = require('qrcode-terminal');
            qrTerminal.generate(qr, { small: true });
        }
    });

    whatsappClient.on('ready', () => {
        console.log('✅ WhatsApp client is ready! (fallback mode)');
        isClientReady = true;
        qrCodeData = null;
        reconnectAttempts = 0; // Reset reconnect attempts on successful connection
        reconnectDelay = 1000; // Reset delay
        isReconnecting = false;
    });

    whatsappClient.on('authenticated', () => {
        console.log('🔐 WhatsApp client authenticated (fallback mode)');
    });

    whatsappClient.on('auth_failure', (msg) => {
        console.error('❌ Authentication failed (fallback mode):', msg);
        isClientReady = false;
        // Don't trigger reconnection on auth failure - need new QR
        scheduleReconnection();
    });

    whatsappClient.on('disconnected', (reason) => {
        console.log('⚠️ WhatsApp client disconnected (fallback mode):', reason);
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
            console.error('❌ Message handler error (fallback mode):', error);
        }
    });

    // Add initialization timeout and enhanced error handling
    try {
        // Set a longer timeout for fallback initialization
        const initTimeout = setTimeout(() => {
            console.error('❌ WhatsApp client fallback initialization timeout (90s)');
            if (whatsappClient) {
                whatsappClient.destroy().catch(() => {});
            }
        }, 90000);

        await whatsappClient.initialize();
        clearTimeout(initTimeout);
        console.log('✅ WhatsApp client initialized successfully with fallback settings');
        
    } catch (error) {
        console.error('❌ WhatsApp client fallback initialization failed:', error.message);
        
        // Ensure client is properly cleaned up on error
        if (whatsappClient) {
            try {
                await whatsappClient.destroy();
            } catch (destroyError) {
                console.log('⚠️ Error during fallback cleanup:', destroyError.message);
            }
            whatsappClient = null;
        }
        
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

// Global error handlers with enhanced browser crash detection
process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error.message);
    console.log('🔄 Attempting graceful recovery...');
    
    // Enhanced error categorization for better handling
    if (error.message.includes('Protocol error') || 
        error.message.includes('Session closed') || 
        error.message.includes('Target closed')) {
        console.log('🔍 Detected browser-related error in uncaught exception');
        
        // Clean up the current client if it exists
        if (whatsappClient) {
            console.log('🧹 Cleaning up crashed browser client...');
            whatsappClient = null;
            isClientReady = false;
            qrCodeData = null;
            stopConnectionHealthCheck();
        }
    }
    
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
    
    // Enhanced handling for browser-related rejections
    if (typeof reason === 'object' && reason.message) {
        if (reason.message.includes('Protocol error') || 
            reason.message.includes('Session closed') || 
            reason.message.includes('Target closed')) {
            console.log('🔍 Detected browser-related error in unhandled rejection');
            
            // Clean up the current client if it exists
            if (whatsappClient) {
                console.log('🧹 Cleaning up crashed browser client...');
                whatsappClient = null;
                isClientReady = false;
                qrCodeData = null;
                stopConnectionHealthCheck();
            }
        }
    }
    
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

// Send image/video message endpoint
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
        if (ENABLE_REAL_WHATSAPP && whatsappClient) {
            // Production mode - send real media
            const media = MessageMedia.fromFilePath(mediaFile.path);
            
            // Set proper mimetype based on file type
            if (mediaFile.mimetype.startsWith('image/')) {
                media.mimetype = mediaFile.mimetype;
            } else if (mediaFile.mimetype.startsWith('video/')) {
                media.mimetype = mediaFile.mimetype;
            } else {
                media.mimetype = 'application/octet-stream';
            }
            
            const options = {};
            if (caption) {
                options.caption = caption;
            }
            
            await whatsappClient.sendMessage(chatId, media, options);
            
            console.log(`📷 Media sent to ${chatId}: ${mediaFile.originalname}`);
            res.json({ 
                success: true, 
                message: 'Media sent successfully',
                filename: mediaFile.originalname,
                type: mediaFile.mimetype
            });
        } else {
            // Mock mode - simulate media sending
            console.log(`📷 Mock sending media to ${chatId}: ${mediaFile.originalname} (${mediaFile.size} bytes)`);
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
        // Clean up uploaded file
        if (mediaFile && mediaFile.path && fs.existsSync(mediaFile.path)) {
            fs.unlinkSync(mediaFile.path);
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
