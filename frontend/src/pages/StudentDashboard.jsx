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
  LogOut,
  ShieldCheck,
  Compass,
  BookOpenCheck,
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import CustomDropdown from '../components/CustomDropdown'

const SUBJECTS = [
  { value: 'math', label: 'ریاضی', Icon: Sigma },
  { value: 'physics', label: 'فیزیک', Icon: Atom },
  { value: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const GRADES = [10, 11, 12]

const HOW_STEPS = [
  { Icon: SearchCheck, title: '۱. دفترچهٔ ۹ سؤالی', text: 'از مفهومی تا نموداری — کل ابعاد فهم در یک آزمون.' },
  { Icon: Waypoints, title: '۲. بدون بازخورد لحظه‌ای', text: 'حین آزمون چیزی فاش نمی‌شود؛ پاسخ‌ها جمع می‌شوند تا تحلیل یکپارچه انجام شود.' },
  { Icon: Map, title: '۳. گزارش تشخیصی', text: 'ابعاد فهم، ریشهٔ بدفهمی‌ها و راهکارهای کیفی.' },
]

export default function StudentDashboard() {
  const { user, logout } = useAuth()
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
  const [started, setStarted] = useState(false) // false = صفحهٔ خوش‌آمد، true = جریان فهم‌سنجی
  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

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

  const selectedConcept = useMemo(
    () => concepts.find((c) => String(c.id) === String(conceptId)) ?? null,
    [concepts, conceptId],
  )

  const startTopicSession = async () => {
    if (!conceptId) return setError('اول یک مفهوم را انتخاب کن.')
    setSubmitting(true)
    setError('')
    try {
      // بدنه دقیقاً مطابق اسکیما: concept_id عدد صحیح + trigger_type ثابت
      const { data } = await client.post('/api/assess/start', {
        trigger_type: 'topic_selection',
        concept_id: Number.parseInt(conceptId, 10),
        wrong_answer: null,
      })
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
      const { data } = await client.post('/api/assess/start', {
        trigger_type: 'wrong_answer',
        concept_id: Number.parseInt(wrongConceptId, 10),
        wrong_answer: {
          problem_text: problemText.trim(),
          student_answer: wrongAnswer.trim(),
          concept_id: Number.parseInt(wrongConceptId, 10),
        },
      })
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
        <button
          type="button"
          onClick={handleLogout}
          className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-2 text-[12px] font-bold text-slate-600 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700"
        >
          <LogOut className="h-4 w-4" />
          خروج از حساب
        </button>
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
              دفترچهٔ ۹ سؤالی از همین مفهوم آماده است.
              در پایان، گزارش تشخیصیِ کامل با ریشه‌یابی بدفهمی‌هایت می‌سازیم.
            </p>
          </div>
          <div className="hidden shrink-0 flex-col items-center gap-2 rounded-3xl bg-white/10 px-6 py-4 text-center ring-1 ring-white/15 backdrop-blur md:flex">
            <HeartHandshake className="h-9 w-9 text-amber-200" />
            <p className="text-[11px] font-bold leading-5 text-brand-100">
              دفترچهٔ ۹ سؤالی
              <br /> تحلیل تک‌تک سؤال‌ها
            </p>
          </div>
        </div>
      </section>

      {/* ── تب‌های مسیر شروع ── */}
      <div className="grid gap-3 sm:grid-cols-2" role="tablist" aria-label="دو مسیر شروع آزمون جامع">
        {[
          { key: 'topic', Icon: Route, title: 'مسیر الف — آزمون جامع یک موضوع', sub: 'یک مفهوم درسی را انتخاب کن؛ دفترچهٔ ۹ سؤالی از همان مفهوم بساز' },
          { key: 'wrong_answer', Icon: GitBranch, title: 'مسیر ب — شروع از پاسخ اشتباه', sub: 'جواب اشتباهت را بفرست؛ دفترچهٔ ۹ سؤالی طوری ساخته می‌شود که ریشهٔ خطا را ردیابی کند' },
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
                  options={GRADES.map((g) => ({ value: g, label: `پایهٔ ${g}` }))}
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
                  {(selectedConcept.target_behaviors ?? []).map((b) => (
                    <span key={b} className="chip bg-white text-brand-800 ring-1 ring-brand-200">{b}</span>
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
                  ...allConcepts.map((c) => ({ value: c.id, label: `${c.name} · ${c.subject}` })),
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
    </div>
  )
}
