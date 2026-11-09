import { useState } from 'react'
import { useNavigate, useLocation, Navigate } from 'react-router-dom'
import {
  Sparkles,
  ShieldCheck,
  Compass,
  Brain,
  GraduationCap,
  BookOpenCheck,
  User,
  Lock,
  Eye,
  EyeOff,
  Loader2,
  ChevronDown,
  Lightbulb,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { friendlyError } from '../api/client'

const SUBJECTS = [
  { value: 'experimental', label: 'تجربی' },
  { value: 'math', label: 'ریاضی / فیزیک' },
  { value: 'general', label: 'عمومی' },
]
const GRADES = [10, 11, 12]

function HeroArt() {
  return (
    <svg viewBox="0 0 420 360" className="mx-auto w-full max-w-md" role="img" aria-label="تصویر ذهنیِ فهمیدن">
      <defs>
        <radialGradient id="glow" cx="50%" cy="38%" r="60%">
          <stop offset="0%" stopColor="#fde9c8" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#fde9c8" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="bulb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff7e0" />
          <stop offset="100%" stopColor="#f6d493" />
        </linearGradient>
      </defs>
      <circle cx="210" cy="150" r="150" fill="url(#glow)" />
      {/* لامپ */}
      <g className="origin-[210px_150px] animate-breathe">
        <path
          d="M210 62c-46 0-78 30-78 72 0 24 11 39 21 52 7 9 10 15 10 24h94c0-9 3-15 10-24 10-13 21-28 21-52 0-42-32-72-78-72z"
          fill="url(#bulb)" stroke="#1f6a55" strokeWidth="5" strokeLinejoin="round"
        />
        <path d="M188 238h44M192 254h36M199 270h22" stroke="#1f6a55" strokeWidth="6" strokeLinecap="round" />
        {/* شبکهٔ عصبی درون لامپ */}
        {[[210, 118], [178, 142], [242, 142], [196, 168], [226, 168], [210, 190]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="4.6" fill="#1f6a55" opacity="0.85" />
        ))}
        <path d="M210 118 L178 142 M210 118 L242 142 M178 142 L196 168 M242 142 L226 168 M178 142 L226 168 M242 142 L196 168 M196 168 L210 190 M226 168 L210 190"
              stroke="#1f6a55" strokeWidth="2.4" opacity="0.55" />
      </g>
      {/* سه جرقهٔ فهم */}
      {[[118, 96, 0], [302, 108, 1], [330, 214, 2]].map(([x, y, i]) => (
        <path key={i} d={`M${x} ${y - 9} L${x + 2.4} ${y - 2.4} L${x + 9} ${y} L${x + 2.4} ${y + 2.4} L${x} ${y + 9} L${x - 2.4} ${y + 2.4} L${x - 9} ${y} L${x - 2.4} ${y - 2.4} Z`}
              fill="#7ed4b5" opacity="0.9" />
      ))}
    </svg>
  )
}

const FEATURES = [
  { Icon: Brain, text: 'ریشهٔ خطا را پیدا می‌کند — حتی اگر بین‌درسی باشد (مثلاً خطای فیزیک ریشه‌اش در ریاضی است).' },
  { Icon: Compass, text: 'با سؤال‌های انطباقیِ پی‌درپی، شواهد کیفیِ کافی دربارهٔ فهمیدنت جمع می‌کند.' },
  { Icon: ShieldCheck, text: 'هیچ نمره، رتبه یا مقایسه‌ای نیست — فقط یک نقشهٔ آرام از «فهمیده شد / مبهم است / نونوار».' },
]

export default function Login() {
  const { login, register, isAuthenticated, user } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [mode, setMode] = useState('login') // login | register
  const [role, setRole] = useState('student') // student | teacher
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

  if (isAuthenticated && user) {
    return <Navigate to={user.role === 'student' ? '/dashboard' : '/teacher'} replace />
  }

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
      if (mode === 'login') {
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
      const target = location.state?.from ?? (loggedUser.role === 'student' ? '/dashboard' : '/teacher')
      navigate(target, { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid items-stretch gap-6 lg:grid-cols-2">
      {/* ── ستون معرفی ── */}
      <section className="relative overflow-hidden rounded-4xl border border-brand-800/60 bg-gradient-to-bl from-brand-900 via-brand-800 to-brand-950 p-6 text-brand-50 shadow-lift sm:p-9">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            background:
              'radial-gradient(600px 300px at 80% 0%, rgba(126,212,181,0.35), transparent 60%), radial-gradient(500px 300px at 10% 100%, rgba(253,233,200,0.18), transparent 55%)',
          }}
        />
        <div className="relative flex h-full flex-col">
          <span className="chip w-fit bg-white/10 text-brand-100 ring-1 ring-white/20">
            <Sparkles className="h-4 w-4 text-amber-200" />
            سامانهٔ تشخیصیِ آموزشی — بدون نمره، بدون استرس
          </span>
          <h1 className="mt-6 text-3xl font-black leading-[1.35] sm:text-4xl">
            اینجا «جواب درست» مهم نیست؛
            <br />
            <span className="text-amber-200">«فهمیدنِ تو»</span> مهم است.
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-8 text-brand-100/90">
            فهم‌یار به‌جای تصحیح مکانیکی، مثل یک معلمِ صبور کنارت می‌نشیند؛ تصمیم‌های هوشمندانه می‌سازد
            و دقیق می‌گوید کدام بخش از «فهمیدن» جاافتاده و کدام هنوز مبهم است.
          </p>

          <HeroArt />

          <ul className="mt-auto space-y-3 pt-6 text-[13px] leading-7 text-brand-100/95">
            {FEATURES.map(({ Icon, text }, i) => (
              <li key={i} className="flex items-start gap-3">
                <span className="mt-0.5 rounded-xl bg-white/10 p-1.5 ring-1 ring-white/15">
                  <Icon className="h-4 w-4 text-amber-200" />
                </span>
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ── ستون فرم ── */}
      <section className="card flex flex-col justify-center p-6 sm:p-9">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-6 flex rounded-2xl bg-brand-50 p-1.5 ring-1 ring-brand-100">
            {[
              { key: 'login', label: 'ورود' },
              { key: 'register', label: 'عضویت' },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setMode(tab.key)
                  setError('')
                }}
                className={`flex-1 rounded-xl py-2.5 text-sm font-black transition ${
                  mode === tab.key ? 'bg-white text-brand-800 shadow-card' : 'text-brand-600 hover:text-brand-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <h2 className="text-2xl font-black text-brand-950">
            {mode === 'login' ? 'خوش آمدی 👋' : 'به خانوادهٔ فهم‌یار خوش آمدی'}
          </h2>
          <p className="mt-1.5 text-[13px] text-slate-500">
            {mode === 'login'
              ? 'با حساب خودت وارد شو و مسیر فهمیدنت را ادامه بده.'
              : 'در کمتر از یک دقیقه حسابت را بساز و اولین فهم‌سنجی را شروع کن.'}
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            {mode === 'register' && (
              <>
                <div>
                  <span className="label">شما…</span>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { key: 'student', label: 'دانش‌آموز هستم', Icon: GraduationCap },
                      { key: 'teacher', label: 'معلم / کادر مدرسه', Icon: BookOpenCheck },
                    ].map(({ key, label, Icon }) => (
                      <button
                        type="button"
                        key={key}
                        onClick={() => setRole(key)}
                        aria-pressed={role === key}
                        className={`flex items-center justify-center gap-2 rounded-2xl border px-3 py-3 text-[13px] font-bold transition ${
                          role === key
                            ? 'border-brand-400 bg-brand-50 text-brand-900 ring-2 ring-brand-200'
                            : 'border-slate-200 bg-white text-slate-500 hover:border-brand-200 hover:text-brand-800'
                        }`}
                      >
                        <Icon className="h-5 w-5" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="label" htmlFor="full_name">نام و نام خانوادگی (اختیاری)</label>
                  <input id="full_name" className="input" value={form.full_name} onChange={set('full_name')} placeholder="مثلاً: رها محمدی" autoComplete="name" />
                </div>
              </>
            )}

            <div>
              <label className="label" htmlFor="username">نام کاربری</label>
              <div className="relative">
                <User className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input id="username" className="input pr-12" value={form.username} onChange={set('username')} placeholder="مثلاً: raha11" autoComplete="username" dir="auto" />
              </div>
            </div>

            <div>
              <label className="label" htmlFor="password">رمز عبور</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute right-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input
                  id="password"
                  className="input px-12"
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={set('password')}
                  placeholder="حداقل ۶ نویسه"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
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

            {mode === 'register' && role === 'student' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label" htmlFor="grade">پایه</label>
                  <div className="relative">
                    <select id="grade" className="input appearance-none pl-9" value={form.grade} onChange={set('grade')}>
                      {GRADES.map((g) => (
                        <option key={g} value={g}>پایهٔ {g}</option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  </div>
                </div>
                <div>
                  <label className="label" htmlFor="major">رشته</label>
                  <div className="relative">
                    <select id="major" className="input appearance-none pl-9" value={form.major} onChange={set('major')}>
                      {SUBJECTS.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium leading-7 text-amber-900" role="alert">
                {error}
              </div>
            )}

            <button type="submit" disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand-700 py-3.5 text-[15px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-70">
              {loading && <Loader2 className="h-5 w-5 animate-spin" />}
              {mode === 'login' ? 'ورود به فهم‌یار' : 'ساخت حساب و شروع'}
            </button>
          </form>

          <p className="mt-5 flex items-start gap-2 text-[11px] leading-6 text-slate-500">
            <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-calm-400" />
            حساب دمو برای امتحان: <code className="mx-1 rounded bg-brand-50 px-1.5 py-0.5 text-brand-800">student1 / student123</code> یا <code className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-800">teacher1 / teacher123</code>
          </p>
        </div>
      </section>
    </div>
  )
}
