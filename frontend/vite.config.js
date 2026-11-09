import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// بک‌اند FastAPI روی پورت ۸۰۰۰ اجرا می‌شود؛ مرورگر هرگز مستقیم با 127.0.0.1 حرف نمی‌زند،
// بلکه درخواست‌های /api از طریق همین پروکسی به بک‌اند می‌رسند (هم در dev و هم در preview).
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
