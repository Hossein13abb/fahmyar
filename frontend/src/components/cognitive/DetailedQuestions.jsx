/**
 * اجزای کارنامه — تمِ روشنِ «فهم‌یار» (فاز ۱۵)
 *
 * قراردادِ بصری: تمام سطوح روشن‌اند. هیچ `bg-slate-900` و متنِ سفید روی
 * سرمه‌ای در این فایل نیست — کارنامه یک سندِ آموزشی است، نه داشبوردِ شبانه.
 *
 * سه جزء:
 *   ۱. <QuestionCard>       — کارتِ سؤال با حاشیهٔ فوقانیِ رنگی
 *   ۲. <ContradictionCard>  — کارتِ شکارِ تناقض، روشن و کهربایی‌لبه
 *   ۳. <LiveTutorModal>     — مودالِ «میز معلم»، محتوا از /api/tutor/explain
 */
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  KeyRound,
  Lightbulb,
  MessageCircleQuestion,
  Sparkles,
  Target,
  Workflow,
  Wrench,
  X,
} from 'lucide-react'
import client from '../../api/client'
import MathText from '../MathText'

const faNum = (v) => String(v ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

export const STAGE_NAMES = [
  'فلسفه و تصویر کلان',
  'تستِ لایهٔ نقاب',
  'مونتاژ ذهنی و دستکاری',
  'عیب‌یابیِ ساعتِ خراب',
  'چالشِ فاینمن',
]

/**
 * وضعیت → حاشیهٔ فوقانی، بج و برچسب.
 * کلیدها همان چهار حالتِ استانداردِ بک‌اند هستند (نگاشت در لایهٔ نمایش).
 */
export const TONE = {
  CORRECT: {
    border: 'border-t-emerald-500',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    label: 'درست',
    Icon: CheckCircle2,
  },
  HALF_CORRECT: {
    border: 'border-t-amber-500',
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    label: 'نیمه‌درست',
    Icon: AlertTriangle,
  },
  WRONG: {
    border: 'border-t-rose-500',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    label: 'نادرست',
    Icon: AlertTriangle,
  },
  INSUFFICIENT_EVIDENCE: {
    border: 'border-t-slate-300',
    badge: 'bg-slate-100 text-slate-600 border-slate-200',
    label: 'شواهد ناکافی',
    Icon: BookOpen,
  },
}

export const toneOf = (status) =>
  TONE[String(status ?? '').toUpperCase()] ?? TONE.INSUFFICIENT_EVIDENCE

const rawText = (value) => String(value ?? '').trim()

/** متنِ چندخطی با رندرِ ریاضی (همان MathText بقیهٔ کارنامه). */
function RichText({ content, className = '' }) {
  const text = rawText(content)
  if (!text) return null
  return (
    <div className={`math-content whitespace-pre-line ${className}`}>
      <MathText content={text} />
    </div>
  )
}

// ═══════════════════════════ کارتِ سؤال ═══════════════════════════
export function QuestionCard({ q, index, onOpen }) {
  const tone = toneOf(q?.status)
  const ToneIcon = tone.Icon
  const order = Number(q?.order) || index + 1
  const stage = Number(q?.stage) || Math.min(5, Math.floor((order - 1) / 2) + 1)
  const hasOptions = Array.isArray(q?.options) && q.options.length > 0
  const pickedIdx = Number.isInteger(Number(q?.selected_option_index))
    ? Number(q.selected_option_index)
    : null
  const selectedText =
    pickedIdx !== null ? rawText(q?.selected_option_text ?? q?.options?.[pickedIdx]) : ''
  const answer = rawText(q?.response)

  return (
    <article
      className={`flex flex-col justify-between rounded-2xl border border-slate-200/80 border-t-4 bg-white p-5 shadow-sm transition-all duration-200 hover:shadow-md ${tone.border}`}
    >
      {/* هدر: شماره + مرحله در راست، وضعیت در چپ */}
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[11px] font-black text-slate-700 tabular-nums">
            {faNum(order)}
          </span>
          <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-bold text-slate-600">
            مرحلهٔ {faNum(stage)}: {STAGE_NAMES[stage - 1] ?? 'زنجیرهٔ فهم'}
          </span>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-black ${tone.badge}`}
        >
          <ToneIcon className="h-3 w-3" strokeWidth={2.5} />
          {tone.label}
        </span>
      </header>

      {/* صورتِ سؤال */}
      {rawText(q?.question_text) && (
        <RichText
          content={q.question_text}
          className="mt-3 mb-3 text-sm font-medium leading-relaxed text-slate-800"
        />
      )}

      {/* پاسخِ تو */}
      <div className="mb-3 rounded-xl border border-slate-200/60 bg-slate-50/80 p-3">
        <p className="mb-1 flex items-center gap-1.5 text-[10px] font-black text-slate-500">
          <MessageCircleQuestion className="h-3 w-3" /> پاسخِ تو
        </p>
        {hasOptions ? (
          pickedIdx === null ? (
            <p className="text-xs text-slate-400">بدون پاسخ</p>
          ) : (
            <div className="text-xs leading-6 text-slate-700">
              گزینهٔ {faNum(pickedIdx + 1)}:{' '}
              <span className="math-inline font-bold text-slate-900">
                <MathText content={selectedText} />
              </span>
            </div>
          )
        ) : (
          <RichText
            content={answer || 'بدون پاسخ'}
            className={`text-xs leading-6 ${answer ? 'text-slate-700' : 'text-slate-400'}`}
          />
        )}
      </div>

      {/* دیدگاهِ تشخیصی */}
      {rawText(q?.diagnostic_insight) && (
        <div className="mb-4 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-[10px] font-black text-emerald-800">
            <Sparkles className="h-3 w-3" /> دیدگاهِ تشخیصیِ فهم‌یار
          </p>
          <RichText
            content={q.diagnostic_insight}
            className="text-xs leading-relaxed text-emerald-900"
          />
        </div>
      )}

      <button
        type="button"
        onClick={() => onOpen?.(q, order)}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-medium text-white shadow-sm transition-all hover:bg-emerald-700"
      >
        <Lightbulb className="h-4 w-4" />
        می‌خوای این گره رو باز کنیم؟ (آموزش زنده)
      </button>
    </article>
  )
}

// ═══════════════════════ کارتِ شکارِ تناقض ═══════════════════════
/** نوعِ یافته → برچسب و رنگِ بج (همه روشن، بدونِ زمینهٔ تیره). */
const FINDING_LOOK = {
  CONTRADICTION: {
    label: 'تناقض عمیق',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    title: 'text-slate-800',
  },
  JARGON_VIOLATION: {
    label: 'زندانِ اصطلاح',
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    title: 'text-slate-800',
  },
  BLUFF_DETECTED: {
    label: 'بلوفِ شناخته‌شده',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    title: 'text-slate-800',
  },
  SYNERGY: {
    label: 'هم‌افزایی',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    title: 'text-slate-800',
  },
  SLIP_RESOLVED: {
    label: 'حل‌شده در بازپرسی',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    title: 'text-slate-800',
  },
}

export function ContradictionCard({ finding, onTeach, busy = false }) {
  const type = String(finding?.type ?? '').toUpperCase()
  const look = FINDING_LOOK[type] ?? FINDING_LOOK.SYNERGY
  const isContradiction = type === 'CONTRADICTION'
  // «حل‌شده در بازپرسی» وقتی کارنامه خودش resolution ثبت کرده باشد.
  const resolved = Boolean(rawText(finding?.resolution))

  return (
    <div className="flex flex-col rounded-2xl border border-amber-200/80 bg-white p-5 shadow-sm transition-all hover:border-amber-300 hover:shadow-md">
      <div className="flex flex-wrap items-center gap-2">
        <p className={`min-w-0 flex-1 text-sm font-bold leading-6 ${look.title}`}>
          {finding?.contradiction_title || finding?.title}
        </p>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-black ${
            resolved ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : look.badge
          }`}
        >
          {resolved ? (
            <>
              <CheckCircle2 className="h-3 w-3" strokeWidth={2.5} />
              حل‌شده در بازپرسی
            </>
          ) : (
            look.label
          )}
        </span>
      </div>

      {rawText(finding?.description) && (
        <p className="mt-2 text-sm leading-relaxed text-slate-600">{finding.description}</p>
      )}

      {/* یادآوریِ دو حرفِ متناقض / توضیحِ خودِ دانش‌آموز */}
      {rawText(finding?.resolution) && (
        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-6 text-slate-700">
          <span className="font-bold text-slate-800">توضیحِ خودت: </span>
          {finding.resolution}
        </div>
      )}

      {isContradiction && (
        <button
          type="button"
          onClick={() => onTeach?.(finding)}
          disabled={busy}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-xs font-bold text-amber-900 shadow-sm transition-all hover:border-emerald-400 hover:bg-emerald-50 hover:text-emerald-800 disabled:opacity-60"
        >
          <Sparkles className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
          {busy ? 'معلم دارد تحلیل می‌کند...' : 'حل این تناقض با معلم (چرا تناقض داشتم؟)'}
        </button>
      )}
    </div>
  )
}

// ══════════════════════ مودالِ «میز معلم» ══════════════════════
const LOADING_LINES = [
  'معلم فهم‌یار در حال بررسی گره ذهنی توست...',
  'دارد ردِ پای فکرت را پیدا می‌کند...',
  'دارد یک مثالِ روزمره برایت آماده می‌کند...',
]

/** سه باکسِ محتوا — همه روشن، بدونِ سایهٔ تیره. */
const BOX = {
  rose: 'border-rose-200 bg-rose-50 text-rose-950',
  emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950',
  amber: 'border-amber-200 bg-amber-50 text-amber-950',
}

function TeachingBox({ Icon, iconTone, step, title, className, children }) {
  return (
    <section className={`mb-3 rounded-2xl border p-4 text-sm ${className}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <Icon className={`h-4 w-4 shrink-0 ${iconTone}`} strokeWidth={2.3} />
        <span className="text-[10px] font-black opacity-60">بخش {faNum(step)}</span>
      </div>
      <h3 className="mb-1.5 text-sm font-black leading-6">{title}</h3>
      <div className="text-sm leading-relaxed opacity-90">{children}</div>
    </section>
  )
}

function LoadingState() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % LOADING_LINES.length), 2200)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/60 px-4 py-3">
        <span className="relative flex h-8 w-8 shrink-0 items-center justify-center">
          <span className="absolute inset-0 animate-ping rounded-full bg-emerald-300/50" />
          <Sparkles className="relative h-4 w-4 animate-pulse text-emerald-600" />
        </span>
        <p className="text-xs font-bold leading-6 text-emerald-900">{LOADING_LINES[step]}</p>
      </div>

      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="animate-pulse rounded-2xl border border-slate-100 bg-slate-50 p-4"
          style={{ animationDelay: `${i * 160}ms` }}
        >
          <div className="h-3 w-32 rounded-full bg-slate-200" />
          <div className="mt-2.5 space-y-2">
            <div className="h-2.5 w-full rounded-full bg-slate-200/80" />
            <div className="h-2.5 w-[92%] rounded-full bg-slate-200/60" />
            <div className="h-2.5 w-[68%] rounded-full bg-slate-200/50" />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * مودالِ مرکزیِ آموزش زنده. تا رسیدنِ پاسخ، اسکلتونِ پالس‌دار نشان می‌دهد؛
 * بعد سه باکسِ تدریس. محتوا از `POST /api/tutor/explain` می‌آید.
 */
export function LiveTutorModal({ open, target, sessionId, onClose }) {
  const [state, setState] = useState({ loading: false, error: '', data: null })
  const isContradiction = target?.type === 'contradiction'

  useEffect(() => {
    if (!open || !target) return undefined
    const ctrl = new AbortController()
    setState({ loading: true, error: '', data: null })

    client
      .post(
        '/api/tutor/explain',
        {
          session_id: sessionId,
          type: isContradiction ? 'contradiction' : 'question',
          order: isContradiction ? null : target.order,
          finding_index: isContradiction ? target.findingIndex : null,
        },
        { signal: ctrl.signal },
      )
      .then(({ data }) => {
        if (!ctrl.signal.aborted) setState({ loading: false, error: '', data })
      })
      .catch((err) => {
        if (ctrl.signal.aborted) return
        const msg =
          err?.response?.data?.detail || 'نشد به معلم وصل شویم. یک بار دیگر امتحان کن.'
        setState({ loading: false, error: String(msg), data: null })
      })

    return () => ctrl.abort()
  }, [open, target, sessionId, isContradiction])

  // Esc برای بستن + قفلِ اسکرولِ پشت
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!open) {
      setShown(false)
      return undefined
    }
    const raf = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(raf)
  }, [open])

  if (!open) return null

  const content = state.data?.content ?? {}
  const title = isContradiction
    ? state.data?.title || target?.finding?.contradiction_title || target?.finding?.title
    : null

  // Portal: بدونِ این، هر والدِ `transform`دار مرجعِ `fixed` می‌شود و مودال
  // به کارت می‌چسبد نه به پنجره (این باگ در فاز ۱۲ هم رخ داده بود).
  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tutor-title"
      aria-busy={state.loading}
    >
      <button
        type="button"
        aria-label="بستن"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default"
      />

      <div
        className={`relative flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-slate-100 bg-white shadow-2xl transition-all duration-200 ${
          shown ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        }`}
      >
        {/* هدر */}
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-emerald-100 bg-emerald-50/70 px-5 py-4">
          <div className="min-w-0">
            <h2
              id="tutor-title"
              className="flex items-center gap-2 text-base font-black text-emerald-950"
            >
              <span aria-hidden="true">👨‍🏫</span>
              میز معلم فهم‌یار
            </h2>
            <p className="mt-1 truncate text-xs font-medium text-emerald-800/80">
              {isContradiction
                ? title || 'حلِ تناقض'
                : `سؤال ${faNum(target?.order)} · مرحلهٔ ${faNum(
                    Number(target?.q?.stage) ||
                      Math.min(5, Math.floor(((Number(target?.order) || 1) - 1) / 2) + 1),
                  )}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="بستنِ میز معلم"
            className="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        {/* بدنه */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          {state.loading ? (
            <LoadingState />
          ) : state.error ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
              <p className="flex items-center gap-2 text-sm font-bold text-rose-900">
                <AlertTriangle className="h-4 w-4" /> {state.error}
              </p>
              <p className="mt-1 text-xs leading-6 text-rose-700">
                هیچ داده‌ای از دست نرفت — می‌توانی دوباره امتحان کنی.
              </p>
            </div>
          ) : isContradiction ? (
            <>
              <TeachingBox
                Icon={Target}
                iconTone="text-rose-600"
                step={1}
                title="چرا این تناقض در ذهنت شکل گرفت؟"
                className={BOX.rose}
              >
                <RichText content={content.why_it_happened} />
              </TeachingBox>
              <TeachingBox
                Icon={Workflow}
                iconTone="text-emerald-600"
                step={2}
                title="پلِ اتصالِ این دو مفهوم"
                className={BOX.emerald}
              >
                <RichText content={content.how_to_connect_bridge} />
              </TeachingBox>
              <TeachingBox
                Icon={KeyRound}
                iconTone="text-amber-600"
                step={3}
                title="چطور سرِ آزمون در این دام نیفتیم؟"
                className={`${BOX.amber} font-medium`}
              >
                <RichText content={content.exam_shield_tip} />
              </TeachingBox>
            </>
          ) : (
            <>
              <TeachingBox
                Icon={Target}
                iconTone="text-rose-600"
                step={1}
                title="کجای ماجرا لغزیدی؟"
                className={BOX.rose}
              >
                <RichText content={content.misconception_root} />
              </TeachingBox>
              <TeachingBox
                Icon={Lightbulb}
                iconTone="text-emerald-600"
                step={2}
                title="اصل ماجرا چیه؟ (آموزش مفهومی)"
                className={BOX.emerald}
              >
                <RichText content={content.intuitive_explanation} />
              </TeachingBox>
              <TeachingBox
                Icon={KeyRound}
                iconTone="text-amber-600"
                step={3}
                title="رمز طلایی ساعت‌ساز"
                className={`${BOX.amber} font-medium`}
              >
                <RichText content={content.golden_tip} />
              </TeachingBox>
            </>
          )}
        </div>

        {/* فوتر */}
        {!state.loading && (
          <footer className="shrink-0 px-5 pb-5">
            <button
              type="button"
              onClick={onClose}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-medium text-white transition-all hover:bg-slate-800"
            >
              <CheckCircle2 className="h-4 w-4" />
              فهمیدم! ساعت رو بستم
              <span aria-hidden="true">🚀</span>
              <ArrowLeft className="h-4 w-4" />
            </button>
          </footer>
        )}
      </div>
    </div>
  )

  return typeof document === 'undefined' ? modal : createPortal(modal, document.body)
}

// ═════════════════ بخشِ «تحلیل تفصیلی» ═════════════════
export default function DetailedQuestions({ questions = [], sessionId }) {
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState(null)

  const openFor = (q, order) => {
    setTarget({ type: 'question', q, order })
    setOpen(true)
  }

  const cards = useMemo(
    () => questions.map((q, i) => <QuestionCard key={q.question_id ?? i} q={q} index={i} onOpen={openFor} />),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [questions],
  )

  if (!questions.length) {
    return <p className="text-[13px] text-slate-500">سؤالی ثبت نشده است.</p>
  }

  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">{cards}</div>
      <LiveTutorModal
        open={open}
        target={target}
        sessionId={sessionId}
        onClose={() => setOpen(false)}
      />
    </>
  )
}

export { Wrench }
