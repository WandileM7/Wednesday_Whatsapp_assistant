import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/health': 'http://localhost:3000',
      '/send': 'http://localhost:3000',
      '/whatsapp-status': 'http://localhost:3000',
      '/whatsapp-qr': 'http://localhost:3000',
      '/n8n-status': 'http://localhost:3000',
    }
  },
  build: {
    outDir: '../static/dashboard',
    emptyOutDir: true,
  }
})
