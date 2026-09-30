import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// VITE_* variables are read from the repo-root .env; only VITE_-prefixed keys reach the browser.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..',
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src'), '@config': path.resolve(import.meta.dirname, '../config') } },
  server: { port: 5173, fs: { allow: ['..'] }, proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { chunkSizeWarningLimit: 1500 },
})
