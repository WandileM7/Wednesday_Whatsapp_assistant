import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/health': 'http://localhost:5000',
      '/services': 'http://localhost:5000',
    }
  },
  build: {
    outDir: '../static/dashboard',
    emptyOutDir: true,
  }
})
