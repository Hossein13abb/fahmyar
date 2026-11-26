/**
 * «معلمِ هوشمند فهم‌یار» — کارتِ سؤال + کشوی تدریسِ تعاملی (فاز ۱۲)
 *
 * دو چیز در این فایل است:
 *   ۱. <QuestionCard> — کارتِ ماژولار با نوارِ وضعیتِ رنگی، سربرگ، جعبهٔ
 *      «پاسخِ دانش‌آموز» و «دیدگاهِ تشخیصی».
 *   ۲. <TutorDrawer> — کشوی نیمه‌صفحهٔ تدریس با سه بخش (ریشهٔ خطا، اصلِ
 *      داستان، نکتهٔ طلایی).
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
  Sparkles,
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

/** یک بخشِ کشو با آیکون و رنگِ اختصاصی. */
function TutorSection({ Icon, step, title, children, tone }) {
  return (
    <section className={`rounded-2xl border p-4 ${tone.card}`}>
      <div className="flex items-center gap-2">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ring-1 ${tone.iconBox}`}>
          <Icon className="h-4 w-4" strokeWidth={2.2} />
        </span>
        <div>
          <p className="text-[10px] font-bold text-slate-400">بخش {faNum(step)}</p>
          <h3 className={`text-[13px] font-black ${tone.title}`}>{title}</h3>
        </div>
      </div>
      <div className="mt-2.5 text-[13px] leading-8 text-slate-700">{children}</div>
    </section>
  )
}

export function TutorDrawer({ open, q, order, onClose }) {
  const [mounted, setMounted] = useState(false)
  const closeRef = useRef(null)

  // انیمیشنِ ورود: یک فریم صبر می‌کنیم تا transition اجرا شود.
  useEffect(() => {
    if (!open) {
      setMounted(false)
      return undefined
    }
    const raf = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(raf)
  }, [open])

  // Esc برای بستن + قفلِ اسکرولِ پشت
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

  if (!open || !q) return null

  const tone = toneOf(q.status)
  const stage = Number(q.stage) || Math.min(5, Math.floor(((Number(q.order) || 1) - 1) / 2) + 1)
  const tutor = q.tutor_teaching ?? {}
  const studentAnswer = rawStudentAnswer(q.response)
  const hasOptions = Array.isArray(q.options) && q.options.length > 0
  const pickedIdx = Number.isInteger(Number(q.selected_option_index))
    ? Number(q.selected_option_index)
    : null

  const drawer = (
    <div className="fixed inset-0 z-[60] flex justify-start" role="dialog" aria-modal="true" aria-labelledby="tutor-title">
      {/* پردهٔ پشت */}
      <button
        type="button"
        aria-label="بستن"
        onClick={onClose}
        className={`absolute inset-0 bg-brand-950/50 backdrop-blur-sm transition-opacity duration-300 ${
          mounted ? 'opacity-100' : 'opacity-0'
        }`}
      />

      {/* کشو */}
      <aside
        className={`relative ml-auto flex h-full w-full max-w-xl flex-col overflow-hidden bg-white shadow-2xl transition-transform duration-300 ease-out sm:rounded-l-3xl ${
          mounted ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* سربرگِ کشو */}
        <header className={`shrink-0 border-b border-slate-100 px-5 py-4 ${tone.soft}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 text-[10px] font-black text-brand-700">
                <GraduationCap className="h-3.5 w-3.5" />
                معلمِ هوشمند فهم‌یار · سؤال {faNum(order)}
              </p>
              <h2 id="tutor-title" className="mt-1 text-[17px] font-black text-brand-950">
                بیا این گره رو با هم باز کنیم!
              </h2>
              <p className="mt-0.5 text-[11px] font-bold text-slate-500">
                مرحلهٔ {faNum(stage)}: {STAGE_NAMES[stage - 1]}
              </p>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="بستنِ پنجرهٔ معلم"
              className="shrink-0 rounded-xl p-2 text-slate-500 transition hover:bg-white/70 hover:text-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* صورتِ سؤال و پاسخ */}
          <div className="mt-3 space-y-2">
            {String(q.question_text ?? '').trim() && (
              <div className="rounded-xl bg-white/70 px-3 py-2">
                <p className="text-[10px] font-black text-slate-500">صورتِ سؤال</p>
                <RichText content={q.question_text} className="mt-0.5 text-[12px] font-bold leading-7 text-slate-700" />
              </div>
            )}
            <div className={`rounded-xl px-3 py-2 ring-1 ${tone.ring} bg-white/70`}>
              <p className="text-[10px] font-black text-slate-500">پاسخِ تو</p>
              {hasOptions ? (
                pickedIdx === null ? (
                  <p className="mt-0.5 text-[12px] font-bold text-slate-500">بدون پاسخ</p>
                ) : (
                  <div className="mt-0.5 text-[12px] leading-7 text-slate-700">
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
                  className={`mt-0.5 text-[12px] leading-7 ${studentAnswer ? 'text-slate-700' : 'text-slate-400'}`}
                />
              )}
            </div>
          </div>
        </header>

        {/* بدنهٔ کشو — سه بخشِ تدریس */}
        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          <TutorSection
            Icon={MessageCircleQuestion}
            step={1}
            title="کجای ماجرا لغزیدی؟"
            tone={{
              card: 'border-rose-200/70 bg-rose-50/40',
              iconBox: 'bg-white text-rose-600 ring-rose-200',
              title: 'text-rose-900',
            }}
          >
            <RichText content={tutor.misconception_root} />
          </TutorSection>

          <TutorSection
            Icon={BookOpen}
            step={2}
            title="اصلِ داستان چیه؟"
            tone={{
              card: 'border-brand-200/70 bg-brand-50/40',
              iconBox: 'bg-white text-brand-700 ring-brand-200',
              title: 'text-brand-950',
            }}
          >
            <RichText content={tutor.intuitive_explanation} />
          </TutorSection>

          <TutorSection
            Icon={KeyRound}
            step={3}
            title="نکتهٔ طلاییِ ساعت‌ساز"
            tone={{
              card: 'border-amber-200/70 bg-amber-50/50',
              iconBox: 'bg-white text-amber-600 ring-amber-200',
              title: 'text-amber-900',
            }}
          >
            <RichText content={tutor.golden_tip} />
          </TutorSection>

          <p className="flex items-start gap-1.5 rounded-xl bg-slate-50 px-3 py-2 text-[10px] font-bold leading-5 text-slate-400">
            <Lightbulb className="mt-0.5 h-3 w-3 shrink-0" />
            این توضیح با همان ارزیابیِ آزمون ساخته شده است — نه یک پاسخِ آمادهٔ
            تکراری؛ همان‌جا که خودت لغزیدی.
          </p>
        </div>

        {/* دکمهٔ اقدام */}
        <footer className="shrink-0 border-t border-slate-100 bg-white px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-700 px-4 py-3 text-[13px] font-black text-white transition hover:bg-brand-800 active:scale-[0.99]"
          >
            <CheckCircle2 className="h-4 w-4" />
            متوجه شدم! برو سؤال بعدی
            <ArrowLeft className="h-4 w-4" />
          </button>
        </footer>
      </aside>
    </div>
  )

  // Portal: کشو باید به body بچسبد، نه به کارتی که transform دارد.
  return typeof document === 'undefined' ? drawer : createPortal(drawer, document.body)
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
      <TutorDrawer
        open={tutorOpen}
        q={activeQ}
        order={activeOrder}
        onClose={() => setTutorOpen(false)}
      />
    </>
  )
}
