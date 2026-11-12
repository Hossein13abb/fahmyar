import { useCallback, useEffect, useState } from 'react'
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
  ChevronLeft,
  RefreshCw,
  AlertTriangle,
  Loader2,
  ScrollText,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import ExamBuilder from './ExamBuilder'
import { toFarsiNumber, subjectFa } from '../utils/faNumbers'
import client, { friendlyError } from '../api/client'

// ── دادهٔ واقعی — از GET /api/teacher/student-results (SQLite + خروجی موتور ECD) ──
const STATUS_CLS = {
  stable: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  growing: 'bg-amber-50 text-amber-800 ring-amber-200',
  remedial: 'bg-rose-50 text-rose-800 ring-rose-200',
  insufficient: 'bg-slate-100 text-slate-600 ring-slate-200',
}

const AVATAR_GRAD = [
  'from-emerald-400 to-teal-600',
  'from-cyan-400 to-sky-600',
  'from-violet-400 to-purple-600',
  'from-amber-400 to-orange-600',
  'from-rose-400 to-pink-600',
  'from-lime-400 to-emerald-600',
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
  const [rows, setRows] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  const loadResults = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    setError('')
    try {
      const { data } = await client.get('/api/teacher/student-results')
      setRows(Array.isArray(data?.students) ? data.students : [])
      setSummary(data?.summary ?? null)
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadResults()
  }, [loadResults])

  const statTiles = summary
    ? [
        { Icon: Users, value: toFarsiNumber(summary.students_total), label: 'دانش‌آموز ثبت‌شده', tone: 'text-emerald-700 bg-emerald-50 ring-emerald-200' },
        { Icon: ClipboardCheck, value: toFarsiNumber(summary.reports_last_30_days), label: 'گزارش ثبت‌شده (۳۰ روز اخیر)', tone: 'text-sky-700 bg-sky-50 ring-sky-200' },
        { Icon: HandHeart, value: toFarsiNumber(summary.remedial_count), label: 'نیازمند آموزش جبرانی', tone: 'text-rose-700 bg-rose-50 ring-rose-200' },
        { Icon: Shapes, value: toFarsiNumber(summary.sessions_completed_total), label: 'کل آزمون‌های ثبت‌شده', tone: 'text-amber-700 bg-amber-50 ring-amber-200' },
      ]
    : []

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
              {user?.full_name || user?.username} · {user?.role === 'admin' ? 'مدیر مدرسه' : 'دبیر'}
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
            {statTiles.map(({ Icon, value, label, tone }) => (
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
                <h2 className="text-[14px] font-black text-slate-800">نتایج واقعی دانش‌آموزان — بر پایهٔ آزمون‌های ثبت‌شده</h2>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-[10px] font-bold text-emerald-700 ring-1 ring-emerald-200">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> اتصال زنده به دیتابیس
                </span>
                <button
                  type="button"
                  onClick={() => loadResults(true)}
                  disabled={refreshing}
                  className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-bold text-slate-500 transition hover:border-brand-200 hover:text-brand-700 disabled:opacity-60"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} /> به‌روزرسانی
                </button>
              </div>
            </div>

            {loading ? (
              <div className="flex flex-col items-center gap-3 px-5 py-14 text-center">
                <Loader2 className="h-7 w-7 animate-spin text-emerald-600" />
                <p className="text-[12px] font-bold text-slate-500">در حال دریافت نتایج واقعی از دیتابیس…</p>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center gap-3 px-5 py-12 text-center">
                <AlertTriangle className="h-8 w-8 text-amber-500" />
                <p className="max-w-md text-[12px] font-bold leading-6 text-amber-900">{error}</p>
                <button
                  type="button"
                  onClick={() => loadResults()}
                  className="rounded-2xl border border-brand-200 px-5 py-2 text-[11px] font-bold text-brand-800 transition hover:bg-brand-50"
                >
                  تلاش دوباره
                </button>
              </div>
            ) : rows.length === 0 ? (
              <p className="px-5 py-12 text-center text-[12px] font-bold text-slate-400">هنوز دانش‌آموزی در دیتابیس ثبت نشده است.</p>
            ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-right text-[12px]">
                <thead>
                  <tr className="bg-slate-50 text-[10px] font-black uppercase tracking-wide text-slate-400">
                    <th className="px-5 py-3 font-black">دانش‌آموز</th>
                    <th className="px-5 py-3 font-black">درس — مبحث</th>
                    <th className="px-5 py-3 font-black">تاریخ آزمون</th>
                    <th className="px-5 py-3 font-black">وضعیت درک (ECD)</th>
                    <th className="px-5 py-3 font-black"><span className="sr-only">اقدام</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((row, i) => {
                    const chip = STATUS_CLS[row.comprehension] ?? STATUS_CLS.insufficient
                    const fullName = row.student?.full_name?.trim() || row.student?.username || '—'
                    const examDate = row.exam_date
                      ? new Date(row.exam_date).toLocaleDateString('fa-IR', { dateStyle: 'long' })
                      : '—'
                    return (
                      <tr key={row.student?.id ?? i} className="transition-colors hover:bg-slate-50/70">
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span
                              className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-bl text-[11px] font-black text-white ${AVATAR_GRAD[i % AVATAR_GRAD.length]}`}
                            >
                              {fmtFaName(fullName)}
                            </span>
                            <div>
                              <p className="font-black text-slate-800">{fullName}</p>
                              <p className="text-[10px] font-medium text-slate-400">
                                {row.grade ? `پایهٔ ${toFarsiNumber(row.grade)}` : 'پایهٔ —'} · {toFarsiNumber(row.completed_exams)} آزمون ثبت‌شده
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <p className="font-bold text-slate-700">{row.subject ? subjectFa(row.subject) : '—'}</p>
                          <p className="max-w-[16rem] truncate text-[10px] font-medium text-slate-400" title={row.concept_name ?? ''}>
                            {row.concept_name ?? 'هنوز آزمونی ثبت نشده'}
                          </p>
                        </td>
                        <td className="whitespace-nowrap px-5 py-3 text-[11px] font-medium text-slate-500">{examDate}</td>
                        <td className="px-5 py-3">
                          <span className={`inline-flex whitespace-nowrap rounded-full px-3 py-1 text-[10px] font-black ring-1 ${chip}`}>
                            {row.comprehension_label || 'شواهد ناکافی'}
                          </span>
                          {row.needs_teacher_review && (
                            <span className="mt-1 block text-[9px] font-bold text-amber-700">نیازمند نگاه معلم</span>
                          )}
                        </td>
                        <td className="px-5 py-3 text-left">
                          {row.last_session_id ? (
                            <button
                              type="button"
                              onClick={() => navigate(`/teacher/report/${row.student.id}/${row.last_session_id}`)}
                              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-xl border border-emerald-200 bg-emerald-50/60 px-3 py-1.5 text-[10px] font-black text-emerald-800 transition hover:border-emerald-300 hover:bg-emerald-100"
                            >
                              <ScrollText className="h-3.5 w-3.5" />
                              مشاهدهٔ کارنامه کیفی
                              <ChevronLeft className="h-3.5 w-3.5" />
                            </button>
                          ) : (
                            <span className="inline-flex items-center whitespace-nowrap rounded-xl border border-slate-100 px-3 py-1.5 text-[10px] font-bold text-slate-300">
                              کارنامه‌ای ثبت نشده
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            )}

            <div className="border-t border-slate-100 px-5 py-3">
              <p className="text-[10px] font-medium leading-5 text-slate-400">
                این جدول فقط وضعیت کیفیِ فهم را نشان می‌دهد؛ هیچ نمره، درصد یا رتبه‌ای نمایش داده نمی‌شود. «مشاهدهٔ کارنامه کیفی» دقیقاً همان کارنامهٔ تحلیلی کامل (همراه با گراف پیش‌نیازها) را باز می‌کند.
              </p>
            </div>
          </section>
        </div>
      )}

      {/* ══════════ تب طراحی آزمون ══════════ */}
      {tab === 'builder' && <ExamBuilder embedded />}
    </div>
  )
}
