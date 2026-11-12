import { useNavigate } from 'react-router-dom'
import {
  GraduationCap,
  School,
  ArrowLeft,
  Sparkles,
  BookOpenCheck,
  Wand2,
  ListChecks,
} from 'lucide-react'

export default function Home() {
  const navigate = useNavigate()
  // کلیک روی کارت‌ها، کاربر را مستقیماً لاگین نمی‌کند — بلکه فرم ورود همان درگاه را باز می‌کند
  const goStaff = () => navigate('/login/staff')
  const goStudent = () => navigate('/login/student')

  return (
    <div className="relative overflow-hidden">
      {/* ── پس‌زمینهٔ دکوراتیو ── */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -right-24 top-10 h-72 w-72 rounded-full bg-brand-200/40 blur-3xl" />
        <div className="absolute -left-20 bottom-24 h-72 w-72 rounded-full bg-amber-200/40 blur-3xl" />
        <svg className="absolute left-1/2 top-1/3 h-96 w-96 -translate-x-1/2 opacity-[0.05]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="96" stroke="currentColor" strokeWidth="2" strokeDasharray="4 6" className="text-brand-900" />
          <circle cx="100" cy="100" r="64" stroke="currentColor" strokeWidth="2" strokeDasharray="3 5" className="text-brand-900" />
        </svg>
      </div>

      <div className="mx-auto max-w-5xl py-4 sm:py-8">
        {/* ── عنوان ── */}
        <div className="text-center">
          <span className="chip bg-white text-brand-800 shadow-soft ring-1 ring-brand-100">
            <Sparkles className="h-3.5 w-3.5 text-amber-500" /> سامانهٔ فهم‌سنجی تشخیصی
          </span>
          <h1 className="mt-4 text-3xl font-black leading-[1.35] text-brand-950 sm:text-[42px]">
            یک قدم تا <span className="bg-gradient-to-l from-brand-600 to-brand-800 bg-clip-text text-transparent">فهم عمیق‌تر</span>
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-[14px] leading-8 text-slate-600">
            فهم‌یار دو راه دارد؛ هر کدام را که مربوط توست انتخاب کن.
          </p>
        </div>

        {/* ── دو مسیر اصلی ── */}
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {/* کارت کادر مدرسه */}
          <button
            onClick={goStaff}
            className="group relative overflow-hidden rounded-2xl border border-brand-800/60 bg-gradient-to-bl from-brand-800 via-brand-900 to-brand-950 p-6 text-right text-brand-50 shadow-lift transition-transform duration-300 hover:-translate-y-1 sm:p-7"
          >
            <div aria-hidden className="pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full bg-amber-400/15 blur-3xl transition group-hover:bg-amber-400/25" />
            <div className="relative">
              <span className="inline-flex rounded-2xl bg-white/10 p-3.5 ring-1 ring-white/15 backdrop-blur">
                <School className="h-9 w-9 text-amber-200" strokeWidth={1.6} />
              </span>
              <h2 className="mt-4 text-xl font-black text-white sm:text-2xl">ورود کادر مدرسه</h2>
              <p className="mt-1 text-[13px] font-bold text-amber-200/90">طراحی آزمون</p>
              <ul className="mt-4 space-y-2 text-[12px] leading-6 text-brand-100/90">
                <li className="flex items-center gap-2"><BookOpenCheck className="h-4 w-4 shrink-0 text-brand-300" /> ساخت دفترچهٔ ترکیبی از چند درس</li>
                <li className="flex items-center gap-2"><ListChecks className="h-4 w-4 shrink-0 text-brand-300" /> تعیین تعداد سؤال، زمان و منبع (بانک مؤسسات / هوش مصنوعی / ترکیبی)</li>
                <li className="flex items-center gap-2"><Wand2 className="h-4 w-4 shrink-0 text-brand-300" /> دفترچه‌های تشخیصی با سؤالات عمیق، نه حفظی</li>
              </ul>
              <span className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-amber-300 px-5 py-3 text-[13px] font-black text-brand-950 shadow transition group-hover:bg-amber-200">
                ورود به داشبورد مدرسه
                <ArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
              </span>
            </div>
          </button>

          {/* کارت دانش‌آموز */}
          <button
            onClick={goStudent}
            className="group relative overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-6 text-right text-brand-950 shadow-lift transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_24px_56px_rgba(13,39,31,0.22)] sm:p-7"
          >
            <div aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-brand-100/60 blur-3xl transition group-hover:bg-brand-100" />
            <div className="relative">
              <span className="inline-flex rounded-2xl bg-brand-50 p-3.5 ring-1 ring-brand-100">
                <GraduationCap className="h-9 w-9 text-brand-700" strokeWidth={1.6} />
              </span>
              <h2 className="mt-4 text-xl font-black text-brand-950 sm:text-2xl">ورود دانش‌آموز</h2>
              <p className="mt-1 text-[13px] font-bold text-brand-700">فهم‌سنجی</p>
              <ul className="mt-4 space-y-2 text-[12px] leading-6 text-slate-600">
                <li className="flex items-center gap-2"><BookOpenCheck className="h-4 w-4 shrink-0 text-brand-600" /> آزمون جامع تشخیصیِ ۹ سؤالی از هر مفهوم</li>
                <li className="flex items-center gap-2"><ListChecks className="h-4 w-4 shrink-0 text-brand-600" /> ریشه‌یابی بدفهمی‌ها — حتی اگر ریشه‌اش در درس دیگری باشد</li>
                <li className="flex items-center gap-2"><Wand2 className="h-4 w-4 shrink-0 text-brand-600" /> گزارش کامل فهمیدنت، قدم‌به‌قدم و بدون استرس</li>
              </ul>
              <span className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-5 py-3 text-[13px] font-black text-white shadow-lift transition group-hover:bg-brand-800">
                ورود به فهم‌سنجی من
                <ArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
              </span>
            </div>
          </button>
        </div>
      </div>
    </div>
  )
}
