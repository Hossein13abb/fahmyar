import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Check, ChevronDown, ChevronLeft, GraduationCap, Layers, Sparkles, X } from 'lucide-react'
import {
  GRADE_LABELS,
  IRAN_CURRICULUM_DATA,
  MAJOR_LABELS,
  TOTAL_CONCEPTS,
  getChapters,
  getConcepts,
  getSubjects,
  resolveConcept,
} from '../lib/curriculum/iranHighSchoolCurriculum'
import { toFarsiNumber } from '../utils/faNumbers'

/**
 * انتخاب‌گرِ آبشاریِ رشته → پایه → درس → فصل → مفهوم.
 *
 * ── چرا پله‌به‌پله و نه یک فرمِ بلند ──
 * پنج دراپ‌داونِ کنارِ هم روی صفحه، دانش‌آموز را وادار می‌کند همه‌چیز را
 * هم‌زمان ببیند و سه‌تا‌شان تا انتخابِ قبلی خالی‌اند. این‌جا هر پله فقط وقتی
 * باز می‌شود که پلهٔ قبل انتخاب شده باشد — همان‌طور که آدم واقعاً انتخاب
 * می‌کند: اول رشته، بعد کتاب.
 *
 * ── دسترس‌پذیری ──
 * هر پله یک ``<fieldset>`` با ``legend`` است، انتخاب‌ها ``role="radio"``
 * هستند (نه دکمه‌های تزئینی)، و همیشه متنِ «گامِ بعدی» زیرِ دسترس است.
 */
function StepShell({ index, label, hint, done, active, children }) {
  // چیدمانِ دو‌ستونی: ریلِ باریکِ راست برای شماره+عنوان، ستونِ پهن برای گزینه‌ها.
  // دلیل: در چیدمانِ تک‌ستونی، یک کادرِ ۱۱۰۰px‌ای با دو پیلِ کوچک در گوشه
  // «خالی» به‌نظر می‌رسید. ریلِ ثابت این خالی‌بودن را پر می‌کند و روی موبایل
  // به هم می‌ریزد (flex-col).
  return (
    <div
      role="group"
      aria-label={label}
      aria-disabled={!active && !done}
      className={`flex flex-col gap-2.5 rounded-2xl border p-3 transition-colors sm:flex-row sm:items-start sm:gap-4 sm:p-3.5 ${
        active
          ? 'border-brand-300 bg-white'
          : done
            ? 'border-brand-100 bg-brand-50/40'
            : 'border-slate-200 bg-slate-50/50'
      }`}
    >
      <div className="flex shrink-0 items-center gap-2 sm:w-[104px] sm:flex-col sm:items-start sm:gap-1 sm:pt-0.5">
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${
            done
              ? 'bg-brand-600 text-white'
              : active
                ? 'bg-brand-800 text-white'
                : 'bg-slate-200 text-slate-500'
          }`}
          aria-hidden="true"
        >
          {done ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : toFarsiNumber(index)}
        </span>
        <span className={`text-[12.5px] font-black ${active || done ? 'text-brand-950' : 'text-slate-400'}`}>
          {label}
        </span>
        {active && hint && (
          <span className="hidden text-[10px] font-medium leading-4 text-slate-400 sm:block">{hint}</span>
        )}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/** کپسولِ انتخاب — دکمهٔ قابلِ کلیک با وضعیتِ واضح. */
function Pill({ selected, onClick, children, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      role="radio"
      aria-checked={selected}
      className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-[12px] font-bold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 ${
        selected
          ? 'border-brand-700 bg-brand-700 text-white shadow-sm'
          : 'border-slate-200 bg-white text-slate-700 hover:border-brand-300 hover:bg-brand-50'
      }`}
    >
      {selected && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
      {children}
    </button>
  )
}

/**
 * @param {{
 *   value: object|null,
 *   onChange: (sel: {major:string,grade:string,subjectId:string,chapterId:string,conceptId:string}|null) => void,
 *   disabled?: boolean,
 * }} props
 */
export default function CurriculumCascader({ value, onChange, disabled = false }) {
  const [major, setMajor] = useState(value?.major ?? '')
  const [grade, setGrade] = useState(value?.grade ?? '')
  const [subjectId, setSubjectId] = useState(value?.subjectId ?? '')
  const [chapterId, setChapterId] = useState(value?.chapterId ?? '')
  const [conceptId, setConceptId] = useState(value?.conceptId ?? '')
  // روی موبایل، پله‌های حل‌شده جمع می‌شوند تا صفحه بلند نشود.
  const [openStep, setOpenStep] = useState(1)

  const subjects = useMemo(() => (major && grade ? getSubjects(major, grade) : []), [major, grade])
  const chapters = useMemo(() => (subjectId ? getChapters(subjectId) : []), [subjectId])
  const concepts = useMemo(
    () => (subjectId && chapterId ? getConcepts(subjectId, chapterId) : []),
    [subjectId, chapterId],
  )

  const selected = useMemo(
    () => (major && grade && subjectId && chapterId && conceptId
      ? resolveConcept(major, grade, subjectId, chapterId, conceptId)
      : null),
    [major, grade, subjectId, chapterId, conceptId],
  )

  // هر تغییرِ سطحِ بالاتر، سطوحِ پایین‌تر را پاک می‌کند — وگرنه ترکیبِ
  // ناممکن می‌سازد (مثلاً «زیست‌شناسی ۱» زیرِ رشتهٔ ریاضی).
  const pickMajor = (m) => {
    setMajor(m)
    setGrade('')
    setSubjectId('')
    setChapterId('')
    setConceptId('')
    setOpenStep(2)
  }
  const pickGrade = (g) => {
    setGrade(g)
    setSubjectId('')
    setChapterId('')
    setConceptId('')
    setOpenStep(3)
  }
  const pickSubject = (id) => {
    setSubjectId(id)
    setChapterId('')
    setConceptId('')
    setOpenStep(4)
  }
  const pickChapter = (id) => {
    setChapterId(id)
    setConceptId('')
    setOpenStep(5)
  }
  const pickConcept = (id) => {
    setConceptId(id)
    setOpenStep(5)
  }

  useEffect(() => {
    onChange(selected)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.conceptId, selected?.major, selected?.grade])

  // وقتی همه‌چیز انتخاب شد، همهٔ پله‌ها جمع می‌شوند تا خلاصه دیده شود
  const collapsed = Boolean(selected)

  return (
    <div className="space-y-2.5">
      {/* ── پله ۱: رشته ── */}
      <StepShell
        index={1}
        label="رشته"
        hint="کدام رشته‌ای؟"
        done={Boolean(major)}
        active={openStep === 1}
      >
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="رشته">
          {Object.entries(MAJOR_LABELS).map(([key, label]) => (
            <Pill
              key={key}
              selected={major === key}
              onClick={() => pickMajor(key)}
              disabled={disabled}
            >
              {label}
            </Pill>
          ))}
        </div>
      </StepShell>

      {/* ── پله ۲: پایه ── */}
      {major && (
        <StepShell index={2} label="پایه" hint="کدام سالِ تحصیلی؟" done={Boolean(grade)} active={openStep === 2}>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="پایه">
            {Object.entries(GRADE_LABELS).map(([key, label]) => (
              <Pill key={key} selected={grade === key} onClick={() => pickGrade(key)} disabled={disabled}>
                {label}
              </Pill>
            ))}
          </div>
        </StepShell>
      )}

      {/* ── پله ۳: درس ── */}
      {grade && (
        <StepShell
          index={3}
          label="درس"
          hint={`${toFarsiNumber(subjects.length)} کتاب برای این رشته و پایه`}
          done={Boolean(subjectId)}
          active={openStep === 3}
        >
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" role="radiogroup" aria-label="درس">
            {subjects.map((sub) => {
              const isSel = subjectId === sub.id
              return (
                <button
                  key={sub.id}
                  type="button"
                  role="radio"
                  aria-checked={isSel}
                  disabled={disabled}
                  onClick={() => pickSubject(sub.id)}
                  className={`flex items-center gap-2.5 rounded-xl border px-3 py-2.5 text-right transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-50 ${
                    isSel
                      ? 'border-brand-600 bg-brand-50'
                      : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-brand-50/50'
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                      isSel ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    <BookOpen className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-black text-brand-950">{sub.title}</span>
                    <span className="block text-[10.5px] text-slate-500">
                      {toFarsiNumber(sub.chapters.length)} فصل
                    </span>
                  </span>
                  {isSel && <Check className="h-4 w-4 shrink-0 text-brand-600" strokeWidth={3} />}
                </button>
              )
            })}
          </div>
          {subjects.length === 0 && (
            <p className="text-[11.5px] text-amber-800">برای این ترکیب کتابی ثبت نشده است.</p>
          )}
        </StepShell>
      )}

      {/* ── پله ۴: فصل ── */}
      {subjectId && (
        <StepShell
          index={4}
          label="فصل"
          hint={`${toFarsiNumber(chapters.length)} فصل`}
          done={Boolean(chapterId)}
          active={openStep === 4}
        >
          <div className="max-h-64 space-y-1 overflow-y-auto pl-0.5" role="radiogroup" aria-label="فصل">
            {chapters.map((ch) => {
              const isSel = chapterId === ch.id
              return (
                <button
                  key={ch.id}
                  type="button"
                  role="radio"
                  aria-checked={isSel}
                  disabled={disabled}
                  onClick={() => pickChapter(ch.id)}
                  className={`flex w-full items-center gap-2 rounded-lg border px-3 py-2 text-right transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-50 ${
                    isSel
                      ? 'border-brand-600 bg-brand-50 text-brand-950'
                      : 'border-transparent bg-white text-slate-700 hover:border-brand-200 hover:bg-brand-50/40'
                  }`}
                >
                  <span className="shrink-0 text-[10.5px] font-black tabular-nums text-slate-400">
                    {toFarsiNumber(ch.chapterNumber)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px] font-bold">
                    {ch.title.replace(/^فصل\s*[۰-۹0-9]+\s*:\s*/, '')}
                  </span>
                  <span className="shrink-0 text-[10px] text-slate-400">
                    {toFarsiNumber(ch.concepts.length)} مفهوم
                  </span>
                </button>
              )
            })}
          </div>
        </StepShell>
      )}

      {/* ── پله ۵: مفهوم ── */}
      {chapterId && (
        <StepShell
          index={5}
          label="مفهوم کلیدی"
          hint={`${toFarsiNumber(concepts.length)} مفهوم در این فصل`}
          done={Boolean(conceptId)}
          active
        >
          <div className="max-h-72 space-y-1 overflow-y-auto pl-0.5" role="radiogroup" aria-label="مفهوم کلیدی">
            {concepts.map((c) => {
              const isSel = conceptId === c.id
              return (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  aria-checked={isSel}
                  disabled={disabled}
                  onClick={() => pickConcept(c.id)}
                  className={`flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-right transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 disabled:cursor-not-allowed disabled:opacity-50 ${
                    isSel
                      ? 'border-brand-600 bg-brand-50'
                      : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-brand-50/40'
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${
                      isSel ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300'
                    }`}
                    aria-hidden="true"
                  >
                    {isSel && <Check className="h-2.5 w-2.5" strokeWidth={4} />}
                  </span>
                  <span className="min-w-0 flex-1 text-[12px] font-bold leading-6 text-slate-800">
                    {c.title}
                  </span>
                </button>
              )
            })}
          </div>
        </StepShell>
      )}

      {/* ── خلاصهٔ انتخاب ── */}
      {selected ? (
        <div className="rounded-2xl border-2 border-brand-600 bg-brand-50/70 p-3.5">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="min-w-0 flex-1">
              <p className="text-[10.5px] font-bold text-brand-800">
                {MAJOR_LABELS[selected.major]} · {GRADE_LABELS[selected.grade]} · {selected.subjectTitle}
              </p>
              <p className="mt-0.5 text-[13px] font-black leading-6 text-brand-950">
                {selected.conceptTitle}
              </p>
              <p className="mt-0.5 text-[10.5px] text-brand-800/70">{selected.chapterTitle}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setConceptId('')
                setChapterId('')
                setOpenStep(1)
              }}
              className="shrink-0 rounded-lg p-1 text-brand-700 transition hover:bg-white"
              aria-label="تغییرِ انتخاب از ابتدا"
              title="تغییرِ انتخاب"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 px-1 text-[10.5px] text-slate-400">
          <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
          {openStep === 1 && 'اول رشته، بعد پایه، بعد کتاب — تا برسیم به مفهوم.'}
          {openStep === 2 && 'حالا پایهٔ تحصیلی را انتخاب کن.'}
          {openStep === 3 && 'کتاب را انتخاب کن؛ فصل‌ها خودشان می‌آیند.'}
          {openStep === 4 && 'فصل را انتخاب کن تا مفاهیمش باز شود.'}
          {openStep === 5 && `از ${toFarsiNumber(concepts.length)} مفهومِ این فصل یکی را انتخاب کن.`}
        </p>
      )}
    </div>
  )
}

export { TOTAL_CONCEPTS, IRAN_CURRICULUM_DATA }
