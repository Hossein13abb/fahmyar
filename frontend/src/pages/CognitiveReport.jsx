import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import client, { friendlyError } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import MathText from '../components/MathText'
import { toFarsiNumber } from '../utils/faNumbers'
import {
  FINDING_ICONS,
  PERSONA_ICONS,
  STAGE_ICONS,
  UI_ICONS,
} from '../components/cognitive/icons'

/**
 * کارنامهٔ اشعهٔ ایکس — گزارشِ کالبدشکافیِ ذهن.
 *
 * **هیچ نمره‌ای این‌جا نیست.** نه ۱۶ از ۲۰، نه درصد، نه رتبه. عدد در این
 * صفحه فقط یک کار می‌کند: مقایسه را تحریک می‌کند و انگیزهٔ یادگیری را
 * به «بیشتر شدنِ عدد» فرو می‌کاهد. این گزارش به‌جای «چقدر»، به «چگونه»
 * پاسخ می‌دهد.
 */

const FINDING_STYLES = {
  CONTRADICTION: {
    label: 'تناقض',
    wrap: 'border-rose-200 bg-rose-50',
    chip: 'bg-rose-600 text-white',
    title: 'text-rose-900',
  },
  JARGON_VIOLATION: {
    label: 'وابستگی به اصطلاح',
    wrap: 'border-amber-200 bg-amber-50',
    chip: 'bg-amber-500 text-white',
    title: 'text-amber-900',
  },
  BLUFF_DETECTED: {
    label: 'بلوف',
    wrap: 'border-orange-200 bg-orange-50',
    chip: 'bg-orange-500 text-white',
    title: 'text-orange-900',
  },
  SLIP_RESOLVED: {
    label: 'بی‌دقتیِ حل‌شده',
    wrap: 'border-sky-200 bg-sky-50',
    chip: 'bg-sky-600 text-white',
    title: 'text-sky-900',
  },
  SYNERGY: {
    label: 'هم‌خوانیِ درخشان',
    wrap: 'border-emerald-200 bg-emerald-50',
    chip: 'bg-emerald-600 text-white',
    title: 'text-emerald-900',
  },
}

const PERSONA_STYLES = {
  emerald: { ring: 'ring-emerald-200', bg: 'bg-emerald-50', text: 'text-emerald-900', bar: 'bg-emerald-500' },
  rose: { ring: 'ring-rose-200', bg: 'bg-rose-50', text: 'text-rose-900', bar: 'bg-rose-500' },
  amber: { ring: 'ring-amber-200', bg: 'bg-amber-50', text: 'text-amber-900', bar: 'bg-amber-500' },
  sky: { ring: 'ring-sky-200', bg: 'bg-sky-50', text: 'text-sky-900', bar: 'bg-sky-500' },
  slate: { ring: 'ring-slate-200', bg: 'bg-slate-50', text: 'text-slate-900', bar: 'bg-slate-400' },
}

// زیرعنوان باید با وضعیتِ واقعی هم‌خوان باشد. کارتِ پرسونا از یک قالبِ ثابت
// می‌آید، ولی وقتی مدل عنوانِ اختصاصی می‌دهد (مثلاً «استادِ بی‌دقت»)، زیرعنوانِ
// «ساعت را در ذهنت بستی» با آن تناقض پیدا می‌کند و گزارش بی‌اعتبار می‌شود.
const PERSONA_TITLES = {
  MASTERED: 'معمارِ مفهوم',
  ILLUSION_OF_COMPETENCE: 'گرفتارِ تضادِ فرمول و شهود',
  JARGON_DEPENDENT: 'معتاد به ادبیاتِ کتاب',
  PARTIAL_FRAGMENTED: 'تفکرِ جزیره‌ای',
  UNSTRUCTURED: 'نقشهٔ ذهنیِ نامنظم',
}

const STATUS_SUBTITLES = {
  MASTERED: 'ساعت را در ذهنت بستی',
  ILLUSION_OF_COMPETENCE: 'فرمول را بلدی، شهودت نه',
  JARGON_DEPENDENT: 'فهمِ محبوس در کلمات',
  PARTIAL_FRAGMENTED: 'چرخ‌دنده‌ها جدا از هم',
  UNSTRUCTURED: 'پایه‌ها هنوز شکل نگرفته',
}

function subtitleFor(status, personaTitle) {
  // اگر مدل عنوانِ اختصاصی داده و با عنوانِ قالبِ پرسونا یکی نیست،
  // زیرعنوانِ قالب دیگر معنا ندارد و باید حذف شود — نه اینکه چیزی بگوید
  // که با عنوان در تضاد است («استادِ بی‌دقت» + «ساعت را در ذهنت بستی»).
  const canonical = PERSONA_TITLES[status]
  if (personaTitle && canonical && personaTitle.trim() !== canonical) {
    return 'این عنوان را کارآگاه از دلِ پاسخ‌های خودت ساخت'
  }
  return STATUS_SUBTITLES[status] || ''
}

export default function CognitiveReport({ mode = 'student' }) {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)

  useEffect(() => {
    let alive = true
    client
      .get(`/api/assessment/${sessionId}`)
      .then(({ data: payload }) => {
        if (!alive) return
        if (payload.report?.needs_clarification) {
          navigate(`/exam/xray/${sessionId}/clarify`, { replace: true })
          return
        }
        if (!payload.report) {
          navigate(`/exam/xray/${sessionId}`, { replace: true })
          return
        }
        setData(payload)
      })
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [sessionId, navigate])

  const report = data?.report
  const evaluation = report?.evaluation_report || {}
  const persona = report?.persona
  const questions = data?.assessment?.questions || []
  const answers = data?.saved_answers || {}

  const style = PERSONA_STYLES[persona?.color] || PERSONA_STYLES.slate

  const insightsById = useMemo(() => {
    const map = {}
    ;(evaluation.question_by_question_insight || []).forEach((item) => {
      map[item.question_id] = item
    })
    return map
  }, [evaluation.question_by_question_insight])

  if (loading) return <LoadingSpinner label="در حال بازکردنِ کارنامه…" />

  if (error || !data) {
    return (
      <div className="mx-auto max-w-lg rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center shadow-soft">
        <p className="text-3xl">⚠️</p>
        <p className="mt-2 text-sm font-bold text-rose-900">{error || 'کارنامه پیدا نشد.'}</p>
        <button
          type="button"
          onClick={() => navigate(mode === 'teacher' ? '/staff' : '/dashboard')}
          className="mt-4 rounded-xl bg-brand-600 px-4 py-2 text-sm font-bold text-white"
        >
          بازگشت
        </button>
      </div>
    )
  }

  const findings = evaluation.cross_check_findings || []

  return (
    <div className="mx-auto max-w-3xl space-y-4 pb-16">
      {/* سربرگ + نشانِ پرسونا */}
      <header
        className={`overflow-hidden rounded-3xl border border-slate-200 ${style.bg} p-6 shadow-soft ring-1 ${style.ring} animate-fade-up`}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold text-slate-500">کارنامهٔ اشعهٔ ایکس · {data.topic}</p>
            <div className="mt-2 flex items-center gap-3">
              <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-white/80 ring-1 ${style.ring}`}>
                {(() => {
                  const PersonaIcon = PERSONA_ICONS[evaluation.mastery_status] || UI_ICONS.compass
                  return <PersonaIcon className={`h-7 w-7 ${style.text}`} strokeWidth={1.9} aria-hidden="true" />
                })()}
              </span>
              <div className="min-w-0">
                <h1 className={`text-xl font-extrabold sm:text-2xl ${style.text}`}>
                  {evaluation.persona_title || persona?.title}
                </h1>
                <p className="text-xs font-bold text-slate-500">
                  {subtitleFor(evaluation.mastery_status, evaluation.persona_title)}
                </p>
              </div>
            </div>
          </div>
          <span className="shrink-0 rounded-full bg-white/80 px-3 py-1 text-[10px] font-extrabold text-slate-600 ring-1 ring-slate-200">
            {report.status_label || {
              MASTERED: 'تسلطِ کامل',
              ILLUSION_OF_COMPETENCE: 'توهمِ یادگیری',
              JARGON_DEPENDENT: 'وابستگی به اصطلاحات',
              PARTIAL_FRAGMENTED: 'فهمِ ناقص',
              UNSTRUCTURED: 'نقشهٔ نامنظم',
            }[evaluation.mastery_status] || 'نامشخص'}
          </span>
        </div>

        <p className="mt-4 rounded-2xl bg-white/70 p-4 text-sm leading-7 text-slate-800">
          {evaluation.executive_summary || persona?.meaning}
        </p>

        {persona?.meaning && (
          <p className="mt-2 px-1 text-[11px] font-medium leading-6 text-slate-600">
            <strong className="font-extrabold">این یعنی چه؟ </strong>
            {persona.meaning}
          </p>
        )}
      </header>

      {/* یافته‌های مقایسه‌ای */}
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-card">
        <div className="mb-3 flex items-center gap-2">
          <UI_ICONS.search className="h-5 w-5 text-slate-700" strokeWidth={2.1} aria-hidden="true" />
          <h2 className="text-base font-extrabold text-slate-900">مچ‌گیری و تناقض‌ها</h2>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
            {toFarsiNumber(findings.length)} یافته
          </span>
        </div>

        {findings.length === 0 ? (
          <p className="rounded-xl bg-slate-50 p-4 text-xs font-medium text-slate-500">
            تناقضِ روشنی بین پاسخ‌ها پیدا نشد.
          </p>
        ) : (
          <div className="space-y-2.5">
            {findings.map((finding, index) => {
              const s = FINDING_STYLES[finding.type] || FINDING_STYLES.SYNERGY
              return (
                <article
                  key={index}
                  className={`rounded-2xl border p-4 ${s.wrap}`}
                  style={{ animationDelay: `${index * 60}ms` }}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {(() => {
                      const FindingIcon = FINDING_ICONS[finding.type] || UI_ICONS.sparkles
                      return <FindingIcon className={`h-4 w-4 ${s.title}`} strokeWidth={2.3} aria-hidden="true" />
                    })()}
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold ${s.chip}`}>
                      {s.label}
                    </span>
                    <h3 className={`text-sm font-extrabold ${s.title}`}>{finding.title}</h3>
                  </div>
                  <p className="mt-1.5 text-xs leading-6 text-slate-700">{finding.description}</p>
                </article>
              )
            })}
          </div>
        )}
      </section>

      {/* وضعیت قطعات ساعت */}
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-card">
        <div className="mb-3 flex items-center gap-2">
          <UI_ICONS.brain className="h-5 w-5 text-slate-700" strokeWidth={2.1} aria-hidden="true" />
          <h2 className="text-base font-extrabold text-slate-900">وضعیتِ قطعاتِ ساعت</h2>
        </div>
        <div className="space-y-2">
          {questions.map((question) => {
            const insight = insightsById[question.id]
            const answerText = answers[String(question.id)] || answers[question.id] || ''
            const missing = insight?.missing_gear
            return (
              <details
                key={question.id}
                className="group rounded-2xl border border-slate-200 bg-slate-50/60 p-3 open:bg-white"
              >
                <summary className="flex cursor-pointer list-none items-center gap-2">
                  {(() => {
                    const StageIcon = STAGE_ICONS[question.type]
                    return StageIcon ? (
                      <StageIcon className="h-4 w-4 shrink-0 text-slate-500" strokeWidth={2} aria-hidden="true" />
                    ) : null
                  })()}
                  <span className="flex-1 text-xs font-extrabold text-slate-800">
                    سؤال {toFarsiNumber(question.id)} · {question.title}
                  </span>
                  <span
                    className={[
                      'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold',
                      missing ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800',
                    ].join(' ')}
                  >
                    {missing ? `چرخ‌دندهٔ جاافتاده: ${missing}` : '✓ سالم'}
                  </span>
                </summary>
                <div className="mt-2.5 space-y-2 border-t border-slate-200 pt-2.5">
                  {insight?.cognitive_verdict && (
                    <p className="text-[11px] font-bold leading-6 text-slate-700">
                      {insight.cognitive_verdict}
                    </p>
                  )}
                  {answerText && (
                    <div className="rounded-xl bg-slate-50 p-2.5">
                      <p className="mb-1 text-[10px] font-bold text-slate-400">پاسخِ تو:</p>
                      <p className="whitespace-pre-wrap text-[11px] leading-6 text-slate-600">
                        <MathText content={answerText} />
                      </p>
                    </div>
                  )}
                </div>
              </details>
            )
          })}
        </div>
      </section>

      {/* توصیه */}
      <section className="rounded-3xl border-2 border-brand-200 bg-brand-50/60 p-5 shadow-soft">
        <div className="flex items-center gap-2">
          <UI_ICONS.target className="h-5 w-5 text-brand-800" strokeWidth={2.1} aria-hidden="true" />
          <h2 className="text-base font-extrabold text-brand-900">برای بستنِ کاملِ ساعت</h2>
        </div>
        <p className="mt-2 text-sm leading-7 text-brand-900/90">{evaluation.actionable_advice || persona?.advice_focus}</p>
        {persona?.advice_focus && evaluation.actionable_advice && (
          <p className="mt-2 rounded-xl bg-white/70 p-3 text-[11px] font-medium leading-6 text-brand-800">
            <strong className="font-extrabold">تمرینِ پیشنهادی: </strong>
            {persona.advice_focus}
          </p>
        )}
      </section>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => navigate(mode === 'teacher' ? '/staff' : '/dashboard')}
          className="rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-200"
        >
          بازگشت به داشبورد
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-50"
        >
          چاپ / ذخیرهٔ PDF
        </button>
      </div>
    </div>
  )
}
