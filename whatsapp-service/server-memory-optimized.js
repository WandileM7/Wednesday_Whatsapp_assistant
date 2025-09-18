/**
 * Memory-Optimized WhatsApp Service
 * Automatically chooses production or mock mode based on available resources
 */

const express = require('express');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

const app = express();
const PORT = process.env.PORT || 3000;

// Memory monitoring and resource management
const MEMORY_THRESHOLD_MB = parseInt(process.env.MEMORY_THRESHOLD_MB) || 400; // Memory limit in MB
const FORCE_MOCK_MODE = process.env.FORCE_MOCK_MODE === 'true';

// Check available memory
function getAvailableMemoryMB() {
    const totalMem = os.totalmem();
    const freeMem = os.freemem();
    return Math.round((totalMem - freeMem) / 1024 / 1024);
}

// Determine optimal mode based on resources
function determineOptimalMode() {
    if (FORCE_MOCK_MODE) {
        console.log('🔧 Mode: FORCED MOCK (Environment override)');
        return 'mock';
    }

    const currentMemoryMB = getAvailableMemoryMB();
    const enableRealWhatsApp = process.env.ENABLE_REAL_WHATSAPP === 'true';
    
    console.log(`📊 Current memory usage: ${currentMemoryMB}MB`);
    console.log(`⚖️ Memory threshold: ${MEMORY_THRESHOLD_MB}MB`);
    
    if (currentMemoryMB > MEMORY_THRESHOLD_MB) {
        console.log('⚠️ High memory usage detected - forcing mock mode for stability');
        return 'mock';
    }
    
    if (!enableRealWhatsApp) {
        console.log('🔧 Mode: MOCK (Environment configuration)');
        return 'mock';
    }
    
    // Check if production dependencies are available
    try {
        require('whatsapp-web.js');
        require('puppeteer');
        console.log('🔧 Mode: PRODUCTION (Full WhatsApp functionality)');
        return 'production';
    } catch (error) {
        console.log('🔧 Mode: MOCK (Production dependencies not available)');
        console.log('💡 To enable production mode, install: npm install whatsapp-web.js puppeteer');
        return 'mock';
    }
}

// Memory monitoring middleware
function memoryMonitoring(req, res, next) {
    const memUsage = process.memoryUsage();
    const heapUsedMB = Math.round(memUsage.heapUsed / 1024 / 1024);
    
    // Log high memory usage
    if (heapUsedMB > MEMORY_THRESHOLD_MB * 0.8) {
        console.log(`⚠️ High heap usage: ${heapUsedMB}MB`);
    }
    
    // Set memory usage in response headers for monitoring
    res.setHeader('X-Memory-Usage-MB', heapUsedMB);
    next();
}

// Apply memory monitoring
app.use(memoryMonitoring);

// Determine mode and start appropriate server
const mode = determineOptimalMode();

// Memory optimization settings
if (mode === 'mock') {
    // Minimize memory for mock mode
    if (global.gc) {
        setInterval(() => {
            global.gc();
        }, 30000); // Force garbage collection every 30 seconds
    }
    
    console.log('🚀 Starting lightweight mock server...');
    require('./server.js');
} else {
    console.log('🚀 Starting production server with memory optimizations...');
    
    // Set production memory limits
    process.env.MAX_RECONNECT_ATTEMPTS = process.env.MAX_RECONNECT_ATTEMPTS || '2';
    process.env.INITIAL_RECONNECT_DELAY = process.env.INITIAL_RECONNECT_DELAY || '10000';
    process.env.SHOW_QR = process.env.SHOW_QR || 'false';
    
    require('./server-production.js');
}

// Graceful shutdown on memory pressure
process.on('SIGTERM', () => {
    console.log('🛑 Received SIGTERM, graceful shutdown...');
    process.exit(0);
});

process.on('SIGINT', () => {
    console.log('🛑 Received SIGINT, graceful shutdown...');
    process.exit(0);
});

// Monitor memory and restart if needed
setInterval(() => {
    const memUsage = process.memoryUsage();
    const heapUsedMB = Math.round(memUsage.heapUsed / 1024 / 1024);
    
    if (heapUsedMB > MEMORY_THRESHOLD_MB * 1.2) {
        console.log(`🚨 Critical memory usage: ${heapUsedMB}MB - initiating graceful restart`);
        process.exit(1); // Let container orchestrator restart
    }
}, 60000); // Check every minute

module.exports = app;