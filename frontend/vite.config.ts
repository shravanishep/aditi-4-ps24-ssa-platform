import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Vite dev server proxies all API routes to the FastAPI backend.
// This avoids CORS issues during development without modifying the backend.
// For production, set VITE_API_BASE_URL to the actual backend URL.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/satellites': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/conjunction': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
    },
  },
})
