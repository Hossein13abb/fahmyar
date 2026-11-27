import { AlertCircle, CheckCircle2, HelpCircle, Layers } from 'lucide-react'
import { toFarsiNumber } from '../../utils/faNumbers'

/**
 * ابعاد پنج‌گانهٔ فهم — کارت‌های تسلط (فاز ۳۰).
 *
 * چرا بازنویسی شد
 * ---------------
 * نسخهٔ قبلی پنج کارتِ متنیِ هم‌شکل بود: یک برچسبِ کوچکِ وضعیت در گوشه و یک
 * پاراگرافِ کوتاه. دانش‌آموز نمی‌توانست در یک نگاه بفهمد کدام مهارت قوی است و
 * کدام نه — همه مثل هم دیده می‌شدند و تنها تفاوت، رنگِ حاشیه بود.
 *
 * این نسخه سه چیز را با هم نشان می‌دهد:
 *   ۱. **نامِ مهارت** به زبانِ دانش‌آموز، نه نامِ درونیِ سنجش («دانش مفهومی»).
 *   ۲. **نوارِ تسلط** که از پاسخ‌های واقعیِ همان مهارت ساخته شده.
 *   ۳. **تحلیلِ یک‌خطیِ متنی** که می‌گوید در همین آزمون چه اتفاقی افتاد.
 *
 * ⚠️ نوارِ تسلط هرگز عددِ ساختگی نشان نمی‌دهد. اگر برای مهارتی هیچ شاهدی
 * ثبت نشده باشد، نوار و برچسبِ سطح اصلاً رندر نمی‌شوند — به‌جایش یک خطِ
 * صادقانه می‌آید که «این مهارت در این آزمون سنجیده نشد». پر کردنِ نوار با
 * عددِ حدسی، همان دادهٔ ساختگی است که محصول اجازه نمی‌دهد.
 */

const LEVEL_STYLE = {
  mastered: {
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    icon: CheckCircle2,
    iconClass: 'text-emerald-600',
    label: 'تسلط کامل',
    bar: 'bg-emerald-500',
    card: 'border-emerald-200/80 bg-gradient-to-br from-emerald-50/70 via-white to-white',
    dot: 'bg-emerald-500',
  },
  shaky: {
    badge: 'bg-amber-50 text-amber-800 border-amber-200',
    icon: HelpCircle,
    iconClass: 'text-amber-600',
    label: 'نیازمند تثبیت',
    bar: 'bg-amber-400',
    card: 'border-amber-200/80 bg-gradient-to-br from-amber-50/70 via-white to-white',
    dot: 'bg-amber-400',
  },
  needs_work: {
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    icon: AlertCircle,
    iconClass: 'text-rose-600',
    label: 'نیازمند تقویت',
    bar: 'bg-rose-400',
    card: 'border-rose-200/80 bg-gradient-to-br from-rose-50/70 via-white to-white',
    dot: 'bg-rose-400',
  },
}

/** نگاشتِ وضعیتِ بک‌اند (developing) به سطحِ نمایشیِ کارت. */
const LEVEL_FROM_STATUS = {
  mastered: 'mastered',
  developing: 'shaky',
  needs_work: 'needs_work',
}

function normalize(dim, fallbackTitles) {
  const level =
    dim.mastery_level ??
    LEVEL_FROM_STATUS[String(dim.status ?? '').toLowerCase()] ??
    null
  const style = level ? LEVEL_STYLE[level] : null
  return {
    key: dim.id ?? dim.key ?? fallbackTitles.index,
    title: dim.title ?? dim.label ?? fallbackTitles[dim.key] ?? 'مهارت ذهنی',
    subtitle: dim.subtitle ?? '',
    insight: String(dim.finding ?? dim.insight ?? '').trim(),
    level,
    style,
    score: typeof dim.score_pct === 'number' ? dim.score_pct : null,
  }
}

export default function DimensionsSection({ dimensions, fallbackTitles = {} }) {
  if (!Array.isArray(dimensions) || dimensions.length === 0) return null

  const items = dimensions.map((d) => normalize(d, fallbackTitles))
  // کارتِ آخر اگر تعداد فرد باشد، تمام‌عرض می‌شود تا یک خانهٔ خالی نماند.
  const odd = items.length % 2 !== 0

  return (
    <section className="card p-5 sm:p-6">
      {/* ── سربرگ ── */}
      <div className="mb-5 flex items-start gap-3 border-b border-slate-100 pb-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
          <Layers className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-[15px] font-black text-brand-950">
            ابعادِ پنج‌گانهٔ فهم — کالبدشکافیِ مهارت‌های ذهنی
          </h3>
          <p className="mt-1 text-[11.5px] font-medium leading-5 text-slate-500">
            ارزیابیِ دقیقِ شیوهٔ فکر کردنت در ۵ جنبهٔ کلیدیِ تسلط بر این مفهوم
          </p>
        </div>
      </div>

      {/* ── کارت‌ها ── */}
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item, idx) => {
          const Style = item.style
          const Icon = Style?.icon
          const isLastOdd = odd && idx === items.length - 1
          return (
            <article
              key={`${item.key}-${idx}`}
              className={`flex flex-col rounded-2xl border p-4 transition-colors ${
                Style ? Style.card : 'border-slate-200 bg-slate-50/60'
              } ${isLastOdd ? 'md:col-span-2' : ''}`}
            >
              {/* سرِ کارت: عنوان + برچسبِ سطح */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h4 className="text-[13px] font-black leading-6 text-brand-950">{item.title}</h4>
                  {item.subtitle && (
                    <p className="mt-0.5 text-[10.5px] font-medium leading-5 text-slate-500">
                      {item.subtitle}
                    </p>
                  )}
                </div>
                {Style && Icon && (
                  <span
                    className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10.5px] font-black ${Style.badge}`}
                  >
                    <Icon className={`h-3 w-3 ${Style.iconClass}`} aria-hidden="true" />
                    {Style.label}
                  </span>
                )}
              </div>

              {/* نوارِ تسلط — فقط با دادهٔ واقعی */}
              {item.level && (
                <div className="my-3">
                  <div className="mb-1 flex items-baseline justify-between">
                    <span className="text-[10px] font-bold text-slate-400">میزانِ تسلط در این آزمون</span>
                    {item.score !== null && (
                      <span className="text-[10.5px] font-black tabular-nums text-slate-500">
                        {toFarsiNumber(item.score)}٪
                      </span>
                    )}
                  </div>
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80"
                    role="img"
                    aria-label={`میزانِ تسلط: ${Style.label}`}
                  >
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${Style.bar}`}
                      style={{ width: `${Math.min(100, Math.max(6, item.score ?? 0))}%` }}
                    />
                  </div>
                </div>
              )}

              {/* تحلیل — بدونِ داده هم جملهٔ صادقانه می‌آید، نه کارتِ خالی */}
              <p className="mt-1 text-justify text-[12px] leading-6 text-slate-600">
                {item.insight ||
                  'برای این مهارت در این آزمون شاهدِ کافی ثبت نشد؛ درباره‌اش داوری نمی‌کنیم.'}
              </p>
            </article>
          )
        })}
      </div>
    </section>
  )
}
