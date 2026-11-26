/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        vazir: ['Vazirmatn', 'Tahoma', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // ── توکن‌های فاز ۲۷ ──
        //
        // ⚠️ این‌ها اول داخلِ بلوکِ ``@theme`` در index.css نوشته شده بودند.
        // پروژه Tailwind **v3.4** است و ``@theme`` سینتکسِ v4 است؛ نتیجه این
        // بود که هیچ‌کدام از این کلاس‌ها در CSS نهایی تولید نمی‌شد و کلِ
        // بازطراحی بی‌اثر می‌ماند. تنها راهِ درست در v3، همین‌جاست.
        canvas: '#f2f5f2',        // بومِ خاکستریِ گرم با تهِ سبز
        'canvas-deep': '#e8ede9',
        ink: '#0f2a22',           // متنِ سبزِ زغالی
        'ink-soft': '#3f544c',
        'ink-faint': '#6b7f77',
        surface: {
          DEFAULT: '#ffffff',
          muted: '#f7f9f7',       // پنل‌های فرعی — نه سفیدِ خالص
        },
        primary: {
          DEFAULT: '#1f6a55',
          deep: '#164c3e',
          soft: '#e3f0ea',
        },
        analytic: {
          DEFAULT: '#4f5fa8',
          soft: '#eaeafa',
        },
        caution: {
          DEFAULT: '#b4761a',
          soft: '#fbf1dd',
        },
        danger: {
          DEFAULT: '#b34a5c',
          soft: '#fbeaed',
        },
        brand: {
          50: '#effaf4',
          100: '#d7f3e5',
          200: '#b0e6cf',
          300: '#7ed4b5',
          400: '#4dbc98',
          500: '#2ea37f',
          600: '#238569',
          700: '#1f6a55',
          800: '#1f5546',
          900: '#1d473b',
          950: '#0d271f',
        },
        calm: {
          50: '#fbf7ef',
          100: '#f6ecdc',
          200: '#eddab9',
          300: '#e2c28e',
          400: '#d7a966',
          500: '#cd9249',
        },
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        soft: '0 10px 34px rgba(13, 39, 31, 0.12)',
        card: '0 8px 28px rgba(2, 20, 15, 0.10)',
        lift: '0 18px 48px rgba(2, 20, 15, 0.20)',
        // سایهٔ دو‌لایه: نزدیک و تیز برای تعریفِ لبه + دور و نرم برای عمق.
        // کارت‌های تک‌سایه‌ای «تخت» دیده می‌شدند.
        panel: '0 1px 2px rgba(16,24,40,0.04), 0 12px 32px -12px rgba(13,39,31,0.14)',
        // فاز ۲۷: دو سایهٔ ثبت‌شده — آرام و کمی بلندتر. جایگزینِ ``--shadow-rest``
        // و ``--shadow-lift`` که در :root تعریف شده بودند ولی قابلِ استفاده نبودند.
        rest: '0 1px 2px rgba(15,42,34,0.04), 0 6px 18px -8px rgba(15,42,34,0.10)',
        'rest-lift': '0 2px 4px rgba(15,42,34,0.05), 0 16px 34px -14px rgba(15,42,34,0.18)',
        'panel-hover':
          '0 2px 4px rgba(16,24,40,0.05), 0 24px 48px -16px rgba(13,39,31,0.22)',
        glow: '0 0 0 1px rgba(46,163,127,0.12), 0 14px 40px -12px rgba(46,163,127,0.35)',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        breathe: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.85' },
          '50%': { transform: 'scale(1.06)', opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'fade-up': 'fadeUp 0.5s ease-out both',
        breathe: 'breathe 2.6s ease-in-out infinite',
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [],
}
