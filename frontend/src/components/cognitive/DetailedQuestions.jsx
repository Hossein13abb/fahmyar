/**
 * «معلمِ هوشمند فهم‌یار» — کارتِ سؤال + کشوی تدریسِ تعاملی (فاز ۱۲)
 *
 * دو چیز در این فایل است:
 *   ۱. <QuestionCard> — کارتِ ماژولار با نوارِ وضعیتِ رنگی، سربرگ، جعبهٔ
 *      «پاسخِ دانش‌آموز» و «دیدگاهِ تشخیصی».
 *   ۲. <TutorModal> — مودالِ وسط‌چینِ تدریس با سه بخش (ریشهٔ گیر، اصلِ
 *      داستان، رمزِ طلایی).
 *   ۳. <ContradictionTutorModal> — همان مودال برای حلِ تناقضِ «شکارِ تناقض».
 *
 * اصلِ طراحی: این کامپوننت **هیچ داده‌ای از خودش نمی‌سازد**. هر متن از
 * `tutor_teaching` می‌آید که بک‌اند در همان فراخوانیِ اولِ ارزیابی تولید
 * کرده است؛ پس باز کردنِ کشو هیچ درخواستی به سرور نمی‌فرستد.
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  GraduationCap,
  KeyRound,
  Lightbulb,
  MessageCircleQuestion,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
} from 'lucide-react'
import MathText from '../MathText'

const faNum = (v) => String(v ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

const STAGE_NAMES = [
  'فلسفه و تصویر کلان',
  'تستِ لایهٔ نقاب',
  'مونتاژ ذهنی و دستکاری',
  'عیب‌یابیِ ساعتِ خراب',
  'چالشِ فاینمن',
]

/** وضعیت → رنگ، برچسب و آیکون. کلیدها همان چهار حالتِ استانداردِ بک‌اند. */
const TONE = {
  CORRECT: {
    rail: 'bg-emerald-500',
    ring: 'ring-emerald-200/70',
    soft: 'bg-emerald-50/50',
    head: 'text-emerald-900',
    badge: 'bg-emerald-100 text-emerald-800 ring-emerald-300',
    Icon: CheckCircle2,
    label: 'درست',
    question: 'این گره را باز کردی — می‌خواهی عمیق‌ترش کنیم؟',
  },
  HALF_CORRECT: {
    rail: 'bg-amber-400',
    ring: 'ring-amber-200/70',
    soft: 'bg-amber-50/50',
    head: 'text-amber-900',
    badge: 'bg-amber-100 text-amber-900 ring-amber-300',
    Icon: AlertTriangle,
    label: 'نیمه‌درست',
    question: 'نصفِ راه را رفتی — بقیه‌اش را با هم ببندیم؟',
  },
  WRONG: {
    rail: 'bg-rose-400',
    ring: 'ring-rose-200/70',
    soft: 'bg-rose-50/50',
    head: 'text-rose-900',
    badge: 'bg-rose-100 text-rose-800 ring-rose-300',
    Icon: AlertTriangle,
    label: 'نادرست',
    question: 'اینجا گره خوردیم — می‌خواهی بهت توضیح بدم؟',
  },
  INSUFFICIENT_EVIDENCE: {
    rail: 'bg-slate-300',
    ring: 'ring-slate-200/70',
    soft: 'bg-slate-50/60',
    head: 'text-slate-700',
    badge: 'bg-slate-100 text-slate-600 ring-slate-300',
    Icon: BookOpen,
    label: 'شواهد ناکافی',
    question: 'اینجا پاسخی نرسید — می‌خواهی از صفر توضیح بدهم؟',
  },
}

const toneOf = (status) => TONE[String(status ?? '').toUpperCase()] ?? TONE.INSUFFICIENT_EVIDENCE

const rawStudentAnswer = (value) => String(value ?? '').trim()

/** متنِ چندخطی با احترام به `$...$` — همان رندرِ ریاضیِ بقیهٔ کارنامه. */
function RichText({ content, className = '' }) {
  const text = String(content ?? '').trim()
  if (!text) return null
  return (
    <div className={`math-content whitespace-pre-line ${className}`}>
      <MathText content={text} />
    </div>
  )
}

export function QuestionCard({ q, index, onOpenTutor }) {
  const tone = toneOf(q?.status)
  const ToneIcon = tone.Icon
  const stage = Number(q?.stage) || Math.min(5, Math.floor((Number(q?.order) ?? index + 1) - 1) / 2 + 1)
  const order = Number(q?.order) || index + 1
  const questionText = String(q?.question_text ?? '').trim()
  const answerSummary = String(q?.student_answer_summary ?? '').trim()
  const insight = String(q?.diagnostic_insight ?? '').trim()
  const studentAnswer = rawStudentAnswer(q?.response)
  const hasOptions = Array.isArray(q?.options) && q.options.length > 0
  const pickedIdx = Number.isInteger(Number(q?.selected_option_index))
    ? Number(q.selected_option_index)
    : null
  const selectedText = pickedIdx !== null
    ? String(q?.selected_option_text ?? q?.options?.[pickedIdx] ?? '').trim()
    : ''

  const tutor = q?.tutor_teaching ?? {}
  const hasTutor = Boolean(
    tutor.misconception_root || tutor.intuitive_explanation || tutor.golden_tip,
  )

  return (
    <article
      className={`group relative overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ${tone.ring} transition-all duration-300 hover:shadow-md`}
    >
      {/* نوارِ وضعیتِ رنگی */}
      <span className={`absolute inset-y-0 right-0 w-1.5 ${tone.rail}`} aria-hidden="true" />

      {/* ── سربرگ کارت ── */}
      <header className={`flex flex-wrap items-center justify-between gap-2 px-4 py-3 pr-6 ${tone.soft}`}>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-[12px] font-black text-brand-900 ring-1 ring-brand-100 tabular-nums">
            {faNum(order)}
          </span>
          <div className="min-w-0">
            <p className="text-[12px] font-black text-brand-950">
              سؤال {faNum(order)} <span className="text-slate-400">از {faNum(10)}</span>
            </p>
            <p className="text-[10px] font-bold text-slate-500">
              مرحلهٔ {faNum(stage)}: {STAGE_NAMES[stage - 1] ?? 'زنجیرهٔ فهم'}
            </p>
          </div>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-black ring-1 ${tone.badge}`}
        >
          <ToneIcon className="h-3 w-3" strokeWidth={2.4} />
          {tone.label}
        </span>
      </header>

      <div className="px-4 py-3.5 pr-6">
        {/* صورتِ سؤال */}
        {questionText && (
          <RichText
            content={questionText}
            className="rounded-xl bg-slate-50/80 px-3 py-2 text-[12px] font-bold leading-7 text-slate-600"
          />
        )}

        {/* ── جعبهٔ «پاسخِ دانش‌آموز» ── */}
        <div className="mt-3 rounded-xl border border-brand-100 bg-brand-50/40 px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-[10px] font-black tracking-wide text-brand-800">
            <MessageCircleQuestion className="h-3.5 w-3.5" />
            پاسخِ تو
          </p>
          {hasOptions ? (
            pickedIdx === null ? (
              <p className="mt-1 text-[12px] font-bold text-slate-500">بدون پاسخ</p>
            ) : (
              <div className="mt-1 text-[12px] leading-7 text-slate-700">
                گزینهٔ {faNum(pickedIdx + 1)}:{' '}
                <span className="math-inline font-black text-brand-950">
                  <MathText content={selectedText} />
                </span>
              </div>
            )
          ) : (
            <RichText
              content={studentAnswer || 'بدون پاسخ'}
              className={`mt-1 text-[12px] leading-7 ${
                studentAnswer ? 'text-slate-700' : 'text-slate-400'
              }`}
            />
          )}
        </div>

        {/* ── «دیدگاهِ تشخیصیِ فهم‌یار» — نقطه‌ای و کوتاه ── */}
        {(insight || answerSummary) && (
          <div className="mt-2.5 flex items-start gap-2 rounded-xl bg-slate-50/70 px-3 py-2.5">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
            <div className="min-w-0">
              <p className="text-[10px] font-black text-slate-500">دیدگاهِ تشخیصیِ فهم‌یار</p>
              {insight && (
                <RichText content={insight} className="mt-0.5 text-[12px] leading-6 text-brand-950" />
              )}
              {answerSummary && answerSummary !== insight && (
                <p className="mt-1 text-[11px] leading-6 text-slate-500">
                  {String(answerSummary).replace(/\$/g, '')}
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── دکمهٔ معلم ── */}
        <button
          type="button"
          onClick={() => onOpenTutor?.(q, order)}
          disabled={!hasTutor}
          className={`mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-[12px] font-black transition-all duration-200 ${
            hasTutor
              ? 'bg-brand-700 text-white shadow-sm hover:-translate-y-0.5 hover:bg-brand-800 hover:shadow-md active:translate-y-0'
              : 'cursor-not-allowed bg-slate-100 text-slate-400'
          }`}
        >
          <GraduationCap className="h-4 w-4" />
          {hasTutor ? tone.question : 'توضیحی برای این سؤال ثبت نشده'}
        </button>
      </div>
    </article>
  )
}

/** آیکون و لحنِ هر بخشِ مودال — یک‌جا، تا هر دو حالت از یک زبانِ بصری بیایند. */
const SECTION_STYLE = {
  rose: {
    card: 'border-rose-200/80 bg-gradient-to-br from-rose-50 to-rose-50/40',
    iconBox: 'bg-white text-rose-500 ring-rose-200 shadow-rose-100',
    title: 'text-rose-900',
    chip: 'bg-rose-100 text-rose-700',
  },
  brand: {
    card: 'border-brand-200/80 bg-gradient-to-br from-brand-50 to-brand-50/30',
    iconBox: 'bg-white text-brand-600 ring-brand-200 shadow-brand-100',
    title: 'text-brand-950',
    chip: 'bg-brand-100 text-brand-800',
  },
  amber: {
    card: 'border-amber-200/80 bg-gradient-to-br from-amber-50 to-amber-50/40',
    iconBox: 'bg-white text-amber-500 ring-amber-200 shadow-amber-100',
    title: 'text-amber-900',
    chip: 'bg-amber-100 text-amber-800',
  },
}

/** یک باکسِ کارت‌مانندِ داخلِ مودال. */
function TutorBox({ Icon, badge, title, tone, children }) {
  const st = SECTION_STYLE[tone]
  return (
    <section className={`rounded-2xl border p-4 shadow-sm sm:p-5 ${st.card}`}>
      <div className="flex items-start gap-3">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ring-1 shadow-sm ${st.iconBox}`}
        >
          <Icon className="h-[18px] w-[18px]" strokeWidth={2.2} />
        </span>
        <div className="min-w-0 flex-1">
          <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-black ${st.chip}`}>
            {badge}
          </span>
          <h3 className={`mt-1 text-[14px] font-black leading-6 ${st.title}`}>{title}</h3>
        </div>
      </div>
      <div className="mt-3 text-[13px] leading-8 text-slate-700 sm:text-[13.5px]">{children}</div>
    </section>
  )
}

/**
 * شِلِ مشترکِ مودالِ معلم — وسطِ صفحه، شیشه‌ای، با انیمیشنِ scale+fade.
 *
 * هر دو حالت (تدریسِ سؤال و حلِ تناقض) از همین می‌گذرند تا تجربه یکدست بماند.
 * رندر با `createPortal` روی `document.body` است: بدونِ آن، هر والدِ
 * `transform`دار مرجعِ `fixed` می‌شود و مودال به کارت می‌چسبد نه به پنجره.
 */
function TutorModalShell({ open, titleId, header, children, footer, onClose }) {
  const [shown, setShown] = useState(false)
  const closeRef = useRef(null)

  useEffect(() => {
    if (!open) {
      setShown(false)
      return undefined
    }
    // یک فریم بعد وارد شو تا transition واقعاً اجرا شود.
    const raf = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(raf)
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      {/* پردهٔ شیشه‌ایِ پشت */}
      <button
        type="button"
        aria-label="بستن"
        onClick={onClose}
        className={`absolute inset-0 bg-black/60 backdrop-blur-md transition-opacity duration-300 ${
          shown ? 'opacity-100' : 'opacity-0'
        }`}
      />

      {/* بدنهٔ مودال */}
      <div
        className={`relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl ring-1 ring-black/5 transition-all duration-300 ease-out ${
          shown ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        }`}
      >
        <header className="relative shrink-0 overflow-hidden border-b border-slate-100 bg-gradient-to-l from-brand-50 via-white to-brand-50/40 px-5 py-4 sm:px-6 sm:py-5">
          <div className="pointer-events-none absolute -left-8 -top-10 h-32 w-32 rounded-full bg-brand-100/40 blur-2xl" />
          <div className="relative flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-700 text-white shadow-md shadow-brand-200">
                <GraduationCap className="h-5 w-5" strokeWidth={2.2} />
              </span>
              <div className="min-w-0">{header}</div>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="بستنِ پنجرهٔ معلم"
              className="shrink-0 rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </header>

        {/* اسکرولِ نرمِ داخلی */}
        <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6 sm:py-5">
          {children}
        </div>

        {footer && (
          <footer className="shrink-0 border-t border-slate-100 bg-slate-50/60 px-4 py-3 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )

  return typeof document === 'undefined' ? modal : createPortal(modal, document.body)
}

/** مودالِ تدریسِ یک سؤال — سه بخش: ریشهٔ گیر، اصلِ داستان، رمزِ طلایی. */
export function TutorModal({ open, q, order, onClose }) {
  const tone = toneOf(q?.status)
  const stage =
    Number(q?.stage) || Math.min(5, Math.floor(((Number(q?.order) || 1) - 1) / 2) + 1)
  const tutor = q?.tutor_teaching ?? {}
  const studentAnswer = rawStudentAnswer(q?.response)
  const hasOptions = Array.isArray(q?.options) && q.options.length > 0
  const pickedIdx = Number.isInteger(Number(q?.selected_option_index))
    ? Number(q.selected_option_index)
    : null

  const header = (
    <>
      <p className="text-[10px] font-black text-brand-700">
        معلمِ خصوصیِ فهم‌یار · سؤال {faNum(order)}
      </p>
      <h2 id="tutor-title" className="mt-0.5 text-[17px] font-black leading-7 text-brand-950 sm:text-[19px]">
        بیا این گره رو با هم باز کنیم!
      </h2>
      <p className="mt-0.5 text-[11px] font-bold text-slate-500">
        مرحلهٔ {faNum(stage)}: {STAGE_NAMES[stage - 1]}
      </p>
    </>
  )

  const footer = (
    <button
      type="button"
      onClick={onClose}
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 py-3 text-[13px] font-black text-white shadow-sm transition hover:bg-brand-800 active:scale-[0.99]"
    >
      <CheckCircle2 className="h-4 w-4" />
      متوجه شدم!
      <ArrowLeft className="h-4 w-4" />
    </button>
  )

  return (
    <TutorModalShell open={open} titleId="tutor-title" header={header} footer={footer} onClose={onClose}>
      {/* صورتِ سؤال + پاسخِ دانش‌آموز */}
      <div className="grid gap-2 sm:grid-cols-2">
        {String(q?.question_text ?? '').trim() && (
          <div className="rounded-2xl bg-slate-50 px-4 py-3 ring-1 ring-slate-100">
            <p className="text-[10px] font-black text-slate-500">صورتِ سؤال</p>
            <RichText
              content={q.question_text}
              className="mt-1 text-[12px] font-bold leading-7 text-slate-700"
            />
          </div>
        )}
        <div className={`rounded-2xl bg-white px-4 py-3 ring-1 ${tone.ring}`}>
          <p className="text-[10px] font-black text-slate-500">پاسخِ تو</p>
          {hasOptions ? (
            pickedIdx === null ? (
              <p className="mt-1 text-[12px] font-bold text-slate-400">بدون پاسخ</p>
            ) : (
              <div className="mt-1 text-[12px] leading-7 text-slate-700">
                گزینهٔ {faNum(pickedIdx + 1)}:{' '}
                <span className="math-inline font-black text-brand-950">
                  <MathText
                    content={String(q.selected_option_text ?? q.options?.[pickedIdx] ?? '')}
                  />
                </span>
              </div>
            )
          ) : (
            <RichText
              content={studentAnswer || 'بدون پاسخ'}
              className={`mt-1 text-[12px] leading-7 ${
                studentAnswer ? 'text-slate-700' : 'text-slate-400'
              }`}
            />
          )}
        </div>
      </div>

      <TutorBox
        Icon={MessageCircleQuestion}
        tone="rose"
        badge="بخش ۱"
        title="کجای ماجرا گیر کردی؟"
      >
        <RichText content={tutor.misconception_root} />
      </TutorBox>

      <TutorBox Icon={BookOpen} tone="brand" badge="بخش ۲" title="اصلِ داستان به زبانِ ساده">
        <RichText content={tutor.intuitive_explanation} />
      </TutorBox>

      <TutorBox Icon={KeyRound} tone="amber" badge="بخش ۳" title="رمزِ طلاییِ ساعت‌ساز">
        <RichText content={tutor.golden_tip} />
      </TutorBox>

      <p className="flex items-start gap-1.5 px-1 text-[10px] font-bold leading-5 text-slate-400">
        <Lightbulb className="mt-0.5 h-3 w-3 shrink-0" />
        این توضیح با همان ارزیابیِ آزمون ساخته شده است — نه یک پاسخِ آمادهٔ تکراری؛
        همان‌جا که خودت گیر کردی.
      </p>
    </TutorModalShell>
  )
}

/**
 * مودالِ «حلِ تناقض» — همان شِل، ولی محتوایش سه سؤالِ متفاوت است:
 * چرا این تناقض شکل گرفت، پلِ اتصالِ دو مفهوم، و سپرِ آزمون.
 */
export function ContradictionTutorModal({ open, finding, onClose }) {
  const res = finding?.tutor_resolution ?? {}
  const header = (
    <>
      <p className="text-[10px] font-black text-amber-700">معلمِ خصوصیِ فهم‌یار · شکارِ تناقض</p>
      <h2 id="tutor-title" className="mt-0.5 text-[17px] font-black leading-7 text-brand-950 sm:text-[19px]">
        بیا این تناقض رو با هم حل کنیم!
      </h2>
      <p className="mt-0.5 text-[11px] font-bold text-slate-500">
        {finding?.contradiction_title || finding?.title || 'دو حرفت با هم نمی‌خوانند'}
      </p>
    </>
  )

  const footer = (
    <button
      type="button"
      onClick={onClose}
      className="flex w-full items-center justify-center gap-2 rounded-xl bg-amber-600 px-4 py-3 text-[13px] font-black text-white shadow-sm transition hover:bg-amber-700 active:scale-[0.99]"
    >
      <CheckCircle2 className="h-4 w-4" />
      قفلش کردم! بریم بعدی
      <ArrowLeft className="h-4 w-4" />
    </button>
  )

  return (
    <TutorModalShell open={open} titleId="tutor-title" header={header} footer={footer} onClose={onClose}>
      {String(finding?.description ?? '').trim() && (
        <div className="rounded-2xl bg-slate-50 px-4 py-3 ring-1 ring-slate-100">
          <p className="text-[10px] font-black text-slate-500">آنچه در کارنامه دیدی</p>
          <p className="mt-1 text-[12px] font-medium leading-7 text-slate-700">
            {finding.description}
          </p>
        </div>
      )}

      <TutorBox Icon={Sparkles} tone="rose" badge="بخش ۱" title="چرا این تناقض در ذهنت شکل گرفت؟">
        <RichText content={res.why_it_happened} />
      </TutorBox>

      <TutorBox Icon={Workflow} tone="brand" badge="بخش ۲" title="پلِ اتصالِ این دو مفهوم">
        <RichText content={res.how_to_connect_bridge} />
      </TutorBox>

      <TutorBox Icon={ShieldCheck} tone="amber" badge="بخش ۳" title="چطور سرِ آزمون در این دام نیفتیم؟">
        <RichText content={res.exam_shield_tip} />
      </TutorBox>
    </TutorModalShell>
  )
}

/** بخشِ «تحلیل تفصیلی» با گریدِ کارت‌ها و کشوی معلم. */
export default function DetailedQuestions({ questions = [] }) {
  const [tutorOpen, setTutorOpen] = useState(false)
  const [activeQ, setActiveQ] = useState(null)
  const [activeOrder, setActiveOrder] = useState(null)

  const openTutor = (q, order) => {
    setActiveQ(q)
    setActiveOrder(order)
    setTutorOpen(true)
  }

  if (!questions.length) {
    return <p className="text-[13px] text-slate-500">سؤالی ثبت نشده است.</p>
  }

  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        {questions.map((q, i) => (
          <QuestionCard key={q.question_id ?? i} q={q} index={i} onOpenTutor={openTutor} />
        ))}
      </div>
      <TutorModal
        open={tutorOpen}
        q={activeQ}
        order={activeOrder}
        onClose={() => setTutorOpen(false)}
      />
    </>
  )
}
