import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'

/**
 * CustomDropdown — جایگزین تگ بومی <select>
 * دکمهٔ اصلی و منوی بازشونده هر دو کاملاً گرد (rounded-2xl / rounded-xl) هستند
 * و در هیچ حالتی گوشهٔ تیزی دیده نمی‌شود.
 *
 * options: [{ value, label, disabled? }]
 */
export default function CustomDropdown({
  id,
  value,
  onChange,
  options = [],
  placeholder = 'انتخاب کنید…',
  disabled = false,
  className = '',
  buttonClassName = '',
  ariaLabel,
}) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const ref = useRef(null)
  const listId = useId()
  const selected = options.find((o) => String(o.value) === String(value))

  // بستن با کلیک خارج و Escape
  useEffect(() => {
    if (!open) return
    const onDocDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // هنگام باز شدن، آیتم فعال = آیتم انتخاب‌شده
  useEffect(() => {
    if (open) {
      const idx = options.findIndex((o) => String(o.value) === String(value))
      setActiveIndex(idx >= 0 ? idx : 0)
    }
  }, [open, options, value])

  const choose = (opt) => {
    if (!opt || opt.disabled) return
    onChange?.(opt.value)
    setOpen(false)
  }

  const onButtonKeyDown = (e) => {
    if (disabled) return
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setOpen((v) => !v)
    }
  }

  const onMenuKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(options.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      choose(options[activeIndex])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActiveIndex(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      setActiveIndex(options.length - 1)
    }
  }

  return (
    <div ref={ref} className={`relative ${className}`}>
      {/* ── دکمهٔ اصلی ── */}
      <button
        type="button"
        id={id}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onButtonKeyDown}
        className={`flex w-full items-center justify-between gap-2 rounded-2xl border border-slate-200/80 bg-white px-4 py-3 text-right text-[15px] leading-7 text-brand-900 shadow-sm transition hover:border-brand-200 focus:border-brand-400 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60 ${buttonClassName}`}
      >
        <span className={`truncate ${selected ? 'font-bold' : 'text-slate-400'}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={`h-5 w-5 shrink-0 text-slate-400 transition-transform duration-200 ${open ? 'rotate-180 text-brand-600' : ''}`}
        />
      </button>

      {/* ── منوی بازشونده ── */}
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          className="absolute z-50 mt-2 max-h-64 w-full origin-top animate-fade-up overflow-auto rounded-2xl border border-slate-100 bg-white p-1.5 shadow-lift ring-1 ring-black/5"
        >
          {options.length === 0 && (
            <li className="rounded-xl px-3 py-2.5 text-[12px] text-slate-400">موردی برای نمایش نیست.</li>
          )}
          {options.map((opt, i) => {
            const isSelected = String(opt.value) === String(value)
            const isActive = i === activeIndex
            return (
              <li key={`${opt.value}-${i}`} role="option" aria-selected={isSelected} aria-disabled={opt.disabled || undefined}>
                <button
                  type="button"
                  disabled={opt.disabled}
                  onClick={() => choose(opt)}
                  onMouseEnter={() => setActiveIndex(i)}
                  className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-right text-[13px] leading-6 transition-colors disabled:opacity-40 ${
                    isActive ? 'bg-brand-50 text-brand-900' : 'text-slate-700'
                  }`}
                >
                  <span className="truncate">{opt.label}</span>
                  {isSelected && <Check className="h-4 w-4 shrink-0 text-brand-600" strokeWidth={2.5} />}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
