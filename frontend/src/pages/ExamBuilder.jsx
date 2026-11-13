import { useEffect, useMemo, useState } from 'react'
import {
  ClipboardEdit,
  Sigma,
  Atom,
  FlaskConical,
  Leaf,
  Shapes,
  Binary,
  Timer,
  Info,
  Smile,
  Meh,
  Flame,
  Rocket,
  Wand2,
  Loader2,
  FileDown,
  FileText,
  ChevronDown,
  Percent,
  Trash2,
  ArrowUp,
  ArrowDown,
  Check,
  CheckCircle2,
  RotateCcw,
} from 'lucide-react'
import { toFarsiNumber } from '../utils/faNumbers'
import client, { friendlyError } from '../api/client'

const FIELDS = [
  { id: 'math', label: 'ریاضی', Icon: Sigma, grad: 'from-indigo-500 to-blue-600' },
  { id: 'tajrobi', label: 'تجربی', Icon: Leaf, grad: 'from-emerald-500 to-green-600' },
]

// لیست دروس — دقیقاً بر اساس ترکیب «رشته × پایه» (محل منبع حقیقتِ UI آزمون‌ساز)
const MATH_SUBJECTS_10 = [
  { id: 'math', label: 'ریاضی', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const MATH_SUBJECTS_11 = [
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'statistics', label: 'آمار و احتمال', Icon: Percent },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const MATH_SUBJECTS_12 = [ // دوازدهم و جامع
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'discrete', label: 'گسسته', Icon: Binary },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const EXPERIMENTAL_SUBJECTS = [ // تجربی — همهٔ پایه‌ها
  { id: 'biology', label: 'زیست‌شناسی', Icon: Leaf },
  { id: 'math', label: 'ریاضیات', Icon: Sigma },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
// «جامع» = اجتماعِ همهٔ دروس دهم، یازدهم و دوازدهمِ همان رشته — بدون تکراری
const COMPREHENSIVE_MATH = [
  { id: 'math', label: 'ریاضی', Icon: Sigma },
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'statistics', label: 'آمار و احتمال', Icon: Percent },
  { id: 'discrete', label: 'گسسته', Icon: Binary },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const dedupeById = (list) => list.filter((item, i) => list.findIndex((x) => x.id === item.id) === i)
const subjectsFor = (field, grade) => {
  const isComprehensive = grade === 'comprehensive' || grade === 'جامع'
  if (field === 'math' || field === 'ریاضی') {
    if (isComprehensive) {
      return dedupeById([...MATH_SUBJECTS_10, ...MATH_SUBJECTS_11, ...MATH_SUBJECTS_12])
    }
    if (grade === '10' || grade === 'دهم') return MATH_SUBJECTS_10
    if (grade === '11' || grade === 'یازدهم') return MATH_SUBJECTS_11
    return MATH_SUBJECTS_12
  }
  return dedupeById([...EXPERIMENTAL_SUBJECTS, ...EXPERIMENTAL_SUBJECTS, ...EXPERIMENTAL_SUBJECTS])
}

// درخت سرفصل‌های ایران (Mock) — برای پیکربندی per-درس سؤال‌ها (پشتیبانی از نام فارسی و slug)
const _MATH_CHAPTERS = [
  'فصل ۱: مجموعه، الگو و دنباله',
  'فصل ۲: مثلثات',
  'فصل ۳: توان‌های گویا و عبارت‌های جبری',
  'فصل ۴: معادلهٔ درجهٔ دوم و کاربردها',
  'فصل ۵: تابع و معادلهٔ درجهٔ دوم (پیشرفته)',
  'فصل ۶: حد و پیوستگی',
]
const _CALCULUS_CHAPTERS = [
  'فصل ۱: دنباله و سری‌های حسابی و هندسی',
  'فصل ۲: تابع و انواع آن',
  'فصل ۳: حد، پیوستگی و مجانب',
  'فصل ۴: مشتق و قواعد مشتق‌گیری',
  'فصل ۵: کاربردهای مشتق',
  'فصل ۶: انتگرال و کاربردهای آن',
]
const _GEOMETRY_CHAPTERS = [
  'فصل ۱: خطوط و زوایا',
  'فصل ۲: چندضلعی‌ها و مساحت',
  'فصل ۳: قضیهٔ تالس و تشابه',
  'فصل ۴: مثلث و دایره',
  'فصل ۵: دایره و خط',
  'فصل ۶: تبدیل‌های هندسی و بردار',
]
const _DISCRETE_CHAPTERS = [
  'فصل ۱: مبانی شمارش',
  'فصل ۲: آشنایی با نظریهٔ اعداد',
  'فصل ۳: الگوریتم‌ها و فلوچارت',
  'فصل ۴: گراف و مدل‌سازی',
  'فصل ۵: ترکیب و جایگشت',
]
const _STATISTICS_CHAPTERS = [
  'فصل ۱: آمار توصیفی و نمایش داده‌ها',
  'فصل ۲: احتمال در یک مرحلهٔ ساده',
  'فصل ۳: متغیر تصادفی و توزیع‌های آن',
  'فصل ۴: توزیع نرمال و کاربردها',
  'فصل ۵: برآورد و استنباط آماری',
]
const _PHYSICS_CHAPTERS = [
  'فصل ۱: فیزیک و اندازه‌گیری',
  'فصل ۲: کار، انرژی و توان',
  'فصل ۳: فشار و ویژگی‌های مواد',
  'فصل ۴: دما و گرما',
  'فصل ۵: الکتریسیتهٔ ساکن و جریان الکتریکی',
  'فصل ۶: مغناطیس و القای الکترومغناطیسی',
]
const _CHEMISTRY_CHAPTERS = [
  'فصل ۱: کیهان زادگاه الفبای هستی',
  'فصل ۲: ردپای گازها در زندگی',
  'فصل ۳: آب؛ آهنگِ زندگی',
  'فصل ۴: قدرِ هدایای زمینی را بدانیم',
  'فصل ۵: در پیِ غذای سالم',
  'فصل ۶: شیمی آلی و پلیمرها',
]
const _BIOLOGY_CHAPTERS = [
  'فصل ۱: مولکول‌های زیستی',
  'فصل ۲: تنظیم عصبی و حواس',
  'فصل ۳: تنظیم هورمونی و تولیدمثل',
  'فصل ۴: ژنتیک و وراثت',
  'فصل ۵: گیاهان و فتوسنتز',
  'فصل ۶: زیست‌فناوری و کاربردهای آن',
]

const CURRICULUM_TREE = {
  'ریاضی ۱': _MATH_CHAPTERS,
  'ریاضی ۲': _MATH_CHAPTERS,
  'ریاضی ۳': _MATH_CHAPTERS,
  'ریاضی': _MATH_CHAPTERS,
  'ریاضیات': _MATH_CHAPTERS,
  'حسابان ۱': _CALCULUS_CHAPTERS,
  'حسابان ۲': _CALCULUS_CHAPTERS,
  'حسابان': _CALCULUS_CHAPTERS,
  'هندسه ۱': _GEOMETRY_CHAPTERS,
  'هندسه ۲': _GEOMETRY_CHAPTERS,
  'هندسه ۳': _GEOMETRY_CHAPTERS,
  'هندسه': _GEOMETRY_CHAPTERS,
  'ریاضیات گسسته': _DISCRETE_CHAPTERS,
  'گسسته': _DISCRETE_CHAPTERS,
  'آمار و احتمال': _STATISTICS_CHAPTERS,
  'فیزیک ۱': _PHYSICS_CHAPTERS,
  'فیزیک ۲': _PHYSICS_CHAPTERS,
  'فیزیک ۳': _PHYSICS_CHAPTERS,
  'فیزیک': _PHYSICS_CHAPTERS,
  'شیمی ۱': _CHEMISTRY_CHAPTERS,
  'شیمی ۲': _CHEMISTRY_CHAPTERS,
  'شیمی ۳': _CHEMISTRY_CHAPTERS,
  'شیمی': _CHEMISTRY_CHAPTERS,
  'زیست‌شناسی ۱': _BIOLOGY_CHAPTERS,
  'زیست‌شناسی ۲': _BIOLOGY_CHAPTERS,
  'زیست‌شناسی ۳': _BIOLOGY_CHAPTERS,
  'زیست‌شناسی': _BIOLOGY_CHAPTERS,
  math: _MATH_CHAPTERS,
  calculus: _CALCULUS_CHAPTERS,
  geometry: _GEOMETRY_CHAPTERS,
  discrete: _DISCRETE_CHAPTERS,
  statistics: _STATISTICS_CHAPTERS,
  physics: _PHYSICS_CHAPTERS,
  chemistry: _CHEMISTRY_CHAPTERS,
  biology: _BIOLOGY_CHAPTERS,
}

const FIELD_LABELS = { math: 'ریاضی', tajrobi: 'تجربی' }
const FIELD_PRINT_LABELS = { math: 'ریاضی و فیزیک', tajrobi: 'علوم تجربی' }

const GRADES = [
  { id: '10', label: 'دهم' },
  { id: '11', label: 'یازدهم' },
  { id: '12', label: 'دوازدهم' },
  { id: 'comprehensive', label: 'جامع' },
]
const GRADE_LABELS = Object.fromEntries(GRADES.map((g) => [g.id, g.label]))

const QUESTION_TYPES = [
  { id: 'mixed', label: 'نامشخص / ترکیبی' },
  { id: 'conceptual', label: 'مفهومی' },
  { id: 'recall', label: 'حفظی' },
  { id: 'computational', label: 'محاسباتی' },
  { id: 'problem', label: 'مسئله' },
]
const QUESTION_TYPE_LABELS = Object.fromEntries(QUESTION_TYPES.map((t) => [t.id, t.label]))

const TIME_PRESETS = [45, 60, 75, 100, 120]
const DIFFICULTY_OPTIONS = [
  { id: 'easy', label: 'آسان', desc: 'سؤال‌های مستقیم و پایه‌ای', Icon: Smile },
  { id: 'medium', label: 'متوسط', desc: 'استاندارد کنکور', Icon: Meh },
  { id: 'hard', label: 'سخت', desc: 'عمیق و تحلیلی', Icon: Flame },
  { id: 'challenging', label: 'چالش‌برانگیز', desc: 'بالاتر از کنکور', Icon: Rocket },
]
const DIFFICULTY_LABELS = Object.fromEntries(DIFFICULTY_OPTIONS.map((d) => [d.id, d.label]))

const GEN_STEPS = [
  'در حال طراحی سؤال‌های چهارگزینه‌ای…',
  'در حال تنظیم دام‌های حلال هر سؤال…',
  'در حال چینش دفترچه و کلید پاسخنامه…',
]

const DRAFT_KEY = 'fahmyar_exam_drafts'

const fmtFa = (n) => toFarsiNumber(Number(n).toLocaleString('fa-IR'))
const loadDrafts = () => {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]')
  } catch {
    return []
  }
}
const loadGrade = () => {
  try {
    const raw = String(localStorage.getItem('fahmyar_grade') || '11')
    return GRADE_LABELS[raw] ? raw : '11'
  } catch {
    return '11'
  }
}
const loadField = () => {
  try {
    const raw = localStorage.getItem('fahmyar_field') || 'math'
    return raw === 'tajrobi' ? 'tajrobi' : 'math'
  } catch {
    return 'math'
  }
}

export default function ExamBuilder({ embedded = false }) {
  // ── فرم مرحلهٔ ۱ ──
  const [field, setField] = useState(loadField)                // math | tajrobi
  const [grade, setGradeState] = useState(loadGrade)           // 10 | 11 | 12 | comprehensive
  const [selectedSubjects, setSelectedSubjects] = useState(() => subjectsFor(loadField(), loadGrade()).map((x) => x.id))
  // پیکربندیِ هر درس: تعداد سؤال + فصل‌های هدف (از درخت سرفصل‌ها)
  const [subjectConfigs, setSubjectConfigs] = useState(() => {
    const init = {}
    subjectsFor(loadField(), loadGrade()).forEach((o) => {
      init[o.id] = { count: 2, topics: [] }
    })
    return init
  })
  const [aiPercentage, setAiPercentage] = useState(100) // درصد سؤالات تولیدی هوش مصنوعی؛ بقیه = بانک آزمون
  const [questionType, setQuestionType] = useState('mixed')
  const [customPrompt, setCustomPrompt] = useState('')
  const [difficulty, setDifficulty] = useState('medium')
  const [duration, setDuration] = useState(75)
  const [title, setTitle] = useState('')
  const [schoolName, setSchoolName] = useState(() => {
    try {
      return localStorage.getItem('fahmyar_school_name') || 'مدرسهٔ نمونه'
    } catch {
      return 'مدرسهٔ نمونه'
    }
  })

  // ── گام دوم: پیش‌نمایش و ویرایش ──
  const [step, setStep] = useState('form')                     // form | preview
  const [questions, setQuestions] = useState([])
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [genStep, setGenStep] = useState(0)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [notice, setNotice] = useState('')
  const [drafts, setDrafts] = useState(loadDrafts)             // پیش‌نویس‌های قدیمی (فقط مشاهده/حذف)

  const syncConfigs = (ids) =>
    setSubjectConfigs((prev) => {
      const next = {}
      ids.forEach((id) => {
        next[id] = prev[id] ?? { count: 2, topics: [] }
      })
      return next
    })

  const setGrade = (g) => {
    setGradeState(g)
    const ids = subjectsFor(field, g).map((x) => x.id)
    setSelectedSubjects(ids)
    syncConfigs(ids)
    try {
      localStorage.setItem('fahmyar_grade', g)
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }
  const setFieldPersist = (f) => {
    setField(f)
    const ids = subjectsFor(f, grade).map((x) => x.id)
    setSelectedSubjects(ids)
    syncConfigs(ids)
    try {
      localStorage.setItem('fahmyar_field', f)
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }

  const availableSubjects = useMemo(() => subjectsFor(field, grade), [field, grade])
  const subjectOptions = availableSubjects
  const selectedOptions = availableSubjects.filter((s) => selectedSubjects.includes(s.id))
  const subjectsLabel = selectedOptions.map((s) => s.label).join('، ')
  const toggleSubject = (id) => {
    const next = selectedSubjects.includes(id) ? selectedSubjects.filter((x) => x !== id) : [...selectedSubjects, id]
    setSelectedSubjects(next)
    syncConfigs(next)
  }
  const updateSubjectCount = (id, raw) =>
    setSubjectConfigs((prev) => {
      const n = Math.max(1, Math.min(20, Number.parseInt(raw, 10) || 1))
      return { ...prev, [id]: { count: n, topics: prev[id]?.topics ?? [] } }
    })
  const toggleSubjectTopic = (id, chapter) =>
    setSubjectConfigs((prev) => {
      const cur = prev[id] ?? { count: 2, topics: [] }
      const topics = cur.topics.includes(chapter) ? cur.topics.filter((t) => t !== chapter) : [...cur.topics, chapter]
      return { ...prev, [id]: { count: cur.count, topics } }
    })
  // مجموع سؤالات از پیکربندیِ هر درس
  const subjectConfigsPayload = selectedOptions.map((o) => ({
    subject: o.id,
    count: Math.max(1, Math.min(20, Number(subjectConfigs[o.id]?.count) || 2)),
    topics: subjectConfigs[o.id]?.topics ?? [],
  }))
  const totalCount = subjectConfigsPayload.reduce((sum, c) => sum + c.count, 0)

  useEffect(() => {
    if (!generating) return undefined
    const t = window.setInterval(() => setGenStep((s) => (s + 1) % GEN_STEPS.length), 750)
    return () => window.clearInterval(t)
  }, [generating])

  // هر تغییری در لیست سؤال‌ها، PDF قبلی را باطل می‌کند
  useEffect(() => {
    setPdfUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [questions])

  const removeDraft = (id) => {
    const next = drafts.filter((d) => d.id !== id)
    setDrafts(next)
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(next))
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }

  const validate = () => {
    if (selectedSubjects.length === 0) return 'حداقل یک درس را انتخاب کنید.'
    if (totalCount > 60) return 'مجموع سؤالات نباید بیشتر از ۶۰ سؤال باشد.'
    if (totalCount < 1) return 'تعداد سؤالات هر درس حداقل ۱ سؤال است.'
    if (!duration || duration < 10) return 'زمان آزمون باید حداقل ۱۰ دقیقه باشد.'
    return ''
  }

  // ── مرحلهٔ ۱ → تولید پیش‌نمایش (JSON فقط؛ بدون PDF) ──
  const generatePreview = async () => {
    const err = validate()
    if (err) return setNotice(`⚠️ ${err}`)
    setNotice('')
    setGenStep(0)
    setGenerating(true)
    try {
      const { data } = await client.post('/api/teacher/generate-exam-preview', {
        field,
        grade,
        subjects: selectedSubjects,
        subject_configs: subjectConfigsPayload,
        ai_percentage: aiPercentage,
        topic: null,
        question_type: questionType,
        difficulty,
        count: totalCount,
        custom_prompt: customPrompt.trim(),
      })
      const list = Array.isArray(data?.questions) ? data.questions : []
      if (list.length === 0) {
        setNotice('⚠️ هوش مصنوعی سؤالِ معتبری برنگرداند؛ دوباره تلاش کنید.')
        return
      }
      setQuestions(list)
      setStep('preview')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (error) {
      let message = friendlyError(error)
      try {
        if (typeof error?.response?.data?.detail === 'string') message = error.response.data.detail
      } catch {
        /* همان پیام عمومی نمایش داده می‌شود */
      }
      setNotice(`⚠️ ${message}`)
    } finally {
      setGenerating(false)
    }
  }

  // ── ویرایش لیست سؤال‌ها ──
  const removeQuestion = (id) => setQuestions((prev) => prev.filter((q) => q.id !== id))
  const moveQuestion = (index, delta) =>
    setQuestions((prev) => {
      const target = index + delta
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.splice(target, 0, item)
      return next
    })

  // ── مرحلهٔ ۲ → تأیید و دانلود PDF نهایی (تگ منبع در PDF چاپ نمی‌شود) ──
  const confirmAndDownload = async () => {
    if (questions.length === 0) return setNotice('⚠️ حداقل یک سؤال باید باقی بماند.')
    setNotice('')
    setDownloading(true)
    try {
      const { data } = await client.post(
        '/api/teacher/generate-exam-pdf',
        {
          title: title.trim(),
          school_name: schoolName.trim() || 'مدرسهٔ نمونه',
          grade,
          major: FIELD_PRINT_LABELS[field],
          subject_label: subjectsLabel,
          topic: '',
          duration_minutes: duration,
          difficulty,
          questions: questions.map((q, i) => ({
            id: i + 1,
            text: q.text,
            options: q.options,
            correct_answer: q.correct_answer,
            source_tag: q.source_tag || '',
            explanation: q.explanation || '',
          })),
        },
        { responseType: 'blob', timeout: 180000 },
      )
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
      setPdfUrl(URL.createObjectURL(data))
      setNotice('✓ PDF نهایی ساخته شد؛ تگ منابع در آن چاپ نشده است.')
    } catch (error) {
      let message = friendlyError(error)
      try {
        const blob = error?.response?.data
        if (blob instanceof Blob) {
          const parsed = JSON.parse(await blob.text())
          if (typeof parsed?.detail === 'string') message = parsed.detail
        }
      } catch {
        /* همان پیام عمومی نمایش داده می‌شود */
      }
      setNotice(`⚠️ ${message}`)
    } finally {
      setDownloading(false)
    }
  }

  const difficultyLabel = DIFFICULTY_LABELS[difficulty] ?? 'متوسط'
  const questionTypeLabel = QUESTION_TYPE_LABELS[questionType] ?? 'نامشخص / ترکیبی'

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── سربرگ صفحه ── */}
      {!embedded && (
        <section className="relative overflow-hidden rounded-2xl border border-brand-800/50 bg-gradient-to-bl from-brand-800 via-brand-900 to-brand-950 p-6 text-brand-50 shadow-lift sm:p-7">
          <div aria-hidden className="pointer-events-none absolute -left-16 -top-16 h-56 w-56 rounded-full bg-brand-400/20 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -bottom-14 left-1/3 h-48 w-48 rounded-full bg-amber-400/10 blur-3xl" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <span className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/15 backdrop-blur">
                <ClipboardEdit className="h-7 w-7 text-amber-200" />
              </span>
              <div>
                <h1 className="text-xl font-black text-white sm:text-2xl">آزمون‌ساز کنکوری</h1>
                <p className="mt-1 text-[12px] font-medium text-brand-100/85">
                  سؤال‌های چهارگزینه‌ایِ سطح کنکور بساز، پیش‌نمایش بگیر، ویرایش کن و PDF نهایی را چاپ کن.
                </p>
              </div>
            </div>
            <div className="rounded-2xl bg-white/10 px-4 py-2.5 text-center ring-1 ring-white/15 backdrop-blur">
              <p className="text-2xl font-black leading-none text-amber-200">{fmtFa(step === 'preview' ? questions.length : totalCount)}</p>
              <p className="mt-1 text-[10px] font-bold text-brand-100/80">سؤال چهارگزینه‌ای</p>
            </div>
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        {/* ════════════════════════ گام ۱ — فرم ════════════════════════ */}
        {step === 'form' && (
          <>
            <div className="space-y-6 lg:col-span-8">
              {/* ── اطلاعات آزمون ── */}
              <section className="card p-5 sm:p-6">
                <label htmlFor="exam-title" className="label">نام آزمون (اختیاری)</label>
                <input
                  id="exam-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="مثلاً: آزمون کنکوری مشتق — دوازدهم ریاضی"
                  className="input"
                />
                <label htmlFor="school-name" className="label mt-4">نام مدرسه/مؤسسه (روی سربرگ PDF)</label>
                <input
                  id="school-name"
                  value={schoolName}
                  onChange={(e) => {
                    setSchoolName(e.target.value)
                    try {
                      localStorage.setItem('fahmyar_school_name', e.target.value)
                    } catch {
                      /* فضای ذخیره در دسترس نیست */
                    }
                  }}
                  placeholder="مثلاً: دبیرستان نمونهٔ اندیشه"
                  className="input"
                />

                {/* رشته — فقط ریاضی و تجربی */}
                <span className="label mt-4 block">رشته</span>
                <div className="mt-1.5 grid grid-cols-2 gap-2.5" role="group" aria-label="رشته">
                  {FIELDS.map(({ id, label, Icon, grad }) => {
                    const active = field === id
                    return (
                      <button
                        key={id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setFieldPersist(id)}
                        className={`flex items-center gap-3 rounded-2xl border p-3.5 transition-all duration-200 ${
                          active
                            ? 'border-transparent bg-gradient-to-br text-white shadow-lift ring-2 ring-brand-300/60 ' + grad
                            : 'border-slate-200/80 bg-slate-50/50 text-slate-600 hover:border-brand-200 hover:bg-white'
                        }`}
                      >
                        <Icon className={`h-7 w-7 ${active ? 'text-white' : 'text-brand-700'}`} strokeWidth={1.8} />
                        <span className="text-[14px] font-black">{label}</span>
                        {active && <Check className="mr-auto h-5 w-5" />}
                      </button>
                    )
                  })}
                </div>

                {/* پایه — دهم تا دوازدهم و جامع */}
                <span className="label mt-4 block">پایه</span>
                <div className="mt-1.5 grid grid-cols-4 gap-2" role="group" aria-label="پایه">
                  {GRADES.map((g) => {
                    const active = grade === g.id
                    return (
                      <button
                        key={g.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setGrade(g.id)}
                        className={`rounded-2xl border py-2.5 text-[12px] font-black transition-all duration-200 ${
                          active
                            ? 'border-transparent bg-emerald-600 text-white shadow-soft'
                            : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-emerald-200 hover:text-emerald-700'
                        }`}
                      >
                        {g.label}
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── انتخاب درس (دینامیک بر اساس رشته) ── */}
              <section className="card p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                    <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۱</span>
                    انتخاب درس (چندگانه)
                  </h2>
                  <div className="flex items-center gap-2">
                    <span className="chip bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200">{toFarsiNumber(selectedSubjects.length)} درس انتخاب شد</span>
                    <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">رشتهٔ {FIELD_LABELS[field]}</span>
                  </div>
                </div>
                <p className="mt-2 text-[11px] font-medium leading-5 text-slate-500">
                  امکان انتخاب/لغو چند درس با کلیک وجود دارد؛ سؤالات به‌طور متوازن بین درس‌های انتخابی تقسیم می‌شوند.
                </p>
                <div className={`mt-4 grid gap-2.5 ${subjectOptions.length > 4 ? 'grid-cols-2 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4'}`}>
                  {subjectOptions.map(({ id, label, Icon }) => {
                    const on = selectedSubjects.includes(id)
                    return (
                      <button
                        key={id}
                        type="button"
                        aria-pressed={on}
                        onClick={() => toggleSubject(id)}
                        className={`relative flex flex-col items-center gap-2 rounded-2xl border p-3.5 transition-all duration-200 ${
                          on
                            ? 'border-transparent bg-gradient-to-br from-brand-600 to-emerald-700 text-white shadow-lift ring-2 ring-brand-300/60'
                            : 'border-slate-200/80 bg-slate-50/50 text-slate-600 hover:border-brand-200 hover:bg-white'
                        }`}
                      >
                        {on && (
                          <span className="absolute left-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-white text-emerald-700 shadow-sm">
                            <Check className="h-3.5 w-3.5" strokeWidth={3} />
                          </span>
                        )}
                        <Icon className={`h-6 w-6 ${on ? 'text-white' : 'text-brand-700'}`} strokeWidth={1.8} />
                        <span className="text-[12px] font-black leading-5">{label}</span>
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── تنظیماتِ هر درس: تعداد سؤال + فصل‌های هدف ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۲</span>
                  تنظیمات سؤالات هر درس
                </h2>
                <p className="mt-1.5 text-[11px] font-medium leading-6 text-slate-500">
                  برای هر درسی که انتخاب کرده‌اید، تعداد سؤال و فصل‌های هدف را مشخص کنید؛ فصل انتخاب‌نشده یعنی پوششِ همهٔ فصول.
                </p>

                <div className="mt-4 space-y-3">
                  {selectedOptions.length === 0 && (
                    <p className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-4 py-6 text-center text-[12px] font-bold text-slate-400">
                      ابتدا حداقل یک درس را در بخش ۱ انتخاب کنید.
                    </p>
                  )}
                  {selectedOptions.map(({ id, label, Icon }) => {
                    const cfg = subjectConfigs[id] ?? { count: 2, topics: [] }
                    const chapters = CURRICULUM_TREE[label] ?? CURRICULUM_TREE[id] ?? []
                    return (
                      <fieldset key={id} className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <legend className="sr-only">{label}</legend>
                          <p className="flex items-center gap-2 text-[13px] font-black text-brand-950">
                            <Icon className="h-5 w-5 text-brand-700" strokeWidth={1.8} />
                            {label}
                          </p>
                          <div className="flex items-center gap-2">
                            <label htmlFor={`count-${id}`} className="text-[10px] font-bold text-slate-500">تعداد سوال این درس</label>
                            <input
                              id={`count-${id}`}
                              type="number"
                              min={1}
                              max={20}
                              step={1}
                              value={cfg.count}
                              onChange={(e) => updateSubjectCount(id, e.target.value)}
                              className="input w-20 px-3 py-2 text-center text-[13px] font-black tabular-nums"
                              inputMode="numeric"
                            />
                          </div>
                        </div>
                        {chapters.length > 0 && (
                          <div className="mt-3">
                            <p className="text-[10px] font-bold text-slate-500">فصل‌ها / مباحث هدف این درس</p>
                            <div className="mt-1.5 max-h-36 space-y-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2">
                              {chapters.map((chapter) => {
                                const on = cfg.topics.includes(chapter)
                                return (
                                  <label
                                    key={chapter}
                                    className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-[11px] leading-6 transition ${
                                      on ? 'bg-brand-50 text-brand-900' : 'text-slate-600 hover:bg-slate-50'
                                    }`}
                                  >
                                    <input
                                      type="checkbox"
                                      checked={on}
                                      onChange={() => toggleSubjectTopic(id, chapter)}
                                      className="h-4 w-4 shrink-0 accent-emerald-600"
                                    />
                                    <span>{chapter}</span>
                                  </label>
                                )
                              })}
                            </div>
                            {cfg.topics.length > 0 && (
                              <p className="mt-1.5 text-[10px] font-bold text-brand-700">{toFarsiNumber(cfg.topics.length)} فصل انتخاب شد</p>
                            )}
                          </div>
                        )}
                      </fieldset>
                    )
                  })}
                </div>

                {/* مجموع سؤالات */}
                <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-2.5">
                  <span className="text-[12px] font-black text-brand-900">مجموع سؤالات آزمون</span>
                  <span className={`text-[13px] font-black tabular-nums ${totalCount > 60 ? 'text-rose-600' : 'text-brand-950'}`}>
                    {toFarsiNumber(totalCount)} سؤال
                  </span>
                </div>
              </section>

              {/* ── توزیع منبع سؤالات: هوش مصنوعی در برابر بانک آزمون ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۳</span>
                  درصد سوالات تولیدی هوش مصنوعی
                </h2>
                <p className="mt-1.5 text-[11px] font-medium leading-6 text-slate-500">
                  نسبت «درصد سوالات تولیدی هوش مصنوعی» به «سوالات بانک آزمون» (کنکور / قلم‌چی / گاج) را مشخص کنید.
                </p>
                <div className="mt-4 flex items-center gap-3 text-[10px] font-black text-slate-400">
                  <span className="shrink-0">۰٪</span>
                  <input
                    id="ai-percentage"
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={aiPercentage}
                    onChange={(e) => setAiPercentage(Number(e.target.value))}
                    className="w-full accent-emerald-600"
                    aria-label="درصد سوالات تولیدی هوش مصنوعی"
                  />
                  <span className="shrink-0">۱۰۰٪</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-slate-50 px-4 py-2.5 text-[12px] font-black">
                  <span className="text-emerald-700">درصد سوالات تولیدی هوش مصنوعی: {toFarsiNumber(aiPercentage)}٪</span>
                  <span className="text-slate-600">سوالات بانک آزمون: {toFarsiNumber(100 - aiPercentage)}٪</span>
                </div>
              </section>

              {/* ── سبک سؤال ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۴</span>
                  سبک سؤال
                </h2>

                <div className="mt-4">
                  <label htmlFor="question-type" className="label">نوع سؤالات</label>
                  <select
                    id="question-type"
                    value={questionType}
                    onChange={(e) => setQuestionType(e.target.value)}
                    className="input mt-1.5"
                  >
                    {QUESTION_TYPES.map((t) => (
                      <option key={t.id} value={t.id}>{t.label}</option>
                    ))}
                  </select>
                </div>

                <label htmlFor="custom-prompt" className="label mt-4">دستورالعمل سفارشی (اختیاری)</label>
                <textarea
                  id="custom-prompt"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  rows={3}
                  maxLength={600}
                  placeholder="مثلاً: از مبحث فلان سخت‌تر باشد و دام‌های تستی آن مبحث را هدف بگیرد…"
                  className="input mt-1.5"
                />
                <p className="mt-1 text-left text-[10px] font-bold tabular-nums text-slate-400">{fmtFa(customPrompt.length)} / ۶۰۰</p>
              </section>

              {/* ── سطح سختی ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <Flame className="h-5 w-5 text-brand-700" /> سطح سختی
                </h2>
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" role="radiogroup" aria-label="سطح سختی آزمون">
                  {DIFFICULTY_OPTIONS.map(({ id, label, desc, Icon }) => {
                    const on = difficulty === id
                    return (
                      <button
                        key={id}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        onClick={() => setDifficulty(id)}
                        className={`rounded-2xl border p-4 text-center transition-all duration-200 ${
                          on
                            ? 'border-brand-500 bg-brand-50 shadow-lift ring-2 ring-brand-200'
                            : 'border-slate-200/80 bg-white hover:-translate-y-0.5 hover:border-brand-200'
                        }`}
                      >
                        <Icon className={`mx-auto h-6 w-6 ${on ? 'text-brand-700' : 'text-slate-400'}`} strokeWidth={1.8} />
                        <span className="mt-2 block text-[13px] font-black text-brand-950">{label}</span>
                        <span className="mt-1 block text-[9px] font-medium leading-4 text-slate-400">{desc}</span>
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── زمان آزمون ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <Timer className="h-5 w-5 text-brand-700" /> زمان آزمون
                </h2>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {TIME_PRESETS.map((t) => {
                    const on = duration === t
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setDuration(t)}
                        aria-pressed={on}
                        className={`rounded-2xl border px-4 py-2.5 text-[13px] font-black tabular-nums transition-all ${
                          on
                            ? 'border-transparent bg-brand-700 text-white shadow-lift'
                            : 'border-slate-200 bg-white text-brand-900 shadow-sm hover:border-brand-300 hover:bg-brand-50'
                        }`}
                      >
                        {fmtFa(t)} دقیقه
                      </button>
                    )
                  })}
                </div>
              </section>
            </div>

            {/* ── ستون کنار: خلاصه + دکمهٔ تولید پیش‌نمایش ── */}
            <div className="space-y-6 lg:col-span-4">
              <section className="card overflow-hidden p-0">
                <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3.5">
                  <h2 className="flex items-center gap-2 text-[14px] font-black text-brand-950"><FileText className="h-4 w-4 text-brand-700" /> پیش‌نمایش تنظیمات</h2>
                </div>
                <dl className="space-y-2.5 px-5 py-4 text-[12px] leading-7">
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">رشته</dt>
                    <dd className="font-bold text-brand-950">{FIELD_LABELS[field]}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">پایه</dt>
                    <dd className="font-bold text-brand-950">{grade === 'comprehensive' ? 'جامع (همهٔ پایه‌ها)' : `پایهٔ ${GRADE_LABELS[grade]}`}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">درس‌ها</dt>
                    <dd className="max-w-[62%] truncate text-left font-bold text-brand-950" title={subjectsLabel}>{subjectsLabel || '—'}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">تعداد کل سؤالات</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(totalCount)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">منبع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{toFarsiNumber(aiPercentage)}٪ AI · {toFarsiNumber(100 - aiPercentage)}٪ بانک</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">نوع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{questionTypeLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">سطح سختی</dt>
                    <dd className="font-bold text-brand-950">{difficultyLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-slate-500">زمان</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(duration)} دقیقه</dd>
                  </div>
                </dl>
                <div className="border-t border-slate-100 bg-white px-5 py-4">
                  <button
                    onClick={generatePreview}
                    disabled={generating}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-3.5 text-[14px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-80"
                  >
                    {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
                    {generating ? 'در حال تولید پیش‌نمایش…' : 'تولید پیش‌نمایش آزمون'}
                  </button>
                  {notice && (
                    <p className="mt-3 rounded-2xl bg-amber-50 px-4 py-2.5 text-[11px] font-bold leading-6 text-amber-900" role="status">
                      {notice}
                    </p>
                  )}
                </div>
              </section>

              {/* ── پیش‌نویس‌های قدیمی (فقط مشاهده و حذف) ── */}
              {drafts.length > 0 && (
                <section className="card p-5">
                  <h2 className="flex items-center gap-2 text-[13px] font-black text-brand-950">
                    <ChevronDown className="h-4 w-4 rotate-[-90deg] text-brand-700" /> پیش‌نویس‌های قدیمی ({fmtFa(drafts.length)})
                  </h2>
                  <p className="mt-1.5 text-[10px] leading-5 text-slate-500">قالب آزمون‌ساز به کنکوری تغییر کرده است؛ پیش‌نویس‌های قبلی فقط برای مشاهده و حذف نگه داشته شده‌اند.</p>
                  <ul className="mt-3 max-h-72 space-y-2 overflow-auto">
                    {drafts.map((d) => (
                      <li key={d.id} className="flex items-start justify-between gap-2 rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                        <div className="min-w-0">
                          <p className="truncate text-[12px] font-black text-brand-950">{d.title}</p>
                          <p className="mt-0.5 text-[10px] leading-5 text-slate-500">
                            {fmtFa(d.totalQuestions ?? 0)} سؤال · {fmtFa(d.duration ?? 0)} دقیقه
                          </p>
                        </div>
                        <button onClick={() => removeDraft(d.id)} aria-label="حذف پیش‌نویس" className="shrink-0 rounded-xl p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </>
        )}

        {/* ════════════════════════ گام ۲ — پیش‌نمایش و ویرایش ════════════════════════ */}
        {step === 'preview' && (
          <>
            <div className="space-y-4 lg:col-span-8">
              <section className="card flex flex-wrap items-center justify-between gap-3 p-5">
                <div>
                  <h2 className="flex items-center gap-2 text-[16px] font-black text-brand-950">
                    <Wand2 className="h-5 w-5 text-brand-700" /> پیش‌نمایش سؤالات
                  </h2>
                  <p className="mt-1 text-[11px] font-medium text-slate-500">قبل از چاپ، سؤال‌ها را ویرایش کن: حذف، بالا/پایین بردن.</p>
                </div>
                <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">{fmtFa(questions.length)} سؤال</span>
              </section>

              {questions.length === 0 ? (
                <section className="card p-8 text-center">
                  <Info className="mx-auto h-8 w-8 text-amber-500" />
                  <p className="mt-3 text-[13px] font-bold text-slate-600">همهٔ سؤال‌ها حذف شدند.</p>
                  <button onClick={() => setStep('form')} className="mt-4 inline-flex items-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-2.5 text-[12px] font-bold text-brand-800 transition hover:bg-brand-50">
                    <RotateCcw className="h-4 w-4" /> بازگشت به فرم
                  </button>
                </section>
              ) : (
                <ol className="space-y-4">
                  {questions.map((q, idx) => (
                    <li key={q.id ?? idx} className="card p-4 sm:p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">{fmtFa(idx + 1)}</span>
                          {q.subject && (
                            <span className="chip bg-sky-50 text-sky-800 ring-1 ring-sky-200">{q.subject}</span>
                          )}
                          {q.source_tag && (
                            <span className="chip bg-amber-50 text-amber-800 ring-1 ring-amber-200" title="این تگ فقط در پیش‌نمایش دیده می‌شود و در PDF چاپ نمی‌شود">
                              {q.source_tag}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => moveQuestion(idx, -1)}
                            disabled={idx === 0}
                            aria-label="بالا بردن سؤال"
                            title="بالا بردن"
                            className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 transition hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            <ArrowUp className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveQuestion(idx, +1)}
                            disabled={idx === questions.length - 1}
                            aria-label="پایین آوردن سؤال"
                            title="پایین آوردن"
                            className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 transition hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            <ArrowDown className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => removeQuestion(q.id ?? idx)}
                            aria-label="حذف سؤال"
                            title="حذف"
                            className="rounded-xl border border-red-100 bg-red-50/60 p-2 text-red-500 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                      <p className="mt-3 text-[13px] font-bold leading-7 text-brand-950">{q.text}</p>
                      <ol className="mt-3 grid gap-2 sm:grid-cols-2">
                        {(q.options || []).map((opt, oi) => {
                          const correct = oi === Number(q.correct_answer) - 1
                          return (
                            <li
                              key={oi}
                              className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-[12px] leading-6 ${
                                correct
                                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200'
                                  : 'border-slate-200 bg-slate-50/60 text-slate-600'
                              }`}
                            >
                              <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${correct ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-600'}`}>
                                {fmtFa(oi + 1)}
                              </span>
                              <span className="min-w-0">{opt}</span>
                              {correct && <Check className="mr-auto h-4 w-4 shrink-0 self-center text-emerald-600" />}
                            </li>
                          )
                        })}
                      </ol>
                    </li>
                  ))}
                </ol>
              )}

              <p className="rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-2.5 text-[10px] font-bold leading-6 text-amber-800">
                «تگ منبع» (مثلاً کنکور ۱۴۰۱، قلم‌چی یا تألیفی AI) فقط در این پیش‌نمایش نمایش داده می‌شود و در PDF نهایی هرگز چاپ نمی‌شود.
              </p>
            </div>

            {/* ── ستون کنار: خلاصهٔ نهایی + تأیید و دانلود ── */}
            <div className="space-y-6 lg:col-span-4">
              <section className="card overflow-hidden p-0 lg:sticky lg:top-6">
                <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3.5">
                  <h2 className="flex items-center gap-2 text-[14px] font-black text-brand-950"><FileText className="h-4 w-4 text-brand-700" /> خلاصهٔ PDF نهایی</h2>
                </div>
                <dl className="space-y-2.5 px-5 py-4 text-[12px] leading-7">
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">مدرسه</dt>
                    <dd className="max-w-[60%] truncate text-left font-bold text-brand-950" title={schoolName}>{schoolName.trim() || 'مدرسهٔ نمونه'}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">رشته / پایه</dt>
                    <dd className="font-bold text-brand-950">{FIELD_PRINT_LABELS[field]} · {grade === 'comprehensive' ? 'جامع' : `پایهٔ ${GRADE_LABELS[grade]}`}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">درس‌ها / تعداد</dt>
                    <dd className="max-w-[62%] truncate text-left font-bold text-brand-950" title={subjectsLabel}>{subjectsLabel || '—'} · {fmtFa(totalCount)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">نوع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{questionTypeLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">تعداد سؤال نهایی</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(questions.length)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-slate-500">زمان / سختی</dt>
                    <dd className="font-bold text-brand-950">{fmtFa(duration)} دقیقه · {difficultyLabel}</dd>
                  </div>
                </dl>
                <div className="border-t border-slate-100 bg-white px-5 py-4">
                  <button
                    onClick={confirmAndDownload}
                    disabled={downloading || questions.length === 0}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-4 text-[14px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {downloading ? <Loader2 className="h-5 w-5 animate-spin" /> : <CheckCircle2 className="h-5 w-5" />}
                    {downloading ? 'در حال ساخت PDF…' : 'تأیید و دانلود PDF نهایی'}
                  </button>
                  <button
                    onClick={() => setStep('form')}
                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white py-3 text-[12px] font-bold text-brand-800 transition hover:bg-brand-50"
                  >
                    <RotateCcw className="h-4 w-4" /> بازگشت و تغییر تنظیمات
                  </button>
                  {pdfUrl && (
                    <a
                      href={pdfUrl}
                      download="fahmyar-konkur-exam.pdf"
                      className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-700 py-3 text-[13px] font-black text-white shadow-lift transition hover:bg-emerald-800"
                    >
                      <FileDown className="h-5 w-5" />
                      دانلود PDF آزمون و پاسخنامه
                    </a>
                  )}
                  {notice && (
                    <p className={`mt-3 rounded-2xl px-4 py-2.5 text-[11px] font-bold leading-6 ${notice.startsWith('⚠️') ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`} role="status">
                      {notice}
                    </p>
                  )}
                </div>
              </section>
            </div>
          </>
        )}
      </div>

      {/* ── پوشش تمام‌صفحهٔ «در حال تولید» ── */}
      {generating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm" role="alertdialog" aria-modal="true" aria-label="در حال تولید پیش‌نمایش">
          <div className="w-full max-w-md rounded-3xl border border-emerald-100 bg-white p-8 text-center shadow-lift">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 ring-1 ring-emerald-100">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
            </span>
            <h3 className="mt-5 text-lg font-black text-slate-800">در حال تولید پیش‌نمایش…</h3>
            <p className="mt-1.5 min-h-6 text-[12px] font-bold leading-6 text-emerald-700">{GEN_STEPS[genStep]}</p>
            <div className="mt-5 h-2.5 w-full overflow-hidden rounded-full bg-emerald-100">
              <div className="h-full w-1/3 animate-[genbar_1.15s_linear_infinite] rounded-full bg-gradient-to-l from-emerald-500 to-teal-500" />
            </div>
            <p className="mt-3 text-[10px] font-medium text-slate-400">لطفاً صفحه را نبند؛ این کار چند لحظه طول می‌کشد.</p>
          </div>
        </div>
      )}
    </div>
  )
}
