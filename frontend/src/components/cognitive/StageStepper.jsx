import { toFarsiNumber } from '../../utils/faNumbers'
import { STAGE_ICONS } from './icons'

/**
 * استپرِ پنج‌مرحله‌ایِ آزمون شناختی.
 *
 * هر مرحله یک *نقشِ شناختی* دارد، نه فقط یک شماره: «عیب‌یابی» معنایی
 * متفاوت از «سؤال ۴» دارد و کاربر باید بداند کجاست.
 */
export default function StageStepper({ stages = [], current = 0, answered = {}, onJump }) {
  return (
    <div className="rounded-3xl border border-brand-100 bg-white/80 p-3 shadow-soft sm:p-4">
      <ol className="flex items-stretch justify-between gap-1 sm:gap-2">
        {stages.map((stage, index) => {
          const isCurrent = index === current
          const isDone = Boolean(answered[stage.index])
          // «قبلی» فقط وقتی تیک می‌خورد که پاسخ داده شده باشد؛ صرفِ عبور از
          // یک مرحله بدونِ نوشتنِ پاسخ، «انجام‌شده» نیست.
          const showCheck = isDone && !isCurrent
          const Icon = STAGE_ICONS[stage.type]
          const reachable = Boolean(onJump)
          return (
            <li key={stage.type} className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => reachable && onJump(index)}
                disabled={!reachable}
                aria-current={isCurrent ? 'step' : undefined}
                aria-label={`مرحلهٔ ${toFarsiNumber(stage.index)}: ${stage.title}${isDone ? ' — پاسخ داده شد' : ''}`}
                className={[
                  'group flex w-full flex-col items-center gap-1.5 rounded-2xl px-1 py-2 transition sm:px-2',
                  isCurrent ? 'bg-brand-50 ring-2 ring-brand-300' : 'hover:bg-slate-50',
                  reachable ? 'cursor-pointer' : 'cursor-default',
                ].join(' ')}
              >
                <span
                  className={[
                    'flex h-9 w-9 items-center justify-center rounded-full transition sm:h-10 sm:w-10',
                    isCurrent
                      ? 'bg-brand-600 text-white shadow-soft'
                      : showCheck
                        ? 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200'
                        : 'bg-slate-100 text-slate-400',
                  ].join(' ')}
                >
                  {showCheck ? (
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                      <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : Icon ? (
                    <Icon className="h-[18px] w-[18px] sm:h-5 sm:w-5" strokeWidth={2} aria-hidden="true" />
                  ) : (
                    <span className="text-xs font-extrabold">{toFarsiNumber(stage.index)}</span>
                  )}
                </span>
                <span
                  className={[
                    'truncate text-[10px] font-bold sm:text-xs',
                    isCurrent ? 'text-brand-800' : isDone ? 'text-emerald-700' : 'text-slate-400',
                  ].join(' ')}
                >
                  {stage.label}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
