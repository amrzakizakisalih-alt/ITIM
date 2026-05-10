import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    https: {
      key: fs.readFileSync('./localhost-key.pem'),
      cert: fs.readFileSync('./localhost.pem'),
    },
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'https://127.0.0.1:9000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'wss://127.0.0.1:9000',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
  },
})
