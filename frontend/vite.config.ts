import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base: '/app/' — FastAPI mountet das Build-Ergebnis unter /app (siehe
// web/app.py). Ohne das lösen die erzeugten Asset-Pfade relativ zu / auf
// und laufen ins Leere.
export default defineConfig({
  base: '/app/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8765',
      '/applications': 'http://127.0.0.1:8765',
      '/template-assets': 'http://127.0.0.1:8765',
    },
  },
})
