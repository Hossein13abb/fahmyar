import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import DetailedQuestions, { ContradictionCard, LiveTutorModal } from '../components/cognitive/DetailedQuestions'
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
  GraduationCap,
  Puzzle,
  Search,
  FileText,
  Layers,
  FileDown,
  Loader2,
  Cpu,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import Badge from '../components/Badge'
import MathText from '../components/MathText'
import LoadingSpinner from '../components/LoadingSpinner'
import { toFarsiNumber } from '../utils/faNumbers'

/**
 * کارتِ بخش — هر بخش یک «کارتِ پنل» با نوارِ گرادیانتیِ بالاست.
 *
 * بدونِ این نوار، همهٔ بخش‌ها یک مستطیلِ تخت با یک آیکونِ کوچک دیده
 * می‌شدند و صفحه بی‌روح می‌شد. نوار مرجعِ بصریِ هر بخش است.
 */
function SectionCard({ Icon, title, tone = 'brand', children, className = '' }) {
  const tones = {
    brand: {
      rail: 'from-brand-400 via-emerald-400 to-teal-400',
      head: 'bg-gradient-to-l from-brand-50/80 via-white to-white',
      icon: 'bg-gradient-to-br from-brand-600 to-emerald-600 text-white shadow-sm',
      ring: 'ring-slate-200/70',
    },
    amber: {
      rail: 'from-amber-300 via-orange-300 to-calm-400',
      head: 'bg-gradient-to-l from-amber-50/80 via-white to-white',
      icon: 'bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-sm',
      ring: 'ring-amber-100',
    },
    teal: {
      rail: 'from-teal-300 via-cyan-400 to-brand-400',
      head: 'bg-gradient-to-l from-teal-50/80 via-white to-white',
      icon: 'bg-gradient-to-br from-teal-600 to-cyan-600 text-white shadow-sm',
      ring: 'ring-teal-100',
    },
  }
  const st = tones[tone] ?? tones.brand
  return (
    <section
      className={`group relative overflow-hidden rounded-2xl bg-white shadow-panel ring-1 transition-shadow duration-300 hover:shadow-panel-hover ${st.ring} ${className}`}
    >
      <span className={`block h-1 w-full bg-gradient-to-l ${st.rail}`} aria-hidden="true" />
      <div className="p-5">
        <h2 className="flex items-center gap-2.5 text-[15px] font-black text-brand-950">
          <span className={`rounded-2xl p-2 ${st.icon}`}>
            <Icon className="h-5 w-5" />
          </span>
          {title}
        </h2>
        <div className="mt-3">{children}</div>
      </div>
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
      className="flex items-center justify-center gap-2 rounded-2xl bg-white px-5 py-3 text-[13px] font-black text-brand-900 shadow-lift transition hover:bg-emerald-50 disabled:cursor-wait disabled:opacity-80"
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

const BADGE_STATUSES = [
  'CORRECT',
  'HALF_CORRECT',
  'WRONG',
  'CONFIRMED',
  'LIKELY_UNDERSTOOD',
  'UNCLEAR',
  'NEEDS_REVIEW',
  'INSUFFICIENT_EVIDENCE',
  'completed',
  'active',
  'paused',
]

const validBadgeStatus = (status) => (BADGE_STATUSES.includes(status) ? status : 'UNCLEAR')

// عنوانِ فارسیِ مرحله — هرگز «نامشخص» به‌جای عنوانِ مرحله نمی‌نشیند.
// برچسب‌های عمومی — هم‌راستا با ai/brand_terms.py
const STAGE_NAMES = [
  'سؤال مفهومی',
  'سؤال چهارگزینه‌ای',
  'پیش‌بینی رفتار پدیده',
  'بررسی استدلال علمی',
  'توضیح ساده و شهودی',
]

const faDigits = (text) =>
  String(text ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

// بُعدی که فاقد هر دادهٔ معنادار است، «بُعد فهم» نیست؛ کارتِ خالی است.
// placeholderهایی که بک‌اند فقط برای پر نماندنِ ساختار می‌گذارد
const PLACEHOLDER_DIMENSIONS = [
  'تحلیل ابعادی انجام نشد',
  'تحلیل ابعادی ثبت نشده',
]

const isEmptyDimension = (d) => {
  const status = String(d?.status ?? '').toUpperCase()
  const finding = String(d?.finding ?? '').trim()
  const dim = String(d?.dimension ?? '').trim()
  if (PLACEHOLDER_DIMENSIONS.some((p) => finding.includes(p))) return true
  const statusEmpty = !status || status === 'UNCLEAR'
  const findingEmpty = !finding || finding.length < 3
  const dimEmpty = !dim
  return statusEmpty && findingEmpty && dimEmpty
}

const hasOptions = (q) => Array.isArray(q?.options) && q.options.length > 0

// انتخاب فقط از اندیسِ ذخیره‌شده می‌آید — نه از مقایسهٔ متن یا عددی در توضیح.
const pickedOptionIndex = (q) => {
  if (!hasOptions(q)) return null
  const raw = q?.selected_option_index
  if (raw === null || raw === undefined || raw === '') return null
  const n = Number(raw)
  return Number.isInteger(n) && n >= 0 && n < q.options.length ? n : null
}

// متنِ گزینهٔ انتخاب‌شده: اول از فیلدِ صریحِ ذخیره‌شده، بعد از لیستِ گزینه‌ها.
// این ترتیب یعنی کارنامه هرگز به بازسازیِ حدسی وابسته نیست.
const selectedText = (q) => {
  const stored = String(q?.selected_option_text ?? '').trim()
  if (stored) return stored
  const idx = pickedOptionIndex(q)
  if (idx === null) return null
  return String(q?.options?.[idx] ?? '')
}

/**
 * عنوانِ مرحله — همیشه برچسبِ عمومی، هرگز نامِ متدولوژیِ داخلی.
 *
 * ``stage_title`` ممکن است از سمتِ سرور بیاید و در کارنامه‌های قدیمی
 * «مرحله ۲: تست لایه نقاب» باشد. پس به آن اعتماد نمی‌کنیم و از شمارهٔ
 * ترتیب برچسبِ عمومی می‌سازیم. (سرور هم از فاز ۱۷ همین را می‌فرستد؛ این
 * لایه برای داده‌های ذخیره‌شدهٔ قدیمی است.)
 */
const faStageTitle = (q, index) => {
  const order = Number(q?.order) || index + 1
  const stage = Math.min(5, Math.max(1, Math.ceil(order / 2)))
  return STAGE_NAMES[stage - 1] ?? 'سؤال تحلیلی'
}

const stageFallback = (status) => {
  const st = String(status ?? '').toUpperCase()
  if (st === 'CORRECT') return 'این مرحله با استدلالِ درست پاسخ داده شده است.'
  if (st === 'HALF_CORRECT') return 'بخشی از استدلال درست بود، اما هستهٔ منطقِ مورد انتظار کامل گفته نشد.'
  if (st === 'WRONG') return 'پاسخِ این مرحله به نتیجه یا استدلالِ نادرست می‌رسد.'
  return 'برای این مرحله شاهدِ کافی ثبت نشده است.'
}

const faDimension = (name) => {
  const hit = faAliasLookup(name)
  if (hit) return hit
  const s = String(name ?? '').trim()
  return latinHeavy(s) ? 'بُعد فهم' : (s || 'بُعد فهم')
}

// پنج بُعدِ استاندارد — کلیدها قراردادِ مشترک با بک‌اند (reports/dimensions.py)
const DIM_LABEL = {
  conceptual_knowledge: 'دانش مفهومی',
  distractor_resistance: 'مقاومت در برابر دادهٔ انحرافی',
  causal_reasoning: 'استدلال علّی',
  critical_debugging: 'نقد استدلال',
  simple_communication: 'انتقال ساده',
}

const DIM_STYLE = {
  mastered: {
    card: 'border-emerald-200/70 bg-gradient-to-br from-emerald-50 via-emerald-50/70 to-teal-50/40',
    chip: 'bg-emerald-100 text-emerald-900 ring-emerald-300',
    label: 'تسلط',
    fallback: 'این بُعد با استدلالِ روشن در پاسخ‌ها ثبت شده است.',
  },
  developing: {
    card: 'border-amber-200/70 bg-gradient-to-br from-amber-50 via-amber-50/70 to-orange-50/40',
    chip: 'bg-amber-100 text-amber-900 ring-amber-300',
    label: 'در حال رشد',
    fallback: 'هستهٔ این بُعد درست است، اما بیان باید کامل‌تر شود.',
  },
  needs_work: {
    card: 'border-rose-200/70 bg-gradient-to-br from-rose-50 via-rose-50/70 to-red-50/40',
    chip: 'bg-rose-100 text-rose-900 ring-rose-300',
    label: 'نیازمند کار',
    fallback: 'این بُعد بدفهمیِ روشن دارد و باید بازسازی شود.',
  },
  not_assessed: {
    card: 'border-slate-200/80 bg-gradient-to-br from-slate-50 to-brand-50/30',
    chip: 'bg-slate-100 text-slate-600 ring-slate-300',
    label: 'بدون پاسخ',
    fallback: 'به این مرحله پاسخی نداده است؛ داوری ممکن نیست.',
  },
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

// پیشنهادها ممکن است از دادهٔ قدیمی/مدل به شکلِ دیکشنری آمده باشند.
// هر شکلِ معقولی به یک رشتهٔ فارسی تبدیل می‌شود؛ هیچ `[object Object]`ی
// نباید به چشمِ دانش‌آموز برسد.
const suggestionText = (raw) => {
  if (raw === null || raw === undefined) return ''
  if (typeof raw === 'string') return raw.trim()
  if (typeof raw === 'number') return String(raw)
  if (Array.isArray(raw)) return raw.map(suggestionText).filter(Boolean).join(' ')
  if (typeof raw === 'object') {
    for (const key of ['suggestion', 'text', 'description', 'title', 'action', 'advice']) {
      const value = raw[key]
      if (typeof value === 'string' && value.trim()) return value.trim()
    }
    const first = Object.values(raw).find((v) => typeof v === 'string' && v.trim())
    return typeof first === 'string' ? first.trim() : ''
  }
  return ''
}

const cleanSuggestions = (list) => {
  const out = []
  for (const item of Array.isArray(list) ? list : []) {
    const text = suggestionText(item).replace(/\s+/g, ' ').trim()
    if (!text) continue
    if (/^[[{].*[}\]]$/.test(text)) continue
    if (!out.includes(text)) out.push(text)
  }
  return out
}

const faSuggestion = (text) =>
  faText(text, 'پیش‌نیازها را مرور کنید و برای هر بدفهمیِ شناسایی‌شده یک مثال نقض ساده طراحی و بلند بلند توضیح دهید.')

const faExamType = (t) => {
  const raw = String(t ?? '').trim()
  return EXAM_TYPE_TITLES[raw] || (latinHeavy(raw) ? 'تحلیلی' : raw || '—')
}


// پاسخِ خامِ دانش‌آموز — اگر رشته شبیه خروجی/JSONِ مدل باشد، آن را نشان نمی‌دهیم (بک‌اند هم تطهیر می‌کند)
// ── نقشهٔ رنگ و برچسبِ کارنامهٔ X-Ray ─────────────────────────────────────
const MASTERY_LABEL = {
  MASTERED: 'مسلط',
  ILLUSION_OF_COMPETENCE: 'توهمِ دانایی',
  JARGON_DEPENDENT: 'وابسته به اصطلاح',
  PARTIAL_FRAGMENTED: 'تکه‌تکه اما امیدبخش',
  UNSTRUCTURED: 'بی‌ساختار',
}

// هدرِ «کارنامهٔ اشعهٔ ایکس» هم روشن است، هم‌خانواده با بقیهٔ کارت‌ها.
// هدرِ «کارنامهٔ اشعهٔ ایکس»: گرادیانتِ دو‌رنگ + هاله، نه یک زمینهٔ تک‌رنگ.
/**
 * هدرِ «کارنامهٔ اشعهٔ ایکس» — نواری پُررنگ و اشباع، با متنِ سفید.
 *
 * کاربر صریحاً همین را خواست: نسخهٔ روشنِ کم‌رنگ سرد و بی‌روح بود. ولی
 * یک گرادیانتِ ملایمِ هم‌خانواده به آن اضافه شده تا «مستطیلِ تک‌رنگ»
 * نباشد؛ هرچند جنسِ رنگ همان رنگِ برند است، نه صورتیِ تهاجمی.
 */
const MASTERY_STYLE = {
  MASTERED: {
    head: 'bg-gradient-to-l from-emerald-600 via-emerald-500 to-teal-500',
    aurora: 'bg-teal-200/25',
    chip: 'bg-white text-emerald-800',
    chipGhost: 'bg-white/20 text-white ring-1 ring-white/25',
  },
  ILLUSION_OF_COMPETENCE: {
    head: 'bg-gradient-to-l from-rose-600 via-rose-500 to-red-500',
    aurora: 'bg-rose-200/25',
    chip: 'bg-white text-rose-800',
    chipGhost: 'bg-white/20 text-white ring-1 ring-white/25',
  },
  JARGON_DEPENDENT: {
    head: 'bg-gradient-to-l from-orange-500 via-orange-500 to-amber-500',
    aurora: 'bg-amber-200/25',
    chip: 'bg-white text-orange-800',
    chipGhost: 'bg-white/20 text-white ring-1 ring-white/25',
  },
  PARTIAL_FRAGMENTED: {
    head: 'bg-gradient-to-l from-amber-600 via-amber-500 to-orange-500',
    aurora: 'bg-orange-200/25',
    chip: 'bg-white text-amber-800',
    chipGhost: 'bg-white/20 text-white ring-1 ring-white/25',
  },
  UNSTRUCTURED: {
    head: 'bg-gradient-to-l from-slate-700 via-slate-600 to-slate-500',
    aurora: 'bg-slate-200/20',
    chip: 'bg-white text-slate-800',
    chipGhost: 'bg-white/20 text-white ring-1 ring-white/25',
  },
}

const FINDING_LABEL = {
  CONTRADICTION: 'تناقض',
  SYNERGY: 'هم‌افزایی',
  JARGON_VIOLATION: 'نقضِ کلماتِ ممنوعه',
  BLUFF_DETECTED: 'بلوف',
  SLIP_RESOLVED: 'حل‌شده',
}

// قرمز/نارنجی = یافتهٔ منفی؛ سبز/آبی = یافتهٔ مثبت

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

function ExamReport({ report, mode, onBackToDashboard, sessionIdProp }) {
  // معلمِ تناقض: کدام یافته باز است و آیا مودال نمایان است.
  const [contradictionOpen, setContradictionOpen] = useState(false)
  const [tutorFinding, setTutorFinding] = useState(null)
  // چک‌لیستِ گیمیفای‌شده: پیشرفت در localStorage می‌ماند (کلید به نشست گره دارد).
  const checklistKey = `fahmyar_checklist_${report.session_id ?? 'x'}`
  const [doneSuggestions, setDoneSuggestions] = useState(() => {
    try {
      const raw = localStorage.getItem(checklistKey)
      return new Set(raw ? JSON.parse(raw) : [])
    } catch {
      return new Set()
    }
  })
  const toggleSuggestion = (i) => {
    setDoneSuggestions((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      try {
        localStorage.setItem(checklistKey, JSON.stringify([...next]))
      } catch {
        /* حافظهٔ مرورگر پر — چک‌لیست فقط برای این نشست کار می‌کند */
      }
      return next
    })
  }

  const navigate = useNavigate()
  const handleBack = onBackToDashboard ?? (() => navigate(mode === 'teacher' ? '/staff' : '/dashboard'))
  const backLabel = mode === 'teacher' ? 'بازگشت به داشبورد مدرسه' : 'بازگشت به داشبورد'
  const dimensions = Array.isArray(report.dimensions) ? report.dimensions.filter((d) => d && !isEmptyDimension(d)) : []
  const perQuestion = report.per_question ?? []
  // «ابعاد فهم» فقط با شواهدِ واقعیِ ۵ مرحله‌ای معنا دارد؛ کارتِ خالی
  // («نامشخص») نشانهٔ ابهامِ دانش‌آموز نیست، نشانهٔ نبودِ تحلیل است.
  const stageDimensions = perQuestion
    .filter((q) => q && (q.status || q.cognitive_verdict || q.qualitative_feedback))
    .sort((a, b) => (Number(a.order) || 0) - (Number(b.order) || 0))
  const aiUsage = report.ai_usage && typeof report.ai_usage === 'object' ? report.ai_usage : null
  const openGears = stageDimensions.filter(
    (q) => String(q.missing_gear ?? '').trim().length > 0,
  )
  const rootCauses = report.root_causes ?? []
  const suggestions = cleanSuggestions(report.suggestions)
  const crossCheck = Array.isArray(report.cross_check_findings) ? report.cross_check_findings : []
  // نامِ مدلِ ارزیاب — از متادیتای کارنامه (بک‌اند: model_name)
  const modelName = String(
    report.model_name ?? (report.ai_usage?.models ?? [])[0] ?? '',
  ).trim()
  const stageDims = Array.isArray(report.stage_dimensions) ? report.stage_dimensions : []
  const mastery = report.mastery_status ?? null
  const personaTitle = report.persona_title ?? null
  const executiveSummary = report.executive_summary ?? null
  const mentorNote = report.mastery_note ?? null
  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleDateString('fa-IR', { dateStyle: 'long' })
    : ''

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── سربرگ گزارش ── */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-l from-brand-900 via-brand-800 to-emerald-700 p-6 text-white shadow-panel">
        {/* هالهٔ گوشه‌ها — عمق بدونِ تیرگیِ اضافه */}
        <span
          className="pointer-events-none absolute -left-16 -top-20 h-52 w-52 rounded-full bg-emerald-400/25 blur-3xl"
          aria-hidden="true"
        />
        <span
          className="pointer-events-none absolute -bottom-24 -right-10 h-56 w-56 rounded-full bg-teal-300/20 blur-3xl"
          aria-hidden="true"
        />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="flex items-center gap-2 text-[11px] font-bold text-emerald-200">
            <ClipboardList className="h-4 w-4" />
            گزارش تشخیصی آزمون جامع · {generatedAt}
          </p>
          <h1 className="mt-1.5 text-2xl font-black text-white drop-shadow-[0_2px_6px_rgba(0,0,0,0.18)] sm:text-3xl">{report.concept_name ?? 'مفهوم نامشخص'}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="chip bg-white/15 text-white ring-1 ring-white/25 backdrop-blur-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_6px_rgba(110,231,183,0.9)]" />
              تکمیل‌شده
            </span>
            <span className="chip bg-white/10 text-white/90 ring-1 ring-white/20">{toFarsiNumber(report.questions_answered ?? perQuestion.length)} سؤال تحلیل شد</span>
            {/* بجِ مدلِ ارزیاب — کاربر همیشه می‌داند کارنامه با چه مدلی ساخته شده */}
            {modelName && (
              <span
                className="chip inline-flex items-center gap-1.5 bg-white/95 text-brand-900 shadow-sm"
                dir="ltr"
                title="مدل هوش مصنوعی که این آزمون را تولید و ارزیابی کرده است"
              >
                <Cpu className="h-3.5 w-3.5 text-brand-700" />
                <span className="font-black">مدل ارزیاب:</span>
                <code className="font-mono text-[11px] font-bold">{modelName}</code>
              </span>
            )}
          </div>
        </div>
        <div className="no-print flex shrink-0 flex-col gap-2">
          <DownloadPdfButton sessionId={report.session_id} />
          <button onClick={() => window.print()} className="flex items-center justify-center gap-2 rounded-2xl border border-white/30 bg-white/10 px-5 py-3 text-[13px] font-black text-white backdrop-blur-sm transition hover:bg-white/20">
            <Printer className="h-5 w-5" />
            چاپ / دانلود گزارش
          </button>
          <button
            onClick={handleBack}
            className="flex items-center justify-center gap-2 rounded-2xl border border-white/30 bg-white/10 px-5 py-3 text-[13px] font-bold text-white backdrop-blur-sm transition hover:bg-white/20"
          >
            <ArrowRight className="h-5 w-5" />
            {backLabel}
          </button>
        </div>
        </div>
      </section>

      {/* ── کارنامهٔ اشعهٔ ایکس — حکمِ شناختی ── */}
      {(mastery || personaTitle || crossCheck.length > 0 || executiveSummary) && (
        <section className="card overflow-hidden p-0">
          {(() => {
            const st = MASTERY_STYLE[mastery] ?? MASTERY_STYLE.UNSTRUCTURED
            return (
              <div className={`relative overflow-hidden px-6 py-5 ${st.head}`}>
                {/* هالهٔ گوشه — همان نوارِ رنگی، ولی با عمق */}
                <span
                  className={`pointer-events-none absolute -left-12 -top-16 h-44 w-44 rounded-full blur-3xl ${st.aurora}`}
                  aria-hidden="true"
                />
                <div className="relative flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-[10px] font-black ${st.chipGhost}`}
                  >
                    کارنامهٔ اشعهٔ ایکس
                  </span>
                  <span className={`rounded-full px-2.5 py-1 text-[10px] font-black shadow-sm ${st.chip}`}>
                    {MASTERY_LABEL[mastery] ?? 'وضعیتِ نامشخص'}
                  </span>
                </div>
                {personaTitle && (
                  <h2 className="relative mt-2 text-xl font-black text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.15)] sm:text-2xl">
                    «{personaTitle}»
                  </h2>
                )}
                {executiveSummary && (
                  <p className="relative mt-2 max-w-3xl text-[13px] font-bold leading-8 text-white/95">
                    {executiveSummary}
                  </p>
                )}
              </div>
            )
          })()}

          {mentorNote && (
            <div className="border-b border-slate-100 bg-slate-50 px-6 py-3 text-[12px] font-bold leading-7 text-slate-700">
              {mentorNote}
            </div>
          )}

          <div className="p-6">
            <h3 className="flex items-center gap-2 text-[13px] font-black text-brand-950">
              <Search className="h-4 w-4 text-brand-600" />
              شکارِ تناقض — مقایسهٔ پاسخ‌ها با هم
            </h3>
            {crossCheck.length === 0 ? (
              <p className="mt-2 text-[12px] text-slate-500">تناقضِ روشنی میان پاسخ‌هایت پیدا نشد.</p>
            ) : (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {crossCheck.map((f, i) => (
                  <ContradictionCard
                    key={i}
                    finding={f}
                    onTeach={() => {
                      setTutorFinding({ type: 'contradiction', finding: f, findingIndex: i })
                      setContradictionOpen(true)
                    }}
                  />
                ))}
              </div>
            )}

            {perQuestion.some((q) => q.missing_gear) && (
              <div className="mt-4 rounded-2xl border border-amber-200/70 bg-gradient-to-br from-amber-100 via-amber-50 to-orange-50/60 p-4 shadow-sm">
                <p className="flex items-center gap-1.5 text-[12px] font-black text-amber-900">
                  <Puzzle className="h-3.5 w-3.5" /> گره‌های کلیدی برای تسلط کامل
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {perQuestion
                    .filter((q) => q.missing_gear)
                    .map((q, i) => (
                      <span
                        key={i}
                        title={faText(q.missing_gear, '')}
                        className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-amber-300/60 bg-gradient-to-l from-white to-amber-50 px-3 py-1.5 text-[11px] font-bold text-amber-900 shadow-sm transition hover:-translate-y-0.5 hover:border-amber-400 hover:shadow-md"
                      >
                        <Puzzle className="h-3 w-3 shrink-0 text-amber-500" />
                        <span className="truncate">
                          {q.stage_title || `مرحلهٔ ${toFarsiNumber(q.order ?? i + 1)}`}
                        </span>
                        <span className="text-amber-300">|</span>
                        <span className="truncate font-black">{faText(q.missing_gear, '')}</span>
                      </span>
                    ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── (الف) ابعاد فهم ──
          فقط زمانی رندر می‌شود که دادهٔ واقعیِ ۵ مرحله‌ای در per_question باشد.
          پیش‌تر وقتی تحلیلی نبود، همین‌جا پنج کارتِ «نامشخص» ساخته می‌شد و
          دانش‌آموز آن را «ابهام واقعی» می‌خواند؛ حالا معیار، وجودِ داده است. */}
      {/* ── (الف) حذف‌شده در فاز ۱۷ ──
          سکشنِ «ابعاد فهم — پنج مرحلهٔ زنجیره» (۱۰ باکسِ کوچک) عمداً حذف شد:
          هم نامِ متدولوژیِ داخلی را لو می‌داد، هم با «تحلیل کلی» که همان
          پنج بُعد را معنادارتر نشان می‌دهد هم‌پوشانی داشت. تنها منبعِ شواهدِ
          مرحله‌ای، سکشنِ «تحلیل کلی» است. */}

      {/* ── ابعاد فهم — تحلیل کلی ──
          پنج بُعدِ استاندارد با کلیدهای ثابت (conceptual_knowledge …). داده از
          report.stage_dimensions می‌آید که بک‌اند آن را از شواهدِ خودِ پنج مرحله
          می‌سازد؛ پس کلیدها هرگز با فرانت ناهمخوان نمی‌شوند و «نامشخص» فقط برای
          مرحله‌ای است که واقعاً بی‌پاسخ مانده. */}
      {stageDims.length > 0 && (
        <SectionCard Icon={Layers} title="ابعاد فهم — تحلیل کلی" tone="teal">
          <div className="grid gap-2 md:grid-cols-2">
            {stageDims.map((d, i) => {
              const st = String(d.status ?? 'not_assessed').toLowerCase()
              const style = DIM_STYLE[st] ?? DIM_STYLE.not_assessed
              return (
                <div key={d.key ?? i} className={`flex items-start gap-3 rounded-2xl border p-4 ${style.card}`}>
                  <span className={`mt-0.5 shrink-0 rounded-lg px-2 py-1 text-[10px] font-black ring-1 ${style.chip}`}>
                    {d.status_fa ?? style.label}
                  </span>
                  <div className="min-w-0">
                    <p className="text-[13px] font-black text-brand-950">
                      {DIM_LABEL[d.key] ?? d.label ?? 'بُعد فهم'}
                    </p>
                    <p className="mt-1 text-justify text-right text-[12px] leading-6 text-slate-600">
                      {faText(d.finding, style.fallback)}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </SectionCard>
      )}

      {/* ── (ب) تحلیل تفصیلی تک‌تک سوالات — کارت‌های ماژولار + معلمِ تعاملی ── */}
      <SectionCard Icon={FileText} title="تحلیل تفصیلی تک‌تک سوالات">
        <DetailedQuestions questions={perQuestion} sessionId={Number(report.session_id ?? sessionIdProp)} />
      </SectionCard>

      {/* ── (ج) تحلیل ریشه‌ای بدفهمی‌ها — گراف وابستگی مفاهیم (DAG) ── */}
      <SectionCard Icon={GitBranch} title="تحلیل ریشه‌ای بدفهمی‌ها — گراف وابستگی مفاهیم" tone="amber">
        <RootCauseDag target={report.concept_name ?? 'مفهوم هدف'} nodes={rootCauses} />
      </SectionCard>

      {/* ── (د) پیشنهادهای بهبود کیفی ── */}
      <SectionCard Icon={Lightbulb} title={mode === 'teacher' ? 'پیشنهادهای بهبود (برای برنامه‌ریزی معلم)' : 'پیشنهادهای بهبود — قدم‌به‌قدم'}>
        <ul className="space-y-2">
          {suggestions.map((sug, i) => {
            const done = doneSuggestions.has(i)
            return (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => toggleSuggestion(i)}
                  aria-pressed={done}
                  className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-right text-[13px] leading-7 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${
                    done
                      ? 'border-emerald-200 bg-gradient-to-l from-emerald-50 to-teal-50/40 text-emerald-900'
                      : 'border-brand-100 bg-gradient-to-l from-white to-brand-50/40 text-brand-950 hover:border-brand-300'
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border-2 transition-colors ${
                      done
                        ? 'border-emerald-500 bg-emerald-500 text-white'
                        : 'border-slate-300 bg-white text-transparent'
                    }`}
                  >
                    <CheckCircle2 className="h-4 w-4" strokeWidth={3} />
                  </span>
                  <span className={done ? 'line-through decoration-emerald-400/60' : ''}>
                    {faSuggestion(sug)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
        {suggestions.length > 0 && (
          <div className="mt-3 flex items-center gap-2">
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-gradient-to-l from-emerald-400 via-teal-400 to-brand-500 shadow-[0_0_8px_rgba(46,163,127,0.5)] transition-all duration-500"
                style={{ width: `${Math.round((doneSuggestions.size / suggestions.length) * 100)}%` }}
              />
            </div>
            <span className="shrink-0 text-[10px] font-black tabular-nums text-slate-500">
              {toFarsiNumber(doneSuggestions.size)} از {toFarsiNumber(suggestions.length)}
            </span>
          </div>
        )}
      </SectionCard>

      {/* ── موارد هنوز روشن‌نشده ──
          فقط گرهٔ کلیدیِ واقعی نمایش داده می‌شود. فهرستِ ساختگیِ
          «سؤال ۳ (نامشخص)» که از نبودِ تحلیل ساخته می‌شد، حذف شده است. */}
      {openGears.length > 0 && (
        <SectionCard Icon={HelpCircle} title="حلقه‌های مفقوده در یادگیری" tone="amber">
          <ul className="space-y-2">
            {openGears.map((g, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-2 rounded-2xl border border-amber-200/60 bg-gradient-to-l from-white to-amber-50/70 px-4 py-2.5 text-justify text-right text-[12px] leading-6 text-amber-950 shadow-sm"
              >
                {/* اصلِ مفهوم اول می‌آید — این چیزی است که دانش‌آموز باید یاد بگیرد.
                    نامِ مرحله فقط یک برچسبِ کوچک کنارش است، نه تیترِ جمله. */}
                <span className="min-w-0 flex-1 font-bold">
                  {faText(g.missing_gear, 'این بخش هنوز روشن نشده است.')}
                </span>
                <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-black text-amber-700 ring-1 ring-amber-200">
                  {faStageTitle(g, i)}
                </span>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* ── ردیابیِ مدل/هزینه (فقط برای معلم) ── */}
      {mode === 'teacher' && aiUsage && aiUsage.call_count > 0 && (
        <SectionCard Icon={ScanSearch} title="ردیابیِ مدل و هزینه (برای معلم)" tone="amber">
          <div className="grid gap-2 text-[12px] leading-7 text-slate-700 sm:grid-cols-2">
            <p>
              <span className="font-black text-slate-900">مدل: </span>
              <span dir="ltr" className="font-mono text-[11px]">
                {(aiUsage.models ?? []).join(' , ') || '—'}
              </span>
            </p>
            <p>
              <span className="font-black text-slate-900">فراخوانی: </span>
              {toFarsiNumber(aiUsage.call_count ?? 0)}
            </p>
            <p>
              <span className="font-black text-slate-900">توکن (ورودی + خروجی): </span>
              {toFarsiNumber(aiUsage.prompt_tokens ?? 0)} + {toFarsiNumber(aiUsage.completion_tokens ?? 0)}
              {' = '}
              {toFarsiNumber(aiUsage.total_tokens ?? 0)}
            </p>
            <p>
              <span className="font-black text-slate-900">هزینهٔ گزارش‌شده: </span>
              <span dir="ltr">${Number(aiUsage.total_cost_usd ?? 0).toFixed(6)}</span>
            </p>
          </div>
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

      {/* معلمِ تناقض — درلحظه، از /api/tutor/explain */}
      <LiveTutorModal
        open={contradictionOpen}
        target={tutorFinding}
        sessionId={Number(report.session_id ?? sessionIdProp)}
        onClose={() => setContradictionOpen(false)}
      />
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
    return <ExamReport report={report} mode={mode} onBackToDashboard={onBackToDashboard} sessionIdProp={sessionId} />
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

        <SectionCard Icon={HelpCircle} title="حلقه‌های مفقوده در یادگیری" tone="amber" className="lg:col-span-2">
          {unclear.length === 0 ? (
            <p className="flex items-center gap-2 text-[13px] font-bold text-emerald-800">
              <CheckCircle2 className="h-5 w-5" /> مورد مبهمی باقی نمانده است 🌱
            </p>
          ) : (
            <ul className="space-y-2">
              {unclear.map((u, i) => (
                <li key={i} className="rounded-2xl border border-amber-200/60 bg-white/70 px-4 py-2.5 text-justify text-right text-[12px] leading-6 text-amber-950">
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
            <ol className="mt-3 list-decimal space-y-1.5 pr-5 text-justify text-right text-[12px] leading-7 text-slate-600">
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
