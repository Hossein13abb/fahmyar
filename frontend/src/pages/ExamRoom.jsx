import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Loader2,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Home,
  ListChecks,
  RefreshCw,
  FileText,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'

const answersKey = (id) => `fahmyar_exam_${id}`

// فقط تگ‌های پایه مجازند: svg/rect/circle/line/polyline/text — ساختار کانونیکال اجباری است
const _ALLOWED_SVG_TAGS = new Set(['svg', 'rect', 'circle', 'line', 'polyline', 'text'])
const _CANONICAL_SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">'
const sanitizeSvg = (raw) => {
  let s = String(raw || '').trim()
  if (!s) return ''
  // فنس‌های مارک‌داون را از دور SVG بردار
  s = s.replace(/^```(?:[a-zA-Z]*)\s*/g, '').replace(/\s*```\s*$/gm, '')
  const start = s.indexOf('<svg')
  const end = s.lastIndexOf('</svg>')
  if (start === -1 || end === -1 || end < start) return '' // SVG ناتمام/خراب — رندر نمی‌شود
  s = s.slice(start, end + '</svg>'.length)
  // حذف اسکریپت/آبجکت خارجی/هندلرهای رویداد
  s = s.replace(/<script[\s\S]*?<\/script>/gi, '')
  s = s.replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, '')
  if (/\son[a-zA-Z]+\s*=/.test(s)) return ''
  if (/javascript:/i.test(s)) return ''
  // فقط تگ‌های مجاز — هر تگ دیگر (path, g, ellipse, image, ...) کل SVG را نامعتبر می‌کند
  const tagRe = /<\/?([A-Za-z][A-Za-z0-9-]*)/g
  let m
  while ((m = tagRe.exec(s))) {
    if (!_ALLOWED_SVG_TAGS.has(m[1].toLowerCase())) return ''
  }
  // تگ بازشونده را با ساختار کانونیکال جایگزین کن
  s = s.replace(/<svg[^>]*>/i, _CANONICAL_SVG_OPEN)
  return s
}

// ── رندر مارک‌داونِ حداقلی: جدول‌های استاندارد (با خط جداکنندهٔ ≥۳ خط تیره) + متن ساده ──
const _MD_TABLE_SEP = /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/
const _isTableRow = (line) => line.trim().startsWith('|') && line.trim().includes('|', 1)
const _splitRow = (line) =>
  line.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())

const renderQuestionText = (text) => {
  const src = String(text || '')
  const lines = src.split('\n')
  const blocks = []
  let i = 0
  let buf = []
  const flushBuf = () => {
    if (buf.length) {
      blocks.push({ type: 'text', content: buf.join('\n') })
      buf = []
    }
  }
  while (i < lines.length) {
    const line = lines[i]
    if (
      _isTableRow(line) &&
      i + 1 < lines.length &&
      _MD_TABLE_SEP.test(lines[i + 1].trim())
    ) {
      flushBuf()
      const header = _splitRow(line)
      const rows = []
      i += 2
      while (i < lines.length && _isTableRow(lines[i])) {
        const cells = _splitRow(lines[i])
        if (cells.length === header.length) rows.push(cells)
        i += 1
      }
      blocks.push({ type: 'table', header, rows })
      continue
    }
    buf.push(line)
    i += 1
  }
  flushBuf()
  return blocks.map((b, bi) =>
    b.type === 'text' ? (
      <p key={bi} className="whitespace-pre-line">{b.content}</p>
    ) : (
      <div key={bi} className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-[13px] leading-7">
          <thead>
            <tr>
              {b.header.map((h, j) => (
                <th key={j} className="border border-brand-200 bg-brand-50 px-3 py-1.5 text-right font-black text-brand-900">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {b.rows.map((row, ri) => (
              <tr key={ri} className={ri % 2 ? 'bg-slate-50/60' : 'bg-white'}>
                {row.map((cell, ci) => (
                  <td key={ci} className="border border-brand-100 px-3 py-1.5 align-top text-brand-950">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  )
}

export default function ExamRoom() {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [questions, setQuestions] = useState(null)
  const [concept, setConcept] = useState('آزمون جامع تشخیصی')
  const [answers, setAnswers] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(answersKey(sessionId)) || '{}')
    } catch {
      return {}
    }
  })
  const [index, setIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [errorStatus, setErrorStatus] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const textareaRef = useRef(null)

  const fetchExam = useCallback(async () => {
    setLoading(true)
    setError('')
    setErrorStatus(null)
    try {
      const { data } = await client.get(`/api/assess/session/${sessionId}`)
      const list = Array.isArray(data?.questions) ? data.questions : []
      if (list.length === 0) {
        setQuestions([])
        setError('هیچ سؤالی برای این جلسه یافت نشد. لطفاً دوباره تلاش کنید یا با معلم هماهنگ شوید.')
        return
      }
      setQuestions(list)
      setConcept(data?.concept_name ?? 'آزمون جامع تشخیصی')
      setIndex((current) => Math.min(Math.max(0, current), list.length - 1))
    } catch (err) {
      setQuestions([])
      setError(friendlyError(err) || 'دریافت اطلاعات آزمون با خطا مواجه شد.')
      setErrorStatus(err?.response?.status ?? null)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  // در بدو ورود، اطلاعات جلسه و سوالات از بک‌اند دریافت می‌شود
  useEffect(() => {
    fetchExam()
  }, [fetchExam])

  // اگر آرایهٔ سوالات تغییر کند، گام فعلی خارج از بازه نشود
  useEffect(() => {
    if (questions && index > questions.length - 1) setIndex(0)
  }, [questions, index])

  const setAnswer = (qid, value) => {
    setAnswers((prev) => {
      const next = { ...prev, [qid]: value }
      try {
        localStorage.setItem(answersKey(sessionId), JSON.stringify(next))
      } catch {
        /* ذخیره‌سازی محلی غیرفعال است — آزمون همچنان ادامه دارد */
      }
      return next
    })
  }

  const total = questions?.length ?? 0
  const current = total > 0 ? questions[index] : null
  const currentAnswer = current ? answers[current.id] ?? '' : ''
  const answeredCount = useMemo(
    () => (questions ?? []).filter((q) => String(answers[q.id] ?? '').trim().length > 0).length,
    [questions, answers],
  )
  const unanswered = total - answeredCount
  const isLast = total > 0 && index === total - 1

  useEffect(() => {
    textareaRef.current?.focus({ preventScroll: true })
  }, [index, current?.id])

  const submitTest = async () => {
    setConfirming(false)
    setSubmitting(true)
    setError('')
    try {
      const payload = (questions ?? []).map((q) => ({
        question_id: q.id,
        response_text: String(answers[q.id] ?? '').trim(),
      }))
      await client.post(`/api/assess/${sessionId}/submit-test`, { answers: payload })
      localStorage.removeItem(answersKey(sessionId))
      navigate(`/report/${sessionId}`, { replace: true })
    } catch (err) {
      setError(friendlyError(err))
      setSubmitting(false)
    }
  }

  if (loading) {
    return <LoadingSpinner label="در حال آماده‌سازی دفترچهٔ آزمون…" className="min-h-[22rem]" />
  }

  if (error || !current) {
    const completed = errorStatus === 422
    return (
      <div className="card mx-auto max-w-lg p-8 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-amber-500" />
        <h1 className="mt-3 text-lg font-black text-brand-950">آزمون قابل نمایش نیست</h1>
        <p className="mt-2 font-bold leading-7 text-amber-900">
          {error || 'اطلاعات این آزمون کامل نیست.'}
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <button
            onClick={fetchExam}
            className="inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-5 py-2.5 font-black text-white hover:bg-brand-800"
          >
            <RefreshCw className="h-4 w-4" /> تلاش مجدد
          </button>
          {completed && (
            <button
              onClick={() => navigate(`/report/${sessionId}`)}
              className="inline-flex items-center gap-2 rounded-2xl bg-emerald-700 px-5 py-2.5 font-black text-white hover:bg-emerald-800"
            >
              <FileText className="h-4 w-4" /> مشاهدهٔ گزارش
            </button>
          )}
          <button
            onClick={() => navigate('/dashboard')}
            className="inline-flex items-center gap-2 rounded-2xl border border-brand-200 px-5 py-2.5 font-bold text-brand-800 hover:bg-brand-50"
          >
            <Home className="h-4 w-4" /> بازگشت به داشبورد
          </button>
        </div>
      </div>
    )
  }

  if (submitting) {
    return (
      <div className="card mx-auto flex max-w-lg flex-col items-center p-10 text-center">
        <Loader2 className="h-12 w-12 animate-spin text-brand-600" />
        <h1 className="mt-5 text-lg font-black text-brand-950">در حال تحلیل یکپارچهٔ آزمون…</h1>
        <p className="mt-2 max-w-sm text-[13px] leading-7 text-slate-500">
          همهٔ پاسخ‌هایت یک‌جا و با هم بررسی می‌شوند تا الگوهای بدفهمی و ریشه‌های خطا روشن شوند.
          این کار چند لحظه طول می‌کشد — لطفاً صفحه را نبند.
        </p>
      </div>
    )
  }

  const progress = total ? Math.round((answeredCount / total) * 100) : 0

  return (
    <div className="animate-fade-up mx-auto max-w-4xl space-y-4">
      {/* ── نوار بالای آزمون ── */}
      <div className="card flex flex-wrap items-center justify-between gap-3 p-4 sm:p-5">
        <div className="min-w-0">
          <p className="text-[11px] font-bold text-brand-600">آزمون جامع تشخیصی</p>
          <h1 className="truncate text-lg font-black text-brand-950">{concept}</h1>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="rounded-2xl border border-brand-100 bg-brand-50 px-4 py-2 text-center">
            <p className="text-[10px] font-bold text-brand-700">پیشرفت</p>
            <p className="text-[15px] font-black tabular-nums text-brand-900">{answeredCount} از {total}</p>
          </div>
          <div
            className="h-11 w-11 shrink-0 rounded-full text-center text-[10px] font-black leading-[2.75rem] text-white"
            style={{ background: `conic-gradient(#0f766e ${progress * 3.6}deg, #e2e8f0 0deg)` }}
            aria-label={`${progress}% تکمیل شده`}
          >
            <span className="tabular-nums">{progress}%</span>
          </div>
        </div>
      </div>

      {/* ── نوار گام‌ها (Stepper) ── */}
      <nav aria-label="گام‌های آزمون" className="flex flex-wrap items-center justify-center gap-2 rounded-3xl border border-brand-100/70 bg-white/70 px-4 py-3">
        {(questions ?? []).map((q, i) => {
          const done = String(answers[q.id] ?? '').trim().length > 0
          const currentStep = i === index
          return (
            <button
              key={q.id}
              onClick={() => setIndex(i)}
              aria-current={currentStep ? 'step' : undefined}
              aria-label={`سؤال ${i + 1}${done ? ' — پاسخ داده شده' : ''}`}
              className={[
                'flex h-10 w-10 items-center justify-center rounded-xl text-[12px] font-black tabular-nums transition',
                currentStep
                  ? 'bg-brand-700 text-amber-200 ring-2 ring-brand-400 shadow-lift scale-110'
                  : done
                    ? 'bg-brand-100 text-brand-800 ring-1 ring-brand-300'
                    : 'bg-slate-100 text-slate-400 ring-1 ring-slate-200 hover:bg-slate-200',
              ].join(' ')}
            >
              {i + 1}
            </button>
          )
        })}
      </nav>

      {/* ── کارت سؤال ── */}
      <div className="card border-brand-100/80 p-6 sm:p-8">
        <div className="flex items-center justify-between gap-3 border-b border-brand-100/70 pb-4">
          <p className="text-[13px] font-black text-brand-700">سؤال {index + 1} از {total}</p>
          <span className="inline-flex items-center gap-2 text-[10px] font-bold text-slate-400">
            آزمون جامع تشخیصی
          </span>
        </div>

        <div className="mt-5 text-[16px] font-bold leading-9 text-brand-950">
          {renderQuestionText(current.text)}
        </div>

        {current.diagram_svg && (
          <figure className="mt-5 overflow-hidden rounded-2xl border border-teal-200/70 bg-white p-4 shadow-inner">
            <div
              className="mx-auto max-w-md"
              dangerouslySetInnerHTML={{ __html: sanitizeSvg(current.diagram_svg) }}
            />
            <figcaption className="mt-2 text-center text-[10px] font-bold text-teal-800">
              نمودار/شکلِ صورت سؤال — با دقت بررسی کنید.
            </figcaption>
          </figure>
        )}

        <label htmlFor="answer" className="label mt-6">پاسخ شما</label>
        <textarea
          id="answer"
          ref={textareaRef}
          rows={5}
          className="input resize-y leading-8"
          placeholder="با دلیل بنویسید؛ «چرا» و «چطور» مهم‌تر از جواب نهایی است…"
          value={currentAnswer}
          onChange={(e) => setAnswer(current.id, e.target.value)}
        />
        <p className="mt-1.5 text-[10px] text-slate-400">
          پاسخ‌ها فقط پس از ثبت نهایی تحلیل می‌شوند — حین آزمون هیچ بازخوردی داده نمی‌شود.
        </p>
      </div>

      {error && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium leading-7 text-amber-900" role="alert">
          {error}
        </div>
      )}

      {/* ── دکمه‌های ناوبری ── */}
      <div className="flex items-center justify-between gap-3">
        <button
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          disabled={index === 0}
          className="inline-flex items-center gap-2 rounded-2xl border border-brand-200 bg-white px-4 py-3 text-[13px] font-bold text-brand-800 transition hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" /> قبلی
        </button>

        {!isLast ? (
          <button
            onClick={() => setIndex((i) => Math.min(total - 1, i + 1))}
            className="inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-6 py-3 text-[13px] font-black text-white shadow-card transition hover:bg-brand-800"
          >
            سؤال بعدی <ChevronLeft className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-2 rounded-2xl bg-emerald-700 px-6 py-3 text-[13px] font-black text-white shadow-card transition hover:bg-emerald-800"
          >
            <ClipboardCheck className="h-5 w-5" />
            ثبت نهایی آزمون و تولید گزارش تشخیصی
          </button>
        )}
      </div>

      {/* ── تأییدیهٔ ثبت نهایی ── */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="card w-full max-w-md border-amber-200 p-6 text-center shadow-lift">
            <AlertTriangle className="mx-auto h-12 w-12 text-amber-500" />
            <h2 className="mt-3 text-lg font-black text-brand-950">ثبت نهایی آزمون</h2>
            {unanswered > 0 ? (
              <p className="mt-2 text-[13px] leading-7 text-amber-900">
                <strong>{unanswered} سؤال بی‌پاسخ</strong> باقی مانده است. بعد از ثبت نهایی، امکان اصلاح پاسخ‌ها نیست.
              </p>
            ) : (
              <p className="mt-2 text-[13px] leading-7 text-slate-600">
                همهٔ {total} پاسخ ثبت می‌شود و تحلیل یکپارچه انجام می‌شود. بعد از ثبت نهایی، امکان اصلاح نیست.
              </p>
            )}
            <div className="mt-5 flex justify-center gap-3">
              <button
                onClick={() => setConfirming(false)}
                className="rounded-2xl border border-brand-200 px-5 py-2.5 font-bold text-brand-800 hover:bg-brand-50"
              >
                برگردم و مرور کنم
              </button>
              <button
                onClick={submitTest}
                className="inline-flex items-center gap-2 rounded-2xl bg-emerald-700 px-5 py-2.5 font-black text-white hover:bg-emerald-800"
              >
                <ClipboardCheck className="h-4 w-4" /> ثبت و تحلیل
              </button>
            </div>
          </div>
        </div>
      )}

      <p className="flex items-center justify-center gap-2 pb-2 text-center text-[11px] text-slate-400">
        <ListChecks className="h-4 w-4" />
        پاسخ‌هایت فقط روی همین دستگاه تا زمان ثبت نهایی ذخیره می‌شوند — اگر صفحه را ببندی، ادامه از همین‌جا ممکن است.
      </p>
    </div>
  )
}
