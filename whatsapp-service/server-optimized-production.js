/**
 * Memory-Optimized Production WhatsApp Service
 * Real WhatsApp Web.js implementation with aggressive memory optimizations
 * No mock mode fallbacks - production-only
 */

const express = require('express');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

const app = express();
const PORT = process.env.PORT || 3000;

// Memory optimization constants
const MEMORY_THRESHOLD_MB = parseInt(process.env.MEMORY_THRESHOLD_MB) || 300; // Reduced from 400
const MAX_HEAP_SIZE_MB = parseInt(process.env.MAX_HEAP_SIZE_MB) || 256;
const GC_INTERVAL_MS = parseInt(process.env.GC_INTERVAL_MS) || 15000; // More frequent GC

// Force production mode - no mock fallbacks
const PRODUCTION_ONLY = true;

console.log('🚀 Starting Memory-Optimized Production WhatsApp Service (NO MOCK MODE)');
console.log(`📊 Memory threshold: ${MEMORY_THRESHOLD_MB}MB`);
console.log(`🧠 Max heap size: ${MAX_HEAP_SIZE_MB}MB`);

// Enhanced memory optimization middleware
app.use(express.json({ limit: '5mb' })); // Further reduced from 10mb
app.use(express.urlencoded({ extended: true, limit: '5mb' }));

// Aggressive connection management
app.use((req, res, next) => {
    res.setHeader('Connection', 'close');
    res.setHeader('Keep-Alive', 'timeout=1');
    next();
});

// Global state with memory-conscious design
let whatsappClient = null;
let isClientReady = false;
let qrCodeData = null;
let lastQRTime = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 2; // Reduced attempts
let reconnectDelay = parseInt(process.env.INITIAL_RECONNECT_DELAY) || 10000;
let isReconnecting = false;
let connectionHealthCheck = null;

const WEBHOOK_URL = process.env.WHATSAPP_HOOK_URL;
const WEBHOOK_EVENTS = (process.env.WHATSAPP_HOOK_EVENTS || 'message').split(',');
const SESSION_PATH = process.env.SESSION_PATH || './session';

// Memory monitoring
function getMemoryUsage() {
    const usage = process.memoryUsage();
    return {
        heapUsed: Math.round(usage.heapUsed / 1024 / 1024),
        heapTotal: Math.round(usage.heapTotal / 1024 / 1024),
        external: Math.round(usage.external / 1024 / 1024),
        rss: Math.round(usage.rss / 1024 / 1024)
    };
}

// Aggressive memory cleanup
function performMemoryCleanup() {
    try {
        // Clear require cache for non-essential modules
        Object.keys(require.cache).forEach(key => {
            if (key.includes('node_modules') && 
                !key.includes('whatsapp-web.js') && 
                !key.includes('puppeteer') &&
                !key.includes('express')) {
                delete require.cache[key];
            }
        });
        
        // Force garbage collection if available
        if (global.gc) {
            global.gc();
        }
        
        const memory = getMemoryUsage();
        console.log(`🧹 Memory cleanup: Heap ${memory.heapUsed}/${memory.heapTotal}MB, RSS ${memory.rss}MB`);
        
        return memory;
    } catch (error) {
        console.error('❌ Memory cleanup failed:', error.message);
        return null;
    }
}

// Memory monitoring middleware with aggressive cleanup
function memoryMonitoring(req, res, next) {
    const memory = getMemoryUsage();
    
    if (memory.heapUsed > MEMORY_THRESHOLD_MB * 0.7) {
        console.log(`⚠️ High memory usage detected: ${memory.heapUsed}MB - triggering cleanup`);
        performMemoryCleanup();
    }
    
    if (memory.heapUsed > MEMORY_THRESHOLD_MB * 1.2) {
        console.log(`🚨 Critical memory usage: ${memory.heapUsed}MB - forcing restart`);
        process.exit(1); // Let container orchestrator restart
    }
    
    res.setHeader('X-Memory-Usage-MB', memory.heapUsed);
    next();
}

app.use(memoryMonitoring);

// Ensure session directory exists
try {
    fs.ensureDirSync(SESSION_PATH);
} catch (error) {
    console.error('❌ Session directory creation failed:', error.message);
    process.exit(1);
}

// Memory-optimized WhatsApp client initialization
async function initializeOptimizedClient() {
    console.log('🚀 Initializing memory-optimized WhatsApp client...');
    
    // Check memory before initialization
    const initialMemory = getMemoryUsage();
    console.log(`📊 Pre-init memory: ${initialMemory.heapUsed}MB`);
    
    if (initialMemory.heapUsed > MEMORY_THRESHOLD_MB * 0.8) {
        console.log('🧹 High memory before init - performing cleanup');
        performMemoryCleanup();
    }
    
    try {
        const { Client, LocalAuth } = require('whatsapp-web.js');
        
        // Ultra-minimal Puppeteer configuration for memory efficiency
        const optimizedPuppeteerOptions = {
            headless: true,
            timeout: 45000, // Reduced timeout
            executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/chromium-browser",
            args: [
                // Core flags for minimal memory usage
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-software-rasterizer',
                
                // Memory optimization flags
                `--max-old-space-size=${MAX_HEAP_SIZE_MB}`,
                '--memory-pressure-off',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                
                // Disable unnecessary features
                '--no-first-run',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-default-apps',
                '--no-default-browser-check',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-ipc-flooding-protection',
                '--disable-logging',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-back-forward-cache',
                '--disable-client-side-phishing-detection',
                '--disable-sync',
                '--disable-translate',
                
                // Audio/video optimization for messaging only
                '--mute-audio',
                '--disable-audio-support-for-desktop-share',
                '--disable-video-capture-use-gpu-memory-buffer',
                
                // Network optimization
                '--aggressive-cache-discard',
                '--enable-low-end-device-mode',
                '--force-prefers-reduced-motion',
                
                // Disable unnecessary UI features
                '--disable-notifications',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-hang-monitor',
                '--disable-domain-reliability'
            ],
            handleSIGINT: false,
            handleSIGTERM: false,
            handleSIGHUP: false
        };

        // Create client with minimal configuration
        whatsappClient = new Client({
            authStrategy: new LocalAuth({ 
                dataPath: SESSION_PATH,
                // Minimal session data
                clientId: 'optimized-client'
            }),
            puppeteer: optimizedPuppeteerOptions,
            // Use minimal web version for better performance
            webVersionCache: {
                type: 'remote',
                remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html',
            }
        });

        // Start minimal health check
        startOptimizedHealthCheck();

        // Optimized event handlers
        whatsappClient.on('qr', (qr) => {
            qrCodeData = qr;
            lastQRTime = new Date();
            isClientReady = false;
            reconnectAttempts = 0;
            console.log('📱 QR Code received');
            
            // Trigger cleanup after QR generation
            setTimeout(() => performMemoryCleanup(), 2000);
        });

        whatsappClient.on('ready', () => {
            console.log('✅ WhatsApp client ready!');
            isClientReady = true;
            qrCodeData = null;
            reconnectAttempts = 0;
            reconnectDelay = 10000; // Reset delay
            isReconnecting = false;
            
            // Post-ready memory cleanup
            setTimeout(() => performMemoryCleanup(), 3000);
        });

        whatsappClient.on('authenticated', () => {
            console.log('🔐 WhatsApp authenticated');
        });

        whatsappClient.on('auth_failure', (msg) => {
            console.error('❌ Authentication failed:', msg);
            isClientReady = false;
            scheduleOptimizedReconnection();
        });

        whatsappClient.on('disconnected', (reason) => {
            console.log('⚠️ WhatsApp disconnected:', reason);
            isClientReady = false;
            qrCodeData = null;
            
            if (!isReconnecting && reason !== 'LOGOUT') {
                scheduleOptimizedReconnection();
            }
        });

        // Optimized message handler with memory management
        whatsappClient.on('message', async (message) => {
            try {
                if (message.fromMe) return;

                console.log(`📨 Message from ${message.from}: ${message.body || '[Media]'}`);
                
                // Create minimal message object to reduce memory footprint
                const minimalMessage = {
                    id: message.id?._serialized || message.id,
                    from: message.from,
                    body: message.body || '',
                    type: message.type || 'text',
                    timestamp: message.timestamp,
                    fromMe: false,
                    hasMedia: message.hasMedia || false
                };

                // Add only essential media properties
                if (message.hasMedia) {
                    minimalMessage.mimetype = message._data?.mimetype || null;
                }

                await forwardToWebhook(minimalMessage);
                
                // Cleanup after message processing
                if (Math.random() < 0.1) { // 10% chance to cleanup
                    performMemoryCleanup();
                }
                
            } catch (error) {
                console.error('❌ Message handler error:', error.message);
            }
        });

        // Initialize with timeout
        const initTimeout = setTimeout(() => {
            console.error('❌ Initialization timeout');
            if (whatsappClient) {
                whatsappClient.destroy().catch(() => {});
            }
            throw new Error('Initialization timeout');
        }, 45000);

        await whatsappClient.initialize();
        clearTimeout(initTimeout);
        
        const postInitMemory = getMemoryUsage();
        console.log(`📊 Post-init memory: ${postInitMemory.heapUsed}MB`);
        
    } catch (error) {
        console.error('❌ WhatsApp initialization failed:', error.message);
        
        // In test/restricted environments, don't exit immediately for network errors
        if (error.message.includes('ERR_NAME_NOT_RESOLVED') || 
            error.message.includes('ERR_INTERNET_DISCONNECTED') ||
            error.message.includes('net::')) {
            console.log('🌐 Network connectivity issue detected');
            console.log('💡 This is expected in restricted environments');
            console.log('📋 Service API remains available for testing');
            
            // Clean up the failed client but keep service running
            if (whatsappClient) {
                try {
                    await whatsappClient.destroy();
                } catch (destroyError) {
                    console.log('⚠️ Cleanup error:', destroyError.message);
                }
                whatsappClient = null;
            }
            
            return; // Keep service running for API testing
        }
        
        if (whatsappClient) {
            try {
                await whatsappClient.destroy();
            } catch (destroyError) {
                console.log('⚠️ Cleanup error:', destroyError.message);
            }
            whatsappClient = null;
        }
        
        throw error;
    }
}

// Optimized reconnection with aggressive memory management
function scheduleOptimizedReconnection() {
    if (isReconnecting || reconnectAttempts >= maxReconnectAttempts) {
        if (reconnectAttempts >= maxReconnectAttempts) {
            console.error('🚫 Max reconnection attempts reached - service requires restart');
            process.exit(1); // Force restart instead of mock mode
        }
        return;
    }
    
    isReconnecting = true;
    reconnectAttempts++;
    
    console.log(`🔄 Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts} in ${reconnectDelay}ms`);
    
    setTimeout(async () => {
        try {
            // Aggressive cleanup before reconnection
            if (whatsappClient) {
                stopOptimizedHealthCheck();
                try {
                    await Promise.race([
                        whatsappClient.destroy(),
                        new Promise((_, reject) => setTimeout(() => reject(new Error('Destroy timeout')), 5000))
                    ]);
                } catch (destroyError) {
                    console.log('⚠️ Destroy error:', destroyError.message);
                }
            }
            
            whatsappClient = null;
            isClientReady = false;
            qrCodeData = null;
            
            // Aggressive memory cleanup before reinit
            performMemoryCleanup();
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            await initializeOptimizedClient();
            isReconnecting = false;
            
        } catch (error) {
            console.error(`❌ Reconnection ${reconnectAttempts} failed:`, error.message);
            isReconnecting = false;
            
            // Exponential backoff with jitter
            reconnectDelay = Math.min(reconnectDelay * 1.5 + Math.random() * 2000, 30000);
            
            if (reconnectAttempts < maxReconnectAttempts) {
                scheduleOptimizedReconnection();
            } else {
                console.error('🚫 All reconnection attempts failed - service requires restart');
                process.exit(1);
            }
        }
    }, reconnectDelay);
}

// Minimal health check to reduce overhead
function startOptimizedHealthCheck() {
    if (connectionHealthCheck) {
        clearInterval(connectionHealthCheck);
    }
    
    connectionHealthCheck = setInterval(async () => {
        if (!whatsappClient || !isClientReady) return;
        
        try {
            const state = await whatsappClient.getState();
            if (state === 'UNPAIRED' || state === 'UNLAUNCHED') {
                console.log(`⚠️ Unhealthy state: ${state} - reconnecting`);
                isClientReady = false;
                scheduleOptimizedReconnection();
            }
        } catch (error) {
            // Silent health check failure - let disconnect handler manage it
        }
    }, 45000); // Less frequent checks to save resources
}

function stopOptimizedHealthCheck() {
    if (connectionHealthCheck) {
        clearInterval(connectionHealthCheck);
        connectionHealthCheck = null;
    }
}

// Optimized message sending
async function sendOptimizedMessage(chatId, text) {
    if (!whatsappClient || !isClientReady) {
        throw new Error('WhatsApp client not ready');
    }
    
    try {
        await whatsappClient.sendMessage(chatId, text);
        console.log(`📤 Sent message to ${chatId}: ${text.substring(0, 50)}...`);
        
        // Cleanup after sending
        if (Math.random() < 0.05) { // 5% chance
            performMemoryCleanup();
        }
        
        return true;
    } catch (error) {
        console.error('❌ Send message error:', error.message);
        throw error;
    }
}

// Optimized webhook forwarding
async function forwardToWebhook(message) {
    if (!WEBHOOK_URL) return;

    try {
        // Use node-fetch for compatibility if fetch is not available
        let fetchFn;
        try {
            fetchFn = fetch;
        } catch {
            const nodeFetch = require('node-fetch');
            fetchFn = nodeFetch;
        }
        
        const response = await fetchFn(WEBHOOK_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payload: message }),
            timeout: 5000 // Quick timeout to prevent hanging
        });

        if (response.ok) {
            console.log(`✅ Webhook forwarded: ${message.id}`);
        } else {
            console.error(`❌ Webhook failed: ${response.status}`);
        }
    } catch (error) {
        console.error('❌ Webhook error:', error.message);
    }
}

// API Routes - Minimal and efficient

// Health check
app.get('/health', (req, res) => {
    const memory = getMemoryUsage();
    res.json({
        status: 'healthy',
        mode: 'production-optimized',
        whatsapp_ready: isClientReady,
        has_qr: !!qrCodeData,
        memory_mb: memory.heapUsed,
        timestamp: new Date().toISOString()
    });
});

// Session status
app.get('/api/sessions/:sessionName', (req, res) => {
    res.json({
        name: req.params.sessionName,
        status: isClientReady ? 'working' : 'starting',
        mode: 'production-optimized'
    });
});

// Create/start session
app.post('/api/sessions/:sessionName', (req, res) => {
    if (!whatsappClient && !isClientReady) {
        initializeOptimizedClient();
    }
    res.json({ success: true, session: req.params.sessionName });
});

app.post('/api/sessions/:sessionName/start', (req, res) => {
    if (!whatsappClient && !isClientReady) {
        initializeOptimizedClient();
    }
    res.json({ success: true, session: req.params.sessionName });
});

// Send message
app.post('/api/sendText', async (req, res) => {
    if (!isClientReady) {
        return res.status(503).json({ 
            error: 'WhatsApp client not ready',
            mode: 'production-optimized'
        });
    }

    const { chatId, text } = req.body;
    if (!chatId || !text) {
        return res.status(400).json({ error: 'chatId and text required' });
    }

    try {
        await sendOptimizedMessage(chatId, text);
        res.json({ 
            success: true, 
            message: 'Message sent',
            mode: 'production-optimized'
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// QR code
app.get('/api/qr', (req, res) => {
    if (qrCodeData) {
        res.json({ 
            qr: qrCodeData, 
            timestamp: lastQRTime.toISOString(),
            mode: 'production-optimized'
        });
    } else if (isClientReady) {
        res.json({ 
            status: 'authenticated', 
            message: 'Client ready',
            mode: 'production-optimized'
        });
    } else {
        res.json({ 
            status: 'waiting', 
            message: 'Initializing...',
            mode: 'production-optimized'
        });
    }
});

// Service info
app.get('/api/info', (req, res) => {
    const memory = getMemoryUsage();
    res.json({
        service: 'optimized-whatsapp-service',
        version: '2.0.0',
        mode: 'production-optimized',
        memory_optimized: true,
        memory_usage_mb: memory.heapUsed,
        features: {
            real_whatsapp_only: true,
            mock_mode: false,
            memory_optimized: true,
            webhook_forwarding: !!WEBHOOK_URL
        }
    });
});

// Memory optimization interval
setInterval(() => {
    const memory = getMemoryUsage();
    
    if (memory.heapUsed > MEMORY_THRESHOLD_MB * 0.6) {
        performMemoryCleanup();
    }
    
    // Log memory status periodically
    if (Math.random() < 0.1) { // 10% chance
        console.log(`📊 Memory: ${memory.heapUsed}/${memory.heapTotal}MB (RSS: ${memory.rss}MB)`);
    }
}, GC_INTERVAL_MS);

// Error handling
process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error.message);
    performMemoryCleanup();
    
    if (whatsappClient) {
        whatsappClient.destroy().catch(() => {});
        whatsappClient = null;
        isClientReady = false;
    }
    
    if (reconnectAttempts < maxReconnectAttempts) {
        scheduleOptimizedReconnection();
    } else {
        console.error('🚫 Service requires restart');
        process.exit(1);
    }
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection:', reason);
    performMemoryCleanup();
    
    if (typeof reason === 'object' && reason.message && 
        (reason.message.includes('Protocol error') || reason.message.includes('Session closed'))) {
        
        if (whatsappClient) {
            whatsappClient.destroy().catch(() => {});
            whatsappClient = null;
            isClientReady = false;
        }
        
        if (reconnectAttempts < maxReconnectAttempts) {
            scheduleOptimizedReconnection();
        } else {
            console.error('🚫 Service requires restart');
            process.exit(1);
        }
    }
});

// Graceful shutdown
const shutdown = async (signal) => {
    console.log(`\n🛑 ${signal} - Shutting down gracefully...`);
    stopOptimizedHealthCheck();
    
    if (whatsappClient) {
        try {
            await Promise.race([
                whatsappClient.destroy(),
                new Promise((_, reject) => setTimeout(() => reject(new Error('Shutdown timeout')), 5000))
            ]);
        } catch (error) {
            console.log('⚠️ Shutdown cleanup error:', error.message);
        }
    }
    
    process.exit(0);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

// Start server
const server = app.listen(PORT, () => {
    console.log(`🌐 Optimized WhatsApp Service running on port ${PORT}`);
    console.log(`📋 Health: http://localhost:${PORT}/health`);
    console.log(`📱 QR code: http://localhost:${PORT}/api/qr`);
    console.log(`ℹ️ Info: http://localhost:${PORT}/api/info`);
    console.log(`🚀 Production-only mode - no mock fallbacks`);
    
    // Initialize WhatsApp client
    initializeOptimizedClient().catch((error) => {
        console.error('❌ Failed to start WhatsApp service:', error.message);
        
        // Don't exit on network connectivity issues in test environments
        if (error.message.includes('ERR_NAME_NOT_RESOLVED') || 
            error.message.includes('ERR_INTERNET_DISCONNECTED') ||
            error.message.includes('net::')) {
            console.log('📋 Service API available despite network limitations');
            return; // Keep service running
        }
        
        process.exit(1);
    });
});

module.exports = { app, server };