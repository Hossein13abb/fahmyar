import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import client, { friendlyError } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import { toFarsiNumber } from '../utils/faNumbers'
import { Search, Hand, ShieldQuestion } from 'lucide-react'

/**
 * ایستگاهِ بازپرسی — «یک لحظه صبر کن! تناقض در گفتار!»
 *
 * این صفحه فقط وقتی ظاهر می‌شود که ارزیاب بین دو پاسخِ کاربر تناقض دیده و
 * مطمئن نیست «بی‌دقتی» بوده یا «کج‌فهمی». به‌جای حکمِ عجولانه، خودِ
 * دانش‌آموز را طرفِ گفت‌وگو می‌کند.
 */
const SHORTCUTS = [
  {
    id: 'slip',
    Icon: Hand,
    label: 'ای وای، بی‌دقتی کردم',
    hint: 'در تست دستم خورد و حواسم نبود.',
    prefix: 'راستش در تست بی‌دقتی کردم. ',
  },
  {
    id: 'firm',
    Icon: ShieldQuestion,
    label: 'نه، واقعاً نظرم همینه',
    hint: 'توضیح می‌دهم چرا فکر می‌کنم حرفم درست است.',
    prefix: 'نه، عمداً آن گزینه را انتخاب کردم چون ',
  },
]

export default function CognitiveClarify() {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mirror, setMirror] = useState('')
  const [topic, setTopic] = useState('')
  const [contradicting, setContradicting] = useState([])
  const [answer, setAnswer] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let alive = true
    client
      .get(`/api/assessment/${sessionId}`)
      .then(({ data }) => {
        if (!alive) return
        const report = data.report
        // اگر بازپرسی باز نیست (مثلاً کاربر رفرش کرده و کارنامه صادر شده)،
        // او را در این صفحه زندانی نکن.
        if (!report || !report.needs_clarification) {
          navigate(`/report/xray/${sessionId}`, { replace: true })
          return
        }
        setMirror(report.clarification_data?.mirror_prompt || '')
        setContradicting(report.clarification_data?.contradicting_questions || [])
        setTopic(data.topic || '')
      })
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [sessionId, navigate])

  const submit = async () => {
    if (!answer.trim()) {
      setError('کوتاه توضیح بده تا بتوانیم حکمِ نهایی را صادر کنیم.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await client.post(
        '/api/assessment/clarify',
        { session_id: Number(sessionId), clarification_answer: answer.trim() },
        { timeout: 180000 },
      )
      navigate(`/report/xray/${sessionId}`, { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <LoadingSpinner label="در حال بازیابیِ تناقض…" />

  return (
    <div className="mx-auto max-w-2xl space-y-4 animate-fade-up">
      <header className="rounded-3xl border-2 border-amber-200 bg-gradient-to-l from-amber-50 to-white p-5 shadow-soft">
        <div className="flex items-center gap-2">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-500 text-white shadow-soft">
            <Search className="h-5 w-5" strokeWidth={2.3} aria-hidden="true" />
          </span>
          <div>
            <p className="text-[11px] font-bold text-amber-700">ایستگاهِ بازپرسی · {topic}</p>
            <h1 className="text-lg font-extrabold text-slate-900">یک لحظه صبر کن! تناقض در گفتار!</h1>
          </div>
        </div>
        <p className="mt-3 text-xs leading-6 text-slate-600">
          بین پاسخ‌های تو چیزی دیدم که با هم جور نیست. نمی‌خواهم عجولانه حکم بدهم — خودت بگو
          کدام‌یک نظرِ واقعیِ توست.
        </p>
      </header>

      {contradicting.length >= 2 && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-white p-3 shadow-soft ring-1 ring-slate-200">
          <span className="text-[11px] font-bold text-slate-500">بینِ این دو پاسخ تناقض دیده شد:</span>
          {contradicting.map((qid) => (
            <span
              key={qid}
              className="rounded-lg bg-amber-100 px-2.5 py-1 text-[11px] font-extrabold text-amber-900"
            >
              سؤال {toFarsiNumber(qid)}
            </span>
          ))}
        </div>
      )}

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
        <div className="rounded-2xl bg-slate-900 p-4 text-sm leading-7 text-white">
          <p className="mb-1 text-[10px] font-bold text-slate-400">پیامِ کارآگاه:</p>
          <p className="whitespace-pre-wrap">{mirror || 'بین پاسخ‌هایت تناقضی دیده شد.'}</p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {SHORTCUTS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setAnswer(item.prefix)}
              className="flex-1 rounded-2xl border-2 border-slate-200 bg-white p-3 text-right transition hover:border-brand-400 hover:bg-brand-50"
            >
              <item.Icon className="h-5 w-5 text-slate-500" strokeWidth={2} aria-hidden="true" />
              <p className="mt-1 text-xs font-extrabold text-slate-800">{item.label}</p>
              <p className="mt-0.5 text-[10px] font-medium text-slate-500">{item.hint}</p>
            </button>
          ))}
        </div>

        <label htmlFor="clarify-answer" className="mt-4 block text-xs font-bold text-slate-700">
          توضیحِ تو
        </label>
        <textarea
          id="clarify-answer"
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          rows={5}
          placeholder="کوتاه و صادقانه بنویس…"
          className="mt-1.5 w-full resize-y rounded-2xl border-2 border-slate-200 p-4 text-sm leading-7 text-slate-800 outline-none transition focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
        />

        {error && (
          <p className="mt-2 rounded-xl bg-rose-50 p-3 text-xs font-bold text-rose-800 ring-1 ring-rose-200">
            ⚠️ {error}
          </p>
        )}

        <button
          type="button"
          onClick={submit}
          disabled={submitting || !answer.trim()}
          className="mt-4 w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-extrabold text-white shadow-soft transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? 'در حال صدورِ حکمِ نهایی…' : 'ثبت و دیدنِ کارنامه'}
        </button>
        <p className="mt-2 text-center text-[10px] font-medium text-slate-400">
          صداقت به نفعِ خودت است — این آزمون دنبالِ نمره نیست، دنبالِ شناختنِ ذهنِ توست.
        </p>
      </section>
    </div>
  )
}
