// کلاینت HTTP فهم‌یار (Axios)
// نکتهٔ مهمی دربارهٔ آدرس پایه: مرورگر هرگز مستقیم به 127.0.0.1:8000 وصل نمی‌شود؛
// درخواست‌ها نسبی (/api/...) هستند و توسط پروکسیِ Vite به بک‌اند FastAPI می‌رسند.
// در صورت نیاز می‌توان فقط با متغیر محیطی آدرس را عوض کرد:
//   VITE_API_BASE_URL=https://api.example.com npm run dev
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 180000, // فراخوانی مدل‌های AI می‌تواند چند ثانیه طول بکشد
})

// پیوست خودکار توکن JWT به همهٔ درخواست‌ها
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('fahmyar_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// اگر توکن نامعتبر/منقضی شد → پاک‌سازی و هدایت به صفحهٔ ورود
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('fahmyar_token')
      localStorage.removeItem('fahmyar_user')
      if (window.location.pathname !== '/') {
        window.location.assign('/')
      }
    }
    return Promise.reject(error)
  },
)

// پیام خطای فارسی و آرام از هر خطای axios
export function friendlyError(error) {
  const data = error?.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail) && data.detail[0]?.msg) {
    const first = data.detail[0]
    return `${first.msg}${first.loc ? ` (${first.loc.join(' → ')})` : ''}`
  }
  if (error?.code === 'ECONNABORTED') return 'پاسخ سرور خیلی طول کشید؛ لحظه‌ای بعد دوباره تلاش کنید.'
  if (!error?.response) return 'اتصال به سرور برقرار نشد؛ مطمئن شوید بک‌اند روی پورت ۸۰۰۰ اجرا است.'
  return 'خطایی رخ داد؛ لطفاً دوباره تلاش کنید.'
}

export default client
