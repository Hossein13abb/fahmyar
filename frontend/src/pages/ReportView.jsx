import { useEffect, useState } from 'react'
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
} from 'lucide-react'
import client, { friendlyError } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'

function SectionCard({ Icon, title, tone = 'brand', children, className = '' }) {
  const tones = {
    brand: 'border-brand-100 bg-white/85',
    amber: 'border-amber-200/70 bg-amber-50/50',
    teal: 'border-teal-100 bg-teal-50/40',
  }
  const iconTones = {
    brand: 'bg-brand-100 text-brand-800',
    amber: 'bg-amber-100 text-amber-800',
    teal: 'bg-teal-100 text-teal-800',
  }
  return (
    <section className={`card border ${tones[tone]} p-5 ${className}`}>
      <h2 className="flex items-center gap-2.5 text-[15px] font-black text-brand-950">
        <span className={`rounded-2xl p-2 ${iconTones[tone]}`}>
          <Icon className="h-5 w-5" />
        </span>
        {title}
      </h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

export default function ReportView({ mode = 'student' }) {
  const { sessionId, studentId } = useParams()
  const navigate = useNavigate()
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
        <button onClick={() => navigate(-1)} className="mt-4 rounded-2xl border border-brand-200 px-5 py-2.5 font-bold text-brand-800 hover:bg-brand-50">
          بازگشت
        </button>
      </div>
    )
  }

  const s = report.sections ?? {}
  const observations = s['مشاهدات'] ?? []
  const evidenceLines = s['شواهد'] ?? []
  const unclear = s['موارد هنوز روشن‌نشده'] ?? []
  const studentActions = s['پیشنهاد اقدام برای دانش‌آموز'] ?? []
  const teacherNotes = s['یادداشت برای معلم'] ?? []
  const rootCauses = s['فرضیه‌های ریشهٔ خطا'] ?? []
  const propositionStatuses = report.proposition_statuses ?? {}
  const generatedAt = report.generated_at ? new Date(report.generated_at).toLocaleDateString('fa-IR', { dateStyle: 'long' }) : ''

  return (
    <div className="animate-fade-up space-y-5">
      {/* ── بنر الزامی ── */}
      <div className="no-print flex items-center gap-3 rounded-3xl border border-amber-300/70 bg-gradient-to-l from-amber-100 to-calm-100 px-5 py-3.5 text-amber-900 shadow-card">
        <AlertTriangle className="h-6 w-6 shrink-0" />
        <p className="text-[13px] font-black leading-7">
          ⚠️ نمرهٔ آزمون — نه سنجش فهم
          <span className="block text-[11px] font-medium text-amber-800">
            این گزارش «فهمیدن» را توصیف می‌کند؛ هیچ عدد، نمره یا رتبه‌ای در آن نیست و جایگزین گفت‌وگوی معلم با دانش‌آموز نمی‌شود.
          </span>
        </p>
      </div>

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
            {report.needs_teacher_review && <Badge status="PENDING_REVIEW" />}
          </div>
        </div>
        <div className="no-print flex shrink-0 flex-col gap-2">
          <button onClick={() => window.print()} className="flex items-center justify-center gap-2 rounded-2xl bg-brand-700 px-5 py-3 text-[13px] font-black text-white shadow-card transition hover:bg-brand-800">
            <Printer className="h-5 w-5" />
            چاپ / دانلود گزارش
          </button>
          <button
            onClick={() => navigate(mode === 'teacher' ? '/teacher' : '/dashboard')}
            className="flex items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-3 text-[13px] font-bold text-brand-800 transition hover:bg-brand-50"
          >
            <ArrowRight className="h-5 w-5" />
            {mode === 'teacher' ? 'بازگشت به پنل معلم' : 'بازگشت به داشبورد'}
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
                  <span className="mt-0.5 shrink-0 font-black text-brand-400">{i + 1}.</span>
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard Icon={HelpCircle} title="موارد هنوز روشن‌نشده" tone="amber" className="lg:col-span-2">
          {unclear.length === 0 ? (
            <p className="flex items-center gap-2 text-[13px] font-bold text-emerald-800">
              <CheckCircle2 className="h-5 w-5" /> مورد مبهمی باقی نمانده است 🌱
            </p>
          ) : (
            <ul className="space-y-2">
              {unclear.map((u, i) => (
                <li key={i} className="rounded-2xl border border-amber-200/60 bg-white/70 px-4 py-2.5 text-[12px] leading-6 text-amber-950">
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
            <ol className="mt-3 list-decimal space-y-1.5 pr-5 text-[12px] leading-7 text-slate-600">
              {evidenceLines.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ol>
          </details>
        )}
      </SectionCard>

      {/* ── فرضیه‌های ریشهٔ خطا (مسیر B) ── */}
      {rootCauses.length > 0 && (
        <SectionCard Icon={GitBranch} title="فرضیه‌های ریشهٔ خطا" tone="amber">
          <ul className="space-y-1.5">
            {rootCauses.map((line, i) => (
              <li key={i} className="rounded-2xl border border-amber-200/60 bg-white/70 px-4 py-2.5 text-[12px] leading-6 text-amber-950">
                {line}
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      {/* ── پیشنهاد گام بعدی ── */}
      <div className={`grid gap-4 ${mode === 'teacher' ? 'lg:grid-cols-2' : ''}`}>
        <SectionCard Icon={Lightbulb} title={mode === 'teacher' ? 'پیشنهاد برای دانش‌آموز' : 'گام بعدی تو'}>
          <ul className="space-y-2">
            {studentActions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-7 text-brand-950">
                <span className="mt-0.5 shrink-0 font-black text-brand-400">{i + 1}.</span>
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
                    <span className="mt-0.5 shrink-0 font-black text-amber-500">{i + 1}.</span>
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
                    <div key={i} className="rounded-xl border border-slate-100 bg-white p-3 text-[11px] leading-6 text-slate-600">
                      <p className="font-black text-slate-500">پاسخ {i + 1} — سؤال #{entry.question_id}</p>
                      <p className="mt-0.5 line-clamp-2">{entry.response}</p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {(entry.evidence ?? []).map((ev, j) => (
                          <Badge key={j} status={ev.status} />
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
