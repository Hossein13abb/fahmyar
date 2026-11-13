import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Eye,
  HelpCircle,
  ClipboardList,
  Lightbulb,
  NotebookPen,
  Printer,
  ArrowRight,
  GitBranch,
  FlaskConical,
  CheckCircle2,
  ScanSearch,
  FileText,
  Layers,
  FileDown,
  Loader2,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import Badge from '../components/Badge'
import MathText from '../components/MathText'
import LoadingSpinner from '../components/LoadingSpinner'
import { toFarsiNumber } from '../utils/faNumbers'

function SectionCard({ Icon, title, tone = 'brand', children, className = '' }) {
  const tones = {
    brand: 'border-brand-100 bg-white/85',
    amber: 'border-amber-200/70 bg-amber-50/50',
    teal: 'border-teal-100 bg-teal-50/40',
  }
  const iconTones = {
    brand: 'bg-brand-100 text-brand-800',
    amber: 'bg-amber-100 text-amber-800',
    teal: 'bg-teal-100 text-teal-800',
  }
  return (
    <section className={`card border ${tones[tone]} p-5 ${className}`}>
      <h2 className="flex items-center gap-2.5 text-[15px] font-black text-brand-950">
        <span className={`rounded-2xl p-2 ${iconTones[tone]}`}>
          <Icon className="h-5 w-5" />
        </span>
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

// ── دکمهٔ برجستهٔ «دانلود PDF کارنامه» — GET /api/assess/{session_id}/report-pdf ──
function DownloadPdfButton({ sessionId }) {
  const [downloading, setDownloading] = useState(false)
  const download = async () => {
    if (!sessionId) return
    setDownloading(true)
    try {
      const { data } = await client.get(`/api/assess/${sessionId}/report-pdf`, {
        responseType: 'blob',
        timeout: 120000,
      })
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url
      a.download = 'fahmyar-qualitative-report.pdf'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      let message = friendlyError(err)
      try {
        const blob = err?.response?.data
        if (blob instanceof Blob) {
          const parsed = JSON.parse(await blob.text())
          if (typeof parsed?.detail === 'string') message = parsed.detail
        }
      } catch {
        /* همان پیام عمومی نمایش داده می‌شود */
      }
      window.alert(message)
    } finally {
      setDownloading(false)
    }
  }
  return (
    <button
      onClick={download}
      disabled={downloading}
      className="flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 py-3 text-[13px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-80"
    >
      {downloading ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileDown className="h-5 w-5" />}
      {downloading ? 'در حال ساخت PDF…' : 'دانلود PDF کارنامه'}
    </button>
  )
}

// ── فلش SVG به‌سمت پایین (وابسته به هیچ فونتی نیست) ──
function DagArrow({ label }) {
  return (
    <div className="flex flex-col items-center gap-1 py-1" aria-hidden="true">
      <svg width="180" height="46" viewBox="0 0 180 46" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="90" y1="2" x2="90" y2="28" stroke="#D97706" strokeWidth="2.5" strokeDasharray="5 5" strokeLinecap="round" />
        <path d="M90 42 L78 24 L102 24 Z" fill="#D97706" />
      </svg>
      <span className="rounded-full bg-amber-100 px-3 py-0.5 text-[10px] font-black text-amber-800 ring-1 ring-amber-300">
        {label}
      </span>
    </div>
  )
}

// ── نمودار درختیِ ریشه‌یابی (Flowchart) — وابستگی پیش‌نیاز ← مفهوم هدف ──
function RootCauseDag({ target, nodes }) {
  const list = (Array.isArray(nodes) ? nodes : []).filter(Boolean)
  if (list.length === 0) {
    return (
      <p className="flex items-center gap-2 text-[13px] font-bold text-emerald-800">
        <CheckCircle2 className="h-5 w-5" /> الگوی بدفهمیِ ریشه‌دارِ تکرارشونده یافت نشد.
      </p>
    )
  }
  return (
    <div role="img" aria-label={`نمودار وابستگی مفاهیم: ${toFarsiNumber(list.length)} ریشه به‌سمتِ ${target}`}>
      {/* سطح ۱ — ریشه‌ها */}
      <p className="text-[10px] font-black uppercase tracking-wide text-amber-700">سطح ۱ — گره‌های ریشهٔ خطا (پیش‌نیازهای ضعیف)</p>
      <div className={`mt-2 grid gap-3 ${list.length > 1 ? 'sm:grid-cols-2' : ''}`}>
        {list.map((rc, i) => (
          <div
            key={i}
            className="rounded-2xl border-2 border-amber-300/70 bg-gradient-to-br from-amber-50 to-orange-50 p-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-[11px] font-black text-white">
                {toFarsiNumber(i + 1)}
              </span>
              <p className="min-w-0 flex-1 text-[12px] font-black leading-6 text-amber-950">
                {rc.concept_name || rc.area || 'عنوان ریشه ثبت نشد — معلم بررسی کند'}
              </p>
              {rc.cross_subject && (
                <span className="chip bg-white text-amber-800 ring-1 ring-amber-300">بین‌درسی</span>
              )}
              {rc.status_label && (
                <span className="chip bg-white text-amber-800 ring-1 ring-amber-300">{rc.status_label}</span>
              )}
            </div>
            {rc.reasoning && <p className="mt-2 text-[11px] leading-6 text-amber-900/90">{rc.reasoning}</p>}
          </div>
        ))}
      </div>

      <DagArrow label="باعث اختلال در" />

      {/* سطح ۲ — گرهٔ هدف */}
      <p className="text-[10px] font-black uppercase tracking-wide text-emerald-700">سطح ۲ — گرهٔ هدف (مفهومِ دارای اختلال)</p>
      <div className="mx-auto mt-2 max-w-md rounded-2xl border-2 border-emerald-600/60 bg-gradient-to-br from-emerald-600 to-teal-700 p-4 text-center shadow-lift">
        <GitBranch className="mx-auto h-6 w-6 text-emerald-100" strokeWidth={1.8} />
        <p className="mt-1.5 text-[14px] font-black text-white">{target}</p>
        <p className="mt-1 text-[10px] font-bold leading-5 text-emerald-100/90">
          ضعف‌های سطح ۱ همین‌جا خودشان را نشان می‌دهند؛ اصلاح هر گره، گرهٔ هدف را سبک‌تر می‌کند.
        </p>
      </div>

      <p className="mt-3 text-center text-[10px] font-medium leading-5 text-slate-500">
        جریان وابستگی: از پیش‌نیاز به‌سمتِ مفهوم هدف · این نمودار جایگزین نمرهٔ عددی نیست؛ فقط مسیرِ علّیِ خطا را نشان می‌دهد.
      </p>
    </div>
  )
}

const EXAM_TYPE_TITLES = {
  conceptual: 'مفهومی/استدلالی',
  real_world: 'کاربرد واقعی',
  diagram: 'نموداری/شکلی',
  misconception_trap: 'تلهٔ بدفهمی',
  computational: 'محاسباتی/رویه‌ای',
  definitional: 'حفظی/تعریفی',
  novel_application: 'کاربرد نو',
  phenomenon_explain: 'تبیین پدیده',
  compare_explanations: 'مقایسهٔ تبیین‌ها',
  predict: 'پیش‌بینی',
  categorize: 'دسته‌بندی',
  error_identify: 'شناسایی خطا',
  identify_error: 'شناسایی خطا',
  explain: 'توضیح مفهومی',
  calculate: 'محاسبه',
  compare: 'مقایسه',
  formulate: 'فرمول‌بندی',
  evaluate: 'ارزیابی',
  recall: 'یادآوری',
  solve: 'حل مسئله',
  convert_representation: 'تبدیل بازنمایی',
  // اگر بک‌اند عنوانِ فارسیِ آماده بدهد، همان نمایش داده می‌شود
  'مفهومی/استدلالی': 'مفهومی/استدلالی',
  'کاربرد واقعی': 'کاربرد واقعی',
  'نموداری/شکلی': 'نموداری/شکلی',
  'تلهٔ بدفهمی': 'تلهٔ بدفهمی',
  'محاسباتی/رویه‌ای': 'محاسباتی/رویه‌ای',
  'حفظی/تعریفی': 'حفظی/تعریفی',
}

// ── نگاشت دفاعی عناوین/متون انگلیسیِ احتمالی به فارسی (UI هرگز انگلیسی نشان نمی‌دهد) ──
const DIMENSION_FA = {
  'Conceptual/Causal Understanding': 'درک مفهومی و علّی',
  'Conceptual-Causal Understanding': 'درک مفهومی و علّی',
  'Conceptual Causal Understanding': 'درک مفهومی و علّی',
  'Conceptual Understanding': 'درک مفهومی و علّی',
  'Causal Understanding': 'درک مفهومی و علّی',
  'فهم مفهومی/علّی': 'درک مفهومی و علّی',
  'فهم مفهومی و علّی': 'درک مفهومی و علّی',
  'درک مفهومی/علّی': 'درک مفهومی و علّی',
  'Real-World Application': 'کاربرد در دنیای واقعی',
  'Real World Application': 'کاربرد در دنیای واقعی',
  'Real-world application': 'کاربرد در دنیای واقعی',
  'Application in the Real World': 'کاربرد در دنیای واقعی',
  'Practical Application': 'کاربرد در دنیای واقعی',
  'کاربرد واقعی': 'کاربرد در دنیای واقعی',
  'کاربرد عملی': 'کاربرد در دنیای واقعی',
  'Quantitative and Computational Skills': 'مهارت‌های کمی و محاسباتی',
  'Quantitative/Computational Skills': 'مهارت‌های کمی و محاسباتی',
  'Quantitative Skills': 'مهارت‌های کمی و محاسباتی',
  'Computational Skills': 'مهارت‌های کمی و محاسباتی',
  'Computational Procedure': 'مهارت‌های کمی و محاسباتی',
  'Numerical Computation': 'مهارت‌های کمی و محاسباتی',
  'رویهٔ حل‌سازی': 'مهارت‌های کمی و محاسباتی',
  'مهارت محاسباتی': 'مهارت‌های کمی و محاسباتی',
  'Diagram/Visual Representation': 'بازنمایی نموداری و تصویری',
  'Visual Representation': 'بازنمایی نموداری و تصویری',
  'Diagrammatic Representation': 'بازنمایی نموداری و تصویری',
  'Graph Reading': 'بازنمایی نموداری و تصویری',
  'Chart Reading': 'بازنمایی نموداری و تصویری',
  'Diagram Interpretation': 'بازنمایی نموداری و تصویری',
  'خواندن نمودار و داده': 'بازنمایی نموداری و تصویری',
  'نموداری': 'بازنمایی نموداری و تصویری',
  'Misconception Trap': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'Misconception Traps': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'Common Misconceptions': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'Misconceptions': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'Identifying Misconceptions': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'ردیابی بدفهمی شایع': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'ردیابی بدفهمی‌های رایج': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'تلهٔ بدفهمی': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'تله‌های بدفهمی': 'مواجهه با تله‌ها و بدفهمی‌ها',
  'Clarity of Explanation': 'شفافیت بیان و خودپایشی',
  'Clarity and Self-monitoring': 'شفافیت بیان و خودپایشی',
  'Clarity and Self-Monitoring': 'شفافیت بیان و خودپایشی',
  'Self-monitoring': 'شفافیت بیان و خودپایشی',
  'Self Monitoring': 'شفافیت بیان و خودپایشی',
  'Metacognitive Clarity': 'شفافیت بیان و خودپایشی',
  'Expression Clarity': 'شفافیت بیان و خودپایشی',
  'شفافیت بیان': 'شفافیت بیان و خودپایشی',
  'خودپایشی': 'شفافیت بیان و خودپایشی',
}

const _faDire = /[؀-ۿﭐ-﷿ﹰ-﻿]/g
const _enWord = /[A-Za-z]{4,}/g

const faKey = (text) => String(text ?? '').trim().toLowerCase().replace(/[‌\s\-_/|:،؛٬–—]/g, '')

const faAliasLookup = (text) => {
  const raw = String(text ?? '').trim()
  if (!raw) return null
  if (DIMENSION_FA[raw]) return DIMENSION_FA[raw]
  const key = faKey(raw)
  const entries = Object.entries(DIMENSION_FA).sort((a, b) => faKey(b[0]).length - faKey(a[0]).length)
  for (const [alias, target] of entries) {
    if (faKey(alias) === key) return target
  }
  for (const [alias, target] of entries) {
    const a = faKey(alias)
    if (a.length >= 6 && key.includes(a)) return target
  }
  return null
}

const latinHeavy = (text) => {
  const s = String(text ?? '').replace(/\$\$[\s\S]*?\$\$|\$[^$]*\$|\\[A-Za-z]+/g, ' ')
  const fa = (s.match(_faDire) || []).length
  const en = (s.match(_enWord) || []).join('').length
  return en >= 8 && en > fa
}

const validBadgeStatus = (status) =>
  ['CONFIRMED', 'LIKELY_UNDERSTOOD', 'UNCLEAR', 'NEEDS_REVIEW', 'INSUFFICIENT_EVIDENCE', 'completed', 'active', 'paused'].includes(status)
    ? status
    : 'UNCLEAR'

const faDimension = (name) => {
  const hit = faAliasLookup(name)
  if (hit) return hit
  const s = String(name ?? '').trim()
  return latinHeavy(s) ? 'بُعد فهم' : (s || 'بُعد فهم')
}

const dimensionFallback = (status) => {
  const st = String(status ?? '').toUpperCase()
  if (st === 'NEEDS_REVIEW') return 'در این بُعد نشانه‌های بدفهمی دیده شد؛ معلم باید با نمونه‌نقض، استدلال دانش‌آموز را بازسازی کند.'
  if (st === 'CONFIRMED') return 'این بُعد در پاسخ‌ها با استدلال روشن ثبت شده است.'
  if (st === 'LIKELY_UNDERSTOOD') return 'هستهٔ این بُعد به نظر می‌رسد درست باشد، اما بیان باید کامل‌تر شود.'
  if (st === 'INSUFFICIENT_EVIDENCE') return 'در این بُعد پاسخ کافی برای داوری ثبت نشده است.'
  return 'در این بُعد پاسخ روشن و قاطع نیست؛ معلم باید با پرسش راهنما ادامه را بررسی کند.'
}

const feedbackFallback = (status) => {
  const st = String(status ?? '').toUpperCase()
  if (st === 'NEEDS_REVIEW') return 'در این پاسخ تناقض علمی روشن دیده می‌شود؛ دانش‌آموز باید همان استدلال را با نمونه‌نقض بازسازی کند.'
  if (st === 'CONFIRMED') return 'این پاسخ با مبانی علمی سازگار است و استدلال علّی روشن دارد.'
  if (st === 'LIKELY_UNDERSTOOD') return 'هستهٔ پاسخ درست است، اما دلیل و مرزبندی آن باید کامل‌تر بیان شود.'
  if (st === 'INSUFFICIENT_EVIDENCE') return 'برای این پاسخ شواهد کافی ثبت نشده است.'
  return 'این پاسخ دلیل روشن و قابل اتکا ندارد؛ معلم باید با پرسش راهنما فهم دانش‌آموز را روشن کند.'
}

const faText = (text, fallbackFa) => {
  const s = String(text ?? '').trim()
  if (!s) return fallbackFa
  return latinHeavy(s) ? fallbackFa : s
}

const faSuggestion = (text) =>
  faText(text, 'پیش‌نیازها را مرور کنید و برای هر بدفهمیِ شناسایی‌شده یک مثال نقض ساده طراحی و بلند بلند توضیح دهید.')

const faExamType = (t) => {
  const raw = String(t ?? '').trim()
  return EXAM_TYPE_TITLES[raw] || (latinHeavy(raw) ? 'تحلیلی' : raw || '—')
}


// پاسخِ خامِ دانش‌آموز — اگر رشته شبیه خروجی/JSONِ مدل باشد، آن را نشان نمی‌دهیم (بک‌اند هم تطهیر می‌کند)
const _modelMarkers = ['<<<', '"per_question"', '"dimension_findings"', '"root_cause_hypotheses"', '"improvement_suggestions"']
const rawStudentAnswer = (text) => {
  const s = String(text ?? '').trim()
  if (!s) return ''
  if (_modelMarkers.some((m) => s.includes(m))) return ''
  if (s.startsWith('{') && s.endsWith('}')) {
    try {
      const obj = JSON.parse(s)
      if (obj && typeof obj === 'object' && ['per_question', 'dimension_findings', 'root_cause_hypotheses', 'improvement_suggestions'].some((k) => k in obj)) return ''
    } catch {
      /* JSON نامعتبر — ولی چون با { شروع می‌شود و محتوا فنی نیست، رد نمی‌کنیم مگر نشانگر داشته باشد */
    }
  }
  return s
}

function ExamReport({ report, mode, onBackToDashboard }) {

  const navigate = useNavigate()
  const handleBack = onBackToDashboard ?? (() => navigate(mode === 'teacher' ? '/staff' : '/dashboard'))
  const backLabel = mode === 'teacher' ? 'بازگشت به داشبورد مدرسه' : 'بازگشت به داشبورد'
  const dimensions = report.dimensions ?? []
  const perQuestion = report.per_question ?? []
  const rootCauses = report.root_causes ?? []
  const suggestions = report.suggestions ?? []
  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleDateString('fa-IR', { dateStyle: 'long' })
    : ''

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── سربرگ گزارش ── */}
      <section className="card flex flex-wrap items-start justify-between gap-4 p-6">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-bold text-brand-600">
            <ClipboardList className="h-4 w-4" />
            گزارش تشخیصی آزمون جامع · {generatedAt}
          </p>
          <h1 className="mt-1.5 text-2xl font-black text-brand-950 sm:text-3xl">{report.concept_name ?? 'مفهوم نامشخص'}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge status="completed" />
            <span className="chip bg-slate-100 text-slate-600 ring-1 ring-slate-200">{toFarsiNumber(report.questions_answered ?? perQuestion.length)} سؤال تحلیل شد</span>
          </div>
        </div>
        <div className="no-print flex shrink-0 flex-col gap-2">
          <DownloadPdfButton sessionId={report.session_id} />
          <button onClick={() => window.print()} className="flex items-center justify-center gap-2 rounded-2xl bg-brand-700 px-5 py-3 text-[13px] font-black text-white shadow-card transition hover:bg-brand-800">
            <Printer className="h-5 w-5" />
            چاپ / دانلود گزارش
          </button>
          <button
            onClick={handleBack}
            className="flex items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-3 text-[13px] font-bold text-brand-800 transition hover:bg-brand-50"
          >
            <ArrowRight className="h-5 w-5" />
            {backLabel}
          </button>
        </div>
      </section>

      {/* ── (الف) نمای کلی وضعیت ── */}
      <SectionCard Icon={Layers} title="نمای کلی وضعیت — ابعاد فهم" tone="teal">
        <div className="grid gap-2 md:grid-cols-2">
          {dimensions.map((d, i) => (
            <div key={i} className="flex items-start gap-3 rounded-2xl border border-teal-100 bg-white/80 p-4">
              <Badge status={validBadgeStatus(d.status)} className="mt-0.5 shrink-0" />
              <div className="min-w-0">
                <p className="text-[13px] font-black text-brand-950">{faDimension(d.dimension)}</p>
                <p className="mt-1 text-[12px] leading-6 text-slate-600">{faText(d.finding, dimensionFallback(d.status))}</p>
              </div>
            </div>
          ))}
          {dimensions.length === 0 && <p className="text-[13px] text-slate-500">تحلیل ابعادی ثبت نشده است.</p>}
        </div>
      </SectionCard>

      {/* ── (ب) تحلیل تفصیلی تک‌تک سوالات ── */}
      <SectionCard Icon={FileText} title="تحلیل تفصیلی تک‌تک سوالات">
        <div className="space-y-3">
          {perQuestion.map((q, i) => (
            <article key={i} className="overflow-hidden rounded-2xl border border-brand-100/70 bg-white/80">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-brand-50 bg-brand-50/40 px-4 py-2.5">
                <p className="text-[12px] font-black text-brand-800">
                  سؤال {toFarsiNumber(q.order ?? i + 1)} <span className="font-medium text-slate-400">· {faExamType(q.exam_type)}</span>
                </p>
                <Badge status={validBadgeStatus(q.status)} />
              </div>
              <div className="px-4 py-3">
                {q.question_text && (
                  <div className="math-content text-[12px] font-bold leading-7 text-slate-500">
                    <MathText content={q.question_text || ''} />
                  </div>
                )}
                {q.response !== undefined && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] font-bold text-slate-400">پاسخ شما</summary>
                    <p className="mt-1 whitespace-pre-line rounded-2xl bg-slate-50 p-3 text-[12px] leading-7 text-slate-700">
                      {rawStudentAnswer(q.response) || '— پاسخی ثبت نشده بود —'}
                    </p>
                  </details>
                )}
                <div className="math-content mt-2 border-r-2 border-brand-200 pr-3 text-[13px] leading-8 text-brand-950">
                  <MathText content={faText(q.qualitative_feedback, feedbackFallback(q.status)) || ''} />
                </div>
              </div>
            </article>
          ))}
          {perQuestion.length === 0 && <p className="text-[13px] text-slate-500">سؤالی ثبت نشده است.</p>}
        </div>
      </SectionCard>

      {/* ── (ج) تحلیل ریشه‌ای بدفهمی‌ها — گراف وابستگی مفاهیم (DAG) ── */}
      <SectionCard Icon={GitBranch} title="تحلیل ریشه‌ای بدفهمی‌ها — گراف وابستگی مفاهیم" tone="amber">
        <RootCauseDag target={report.concept_name ?? 'مفهوم هدف'} nodes={rootCauses} />
      </SectionCard>

      {/* ── (د) پیشنهادهای بهبود کیفی ── */}
      <SectionCard Icon={Lightbulb} title={mode === 'teacher' ? 'پیشنهادهای بهبود (برای برنامه‌ریزی معلم)' : 'پیشنهادهای بهبود — قدم‌به‌قدم'}>
        <ol className="space-y-2">
          {suggestions.map((sug, i) => (
            <li key={i} className="flex items-start gap-2.5 rounded-2xl border border-brand-50 bg-brand-50/40 px-4 py-3 text-[13px] leading-7 text-brand-950">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-700 text-[11px] font-black text-white">{toFarsiNumber(i + 1)}</span>
              {faSuggestion(sug)}
            </li>
          ))}
        </ol>
      </SectionCard>

      {/* ── موارد هنوز روشن‌نشده ── */}
      {Array.isArray(report.sections?.['موارد هنوز روشن‌نشده']) && report.sections['موارد هنوز روشن‌نشده'].length > 0 && (
        <SectionCard Icon={HelpCircle} title="موارد هنوز روشن‌نشده" tone="amber">
          <ul className="space-y-2">
            {report.sections['موارد هنوز روشن‌نشده'].map((u, i) => (
              <li key={i} className="rounded-2xl border border-amber-200/60 bg-white/70 px-4 py-2.5 text-[12px] leading-6 text-amber-950">{u}</li>
            ))}
          </ul>
        </SectionCard>
      )}

      {mode === 'teacher' && Array.isArray(report.evidence_log) && report.evidence_log.length > 0 && (
        <SectionCard Icon={ScanSearch} title="لاگ خام شواهد (برای معلم)" tone="amber">
          <div className="max-h-96 space-y-2 overflow-auto">
            {report.evidence_log.map((entry, i) => (
              <div key={i} className="rounded-2xl border border-slate-100 bg-white p-3 text-[11px] leading-6 text-slate-600">
                <p className="font-black text-slate-500">سؤال {entry.order ?? i + 1} ({faExamType(entry.exam_type)}) — #{entry.question_id}</p>
                <p className="mt-0.5 line-clamp-2">{rawStudentAnswer(entry.response) || '— پاسخی ثبت نشده بود —'}</p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(entry.evidence ?? []).map((ev, j) => (
                    <Badge key={j} status={validBadgeStatus(ev.status)} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <p className="pb-2 text-center text-[11px] text-slate-400">
        این گزارش فقط برای تو و معلمت قابل مشاهده است.
      </p>
    </div>
  )
}

export default function ReportView({ mode = 'student', onBackToDashboard }) {
  const { sessionId, studentId } = useParams()
  const navigate = useNavigate()
  const handleBack = onBackToDashboard ?? (() => navigate(mode === 'teacher' ? '/staff' : '/dashboard'))
  const backLabel = mode === 'teacher' ? 'بازگشت به داشبورد مدرسه' : 'بازگشت به داشبورد'
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    const url =
      mode === 'teacher'
        ? `/api/teacher/students/${studentId}/reports/${sessionId}`
        : `/api/assess/${sessionId}/report`
    client
      .get(url)
      .then(({ data }) => alive && setReport(data))
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [mode, sessionId, studentId])

  if (loading) return <LoadingSpinner label="در حال ساختن گزارش فهم…" className="min-h-[22rem]" />
  if (error) {
    return (
      <div className="card mx-auto max-w-lg p-8 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-amber-500" />
        <p className="mt-2 font-bold text-amber-900">{error}</p>
        <button onClick={handleBack} className="mt-4 rounded-2xl border border-brand-200 px-5 py-2.5 font-bold text-brand-800 hover:bg-brand-50">
          {backLabel}
        </button>
      </div>
    )
  }

  if (report?.exam) {
    return <ExamReport report={report} mode={mode} onBackToDashboard={onBackToDashboard} />
  }

  const s = report.sections ?? {}
  const observations = s['مشاهدات'] ?? []
  const evidenceLines = s['شواهد'] ?? []
  const unclear = s['موارد هنوز روشن‌نشده'] ?? []
  const studentActions = s['پیشنهاد اقدام برای دانش‌آموز'] ?? []
  const teacherNotes = s['یادداشت برای معلم'] ?? []
  const propositionStatuses = report.proposition_statuses ?? {}
  const generatedAt = report.generated_at ? new Date(report.generated_at).toLocaleDateString('fa-IR', { dateStyle: 'long' }) : ''

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── سربرگ گزارش ── */}
      <section className="card flex flex-wrap items-start justify-between gap-4 p-6">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-bold text-brand-600">
            <ClipboardList className="h-4 w-4" />
            گزارش فهم · {generatedAt}
          </p>
          <h1 className="mt-1.5 text-2xl font-black text-brand-950 sm:text-3xl">{report.concept_name ?? 'مفهوم نامشخص'}</h1>
          <p className="mt-1.5 max-w-xl text-[13px] leading-7 text-slate-500">زمینهٔ بررسی: {s['زمینه'] ?? '—'}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge status={report.status} />
            <span className="chip bg-slate-100 text-slate-600 ring-1 ring-slate-200">{report.questions_answered ?? 0} پاسخ ثبت شد</span>
          </div>
        </div>
        <div className="no-print flex shrink-0 flex-col gap-2">
          <DownloadPdfButton sessionId={report.session_id} />
          <button onClick={() => window.print()} className="flex items-center justify-center gap-2 rounded-2xl bg-brand-700 px-5 py-3 text-[13px] font-black text-white shadow-card transition hover:bg-brand-800">
            <Printer className="h-5 w-5" />
            چاپ / دانلود گزارش
          </button>
          <button
            onClick={handleBack}
            className="flex items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-3 text-[13px] font-bold text-brand-800 transition hover:bg-brand-50"
          >
            <ArrowRight className="h-5 w-5" />
            {backLabel}
          </button>
        </div>
      </section>

      {/* ── مشاهدات + مبهم‌ها ── */}
      <div className="grid gap-4 lg:grid-cols-5">
        <SectionCard Icon={Eye} title="مشاهدات (چه چیزی دیدیم؟)" className="lg:col-span-3">
          {observations.length === 0 ? (
            <p className="text-[13px] text-slate-500">پاسخی ثبت نشده است.</p>
          ) : (
            <ul className="space-y-2">
              {observations.map((o, i) => (
                <li key={i} className="flex items-start gap-2 rounded-2xl border border-brand-50 bg-brand-50/40 px-4 py-2.5 text-[13px] leading-7 text-brand-950">
                  <span className="mt-0.5 shrink-0 font-black text-brand-400">{toFarsiNumber(i + 1)}.</span>
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard Icon={HelpCircle} title="موارد هنوز روشن‌نشده" tone="amber" className="lg:col-span-2">
          {unclear.length === 0 ? (
            <p className="flex items-center gap-2 text-[13px] font-bold text-emerald-800">
              <CheckCircle2 className="h-5 w-5" /> مورد مبهمی باقی نمانده است 🌱
            </p>
          ) : (
            <ul className="space-y-2">
              {unclear.map((u, i) => (
                <li key={i} className="rounded-2xl border border-amber-200/60 bg-white/70 px-4 py-2.5 text-[12px] leading-6 text-amber-950">
                  {u}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      {/* ── وضعیت گزاره‌های هسته‌ای ── */}
      <SectionCard Icon={FlaskConical} title="وضعیت گزاره‌های هسته‌ای" tone="teal">
        <div className="grid gap-2 md:grid-cols-2">
          {Object.entries(propositionStatuses).map(([prop, status]) => (
            <div key={prop} className="flex items-start gap-3 rounded-2xl border border-teal-100 bg-white/80 p-4">
              <Badge status={status} className="mt-0.5 shrink-0" />
              <p className="text-[13px] leading-7 text-brand-950">{prop}</p>
            </div>
          ))}
          {Object.keys(propositionStatuses).length === 0 && (
            <p className="text-[13px] text-slate-500">هنوز گزاره‌ای سنجیده نشده است.</p>
          )}
        </div>

        {evidenceLines.length > 0 && (
          <details className="mt-4 rounded-2xl border border-teal-100 bg-white/60 p-4">
            <summary className="cursor-pointer text-[12px] font-black text-teal-900">شواهد تفصیلیِ تحلیل‌گر ({evidenceLines.length} مورد)</summary>
            <ol className="mt-3 list-decimal space-y-1.5 pr-5 text-[12px] leading-7 text-slate-600">
              {evidenceLines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ol>
          </details>
        )}
      </SectionCard>

      {/* ── فرضیه‌های ریشهٔ خطا (مسیر B) — گراف وابستگی مفاهیم (DAG) ── */}
      <SectionCard Icon={GitBranch} title="فرضیه‌های ریشهٔ خطا — گراف وابستگی مفاهیم" tone="amber">
        <RootCauseDag
          target={report.concept_name ?? 'مفهوم هدف'}
          nodes={Array.isArray(report.root_causes) ? report.root_causes : []}
        />
      </SectionCard>

      {/* ── پیشنهاد گام بعدی ── */}
      <div className={`grid gap-4 ${mode === 'teacher' ? 'lg:grid-cols-2' : ''}`}>
        <SectionCard Icon={Lightbulb} title={mode === 'teacher' ? 'پیشنهاد برای دانش‌آموز' : 'گام بعدی تو'}>
          <ul className="space-y-2">
            {studentActions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-7 text-brand-950">
                <span className="mt-0.5 shrink-0 font-black text-brand-400">{toFarsiNumber(i + 1)}.</span>
                {a}
              </li>
            ))}
          </ul>
        </SectionCard>

        {mode === 'teacher' && (
          <SectionCard Icon={NotebookPen} title="یادداشت برای معلم" tone="amber">
            {teacherNotes.length === 0 ? (
              <p className="text-[13px] text-slate-500">یادداشت ویژه‌ای ثبت نشده است.</p>
            ) : (
              <ul className="space-y-2">
                {teacherNotes.map((t, i) => (
                  <li key={i} className="flex items-start gap-2 text-[13px] leading-7 text-amber-950">
                    <span className="mt-0.5 shrink-0 font-black text-amber-500">{toFarsiNumber(i + 1)}.</span>
                    {t}
                  </li>
                ))}
              </ul>
            )}
            {Array.isArray(report.evidence_log) && report.evidence_log.length > 0 && (
              <details className="mt-4 rounded-2xl border border-amber-200/60 bg-white/60 p-4">
                <summary className="cursor-pointer text-[12px] font-black text-amber-900">لاگ خام شواهد (برای معلم)</summary>
                <div className="mt-3 max-h-72 space-y-2 overflow-auto">
                  {report.evidence_log.map((entry, i) => (
                    <div key={i} className="rounded-2xl border border-slate-100 bg-white p-3 text-[11px] leading-6 text-slate-600">
                      <p className="font-black text-slate-500">پاسخ {toFarsiNumber(i + 1)} — سؤال {toFarsiNumber(entry.question_id)}</p>
                      <p className="mt-0.5 line-clamp-2">{rawStudentAnswer(entry.response) || '— پاسخی ثبت نشده بود —'}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {(entry.evidence ?? []).map((ev, j) => (
                          <Badge key={j} status={validBadgeStatus(ev.status)} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </SectionCard>
        )}
      </div>

      <p className="pb-2 text-center text-[11px] text-slate-400">
        این گزارش شخصی است و فقط برای تو (و معلمت) قابل مشاهده است — هرگز مقایسه یا رتبه‌بندی نمی‌شود.
      </p>
    </div>
  )
}
