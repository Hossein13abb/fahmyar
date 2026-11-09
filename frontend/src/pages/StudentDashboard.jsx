import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles,
  BookOpen,
  Microscope,
  Sigma,
  Atom,
  ChevronDown,
  Route,
  GitBranch,
  ArrowLeft,
  Loader2,
  Info,
  Waypoints,
  HeartHandshake,
  SearchCheck,
  Map,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'

const SUBJECTS = [
  { value: 'math', label: 'ریاضی', Icon: Sigma },
  { value: 'physics', label: 'فیزیک', Icon: Atom },
  { value: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const GRADES = [10, 11, 12]

const HOW_STEPS = [
  { Icon: SearchCheck, title: '۱. دفترچهٔ ۹ سؤالی', text: 'از مفهومی تا نموداری — کل ابعاد فهم در یک آزمون.' },
  { Icon: Waypoints, title: '۲. بدون بازخورد لحظه‌ای', text: 'حین آزمون چیزی فاش نمی‌شود؛ پاسخ‌ها جمع می‌شوند تا تحلیل یکپارچه انجام شود.' },
  { Icon: Map, title: '۳. گزارش تشخیصی', text: 'ابعاد فهم، ریشهٔ بدفهمی‌ها و راهکارهای کیفی — بدون نمره و رتبه.' },
]

export default function StudentDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [tab, setTab] = useState('topic') // topic | wrong_answer

  // مسیر A
  const [subject, setSubject] = useState('physics')
  const [grade, setGrade] = useState(user?.grade ?? 11)
  const [concepts, setConcepts] = useState([])
  const [conceptId, setConceptId] = useState('')
  const [loadingConcepts, setLoadingConcepts] = useState(false)

  // مسیر B
  const [problemText, setProblemText] = useState('')
  const [wrongAnswer, setWrongAnswer] = useState('')
  const [wrongConceptId, setWrongConceptId] = useState('')
  const [allConcepts, setAllConcepts] = useState([])

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // بارگذاری مفاهیم مسیر A
  useEffect(() => {
    let alive = true
    setLoadingConcepts(true)
    setError('')
    client
      .get(`/api/concepts/${subject}/${grade}`)
      .then(({ data }) => {
        if (!alive) return
        setConcepts(data.concepts ?? [])
        setConceptId((prev) => (data.concepts?.some((c) => String(c.id) === String(prev)) ? prev : ''))
      })
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoadingConcepts(false))
    return () => {
      alive = false
    }
  }, [subject, grade])

  // بارگذاری همهٔ مفاهیم برای مسیر B (یک بار)
  useEffect(() => {
    client
      .get('/api/concepts')
      .then(({ data }) => setAllConcepts(data.concepts ?? []))
      .catch(() => setAllConcepts([]))
  }, [])

  const selectedConcept = useMemo(
    () => concepts.find((c) => String(c.id) === String(conceptId)) ?? null,
    [concepts, conceptId],
  )

  const startTopicSession = async () => {
    if (!conceptId) return setError('اول یک مفهوم را انتخاب کن.')
    setSubmitting(true)
    setError('')
    try {
      const { data } = await client.post('/api/assess/start-test', {
        trigger_type: 'topic_selection',
        concept_id: Number(conceptId),
        wrong_answer: null,
      })
      navigate(`/exam/${data.session.id}`, {
        state: { startData: data, conceptName: selectedConcept?.name },
      })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const startWrongAnswerSession = async () => {
    if (!wrongConceptId) {
      return setError('برای شروع آزمون جامع، مفهوم مرتبط را انتخاب کن (دفترچهٔ سؤال‌ها از همین مفهوم ساخته می‌شود).')
    }
    if (problemText.trim().length < 10 && wrongAnswer.trim().length < 5) {
      return setError('حداقل متن صورت مسئله یا پاسخ خودت را بنویس.')
    }
    setSubmitting(true)
    setError('')
    try {
      const { data } = await client.post('/api/assess/start-test', {
        trigger_type: 'wrong_answer',
        concept_id: Number(wrongConceptId),
        wrong_answer: {
          problem_text: problemText.trim(),
          student_answer: wrongAnswer.trim(),
          concept_id: wrongConceptId ? Number(wrongConceptId) : null,
        },
      })
      navigate(`/exam/${data.session.id}`, {
        state: {
          startData: data,
          conceptName: allConcepts.find((c) => String(c.id) === String(wrongConceptId))?.name,
        },
      })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const today = new Date().toLocaleDateString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── سربرگ خوش‌آمد ── */}
      <section className="relative overflow-hidden rounded-4xl border border-brand-100 bg-gradient-to-l from-brand-800 to-brand-700 px-6 py-6 text-brand-50 shadow-lift sm:px-8">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(700px 260px at 88% -20%, rgba(253,233,200,0.35), transparent 60%)' }}
        />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 text-[12px] font-bold text-brand-200">
              <Sparkles className="h-4 w-4 text-amber-200" /> {today}
            </p>
            <h1 className="mt-2 text-2xl font-black leading-snug sm:text-[28px]">
              سلام {user?.full_name || user?.username} 👋<br className="hidden sm:block" />
              آماده‌ای برای آزمون جامع تشخیصی؟
            </h1>
            <p className="mt-2 max-w-lg text-[13px] leading-7 text-brand-100/90">
              یک دفترچهٔ ۹ سؤالی در انتظارت است — بدون نمره و بدون چت.
              در پایان، گزارش تشخیصیِ کامل با ریشه‌یابی بدفهمی‌هایت می‌سازیم.
            </p>
          </div>
          <div className="hidden shrink-0 flex-col items-center gap-2 rounded-3xl bg-white/10 px-6 py-4 text-center ring-1 ring-white/15 backdrop-blur md:flex">
            <HeartHandshake className="h-9 w-9 text-amber-200" />
            <p className="text-[11px] font-bold leading-5 text-brand-100">
              بدون نمره · بدون رتبه
              <br /> فقط شواهد کیفی
            </p>
          </div>
        </div>
      </section>

      {/* ── تب‌های مسیر شروع ── */}
      <div className="grid gap-3 sm:grid-cols-2" role="tablist" aria-label="دو مسیر شروع آزمون جامع">
        {[
          { key: 'topic', Icon: Route, title: 'مسیر الف — آزمون جامع یک موضوع', sub: 'یک مفهوم درسی را انتخاب کن؛ دفترچهٔ ۹ سؤالی از همان مفهوم بساز' },
          { key: 'wrong_answer', Icon: GitBranch, title: 'مسیر ب — شروع از پاسخ اشتباه', sub: 'جواب اشتباهت را بفرست؛ دفترچهٔ ۹ سؤالی طوری ساخته می‌شود که ریشهٔ خطا را ردیابی کند' },
        ].map(({ key, Icon, title, sub }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key)
              setError('')
            }}
            className={`group flex items-start gap-4 rounded-3xl border p-5 text-right transition ${
              tab === key
                ? 'border-brand-400 bg-white shadow-lift ring-2 ring-brand-200'
                : 'border-brand-100 bg-white/60 hover:border-brand-200 hover:bg-white'
            }`}
          >
            <span className={`rounded-2xl p-3 transition ${tab === key ? 'bg-brand-700 text-amber-200' : 'bg-brand-50 text-brand-700 group-hover:bg-brand-100'}`}>
              <Icon className="h-6 w-6" />
            </span>
            <span>
              <span className="block text-[15px] font-black text-brand-900">{title}</span>
              <span className="mt-1 block text-[12px] leading-6 text-slate-500">{sub}</span>
            </span>
          </button>
        ))}
      </div>

      {/* ── پنل هر مسیر ── */}
      <section className="card p-6 sm:p-7">
        {tab === 'topic' ? (
          <div className="space-y-5">
            <div className="flex flex-wrap items-end gap-4">
              <div className="min-w-[10rem] flex-1">
                <label className="label" htmlFor="subject">درس</label>
                <div className="relative">
                  <select id="subject" className="input appearance-none pl-10" value={subject} onChange={(e) => setSubject(e.target.value)}>
                    {SUBJECTS.map(({ value, label }) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>
              </div>
              <div className="min-w-[8rem] flex-1">
                <label className="label" htmlFor="grade">پایه</label>
                <div className="relative">
                  <select id="grade" className="input appearance-none pl-10" value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
                    {GRADES.map((g) => (
                      <option key={g} value={g}>پایهٔ {g}</option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>
              </div>
            </div>

            <div>
              <label className="label" htmlFor="concept">مفهوم مورد نظر</label>
              {loadingConcepts ? (
                <LoadingSpinner label="در حال دریافت مفهوم‌ها…" className="py-6" />
              ) : (
                <div className="relative">
                  <select id="concept" className="input appearance-none pl-10" value={conceptId} onChange={(e) => setConceptId(e.target.value)}>
                    <option value="">— یک مفهوم انتخاب کن —</option>
                    {concepts.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} {c.chapter ? `(${c.chapter})` : ''}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>
              )}
              {!loadingConcepts && concepts.length === 0 && (
                <p className="mt-2 flex items-center gap-2 text-[12px] text-amber-800">
                  <Info className="h-4 w-4" /> برای این درس و پایه هنوز مفهومی در بانک نیست.
                </p>
              )}
            </div>

            {selectedConcept && (
              <div className="rounded-2xl border border-brand-100 bg-brand-50/60 p-4 text-[12px] leading-7 text-brand-900">
                <p className="font-black">{selectedConcept.name}</p>
                <p className="mt-1 text-brand-800/80">{selectedConcept.chapter}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(selectedConcept.target_behaviors ?? []).map((b) => (
                    <span key={b} className="chip bg-white text-brand-800 ring-1 ring-brand-200">{b}</span>
                  ))}
                </div>
              </div>
            )}

            <button onClick={startTopicSession} disabled={submitting || !conceptId} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand-700 py-4 text-[15px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60">
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Microscope className="h-5 w-5" />}
              شروع آزمون جامع تشخیصی
              <ArrowLeft className="h-5 w-5" />
            </button>
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <label className="label" htmlFor="problem">صورت مسئله / سؤال</label>
              <textarea id="problem" rows={3} className="input resize-y" value={problemText} onChange={(e) => setProblemText(e.target.value)} placeholder="مثلاً: دو بار الکتریکیِ مشابه در فاصلهٔ ۲ سانتی‌متری…" />
            </div>
            <div>
              <label className="label" htmlFor="wrong">پاسخِ اشتباهِ خودت (همان‌طور که نوشته‌ای)</label>
              <textarea id="wrong" rows={4} className="input resize-y" value={wrongAnswer} onChange={(e) => setWrongAnswer(e.target.value)} placeholder="مثلاً: چون فاصله نصف شد، نیرو هم نصف می‌شود…" />
              <p className="mt-1.5 text-[11px] text-slate-500">نگران نباش — هدف از دیدن این پاسخ، پیدا کردن ریشهٔ خطاست، نه نمره‌دادن.</p>
            </div>
            <div>
              <label className="label" htmlFor="wconcept">مفهوم مرتبط (الزامی — دفترچهٔ سؤالات از این مفهوم ساخته می‌شود)</label>
              <div className="relative">
                <select id="wconcept" className="input appearance-none pl-10" value={wrongConceptId} onChange={(e) => setWrongConceptId(e.target.value)}>
                  <option value="">— یک مفهوم انتخاب کن —</option>
                  {allConcepts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name} · {c.subject}</option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              </div>
            </div>
            <button onClick={startWrongAnswerSession} disabled={submitting} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-700 py-4 text-[15px] font-black text-white shadow-lift transition hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-60">
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <GitBranch className="h-5 w-5" />}
              شروع آزمون جامع تشخیصی
              <ArrowLeft className="h-5 w-5" />
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium leading-7 text-amber-900" role="alert">
            {error}
          </div>
        )}
      </section>

      {/* ── چطور کار می‌کند ── */}
      <section className="grid gap-3 sm:grid-cols-3">
        {HOW_STEPS.map(({ Icon, title, text }) => (
          <div key={title} className="rounded-3xl border border-brand-100/70 bg-white/70 p-5 text-center">
            <Icon className="mx-auto h-7 w-7 text-brand-600" strokeWidth={1.8} />
            <p className="mt-2 text-[13px] font-black text-brand-900">{title}</p>
            <p className="mt-1 text-[11px] leading-6 text-slate-500">{text}</p>
          </div>
        ))}
      </section>

      <p className="flex items-center justify-center gap-2 text-center text-[11px] text-slate-400">
        <BookOpen className="h-4 w-4" /> هر جلسه حداکثر ۳۰ دقیقه طول می‌کشد و می‌توانی هر وقت خواستی مکث کنی.
      </p>
    </div>
  )
}
