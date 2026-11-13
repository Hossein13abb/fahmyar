import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { toFarsiNumber } from '../utils/faNumbers'
import {
  GraduationCap,
  User,
  Lock,
  School,
  ArrowLeft,
  Eye,
  EyeOff,
  Loader2,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import CustomDropdown from './CustomDropdown'
import { friendlyError } from '../api/client'

const SUBJECTS = [
  { value: 'experimental', label: 'تجربی' },
  { value: 'math', label: 'ریاضی / فیزیک' },
  { value: 'general', label: 'عمومی' },
]
const GRADES = [10, 11, 12]
const STAFF_ROLES = ['teacher', 'admin', 'school_staff']

/**
 * پنل ورود/عضویتِ مدالِ صفحهٔ اصلی — تنها درگاه ورود فهم‌یار.
 * portal: 'staff' (فقط کادر مدرسه) | 'student' (ورود/عضویت دانش‌آموزی)
 */
export default function LoginModal({ portal, onClose }) {
  const { login, register, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const isStaff = portal === 'staff'

  const [mode, setMode] = useState('login') // login | register (فقط student)
  const role = isStaff ? 'school_staff' : 'student'
  const activeMode = isStaff ? 'login' : mode
  const [showPassword, setShowPassword] = useState(false)
  const [form, setForm] = useState({
    username: '',
    password: '',
    full_name: '',
    grade: 11,
    major: 'experimental',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // بستن با Escape + قفل اسکرول بدنه
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [onClose])

  if (!portal) return null

  const set = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    setError('')
  }

  const onSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (form.username.trim().length < 3) return setError('نام کاربری حداقل ۳ نویسه باشد.')
    if (form.password.length < 6) return setError('رمز عبور حداقل ۶ نویسه باشد.')
    setLoading(true)
    try {
      let loggedUser
      if (activeMode === 'login') {
        loggedUser = await login(form.username.trim(), form.password)
      } else {
        const payload = {
          username: form.username.trim(),
          password: form.password,
          role,
          full_name: form.full_name.trim(),
        }
        if (role === 'student') {
          payload.grade = Number(form.grade)
          payload.major = form.major
        }
        loggedUser = await register(payload)
      }
      // ── دیوار آتش بین دو درگاه ──
      const allowed = isStaff ? STAFF_ROLES.includes(loggedUser.role) : loggedUser.role === 'student'
      if (!allowed) {
        logout()
        setError(
          isStaff
            ? 'این حساب دسترسی کادر مدرسه ندارد؛ این درگاه فقط برای حساب‌های کادر مدرسه (دبیر / مدیر / کادر مدرسه) است.'
            : 'این حساب با درگاه دانش‌آموز سازگار نیست؛ لطفاً از درگاه کادر مدرسه وارد شوید.',
        )
        setLoading(false)
        return
      }
      const from = location.state?.from
      const fallback = isStaff ? '/staff' : '/dashboard'
      const target = typeof from === 'string' && from.startsWith('/') && from !== '/' ? from : fallback
      onClose?.()
      navigate(target, { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }

  const accentBox = isStaff
    ? 'from-brand-800 via-brand-900 to-brand-950 text-brand-50'
    : 'from-emerald-600 via-emerald-700 to-emerald-900 text-white'

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/55 p-3 backdrop-blur-sm sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={isStaff ? 'ورود کادر مدرسه' : 'ورود دانش‌آموز'}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-3xl border border-white/10 bg-white shadow-lift"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── سربرگ درگاه ── */}
        <div className={`relative bg-gradient-to-bl ${accentBox} px-6 py-5`}>
          <button
            onClick={onClose}
            aria-label="بستن پنجرهٔ ورود"
            className="absolute left-4 top-4 rounded-xl bg-white/10 p-1.5 text-white/85 ring-1 ring-white/20 transition hover:bg-white/20 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
          <span className="inline-flex rounded-2xl bg-white/10 p-3 ring-1 ring-white/20">
            {isStaff ? (
              <School className="h-7 w-7 text-amber-200" strokeWidth={1.7} />
            ) : (
              <GraduationCap className="h-7 w-7 text-emerald-100" strokeWidth={1.7} />
            )}
          </span>
          <h2 className="mt-3 text-xl font-black text-white">
            {isStaff ? 'ورود کادر مدرسه' : activeMode === 'login' ? 'ورود دانش‌آموز' : 'عضویت دانش‌آموزی'}
          </h2>
          <p className="mt-1 text-[11px] font-bold leading-5 text-white/75">
            {isStaff
              ? 'برای مدیریت آزمون‌ها، آزمون‌ساز کنکوری و مشاهدهٔ نتایج کیفی دانش‌آموزان وارد شو.'
              : 'با حساب خودت وارد شو و مسیر فهمیدنت را بدون نمره و استرس ادامه بده.'}
          </p>
        </div>

        {/* ── بدنهٔ فرم ── */}
        <div className="px-6 py-5">
          {isStaff ? (
            <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-[11px] font-bold leading-6 text-amber-900">
              ورود دانش‌آموز از این درگاه ممکن نیست — فقط حساب‌های کادر مدرسه (دبیر / مدیر / کادر مدرسه) پذیرفته می‌شوند.
            </div>
          ) : (
            <div className="mb-4 flex rounded-2xl bg-brand-50 p-1.5 ring-1 ring-brand-100" role="tablist" aria-label="ورود یا عضویت">
              {[
                { key: 'login', label: 'ورود' },
                { key: 'register', label: 'عضویت' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  role="tab"
                  aria-selected={mode === tab.key}
                  onClick={() => {
                    setMode(tab.key)
                    setError('')
                  }}
                  className={`flex-1 rounded-xl py-2 text-[13px] font-black transition ${
                    mode === tab.key ? 'bg-white text-brand-800 shadow-card' : 'text-brand-600 hover:text-brand-900'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-3.5" noValidate>
            {activeMode === 'register' && (
              <div>
                <label className="label" htmlFor="modal-full_name">نام و نام خانوادگی (اختیاری)</label>
                <input id="modal-full_name" className="input" value={form.full_name} onChange={set('full_name')} placeholder="مثلاً: رها محمدی" autoComplete="name" />
              </div>
            )}

            <div>
              <label className="label" htmlFor="modal-username">نام کاربری</label>
              <div className="relative">
                <User className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input id="modal-username" className="input pr-12" value={form.username} onChange={set('username')} placeholder="مثلاً: raha11" autoComplete="username" dir="auto" autoFocus />
              </div>
            </div>

            <div>
              <label className="label" htmlFor="modal-password">رمز عبور</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input
                  id="modal-password"
                  className="input px-12"
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={set('password')}
                  placeholder="حداقل ۶ نویسه"
                  autoComplete={activeMode === 'login' ? 'current-password' : 'new-password'}
                  dir="auto"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute left-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:text-brand-700"
                  aria-label={showPassword ? 'پنهان کردن رمز' : 'نمایش رمز'}
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {activeMode === 'register' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="modal-grade">پایه</label>
                  <CustomDropdown
                    id="modal-grade"
                    value={form.grade}
                    onChange={(v) => setForm((f) => ({ ...f, grade: v }))}
                    ariaLabel="پایه"
                    options={GRADES.map((g) => ({ value: g, label: `پایهٔ ${toFarsiNumber(g)}` }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="modal-major">رشته</label>
                  <CustomDropdown
                    id="modal-major"
                    value={form.major}
                    onChange={(v) => setForm((f) => ({ ...f, major: v }))}
                    ariaLabel="رشته"
                    options={SUBJECTS.map((s) => ({ value: s.value, label: s.label }))}
                  />
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] font-medium leading-6 text-amber-900" role="alert">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand-700 py-3.5 text-[14px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {loading && <Loader2 className="h-5 w-5 animate-spin" />}
              {isStaff ? 'ورود کادر مدرسه' : activeMode === 'login' ? 'ورود به فهم‌یار' : 'ساخت حساب و شروع'}
              {!loading && <ArrowLeft className="h-5 w-5" />}
            </button>
          </form>

          <p className="mt-4 text-center text-[10px] leading-6 text-slate-400">
            {isStaff ? (
              <>حساب دمو — مدیر: <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">admin / admin123</code> · دبیر: <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">teacher1 / teacher123</code> · کادر مدرسه: <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">school_staff1 / school_staff123</code></>
            ) : (
              <>حساب دمو دانش‌آموز: <code className="rounded bg-brand-50 px-1.5 py-0.5 text-brand-800">student1 / student123</code></>
            )}
          </p>
        </div>
      </div>
    </div>
  )
}
