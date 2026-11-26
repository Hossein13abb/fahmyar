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
import {
  ArrowLeft,
  BookOpen,
  Check,
  Compass,
  GitBranch,
  Info,
  Sparkles,
} from 'lucide-react'
import { UnifiedSectionHeader } from './UnifiedSectionHeader'

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
/** توکنی که واقعاً فرمول است: حروفِ لاتین + عملگر، بدونِ فاصله. */
const FORMULA = /^[A-Za-z][A-Za-z0-9_^{}\s./=+\-*()]*[=^/]/u

function isFormula(token) {
  if (!token || token.length > 24) return false
  const clean = token.replace(/[،؛.:!؟«»"'()]/g, '')
  if (!clean || !FORMULA.test(clean)) return false
  // فقط حروفِ لاتین/عدد/عملگر — اگر حرفِ فارسی داشت، فرمول نیست
  return /^[A-Za-z0-9_^{}./=+\-*]+$/.test(clean)
}

function MathAwareText({ text }) {
  const parts = rawText(text).split(/(\$[^$]+\$)/g).filter(Boolean)
  return (
    <>
      {parts.map((part, i) => {
        // حالتِ اول: مدل خودش دلار گذاشته
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
        // حالتِ دوم: فرمولِ خام مثلِ «I=V/R» که در متنِ فارسی جابه‌جا می‌شود
        const words = part.split(/(\s+)/)
        return (
          <span key={i}>
            {words.map((w, j) =>
              isFormula(w) ? (
                <span
                  key={j}
                  dir="ltr"
                  className="mx-0.5 inline-block rounded bg-slate-100 px-1 font-mono text-[11px] tracking-tight text-slate-800"
                >
                  {w}
                </span>
              ) : (
                w
              ),
            )}
          </span>
        )
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
          ? 'border-amber-300 bg-gradient-to-br from-amber-50 to-amber-50/40 shadow-[0_0_0_3px_rgba(251,191,36,0.18)]'
          : 'border-indigo-100 bg-white shadow-sm'
      }`}
    >
      {isRoot && (
        <span className="absolute -top-2 right-3 rounded-full bg-amber-500 px-2 py-0.5 text-[9px] font-black text-white shadow-sm">
          ریشه اولیه لغزش
        </span>
      )}
      <span
        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-black ${
          isRoot ? 'bg-amber-100 text-amber-800' : 'bg-indigo-50 text-indigo-700'
        }`}
      >
        <BookOpen className="h-2.5 w-2.5 shrink-0 opacity-70" aria-hidden="true" />
        {rawText(node.grade_and_subject)}
      </span>
      <p
        className={`mt-1.5 text-justify text-right text-[12px] font-bold leading-6 ${
          isRoot ? 'text-amber-950' : 'text-slate-700'
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
                لغزش مشاهده‌شده
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

/**
 * نشانِ منبعِ داده.
 *
 * زنجیره‌ای که از misconceptions خودِ آزمون ساخته شده، با زنجیره‌ای که مدل
 * نوشته یکی نیست — و پنهان‌کردنِ این تفاوت، اعتماد را می‌شکند. متن کوتاه
 * است تا دانش‌آموز را نترساند، ولی صادق است.
 */
function SourceNote({ items }) {
  if (!(items || []).some((c) => c?.generated_by === 'fallback')) return null
  return (
    <p className="mt-4 flex items-start gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[10px] leading-5 text-slate-500">
      <Info className="mt-0.5 h-3 w-3 shrink-0 text-slate-400" aria-hidden="true" />
      <span className="text-justify text-right">
        این بخش از مفاهیمِ ثبت‌شدهٔ همین مبحث و پاسخ‌های خودت ساخته شده است.
      </span>
    </p>
  )
}

export function RootCauseAnalysisSection({ chains }) {
  const list = (Array.isArray(chains) ? chains : []).filter(
    (c) => c && Array.isArray(c.chain_nodes) && c.chain_nodes.length >= 2,
  )
  if (list.length === 0) return null

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-rest md:p-6">
      <UnifiedSectionHeader
        icon={GitBranch}
        accentColor="indigo"
        title="ریشه‌یابی زنجیره‌ای لغزش‌ها و پیش‌نیازها"
        subtitle="ردیابی این‌که کدام گره‌های پایه‌ای در مقاطع قبل، مانعِ تسلط بر مبحثِ فعلی شدند"
      />

      {list.map((chain, i) => (
        <RootCauseChain key={i} chain={chain} index={i} />
      ))}

      <SourceNote items={list} />
    </section>
  )
}

// ═══════════════════ ایستگاه‌های نقشهٔ راه ترمیم ═══════════════════

const SEVERITY = {
  critical: {
    label: 'پیش‌نیاز حیاتی • نیازمند یادگیری عمیق',
    dot: '🔴',
    pin: 'bg-rose-500 text-white ring-rose-100',
    badge: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  },
  shaky: {
    label: 'مرز لغزنده • نیازمند تثبیت',
    dot: '🟡',
    pin: 'bg-amber-400 text-slate-900 ring-amber-100',
    badge: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  },
}

/**
 * یک ایستگاه از نقشهٔ راه.
 *
 * تفاوتِ طراحی با کارتِ آزمونی، عمدی و معنادار است:
 *
 *   • ستونِ رز «گره ذهنی» است، نه «پاسخِ غلط». باورِ دانش‌آموز را نام می‌برد.
 *   • ستونِ زمرد «نگاه درست» است، نه «پاسخِ صحیح». حقیقتِ علمی را می‌گوید.
 *   • دکمه pill است، نه نوارِ تمام‌عرض — چون اینجا «ارسالِ پاسخ» نیست،
 *     «رفتن به ایستگاه» است.
 *
 * اگر مدل هیچ متنی برای یکی از دو ستون نداد، همان ستون حذف می‌شود و
 * ستونِ دیگر تمامِ عرض را می‌گیرد؛ جعبهٔ خالیِ برچسب‌دار ساخته نمی‌شود.
 */
function GapStation({ gap, index, onTeach, busy }) {
  const sev = SEVERITY[gap.severity] ?? SEVERITY.shaky
  const belief = rawText(gap.why_you_slipped)
  const insight = rawText(gap.quick_fix_tip)
  const station = faNum(index + 1).padStart(2, '۰')

  return (
    <li className="relative flex flex-col items-start gap-4 md:flex-row md:gap-6">
      {/* نشانِ ایستگاه — لنگرِ خطِ زمان */}
      <div className="z-10 flex shrink-0 items-center gap-3 self-start md:flex-col">
        <div
          className={`flex h-11 w-11 flex-col items-center justify-center rounded-2xl shadow-sm ring-4 md:h-14 md:w-14 ${sev.pin}`}
        >
          <span className="text-[9px] font-medium leading-none opacity-80 md:text-[10px]">
            ایستگاه
          </span>
          <span className="mt-0.5 text-sm font-black leading-none md:text-base">
            {station}
          </span>
        </div>
      </div>

      {/* بدنهٔ ایستگاه */}
      <div className="w-full flex-1 rounded-xl border border-slate-200/80 bg-white p-4 md:p-5">
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          {rawText(gap.source_topic) && (
            <span
              className="rounded-md bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-500"
              dir="auto"
            >
              {gap.source_topic}
            </span>
          )}
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-black ${sev.badge}`}
          >
            <span aria-hidden="true">{sev.dot}</span>
            {sev.label}
          </span>
        </div>

        <h4 className="mb-4 text-justify text-right text-[14px] font-black leading-6 text-slate-800">
          <MathAwareText text={gap.gap_title} />
        </h4>

        <div
          className={`mb-4 grid gap-3 ${
            belief && insight ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1'
          }`}
        >
          {belief && (
            <div className="rounded-xl border border-rose-100 bg-rose-50/50 p-3.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-black text-rose-800">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-rose-500" />
                گره ذهنی و دامِ پرتکرار
              </div>
              <p className="text-justify text-right text-[12px] leading-7 text-slate-700">
                <MathAwareText text={belief} />
              </p>
            </div>
          )}
          {insight && (
            <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-3.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-black text-emerald-800">
                <Check className="h-3.5 w-3.5 text-emerald-600" strokeWidth={3} />
                نگاه درست و کلیدِ حلِ مسئله
              </div>
              <p className="text-justify text-right text-[12px] leading-7 text-slate-700">
                <MathAwareText text={insight} />
              </p>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <span className="text-[10px] font-medium text-slate-400">
            آموزشِ مکالمه‌ای و مفهومی در ۲ دقیقه
          </span>
          <button
            type="button"
            onClick={() => onTeach?.(gap)}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-[11px] font-black text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-indigo-600 hover:shadow-md active:translate-y-0 disabled:opacity-60"
          >
            <Sparkles className={`h-3.5 w-3.5 text-amber-300 ${busy ? 'animate-spin' : ''}`} />
            <span>{busy ? 'معلم دارد آماده می‌کند…' : 'رفع سریع این گره با معلم هوشمند'}</span>
            <ArrowLeft className="h-3.5 w-3.5 text-slate-400" />
          </button>
        </div>
      </div>
    </li>
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
    <section className="rounded-3xl border border-slate-200/90 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.06)] transition-all duration-300 hover:shadow-[0_18px_44px_rgba(15,23,42,0.10)] md:p-6">
      <UnifiedSectionHeader
        icon={Compass}
        accentColor="emerald"
        title="ایستگاه‌های نقشهٔ راه ترمیم"
        badgeText={`${faNum(list.length)} گره شناسایی‌شده`}
        subtitle="مفاهیمِ بنیادیِ پیش‌نیاز که با یک بار بازخوانیِ هدفمند، مسیرِ تسلط را کامل می‌کنند"
      />

      {/* خطِ زمانِ نقشه: در موبایل پشتِ نشان‌ها، در دسکتاپ درست زیرِ آن‌ها */}
      <ol className="relative space-y-5 before:absolute before:inset-y-2 before:right-[1.375rem] before:hidden before:w-0.5 before:bg-slate-200 md:before:block md:before:right-[1.75rem] md:before:content-['']">
        {list.map((gap, i) => (
          <GapStation
            key={gap.id ?? i}
            gap={gap}
            index={i}
            busy={busyId === (gap.id ?? gap.gap_title)}
            onTeach={teach}
          />
        ))}
      </ol>

      <SourceNote items={list} />
    </section>
  )
}
