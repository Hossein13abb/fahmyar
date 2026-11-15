import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import client, { friendlyError } from '../api/client'
import LoadingSpinner from '../components/LoadingSpinner'
import MathText from '../components/MathText'
import StageStepper from '../components/cognitive/StageStepper'
import ForbiddenWords from '../components/cognitive/ForbiddenWords'
import { countWords } from '../utils/forbidden'
import { toFarsiNumber } from '../utils/faNumbers'
import { BrainCircuit, Lightbulb, CheckCircle2 } from 'lucide-react'

/**
 * اتاقِ آزمونِ شناختی — پنج مرحلهٔ زنجیره‌ای.
 *
 * اصلِ طراحی: **در طولِ آزمون هیچ فیدبکی داده نمی‌شود.** نه درست/غلط، نه
 * درصد، نه پیامِ تشویقی. هر بازخوردی در این مرحله، ارزیابیِ بعدی را آلوده
 * می‌کند، چون کاربر پاسخ‌های بعدی‌اش را با آن تنظیم می‌کند و «شهودِ» واقعی
 * دیگر اندازه‌گیری نمی‌شود.
 */
const EMPTY_ANSWERS = { 1: '', 2: '', 3: '', 4: '', 5: '' }

const HINTS = {
  philosophy: 'بدونِ فرمول و عدد توضیح بده. ساده و صادقانه — نه قلمبه‌سلمبه.',
  mask_mcq: 'یک گزینه را انتخاب کن. اگر اطلاعاتِ اضافی دیدی، به خودت بگو چرا آن‌جاست.',
  perturbation: 'زنجیرهٔ علّی بنویس: چه چیزی تغییر می‌کند → بعد چه می‌شود → چرا.',
  debugging: 'یک جمله از استدلال را نقل کن و بگو کجای آن می‌لنگد.',
  feynman_synthesis: 'طوری بنویس که یک بچهٔ ۱۰ ساله بفهمد و بتواند برای دوستش تعریف کند.',
}

const MIN_WORDS = { philosophy: 15, perturbation: 15, debugging: 12, feynman_synthesis: 20 }

export default function CognitiveExamRoom() {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assessment, setAssessment] = useState(null)
  const [topic, setTopic] = useState('')
  const [stages, setStages] = useState([])
  const [answers, setAnswers] = useState(EMPTY_ANSWERS)
  const [index, setIndex] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const topRef = useRef(null)

  // بارگذاریِ آزمون — با بازیابیِ پاسخ‌های ذخیره‌شده اگر کاربر صفحه را رفرش کرده باشد.
  useEffect(() => {
    let alive = true
    setLoading(true)
    client
      .get(`/api/assessment/${sessionId}`)
      .then(({ data }) => {
        if (!alive) return
        setAssessment(data.assessment)
        setTopic(data.topic || '')
        setStages(data.stages || [])
        if (data.report) {
          // آزمون قبلاً تحلیل شده — مستقیم به کارنامه
          navigate(`/report/xray/${sessionId}`, { replace: true })
          return
        }
        const saved = data.saved_answers || {}
        setAnswers({
          1: saved['1'] ?? '',
          2: saved['2'] ?? '',
          3: saved['3'] ?? '',
          4: saved['4'] ?? '',
          5: saved['5'] ?? '',
        })
      })
      .catch((err) => alive && setError(friendlyError(err)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [sessionId, navigate])

  const questions = assessment?.questions || []
  const question = questions[index]
  const qid = question?.id ?? index + 1
  const totalStages = questions.length

  const answeredMap = useMemo(() => {
    const map = {}
    Object.entries(answers).forEach(([key, value]) => {
      if (String(value || '').trim()) map[Number(key)] = true
    })
    return map
  }, [answers])

  const answeredCount = Object.keys(answeredMap).length
  const isLast = index === totalStages - 1

  const setAnswer = useCallback(
    (value) => setAnswers((prev) => ({ ...prev, [qid]: value })),
    [qid],
  )

  const wordCount = countWords(answers[qid] || '')
  const minWords = MIN_WORDS[question?.type] || 0
  const tooShort = question?.type !== 'mask_mcq' && wordCount > 0 && wordCount < minWords
  const canAdvance = question?.type === 'mask_mcq' ? Boolean(answers[qid]) : wordCount >= 3

  const goTo = useCallback(
    (next) => {
      setIndex(Math.max(0, Math.min(totalStages - 1, next)))
      topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    },
    [totalStages],
  )

  const submitForAnalysis = async () => {
    setSubmitting(true)
    setError('')
    try {
      // ارسالِ همهٔ پاسخ‌ها *یک‌جا* — هیچ سؤالی جداگانه ارسال نمی‌شود.
      const payload = {}
      Object.entries(answers).forEach(([key, value]) => {
        if (String(value || '').trim()) payload[Number(key)] = String(value)
      })
      const { data } = await client.post(
        '/api/assessment/evaluate',
        { session_id: Number(sessionId), answers: payload },
        { timeout: 180000 },
      )
      if (data?.report?.needs_clarification) {
        navigate(`/exam/xray/${sessionId}/clarify`, { replace: true })
      } else {
        navigate(`/report/xray/${sessionId}`, { replace: true })
      }
    } catch (err) {
      setError(friendlyError(err))
      setConfirming(false)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <LoadingSpinner label="در حال آماده‌سازیِ آزمون…" />

  if (error && !assessment) {
    return (
      <div className="mx-auto max-w-lg rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center shadow-soft">
        <p className="text-3xl">⚠️</p>
        <p className="mt-2 text-sm font-bold text-rose-900">{error}</p>
        <button
          type="button"
          onClick={() => navigate('/dashboard')}
          className="mt-4 rounded-xl bg-brand-600 px-4 py-2 text-sm font-bold text-white"
        >
          بازگشت به داشبورد
        </button>
      </div>
    )
  }

  if (!question) return <LoadingSpinner label="سؤالی برای نمایش نیست…" />

  return (
    <div ref={topRef} className="mx-auto max-w-3xl space-y-4 pb-24">
      {/* سربرگ */}
      <header className="rounded-3xl border border-brand-100 bg-gradient-to-l from-brand-50 to-white p-5 shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold text-brand-600">آزمونِ فهم‌سنجی شناختی</p>
            <h1 className="mt-0.5 truncate text-lg font-extrabold text-brand-900 sm:text-xl">{topic}</h1>
          </div>
          <span className="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
            {toFarsiNumber(answeredCount)} از {toFarsiNumber(totalStages)} پاسخ
          </span>
        </div>
        <p className="mt-2 text-[11px] font-medium leading-5 text-slate-500">
          در طولِ آزمون هیچ بازخوردی نمی‌گیری. این عمدی است: اگر بدانی درست زدی یا نه،
          پاسخِ بعدی‌ات دیگر شهودِ خالص نیست.
        </p>
      </header>

      <StageStepper stages={stages} current={index} answered={answeredMap} onJump={goTo} />

      {/* کارتِ سؤال */}
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-card sm:p-7">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-brand-600 px-3 py-1 text-[11px] font-extrabold text-white">
            مرحلهٔ {toFarsiNumber(index + 1)}
          </span>
          <h2 className="text-base font-extrabold text-slate-900 sm:text-lg">{question.title}</h2>
        </div>

        <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-7 text-slate-800 sm:text-[15px]">
          <MathText content={question.question_text} />
        </div>

        <p className="mt-3 flex items-start gap-1.5 text-[11px] font-medium text-slate-500">
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" strokeWidth={2.2} aria-hidden="true" />
          <span>{HINTS[question.type]}</span>
        </p>

        {/* پاسخ */}
        <div className="mt-5">
          {question.type === 'mask_mcq' ? (
            <div className="space-y-2.5" role="radiogroup" aria-label="گزینه‌ها">
              {(question.options || []).map((option, optionIndex) => {
                const selected = answers[qid] === option
                return (
                  <button
                    key={optionIndex}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setAnswer(option)}
                    className={[
                      'flex w-full items-start gap-3 rounded-2xl border-2 p-3.5 text-right transition',
                      selected
                        ? 'border-brand-500 bg-brand-50 shadow-soft'
                        : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-slate-50',
                    ].join(' ')}
                  >
                    <span
                      className={[
                        'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-extrabold',
                        selected ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500',
                      ].join(' ')}
                    >
                      {toFarsiNumber(optionIndex + 1)}
                    </span>
                    <span className="min-w-0 flex-1 text-sm leading-6 text-slate-800">
                      <MathText content={option} />
                    </span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="space-y-3">
              {question.type === 'feynman_synthesis' && (
                <ForbiddenWords words={question.forbidden_words || []} answer={answers[qid] || ''} />
              )}
              <textarea
                value={answers[qid] || ''}
                onChange={(event) => setAnswer(event.target.value)}
                rows={question.type === 'feynman_synthesis' ? 8 : 6}
                placeholder="پاسخِ خودت را با کلماتِ خودت بنویس…"
                className="w-full resize-y rounded-2xl border-2 border-slate-200 p-4 text-sm leading-7 text-slate-800 outline-none transition focus:border-brand-400 focus:ring-4 focus:ring-brand-100"
              />
              <div className="flex items-center justify-between text-[11px] font-bold">
                <span className={tooShort ? 'text-amber-600' : 'text-slate-400'}>
                  {toFarsiNumber(wordCount)} کلمه
                  {tooShort ? ` · دستِ‌کم ${toFarsiNumber(minWords)} کلمه بنویس` : ''}
                </span>
                {wordCount >= minWords && (
                  <span className="inline-flex items-center gap-1 text-emerald-600">
                    <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden="true" />
                    به‌اندازهٔ کافی توضیح دادی
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {error && (
          <p className="mt-3 rounded-xl bg-rose-50 p-3 text-xs font-bold text-rose-800 ring-1 ring-rose-200">
            ⚠️ {error}
          </p>
        )}

        {/* ناوبری */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => goTo(index - 1)}
            disabled={index === 0}
            className="rounded-xl px-4 py-2 text-sm font-bold text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← مرحلهٔ قبل
          </button>

          {isLast ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              disabled={submitting || answeredCount === 0}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-extrabold text-white shadow-soft transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <BrainCircuit className="h-4 w-4" strokeWidth={2.4} aria-hidden="true" />
              پایان و تحلیلِ ذهن
            </button>
          ) : (
            <button
              type="button"
              onClick={() => goTo(index + 1)}
              disabled={!canAdvance}
              className="rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-extrabold text-white shadow-soft transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              مرحلهٔ بعد →
            </button>
          )}
        </div>

        {isLast && answeredCount < totalStages && (
          <p className="mt-3 text-[11px] font-medium text-amber-700">
            به {toFarsiNumber(totalStages - answeredCount)} سؤال پاسخ ندادی. می‌توانی همان‌ها را هم بنویسی،
            ولی تحلیل بر پایهٔ پاسخ‌های موجود انجام می‌شود.
          </p>
        )}
      </section>

      {/* گفت‌وگوی تأییدِ پایان */}
      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 backdrop-blur-sm sm:items-center"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-lift animate-fade-up">
            <h3 className="text-base font-extrabold text-slate-900">پایانِ آزمون و تحلیلِ ذهن</h3>
            <p className="mt-2 text-xs leading-6 text-slate-600">
              پس از این مرحله، پاسخ‌ها دیگر تغییرپذیر نیستند. هوش مصنوعی همهٔ جواب‌های تو را
              <strong className="mx-1 font-extrabold text-slate-900">با هم</strong>
              مقایسه می‌کند تا تناقض‌های ذهنی را پیدا کند — نه اینکه تک‌به‌تک نمره بدهد.
            </p>
            <ul className="mt-3 space-y-1 text-[11px] font-bold text-slate-500">
              <li>• {toFarsiNumber(answeredCount)} پاسخ ثبت شده</li>
              <li>• {toFarsiNumber(totalStages - answeredCount)} سؤال بی‌پاسخ</li>
            </ul>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                disabled={submitting}
                className="flex-1 rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:bg-slate-200"
              >
                بازگشت
              </button>
              <button
                type="button"
                onClick={submitForAnalysis}
                disabled={submitting}
                className="flex-1 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-extrabold text-white transition hover:bg-slate-800 disabled:opacity-60"
              >
                {submitting ? 'در حال تحلیل…' : 'بله، تحلیل کن'}
              </button>
            </div>
            {submitting && (
              <p className="mt-3 text-center text-[11px] font-medium text-slate-500">
                هوش مصنوعی در حال مقایسهٔ پاسخ‌ها با یکدیگر است…
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
