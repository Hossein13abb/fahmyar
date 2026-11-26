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
    // توپر + هالهٔ رنگی زیرِ آیکون تا روی بومِ روشن «بدرخشد»
    icon: 'bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-[0_8px_20px_-4px_rgba(16,185,129,0.55)] ring-emerald-500/20',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    rail: 'from-emerald-500 via-teal-400 to-emerald-300',
  },
  indigo: {
    icon: 'bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-[0_8px_20px_-4px_rgba(99,102,241,0.55)] ring-indigo-500/20',
    badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    rail: 'from-indigo-500 via-violet-400 to-indigo-300',
  },
  rose: {
    icon: 'bg-gradient-to-br from-rose-500 to-red-600 text-white shadow-[0_8px_20px_-4px_rgba(244,63,94,0.5)] ring-rose-500/20',
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    rail: 'from-rose-500 via-red-400 to-rose-300',
  },
  amber: {
    icon: 'bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-[0_8px_20px_-4px_rgba(245,158,11,0.5)] ring-amber-500/20',
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    rail: 'from-amber-500 via-orange-400 to-amber-300',
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
