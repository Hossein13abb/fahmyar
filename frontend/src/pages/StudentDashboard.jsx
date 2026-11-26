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
  { Icon: SearchCheck, title: 'گفت‌وگوی چندسؤالی', text: 'از مفهوم تا کاربرد: پرسشِ مفهومی، محاسبه، پیش‌بینی، نقدِ استدلال و توضیحِ ساده.' },
  { Icon: Waypoints, title: 'بدونِ بازخوردِ لحظه‌ای', text: 'حین آزمون چیزی فاش نمی‌شود؛ پاسخ‌ها جمع می‌شوند تا تحلیل یکپارچه انجام شود.' },
  { Icon: Map, title: 'کارنامه و نقشهٔ راه', text: 'شکارِ تناقض میان پاسخ‌ها، گره‌های کلیدیِ یادگیری و راهکارِ کیفی.' },
]

export default function StudentDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()

  const [tab, setTab] = useState('topic') // topic | wrong_answer
  const [showAllHistory, setShowAllHistory] = useState(false)

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
    if (!conceptId) return setError('اول یک مفهوم را انتخاب کن.')
    setSubmitting(true)
    setError('')
    try {
      // بدنه دقیقاً مطابق اسکیما: concept_id عدد صحیح + trigger_type ثابت
      const { data } = await client.post(
        '/api/assess/start',
        {
          trigger_type: 'topic_selection',
          concept_id: Number.parseInt(conceptId, 10),
          wrong_answer: null,
        },
        { timeout: 180000 },
      )
      const sessionId = data?.session_id ?? data?.session?.id
      if (!sessionId) throw new Error('شناسهٔ جلسه از سرور دریافت نشد.')
      navigate('/exam/' + sessionId, {
        state: { startData: data, conceptName: selectedConcept?.name ?? data?.concept_name },
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
      {/* ── سربرگِ «پنل دانش‌آموز» حذف شد (فاز ۲۷) ──
          شلِ برنامه قبلاً نام و نقشِ کاربر را نشان می‌دهد؛ این کارت فقط یک
          سربرگِ دومِ تکراری بود که ~۷۰px بالای صفحه می‌گرفت و چیزی اضافه
          نمی‌کرد. اسپک صریحاً «بدونِ سربرگ‌های روی‌هم» گفته است. */}

      {/* ── نقطهٔ ورود ──
          قبلاً: یک گرادیانتِ زمردیِ تمام‌عرض با سه کارتِ شیشه‌ای و یک دکمهٔ
          بزرگ. همان الگویی که فاز ۲۷ برچید. حالا: یک کارتِ کاغذیِ روشن با
          یک جملهٔ کوتاه و یک اقدامِ اصلی. سه توضیح، زیرِ هم و کم‌حجم‌تر. */}
      {!started ? (
        <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest">
          <div className="grid lg:grid-cols-12">
            <div className="p-6 sm:p-8 lg:col-span-7">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft px-2.5 py-1 text-[10px] font-black text-primary-deep">
                <Compass className="h-3 w-3" />
                قدمِ اول
              </span>
              <h1 className="mt-3 text-[26px] font-black leading-tight tracking-tight text-ink sm:text-[30px]">
                بیایید بفهمیم چه چیزهایی را <span className="text-primary">واقعاً</span> فهمیده‌ای
              </h1>
              <p className="mt-2.5 max-w-md text-justify text-right text-[13px] leading-8 text-ink-soft">
                نه نمره، نه رتبه. یک گفت‌وگوی چند سؤالی که نشان می‌دهد کجا محکمی و کدام پیش‌نیاز
                لنگ می‌زند — بعدش خودت را بهتر می‌شناسی.
              </p>
              <button
                type="button"
                onClick={() => setStarted(true)}
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-[13px] font-black text-white shadow-rest transition hover:bg-primary-deep focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
              >
                انتخاب مبحث و شروع
                <ArrowLeft className="h-4 w-4" strokeWidth={2.4} />
              </button>
            </div>

            {/* ستونِ کناری: سه اصلِ کار، به‌صورتِ فهرستِ عمودی نه سه کارت */}
            <aside className="border-t border-slate-100 bg-surface-muted p-6 sm:p-8 lg:col-span-5 lg:border-r lg:border-t-0">
              <ul className="space-y-3.5">
                {[
                  { Icon: ShieldCheck, title: 'بدونِ نمره و رتبه', text: 'فقط شواهدِ کیفی از فهمیدنت ثبت می‌شود.' },
                  { Icon: Compass, title: 'دقیقاً می‌دانی کجایی', text: 'کارنامه نشان می‌دهد کدام پیش‌نیاز را مرور کنی.' },
                  { Icon: HeartHandshake, title: 'فقط برای تو و معلمت', text: 'کارنامه‌ها خصوصی‌اند و مقایسه‌ای در کار نیست.' },
                ].map(({ Icon, title, text }) => (
                  <li key={title} className="flex gap-3">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-primary ring-1 ring-slate-200">
                      <Icon className="h-4 w-4" strokeWidth={2} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-[12px] font-black text-ink">{title}</p>
                      <p className="mt-0.5 text-[11px] leading-6 text-ink-soft">{text}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </aside>
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
      {/* ── نوارِ خوش‌آمد ──
          جای گرادیانتِ brand-800 و کارتِ شیشه‌ایِ کنارش: یک ردیفِ کم‌ارتفاع
          که سلام می‌کند و کارِ امروز را می‌گوید. نه بیشتر. */}
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white px-5 py-3.5 shadow-rest">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary-deep">
            <GraduationCap className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-[16px] font-black text-ink">
              سلام {user?.full_name || user?.username}، ادامه بده
            </h1>
            <p className="text-[11px] text-ink-faint">{today} · هر جلسه حدود ۳۰ دقیقه</p>
          </div>
        </div>
      </header>

      {/* ══════════ ادامهٔ مسیر ══════════
          این بخش قلبِ داشبورد است و قبلاً یک کارتِ indigo با قابِ ضخیم و
          پس‌زمینهٔ گرادیانتی بود که با سه کارتِ زیرش هیچ فرقی در وزن نداشت.

          حالا چیدمانِ افقی و نامتقارن دارد: در راست، «کاری که امروز باید
          بکنی» با یک ورودیِ مبحث و یک دکمهٔ اصلی؛ در چپ، مسیرِ سه‌گامی به‌صورتِ
          یک خطِ عمودی با گره — همان موتیفِ مسیر که در کارنامه هم تکرار می‌شود. */}
      <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-rest">
        <div className="grid lg:grid-cols-12">
          {/* ── راست: ورودیِ مبحث ── */}
          <div className="p-5 sm:p-6 lg:col-span-7">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-primary-deep">
                <BrainCircuit className="h-4 w-4" strokeWidth={2.2} />
              </span>
              <div>
                <h2 className="text-[15px] font-black leading-tight text-ink">ادامهٔ مسیر</h2>
                <p className="text-[10.5px] text-ink-faint">مبحث را بگو، سؤال‌ها را می‌سازیم</p>
              </div>
            </div>

            <p className="mt-3 max-w-lg text-justify text-right text-[12px] leading-7 text-ink-soft">
              پنج تا ده سؤال که ذهنت را می‌خوانند: از پرسشِ مفهومی تا نقدِ یک استدلالِ غلط.
              هیچ نمره‌ای در کار نیست — خروجی، نقشهٔ فهمِ خودت است.
            </p>

            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <input
                value={xrayTopic}
                onChange={(event) => setXrayTopic(event.target.value)}
                onKeyDown={(event) => event.key === 'Enter' && startCognitiveAssessment()}
                placeholder={selectedConcept ? `مبحث: ${selectedConcept.name}` : 'مبحث را بنویس، مثلاً «فشار در مایعات»'}
                className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-surface-muted px-3.5 py-2.5 text-[12.5px] font-bold text-ink outline-none transition placeholder:font-normal placeholder:text-ink-faint focus:border-primary focus:bg-white focus:ring-2 focus:ring-primary/15"
              />
              <button
                type="button"
                onClick={startCognitiveAssessment}
                disabled={xrayStarting}
                className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-[12.5px] font-black text-white shadow-rest transition hover:bg-primary-deep disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
              >
                {xrayStarting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Fingerprint className="h-4 w-4" />
                )}
                {xrayStarting ? 'در حال ساختِ آزمون…' : 'سؤال‌های این مبحث را بساز'}
              </button>
            </div>

            {xrayError && (
              <p
                className="mt-2.5 rounded-lg border-r-2 border-danger bg-danger-soft px-3 py-2 text-[11px] font-bold text-danger"
                role="alert"
              >
                {xrayError}
              </p>
            )}
            {selectedConcept && (
              <p className="mt-2 text-[10.5px] text-ink-faint">
                مبحثِ انتخاب‌شده: «{selectedConcept.name}» — می‌توانی همین را بفرستی یا مبحثِ دیگری بنویسی.
              </p>
            )}
          </div>

          {/* ── چپ: مسیرِ سه‌گامی ── */}
          <aside className="border-t border-slate-100 bg-surface-muted p-5 sm:p-6 lg:col-span-5 lg:border-r lg:border-t-0">
            <p className="text-[10.5px] font-black text-ink-faint">مسیر تا کارنامه</p>
            <ol className="relative mt-3 space-y-3.5 border-r border-dashed border-slate-300 pr-4">
              {[
                { title: 'انتخاب مبحث', done: true },
                { title: 'پاسخ به سؤال‌ها', done: false },
                { title: 'کارنامه و نقشهٔ راه', done: false },
              ].map(({ title, done }) => (
                <li key={title} className="relative">
                  <span
                    className={`absolute -right-[21px] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-surface-muted ${
                      done ? 'bg-primary' : 'bg-slate-300'
                    }`}
                    aria-hidden="true"
                  />
                  <p
                    className={`text-[11.5px] font-bold ${
                      done ? 'text-ink' : 'text-ink-faint'
                    }`}
                  >
                    {title}
                  </p>
                </li>
              ))}
            </ol>
            <p className="mt-4 text-[10px] leading-5 text-ink-faint">
              هر جلسه حدود ۳۰ دقیقه؛ هر وقت خواستی می‌توانی مکث کنی.
            </p>
          </aside>
        </div>
      </section>

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
            <div className="flex flex-wrap items-end gap-4">
              <div className="min-w-[10rem] flex-1">
                <label className="label" htmlFor="subject">درس</label>
                <CustomDropdown
                  id="subject"
                  value={subject}
                  onChange={(v) => setSubject(v)}
                  ariaLabel="درس"
                  options={SUBJECTS.map(({ value, label }) => ({ value, label }))}
                />
              </div>
              <div className="min-w-[8rem] flex-1">
                <label className="label" htmlFor="grade">پایه</label>
                <CustomDropdown
                  id="grade"
                  value={grade}
                  onChange={(v) => setGrade(Number(v))}
                  ariaLabel="پایه"
                  options={GRADES.map((g) => ({ value: g, label: `پایهٔ ${toFarsiNumber(g)}` }))}
                />
              </div>
            </div>

            <div>
              <label className="label" htmlFor="concept">مفهوم مورد نظر</label>
              {loadingConcepts ? (
                <LoadingSpinner label="در حال دریافت مفهوم‌ها…" className="py-6" />
              ) : (
                <CustomDropdown
                  id="concept"
                  value={conceptId}
                  onChange={(v) => setConceptId(v)}
                  ariaLabel="مفهوم مورد نظر"
                  placeholder="— یک مفهوم انتخاب کن —"
                  options={[
                    { value: '', label: '— یک مفهوم انتخاب کن —' },
                    ...concepts.map((c) => ({
                      value: c.id,
                      label: `${c.name}${c.chapter ? ` (${c.chapter})` : ''}`,
                    })),
                  ]}
                />
              )}
              {!loadingConcepts && concepts.length === 0 && (
                <p className="mt-2 flex items-center gap-2 text-[12px] text-amber-800">
                  <Info className="h-4 w-4" /> برای این درس و پایه هنوز مفهومی در بانک نیست.
                </p>
              )}
            </div>

            {selectedConcept && (
              <div className="rounded-2xl border border-brand-100 bg-brand-50/60 p-4 text-[12px] leading-7 text-brand-900">
                <p className="font-black">{selectedConcept.name}</p>
                <p className="mt-1 text-brand-800/80">{selectedConcept.chapter}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(selectedConcept.target_behaviors ?? []).map((tag) => (
                    <span key={tag} className="chip bg-white text-brand-800 ring-1 ring-brand-200">{tagMap[tag] || tag}</span>
                  ))}
                </div>
              </div>
            )}

            <button onClick={startTopicSession} disabled={submitting || !conceptId} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-brand-700 py-4 text-[15px] font-black text-white shadow-lift transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60">
              {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Microscope className="h-5 w-5" />}
              شروع آزمون جامع تشخیصی
              <ArrowLeft className="h-5 w-5" />
            </button>
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
      {/* ── سه اصلِ کار ──
          قبلاً سه کارتِ هم‌اندازهٔ وسط‌چین. حالا یک نوارِ افقیِ شماره‌دار:
          سه گامِ یک مسیر، نه سه کارتِ مستقل. */}
      <section
        className="flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white px-5 py-4 sm:flex-row sm:items-center"
        aria-label="مسیرِ کار"
      >
        {HOW_STEPS.map(({ Icon, title, text }, i) => (
          <div key={title} className="flex flex-1 items-start gap-2.5">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[10px] font-black text-primary-deep">
              {toFarsiNumber(i + 1)}
            </span>
            <div className="min-w-0">
              <p className="flex items-center gap-1 text-[11.5px] font-black text-ink">
                <Icon className="h-3.5 w-3.5 text-primary" strokeWidth={2} />
                {title}
              </p>
              <p className="mt-0.5 text-[10.5px] leading-5 text-ink-faint">{text}</p>
            </div>
          </div>
        ))}
      </section>
        </>
      )}

      {/* ── تاریخچهٔ آزمون‌های من — دادهٔ واقعی دیتابیس (GET /api/student/history) ── */}
      <section className="rounded-2xl border border-slate-200/80 bg-white shadow-rest" aria-label="تاریخچهٔ آزمون‌های من">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3.5">
          <h2 className="flex items-center gap-2 text-[13px] font-black text-ink">
            <History className="h-4 w-4 text-primary" /> تاریخچهٔ آزمون‌های من
          </h2>
          <span className="text-[10px] font-bold text-ink-faint">
            {history?.length ? `${toFarsiNumber(history.length)} جلسه` : 'اتصال زنده به دیتابیس'}
          </span>
        </div>
        {historyError ? (
          <p className="m-4 rounded-lg border-r-2 border-caution bg-caution-soft px-3 py-2 text-[11.5px] font-bold text-caution" role="alert">
            {historyError}
          </p>
        ) : history === null ? (
          <div className="flex items-center justify-center gap-2 py-8 text-[11.5px] font-bold text-ink-faint">
            <Loader2 className="h-4 w-4 animate-spin text-primary" /> در حال دریافت تاریخچه…
          </div>
        ) : history.length === 0 ? (
          <p className="m-4 rounded-xl border border-dashed border-slate-200 bg-surface-muted px-4 py-8 text-center text-[11.5px] font-bold leading-6 text-ink-faint">
            هنوز آزمونی ثبت نکرده‌ای؛<br />اولین فهم‌سنجی را همین‌جا شروع کن.
          </p>
        ) : (
          /* ── فهرستِ تاریخچه ──
             جای گریدِ کارت‌های هم‌شکل: یک جدولِ سبکِ ردیفی. هر ردیف یک جلسه،
             با وضعیت در راست و اقدام در چپ — قابلِ اسکن با یک نگاه.

             نوزده ردیفِ پشتِ‌سرِهم خودش یک دیوار است؛ پنج جلسهٔ آخر نشان داده
             می‌شود و بقیه با یک دکمه باز می‌شوند. هیچ درخواستِ تازه‌ای به API
             نمی‌رود — همان آرایهٔ دریافت‌شده برش می‌خورد. */
          <ul className="divide-y divide-slate-100">
            {(showAllHistory ? history : history.slice(0, 5)).map((h) => (
              <li key={h.session_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3 transition-colors hover:bg-surface-muted">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-black text-ink">
                    {h.concept_name}
                    {h.subject && <span className="font-normal text-ink-faint"> · {subjectFa(h.subject)}</span>}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2.5 text-[10px] text-ink-faint">
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="h-3 w-3" />
                      {h.exam_date
                        ? new Date(h.exam_date).toLocaleDateString('fa-IR', { dateStyle: 'long' })
                        : '—'}
                    </span>
                    <span>{toFarsiNumber(h.questions_answered)} پاسخ</span>
                  </p>
                </div>
                <span className={`shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-black ${HISTORY_CHIP[h.comprehension] ?? HISTORY_CHIP.insufficient}`}>
                  {h.comprehension_label}
                </span>
                <button
                  type="button"
                  onClick={() => navigate(`/report/${h.session_id}`)}
                  className="shrink-0 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10.5px] font-black text-ink-soft transition hover:border-primary/40 hover:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  کارنامه
                </button>
              </li>
            ))}
          </ul>
        )}
        {!historyError && Array.isArray(history) && history.length > 5 && (
          <div className="border-t border-slate-100 px-5 py-2.5 text-center">
            <button
              type="button"
              onClick={() => setShowAllHistory((v) => !v)}
              className="text-[10.5px] font-black text-primary transition hover:text-primary-deep focus:outline-none focus-visible:underline"
            >
              {showAllHistory
                ? 'نمایشِ کمتر'
                : `نمایشِ همهٔ ${toFarsiNumber(history.length)} جلسه`}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
