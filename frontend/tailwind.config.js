/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        vazir: ['Vazirmatn', 'Tahoma', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        // پالت آرام و استرس‌زدای فهم‌یار — سبز زمردی + ایندیگو ملایم + کهربایی گرم
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
        soft: '0 10px 34px rgba(13, 39, 31, 0.10)',
        card: '0 2px 14px rgba(13, 39, 31, 0.07)',
        lift: '0 18px 48px rgba(13, 39, 31, 0.16)',
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
