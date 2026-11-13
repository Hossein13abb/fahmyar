import { useState } from 'react'
import { useNavigate, useLocation, Navigate, Link } from 'react-router-dom'
import { toFarsiNumber } from '../utils/faNumbers'
import {
  Sparkles,
  ShieldCheck,
  Compass,
  Brain,
  GraduationCap,
  BookOpenCheck,
  User,
  Lock,
  School,
  ArrowLeft,
  Eye,
  EyeOff,
  Loader2,
  Lightbulb,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import CustomDropdown from '../components/CustomDropdown'
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
  { Icon: ShieldCheck, text: 'نقشهٔ روشن از وضعیت فهم: چه چیزی را می‌دانی، چه چیزی مبهم است و چه چیزی را باید از صفر یاد بگیری.' },
]

export default function Login({ portal }) {
  const { login, register, isAuthenticated, user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const isStaff = portal === 'staff'
  const isStudent = portal === 'student'

  const [mode, setMode] = useState('login') // login | register
  // درگاه کادر مدرسه فقط حساب admin را می‌پذیرد؛ درگاه دانش‌آموز فقط حساب student را
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

  if (isAuthenticated && user) {
    return <Navigate to={user.role === 'student' ? '/dashboard' : '/staff'} replace />
  }

  if (!portal) {
    // صفحهٔ انتخاب درگاه — دو مسیر کاملاً جدا برای ورود
    return (
      <div className="mx-auto max-w-3xl py-6 text-center sm:py-10">
        <span className="chip bg-white text-brand-800 shadow-soft ring-1 ring-brand-100">ورود به فهم‌یار</span>
        <h1 className="mt-4 text-3xl font-black text-brand-950">از کدام درگاه وارد می‌شوی؟</h1>
        <p className="mx-auto mt-2 max-w-md text-[13px] leading-7 text-slate-500">
          هر درگاه حساب و دسترسی خودش را دارد — ورود از درگاه اشتباه ممکن نیست.
        </p>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          <Link
            to="/login/staff"
            className="group rounded-2xl border border-brand-800/60 bg-gradient-to-bl from-brand-800 via-brand-900 to-brand-950 p-6 text-right text-brand-50 shadow-lift transition hover:-translate-y-0.5"
          >
            <span className="inline-flex rounded-2xl bg-white/10 p-3 ring-1 ring-white/15"><School className="h-7 w-7 text-amber-200" /></span>
            <span className="mt-4 block text-lg font-black text-white">ورود کادر مدرسه</span>
            <span className="mt-1 block text-[11px] font-bold text-amber-200/90">ورود کادر مدرسه: دبیر · مدیر · کادر مدرسه</span>
            <span className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-amber-300 px-4 py-2.5 text-[12px] font-black text-brand-950 transition group-hover:bg-amber-200">ادامه به درگاه کادر مدرسه <ArrowLeft className="h-4 w-4" /></span>
          </Link>
          <Link
            to="/login/student"
            className="group rounded-2xl border border-slate-200/70 bg-white p-6 text-right shadow-lift transition hover:-translate-y-0.5"
          >
            <span className="inline-flex rounded-2xl bg-brand-50 p-3 ring-1 ring-brand-100"><GraduationCap className="h-7 w-7 text-brand-700" /></span>
            <span className="mt-4 block text-lg font-black text-brand-950">ورود دانش‌آموز</span>
            <span className="mt-1 block text-[11px] font-bold text-brand-700">حساب دانش‌آموزی — فهم‌سنجی بدون نمره</span>
            <span className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-4 py-2.5 text-[12px] font-black text-white transition group-hover:bg-brand-800">ادامه به درگاه دانش‌آموز <ArrowLeft className="h-4 w-4" /></span>
          </Link>
        </div>
        <p className="mx-auto mt-6 text-[11px] leading-6 text-slate-400">
          حساب دمو — مدیر: <code className="rounded bg-slate-100 px-1.5 py-0.5">admin / admin123</code> · دبیر: <code className="rounded bg-slate-100 px-1.5 py-0.5">teacher1 / teacher123</code> · کادر مدرسه: <code className="rounded bg-slate-100 px-1.5 py-0.5">school_staff1 / school_staff123</code> · دانش‌آموز: <code className="rounded bg-slate-100 px-1.5 py-0.5">student1 / student123</code>
        </p>
      </div>
    )
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
      const STAFF_ROLES = ['teacher', 'admin', 'school_staff']
      const allowed = isStaff ? STAFF_ROLES.includes(loggedUser.role) : loggedUser.role === 'student'
      if (!allowed) {
        logout()
        setError(isStaff
          ? 'این حساب دسترسی کادر مدرسه ندارد؛ این درگاه فقط برای حساب‌های کادر مدرسه (دبیر / مدیر / کادر مدرسه) است.'
          : 'این حساب با درگاه دانش‌آموز سازگار نیست؛ لطفاً از درگاه کادر مدرسه وارد شوید.')
        setLoading(false)
        return
      }
      const from = location.state?.from
      const target = typeof from === 'string' && !from.startsWith('/login') ? from : (isStaff ? '/staff' : '/dashboard')
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
            سامانهٔ فهم‌سنجی تشخیصی
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
          {isStudent && (
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
          )}
          {isStaff && (
            <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-[11px] font-bold leading-6 text-amber-900">
              ورود دانش‌آموز از این درگاه ممکن نیست — فقط حساب مدیر مدرسه (admin) پذیرفته می‌شود.
            </div>
          )}

          <h2 className="text-2xl font-black text-brand-950">
            {isStaff ? 'ورود کادر مدرسه' : mode === 'login' ? 'خوش آمدی 👋' : 'به خانوادهٔ فهم‌یار خوش آمدی'}
          </h2>
          <p className="mt-1.5 text-[13px] text-slate-500">
            {isStaff
              ? 'برای مدیریت آزمون‌ها و مشاهدهٔ نتایج کیفی دانش‌آموزان وارد شو.'
              : mode === 'login'
                ? 'با حساب خودت وارد شو و مسیر فهمیدنت را ادامه بده.'
                : 'در کمتر از یک دقیقه حسابت را بساز و اولین فهم‌سنجی را شروع کن.'}
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
            {activeMode === 'register' && (
              <>
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
                  <label className="label" htmlFor="grade">پایه</label>
                  <CustomDropdown
                    id="grade"
                    value={form.grade}
                    onChange={(v) => setForm((f) => ({ ...f, grade: v }))}
                    ariaLabel="پایه"
                    options={GRADES.map((g) => ({ value: g, label: `پایهٔ ${toFarsiNumber(g)}` }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="major">رشته</label>
                  <CustomDropdown
                    id="major"
                    value={form.major}
                    onChange={(v) => setForm((f) => ({ ...f, major: v }))}
                    ariaLabel="رشته"
                    options={SUBJECTS.map((s) => ({ value: s.value, label: s.label }))}
                  />
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
              {isStaff ? 'ورود کادر مدرسه' : activeMode === 'login' ? 'ورود به فهم‌یار' : 'ساخت حساب و شروع'}
            </button>
          </form>

          <p className="mt-5 flex items-start gap-2 text-[11px] leading-6 text-slate-500">
            <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-calm-400" />
            {isStaff
              ? <>حساب دمو مدیر مدرسه: <code className="mx-1 rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-800">admin / admin123</code></>
              : <>حساب دمو دانش‌آموز: <code className="mx-1 rounded bg-brand-50 px-1.5 py-0.5 text-brand-800">student1 / student123</code></>}
          </p>
        </div>
      </section>
    </div>
  )
}
