/**
 * هدرِ مشترکِ همهٔ بخش‌های کارنامه — یک زبان، چهار لهجه.
 *
 * چرا کامپوننت و نه تکرارِ کلاس‌ها: پیش از این، هر بخش هدرِ خودش را داشت و
 * نتیجه‌اش صفحه‌ای بود که شبیهِ چند محصولِ چسبیده به هم دیده می‌شد. رنگ
 * «لهجه» را عوض می‌کند، ولی ساختار (آیکونِ مربعِ گرد + عنوان + بج + زیرعنوان)
 * در همه یکی است — همان چیزی که صفحه را منسجم می‌کند بدونِ اینکه بخش‌ها
 * یکنواخت شوند.
 *
 * قاعدهٔ رنگ که از قبل در پروژه بود و این‌جا هم رعایت می‌شود:
 * زمردی=خوب، کهربایی=هشدار، رز=آسیب، ایندیگو=پیش‌نیاز/تحلیلِ ریشه‌ای.
 */
const ACCENTS = {
  /* ── فاز ۲۷: آیکونِ آرام ──
     نسخهٔ قبل گرادیانتِ دو‌رنگ + سایهٔ رنگیِ اشباع + ring-4 داشت؛ همین یک
     عنصر، صفحه را «داشبوردِ SaaS» می‌کرد. حالا آیکون یک پلاکِ کم‌رنگ با
     آیکونِ رنگ‌شده است: لهجه را می‌رساند، بدونِ اینکه چشم را بزند. */
  emerald: {
    icon: 'bg-primary-soft text-primary',
    badge: 'bg-primary-soft text-primary-deep border-primary/20',
    rail: 'from-primary via-primary/70 to-primary-soft',
  },
  indigo: {
    icon: 'bg-analytic-soft text-analytic',
    badge: 'bg-analytic-soft text-analytic border-analytic/20',
    rail: 'from-analytic via-analytic/70 to-analytic-soft',
  },
  rose: {
    icon: 'bg-danger-soft text-danger',
    badge: 'bg-danger-soft text-danger border-danger/20',
    rail: 'from-danger via-danger/70 to-danger-soft',
  },
  amber: {
    icon: 'bg-caution-soft text-caution',
    badge: 'bg-caution-soft text-caution border-caution/20',
    rail: 'from-caution via-caution/70 to-caution-soft',
  },
}

export function UnifiedSectionHeader({
  icon: Icon,
  accentColor = 'indigo',
  title,
  badgeText,
  subtitle,
}) {
  const tone = ACCENTS[accentColor] ?? ACCENTS.indigo
  return (
    <div className="mb-4 flex items-start gap-3 border-b border-slate-100 pb-3.5">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className={`flex shrink-0 items-center justify-center rounded-xl p-2 ${tone.icon}`}>
          {Icon ? <Icon className="h-4 w-4" strokeWidth={2.2} /> : null}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-black tracking-tight text-ink">{title}</h3>
            {badgeText && (
              <span className={`rounded-md border px-2 py-0.5 text-[9.5px] font-black ${tone.badge}`}>
                {badgeText}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-1 text-justify text-right text-[10.5px] leading-5 text-ink-faint">
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default UnifiedSectionHeader
