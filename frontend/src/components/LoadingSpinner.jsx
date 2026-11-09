import { Loader2 } from 'lucide-react'

export default function LoadingSpinner({ label = 'در حال بارگذاری…', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-10 ${className}`} role="status" aria-live="polite">
      <Loader2 className="h-8 w-8 animate-spin text-brand-600" strokeWidth={2.2} />
      <p className="text-sm font-medium text-brand-800">{label}</p>
    </div>
  )
}
