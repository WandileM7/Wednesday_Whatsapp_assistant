import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
const BACKEND = process.env.BACKEND_URL || "http://localhost:8000"
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true,
    proxy: { "/ws": { target: BACKEND, ws: true, changeOrigin: true }, "/health": BACKEND, "/voice": BACKEND, "/whatsapp": BACKEND } },
  build: { outDir: "dist", emptyOutDir: true },
})