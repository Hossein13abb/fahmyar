/**
 * شِلِ مودالِ معلم — نسخهٔ نسلِ جدید (فاز ۱۴)
 *
 * مسئولیت: موقعیت، پردهٔ شیشه‌ای، انیمیشنِ ورود، قفلِ اسکرول، Esc، و
 * **حالتِ بارگذاریِ زنده**. محتوا را از بیرون می‌گیرد تا هم مودالِ سؤال و
 * هم مودالِ تناقض از یک تجربهٔ بصری استفاده کنند.
 *
 * چرا Portal؟ هر والدِ `transform`دار (مثل کارتِ `hover`) مرجعِ `fixed`
 * می‌شود و مودال به کارت می‌چسبد، نه به پنجره. `createPortal` این را حل می‌کند.
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { GraduationCap, Sparkles, X } from 'lucide-react'

/** متن‌های چرخشیِ حالتِ لودینگ — هر ۲.۲ ثانیه عوض می‌شوند. */
const LOADING_LINES = [
  'معلم فهم‌یار در حال بررسی زنجیرهٔ استدلال توست...',
  'دارد ردِ پای فکرت را پیدا می‌کند...',
  'دارد یک مثال روزمره برایت آماده می‌کند...',
  'نزدیک است — دارد تمثیلِ درست را انتخاب می‌کند...',
]

function LoadingState() {
  const [step, setStep] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % LOADING_LINES.length), 2200)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <div className="flex items-center gap-3 rounded-2xl bg-brand-50/70 px-4 py-3 ring-1 ring-brand-100">
        <span className="relative flex h-9 w-9 shrink-0 items-center justify-center">
          <span className="absolute inset-0 animate-ping rounded-full bg-brand-400/30" />
          <Sparkles className="relative h-5 w-5 animate-pulse text-brand-600" />
        </span>
        <p key={step} className="text-[12.5px] font-bold leading-6 text-brand-900 animate-[fadeIn_400ms_ease-out]">
          {LOADING_LINES[step]}
        </p>
      </div>

      {/* اسکلتونِ سه بخش — هم‌شکل با محتوای نهایی، تا پرشِ چیدمان نداشته باشیم */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="animate-pulse rounded-2xl border border-slate-100 bg-slate-50/80 p-4"
          style={{ animationDelay: `${i * 160}ms` }}
        >
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-slate-200/80" />
            <div className="flex-1 space-y-2">
              <div className="h-2.5 w-16 rounded-full bg-slate-200/80" />
              <div className="h-3 w-40 rounded-full bg-slate-200/60" />
            </div>
          </div>
          <div className="mt-3 space-y-2">
            <div className="h-2.5 w-full rounded-full bg-slate-200/60" />
            <div className="h-2.5 w-[92%] rounded-full bg-slate-200/50" />
            <div className="h-2.5 w-[70%] rounded-full bg-slate-200/40" />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function TutorModalShell({
  open,
  titleId = 'tutor-title',
  header,
  children,
  footer,
  onClose,
  loading = false,
}) {
  const [shown, setShown] = useState(false)
  const closeRef = useRef(null)

  useEffect(() => {
    if (!open) {
      setShown(false)
      return undefined
    }
    const raf = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(raf)
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  const modal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-busy={loading}
    >
      <button
        type="button"
        aria-label="بستن"
        onClick={onClose}
        className={`absolute inset-0 bg-black/70 backdrop-blur-2xl transition-opacity duration-300 ${
          shown ? 'opacity-100' : 'opacity-0'
        }`}
      />

      <div
        className={`relative flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-[28px] bg-white shadow-[0_24px_80px_-12px_rgba(15,23,42,0.45)] ring-1 ring-white/40 transition-all duration-300 ease-out ${
          shown ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        }`}
      >
        <header className="relative shrink-0 overflow-hidden border-b border-slate-100 bg-gradient-to-l from-brand-50 via-white to-brand-50/30 px-4 py-4 sm:px-6 sm:py-5">
          <div className="pointer-events-none absolute -left-10 -top-12 h-36 w-36 rounded-full bg-brand-200/30 blur-3xl" />
          <div className="pointer-events-none absolute -right-6 bottom-0 h-24 w-24 rounded-full bg-amber-200/20 blur-2xl" />
          <div className="relative flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-lg shadow-brand-300/50">
                <GraduationCap className="h-5 w-5" strokeWidth={2.2} />
                {loading && (
                  <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 animate-ping rounded-full bg-amber-400" />
                )}
              </span>
              <div className="min-w-0">{header}</div>
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="بستنِ پنجرهٔ معلم"
              className="shrink-0 rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-400"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto overscroll-contain px-3.5 py-4 sm:px-6 sm:py-5">
          {loading ? <LoadingState /> : children}
        </div>

        {footer && !loading && (
          <footer className="shrink-0 border-t border-slate-100 bg-slate-50/70 px-3.5 py-3 sm:px-6">
            {footer}
          </footer>
        )}
      </div>
    </div>
  )

  return typeof document === 'undefined' ? modal : createPortal(modal, document.body)
}
