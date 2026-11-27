import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles,
  BookOpen,
  Microscope,
  Sigma,
  Atom,
  FlaskConical,
  Route,
  GitBranch,
  ArrowLeft,
  Loader2,
  Info,
  Waypoints,
  HeartHandshake,
  SearchCheck,
  Map,
  GraduationCap,
  ShieldCheck,
  Compass,
  BookOpenCheck,
  ScrollText,
  CalendarDays,
  History,
  BrainCircuit,
  Fingerprint,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import CustomDropdown from '../components/CustomDropdown'
import CurriculumCascader from '../components/CurriculumCascader'
import { TOTAL_CONCEPTS } from '../lib/curriculum/iranHighSchoolCurriculum'
import { toFarsiNumber, subjectFa } from '../utils/faNumbers'

const SUBJECTS = [
  { value: 'math', label: 'ریاضی', Icon: Sigma },
  { value: 'physics', label: 'فیزیک', Icon: Atom },
  { value: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const GRADES = [10, 11, 12]

// برچسب‌های فارسی برای تگ‌های رفتاری/شناختیِ مفاهیم (هیچ انگلیسی‌ای در UI دیده نمی‌شود)
const tagMap = {
  identify_error: 'شناسایی خطا',
  predict: 'پیش‌بینی',
  explain: 'توضیح مفهومی',
  calculate: 'محاسبه',
  compare: 'مقایسه',
  formulate: 'فرمول‌بندی',
  evaluate: 'ارزیابی',
  recall: 'یادآوری',
  solve: 'حل مسئله',
  convert_representation: 'تبدیل بازنمایی',
}

const HISTORY_CHIP = {
  stable: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  growing: 'bg-amber-50 text-amber-800 ring-amber-200',
  remedial: 'bg-rose-50 text-rose-800 ring-rose-200',
  insufficient: 'bg-slate-100 text-slate-600 ring-slate-200',
}

const HOW_STEPS = [
  { Icon: SearchCheck, title: '۱. زنجیرهٔ ۵ مرحله‌ای', text: 'از مفهوم تا کاربرد: پرسشِ مفهومی، محاسبه، پیش‌بینی، نقدِ استدلال و توضیحِ ساده.' },
  { Icon: Waypoints, title: '۲. بدون بازخورد لحظه‌ای', text: 'حین آزمون چیزی فاش نمی‌شود؛ پاسخ‌ها جمع می‌شوند تا تحلیل یکپارچه انجام شود.' },
  { Icon: Map, title: '۳. کارنامهٔ اشعهٔ ایکس', text: 'شکارِ تناقض میان پاسخ‌ها، گره‌های کلیدیِ یادگیری و راهکارِ کیفی.' },
]

export default function StudentDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [tab, setTab] = useState('topic') // topic | wrong_answer

  // مسیر A
  const [subject, setSubject] = useState('physics')
  const [grade, setGrade] = useState(user?.grade ?? 11)
  const [concepts, setConcepts] = useState([])
  const [conceptId, setConceptId] = useState('')
  const [loadingConcepts, setLoadingConcepts] = useState(false)

  // مسیر B
  const [problemText, setProblemText] = useState('')
  const [wrongAnswer, setWrongAnswer] = useState('')
  const [wrongConceptId, setWrongConceptId] = useState('')
  const [allConcepts, setAllConcepts] = useState([])

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [history, setHistory] = useState(null) // null = در حال بارگذاری | [] = خالی
  const [historyError, setHistoryError] = useState('')
  const [started, setStarted] = useState(false) // false = صفحهٔ خوش‌آمد، true = جریان فهم‌سنجی
  // بارگذاری مفاهیم مسیر A
  useEffect(() => {
    let alive = true
    setLoadingConcepts(true)
    setError('')
    client
      .get(`/api/concepts/${subject}/${grade}`)
      .then(({ data }) => {
        if (!alive) return
        setConcepts(data.concepts ?? [])
        setConceptId((prev) => (data.concepts?.some((c) => String(c.id) === String(prev)) ? prev : ''))
      })
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoadingConcepts(false))
    return () => {
      alive = false
    }
  }, [subject, grade])

  // بارگذاری همهٔ مفاهیم برای مسیر B (یک بار)
  useEffect(() => {
    client
      .get('/api/concepts')
      .then(({ data }) => setAllConcepts(data.concepts ?? []))
      .catch(() => setAllConcepts([]))
  }, [])

  // بارگذاری تاریخچهٔ آزمون‌های خود دانش‌آموز — دادهٔ واقعی دیتابیس
  useEffect(() => {
    let alive = true
    client
      .get('/api/student/history')
      .then(({ data }) => alive && setHistory(Array.isArray(data?.history) ? data.history : []))
      .catch((err) => alive && setHistoryError(friendlyError(err)))
    return () => {
      alive = false
    }
  }, [])

  const selectedConcept = useMemo(
    () => concepts.find((c) => String(c.id) === String(conceptId)) ?? null,
    [concepts, conceptId],
  )

  // ── آزمونِ فهم‌سنجی شناختی (X-Ray) ──────────────────────────────────────
  // ── انتخابِ سلسله‌مراتبی (فاز ۲۹) ──
  // آبجکتِ کاملِ {major, grade, subjectId, subjectTitle, chapterTitle,
  //   conceptId, conceptTitle} که هم برای UI لازم است هم برای payloadِ API.
  const [curriculumSelection, setCurriculumSelection] = useState(null)
  const [xrayTopic, setXrayTopic] = useState('')
  const [xrayStarting, setXrayStarting] = useState(false)
  const [xrayError, setXrayError] = useState('')

  const startCognitiveAssessment = async () => {
    // مفهومِ انتخاب‌شده اولویت دارد؛ متنِ آزاد فقط وقتی معنا دارد که مفهوم نباشد.
    const typed = xrayTopic.trim()
    const conceptIdToUse = selectedConcept?.id ?? null
    const topic = (selectedConcept?.name || typed).trim()
    if (typed && conceptIdToUse && typed !== selectedConcept?.name) {
      setXrayError(
        `«${typed}» با مفهومِ انتخاب‌شده («${selectedConcept?.name}») یکی نیست. ` +
          'یا کادر را خالی کن یا همان مفهومِ فهرست را نگه دار.',
      )
      return
    }
    if (!conceptIdToUse) {
      setXrayError('این مبحث در بانک مفاهیم نیست؛ از فهرستِ پایین یکی را انتخاب کن یا مبحث را با معلمت اضافه کن.')
      return
    }
    if (topic.length < 2) {
      setXrayError('از فهرستِ پایین یک مفهوم انتخاب کن.')
      return
    }
    setXrayStarting(true)
    setXrayError('')
    try {
      // یک موتور، یک مسیر: زنجیرهٔ ۵ مرحله‌ای از /api/assess/start ساخته می‌شود.
      // مبحث باید یکی از مفاهیمِ بانک باشد تا سؤال‌ها به گزاره‌های اصلی لنگر بگیرند.

      const { data } = await client.post(
        '/api/assess/start',
        { trigger_type: 'topic_selection', concept_id: Number(conceptIdToUse), wrong_answer: null },
        { timeout: 240000 },
      )
      const sessionId = data?.session_id ?? data?.session?.id
      if (!sessionId) throw new Error('شناسهٔ جلسه از سرور دریافت نشد.')
      navigate('/exam/' + sessionId, {
        state: { startData: data, conceptName: data?.concept_name ?? topic },
      })
    } catch (err) {
      setXrayError(friendlyError(err))
    } finally {
      setXrayStarting(false)
    }
  }

  const startTopicSession = async () => {
    if (!curriculumSelection) {
      return setError('اول رشته، پایه، درس، فصل و مفهوم را انتخاب کن.')
    }
    setSubmitting(true)
    setError('')
    try {
      // ── فاز ۲۹: payloadِ کاملِ انتخابِ سلسله‌مراتبی ──
      //
      // ``concept_id`` دیگر اجباری نیست: اگر مفهوم در بانکِ ۱۶تایی باشد،
      // بک‌اند خودش با (subject, grade, name) منطبقش می‌کند؛ اگر نباشد،
      // از عنوان‌های رسمیِ همین درخت می‌سازدش. نتیجه: هر ۲۶۳ مفهومِ درخت
      // قابلِ انتخاب‌اند، نه فقط آن ۱۶ تا.
      const { data } = await client.post(
        '/api/assess/start',
        {
          trigger_type: 'topic_selection',
          concept_id: null,
          wrong_answer: null,
          curriculum: {
            major: curriculumSelection.major,
            grade: String(curriculumSelection.grade),
            subjectId: curriculumSelection.subjectId,
            subjectTitle: curriculumSelection.subjectTitle,
            chapterNumber: curriculumSelection.chapterNumber,
            chapterTitle: curriculumSelection.chapterTitle,
            conceptId: curriculumSelection.conceptId,
            conceptTitle: curriculumSelection.conceptTitle,
          },
        },
        { timeout: 240000 },
      )
      const sessionId = data?.session_id ?? data?.session?.id
      if (!sessionId) throw new Error('شناسهٔ جلسه از سرور دریافت نشد.')
      navigate('/exam/' + sessionId, {
        state: { startData: data, conceptName: data?.concept_name ?? curriculumSelection.conceptTitle },
      })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const startWrongAnswerSession = async () => {
    if (!wrongConceptId) {
      return setError('برای شروع آزمون جامع، مفهوم مرتبط را انتخاب کن (دفترچهٔ سؤال‌ها از همین مفهوم ساخته می‌شود).')
    }
    if (problemText.trim().length < 10 && wrongAnswer.trim().length < 5) {
      return setError('حداقل متن صورت مسئله یا پاسخ خودت را بنویس.')
    }
    setSubmitting(true)
    setError('')
    try {
      const { data } = await client.post(
        '/api/assess/start',
        {
          trigger_type: 'wrong_answer',
          concept_id: Number.parseInt(wrongConceptId, 10),
          wrong_answer: {
            problem_text: problemText.trim(),
            student_answer: wrongAnswer.trim(),
            concept_id: Number.parseInt(wrongConceptId, 10),
          },
        },
        { timeout: 180000 },
      )
      const sessionId = data?.session_id ?? data?.session?.id
      if (!sessionId) throw new Error('شناسهٔ جلسه از سرور دریافت نشد.')
      navigate('/exam/' + sessionId, {
        state: {
          startData: data,
          conceptName: allConcepts.find((c) => String(c.id) === String(wrongConceptId))?.name,
        },
      })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const today = new Date().toLocaleDateString('fa-IR', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── هدر داشبورد دانش‌آموز ── */}
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/70 bg-white px-5 py-3 shadow-soft">
        <div className="flex items-center gap-3">
          <span className="rounded-2xl bg-emerald-50 p-2.5 ring-1 ring-emerald-100">
            <GraduationCap className="h-5 w-5 text-emerald-700" />
          </span>
          <div>
            <p className="text-[13px] font-black text-slate-800">پنل دانش‌آموز</p>
            <p className="text-[10px] font-medium text-slate-400">{user?.full_name || user?.username}</p>
          </div>
        </div>
      </header>

      {!started ? (
        <section className="relative overflow-hidden rounded-3xl border border-emerald-100 bg-gradient-to-bl from-emerald-600 via-emerald-700 to-emerald-900 px-6 py-10 text-center text-white shadow-lift sm:px-10 sm:py-14">
          <div aria-hidden className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-emerald-400/20 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -left-16 bottom-0 h-64 w-64 rounded-full bg-teal-300/15 blur-3xl" />
          <div className="relative">
            <span className="inline-flex rounded-3xl bg-white/10 p-4 ring-1 ring-white/20 backdrop-blur">
              <BookOpenCheck className="h-11 w-11 text-emerald-100" strokeWidth={1.6} />
            </span>
            <h1 className="mt-6 text-3xl font-black leading-snug sm:text-4xl">به فهم‌یار خوش آمدید</h1>
            <p className="mx-auto mt-4 max-w-xl text-[15px] leading-8 text-emerald-50/95">
              در اینجا هیچ نمره‌ای وجود ندارد و هدف فقط کشف نقاط قوت و ضعف مفهومی شماست؛
              نه مقایسه با کسی، نه استرس.
            </p>
            <div className="mx-auto mt-7 grid max-w-3xl gap-3 text-right sm:grid-cols-3">
              {[
                { Icon: ShieldCheck, title: 'بدون نمره، بدون رتبه', text: 'فقط شواهد کیفی از فهمیدنت ثبت می‌شود.' },
                { Icon: Compass, title: 'دقیقاً می‌دانی کجایی', text: 'گزارش نشان می‌دهد کدام پیش‌نیاز را مرور کنی.' },
                { Icon: HeartHandshake, title: 'فقط برای تو و معلمت', text: 'گزارش‌ها خصوصی‌اند و مقایسه‌ای در کار نیست.' },
              ].map(({ Icon, title, text }) => (
                <div key={title} className="rounded-2xl bg-white/10 p-4 ring-1 ring-white/15 backdrop-blur">
                  <Icon className="h-6 w-6 text-emerald-100" strokeWidth={1.8} />
                  <p className="mt-2 text-[12px] font-black text-white">{title}</p>
                  <p className="mt-1 text-[10px] leading-5 text-emerald-100/90">{text}</p>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setStarted(true)}
              className="mt-8 inline-flex items-center gap-3 rounded-2xl bg-white px-8 py-4 text-[16px] font-black text-emerald-800 shadow-lift transition-all duration-200 hover:-translate-y-0.5 hover:bg-emerald-50 sm:px-10"
            >
              شروع ارزیابی / فهم‌سنجی
              <ArrowLeft className="h-6 w-6" strokeWidth={2.2} />
            </button>
            <p className="mt-4 text-[11px] font-medium text-emerald-100/80">
              حدود ۹ سؤال تشریحی · حداکثر ۳۰ دقیقه · هر وقت خواستی می‌توانی مکث کنی
            </p>
          </div>
        </section>
      ) : (
        <>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setStarted(false)}
          className="text-[11px] font-bold text-slate-400 transition hover:text-slate-600"
        >
          ← بازگشت به خوش‌آمد
        </button>
      </div>
      {/* ── سربرگ خوش‌آمد ── */}
      <section className="relative overflow-hidden rounded-4xl border border-brand-100 bg-gradient-to-l from-brand-800 to-brand-700 px-6 py-6 text-brand-50 shadow-lift sm:px-8">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(700px 260px at 88% -20%, rgba(253,233,200,0.35), transparent 60%)' }}
        />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="flex items-center gap-2 text-[12px] font-bold text-brand-200">
              <Sparkles className="h-4 w-4 text-amber-200" /> {today}
            </p>
            <h1 className="mt-2 text-2xl font-black leading-snug sm:text-[28px]">
              سلام {user?.full_name || user?.username} 👋<br className="hidden sm:block" />
              آماده‌ای برای آزمون جامع تشخیصی؟
            </h1>
            <p className="mt-2 max-w-lg text-[13px] leading-7 text-brand-100/90">
              یک زنجیرهٔ فهم‌سنجی ۵ مرحله‌ای از همین مفهوم آماده است.
              در پایان، کارنامهٔ اشعهٔ ایکس با شکارِ تناقض‌های ذهنت می‌سازیم.
            </p>
          </div>
          <div className="hidden shrink-0 flex-col items-center gap-2 rounded-3xl bg-white/10 px-6 py-4 text-center ring-1 ring-white/15 backdrop-blur md:flex">
            <HeartHandshake className="h-9 w-9 text-amber-200" />
            <p className="text-[11px] font-bold leading-5 text-brand-100">
              زنجیرهٔ ۵ مرحله‌ای
              <br /> تحلیلِ مقایسه‌ای
            </p>
          </div>
        </div>
      </section>

      {/* ── کارتِ آبیِ بالا حذف شد (فاز ۲۹) ──
          اسپک صریحاً خواست: «کارتِ آبیِ جست‌وجو/ورودیِ متن کاملاً برداشته شود؛
          مسیر الف نقطهٔ ورودِ اصلی است».

          قابلیتِ «نوشتنِ مبحثِ دلخواه» از دست نرفت: همان ورودی به **داخلِ
          مسیر الف** منتقل شد، پایین‌تر، زیرِ انتخاب‌گرِ سلسله‌مراتبی — به‌عنوان
          گزینهٔ دوم برای وقتی که مفهوم در درخت پیدا نمی‌شود. */}

      {/* ── تب‌های مسیر شروع ── */}
      <div className="grid gap-3 sm:grid-cols-2" role="tablist" aria-label="دو مسیر شروع آزمون جامع">
        {[
          { key: 'topic', Icon: Route, title: 'مسیر الف — آزمون جامع یک موضوع', sub: 'یک مفهوم درسی را انتخاب کن؛ زنجیرهٔ ۵ مرحله‌ای از همان مفهوم ساخته می‌شود' },
          { key: 'wrong_answer', Icon: GitBranch, title: 'مسیر ب — شروع از پاسخ اشتباه', sub: 'جواب اشتباهت را بفرست؛ زنجیره طوری ساخته می‌شود که ریشهٔ خطا را ردیابی کند' },
        ].map(({ key, Icon, title, sub }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => {
              setTab(key)
              setError('')
            }}
            className={`group flex items-start gap-4 rounded-3xl border p-5 text-right transition ${
              tab === key
                ? 'border-brand-400 bg-white shadow-lift ring-2 ring-brand-200'
                : 'border-brand-100 bg-white/60 hover:border-brand-200 hover:bg-white'
            }`}
          >
            <span className={`rounded-2xl p-3 transition ${tab === key ? 'bg-brand-700 text-amber-200' : 'bg-brand-50 text-brand-700 group-hover:bg-brand-100'}`}>
              <Icon className="h-6 w-6" />
            </span>
            <span>
              <span className="block text-[15px] font-black text-brand-900">{title}</span>
              <span className="mt-1 block text-[12px] leading-6 text-slate-500">{sub}</span>
            </span>
          </button>
        ))}
      </div>

      {/* ── پنل هر مسیر ── */}
      <section className="card p-6 sm:p-7">
        {tab === 'topic' ? (
          <div className="space-y-5">
            {/* ══════════ انتخابِ سلسله‌مراتبی (فاز ۲۹) ══════════
                جای سه دراپ‌داونِ مستقلِ «درس/پایه/مفهوم» که هم‌زمان نمایش داده
                می‌شدند و تا انتخابِ قبلی خالی بودند. حالا پله‌به‌پله:
                رشته → پایه → درس → فصل → مفهوم. */}
            <div>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-1">
                <h3 className="flex items-center gap-1.5 text-[13px] font-black text-brand-950">
                  <GraduationCap className="h-4 w-4 text-brand-600" />
                  مفهوم را انتخاب کن
                </h3>
                <span className="text-[10.5px] font-medium text-slate-400">
                  {toFarsiNumber(TOTAL_CONCEPTS)} مفهوم از کتاب‌های رسمی
                </span>
              </div>
              <CurriculumCascader value={curriculumSelection} onChange={setCurriculumSelection} disabled={submitting} />
            </div>

            {/* ── شروع با مفهومِ انتخابی از درخت ── */}
            <button
              onClick={startTopicSession}
              disabled={submitting || !curriculumSelection}
              className="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand-700 py-4 text-[15px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Microscope className="h-5 w-5" />}
              {curriculumSelection
                ? `شروع آزمون جامع تشخیصی (۱۰ سؤال) — ${curriculumSelection.conceptTitle}`
                : 'شروع آزمون جامع تشخیصی (۱۰ سؤال)'}
              <ArrowLeft className="h-5 w-5" />
            </button>
            {error && (
              <p className="rounded-xl bg-rose-50 p-3 text-[11px] font-bold text-rose-800 ring-1 ring-rose-200" role="alert">
                {error}
              </p>
            )}

            {/* ── مسیرِ جایگزین: نوشتنِ مبحثِ دلخواه ──
                این همان قابلیتی است که در کارتِ آبیِ حذف‌شده بود. حالا
                اختیاری و کم‌حجم، زیرِ مسیرِ اصلی — نه بالای صفحه. */}
            <details className="rounded-2xl border border-slate-200 bg-slate-50/60 px-4 py-3">
              <summary className="cursor-pointer text-[12px] font-black text-slate-700">
                مبحثم در فهرست نیست — با نوشتن شروع کنم
              </summary>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <input
                  value={xrayTopic}
                  onChange={(event) => setXrayTopic(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && startCognitiveAssessment()}
                  placeholder="مبحث را بنویس، مثلاً «فشار در مایعات»"
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[12.5px] font-bold text-slate-800 outline-none transition placeholder:font-medium placeholder:text-slate-400 focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
                <button
                  type="button"
                  onClick={startCognitiveAssessment}
                  disabled={xrayStarting}
                  className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl border border-brand-200 bg-white px-4 py-2.5 text-[12px] font-black text-brand-800 transition hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {xrayStarting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Fingerprint className="h-4 w-4" />}
                  {xrayStarting ? 'در حال ساخت…' : 'شروعِ تحلیل'}
                </button>
              </div>
              {xrayError && (
                <p className="mt-2 rounded-lg bg-amber-50 p-2.5 text-[10.5px] font-bold text-amber-900 ring-1 ring-amber-200">
                  {xrayError}
                </p>
              )}
            </details>
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <label className="label" htmlFor="problem">صورت مسئله / سؤال</label>
              <textarea id="problem" rows={3} className="input resize-y" value={problemText} onChange={(e) => setProblemText(e.target.value)} placeholder="مثلاً: دو بار الکتریکیِ مشابه در فاصلهٔ ۲ سانتی‌متری…" />
            </div>
            <div>
              <label className="label" htmlFor="wrong">پاسخِ اشتباهِ خودت (همان‌طور که نوشته‌ای)</label>
              <textarea id="wrong" rows={4} className="input resize-y" value={wrongAnswer} onChange={(e) => setWrongAnswer(e.target.value)} placeholder="مثلاً: چون فاصله نصف شد، نیرو هم نصف می‌شود…" />
              <p className="mt-1.5 text-[11px] text-slate-500">نگران نباش — هدف از دیدن این پاسخ، پیدا کردن ریشهٔ خطاست، نه نمره‌دادن.</p>
            </div>
            <div>
              <label className="label" htmlFor="wconcept">مفهوم مرتبط (الزامی — دفترچهٔ سؤالات از این مفهوم ساخته می‌شود)</label>
              <CustomDropdown
                id="wconcept"
                value={wrongConceptId}
                onChange={(v) => setWrongConceptId(v)}
                ariaLabel="مفهوم مرتبط"
                placeholder="— یک مفهوم انتخاب کن —"
                options={[
                  { value: '', label: '— یک مفهوم انتخاب کن —' },
                  ...allConcepts.map((c) => ({ value: c.id, label: `${c.name} · ${subjectFa(c.subject)}` })),
                ]}
              />
            </div>
            <button onClick={startWrongAnswerSession} disabled={submitting} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-700 py-4 text-[15px] font-black text-white shadow-lift transition hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-60">
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <GitBranch className="h-5 w-5" />}
              شروع آزمون جامع تشخیصی
              <ArrowLeft className="h-5 w-5" />
            </button>
          </div>
        )}

        {submitting && (
          <div className="mt-4 flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 text-[13px] font-bold leading-7 text-emerald-900" role="status">
            <Loader2 className="h-5 w-5 shrink-0 animate-spin text-emerald-700" />
            <span>در حال تولید، اعتبارسنجی و رسم اشکال هندسی... (این فرآیند ممکن است ۱ تا ۲ دقیقه زمان ببرد)</span>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] font-medium leading-7 text-amber-900" role="alert">
            {error}
          </div>
        )}
      </section>

      {/* ── چطور کار می‌کند ── */}
      <section className="grid gap-3 sm:grid-cols-3">
        {HOW_STEPS.map(({ Icon, title, text }) => (
          <div key={title} className="rounded-3xl border border-brand-100/70 bg-white/70 p-5 text-center">
            <Icon className="mx-auto h-7 w-7 text-brand-600" strokeWidth={1.8} />
            <p className="mt-2 text-[13px] font-black text-brand-900">{title}</p>
            <p className="mt-1 text-[11px] leading-6 text-slate-500">{text}</p>
          </div>
        ))}
      </section>

      <p className="flex items-center justify-center gap-2 text-center text-[11px] text-slate-400">
        <BookOpen className="h-4 w-4" /> هر جلسه حداکثر ۳۰ دقیقه طول می‌کشد و می‌توانی هر وقت خواستی مکث کنی.
      </p>
        </>
      )}

      {/* ── تاریخچهٔ آزمون‌های من — دادهٔ واقعی دیتابیس (GET /api/student/history) ── */}
      <section className="card p-6 sm:p-7" aria-label="تاریخچهٔ آزمون‌های من">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
            <History className="h-5 w-5 text-brand-700" /> تاریخچهٔ آزمون‌های من
          </h2>
          <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">اتصال زنده به دیتابیس</span>
        </div>
        {historyError ? (
          <p className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] font-bold text-amber-900" role="alert">{historyError}</p>
        ) : history === null ? (
          <div className="flex items-center justify-center gap-2 py-8 text-[12px] font-bold text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin text-brand-600" /> در حال دریافت تاریخچه…
          </div>
        ) : history.length === 0 ? (
          <p className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 px-4 py-10 text-center text-[12px] font-bold leading-6 text-slate-400">
            هنوز آزمونی ثبت نکرده‌ای؛<br />اولین فهم‌سنجی را همین‌جا شروع کن.
          </p>
        ) : (
          <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {history.map((h) => (
              <li
                key={h.session_id}
                className="flex flex-col rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:shadow-lift"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0 text-[12px] font-black leading-6 text-brand-950">
                    <span className="text-brand-600">{h.subject ? subjectFa(h.subject) : '—'}</span> · {h.concept_name}
                  </span>
                  <span className={`chip ring-1 ${HISTORY_CHIP[h.comprehension] ?? HISTORY_CHIP.insufficient}`}>
                    {h.comprehension_label}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-medium text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <CalendarDays className="h-3.5 w-3.5" />
                    {h.exam_date
                      ? new Date(h.exam_date).toLocaleDateString('fa-IR', { dateStyle: 'long' })
                      : '—'}
                  </span>
                  <span>{toFarsiNumber(h.questions_answered)} پاسخ ثبت‌شده</span>
                  <span>{h.is_exam ? 'آزمون جامع' : h.trigger_type === 'wrong_answer' ? 'مسیر پاسخ غلط' : 'انتخاب موضوع'}</span>
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/report/${h.session_id}`)}
                  className="mt-3 inline-flex items-center justify-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-[11px] font-black text-emerald-800 transition hover:border-emerald-300 hover:bg-emerald-100"
                >
                  <ScrollText className="h-4 w-4" /> مشاهدهٔ کارنامه
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
