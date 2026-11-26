/**
 * اجزای بصریِ کارنامه — نسخهٔ نسلِ جدید (فاز ۱۴)
 *
 * سه چیز در این فایل:
 *   ۱. <QuestionCard>  — کارتِ گلس‌مورفیکِ هر سؤال با نوارِ گرادیانتی
 *   ۲. <ContradictionCard> — کارتِ «شکار تناقض» با حاشیهٔ درخشان
 *   ۳. <LiveTutorModal> — مودالِ مشترکِ درلحظه (سؤال و تناقض)
 *
 * همهٔ متن‌های آموزشی از `POST /api/tutor/explain` می‌آیند — هیچ متنی از
 * پیش در پاسخِ کارنامه تولید نمی‌شود.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  GitCompareArrows,
  GraduationCap,
  KeyRound,
  Lightbulb,
  MessageCircleQuestion,
  ShieldCheck,
  Sparkles,
  Target,
  Workflow,
  Wrench,
} from 'lucide-react'
import client from '../../api/client'
import MathText from '../MathText'
import TutorModalShell from './TutorModalShell'

const faNum = (v) => String(v ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

export const STAGE_NAMES = [
  'فلسفه و تصویر کلان',
  'تستِ لایهٔ نقاب',
  'مونتاژ ذهنی و دستکاری',
  'عیب‌یابیِ ساعتِ خراب',
  'چالشِ فاینمن',
]

// ─────────────────────────── رنگ‌بندیِ وضعیت ───────────────────────────
export const TONE = {
  CORRECT: {
    rail: 'from-emerald-400 via-emerald-500 to-teal-500',
    glow: 'shadow-emerald-200/50',
    ring: 'ring-emerald-200/70',
    chip: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/25',
    label: 'درست',
    Icon: CheckCircle2,
    cta: 'درست رفتی! می‌خوای عمیق‌ترش کنیم؟',
  },
  HALF_CORRECT: {
    rail: 'from-amber-300 via-amber-400 to-orange-400',
    glow: 'shadow-amber-200/50',
    ring: 'ring-amber-200/70',
    chip: 'bg-amber-500/10 text-amber-700 border-amber-500/25',
    label: 'نیمه‌درست',
    Icon: AlertTriangle,
    cta: 'نصفِ راه را رفتی! بقیه‌اش رو با هم ببندیم؟',
  },
  WRONG: {
    rail: 'from-rose-400 via-rose-500 to-pink-500',
    glow: 'shadow-rose-200/50',
    ring: 'ring-rose-200/70',
    chip: 'bg-rose-500/10 text-rose-700 border-rose-500/25',
    label: 'نادرست',
    Icon: AlertTriangle,
    cta: 'اینجا گره خوردیم! می‌خوای بازش کنیم؟',
  },
  INSUFFICIENT_EVIDENCE: {
    rail: 'from-slate-300 via-slate-400 to-slate-500',
    glow: 'shadow-slate-200/50',
    ring: 'ring-slate-200/70',
    chip: 'bg-slate-500/10 text-slate-600 border-slate-500/25',
    label: 'شواهد ناکافی',
    Icon: BookOpen,
    cta: 'از صفر با هم شروع کنیم؟',
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
    pickedIdx !== null
      ? rawText(q?.selected_option_text ?? q?.options?.[pickedIdx])
      : ''

  return (
    <article
      className={`group relative flex flex-col overflow-hidden rounded-3xl bg-white/80 shadow-lg backdrop-blur-sm ring-1 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl ${tone.ring} ${tone.glow}`}
    >
      {/* نوارِ گرادیانتیِ وضعیت */}
      <span
        className={`absolute inset-y-0 right-0 w-1.5 bg-gradient-to-b ${tone.rail}`}
        aria-hidden="true"
      />

      <header className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 pr-6">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-700 to-brand-900 text-[12px] font-black text-white shadow-sm tabular-nums">
            {faNum(order)}
          </span>
          <div className="min-w-0">
            <span
              className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-black ${tone.chip}`}
            >
              مرحلهٔ {faNum(stage)} · {STAGE_NAMES[stage - 1] ?? 'زنجیرهٔ فهم'}
            </span>
          </div>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-black ${tone.chip}`}
        >
          <ToneIcon className="h-3 w-3" strokeWidth={2.5} />
          {tone.label}
        </span>
      </header>

      <div className="flex flex-1 flex-col gap-2.5 px-4 pb-4 pr-6">
        {/* سؤال */}
        {rawText(q?.question_text) && (
          <div className="rounded-2xl bg-slate-50/90 px-3.5 py-2.5 ring-1 ring-slate-100">
            <p className="flex items-center gap-1.5 text-[10px] font-black text-slate-400">
              <MessageCircleQuestion className="h-3.5 w-3.5" /> سؤال
            </p>
            <RichText
              content={q.question_text}
              className="mt-1 text-[12.5px] font-bold leading-7 text-slate-700"
            />
          </div>
        )}

        {/* پاسخِ تو — باکسِ کوتیشن */}
        <div className="relative rounded-2xl border-r-[3px] border-brand-400/70 bg-brand-50/50 px-3.5 py-2.5">
          <p className="text-[10px] font-black text-brand-800">پاسخِ تو</p>
          {hasOptions ? (
            pickedIdx === null ? (
              <p className="mt-1 text-[12px] font-bold text-slate-400">بدون پاسخ</p>
            ) : (
              <div className="mt-1 text-[12.5px] leading-7 text-slate-700">
                گزینهٔ {faNum(pickedIdx + 1)}:{' '}
                <span className="math-inline font-black text-brand-950">
                  <MathText content={selectedText} />
                </span>
              </div>
            )
          ) : (
            <RichText
              content={rawText(q?.response) || 'بدون پاسخ'}
              className={`mt-1 text-[12.5px] leading-7 ${
                rawText(q?.response) ? 'text-slate-700' : 'text-slate-400'
              }`}
            />
          )}
        </div>

        {/* تحلیلِ تشخیصی */}
        {rawText(q?.diagnostic_insight) && (
          <div className="flex items-start gap-2 px-0.5">
            <Sparkles className="mt-1 h-3.5 w-3.5 shrink-0 text-brand-500" />
            <div className="min-w-0">
              <p className="text-[10px] font-black text-slate-400">تحلیلِ تشخیصی</p>
              <RichText
                content={q.diagnostic_insight}
                className="mt-0.5 text-[12px] leading-6 text-brand-950"
              />
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={() => onOpen?.(q, order)}
          className="mt-auto flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-brand-700 to-brand-600 px-4 py-2.5 text-[12px] font-black text-white shadow-md shadow-brand-200/60 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-brand-300/60 active:translate-y-0"
        >
          <Sparkles className="h-4 w-4" />
          می‌خوای این گره رو باز کنیم؟ (آموزش زنده)
        </button>
      </div>
    </article>
  )
}

// ═══════════════════════ کارتِ شکارِ تناقض ═══════════════════════
const FINDING_LOOK = {
  CONTRADICTION: {
    label: 'تناقض عمیق',
    wrap: 'from-rose-500/40 via-amber-400/30 to-emerald-400/30',
    chip: 'bg-rose-500/15 text-rose-200 border-rose-400/40',
    pulse: true,
  },
  JARGON_VIOLATION: {
    label: 'زندانِ اصطلاح',
    wrap: 'from-amber-400/40 via-orange-400/25 to-emerald-400/25',
    chip: 'bg-amber-500/15 text-amber-100 border-amber-400/40',
    pulse: false,
  },
  BLUFF_DETECTED: {
    label: 'بلوفِ شناخته‌شده',
    wrap: 'from-rose-600/35 via-fuchsia-500/25 to-emerald-400/25',
    chip: 'bg-rose-600/15 text-rose-100 border-rose-400/40',
    pulse: false,
  },
  SYNERGY: {
    label: 'هم‌افزایی',
    wrap: 'from-emerald-500/40 via-teal-400/25 to-cyan-400/25',
    chip: 'bg-emerald-500/15 text-emerald-100 border-emerald-400/40',
    pulse: false,
  },
  SLIP_RESOLVED: {
    label: 'حل‌شده در بازپرسی',
    wrap: 'from-sky-500/40 via-cyan-400/25 to-emerald-400/25',
    chip: 'bg-sky-500/15 text-sky-100 border-sky-400/40',
    pulse: false,
  },
}

export function ContradictionCard({ finding, onTeach, busy = false }) {
  const look = FINDING_LOOK[String(finding?.type ?? '').toUpperCase()] ?? FINDING_LOOK.SYNERGY
  const isContradiction = String(finding?.type ?? '').toUpperCase() === 'CONTRADICTION'

  return (
    <div
      className={`group relative overflow-hidden rounded-3xl bg-gradient-to-br p-[1.5px] shadow-lg transition-all duration-300 hover:shadow-2xl ${look.wrap}`}
    >
      <div className="relative h-full rounded-[22px] bg-slate-950/75 p-4 backdrop-blur-xl">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-black ${look.chip}`}
          >
            {look.pulse && (
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
              </span>
            )}
            {look.label}
          </span>
          <p className="min-w-0 text-[13px] font-black text-white drop-shadow-sm">
            {finding?.contradiction_title || finding?.title}
          </p>
        </div>

        {rawText(finding?.description) && (
          <p className="mt-2 text-[12px] font-medium leading-7 text-slate-100">
            {finding.description}
          </p>
        )}

        {rawText(finding?.resolution) && (
          <p className="mt-2 rounded-xl bg-emerald-400/10 px-3 py-2 text-[11px] font-bold leading-6 text-emerald-200 ring-1 ring-emerald-400/20">
            توضیحِ خودت: {finding.resolution}
          </p>
        )}

        {isContradiction && (
          <button
            type="button"
            onClick={() => onTeach?.(finding)}
            disabled={busy}
            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-amber-400 via-amber-500 to-orange-500 px-4 py-2.5 text-[12px] font-black text-slate-900 shadow-lg shadow-amber-500/25 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-amber-400/40 active:translate-y-0 disabled:opacity-60"
          >
            <Sparkles className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
            {busy ? 'معلم دارد تحلیل می‌کند...' : 'چرا این دو تا حرفم با هم نمی‌خوند؟ (تحلیل زنده با معلم)'}
          </button>
        )}
      </div>
    </div>
  )
}

// ═════════════════════ مودالِ تدریسِ درلحظه ═════════════════════
function StepBox({ Icon, badge, title, tone, children }) {
  const styles = {
    amber: {
      card: 'border-amber-200/80 bg-gradient-to-br from-amber-50 via-white to-amber-50/50',
      box: 'bg-amber-100 text-amber-600 ring-amber-200',
      chip: 'bg-amber-100 text-amber-800',
      title: 'text-amber-950',
    },
    brand: {
      card: 'border-brand-200/80 bg-gradient-to-br from-brand-50 via-white to-brand-50/40',
      box: 'bg-brand-100 text-brand-700 ring-brand-200',
      chip: 'bg-brand-100 text-brand-800',
      title: 'text-brand-950',
    },
    gold: {
      card: 'border-yellow-300/70 bg-gradient-to-br from-yellow-50 via-amber-50 to-yellow-100/60 shadow-inner',
      box: 'bg-yellow-200/80 text-yellow-700 ring-yellow-300',
      chip: 'bg-yellow-200/70 text-yellow-900',
      title: 'text-yellow-950',
    },
    rose: {
      card: 'border-rose-200/80 bg-gradient-to-br from-rose-50 via-white to-rose-50/50',
      box: 'bg-rose-100 text-rose-600 ring-rose-200',
      chip: 'bg-rose-100 text-rose-800',
      title: 'text-rose-950',
    },
  }[tone]

  return (
    <section className={`rounded-2xl border p-4 shadow-sm sm:p-5 ${styles.card}`}>
      <div className="flex items-start gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 ${styles.box}`}
        >
          <Icon className="h-[18px] w-[18px]" strokeWidth={2.2} />
        </span>
        <div className="min-w-0 flex-1">
          <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-black ${styles.chip}`}>
            {badge}
          </span>
          <h3 className={`mt-1 text-[14px] font-black leading-6 ${styles.title}`}>{title}</h3>
        </div>
      </div>
      <div className="mt-3 text-[13px] leading-8 text-slate-700 sm:text-[13.5px]">{children}</div>
    </section>
  )
}

/**
 * مودالِ مشترک. محتوا را از اندپوینتِ `/api/tutor/explain` می‌گیرد و تا
 * رسیدنِ پاسخ، اسکلتونِ پالس‌دار نشان می‌دهد.
 */
export function LiveTutorModal({ open, target, sessionId, onClose }) {
  const [state, setState] = useState({ loading: false, error: '', data: null })
  const abort = useRef(null)

  const isContradiction = target?.type === 'contradiction'

  useEffect(() => {
    if (!open || !target) {
      abort.current?.abort?.()
      return undefined
    }
    const ctrl = new AbortController()
    abort.current = ctrl
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
          err?.response?.data?.detail ||
          'نشد به معلم وصل شویم. یک بار دیگر امتحان کن.'
        setState({ loading: false, error: String(msg), data: null })
      })

    return () => ctrl.abort()
  }, [open, target, sessionId, isContradiction])

  const stage = Number(target?.q?.stage) || Math.min(5, Math.floor(((Number(target?.order) || 1) - 1) / 2) + 1)
  const content = state.data?.content ?? {}

  const header = (
    <>
      <p className="text-[10px] font-black text-brand-700">
        معلمِ خصوصیِ فهم‌یار{isContradiction ? ' · شکارِ تناقض' : ` · سؤال ${faNum(target?.order)}`}
      </p>
      <h2
        id="tutor-title"
        className="mt-0.5 text-[17px] font-black leading-7 text-brand-950 sm:text-[19px]"
      >
        {isContradiction ? 'بیا این تناقض رو با هم حل کنیم!' : 'بیا این گره رو با هم باز کنیم!'}
      </h2>
      <p className="mt-0.5 truncate text-[11px] font-bold text-slate-500">
        {isContradiction
          ? state.data?.title || target?.finding?.contradiction_title || target?.finding?.title || '—'
          : `مرحلهٔ ${faNum(stage)}: ${STAGE_NAMES[stage - 1] ?? 'زنجیرهٔ فهم'}`}
      </p>
    </>
  )

  const footer = (
    <button
      type="button"
      onClick={onClose}
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-l from-brand-800 to-brand-600 px-4 py-3 text-[13px] font-black text-white shadow-md shadow-brand-200 transition hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0"
    >
      <CheckCircle2 className="h-4 w-4" />
      فهمیدم! ساعت رو بستم
      <span aria-hidden="true">🚀</span>
      <ArrowLeft className="h-4 w-4" />
    </button>
  )

  return (
    <TutorModalShell
      open={open}
      header={header}
      footer={footer}
      onClose={onClose}
      loading={state.loading}
    >
      {state.error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
          <p className="flex items-center gap-2 text-[13px] font-black text-rose-900">
            <AlertTriangle className="h-4 w-4" /> {state.error}
          </p>
          <p className="mt-1 text-[11px] font-bold leading-6 text-rose-700">
            هیچ داده‌ای از دست نرفت — می‌توانی دوباره امتحان کنی یا به کارنامه برگردی.
          </p>
        </div>
      ) : isContradiction ? (
        <>
          <StepBox Icon={Target} badge="بخش ۱" title="چرا این تناقض در ذهنت شکل گرفت؟" tone="rose">
            <RichText content={content.why_it_happened} />
          </StepBox>
          <StepBox Icon={Workflow} badge="بخش ۲" title="پلِ اتصالِ این دو مفهوم" tone="brand">
            <RichText content={content.how_to_connect_bridge} />
          </StepBox>
          <StepBox Icon={ShieldCheck} badge="بخش ۳" title="چطور سرِ آزمون در این دام نیفتیم؟" tone="gold">
            <RichText content={content.exam_shield_tip} />
          </StepBox>
        </>
      ) : (
        <>
          <StepBox Icon={Target} badge="بخش ۱" title="کجای مسیر لغزیدی؟" tone="rose">
            <RichText content={content.misconception_root} />
          </StepBox>
          <StepBox Icon={BookOpen} badge="بخش ۲" title="اصلِ ماجرا چیه؟" tone="brand">
            <RichText content={content.intuitive_explanation} />
          </StepBox>
          <StepBox Icon={KeyRound} badge="بخش ۳" title="کلیدِ طلاییِ ساعت‌ساز" tone="gold">
            <RichText content={content.golden_tip} />
          </StepBox>
        </>
      )}

      {!state.loading && !state.error && (
        <p className="flex items-start gap-1.5 px-1 text-[10px] font-bold leading-5 text-slate-400">
          <Lightbulb className="mt-0.5 h-3 w-3 shrink-0" />
          این تدریس همین حالا و مخصوصِ همین پاسخ ساخته شد — نه یک متنِ آمادهٔ تکراری.
        </p>
      )}
    </TutorModalShell>
  )
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
    () =>
      questions.map((q, i) => (
        <QuestionCard key={q.question_id ?? i} q={q} index={i} onOpen={openFor} />
      )),
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

export { GraduationCap, GitCompareArrows, Sparkles, Wrench }
