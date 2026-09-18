import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000'

// The dev server proxies REST and Socket.IO to the FastAPI backend, so the
// browser only ever talks to one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  worker: { format: 'es' },
  server: {
    proxy: {
      '/api': backend,
      '/socket.io': { target: backend, ws: true },
    },
  },
})
