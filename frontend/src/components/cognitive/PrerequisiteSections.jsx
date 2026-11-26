/**
 * زنجیرهٔ ریشه‌یابی و گره‌های پیش‌نیاز — دو تمایزِ اصلیِ فهم‌یار.
 *
 * چرا این دو از هم جدا شده‌اند:
 *
 *   RootCauseAnalysis  می‌گوید **چطور** به این خطا رسیدی. یک داستانِ علّی از
 *                      یک گره در پایهٔ دهم تا خطای امروز در فیزیک دوازدهم.
 *
 *   LearningGaps       می‌گوید **چه چیزی** را تمرین کن. یک فهرستِ کوتاهِ
 *                      قابلِ‌اجرا که هر آیتمش یک دکمهٔ «آموزش سریع» دارد.
 *
 * زنجیره بدونِ گره، داستانِ بی‌عمل است؛ گره بدونِ زنجیره، فهرستِ بی‌دلیل.
 * کنارِ هم معنا پیدا می‌کنند — به همین ترتیب هم رندر می‌شوند.
 *
 * طراحی: تمِ روشنِ EdTech، همهٔ متن‌ها ترازِ دوطرفه، و هیچ استعارهٔ داخلی.
 */
import { useState } from 'react'
import { ArrowLeft, Compass, GitBranch, Lightbulb, Sparkles } from 'lucide-react'

const faNum = (v) => String(v ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

const rawText = (value) => String(value ?? '').trim()

/**
 * متنِ دانش‌آموز، با محافظت از فرمول‌ها.
 *
 * مدل گاهی فرمول را داخل ``$...$`` می‌گذارد و در متنِ فارسیِ RTL، همان
 * دلارها خام دیده می‌شوند («$P=VI$ را بنویس»). این‌جا دلارها برداشته
 * می‌شوند و خودِ فرمول در یک جزیرهٔ چپ‌به‌راست جدا می‌نشیند تا نه به
 * کلمهٔ قبل بچسبد و نه ترتیبِ جمله را به‌هم بزند.
 */
function MathAwareText({ text }) {
  const parts = rawText(text).split(/(\$[^$]+\$)/g).filter(Boolean)
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('$') && part.endsWith('$') && part.length > 2) {
          return (
            <span
              key={i}
              dir="ltr"
              className="mx-0.5 inline-block rounded bg-slate-100 px-1 font-mono text-[11px] tracking-tight text-slate-800"
            >
              {part.slice(1, -1)}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}

// ═══════════════════ زنجیرهٔ ریشه‌یابی ═══════════════════

/**
 * یک گرهِ زنجیره: نشانِ جایگاه (پایه + کتاب) بالای مفهوم.
 *
 * ``root_origin`` برجسته می‌شود — چون این همان چیزی است که دانش‌آموز باید
 * برگردد و ترمیمش کند. گره‌های میانی خنثی می‌مانند تا چشم اول به ریشه برود.
 */
function ChainNode({ node, index }) {
  const isRoot = node.role === 'root_origin'
  return (
    <div
      className={`relative flex-1 rounded-xl border p-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md ${
        isRoot
          ? 'border-rose-300 bg-gradient-to-br from-rose-50 to-amber-50/60 shadow-[0_0_0_3px_rgba(253,164,175,0.18)]'
          : 'border-indigo-100 bg-white shadow-sm'
      }`}
    >
      {isRoot && (
        <span className="absolute -top-2 right-3 rounded-full bg-rose-600 px-2 py-0.5 text-[9px] font-black text-white shadow-sm">
          ریشه اولیه لغزش
        </span>
      )}
      <span
        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-black ${
          isRoot ? 'bg-rose-100 text-rose-800' : 'bg-indigo-50 text-indigo-700'
        }`}
      >
        {rawText(node.grade_and_subject)}
      </span>
      <p
        className={`mt-1.5 text-justify text-right text-[12px] font-bold leading-6 ${
          isRoot ? 'text-rose-950' : 'text-slate-700'
        }`}
      >
        <MathAwareText text={node.concept_name} />
      </p>
      <span className="sr-only">گرهٔ {faNum(index + 1)}</span>
    </div>
  )
}

/** فلشِ بینِ گره‌ها — در موبایل می‌چرخد تا عمودی بخواند. */
function ChainConnector({ tone = 'indigo' }) {
  const color = tone === 'rose' ? 'text-rose-300 md:text-rose-400' : 'text-indigo-300 md:text-indigo-400'
  return (
    <div className="flex shrink-0 items-center justify-center py-1" aria-hidden="true">
      {/* در موبایل زنجیره عمودی است و از بالا (ریشه) به پایین (خطا) خوانده
          می‌شود؛ پس فلش باید به سمتِ پایین باشد. در دسکتاپ به سمتِ چپ. */}
      <ArrowLeft className={`h-5 w-5 -rotate-90 md:rotate-0 ${color}`} />
    </div>
  )
}

function RootCauseChain({ chain, index }) {
  const nodes = Array.isArray(chain.chain_nodes) ? chain.chain_nodes : []
  // ترتیبِ داده از نزدیک‌ترین پیش‌نیاز به ریشه است؛ برای خواندن، معکوس
  // می‌شود تا زنجیره از **ریشه** (راست، آغازِ خواندن) تا **خطای امروز**
  // (چپ، پایانِ مسیر) خوانده شود.
  const ordered = [...nodes].reverse()

  return (
    <div className={index > 0 ? 'mt-5 border-t border-slate-100 pt-5' : ''}>
      <div className="flex flex-col items-stretch gap-1 md:flex-row md:items-center">
        {ordered.map((node, i) => (
          <div key={i} className="contents">
            {i > 0 && <ChainConnector />}
            <ChainNode node={node} index={i} />
          </div>
        ))}
        {rawText(chain.current_error_title) && (
          <>
            <ChainConnector tone="rose" />
            {/* پایانِ مسیر: خطای امروز، به‌عنوان گرهِ آخرِ همان زنجیره */}
            <div className="flex-1 rounded-xl border border-rose-200 bg-gradient-to-br from-rose-100 to-rose-50 p-3 shadow-sm">
              <span className="inline-flex items-center gap-1 rounded-md bg-rose-200/70 px-2 py-0.5 text-[10px] font-black text-rose-900">
                خطای فعلی
              </span>
              <p className="mt-1.5 text-justify text-right text-[12px] font-black leading-6 text-rose-950">
                <MathAwareText text={chain.current_error_title} />
              </p>
            </div>
          </>
        )}
      </div>

      {rawText(chain.diagnosis_summary) && (
        <p className="mt-3 border-t border-slate-100 pt-3 text-justify text-right text-[12px] leading-7 text-slate-600">
          <MathAwareText text={chain.diagnosis_summary} />
        </p>
      )}
    </div>
  )
}

export function RootCauseAnalysisSection({ chains }) {
  const list = (Array.isArray(chains) ? chains : []).filter(
    (c) => c && Array.isArray(c.chain_nodes) && c.chain_nodes.length >= 2,
  )
  if (list.length === 0) return null

  return (
    <section className="rounded-2xl border border-indigo-100 bg-white p-6 shadow-panel">
      <header className="mb-4 flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 text-white shadow-sm">
          <GitBranch className="h-4.5 w-4.5" strokeWidth={2.3} />
        </span>
        <div className="min-w-0">
          <h3 className="text-[15px] font-black text-slate-900">
            ریشه‌یابی زنجیره‌ای لغزش‌ها و پیش‌نیازها
          </h3>
          <p className="mt-1 text-justify text-right text-[11px] leading-6 text-slate-500">
            چگونه گره‌های پایه‌ای در مقاطعِ قبل، مانعِ تسلط بر مبحثِ فعلی شدند؟
          </p>
        </div>
      </header>

      {list.map((chain, i) => (
        <RootCauseChain key={i} chain={chain} index={i} />
      ))}
    </section>
  )
}

// ═══════════════════ گره‌های پیش‌نیاز ═══════════════════

const SEVERITY = {
  critical: {
    label: 'نیازمند یادگیری عمیق',
    dot: '🔴',
    badge: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  },
  shaky: {
    label: 'مرز لغزنده — نیازمند تثبیت',
    dot: '🟡',
    badge: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  },
}

/**
 * کارتِ یک گره — دکمه‌اش مودالِ «میز معلم» را با ``type: "learning_gap"``
 * باز می‌کند. تا پاسخ نرسیده، دکمه در حالتِ انتظار می‌ماند.
 */
function GapCard({ gap, onTeach, busy }) {
  const sev = SEVERITY[gap.severity] ?? SEVERITY.shaky
  return (
    <article className="flex flex-col rounded-xl border border-slate-200 bg-slate-50/70 p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-white hover:shadow-md">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-black ${sev.badge}`}
        >
          <span aria-hidden="true">{sev.dot}</span>
          {sev.label}
        </span>
        {rawText(gap.source_topic) && (
          <span
            className="rounded-full bg-white px-2.5 py-1 text-[10px] font-bold text-slate-600 ring-1 ring-slate-200"
            dir="auto"
          >
            {gap.source_topic}
          </span>
        )}
      </div>

      <h4 className="mt-2 text-justify text-right text-[13px] font-black leading-6 text-slate-900">
        {rawText(gap.gap_title)}
      </h4>

      {rawText(gap.why_you_slipped) && (
        <p className="mt-1.5 text-justify text-right text-[12px] leading-7 text-slate-700">
          {gap.why_you_slipped}
        </p>
      )}

      {rawText(gap.quick_fix_tip) && (
        <div className="mt-3 flex items-start gap-1.5 rounded-lg border border-emerald-100 bg-emerald-50/60 p-2.5">
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" strokeWidth={2.4} />
          <p className="text-justify text-right text-[11px] leading-6 text-emerald-900">
            <MathAwareText text={gap.quick_fix_tip} />
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={() => onTeach?.(gap)}
        disabled={busy}
        className="mt-auto flex w-full items-center justify-center gap-1.5 rounded-lg bg-gradient-to-l from-brand-700 to-emerald-600 px-4 py-2.5 pt-2.5 text-[11px] font-black text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:from-brand-800 hover:to-emerald-700 hover:shadow-md active:translate-y-0 disabled:opacity-60"
        style={{ marginTop: '0.75rem' }}
      >
        <Sparkles className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
        {busy ? 'معلم دارد آماده می‌کند…' : 'آموزش سریع و ریشه‌ای این گره'}
      </button>
    </article>
  )
}

export function LearningGapsSection({ gaps, onTeach }) {
  const [busyId, setBusyId] = useState(null)
  const list = (Array.isArray(gaps) ? gaps : []).filter((g) => rawText(g?.gap_title))
  if (list.length === 0) return null

  const teach = async (gap) => {
    setBusyId(gap.id ?? gap.gap_title)
    try {
      await onTeach?.(gap)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="rounded-2xl border border-emerald-100 bg-white p-6 shadow-panel">
      <header className="mb-4 flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
          <Compass className="h-4.5 w-4.5" strokeWidth={2.3} />
        </span>
        <div className="min-w-0">
          <h3 className="text-[15px] font-black text-slate-900">
            ایستگاه‌های نیازمند ترمیم (حلقه‌های پیش‌نیاز)
          </h3>
          <p className="mt-1 text-justify text-right text-[11px] leading-6 text-slate-500">
            گره‌هایی که با یک بار یادگیریِ هدفمند، مسیرِ تسلط را کامل می‌کنند.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {list.map((gap, i) => (
          <GapCard
            key={gap.id ?? i}
            gap={gap}
            busy={busyId === (gap.id ?? gap.gap_title)}
            onTeach={teach}
          />
        ))}
      </div>
    </section>
  )
}
