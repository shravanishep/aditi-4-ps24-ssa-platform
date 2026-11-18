import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cesium from 'vite-plugin-cesium'

// In production (Vercel), VITE_API_BASE_URL is set to the Render backend URL.
// In development, the dev-server proxy below handles all /api/* requests.
const API_BASE = process.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), cesium()],
  define: {
    __API_BASE__: JSON.stringify(API_BASE),
  },
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
      '/threats': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/catalog': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/events': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/ml': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/cdm': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/pc': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/maneuver': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass: (req) => (req.headers.accept?.includes('text/html') ? '/index.html' : undefined),
      },
      '/docs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
