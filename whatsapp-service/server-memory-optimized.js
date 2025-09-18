/**
 * Memory-Optimized WhatsApp Service - Production Only
 * No mock mode fallbacks - uses aggressive memory optimization for real WhatsApp functionality
 */

const express = require('express');
const fs = require('fs-extra');
const path = require('path');
const os = require('os');

// Immediately load the optimized production server
console.log('🚀 Starting Memory-Optimized Production WhatsApp Service');
console.log('📊 Production-only mode with aggressive memory optimization');
console.log('🚫 Mock mode eliminated - real WhatsApp functionality only');

// Check if dependencies are available before starting
try {
    require('whatsapp-web.js');
    require('puppeteer');
    console.log('✅ WhatsApp dependencies verified');
} catch (error) {
    console.error('❌ Missing required dependencies for WhatsApp service:');
    console.error('💡 Install with: npm install whatsapp-web.js puppeteer');
    console.error('🚫 Exiting - mock mode not available in this implementation');
    process.exit(1);
}

// Set optimized environment variables
process.env.ENABLE_REAL_WHATSAPP = 'true'; // Force production mode
process.env.MAX_RECONNECT_ATTEMPTS = process.env.MAX_RECONNECT_ATTEMPTS || '2';
process.env.INITIAL_RECONNECT_DELAY = process.env.INITIAL_RECONNECT_DELAY || '10000';
process.env.SHOW_QR = process.env.SHOW_QR || 'false';
process.env.MAX_HEAP_SIZE_MB = process.env.MAX_HEAP_SIZE_MB || '256';
process.env.GC_INTERVAL_MS = process.env.GC_INTERVAL_MS || '15000';

// Memory optimization: Enable garbage collection
if (process.env.NODE_ENV === 'production') {
    process.env.NODE_OPTIONS = (process.env.NODE_OPTIONS || '') + ' --expose-gc --max-old-space-size=256';
}

console.log('🔧 Starting optimized production server...');
require('./server-optimized-production.js');

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