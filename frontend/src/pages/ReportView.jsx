import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import DetailedQuestions, { ContradictionCard, LiveTutorModal } from '../components/cognitive/DetailedQuestions'
import {
  LearningGapsSection,
  RootCauseAnalysisSection,
} from '../components/cognitive/PrerequisiteSections'
import { UnifiedSectionHeader } from '../components/cognitive/UnifiedSectionHeader'
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
function SectionCard({
  Icon,
  title,
  tone = 'brand',
  subtitle,
  badgeText,
  children,
  className = '',
}) {
  const tones = {
    // لهجهٔ هر بخش متفاوت است ولی هر سه از خانوادهٔ سبزِ زغالی تا نیلی.
    brand: { accent: 'emerald', rail: 'from-primary via-primary/70 to-primary-soft' },
    amber: { accent: 'amber', rail: 'from-caution via-caution/70 to-caution-soft' },
    teal: { accent: 'indigo', rail: 'from-analytic via-analytic/70 to-analytic-soft' },
  }
  const st = tones[tone] ?? tones.brand
  return (
    <section
      /* سکشن‌های بزرگِ محتوایی بلند نمی‌شوند — hover-lift روی یک بلوکِ
          هزارپیکسلی حسِ «کارتِ کلیک‌شدنی» می‌دهد که دروغ است. */
      className={`group relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest ${className}`}
    >
      {/* ریلِ رنگیِ بخش — ۳px به‌جای ۱px تا روی بومِ آبی دیده شود */}
      <span
        className={`block h-[2px] w-full bg-gradient-to-l ${st.rail}`}
        aria-hidden="true"
      />
      <div className="p-5 md:p-6">
        <UnifiedSectionHeader
          icon={Icon}
          accentColor={st.accent}
          title={title}
          badgeText={badgeText}
          subtitle={subtitle}
        />
        {children}
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
/**
 * سه‌پلهٔ وضعیتِ هر بُعد — نه درصدِ ساختگی.
 *
 * داده فقط می‌گوید LIKELY_UNDERSTOOD / NEEDS_REVIEW / UNCLEAR است. ساختنِ
 * «۷۲٪» از این داده دروغ است؛ سه پله صادقانه همان چیزی است که می‌دانیم.
 */
const DIMENSION_TONE = {
  LIKELY_UNDERSTOOD: { label: 'رو به راه', steps: 3, text: 'text-primary', bar: 'bg-primary' },
  NEEDS_REVIEW: { label: 'نیازمندِ بازبینی', steps: 2, text: 'text-caution', bar: 'bg-caution' },
 UNCLEAR: { label: 'نامشخص', steps: 1, text: 'text-ink-faint', bar: 'bg-ink-faint' },
  INSUFFICIENT_EVIDENCE: { label: 'شاهدِ کافی نبود', steps: 1, text: 'text-ink-faint', bar: 'bg-ink-faint' },
}

/** نامِ فارسیِ ابعاد — نگاشتِ صریح تا کلیدِ خام به چشم نرسد. */
const DIMENSION_FA = {
  'دانش مفهومی': 'دانشِ مفهومی',
  'مقاومت در برابر دادهٔ انحرافی': 'مقاومت در برابر دادهٔ انحرافی',
  'استدلال علّی': 'استدلالِ علّی',
  'نقد استدلال': 'نقدِ استدلال',
  'انتقال ساده': 'انتقالِ ساده',
}
const dimensionFa = (name) => DIMENSION_FA[String(name ?? '')] ?? (name || 'بُعد فهم')

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
  // گرهٔ پیش‌نیاز هم از همان مودال استفاده می‌کند، با نوعِ متفاوت
  const [gapOpen, setGapOpen] = useState(false)
  const [tutorGap, setTutorGap] = useState(null)
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
  // اقدامِ بعدی — فقط اگر ارزیاب واقعاً نوشته باشد
  const nextStep = String(report?.next_step ?? '').trim()
  const stageDimensions = perQuestion
    .filter((q) => q && (q.status || q.cognitive_verdict || q.qualitative_feedback))
    .sort((a, b) => (Number(a.order) || 0) - (Number(b.order) || 0))
  const aiUsage = report.ai_usage && typeof report.ai_usage === 'object' ? report.ai_usage : null
  const suggestions = cleanSuggestions(report.suggestions)
  const crossCheck = Array.isArray(report.cross_check_findings) ? report.cross_check_findings : []
  // نامِ مدلِ ارزیاب — از متادیتای کارنامه (بک‌اند: model_name)
  const modelName = String(
    report.model_name ?? (report.ai_usage?.models ?? [])[0] ?? '',
  ).trim()
  const stageDims = Array.isArray(report.stage_dimensions) ? report.stage_dimensions : []
  const mastery = report.mastery_status ?? null
  // رنگِ حکم — برای بجِ خلاصه. نگاشت به رنگ‌های معناییِ توکنی.
  const verdict = {
    chip:
      mastery === 'MASTERED'
        ? 'bg-primary-soft text-primary-deep'
        : mastery === 'ILLUSION_OF_COMPETENCE'
        ? 'bg-danger-soft text-danger'
        : mastery === 'JARGON_DEPENDENT' || mastery === 'PARTIAL_FRAGMENTED'
        ? 'bg-caution-soft text-caution'
        : 'bg-slate-100 text-ink-soft',
  }
  const personaTitle = report.persona_title ?? null
  const executiveSummary = report.executive_summary ?? null
  const mentorNote = report.mastery_note ?? null
  const generatedAt = report.generated_at
    ? new Date(report.generated_at).toLocaleDateString('fa-IR', { dateStyle: 'long' })
    : ''

  return (
    <div className="relative isolate">
      {/* ── موتیفِ «ادامهٔ مسیر» ──
          سه هالهٔ blur-[130-140px] فاز ۲۶ این‌جا برداشته شد: فاز ۲۷ هاله و
          گرادیان را به‌عنوان «جایگزینِ طراحی» ممنوع کرده. جای‌شان یک بافتِ
          نقطه‌چینِ بسیار محو نشسته که همان حسِ «مسیرِ در جریان» را می‌دهد
          بدونِ اینکه لکهٔ رنگی روی صفحه بیندازد.

          با mask-image از بالا محو می‌شود تا به محتوای کارت‌ها نفوذ نکند. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 -z-10 opacity-[0.55] [mask-image:radial-gradient(ellipse_at_top,black,transparent_62%)]"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgb(31 106 85 / 0.16) 1px, transparent 0)',
          backgroundSize: '22px 22px',
        }}
      />

      <div className="animate-fade-up space-y-5">
      {/* ── نوارِ بالای کارنامه ──
          قبل از این، این بخش یک بلوکِ سرمه‌ایِ بزرگ با سه دکمهٔ عمودی بود
          که نیمی از صفحهٔ اول را می‌گرفت و فقط اطلاعاتِ تکراری داشت.
          حالا: یک نوارِ کوتاه — عنوان و شناسه در راست، عملیات در چپ.
          «نگاهی به کارنامه» در نگاهِ اول، نه بعد از اسکرول. */}
      <section className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white px-5 py-4 shadow-rest">
        {/* نوارِ لهجهٔ بالای کارت — نه پس‌زمینهٔ تمام‌عرض */}
        <span
          className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-l from-emerald-500 via-teal-400 to-emerald-300"
          aria-hidden="true"
        />
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          {/* عنوان + شناسه */}
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-bold text-ink-faint">
              <ClipboardList className="h-3.5 w-3.5" />
              کارنامهٔ فهم‌سنجی
              <span className="text-slate-300">·</span>
              <span>{generatedAt}</span>
            </div>
            <h1 className="mt-0.5 truncate text-[22px] font-black tracking-tight text-ink md:text-2xl">
              {report.concept_name ?? 'مفهوم نامشخص'}
            </h1>
          </div>

          {/* عملیات: افقی، کم‌حجم، یک اقدام اصلی */}
          <div className="no-print flex flex-wrap items-center gap-1.5 sm:gap-2">
            <DownloadPdfButton sessionId={report.session_id} />
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-ink-soft transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              <Printer className="h-4 w-4" />
              چاپ
            </button>
            <button
              onClick={handleBack}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-bold text-ink-soft transition hover:border-slate-300 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              <ArrowRight className="h-4 w-4" />
              {backLabel}
            </button>
          </div>
        </div>

        {/* متادیتا: چیزی که واقعاً هست، بدونِ بجِ تزئینی */}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-slate-100 pt-2.5 text-[11px] text-ink-faint">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
            {toFarsiNumber(report.questions_answered ?? perQuestion.length)} سؤال تحلیل شد
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Badge status={report.status} />
          </span>
          {modelName && !/^fake$/i.test(modelName) && (
            <span className="inline-flex items-center gap-1.5" dir="ltr" title="مدل هوش مصنوعیِ ارزیاب">
              <Cpu className="h-3 w-3" />
              <code className="font-mono text-[10px]">{modelName}</code>
            </span>
          )}
        </div>
      </section>

      {/* ══════════════════ خلاصهٔ تشخیصی ══════════════════
          این بخش جایگزینِ «کارنامهٔ اشعهٔ ایکس» است: قبلاً یک بلوکِ نارنجیِ
          تمام‌عرض با پاراگرافِ طولانی بود که تنها پیامش در سه خطِ آخر
          پیدا می‌شد.

          چیدمانِ تازه نامتقارن است و هر ستون کارِ خودش را می‌کند:
            ستونِ راست (۸/۱۲) → حکم + تیپ + جمع‌بندی
            ستونِ چپ  (۴/۱۲) → پنجرهٔ «کجا ایستاده‌ای» با نوارِ ابعاد

          نمودار فقط از ``dimensions`` واقعیِ همین آزمون ساخته می‌شود. اگر
          داده نبود، بخشِ نمودار رندر نمی‌شود — درصدِ ساختگی ممنوع. */}
      {(mastery || personaTitle || executiveSummary) && (
        <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest">
          <div className="grid lg:grid-cols-12">
            {/* ── ستونِ راست: حکم و روایت ── */}
            <div
              className={`relative p-5 md:p-7 ${
                dimensions.length > 0 ? 'lg:col-span-7 xl:col-span-8' : 'lg:col-span-12'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-black ${verdict.chip}`}
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" aria-hidden="true" />
                  {MASTERY_LABEL[mastery] ?? 'وضعیتِ نامشخص'}
                </span>
                {crossCheck.length > 0 && (
                  <span className="rounded-full bg-danger-soft px-2.5 py-1 text-[10px] font-black text-danger">
                    {toFarsiNumber(crossCheck.length)} تناقض یافت شد
                  </span>
                )}
              </div>

              {personaTitle && (
                <h2 className="mt-3 text-balance text-[22px] font-black leading-tight tracking-tight text-ink md:text-[26px]">
                  «{personaTitle}»
                </h2>
              )}

              {executiveSummary && (
                <p className="mt-2.5 text-justify text-right text-[13px] leading-8 text-ink-soft">
                  {executiveSummary}
                </p>
              )}

              {mentorNote && (
                <p className="mt-3 rounded-xl border-r-2 border-emerald-400 bg-primary-soft/60 px-3 py-2 text-justify text-right text-[12px] font-bold leading-7 text-ink">
                  {mentorNote}
                </p>
              )}
            </div>

            {/* ── ستونِ چپ: پنجرهٔ ابعاد ── */}
            {dimensions.length > 0 && (
              <aside className="border-t border-slate-100 bg-surface-muted p-5 md:p-7 lg:col-span-5 lg:border-r lg:border-t-0 xl:col-span-4">
                <h3 className="flex items-center gap-1.5 text-[11px] font-black text-ink-faint">
                  <Search className="h-3.5 w-3.5" />
                  کجا ایستاده‌ای
                </h3>
                <ul className="mt-3 space-y-2.5">
                  {dimensions.map((d, i) => {
                    const tone = DIMENSION_TONE[d.status] ?? DIMENSION_TONE.NEEDS_REVIEW
                    return (
                      <li key={i}>
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate text-[11px] font-bold text-ink">
                            {dimensionFa(d.dimension)}
                          </span>
                          <span className={`shrink-0 text-[10px] font-black ${tone.text}`}>
                            {tone.label}
                          </span>
                        </div>
                        {/* نوارِ ابعاد — سه پله، نه درصدِ ساختگی */}
                        <div className="mt-1 flex gap-1" aria-hidden="true">
                          {[0, 1, 2].map((step) => (
                            <span
                              key={step}
                              className={`h-1.5 flex-1 rounded-full ${
                                step < tone.steps ? tone.bar : 'bg-slate-200'
                              }`}
                            />
                          ))}
                        </div>
                        {d.finding && (
                          <p className="mt-1 line-clamp-2 text-[10px] leading-5 text-ink-faint">
                            {d.finding}
                          </p>
                        )}
                      </li>
                    )
                  })}
                </ul>
                <p className="mt-3 text-[10px] leading-5 text-ink-faint">
                  هر نوار از وضعیتِ ثبت‌شدهٔ همان بُعد در این آزمون ساخته شده است.
                </p>
              </aside>
            )}
          </div>

          {/* ── تناقض‌ها: مقایسه، نه دو کارتِ سؤال ── */}
          {crossCheck.length > 0 && (
            <div className="border-t border-slate-100 p-5 md:p-7">
              <h3 className="flex items-center gap-2 text-[12px] font-black text-ink">
                <Search className="h-4 w-4 text-danger" />
                جایی که دو جوابت با هم نمی‌خوانند
              </h3>
              {/* تک‌ستون: متنِ هر یافته طولانی است و در دو ستون، ارتفاعِ
                  نامتعادل و ستونِ خالیِ بلند می‌سازد. */}
              <div className="mt-3 grid gap-3">
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
            </div>
          )}
        </section>
      )}

      {/* ── (الف) حذف‌شده در فاز ۱۷ ──
          سکشنِ «ابعاد فهم — پنج مرحلهٔ زنجیره» (۱۰ باکسِ کوچک) عمداً حذف شد:
          هم نامِ متدولوژیِ داخلی را لو می‌داد، هم با «تحلیل کلی» که همان
          پنج بُعد را معنادارتر نشان می‌دهد هم‌پوشانی داشت. تنها منبعِ شواهدِ
          مرحله‌ای، سکشنِ «تحلیل کلی» است. */}

      {/* ── «ابعاد فهم — تحلیل کلی» حذف شد (فاز ۲۷) ──
          این سکشن پنج کارتِ دیگر از **همان** ``stage_dimensions`` می‌ساخت که
          خلاصهٔ تشخیصیِ بالای صفحه با نوارهای سه‌پله نشان می‌دهد. نتیجه، دو
          روایتِ متفاوت از یک داده بود: بالا «رو به راه» (سبز) و این‌جا
          «در حال رشد» (زرد) — همان بُعد، دو برچسبِ متناقض در یک صفحه.

          یک داده، یک نمایش. متنِ شاهدِ هر بُعد داخلِ همان خلاصه (با tooltip
          روی نوار) نگه داشته می‌شود، نه در کارتِ جداگانه. */}

      {/* ── (ب) تحلیل تفصیلی تک‌تک سوالات — کارت‌های ماژولار + معلمِ تعاملی ── */}
      <SectionCard
        Icon={FileText}
        title="کالبدشکافی سؤال‌به‌سؤال آزمون"
        subtitle="تحلیلِ عملکرد در ده مرحلهٔ شناختی، همراه با میزِ معلم برای هر گره"
      >
        <DetailedQuestions questions={perQuestion} sessionId={Number(report.session_id ?? sessionIdProp)} />
      </SectionCard>

      {/* ── (ج) ریشه‌یابی زنجیره‌ای — تمایزِ اصلیِ فهم‌یار ──
          ترتیب مهم است: اول «چطور به این خطا رسیدی» (زنجیره)، بعد
          «چه چیزی را تمرین کن» (گره‌ها)، بعد تحلیلِ تک‌تکِ سؤال‌ها.
          هر بخش اگر داده نداشته باشد، خودش را رندر نمی‌کند — باکسِ خالی
          «یافت نشد» ساخته نمی‌شود. */}
      <RootCauseAnalysisSection chains={report.root_cause_chains} />

      <LearningGapsSection
        gaps={report.learning_gaps}
        onTeach={(gap) => {
          setTutorGap(gap)
          setGapOpen(true)
        }}
      />

      {/* ══════════ برنامهٔ اقدام ══════════
          ── قاعده‌ای که قبلاً نقض می‌شد (فاز ۲۸) ──
          این بخش بی‌قید رندر می‌شد و برای جلسه‌هایی که ``suggestions`` نداشتند
          یک کارتِ سفیدِ کاملاً خالی می‌ساخت — همان «فضای خالیِ ناشی از ارتفاع
          ثابت» که اسپک ممنوع کرده.

          حالا:
            • اگر ``suggestions`` واقعیِ ارزیاب هست، همان فهرست می‌آید.
            • وگرنه اگر ``next_step`` دارد، به‌صورتِ یک قدمِ واحد می‌آید.
            • وگرنه کلِ بخش **حذف** می‌شود. کارتِ خالی ساخته نمی‌شود.
       */}
      {(suggestions.length > 0 || nextStep) && (
        <SectionCard
          Icon={Lightbulb}
          title={mode === 'teacher' ? 'پیشنهادهای بهبود (برای برنامه‌ریزی معلم)' : 'قدمِ بعدی تو'}
          tone="brand"
        >
          {suggestions.length > 0 ? (
            <ul className="space-y-1.5">
              {suggestions.map((sug, i) => {
                const done = doneSuggestions.has(i)
                return (
                  <li key={i}>
                    <button
                      type="button"
                      onClick={() => toggleSuggestion(i)}
                      aria-pressed={done}
                      className={`flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-right text-[12px] leading-7 transition ${
                        done
                          ? 'border-primary/30 bg-primary-soft/60 text-primary-deep'
                          : 'border-slate-200 bg-white text-ink hover:border-primary/40 hover:bg-surface-muted'
                      }`}
                    >
                      <span
                        className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                          done ? 'border-primary bg-primary text-white' : 'border-slate-300 bg-white text-transparent'
                        }`}
                      >
                        <CheckCircle2 className="h-3 w-3" strokeWidth={3.5} />
                      </span>
                      <span className={`text-justify ${done ? 'line-through decoration-primary/40' : ''}`}>
                        {faSuggestion(sug)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-justify text-right text-[12.5px] leading-8 text-ink-soft">{nextStep}</p>
          )}

          {suggestions.length > 0 && (
            <div className="mt-3 flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-300"
                  style={{ width: `${Math.round((doneSuggestions.size / suggestions.length) * 100)}%` }}
                />
              </div>
              <span className="shrink-0 text-[10px] font-black tabular-nums text-ink-faint">
                {toFarsiNumber(doneSuggestions.size)} از {toFarsiNumber(suggestions.length)}
              </span>
            </div>
          )}
        </SectionCard>
      )}

      {/* ── حذف‌شده در فاز ۲۰ ──
          بلوکِ فهرستِ کمبودها (فاز ۲۰) حذف شد. برچسب‌هایی مثل
          «پل بین مشاهدهٔ ظاهری…» برای دانش‌آموز مبهم بودند و همان پیام را
          تکرار می‌کردند که کارتِ هر سؤال از قبل می‌گوید. جمع‌بندیِ پایانی
          حالا «پیشنهادهای بهبود — قدم‌به‌قدم» است: یک فهرستِ عملی، نه
          فهرستِ کمبودها. */}

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

      {/* معلمِ گرهٔ پیش‌نیاز — همان مودال، نوعِ متفاوت */}
      <LiveTutorModal
        open={gapOpen}
        target={tutorGap ? { type: 'learning_gap', gap: tutorGap } : null}
        sessionId={Number(report.session_id ?? sessionIdProp)}
        onClose={() => setGapOpen(false)}
      />
      </div>
    </div>
  )
}


/**
 * کارنامهٔ قدیمی — اعلامِ صادقانه، نه نمایشِ گمراه‌کننده.
 *
 * چرا این کامپوننت وجود دارد: پیش از این، هر پاسخی که فیلدِ ``exam`` نداشت
 * بی‌صدا از مسیرِ ``ReportBody`` (کارنامهٔ پیش از آزمونِ ۱۰ سؤالی) رندر
 * می‌شد. نتیجه، صفحه‌ای بود با «مفهوم نامشخص» و «مشاهدات (چه چیزی دیدیم؟)»
 * که هیچ‌کدام از بخش‌های تازه را نداشت — و کاربر فکر می‌کرد کارنامه‌اش
 * همین است، در حالی که در واقع دادهٔ درستی به فرانت نرسیده بود.
 *
 * این صفحه سه چیز را می‌گوید: چه اتفاقی افتاده، چرا بخش‌های تحلیلی نیست، و
 * قدمِ بعدی چیست.
 */
function LegacyReportNotice({ report, onBack, backLabel }) {
  const conceptName = report?.concept_name ?? report?.sections?.['موضوع بررسی']
  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest">
        <span className="block h-1 w-full bg-gradient-to-l from-amber-300 via-orange-300 to-calm-400" aria-hidden="true" />
        <div className="p-6 md:p-8">
          <div className="flex items-start gap-3">
            <span className="flex shrink-0 items-center justify-center rounded-2xl bg-amber-500/10 p-2.5 text-amber-600 ring-4 ring-amber-500/20">
              <AlertTriangle className="h-5 w-5" strokeWidth={2.2} />
            </span>
            <div className="min-w-0">
              <h2 className="text-[16px] font-black text-slate-900">
                این نشست کارنامهٔ آزمونِ تشخیصی ندارد
              </h2>
              <p className="mt-1.5 text-justify text-right text-[12px] leading-7 text-slate-600">
                نشستی که باز کردی از نسخهٔ قدیمیِ گزارش است. تحلیلِ سؤال‌به‌سؤال،
                ریشه‌یابی زنجیره‌ای و نقشهٔ راه ترمیم فقط برای آزمون‌های ده‌سؤالیِ
                فهم‌سنجی ساخته می‌شوند.
              </p>
              {conceptName && (
                <p className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-[12px] font-bold text-slate-700">
                  موضوعِ ثبت‌شده: {conceptName}
                </p>
              )}
              <p className="mt-3 text-justify text-right text-[12px] leading-7 text-slate-500">
                برای دیدنِ بخش‌های کامل، یک آزمونِ تازه شروع کن — کارنامهٔ آن با
                تحلیلِ گام‌به‌گام ساخته می‌شود.
              </p>
              <button
                type="button"
                onClick={onBack}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-[12px] font-black text-white shadow-sm transition-all hover:-translate-y-0.5 hover:bg-indigo-600 hover:shadow-md active:translate-y-0"
              >
                <ArrowRight className="h-4 w-4" />
                {backLabel || 'بازگشت به داشبورد'}
              </button>
            </div>
          </div>
        </div>
      </section>
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
      .then(({ data }) => {
        if (!alive) return
        // ── گاردِ شکلِ پاسخ ──
        // اگر پروکسی/سرور به‌جای JSON، HTML برگرداند (مثلاً SPA fallback یا
        // صفحهٔ ورودِ یک CDN)، axios آن را با status 200 می‌دهد و این‌جا
        // ``report.exam`` تهی می‌شود؛ نتیجه: بی‌صدا کارنامهٔ قدیمی می‌افتد و
        // کاربر فکر می‌کند کارنامه‌اش همین است. یک اپلیکیشنِ استاتیک بدونِ
        // پروکسیِ /api دقیقاً همین را تجربه می‌کند.
        const looksLikeReport =
          data && typeof data === 'object' && !Array.isArray(data) &&
          ('exam' in data || 'sections' in data || 'concept_name' in data)
        if (!looksLikeReport) {
          setError(
            'پاسخِ سرور قابلِ خواندن نبود. اگر نسخهٔ نصب‌شده را مستقیم باز کرده‌ای، ' +
              'باید پشتِ سروری اجرا شود که /api را به بک‌اند وصل می‌کند.',
          )
          return
        }
        setReport(data)
      })
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

  // ══════════════════ دروازهٔ رندر ══════════════════
  //
  // ── باگِ «کارنامهٔ ناقص» (فاز ۲۸) — ریشهٔ واقعی ──
  //
  // شرطِ این‌جا قبلاً ``if (report?.exam)`` بود. یعنی کارنامهٔ کامل فقط برای
  // جلسه‌های آزمونِ ده‌سؤالی رندر می‌شد و هر چیزِ دیگری — حتی وقتی
  // ``per_question`` پنج حکمِ واقعی و ``cross_check_findings`` سه تناقضِ
  // واقعی داشت — به ``LegacyReportNotice`` می‌افتاد: صفحهٔ «این نشست
  // کارنامه ندارد».
  //
  // مهم‌تر: ``exam`` یک کلیدِ **اختیاری** است که فقط ``build_exam_report``
  // تولید می‌کند. ``build_report`` (مسیرِ ارزیابیِ کل‌نگر) هرگز آن را
  // نمی‌سازد، هرچند همان داده‌های کارنامه را دارد. پس معیارِ «کارنامه بودن»
  // نباید وجودِ ``exam`` باشد؛ باید وجودِ **تحلیل** باشد:
  // ``per_question`` یا ``dimensions`` یا جمع‌بندی.
  //
  // این همان دلیلی است که دانش‌آموز در کارنامه «نامشخص» می‌دید: هیچ‌کدام از
  // این داده‌ها به کامپوننتِ کارنامه نمی‌رسید.
  const hasPerQuestion = Array.isArray(report?.per_question) && report.per_question.length > 0
  const hasDimensions = Array.isArray(report?.dimensions) && report.dimensions.length > 0
  const hasNarrative = Boolean(
    String(report?.persona_title ?? '').trim() ||
      String(report?.executive_summary ?? '').trim() ||
      (Array.isArray(report?.cross_check_findings) && report.cross_check_findings.length > 0),
  )

  if (hasPerQuestion || hasDimensions || hasNarrative) {
    return <ExamReport report={report} mode={mode} onBackToDashboard={onBackToDashboard} sessionIdProp={sessionId} />
  }

  // ── مسیرِ کارنامهٔ قدیمی ──
  //
  // ── باگِ «کارنامهٔ ناقص» (فاز ۲۸) ──
  // معیارِ قبلی ``!report.exam && !report.per_question`` بود و هر گزارشی را
  // که ``per_question`` نداشت به این صفحه می‌فرستاد. غافل از این‌که آن
  // شرط با ``!report.per_question`` **آرایهٔ خالی** را هم می‌گرفت، درحالی‌که
  // بک‌اند برای جلسه‌های ارزیابیِ کل‌نگر، ``per_question`` را با مصادیقِ
  // واقعی برمی‌گرداند و فقط ``exam`` ندارد.
  //
  // نتیجه: کارنامه‌ای که تیپ، جمع‌بندی، پنج حکمِ سؤال‌به‌سؤال و سه تناقضِ
  // واقعی داشت، به یک صفحهٔ متنیِ خالی می‌افتاد — همان «نامشخص» و
  // نوارهای بی‌داده‌ای که در تصویر دیده شد.
  //
  // ── گزارش متنیِ قدیمی ──
  //
  // این شاخه (~۱۳۰ خط) با کلاس‌های منسوخِ ``card`` و ``bg-brand-50`` رندر
  // می‌شد و هیچ‌کدام از قواعدِ فاز ۲۷/۲۸ را رعایت نمی‌کرد: هدرِ دکمه‌های
  // عمودی، دو کارتِ هم‌شکل، بخشِ «وضعیت گزاره‌های هسته‌ای» که برای این
  // جلسه‌ها همیشه خالی بود.
  //
  // با اصلاحِ ``build_report`` (پایینِ همین فاز) این جلسه‌ها دیگر بدونِ
  // ``per_question`` نمی‌آیند و تا وقتی داده دارند به ``ExamReport`` می‌روند.
  // فقط جلسه‌هایی که واقعاً هیچ تحلیلِ ساختاریافته‌ای ندارند به
  // ``LegacyReportNotice`` می‌رسند — و آن‌ها هم نباید صفحهٔ «کارنامه» را
  // جعل کنند.
  return <LegacyReportNotice report={report} onBack={handleBack} backLabel={backLabel} />
}
