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
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import client, { friendlyError } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import MathText from '../components/MathText'
import { toFarsiNumber } from '../utils/faNumbers'

const answersKey = (id) => `fahmyar_exam_${id}`

// همان قاعدهٔ سمتِ سرور: تطبیقِ واژهٔ کامل، نه زیررشته.
const _normalizeFa = (t) =>
  String(t || '')
    .replace(/[ي]/g, 'ی')
    .replace(/[ك]/g, 'ک')
    .replace(/[\u064B-\u0652\u0670\u0640]/g, '')
    .replace(/\u200c/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

const usedForbidden = (answer, word) => {
  const w = _normalizeFa(word)
  if (!w) return false
  const escaped = w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}([^\\p{L}\\p{N}]|$)`, 'u').test(_normalizeFa(answer))
}

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
      <div key={bi} className="math-content whitespace-pre-line">
        <MathText content={b.content || ''} />
      </div>
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
                  <td key={ci} className="math-inline border border-brand-100 px-3 py-1.5 align-top text-brand-950"><MathText content={cell || ''} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  )
}

// کلیدِ جداگانه برای انتخابِ گزینه — تا با متنِ پاسخ قاطی نشود
// پنج مرحله — هر مرحله دو سؤال دارد (۱۰ سؤال در کل)
// برچسب‌های عمومی — نامِ متدولوژیِ داخلی به دانش‌آموز نشان داده نمی‌شود.
const STAGE_NAMES = [
  'سؤال مفهومی',
  'سؤال چهارگزینه‌ای',
  'پیش‌بینی رفتار پدیده',
  'بررسی استدلال علمی',
  'توضیح ساده و شهودی',
]

// شمارهٔ مرحله از روی ترتیبِ سؤال: ۱،۲→۱ … ۹،۱۰→۵
const stageOfQuestion = (q, index) => {
  const explicit = Number(q?.stage)
  if (Number.isInteger(explicit) && explicit >= 1 && explicit <= 5) return explicit
  return Math.min(5, Math.floor(index / 2) + 1)
}

const selectionsKey = (sid) => `fahmyar_selections_${sid}`

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
  const [selections, setSelections] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(selectionsKey(sessionId)) || '{}')
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
      const { data } = await client.get(`/api/assess/session/${sessionId}`, { timeout: 180000 })
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

  // انتخابِ گزینه و متنِ آزاد دو چیزِ جدایند:
  //   answers[qid]         → متنِ پاسخ (تشریحی) یا توضیحِ اختیاریِ صاحبِ MCQ
  //   selections[qid]      → اندیسِ صفرمبنای گزینهٔ انتخاب‌شده
  // قبلاً هر دو در یک رشتهٔ مشترک نگه داشته می‌شدند و مقایسهٔ متنیِ گزینه
  // باعث می‌شد توضیحِ حاوی عدد، انتخاب را عوض کند.
  const persist = (key, next) => {
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      /* ذخیره‌سازی محلی غیرفعال است — آزمون همچنان ادامه دارد */
    }
  }

  const setAnswer = (qid, value) => {
    setAnswers((prev) => {
      const next = { ...prev, [qid]: value }
      persist(answersKey(sessionId), next)
      return next
    })
  }

  const setSelection = (qid, optionIndex) => {
    setSelections((prev) => {
      const next = { ...prev }
      if (optionIndex === null || optionIndex === undefined) delete next[qid]
      else next[qid] = Number(optionIndex)
      persist(selectionsKey(sessionId), next)
      return next
    })
  }

  const total = questions?.length ?? 0
  const current = total > 0 ? questions[index] : null
  const currentAnswer = current ? answers[current.id] ?? '' : ''
  // «پاسخ داده شده» برای تستِ چهارگزینه‌ای یعنی گزینه‌ای انتخاب شده؛
  // توضیحِ اختیاری به‌تنهایی پاسخ حساب نمی‌شود.
  const isAnswered = (q) => {
    if (!q) return false
    if (Array.isArray(q.options) && q.options.length > 0) {
      return Number.isInteger(Number(selections[q.id])) && selections[q.id] !== undefined
    }
    return String(answers[q.id] ?? '').trim().length > 0
  }
  const answeredCount = useMemo(
    () => (questions ?? []).filter((q) => isAnswered(q)).length,
    [questions, answers, selections],
  )
  const unanswered = total - answeredCount
  const isLast = total > 0 && index === total - 1

  useEffect(() => {
    textareaRef.current?.focus({ preventScroll: true })
  }, [index, current?.id])

  const [clarification, setClarification] = useState(null)
  const [clarifyText, setClarifyText] = useState('')
  const [clarifyError, setClarifyError] = useState('')

  const submitClarification = async () => {
    const text = clarifyText.trim()
    if (text.length < 3) {
      setClarifyError('کمی بیشتر توضیح بده — همین جملهٔ کوتاه کافی نیست.')
      return
    }
    setClarifyError('')
    setSubmitting(true)
    try {
      await client.post(
        `/api/assess/${sessionId}/clarify`,
        { clarification_response: text },
        { timeout: 180000 },
      )
      localStorage.removeItem(answersKey(sessionId))
      localStorage.removeItem(selectionsKey(sessionId))
      navigate(`/report/${sessionId}`, { replace: true })
    } catch (err) {
      setClarifyError(friendlyError(err))
      setSubmitting(false)
    }
  }

  const submitTest = async () => {
    setConfirming(false)
    setSubmitting(true)
    setError('')
    try {
      const payload = (questions ?? []).map((q) => {
        const entry = {
          question_id: q.id,
          response_text: String(answers[q.id] ?? '').trim(),
        }
        // انتخاب فقط برای سؤالِ واقعاً چهارگزینه‌ای و فقط از روی اندیس
        if (Array.isArray(q.options) && q.options.length > 0) {
          const picked = selections[q.id]
          if (picked !== undefined && picked !== null && Number.isInteger(Number(picked))) {
            entry.selected_option_index = Number(picked)
            // متنِ گزینه هم صریح می‌رود تا بک‌اند برای خواندنِ «پاسخ شما»
            // مجبور به حدس‌زدن از متن نشود (بندِ ۱-الف).
            entry.selected_option_text = String(q.options[Number(picked)] ?? '')
          }
        }
        return entry
      })
      const { data } = await client.post(
        `/api/assess/${sessionId}/submit-test`,
        { answers: payload },
        { timeout: 240000 },
      )
      localStorage.removeItem(answersKey(sessionId))
      localStorage.removeItem(selectionsKey(sessionId))
      const interrogation = data?.interrogation ?? data?.clarification
      if (data?.needs_interrogation || data?.needs_clarification) {
        if (interrogation?.mirror_prompt) {
          setClarification({
            ...interrogation,
            question: interrogation?.question ?? 'کدام یکی را واقعاً باور داری؟',
          })
          setSubmitting(false)
          return
        }
      }
      if (data?.needs_clarification && data?.clarification?.mirror_prompt) {
        // موتور تشخیص داد دو پاسخ در تضادند: پیش از هر حکمی، آینه را نشان بده.
        setClarification(data.clarification)
        setSubmitting(false)
        return
      }
      navigate(`/report/${sessionId}`, { replace: true })
    } catch (err) {
      setError(friendlyError(err))
      setSubmitting(false)
    }
  }

  if (loading) {
    return <LoadingSpinner label="در حال تولید، اعتبارسنجی و رسم اشکال هندسی... (این فرآیند ممکن است ۱ تا ۲ دقیقه زمان ببرد)" className="min-h-[22rem]" />
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
      {/* ══════════ نوارِ بالای آزمون ══════════
          قبلاً سه لایه بود: یک کارتِ عنوان + یک حلقهٔ conic-gradient با
          «۰٪» + یک کارتِ جدا برای ۱۰ گام. حدودِ ۲۰۰px از بالای صفحه را
          می‌گرفت و در حالتِ ۳۹۰px می‌شکست.

          حالا یک نوار: عنوان در راست، گام‌ها در وسط، شمارش در چپ. */}
      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 sm:px-5">
          {/* عنوان */}
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-bold text-ink-faint">آزمون جامع تشخیصی</p>
            <h1 className="truncate text-[15px] font-black text-ink">{concept}</h1>
          </div>

          {/* گام‌ها — کم‌جا، عددِ فارسی، وضعیت با آیکون */}
          <nav aria-label="گام‌های آزمون" className="order-3 w-full sm:order-2 sm:w-auto">
            <ol className="flex flex-wrap items-center gap-1">
              {(questions ?? []).map((q, i) => {
                const done = isAnswered(q)
                const currentStep = i === index
                return (
                  <li key={q.id}>
                    <button
                      onClick={() => setIndex(i)}
                      aria-current={currentStep ? 'step' : undefined}
                      aria-label={`سؤال ${toFarsiNumber(i + 1)} از ${toFarsiNumber(total)} — ${STAGE_NAMES[stageOfQuestion(q, i) - 1]}${done ? ' — پاسخ داده شده' : ''}`}
                      title={`سؤال ${toFarsiNumber(i + 1)} — ${STAGE_NAMES[stageOfQuestion(q, i) - 1]}`}
                      className={[
                        'relative flex h-7 w-7 items-center justify-center rounded-md text-[10.5px] font-black tabular-nums transition',
                        currentStep
                          ? 'bg-primary text-white ring-2 ring-primary/30'
                          : done
                            ? 'bg-primary-soft text-primary-deep'
                            : 'bg-slate-100 text-ink-faint hover:bg-slate-200',
                      ].join(' ')}
                    >
                      {toFarsiNumber(i + 1)}
                      {/* نقطهٔ پاسخ‌داده‌شده — وضعیت فقط با رنگ نیست */}
                      {done && !currentStep && (
                        <span
                          className="absolute -top-0.5 -left-0.5 h-1.5 w-1.5 rounded-full bg-primary ring-1 ring-white"
                          aria-hidden="true"
                        />
                      )}
                    </button>
                  </li>
                )
              })}
            </ol>
          </nav>

          {/* شمارش — متن، نه حلقهٔ conic */}
          <div className="order-2 shrink-0 sm:order-3">
            <p className="text-[13px] font-black tabular-nums text-ink">
              {toFarsiNumber(answeredCount)}
              <span className="text-[11px] font-bold text-ink-faint"> / {toFarsiNumber(total)}</span>
            </p>
            <div className="mt-1 h-1 w-16 overflow-hidden rounded-full bg-slate-200" aria-hidden="true">
              <span
                className="block h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── کارت سؤال ── */}
      <div className="card border-brand-100/80 p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-brand-100/70 pb-4">
          <p className="text-[13px] font-black text-brand-700">
            سؤال {toFarsiNumber(index + 1)} از {toFarsiNumber(total)}
            <span className="mr-2 text-[11px] font-bold text-slate-500">
              · {STAGE_NAMES[stageOfQuestion(current, index) - 1]}
            </span>
          </p>
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

        {Array.isArray(current.forbidden_words) && current.forbidden_words.length > 0 && (
          <div className="mt-5 rounded-2xl border-2 border-rose-300 bg-rose-50 p-4">
            <p className="flex items-center gap-2 text-[12px] font-black text-rose-900">
              <AlertTriangle className="h-4 w-4" />
              کلماتِ ممنوعه — دستت را می‌بندیم!
            </p>
            <p className="mt-1 text-[11px] font-medium leading-6 text-rose-800">
              توضیحت را باید بدونِ این کلمات بنویسی. اگر یکی‌شان را به کار ببری، سیستم خودش تشخیص می‌دهد:
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {current.forbidden_words.map((w) => {
                const used = usedForbidden(currentAnswer, w)
                return (
                  <span
                    key={w}
                    className={[
                      'rounded-lg px-2 py-1 text-[11px] font-black ring-1 transition',
                      used
                        ? 'bg-rose-600 text-white ring-rose-700'
                        : 'bg-white text-rose-800 ring-rose-200',
                    ].join(' ')}
                  >
                    {w}
                    {used ? ' ✕' : ''}
                  </span>
                )
              })}
            </div>
          </div>
        )}

        {Array.isArray(current.options) && current.options.length > 0 && (
          <fieldset className="mt-5">
            <legend className="label">یکی از گزینه‌ها را انتخاب کن</legend>
            <div className="mt-2 grid gap-2">
              {current.options.map((opt, i) => {
                // فقط اندیس تعیین می‌کند؛ متنِ گزینه یا توضیحِ آزاد هرگز.
                const selected = Number(selections[current.id]) === i
                return (
                  <button
                    key={`${current.id}-opt-${i}`}
                    type="button"
                    onClick={() => setSelection(current.id, i)}
                    aria-pressed={selected}
                    className={[
                      'flex items-start gap-3 rounded-2xl border-2 p-3 text-right transition',
                      selected
                        ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-200'
                        : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-brand-50/40',
                    ].join(' ')}
                  >
                    <span
                      className={[
                        'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-black',
                        selected ? 'bg-brand-700 text-white' : 'bg-slate-100 text-slate-500',
                      ].join(' ')}
                    >
                      {toFarsiNumber(i + 1)}
                    </span>
                    {/* گزینه‌ها هم می‌توانند فرمول داشته باشند؛ همان مسیرِ ریاضیِ
                        امنِ متنِ سؤال (MathText) به کار می‌رود تا `$12$` خام
                        نماند. MathText به‌صورتِ پیش‌فرض HTML خام را رندر نمی‌کند. */}
                    <span className="math-inline text-[13px] font-bold leading-7 text-slate-800">
                      <MathText content={String(opt ?? '')} />
                    </span>
                  </button>
                )
              })}
            </div>
          </fieldset>
        )}

        <label htmlFor="answer" className="label mt-6">
          {Array.isArray(current.options) && current.options.length > 0 ? 'توضیحِ خودت (اختیاری)' : 'پاسخ شما'}
        </label>
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
                <strong>{toFarsiNumber(unanswered)} سؤال بی‌پاسخ</strong> باقی مانده است. بعد از ثبت نهایی، امکان اصلاح پاسخ‌ها نیست.
              </p>
            ) : (
              <p className="mt-2 text-[13px] leading-7 text-slate-600">
                همهٔ {toFarsiNumber(total)} پاسخ ثبت می‌شود و تحلیل یکپارچه انجام می‌شود. بعد از ثبت نهایی، امکان اصلاح نیست.
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

      {/* ── مودالِ بازپرسی (Cross-Check) ── */}
      {clarification && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-brand-950/60 p-4 sm:items-center">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-black text-amber-800">
                ایستگاهِ بازپرسی
              </span>
            </div>
            <h2 className="mt-3 text-[16px] font-black text-brand-950">
              یک سؤال تکمیلی برای رفع ابهام
            </h2>
            <p className="mt-1 text-[11px] font-bold text-slate-500">
              این سؤالِ اختیاری (سؤال ۱۱) فقط برای روشن‌شدن تناقضِ میان گفته‌هایت است.
            </p>
            <div className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-[13px] font-bold leading-8 text-amber-950">
              {clarification.mirror_prompt}
            </div>
            {Array.isArray(clarification.contradicting_questions) &&
              clarification.contradicting_questions.length > 0 && (
                <p className="mt-2 text-[11px] font-bold text-slate-500">
                  مرحله‌های درگیر: {clarification.contradicting_questions.map((n) => toFarsiNumber(n)).join(' و ')}
                </p>
              )}
            <label htmlFor="clarify" className="label mt-4">
              {clarification.question || 'خودت روشن کن — کدام یکی را واقعاً باور داری؟'}
            </label>
            <textarea
              id="clarify"
              rows={4}
              className="input resize-y leading-8"
              placeholder="مثلاً: در تست بی‌دقتی کردم؛ منظورِ اصلی‌ام این بود که…"
              value={clarifyText}
              onChange={(e) => setClarifyText(e.target.value)}
            />
            {clarifyError && (
              <p className="mt-2 rounded-xl bg-rose-50 p-2 text-[11px] font-bold text-rose-800" role="alert">
                {clarifyError}
              </p>
            )}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={submitClarification}
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-5 py-2.5 text-[13px] font-black text-white hover:bg-brand-800 disabled:opacity-60"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                ثبتِ توضیح و گرفتنِ کارنامه
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
