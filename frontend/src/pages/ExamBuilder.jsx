import { useEffect, useMemo, useState } from 'react'
import {
  ClipboardEdit,
  Sigma,
  Atom,
  FlaskConical,
  Leaf,
  BookOpen,
  Languages,
  MoonStar,
  Minus,
  Plus,
  Timer,
  Building2,
  Sparkles,
  Shuffle,
  Save,
  Trash2,
  FileText,
  ChevronDown,
  Info,
  Smile,
  Meh,
  Flame,
  Rocket,
  Wand2,
  Loader2,
} from 'lucide-react'
import { toFarsiNumber } from '../utils/faNumbers'

const SUBJECTS = [
  { id: 'math', label: 'ریاضی', Icon: Sigma, grad: 'from-indigo-500 to-blue-600' },
  { id: 'physics', label: 'فیزیک', Icon: Atom, grad: 'from-cyan-500 to-teal-600' },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical, grad: 'from-emerald-500 to-green-600' },
  { id: 'biology', label: 'زیست‌شناسی', Icon: Leaf, grad: 'from-lime-500 to-emerald-600' },
  { id: 'literature', label: 'ادبیات فارسی', Icon: BookOpen, grad: 'from-rose-500 to-pink-600' },
  { id: 'english', label: 'زبان انگلیسی', Icon: Languages, grad: 'from-violet-500 to-purple-600' },
  { id: 'arabic', label: 'عربی', Icon: MoonStar, grad: 'from-amber-500 to-orange-600' },
]

const TIME_PRESETS = [45, 60, 75, 90, 100, 120]
const DIFFICULTY_OPTIONS = [
  { id: 'easy', label: 'آسان', desc: 'سؤال‌های مستقیم و پایه‌ای', Icon: Smile },
  { id: 'medium', label: 'متوسط', desc: 'استاندارد و متعادل', Icon: Meh },
  { id: 'hard', label: 'سخت', desc: 'عمیق و تحلیلی', Icon: Flame },
  { id: 'challenging', label: 'چالش‌برانگیز', desc: 'بالاتر از سطح کتاب درسی', Icon: Rocket },
]
const GEN_STEPS = [
  'در حال انتخاب سؤال‌های متناسب از بانک مؤسسات…',
  'در حال تولید سؤال‌های هوش مصنوعی…',
  'در حال چینش دفترچه و زمان‌بندی آزمون…',
]
const SOURCE_OPTIONS = [
  { id: 'bank', label: 'بانک سؤالات مؤسسات', desc: 'سؤال‌های استاندارد و تأییدشده از بانک‌های معتبر', Icon: Building2 },
  { id: 'ai', label: 'تولید هوش مصنوعی', desc: 'دفترچهٔ تشخیصی تولیدشده توسط فهم‌یار', Icon: Sparkles },
  { id: 'hybrid', label: 'ترکیبی', desc: 'ترکیبِ بانک مؤسسات + سؤالات هوش مصنوعی', Icon: Shuffle },
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

export default function ExamBuilder({ embedded = false }) {
  const [selected, setSelected] = useState(['math'])           // درس‌های انتخابی
  const [counts, setCounts] = useState({ math: 10 })           // تعداد سؤال هر درس
  const [duration, setDuration] = useState(100)                // دقیقه
  const [source, setSource] = useState('hybrid')               // bank | ai | hybrid
  const [bankShare, setBankShare] = useState(60)               // درصد سهم بانک در حالت ترکیبی
  const [difficulty, setDifficulty] = useState('medium')       // easy | medium | hard | challenging
  const [generating, setGenerating] = useState(false)          // در حال تولید آزمون (شبیه‌سازی)
  const [genStep, setGenStep] = useState(0)                    // کپشن‌های در حال چرخش
  const [drafts, setDrafts] = useState(loadDrafts)
  const [notice, setNotice] = useState('')
  const [title, setTitle] = useState('')

  useEffect(() => {
    // اگر درسی برداشته شد، تعداد سؤالش هم پاک شود؛ اگر اضافه شد، پیش‌فرض ۱۰
    setCounts((prev) => {
      const next = {}
      for (const id of selected) next[id] = prev[id] ?? 10
      return next
    })
  }, [selected])

  const totalQuestions = useMemo(
    () => selected.reduce((sum, id) => sum + (Number(counts[id]) || 0), 0),
    [selected, counts],
  )
  const questionsPerMinute = duration > 0 ? (totalQuestions / duration).toFixed(2) : '—'

  const toggleSubject = (id) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]))

  const bump = (id, delta) =>
    setCounts((prev) => ({ ...prev, [id]: Math.min(30, Math.max(1, (Number(prev[id]) || 10) + delta)) }))

  useEffect(() => {
    if (!generating) return undefined
    const t = window.setInterval(() => setGenStep((s) => (s + 1) % GEN_STEPS.length), 750)
    return () => window.clearInterval(t)
  }, [generating])

  const persist = (list) => {
    setDrafts(list)
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(list))
    } catch {
      /* فضای ذخیره پر است — فقط در همین نشست نگه می‌داریم */
    }
  }

  const validate = () => {
    if (selected.length === 0) return 'حداقل یک درس را انتخاب کنید.'
    if (totalQuestions < 1) return 'تعداد کل سؤالات باید حداقل ۱ باشد.'
    if (!duration || duration < 10) return 'زمان آزمون باید حداقل ۱۰ دقیقه باشد.'
    return ''
  }

  const buildDraft = (status) => ({
    id: Date.now(),
    title: title.trim() || `آزمون ${SUBJECTS.filter((s) => selected.includes(s.id)).map((s) => s.label).join(' + ')}`,
    subjects: selected,
    counts,
    duration,
    source,
    bankShare: source === 'hybrid' ? bankShare : null,
    totalQuestions,
    difficulty,
    createdAt: new Date().toISOString(),
    status,
  })

  const saveDraft = () => {
    const err = validate()
    if (err) return setNotice(`⚠️ ${err}`)
    persist([buildDraft('draft'), ...drafts].slice(0, 12))
    setNotice('✓ پیش‌نویس آزمون ذخیره شد.')
  }

  // ── تولید آزمون — شبیه‌سازی کامل جریان واقعی: Loading → موفقیت → انتشار برای دانش‌آموزان ──
  const generateExam = () => {
    const err = validate()
    if (err) return setNotice(`⚠️ ${err}`)
    setNotice('')
    setGenStep(0)
    setGenerating(true)
    window.setTimeout(() => {
      persist([buildDraft('published'), ...drafts].slice(0, 12))
      setGenerating(false)
      setNotice('آزمون با موفقیت ساخته شد و در دسترس دانش‌آموزان قرار گرفت')
    }, 2400)
  }

  const removeDraft = (id) => persist(drafts.filter((d) => d.id !== id))

  const selectedSubjects = SUBJECTS.filter((s) => selected.includes(s.id))
  const difficultyLabel = DIFFICULTY_OPTIONS.find((d) => d.id === difficulty)?.label ?? 'متوسط'

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── سربرگ صفحه (در حالت نهفته داخل داشبورد کادر مدرسه حذف می‌شود) ── */}
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
              <h1 className="text-xl font-black text-white sm:text-2xl">طراحی آزمون مدرسه</h1>
              <p className="mt-1 text-[12px] font-medium text-brand-100/85">
                دفترچهٔ ترکیبی بساز: درس‌ها، تعداد سؤال، زمان و منبع سؤالات را مشخص کن.
              </p>
            </div>
          </div>
          <div className="rounded-2xl bg-white/10 px-4 py-2.5 text-center ring-1 ring-white/15 backdrop-blur">
            <p className="text-2xl font-black leading-none text-amber-200">{fmtFa(totalQuestions)}</p>
            <p className="mt-1 text-[10px] font-bold text-brand-100/80">سؤال در این آزمون</p>
          </div>
        </div>
      </section>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        {/* ══════════ ستون فرم ══════════ */}
        <div className="space-y-6 lg:col-span-8">
          {/* ── نام آزمون ── */}
          <section className="card p-5 sm:p-6">
            <label htmlFor="exam-title" className="label">نام آزمون (اختیاری)</label>
            <input
              id="exam-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="مثلاً: آزمون جامع هماهنگ نوبت اول — تجربی"
              className="input"
            />
          </section>

          {/* ── ۱) انتخاب درس‌های ترکیبی ── */}
          <section className="card p-5 sm:p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۱</span>
                انتخاب درس‌های ترکیبی
              </h2>
              <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">{fmtFa(selected.length)} درس فعال</span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
              {SUBJECTS.map(({ id, label, Icon, grad }) => {
                const on = selected.includes(id)
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggleSubject(id)}
                    aria-pressed={on}
                    className={`group flex flex-col items-center gap-2 rounded-2xl border p-3.5 transition-all duration-200 ${
                      on
                        ? 'border-transparent bg-gradient-to-br text-white shadow-lift ring-2 ring-brand-300/60 ' + grad
                        : 'border-slate-200/80 bg-slate-50/50 text-slate-600 hover:border-brand-200 hover:bg-white hover:shadow-soft'
                    }`}
                  >
                    <Icon className={`h-7 w-7 ${on ? 'text-white' : 'text-brand-700'}`} strokeWidth={1.8} />
                    <span className="text-[12px] font-black leading-5">{label}</span>
                    <span className={`text-[10px] font-bold ${on ? 'text-white/85' : 'text-slate-400'}`}>
                      {on ? '✓ انتخاب شد' : 'لمس برای انتخاب'}
                    </span>
                  </button>
                )
              })}
            </div>
          </section>

          {/* ── ۲) تعداد سؤال هر درس ── */}
          <section className="card p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۲</span>
              تعداد سؤال هر درس
            </h2>
            {selectedSubjects.length === 0 ? (
              <p className="mt-3 flex items-center gap-2 text-[12px] text-slate-500"><Info className="h-4 w-4" /> اول درس‌های بالا را انتخاب کن.</p>
            ) : (
              <ul className="mt-4 divide-y divide-slate-100">
                {selectedSubjects.map(({ id, label, Icon }) => (
                  <li key={id} className="flex items-center justify-between gap-3 py-3">
                    <span className="flex min-w-0 items-center gap-2.5 text-[13px] font-bold text-brand-950">
                      <span className="rounded-xl bg-brand-50 p-2 text-brand-700"><Icon className="h-4 w-4" /></span>
                      <span className="truncate">{label}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <button type="button" onClick={() => bump(id, -1)} aria-label="کاهش سؤال" className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 shadow-sm transition hover:border-brand-300 hover:bg-brand-50">
                        <Minus className="h-4 w-4" />
                      </button>
                      <span className="w-10 text-center text-[17px] font-black tabular-nums text-brand-900">{fmtFa(counts[id] ?? 10)}</span>
                      <button type="button" onClick={() => bump(id, +1)} aria-label="افزایش سؤال" className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 shadow-sm transition hover:border-brand-300 hover:bg-brand-50">
                        <Plus className="h-4 w-4" />
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ── ۳) زمان آزمون ── */}
          <section className="card p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۳</span>
              زمان آزمون
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
              <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
                <Timer className="h-4 w-4 text-brand-700" />
                <input
                  type="number"
                  min={10}
                  max={300}
                  value={duration}
                  onChange={(e) => setDuration(Math.max(0, Number(e.target.value) || 0))}
                  className="w-16 bg-transparent text-center text-[14px] font-black tabular-nums text-brand-900 outline-none"
                  aria-label="زمان دلخواه (دقیقه)"
                />
                <span className="text-[11px] font-bold text-slate-400">دقیقه</span>
              </label>
            </div>
          </section>

          {/* ── ۴) تعیین سطح سختی ── */}
          <section className="card p-6 sm:p-7">
            <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
              <Flame className="h-5 w-5 text-brand-700" /> تعیین سطح سختی
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

          {/* ── ۵) منبع سؤالات ── */}
          <section className="card p-5 sm:p-6">
            <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
              <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۴</span>
              منبع سؤالات
            </h2>
            <div role="radiogroup" aria-label="منبع سؤالات" className="mt-4 grid gap-2.5 sm:grid-cols-3">
              {SOURCE_OPTIONS.map(({ id, label, desc, Icon }) => {
                const on = source === id
                return (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => setSource(id)}
                    className={`flex flex-col items-center gap-2 rounded-2xl border p-4 text-center transition-all duration-200 ${
                      on
                        ? 'border-brand-500 bg-brand-50/70 shadow-lift ring-2 ring-brand-300/70'
                        : 'border-slate-200/80 bg-white hover:border-brand-200 hover:shadow-soft'
                    }`}
                  >
                    <span className={`rounded-2xl p-2.5 ${on ? 'bg-brand-700 text-amber-200' : 'bg-brand-50 text-brand-700'}`}>
                      <Icon className="h-6 w-6" strokeWidth={1.8} />
                    </span>
                    <span className="text-[13px] font-black text-brand-950">{label}</span>
                    <span className="text-[10px] leading-5 text-slate-500">{desc}</span>
                  </button>
                )
              })}
            </div>

            {source === 'hybrid' && (
              <div className="mt-4 rounded-2xl border border-brand-100 bg-brand-50/50 p-4">
                <div className="flex items-center justify-between gap-3 text-[12px] font-black text-brand-900">
                  <span>سهم بانک مؤسسات: {fmtFa(bankShare)}٪</span>
                  <span>سهم هوش مصنوعی: {fmtFa(100 - bankShare)}٪</span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={90}
                  step={10}
                  value={bankShare}
                  onChange={(e) => setBankShare(Number(e.target.value))}
                  className="mt-3 w-full accent-brand-700"
                  aria-label="سهم بانک سؤالات در حالت ترکیبی"
                />
                <div className="mt-1.5 flex justify-between text-[10px] font-bold text-slate-400">
                  <span>۹۰٪ بانک · ۱۰٪ AI</span>
                  <span>۵۰ / ۵۰</span>
                  <span>۱۰٪ بانک · ۹۰٪ AI</span>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* ══════════ ستون کنار: پیش‌نمایش + پیش‌نویس‌ها ══════════ */}
        <div className="space-y-6 lg:col-span-4">
          <section className="card overflow-hidden p-0">
            <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3.5">
              <h2 className="flex items-center gap-2 text-[14px] font-black text-brand-950"><FileText className="h-4 w-4 text-brand-700" /> پیش‌نمایش آزمون</h2>
            </div>
            <dl className="space-y-2.5 px-5 py-4 text-[12px] leading-7">
              <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                <dt className="text-slate-500">درس‌ها</dt>
                <dd className="text-left font-bold text-brand-950">{selectedSubjects.map((s) => s.label).join(' + ') || '—'}</dd>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                <dt className="text-slate-500">تعداد سؤال</dt>
                <dd className="font-black tabular-nums text-brand-950">{fmtFa(totalQuestions)} سؤال</dd>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                <dt className="text-slate-500">زمان</dt>
                <dd className="font-black tabular-nums text-brand-950">{fmtFa(duration)} دقیقه</dd>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                <dt className="text-slate-500">سطح سختی</dt>
                <dd className="font-bold text-brand-950">{difficultyLabel}</dd>
              </div>
              <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                <dt className="text-slate-500">سرعت تقریبی</dt>
                <dd className="font-bold tabular-nums text-brand-950">{questionsPerMinute} سؤال/دقیقه</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-slate-500">منبع</dt>
                <dd className="font-bold text-brand-950">
                  {SOURCE_OPTIONS.find((s) => s.id === source)?.label}
                  {source === 'hybrid' && ` (${fmtFa(bankShare)}٪ بانک / ${fmtFa(100 - bankShare)}٪ AI)`}
                </dd>
              </div>
            </dl>
            <div className="border-t border-slate-100 bg-white px-5 py-4">
              <button onClick={generateExam} disabled={generating} className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-3.5 text-[14px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-80">
                {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
                {generating ? 'در حال تولید آزمون…' : 'تولید آزمون'}
              </button>
              <button onClick={saveDraft} className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white py-3 text-[13px] font-bold text-brand-800 transition hover:bg-brand-50">
                <Save className="h-5 w-5" /> ذخیرهٔ پیش‌نویس
              </button>
              {notice && (
                <p className={`mt-3 rounded-2xl px-4 py-2.5 text-[11px] font-bold leading-6 ${notice.startsWith('⚠️') ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`} role="status">
                  {notice}
                </p>
              )}
            </div>
          </section>

          {/* ── پیش‌نویس‌های ذخیره‌شده ── */}
          {drafts.length > 0 && (
            <section className="card p-5">
              <h2 className="flex items-center justify-between gap-2 text-[13px] font-black text-brand-950">
                <span className="flex items-center gap-2"><ChevronDown className="h-4 w-4 rotate-[-90deg] text-brand-700" /> پیش‌نویس‌های من ({fmtFa(drafts.length)})</span>
              </h2>
              <ul className="mt-3 max-h-72 space-y-2 overflow-auto">
                {drafts.map((d) => (
                  <li key={d.id} className="flex items-start justify-between gap-2 rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-black text-brand-950">{d.title}</p>
                      <p className="mt-0.5 text-[10px] leading-5 text-slate-500">
                        {fmtFa(d.totalQuestions)} سؤال · {fmtFa(d.duration)} دقیقه · {SOURCE_OPTIONS.find((s) => s.id === d.source)?.label}
                        {d.difficulty && ` · سختی: ${DIFFICULTY_OPTIONS.find((x) => x.id === d.difficulty)?.label ?? ''}`}
                        {d.status === 'published' ? ' · ✓ منتشر شد' : d.status === 'submitted' ? ' · ✓ ثبت‌شده' : ' · پیش‌نویس'}
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
      </div>

      {/* ── پوشش تمام‌صفحهٔ «در حال تولید آزمون» ── */}
      {generating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm" role="alertdialog" aria-modal="true" aria-label="در حال تولید آزمون">
          <div className="w-full max-w-md rounded-3xl border border-emerald-100 bg-white p-8 text-center shadow-lift">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 ring-1 ring-emerald-100">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
            </span>
            <h3 className="mt-5 text-lg font-black text-slate-800">در حال تولید آزمون…</h3>
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
