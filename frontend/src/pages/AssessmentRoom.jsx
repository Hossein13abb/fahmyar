import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, Link } from 'react-router-dom'
import {
  Sparkles,
  Send,
  Loader2,
  FlaskConical,
  Pause,
  Play,
  FileText,
  AlertTriangle,
  Home,
  CheckCircle2,
  MessageCircleQuestion,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'

// ذخیرهٔ بازیابی‌شونده برای رفرش تصادفی صفحه
const persistKey = (id) => `fahmyar_session_${id}`
const loadPersisted = (id) => {
  try {
    return JSON.parse(localStorage.getItem(persistKey(id)) || 'null')
  } catch {
    return null
  }
}
const savePersisted = (id, data) => localStorage.setItem(persistKey(id), JSON.stringify(data))

export default function AssessmentRoom() {
  const { sessionId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const startData = location.state?.startData ?? null
  const conceptName = location.state?.conceptName ?? loadPersisted(sessionId)?.conceptName ?? 'جلسهٔ فهم‌سنجی'

  const [question, setQuestion] = useState(() => location.state?.startData?.next_question ?? loadPersisted(sessionId)?.question ?? null)
  const [messages, setMessages] = useState(() => {
    const q = location.state?.startData?.next_question ?? loadPersisted(sessionId)?.question
    return q ? [{ id: `q-${q.id}`, role: 'assistant', text: q.text, meta: q }] : []
  })
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [paused, setPaused] = useState(false)
  const [pausing, setPausing] = useState(false)
  const [done, setDone] = useState(false)
  const [answeredCount, setAnsweredCount] = useState(0)
  const [error, setError] = useState('')
  const [finishedMessage, setFinishedMessage] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, submitting])

  // رفرش صفحه: سؤال فعلی بازیابی می‌شود
  useEffect(() => {
    if (question) savePersisted(sessionId, { question, conceptName })
  }, [question, sessionId, conceptName])

  const canSubmit = answer.trim().length > 0 && !submitting && !paused && question && !done

  const submitAnswer = async () => {
    if (!canSubmit) return
    const text = answer.trim()
    setSubmitting(true)
    setError('')
    // پیام دانش‌آموز را همان لحظه در گفتگو بگذار
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: 'student', text }])
    setAnswer('')
    try {
      const { data } = await client.post(`/api/assess/${sessionId}/answer`, {
        question_id: question.id,
        response_text: text,
      })
      setAnsweredCount((n) => n + 1)
      // کارت شواهد پس از پیام دانش‌آموز
      setMessages((m) => [
        ...m,
        {
          id: `ev-${Date.now()}`,
          role: 'evidence',
          evidence: data.evidence ?? [],
          propositionStatuses: data.proposition_statuses ?? {},
          conflicts: data.conflicts ?? [],
        },
      ])

      const nextQ = data.next_question ?? null
      if (data.done || !nextQ) {
        setDone(true)
        setQuestion(null)
        setFinishedMessage(data.message ?? 'ارزیابی کامل شد.')
        localStorage.removeItem(persistKey(sessionId))
      } else {
        setQuestion(nextQ)
        setMessages((m) => [...m, { id: `q-${nextQ.id}-${Date.now()}`, role: 'assistant', text: nextQ.text, meta: nextQ }])
      }
    } catch (err) {
      setError(friendlyError(err))
      // پیام دانش‌آموز را نگه داریم تا دوباره تلاش کند (حبابِ خوش‌بینانه را برمی‌داریم)
      setAnswer(text)
      setMessages((m) => {
        const rev = [...m].reverse().findIndex((msg) => msg.role === 'student' && msg.text === text)
        if (rev === -1) return m
        const idx = m.length - 1 - rev
        return m.filter((_, i) => i !== idx)
      })
    } finally {
      setSubmitting(false)
    }
  }

  const togglePause = async () => {
    setPausing(true)
    setError('')
    try {
      if (paused) {
        await client.post(`/api/assess/${sessionId}/resume`)
        setPaused(false)
      } else {
        await client.post(`/api/assess/${sessionId}/pause`)
        setPaused(true)
      }
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setPausing(false)
    }
  }

  const goToReport = () => navigate(`/report/${sessionId}`)

  // صفحه‌ای که بدون state/refresh مستقیم باز شود
  if (!startData && !question && messages.length === 0 && !done) {
    return (
      <div className="card mx-auto max-w-lg p-8 text-center">
        <MessageCircleQuestion className="mx-auto h-12 w-12 text-brand-400" />
        <h1 className="mt-3 text-xl font-black text-brand-900">جلسه‌ای در این مرورگر باز نیست</h1>
        <p className="mt-2 text-[13px] leading-7 text-slate-500">
          برای ادامهٔ فهم‌سنجی به داشبورد برگرد و یک جلسهٔ جدید شروع کن؛ یا اگر جلسهٔ قبلی ناتمام مانده، گزارش همان جلسه را ببین.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <Link to="/dashboard" className="rounded-2xl bg-brand-700 px-5 py-3 text-sm font-black text-white hover:bg-brand-800">
            بازگشت به داشبورد
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      {/* ── نوار بالایی جلسه ── */}
      <div className="card flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <span className="rounded-2xl bg-brand-700 p-2 text-amber-200">
            <Sparkles className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-[13px] font-black text-brand-900">{conceptName}</span>
            <span className="block text-[11px] text-slate-500">
              حداکثر ۳۰ دقیقه — بدون عجله؛ با خیال راحت فکر کن
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={togglePause}
            disabled={pausing}
            className="flex items-center gap-1.5 rounded-2xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-[12px] font-bold text-indigo-800 transition hover:bg-indigo-100 disabled:opacity-60"
          >
            {pausing ? <Loader2 className="h-4 w-4 animate-spin" /> : paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
            {paused ? 'ادامهٔ جلسه' : 'مکث'}
          </button>
          <button
            onClick={goToReport}
            className="flex items-center gap-1.5 rounded-2xl border border-brand-200 bg-brand-50 px-3 py-2 text-[12px] font-bold text-brand-800 transition hover:bg-brand-100"
          >
            <FileText className="h-4 w-4" />
            توقف و مشاهدهٔ گزارش
          </button>
        </div>
      </div>

      {/* ── گفتگوی فهم‌سنجی ── */}
      <div className="card flex min-h-[24rem] flex-col gap-4 p-5 sm:p-6">
        {messages.length === 0 && <LoadingSpinner label="در حال آماده‌سازی اولین سؤال…" />}

        {messages.map((msg) => {
          if (msg.role === 'assistant') {
            return (
              <div key={msg.id} className="flex items-start gap-3 animate-fade-up">
                <span className="mt-1 rounded-2xl bg-brand-100 p-2 text-brand-800">
                  <Sparkles className="h-5 w-5" />
                </span>
                <div className="max-w-[85%] rounded-3xl rounded-tr-md border border-brand-100 bg-white px-5 py-4 shadow-card">
                  <p className="text-[11px] font-black text-brand-500">سؤال تشخیصی</p>
                  <p className="mt-1 whitespace-pre-line text-[15px] leading-8 text-brand-950">{msg.text}</p>
                </div>
              </div>
            )
          }
          if (msg.role === 'student') {
            return (
              <div key={msg.id} className="flex items-start justify-end gap-3 animate-fade-up">
                <div className="max-w-[85%] rounded-3xl rounded-tl-md bg-brand-700 px-5 py-4 text-brand-50 shadow-card">
                  <p className="text-[11px] font-black text-brand-200">پاسخ تو</p>
                  <p className="mt-1 whitespace-pre-line text-[14px] leading-8">{msg.text}</p>
                </div>
              </div>
            )
          }
          // کارت شواهد
          return (
            <div key={msg.id} className="mr-12 rounded-3xl border border-teal-100 bg-teal-50/70 p-4 animate-fade-up">
              <p className="flex items-center gap-2 text-[11px] font-black text-teal-800">
                <FlaskConical className="h-4 w-4" />
                تحلیل شواهد — چه چیزهایی روشن شد
              </p>
              <ul className="mt-2 space-y-2">
                {msg.evidence.map((ev, i) => (
                  <li key={i} className="rounded-2xl border border-teal-100/70 bg-white/80 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge status={ev.status} />
                    </div>
                    <p className="mt-1.5 text-[12px] leading-6 text-slate-600">{ev.reasoning}</p>
                  </li>
                ))}
              </ul>
              {msg.conflicts?.length > 0 && (
                <p className="mt-2 flex items-start gap-2 text-[11px] leading-6 text-amber-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  در یک گزاره شواهد متناقض دیدم — یعنی هنوز مطمئن نیستم؛ سؤال بعدی این را روشن می‌کند.
                </p>
              )}
            </div>
          )
        })}

        {submitting && (
          <div className="flex items-center gap-3 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-[13px] font-bold text-brand-800">
            <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
            هوش مصنوعی در حال بررسی استدلال توست…
            <span className="inline-flex gap-1" aria-hidden>
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-400 [animation-delay:-0.2s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-400 [animation-delay:-0.1s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-400" />
            </span>
          </div>
        )}

        {/* پایان جلسه */}
        {done && (
          <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-5 text-center animate-fade-up">
            <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600" />
            <p className="mt-2 text-lg font-black text-emerald-900">این جلسه کامل شد 🌱</p>
            <p className="mt-1 text-[13px] text-emerald-800">{finishedMessage || 'شواهد کافی جمع شد.'}</p>
            <button onClick={goToReport} className="mt-4 inline-flex items-center gap-2 rounded-2xl bg-emerald-600 px-6 py-3.5 text-[15px] font-black text-white shadow-lift transition hover:bg-emerald-700">
              <FileText className="h-5 w-5" />
              مشاهدهٔ گزارش فهم
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── ورودی پاسخ ── */}
      {!done && (
        <div className={`card p-4 transition ${paused ? 'pointer-events-none opacity-60' : ''}`}>
          <label htmlFor="answer" className="label">پاسخت را با «دلیل» بنویس — یعنی بگو چرا</label>
          <textarea
            id="answer"
            rows={4}
            className="input resize-y text-[15px]"
            placeholder="مثلاً: چون … بنابراین … زیرا …"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submitAnswer()
            }}
            disabled={submitting || paused}
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] text-slate-400">پاسخِ درست بدون استدلال = شواهد ضعیف · واژهٔ درست بدون دلیل = هیچ شواهدی نیست</p>
            <button onClick={submitAnswer} disabled={!canSubmit} className="flex items-center gap-2 rounded-2xl bg-brand-700 px-6 py-3 text-[14px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50">
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
              ثبت پاسخ
            </button>
          </div>
          {error && <p className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-900">{error}</p>}
        </div>
      )}

      {/* ── لایهٔ مکث ── */}
      {paused && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-brand-950/45 p-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="جلسه مکث شده">
          <div className="card max-w-md p-8 text-center shadow-lift animate-fade-up">
            <Pause className="mx-auto h-12 w-12 text-indigo-500" />
            <h2 className="mt-3 text-2xl font-black text-brand-950">جلسه مکث شد</h2>
            <p className="mt-2 text-[13px] leading-7 text-slate-500">
              زمانت فریز شده — هر وقت آماده بودی برگرد. می‌توانی حالا گزارشِ همین‌جا را ببینی یا ادامه بدهی.
            </p>
            <div className="mt-6 flex flex-col gap-2">
              <button onClick={togglePause} className="flex items-center justify-center gap-2 rounded-2xl bg-indigo-600 px-5 py-3.5 font-black text-white hover:bg-indigo-700">
                <Play className="h-5 w-5" /> ادامهٔ جلسه
              </button>
              <button onClick={goToReport} className="flex items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-3.5 font-black text-brand-800 hover:bg-brand-50">
                <FileText className="h-5 w-5" /> مشاهدهٔ گزارش همین لحظه
              </button>
              <Link to="/dashboard" className="flex items-center justify-center gap-2 rounded-2xl px-5 py-3 text-[13px] font-bold text-slate-500 hover:text-brand-800">
                <Home className="h-4 w-4" /> بازگشت به داشبورد
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
