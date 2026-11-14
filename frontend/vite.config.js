import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// بک‌اند FastAPI روی پورت ۸۰۰۰ اجرا می‌شود؛ مرورگر هرگز مستقیم با 127.0.0.1 حرف نمی‌زند،
// بلکه درخواست‌های /api از طریق همین پروکسی به بک‌اند می‌رسند (هم در dev و هم در preview).
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // دو ورودی: اپ کاربر، و نقطهٔ ورودِ چاپ که موتور PDF آن را باز می‌کند.
      // خروجی چاپ به assets/ می‌رود تا مسیرِ ثابت و قابل‌اتکا داشته باشد.
      input: {
        main: 'index.html',
        print: 'print.html',
      },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
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
