/**
 * اجزای کارنامه — سیستمِ بصریِ «زمردِ گرم» (فاز ۱۶)
 *
 * جهتِ طراحی: کارنامه باید **غنی** باشد، نه تخت. سه ابزار برای این کار:
 *   ۱. نوارِ فوقانیِ گرادیانتی (نه یک خطِ رنگیِ ساده)
 *   ۲. سایهٔ دولایه (panel) که لبه را تعریف می‌کند و عمق می‌دهد
 *   ۳. هالهٔ رنگِ وضعیت در گوشهٔ کارت، در حدی که فقط «حس» شود
 *
 * همهٔ رنگ‌ها از پالتِ برند (زمردی) + کهرباییِ calm می‌آیند تا هم‌خوان بمانند.
 * هیچ سطحِ تیره‌ای در کارنامه نیست؛ تنها استثنا دکمهٔ پایانیِ مودال است.
 */
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  GitBranch,
  Eye,
  ShieldAlert,
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  KeyRound,
  Lightbulb,
  MessageCircleQuestion,
  Sparkles,
  Target,
  Workflow,
  X,
} from 'lucide-react'
import client from '../../api/client'
import MathText from '../MathText'

const faNum = (v) => String(v ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

// همهٔ دکمه‌های کارت یک ظاهر دارند؛ وضعیت با نوار/بج/هاله گفته می‌شود،
// نه با رنگِ دکمه. چهار دکمهٔ چهار‌رنگ، صفحه را پراکنده می‌کرد.
const CTA = 'from-brand-700 to-emerald-600 hover:from-brand-800 hover:to-emerald-700'

/**
 * برچسبِ رو به کاربرِ مراحل.
 *
 * نام‌های متدولوژیِ داخلی («لایهٔ نقاب»، «فاینمن»، «ساعتِ خراب») عمداً
 * این‌جا نیستند — داراییِ فکری است و نباید در UI دیده شود. منطقِ سنجش
 * دست‌نخورده است؛ فقط زبانِ نمایش عوض شده.
 */
export const STAGE_NAMES = [
  'سؤال مفهومی',
  'سؤال چهارگزینه‌ای',
  'پیش‌بینی رفتار پدیده',
  'بررسی استدلال علمی',
  'توضیح ساده و شهودی',
]

/**
 * وضعیت → نوارِ گرادیانتی، هاله، بج و برچسب.
 *
 * `aurora` رنگِ هاله‌ای است که در گوشهٔ کارت پخش می‌شود؛ بدونِ آن کارت‌ها
 * همه یک‌شکل دیده می‌شدند و وضعیت فقط در یک بجِ کوچک خلاصه می‌شد.
 */
export const TONE = {
  CORRECT: {
    rail: 'from-emerald-400 via-emerald-500 to-teal-500',
    aurora: 'from-emerald-200/45',
    ring: 'ring-emerald-100',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    label: 'درست',
    Icon: CheckCircle2,
    cta: CTA,
  },
  HALF_CORRECT: {
    rail: 'from-amber-300 via-amber-400 to-orange-400',
    aurora: 'from-amber-200/45',
    ring: 'ring-amber-100',
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    label: 'نیمه‌درست',
    Icon: AlertTriangle,
    cta: CTA,
  },
  WRONG: {
    rail: 'from-rose-300 via-rose-400 to-red-400',
    aurora: 'from-rose-200/40',
    ring: 'ring-rose-100',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    label: 'نادرست',
    Icon: AlertTriangle,
    cta: CTA,
  },
  INSUFFICIENT_EVIDENCE: {
    rail: 'from-slate-300 via-slate-400 to-slate-500',
    aurora: 'from-slate-200/40',
    ring: 'ring-slate-100',
    badge: 'bg-slate-100 text-slate-600 border-slate-200',
    label: 'شواهد ناکافی',
    Icon: BookOpen,
    cta: CTA,
  },
}

export const toneOf = (status) =>
  TONE[String(status ?? '').toUpperCase()] ?? TONE.INSUFFICIENT_EVIDENCE

const rawText = (value) => String(value ?? '').trim()

/**
 * متنِ چندخطی با رندرِ ریاضی و ترازِ دوطرفه.
 *
 * ``text-justify`` عمداً **پیش‌فرض** است، نه چیزی که هر مصرف‌کننده یادش
 * باشد اضافه کند. در متنِ فارسی، ترازِ چپ لبه‌ها را دندانه‌دار می‌کند و
 * سند شبیهِ یادداشتِ دستی می‌شود؛ دوطرفه لبه‌ها را صاف و حرفه‌ای می‌کند.
 *
 * ``text-right`` هم لازم است: ``justify`` در خطِ آخر به ``text-align``
 * برمی‌گردد و در RTL باید راست بماند، وگرنه خطِ آخر چپ می‌پرد.
 * ``dir="rtl"`` صریح گذاشته شده تا اگر والد جهتِ دیگری داشت، نشکند.
 */
function RichText({ content, className = '', interactive = true }) {
  const text = rawText(content)
  if (!text) return null
  return (
    <div
      dir="rtl"
      className={`math-content whitespace-pre-line text-justify text-right ${className}`}
    >
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
    <article className="group relative flex flex-col overflow-hidden rounded-2xl bg-white shadow-panel ring-1 ring-slate-200/70 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-panel-hover">
      {/* نوارِ فوقانیِ گرادیانتی — رنگِ وضعیت، با عمق */}
      <span className={`h-1.5 w-full bg-gradient-to-l ${tone.rail}`} aria-hidden="true" />

      {/* هالهٔ گوشه — فقط حسِ رنگ، نه یک لکه */}
      <span
        className={`pointer-events-none absolute -left-16 -top-16 h-40 w-40 rounded-full bg-gradient-to-br to-transparent blur-2xl ${tone.aurora}`}
        aria-hidden="true"
      />

      <div className="relative flex flex-1 flex-col p-5">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-[12px] font-black text-white shadow-sm ${tone.rail} tabular-nums`}
            >
              {faNum(order)}
            </span>
            <span className="rounded-lg bg-slate-50 px-2 py-1 text-[10px] font-bold text-slate-600 ring-1 ring-slate-200/70">
              {STAGE_NAMES[stage - 1] ?? 'سؤال تحلیلی'}
            </span>
          </div>
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-black ${tone.badge}`}
          >
            <ToneIcon className="h-3 w-3" strokeWidth={2.5} />
            {tone.label}
          </span>
        </header>

        {rawText(q?.question_text) && (
          <RichText
            content={q.question_text}
            className="math-content mt-3 mb-3 text-justify text-right text-sm font-medium leading-relaxed text-slate-800"
          />
        )}

        {/* پاسخِ تو — با نوارِ کناری، نه فقط یک باکس */}
        <div className="mb-3 rounded-xl border border-slate-200/70 bg-slate-50/80 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-[10px] font-black text-slate-500">
            <MessageCircleQuestion className="h-3 w-3" /> پاسخِ تو
          </p>
          {hasOptions ? (
            pickedIdx === null ? (
              <p className="text-xs text-slate-400">بدون پاسخ</p>
            ) : (
              <div className="text-justify text-right text-xs leading-6 text-slate-700">
                گزینهٔ {faNum(pickedIdx + 1)}:{' '}
                <span className="math-inline font-bold text-slate-900">
                  <MathText content={selectedText} />
                </span>
              </div>
            )
          ) : (
            <RichText
              content={answer || 'بدون پاسخ'}
              className={`text-justify text-right text-xs leading-6 ${answer ? 'text-slate-700' : 'text-slate-400'}`}
            />
          )}
        </div>

        {/* دیدگاهِ تشخیصی — سبزِ گرم با درخششِ ملایم */}
        {rawText(q?.diagnostic_insight) && (
          <div className="mb-4 rounded-xl border border-emerald-200/70 bg-gradient-to-br from-emerald-50 to-teal-50/40 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
            <p className="mb-1 flex items-center gap-1.5 text-[10px] font-black text-emerald-700">
              <Sparkles className="h-3 w-3" /> دیدگاهِ تشخیصیِ فهم‌یار
            </p>
            <RichText
              content={q.diagnostic_insight}
              className="text-justify text-right text-xs leading-relaxed text-emerald-900"
            />
          </div>
        )}

        <button
          type="button"
          onClick={() => onOpen?.(q, order)}
          className={`mt-auto flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 ${tone.cta}`}
        >
          <Lightbulb className="h-4 w-4" />
          می‌خوای این گره رو باز کنیم؟ (آموزش زنده)
        </button>
      </div>
    </article>
  )
}

// ═══════════════════════ کارتِ شکارِ تناقض ═══════════════════════
/**
 * هویتِ رنگیِ کارت‌های تناقض.
 *
 * سه خانوادهٔ رنگ، نه پنج رنگِ پراکنده. قاعده: هر خانواده یک معنا دارد و
 * همهٔ آن‌ها از یک لنگرِ مشترک (زمردیِ برند) شروع یا به آن می‌رسند، پس
 * کنارِ هم «هم‌خانواده» دیده می‌شوند:
 *
 *   زمردی/فیروزه‌ای  →  چیزِ خوبی پیدا شد (هم‌افزایی، حل‌شده)
 *   کهربایی/نارنجی   →  هشدار (زندانِ اصطلاح)
 *   رز/قرمز          →  جای آسیب (تناقض، بلوف)
 *
 * زمینهٔ کارت خودش رنگی است — نه فقط قابش. قابِ رنگی دورِ سفید، کارت را
 * «قاب‌بندی‌شده» نشان می‌داد نه «رنگی».
 */
const FINDING_LOOK = {
  CONTRADICTION: {
    label: 'تناقض عمیق',
    Icon: GitBranch,
    body: 'bg-gradient-to-br from-rose-100 via-rose-50 to-amber-100/70',
    rail: 'from-rose-400 via-rose-500 to-amber-400',
    icon: 'from-rose-500 to-rose-600',
    title: 'text-rose-950',
    text: 'text-rose-950/80',
    badge: 'bg-white/85 text-rose-700 ring-1 ring-rose-200',
    glow: 'bg-rose-300/50',
  },
  JARGON_VIOLATION: {
    label: 'زندانِ اصطلاح',
    Icon: ShieldAlert,
    body: 'bg-gradient-to-br from-amber-100 via-amber-50 to-orange-100/70',
    rail: 'from-amber-400 via-orange-400 to-amber-300',
    icon: 'from-amber-500 to-orange-500',
    title: 'text-amber-950',
    text: 'text-amber-950/80',
    badge: 'bg-white/85 text-amber-800 ring-1 ring-amber-200',
    glow: 'bg-amber-300/50',
  },
  BLUFF_DETECTED: {
    label: 'بلوفِ شناخته‌شده',
    Icon: Eye,
    body: 'bg-gradient-to-br from-rose-100 via-red-50 to-rose-100/60',
    rail: 'from-rose-500 via-red-400 to-rose-300',
    icon: 'from-rose-600 to-red-600',
    title: 'text-rose-950',
    text: 'text-rose-950/80',
    badge: 'bg-white/85 text-rose-800 ring-1 ring-rose-200',
    glow: 'bg-rose-300/50',
  },
  SYNERGY: {
    label: 'هم‌افزایی',
    Icon: Sparkles,
    body: 'bg-gradient-to-br from-emerald-100 via-teal-50 to-cyan-100/60',
    rail: 'from-emerald-400 via-teal-400 to-cyan-300',
    icon: 'from-emerald-500 to-teal-600',
    title: 'text-emerald-950',
    text: 'text-emerald-950/80',
    badge: 'bg-white/85 text-emerald-800 ring-1 ring-emerald-200',
    glow: 'bg-emerald-300/50',
  },
  SLIP_RESOLVED: {
    label: 'حل‌شده در بازپرسی',
    Icon: CheckCircle2,
    body: 'bg-gradient-to-br from-sky-100 via-emerald-50 to-teal-100/60',
    rail: 'from-sky-400 via-emerald-400 to-teal-300',
    icon: 'from-sky-500 to-emerald-600',
    title: 'text-teal-950',
    text: 'text-teal-950/80',
    badge: 'bg-white/85 text-teal-800 ring-1 ring-teal-200',
    glow: 'bg-sky-300/50',
  },
}

export function ContradictionCard({ finding, onTeach, busy = false }) {
  const type = String(finding?.type ?? '').toUpperCase()
  const look = FINDING_LOOK[type] ?? FINDING_LOOK.SYNERGY
  const isContradiction = type === 'CONTRADICTION'
  const resolved = Boolean(rawText(finding?.resolution))
  const Icon = look.Icon

  // دو پاسخِ ناسازگار — اگر بک‌اند هر دو را داده باشد، کنارِ هم نشان داده
  // می‌شوند تا دانش‌آموز خودش ناسازگاری را ببیند، نه اینکه فقط بخواند.
  const quoteA = rawText(finding?.quote_a ?? finding?.first_quote)
  const quoteB = rawText(finding?.quote_b ?? finding?.second_quote)
  const hasPair = Boolean(quoteA && quoteB)

  return (
    <article className="flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
      {/* نشانگرِ نوع — نوارِ نازکِ رنگی، نه بدنهٔ گرادیانتی */}
      <span
        className={`h-1 w-full ${
          isContradiction ? 'bg-danger' : 'bg-caution'
        }`}
        aria-hidden="true"
      />

      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
            isContradiction ? 'bg-danger-soft text-danger' : 'bg-caution-soft text-caution'
          }`}
        >
          <Icon className="h-3.5 w-3.5" strokeWidth={2.2} />
        </span>
        <p className="min-w-0 flex-1 text-[12.5px] font-black leading-6 text-ink">
          {finding?.contradiction_title || finding?.title}
        </p>
        <span
          className={`shrink-0 rounded-md px-2 py-0.5 text-[9.5px] font-black ${
            resolved
              ? 'bg-primary-soft text-primary-deep'
              : isContradiction
              ? 'bg-danger-soft text-danger'
              : 'bg-caution-soft text-caution'
          }`}
        >
          {resolved ? 'حل‌شده در بازپرسی' : look.label}
        </span>
      </div>

      {/* ── مقایسهٔ دو پاسخ ── */}
      {hasPair ? (
        <div className="mx-4 mt-3 grid gap-2 sm:grid-cols-2">
          {[
            { tag: 'اینجا گفتی', text: quoteA },
            { tag: 'و اینجا', text: quoteB },
          ].map(({ tag, text }) => (
            <blockquote
              key={tag}
              className="rounded-lg border-r-2 border-slate-300 bg-surface-muted px-3 py-2"
            >
              <span className="text-[9.5px] font-black text-ink-faint">{tag}</span>
              <p className="mt-0.5 text-justify text-right text-[11.5px] leading-6 text-ink-soft">
                «{text}»
              </p>
            </blockquote>
          ))}
        </div>
      ) : (
        rawText(finding?.description) && (
          <p className="mx-4 mt-2 text-justify text-right text-[11.5px] leading-7 text-ink-soft">
            {finding.description}
          </p>
        )
      )}

      {rawText(finding?.resolution) && (
        <p className="mx-4 mt-2 rounded-lg bg-surface-muted px-3 py-2 text-justify text-right text-[11px] leading-6 text-ink-soft">
          <span className="font-black text-ink">توضیحِ خودت: </span>
          {finding.resolution}
        </p>
      )}

      {isContradiction && (
        <div className="mt-auto px-4 py-3">
          <button
            type="button"
            onClick={() => onTeach?.(finding)}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger-soft px-3 py-1.5 text-[10.5px] font-black text-danger transition hover:border-danger/60 hover:bg-danger/10 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
          >
            <Sparkles className={`h-3.5 w-3.5 ${busy ? 'animate-spin' : ''}`} />
            {busy ? 'معلم دارد تحلیل می‌کند...' : 'حل این تناقض با معلم (چرا تناقض داشتم؟)'}
          </button>
        </div>
      )}
    </article>
  )
}

// ══════════════════════ مودالِ «میز معلم» ══════════════════════
const LOADING_LINES = [
  'معلم فهم‌یار در حال بررسی گره ذهنی توست...',
  'دارد ردِ پای فکرت را پیدا می‌کند...',
  'دارد یک مثالِ روزمره برایت آماده می‌کند...',
]

const BOX = {
  rose: 'border-rose-200/80 bg-gradient-to-br from-rose-50 to-rose-50/30 text-rose-950',
  emerald:
    'border-emerald-200/80 bg-gradient-to-br from-emerald-50 to-teal-50/40 text-emerald-950',
  amber:
    'border-amber-200/80 bg-gradient-to-br from-amber-50 to-calm-50/60 text-amber-950',
}

function TeachingBox({ Icon, iconTone, step, title, className, children }) {
  return (
    <section className={`mb-3 rounded-2xl border p-4 text-sm shadow-sm ${className}`}>
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`flex h-6 w-6 items-center justify-center rounded-lg bg-white/80 ring-1 ring-current/10 ${iconTone}`}>
          <Icon className="h-3.5 w-3.5" strokeWidth={2.3} />
        </span>
        <span className="text-[10px] font-black opacity-50">بخش {faNum(step)}</span>
      </div>
      <h3 className="mb-1.5 text-sm font-black leading-6">{title}</h3>
      <div className="text-justify text-right text-sm leading-relaxed opacity-90">{children}</div>
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
      <div className="flex items-center gap-3 rounded-2xl border border-emerald-200/70 bg-gradient-to-l from-emerald-50 to-teal-50/50 px-4 py-3">
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

export function LiveTutorModal({ open, target, sessionId, onClose }) {
  const [state, setState] = useState({ loading: false, error: '', data: null })
  const isContradiction = target?.type === 'contradiction'
  const isGap = target?.type === 'learning_gap'

  useEffect(() => {
    if (!open || !target) return undefined
    const ctrl = new AbortController()
    setState({ loading: true, error: '', data: null })

    client
      .post(
        '/api/tutor/explain',
        {
          session_id: sessionId,
          type: isGap ? 'learning_gap' : isContradiction ? 'contradiction' : 'question',
          order: isContradiction || isGap ? null : target.order,
          finding_index: isContradiction ? target.findingIndex : null,
          gap_id: isGap ? target.gap?.id : null,
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
  }, [open, target, sessionId, isContradiction, isGap])

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
  // به کارت می‌چسبد نه به پنجره (این باگ دو بار رخ داده است).
  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 "
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
        className={`relative flex max-h-[calc(100vh-2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-lift ring-1 ring-white/60 transition-all duration-200 ${
          shown ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        }`}
      >
        {/* هدر: نوارِ گرادیانتیِ زمردی */}
        <div className="h-1.5 shrink-0 bg-gradient-to-l from-emerald-400 via-teal-400 to-brand-500" />
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-emerald-100/80 bg-gradient-to-l from-emerald-50 via-white to-emerald-50/50 px-5 py-4">
          <div className="min-w-0">
            <h2
              id="tutor-title"
              className="flex items-center gap-2 text-base font-black text-brand-950"
            >
              <span aria-hidden="true">👨‍🏫</span>
              میز معلم فهم‌یار
            </h2>
            <p className="mt-1 truncate text-xs font-medium text-emerald-800/70">
              {isGap
                ? `${target?.gap?.gap_title || 'گرهٔ پیش‌نیاز'}${
                    target?.gap?.source_topic ? ` · ${target.gap.source_topic}` : ''
                  }`
                : isContradiction
                ? title || 'حلِ تناقض'
                : `سؤال ${faNum(target?.order)} · ${
                    STAGE_NAMES[
                      (Number(target?.q?.stage) ||
                        Math.min(5, Math.floor(((Number(target?.order) || 1) - 1) / 2) + 1)) - 1
                    ] ?? 'سؤال تحلیلی'
                  }`}
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
          ) : isGap ? (
            <>
              <TeachingBox
                Icon={Target}
                iconTone="text-rose-600"
                step={1}
                title="چرا این گرهٔ پایه، تو را در مباحثِ بالاتر به دام می‌اندازد؟"
                className={BOX.rose}
              >
                <RichText content={content.why_it_matters} />
              </TeachingBox>
              <TeachingBox
                Icon={Lightbulb}
                iconTone="text-emerald-600"
                step={2}
                title="بازخوانیِ شهودی — با یک مثالِ روزمره"
                className={BOX.emerald}
              >
                <RichText content={content.intuitive_rebuild} />
              </TeachingBox>
              <TeachingBox
                Icon={KeyRound}
                iconTone="text-amber-600"
                step={3}
                title="کلیدِ ذهنیِ ماندگار"
                className={`${BOX.amber} font-medium`}
              >
                <RichText content={content.memory_key} />
              </TeachingBox>
            </>
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
                title="کلید مفهومی و نکتهٔ ماندگار"
                className={`${BOX.amber} font-medium`}
              >
                <RichText content={content.golden_tip} />
              </TeachingBox>
            </>
          )}
        </div>

        {!state.loading && (
          <footer className="shrink-0 px-5 pb-5">
            <button
              type="button"
              onClick={onClose}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-brand-900 to-brand-800 px-6 py-3 text-sm font-bold text-white shadow-soft transition-all hover:from-brand-950 hover:to-brand-900 hover:shadow-lift"
            >
              <CheckCircle2 className="h-4 w-4" />
              متوجه شدم، کاملاً جا افتاد!
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

/**
 * فهرستِ آکاردئونیِ ده سؤال — جایگزینِ گریدِ ۱۰ کارتِ هم‌شکل.
 *
 * چرا: ده کارتِ بزرگِ هماندازه، صفحه را به دو ستونِ بلند تبدیل می‌کرد که
 * دانش‌آموز در آن گم می‌شد؛ وضعیت‌ها هم فقط داخلِ هر کارت دیده می‌شدند.
 * این‌جا اول یک **نقشهٔ وضعیت** در یک ردیف می‌آید (ده سؤال در یک نگاه)، بعد
 * هر سؤال با باز شدن، جزئیات و دکمهٔ معلم را نشان می‌دهد.
 *
 * فقط یک سؤال هم‌زمان باز است: تمرکز روی «همین یکی» می‌ماند.
 */
function QuestionRow({ q, index, open, onToggle, onOpenTutor }) {
  const tone = toneOf(q?.status)
  const ToneIcon = tone.Icon
  const order = Number(q?.order) || index + 1
  const hasOptions = Array.isArray(q?.options) && q.options.length > 0
  const pickedIdx = Number.isInteger(Number(q?.selected_option_index))
    ? Number(q.selected_option_index)
    : null
  const selectedText =
    pickedIdx !== null ? rawText(q?.selected_option_text ?? q?.options?.[pickedIdx]) : ''
  const answer = rawText(q?.response)
  const insight = rawText(q?.diagnostic_insight)

  return (
    <li className="overflow-hidden rounded-xl border border-slate-200/80 bg-white transition-colors">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-3.5 py-3 text-right transition-colors hover:bg-slate-50/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-400"
      >
        {/* شماره */}
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-[11px] font-black text-ink-soft">
          {faNum(order)}
        </span>

        {/* وضعیت: آیکون + متن، نه فقط رنگ */}
        <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-black ${tone.badge}`}>
          <ToneIcon className="ml-1 inline h-3 w-3 align-[-2px]" aria-hidden="true" />
          {tone.label}
        </span>

        {/* خلاصهٔ سؤال */}
        <span className="min-w-0 flex-1 truncate text-[12px] font-bold text-ink">
          {rawText(q?.question_text) || 'متنِ سؤال ثبت نشده'}
        </span>

        <ChevronDown
          className={`h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200 ${
            open ? 'rotate-180' : ''
          }`}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="border-t border-slate-100 bg-slate-50/40 px-3.5 py-3.5">
          <p className="text-justify text-right text-[12px] font-bold leading-7 text-ink">
            {rawText(q?.question_text)}
          </p>

          {/* پاسخِ دانش‌آموز */}
          <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
            <span className="text-[10px] font-black text-ink-faint">پاسخِ تو</span>
            <p className="mt-1 text-justify text-right text-[12px] leading-7 text-ink-soft">
              {selectedText || answer || '— پاسخی ثبت نشده بود —'}
            </p>
            {hasOptions && pickedIdx !== null && (
              <p className="mt-1 text-[10px] text-ink-faint">
                گزینهٔ {faNum(pickedIdx + 1)} از {faNum(q.options.length)}
              </p>
            )}
          </div>

          {insight && (
            <div className="mt-2 rounded-lg border-r-2 border-emerald-400 bg-primary-soft/50 p-3">
              <span className="text-[10px] font-black text-primary-deep">دیدگاهِ فهم‌یار</span>
              <p className="mt-1 text-justify text-right text-[12px] leading-7 text-ink">
                {insight}
              </p>
            </div>
          )}

          <button
            type="button"
            onClick={onOpenTutor}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-black text-white transition hover:bg-indigo-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
          >
            <Sparkles className="h-3.5 w-3.5 text-amber-300" />
            می‌خوای این گره رو باز کنیم؟ (آموزش زنده)
          </button>
        </div>
      )}
    </li>
  )
}

export default function DetailedQuestions({ questions = [], sessionId }) {
  const [open, setOpen] = useState(false)
  const [target, setTarget] = useState(null)
  const [expanded, setExpanded] = useState(null)

  const openFor = (q, order) => {
    setTarget({ type: 'question', q, order })
    setOpen(true)
  }

  const statusOf = (q) => toneOf(q?.status)

  if (!questions.length) {
    return <p className="text-[13px] text-ink-faint">سؤالی ثبت نشده است.</p>
  }

  return (
    <>
      {/* ── نقشهٔ وضعیت: ده سؤال در یک نگاه ── */}
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        {questions.map((q, i) => {
          const tone = statusOf(q)
          return (
            <button
              key={q.question_id ?? i}
              type="button"
              onClick={() => setExpanded(expanded === i ? null : i)}
              title={`سؤال ${faNum(Number(q?.order) || i + 1)} — ${tone.label}`}
              aria-label={`سؤال ${faNum(Number(q?.order) || i + 1)} — ${tone.label}`}
              className={`flex h-8 w-8 items-center justify-center rounded-lg text-[11px] font-black transition-transform hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${tone.badge} ${
                expanded === i ? 'ring-2 ring-slate-900/20' : ''
              }`}
            >
              {faNum(Number(q?.order) || i + 1)}
            </button>
          )
        })}
      </div>

      <ul className="space-y-1.5">
        {questions.map((q, i) => (
          <QuestionRow
            key={q.question_id ?? i}
            q={q}
            index={i}
            open={expanded === i}
            onToggle={() => setExpanded(expanded === i ? null : i)}
            onOpenTutor={() => openFor(q, Number(q?.order) || i + 1)}
          />
        ))}
      </ul>

      <LiveTutorModal
        open={open}
        target={target}
        sessionId={sessionId}
        onClose={() => setOpen(false)}
      />
    </>
  )
}
