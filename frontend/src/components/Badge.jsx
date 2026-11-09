// نشان وضعیت‌های کیفی فهم‌یار — هرگز عددی نیستند، فقط برچسب فارسی + رنگ پاستلی
const STATUS = {
  CONFIRMED: {
    label: 'تأییدشده',
    cls: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
    dot: 'bg-emerald-500',
  },
  LIKELY_UNDERSTOOD: {
    label: 'احتمالاً آموخته‌شده',
    cls: 'bg-teal-50 text-teal-800 ring-1 ring-teal-200',
    dot: 'bg-teal-500',
  },
  UNCLEAR: {
    label: 'نامشخص',
    cls: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
    dot: 'bg-amber-400',
  },
  NEEDS_REVIEW: {
    label: 'بدفهمی شناسایی‌شده',
    cls: 'bg-orange-50 text-orange-800 ring-1 ring-orange-200',
    dot: 'bg-orange-400',
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'فاقد شواهد کافی',
    cls: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
    dot: 'bg-slate-400',
  },
  // برچسب‌های کمکی
  PENDING_REVIEW: {
    label: 'نیازمند بررسی معلم',
    cls: 'bg-amber-100 text-amber-900 ring-1 ring-amber-300',
    dot: 'bg-amber-500',
  },
  active: {
    label: 'در حال انجام',
    cls: 'bg-teal-50 text-teal-800 ring-1 ring-teal-200',
    dot: 'bg-teal-500',
  },
  completed: {
    label: 'تکمیل‌شده',
    cls: 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200',
    dot: 'bg-emerald-500',
  },
  paused: {
    label: 'مکث‌شده',
    cls: 'bg-indigo-50 text-indigo-800 ring-1 ring-indigo-200',
    dot: 'bg-indigo-400',
  },
  insufficient_evidence: {
    label: 'شواهد کافی به دست نیامد',
    cls: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
    dot: 'bg-slate-400',
  },
}

export default function Badge({ status, className = '' }) {
  const s = STATUS[status] || {
    label: status || 'نامشخص',
    cls: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
    dot: 'bg-slate-400',
  }
  return (
    <span className={`chip ${s.cls} ${className}`}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

export const statusFadeLabel = (status) => (STATUS[status]?.label ?? status)
