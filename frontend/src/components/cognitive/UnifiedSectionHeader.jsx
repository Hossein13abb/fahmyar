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
  emerald: {
    icon: 'bg-emerald-500/10 text-emerald-600 ring-emerald-500/20',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  indigo: {
    icon: 'bg-indigo-500/10 text-indigo-600 ring-indigo-500/20',
    badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  },
  rose: {
    icon: 'bg-rose-500/10 text-rose-600 ring-rose-500/20',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
  },
  amber: {
    icon: 'bg-amber-500/10 text-amber-600 ring-amber-500/20',
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
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
    <div className="mb-5 flex items-start gap-3 border-b border-slate-100/80 pb-4">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className={`flex shrink-0 items-center justify-center rounded-2xl p-2.5 ring-4 ${tone.icon}`}>
          {Icon ? <Icon className="h-5 w-5" strokeWidth={2.2} /> : null}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-black tracking-tight text-slate-900">{title}</h3>
            {badgeText && (
              <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-black ${tone.badge}`}>
                {badgeText}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-1 text-justify text-right text-[11px] leading-6 text-slate-500">
              {subtitle}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default UnifiedSectionHeader
