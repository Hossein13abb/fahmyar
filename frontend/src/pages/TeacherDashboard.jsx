import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Users,
  Layers,
  ListTodo,
  Wallet,
  UserRound,
  Search,
  FileText,
  CalendarDays,
  ThumbsUp,
  ThumbsDown,
  Inbox,
  RefreshCw,
  ChevronLeft,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import CustomDropdown from '../components/CustomDropdown'
import { toFarsiNumber } from '../utils/faNumbers'

const TRIGGER_LABEL = { topic_selection: 'انتخاب موضوع', wrong_answer: 'پاسخ غلط' }

export default function TeacherDashboard() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState(null)
  const [students, setStudents] = useState([])
  const [gradeFilter, setGradeFilter] = useState('')
  const [selected, setSelected] = useState(null)
  const [sessions, setSessions] = useState([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [pendingQuestions, setPendingQuestions] = useState([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)

  const loadAll = async () => {
    setError('')
    const results = await Promise.allSettled([
      client.get('/api/teacher/overview'),
      client.get('/api/teacher/students', { params: gradeFilter ? { grade: gradeFilter } : {} }),
      client.get('/api/teacher/questions/pending', { params: { limit: 5 } }),
    ])
    if (results[0].status === 'fulfilled') setOverview(results[0].value.data)
    if (results[1].status === 'fulfilled') setStudents(results[1].value.data.students ?? [])
    else setError(friendlyError(results[1].reason))
    if (results[2].status === 'fulfilled') setPendingQuestions(results[2].value.data.questions ?? [])
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gradeFilter])

  // انتخاب پیش‌فرض: اولین دانش‌آموز
  useEffect(() => {
    if (!selected && students.length > 0) setSelected(students[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [students])

  // بارگذاری جلسات دانش‌آموز منتخب
  useEffect(() => {
    if (!selected) {
      setSessions([])
      return
    }
    let alive = true
    setLoadingSessions(true)
    client
      .get(`/api/teacher/students/${selected.id}/reports`)
      .then(({ data }) => alive && setSessions(data.sessions ?? []))
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoadingSessions(false))
    return () => {
      alive = false
    }
  }, [selected])

  const filteredStudents = useMemo(() => {
    const q = query.trim()
    if (!q) return students
    return students.filter((s) => (s.full_name || s.username || '').includes(q))
  }, [students, query])

  const moderation = async (questionId, action) => {
    setBusyId(questionId)
    try {
      await client.post(`/api/teacher/questions/${questionId}/${action}`)
      setPendingQuestions((qs) => qs.filter((q) => q.id !== questionId))
      setOverview((o) => (o ? { ...o, questions_pending_approval: Math.max(0, (o.questions_pending_approval ?? 1) - 1) } : o))
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusyId(null)
    }
  }

  const stats = [
    { Icon: UserRound, label: 'دانش‌آموزان', value: overview?.students ?? '—', tone: 'text-brand-700 bg-brand-50' },
    { Icon: Layers, label: 'مفهوم‌های بانک', value: overview?.concepts ?? '—', tone: 'text-indigo-700 bg-indigo-50' },
    { Icon: ListTodo, label: 'سؤالات منتظر تصویب', value: overview?.questions_pending_approval ?? '—', tone: 'text-amber-800 bg-amber-50' },
    { Icon: Wallet, label: 'هزینهٔ AI (دلار)', value: overview ? (overview.ai_cost_usd ?? 0).toFixed(2) : '—', tone: 'text-teal-800 bg-teal-50' },
  ]

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── سربرگ ── */}
      <section className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2.5 text-2xl font-black text-brand-950">
            <span className="rounded-2xl bg-indigo-700 p-2 text-amber-200"><Users className="h-6 w-6" /></span>
            پنل معلم
          </h1>
          <p className="mt-1.5 text-[13px] text-slate-500">گزارش‌های تشخیصی دانش‌آموزان، شواهد کیفی و مدیریت سؤالات هوش مصنوعی.</p>
        </div>
        <button onClick={loadAll} className="flex items-center gap-2 rounded-2xl border border-brand-200 bg-white px-4 py-2.5 text-[12px] font-bold text-brand-800 transition hover:bg-brand-50">
          <RefreshCw className="h-4 w-4" />
          به‌روزرسانی
        </button>
      </section>

      {error && <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium text-amber-900">{error}</div>}

      {/* ── آمار کلی ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map(({ Icon, label, value, tone }) => (
          <div key={label} className="card flex items-center gap-3 p-4">
            <span className={`rounded-2xl p-2.5 ${tone}`}><Icon className="h-6 w-6" /></span>
            <span>
              <span className="block text-xl font-black text-brand-950">{value}</span>
              <span className="block text-[11px] font-medium text-slate-500">{label}</span>
            </span>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-12">
        {/* ── فهرست دانش‌آموزان ── */}
        <aside className="card flex max-h-[34rem] flex-col p-4 lg:col-span-4">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} className="input py-2.5 pr-10 text-[13px]" placeholder="جستجوی نام دانش‌آموز…" aria-label="جستجوی دانش‌آموز" />
            </div>
            <CustomDropdown
              value={gradeFilter}
              onChange={(v) => setGradeFilter(v)}
              ariaLabel="فیلتر پایه"
              className="w-36"
              buttonClassName="py-2.5 text-[13px]"
              options={[
                { value: '', label: 'همهٔ پایه‌ها' },
                { value: 10, label: 'پایهٔ ۱۰' },
                { value: 11, label: 'پایهٔ ۱۱' },
                { value: 12, label: 'پایهٔ ۱۲' },
              ]}
            />
          </div>

          <ul className="mt-3 flex-1 space-y-1.5 overflow-auto" role="listbox" aria-label="دانش‌آموزان">
            {filteredStudents.map((s) => {
              const active = selected?.id === s.id
              return (
                <li key={s.id}>
                  <button
                    role="option"
                    aria-selected={active}
                    onClick={() => setSelected(s)}
                    className={`flex w-full items-center justify-between gap-2 rounded-2xl border px-3 py-2.5 text-right transition ${
                      active ? 'border-brand-400 bg-brand-50 ring-1 ring-brand-200' : 'border-transparent hover:border-brand-100 hover:bg-brand-50/50'
                    }`}
                  >
                    <span className="flex items-center gap-2.5">
                      <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-brand-100 text-[13px] font-black text-brand-800">
                        {(s.full_name || s.username || '؟').trim().charAt(0)}
                      </span>
                      <span>
                        <span className="block text-[13px] font-bold text-brand-950">{s.full_name || s.username}</span>
                        <span className="block text-[10px] text-slate-500">پایهٔ {s.grade != null ? toFarsiNumber(s.grade) : '—'} · {s.major === 'math' ? 'ریاضی' : s.major === 'experimental' ? 'تجربی' : 'عمومی'}</span>
                      </span>
                    </span>
                    <ChevronLeft className={`h-4 w-4 transition ${active ? 'text-brand-600' : 'text-slate-300'}`} />
                  </button>
                </li>
              )
            })}
            {filteredStudents.length === 0 && (
              <li className="rounded-2xl border border-dashed border-slate-200 p-6 text-center text-[12px] text-slate-400">
                دانش‌آموزی یافت نشد.
              </li>
            )}
          </ul>
        </aside>

        {/* ── جلسات دانش‌آموز منتخب ── */}
        <div className="card p-5 lg:col-span-8">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-[15px] font-black text-brand-950">
              جلساتِ تشخیصیِ {selected ? (selected.full_name || selected.username) : '…'}
            </h2>
            <span className="chip bg-slate-100 text-slate-500 ring-1 ring-slate-200">{toFarsiNumber(sessions.length)} جلسه</span>
          </div>

          {loadingSessions ? (
            <LoadingSpinner label="در حال دریافت گزارش‌ها…" />
          ) : sessions.length === 0 ? (
            <div className="py-10 text-center">
              <Inbox className="mx-auto h-10 w-10 text-slate-300" />
              <p className="mt-2 text-[13px] text-slate-500">هنوز جلسه‌ای برای این دانش‌آموز ثبت نشده است.</p>
            </div>
          ) : (
            <ul className="mt-3 divide-y divide-brand-50">
              {sessions.map((s) => (
                <li key={s.session_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-[13px] font-black text-brand-950">
                      {s.concept_name ?? 'مفهوم نامشخص'}
                    </p>
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span className="chip bg-indigo-50 text-indigo-800 ring-1 ring-indigo-100">{TRIGGER_LABEL[s.trigger_type] ?? s.trigger_type}</span>
                      <Badge status={s.status} />
                      <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" />{s.started_at ? new Date(s.started_at).toLocaleDateString('fa-IR') : '—'}</span>
                      <span>{s.questions_answered} پاسخ</span>
                    </p>
                  </div>
                  <button
                    onClick={() => navigate(`/teacher/report/${selected.id}/${s.session_id}`)}
                    className="flex items-center gap-1.5 rounded-2xl border border-brand-200 bg-white px-4 py-2 text-[12px] font-black text-brand-800 transition hover:border-brand-300 hover:bg-brand-50"
                  >
                    <FileText className="h-4 w-4" />
                    مشاهدهٔ گزارش
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* ── صف تصویب سؤالات هوش مصنوعی ── */}
          {pendingQuestions.length > 0 && (
            <div className="mt-5 rounded-3xl border border-amber-200/70 bg-amber-50/50 p-4">
              <h3 className="flex items-center justify-between text-[13px] font-black text-amber-900">
                سؤالات تولیدیِ AI در انتظار تصویب تو
                <span className="chip bg-amber-100 text-amber-900 ring-1 ring-amber-300">{toFarsiNumber(pendingQuestions.length)} مورد</span>
              </h3>
              <ul className="mt-2 space-y-2">
                {pendingQuestions.map((q) => (
                  <li key={q.id} className="rounded-2xl border border-amber-200/60 bg-white/80 p-3">
                    <p className="line-clamp-2 text-[12px] leading-6 text-brand-950">{q.text}</p>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="text-[10px] font-medium text-slate-400">{q.question_type} · {q.difficulty} · {q.ai_model_used ?? 'ai'}</span>
                      <span className="flex gap-1.5">
                        <button onClick={() => moderation(q.id, 'approve')} disabled={busyId === q.id} title="تصویب" aria-label="تصویب سؤال" className="rounded-xl bg-emerald-600 p-2 text-white transition hover:bg-emerald-700 disabled:opacity-50">
                          <ThumbsUp className="h-4 w-4" />
                        </button>
                        <button onClick={() => moderation(q.id, 'reject')} disabled={busyId === q.id} title="رد کردن" aria-label="رد کردن سؤال" className="rounded-xl border border-orange-200 bg-orange-50 p-2 text-orange-700 transition hover:bg-orange-100 disabled:opacity-50">
                          <ThumbsDown className="h-4 w-4" />
                        </button>
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
