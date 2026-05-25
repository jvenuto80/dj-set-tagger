import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Detect Tauri dev mode
const isTauri = process.env.TAURI_ENV_PLATFORM !== undefined

export default defineConfig({
  plugins: [react()],
  // Prevent Vite from obscuring Rust errors in Tauri dev
  clearScreen: false,
  server: {
    port: 8080,
    // Tauri expects a fixed port; fail if busy
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  },
  // Environment variables that start with TAURI_ are exposed to the frontend
  envPrefix: ['VITE_', 'TAURI_'],
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Tauri uses Chromium on macOS and will support ES2021
    target: isTauri ? 'es2021' : 'modules',
    minify: !isTauri ? 'esbuild' : true,
  }
})
