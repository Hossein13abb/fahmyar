import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  School,
  LogOut,
  Users,
  ClipboardEdit,
  ClipboardCheck,
  HandHeart,
  Shapes,
  PenLine,
  CalendarClock,
  ChevronLeft,
  Info,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import ExamBuilder from './ExamBuilder'

// ── داده‌های نمونه برای نمایش (Mock) — اتصال به دادهٔ واقعی در نسخهٔ بعد ──
const STATUS_META = {
  stable: { label: 'تثبیت شده', cls: 'bg-emerald-50 text-emerald-800 ring-emerald-200' },
  growing: { label: 'در حال پرورش', cls: 'bg-amber-50 text-amber-800 ring-amber-200' },
  remedial: { label: 'نیازمند آموزش جبرانی', cls: 'bg-rose-50 text-rose-800 ring-rose-200' },
  insufficient: { label: 'شواهد ناکافی', cls: 'bg-slate-100 text-slate-600 ring-slate-200' },
}

const MOCK_STUDENTS = [
  { name: 'آریا محمدی', grade: 11, subject: 'فیزیک', concept: 'قانون اهم (I = V/R)', status: 'growing', last: 'امروز · ۱۰:۱۵' },
  { name: 'ثنا احمدی', grade: 11, subject: 'ریاضی', concept: 'تابع درجهٔ دوم', status: 'stable', last: 'امروز · ۰۹:۴۰' },
  { name: 'رها کریمی', grade: 10, subject: 'شیمی', concept: 'عدد اکسایش', status: 'remedial', last: 'دیروز · ۱۶:۳۰' },
  { name: 'مهرسا نیک‌نفس', grade: 12, subject: 'زیست‌شناسی', concept: 'میتوز', status: 'growing', last: 'دیروز · ۱۱:۰۵' },
  { name: 'آراد توکلی', grade: 11, subject: 'ریاضی', concept: 'مشتق و نرخ تغییر', status: 'insufficient', last: '۲ روز پیش' },
  { name: 'پارمیس شریفی', grade: 10, subject: 'ادبیات فارسی', concept: 'تشخیص و کنایه', status: 'stable', last: '۳ روز پیش' },
  { name: 'سامان قاسمی', grade: 12, subject: 'فیزیک', concept: 'قوانین نیوتن', status: 'remedial', last: '۳ روز پیش' },
  { name: 'نیایش رستمی', grade: 11, subject: 'عربی', concept: 'مفعول مطلق', status: 'growing', last: '۴ روز پیش' },
]

const AVATAR_GRAD = [
  'from-emerald-400 to-teal-600',
  'from-cyan-400 to-sky-600',
  'from-violet-400 to-purple-600',
  'from-amber-400 to-orange-600',
  'from-rose-400 to-pink-600',
  'from-lime-400 to-emerald-600',
]

const STAT_TILES = [
  { Icon: Users, value: '۱۲۸', label: 'دانش‌آموز فعال', tone: 'text-emerald-700 bg-emerald-50 ring-emerald-200' },
  { Icon: ClipboardCheck, value: '۳۴', label: 'گزارش دریافتی این هفته', tone: 'text-sky-700 bg-sky-50 ring-sky-200' },
  { Icon: HandHeart, value: '۱۷', label: 'نیازمند آموزش امروز', tone: 'text-rose-700 bg-rose-50 ring-rose-200' },
  { Icon: Shapes, value: '۶', label: 'مفهوم در حال تمرکز', tone: 'text-amber-700 bg-amber-50 ring-amber-200' },
]

const fmtFaName = (full) => full.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('‌')

const TABS = [
  { key: 'results', label: 'نتایج دانش‌آموزان', Icon: Users },
  { key: 'builder', label: 'طراحی آزمون', Icon: ClipboardEdit },
]

export default function SchoolStaffDashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState('results')
  const [notice, setNotice] = useState('')

  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── هدر داشبورد کادر مدرسه ── */}
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/70 bg-white px-5 py-3 shadow-soft">
        <div className="flex items-center gap-3">
          <span className="rounded-2xl bg-brand-50 p-2.5 ring-1 ring-brand-100">
            <School className="h-5 w-5 text-brand-700" />
          </span>
          <div>
            <p className="text-[13px] font-black text-slate-800">پنل کادر مدرسه</p>
            <p className="text-[10px] font-medium text-slate-400">
              {user?.full_name || user?.username} · دبیر فیزیک و ریاضی
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-[12px] font-bold text-slate-600 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700"
        >
          <LogOut className="h-4 w-4" />
          خروج از حساب
        </button>
      </header>

      {/* ── تب‌های داشبورد ── */}
      <div
        className="flex gap-2 rounded-2xl border border-slate-200/70 bg-white p-2 shadow-soft"
        role="tablist"
        aria-label="بخش‌های پنل کادر مدرسه"
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = tab === key
          return (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(key)}
              className={`flex flex-1 items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13px] font-black transition-all duration-200 ${
                active
                  ? 'bg-emerald-600 text-white shadow-lift'
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
              }`}
            >
              <Icon className="h-5 w-5" strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </button>
          )
        })}
      </div>

      {/* ══════════ تب نتایج دانش‌آموزان ══════════ */}
      {tab === 'results' && (
        <div className="space-y-5">
          {/* کارت‌های آمار — فقط شمارش، بدون نمره/رتبه */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {STAT_TILES.map(({ Icon, value, label, tone }) => (
              <div
                key={label}
                className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-soft transition hover:shadow-lift"
              >
                <span className={`inline-flex rounded-xl p-2 ring-1 ${tone}`}>
                  <Icon className="h-5 w-5" strokeWidth={1.9} />
                </span>
                <p className="mt-2 text-xl font-black text-slate-800">{value}</p>
                <p className="mt-0.5 text-[10px] font-bold leading-4 text-slate-400">{label}</p>
              </div>
            ))}
          </div>

          {/* جدول کیفی دانش‌آموزان */}
          <section className="overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-soft">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div className="flex items-center gap-2">
                <PenLine className="h-5 w-5 text-brand-700" />
                <h2 className="text-[14px] font-black text-slate-800">وضعیت کیفی دانش‌آموزان — پایهٔ ۱۱ تجربی</h2>
              </div>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-[10px] font-bold text-slate-500 ring-1 ring-slate-200">
                <CalendarClock className="h-3.5 w-3.5" /> داده‌های نمونه (Mock)
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-right text-[12px]">
                <thead>
                  <tr className="bg-slate-50 text-[10px] font-black uppercase tracking-wide text-slate-400">
                    <th className="px-5 py-3 font-black">دانش‌آموز</th>
                    <th className="px-5 py-3 font-black">درس — مفهوم</th>
                    <th className="px-5 py-3 font-black">آخرین وضعیت کیفی</th>
                    <th className="px-5 py-3 font-black">آخرین فعالیت</th>
                    <th className="px-5 py-3 font-black"><span className="sr-only">اقدام</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {MOCK_STUDENTS.map((s, i) => {
                    const meta = STATUS_META[s.status]
                    return (
                      <tr key={s.name} className="transition-colors hover:bg-slate-50/70">
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span
                              className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-bl text-[11px] font-black text-white ${AVATAR_GRAD[i % AVATAR_GRAD.length]}`}
                            >
                              {fmtFaName(s.name)}
                            </span>
                            <div>
                              <p className="font-black text-slate-800">{s.name}</p>
                              <p className="text-[10px] font-medium text-slate-400">پایهٔ {s.grade}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <p className="font-bold text-slate-700">{s.subject}</p>
                          <p className="text-[10px] font-medium text-slate-400">{s.concept}</p>
                        </td>
                        <td className="px-5 py-3">
                          <span className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-[10px] font-black ring-1 ${meta.cls}`}>
                            {meta.label}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-5 py-3 text-[11px] font-medium text-slate-500">{s.last}</td>
                        <td className="px-5 py-3 text-left">
                          <button
                            type="button"
                            onClick={() => setNotice('نسخهٔ نمایشی — اتصال جدول به گزارش‌های واقعی در نسخهٔ بعد.')}
                            className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-1.5 text-[10px] font-black text-slate-500 transition hover:border-brand-200 hover:text-brand-700"
                          >
                            مشاهدهٔ گزارش
                            <ChevronLeft className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="border-t border-slate-100 px-5 py-3">
              {notice ? (
                <p className="flex items-center gap-1.5 text-[10px] font-bold text-amber-700">
                  <Info className="h-3.5 w-3.5" /> {notice}
                </p>
              ) : (
                <p className="text-[10px] font-medium leading-5 text-slate-400">
                  این جدول فقط وضعیت کیفیِ فهم را نشان می‌دهد؛ هیچ نمره، درصد یا رتبه‌ای نمایش داده نمی‌شود.
                </p>
              )}
            </div>
          </section>
        </div>
      )}

      {/* ══════════ تب طراحی آزمون ══════════ */}
      {tab === 'builder' && <ExamBuilder embedded />}
    </div>
  )
}
