import { useMemo } from 'react'
import { ShieldAlert } from 'lucide-react'
import { countWords, findForbidden, segmentForbidden } from '../../utils/forbidden'
import { toFarsiNumber } from '../../utils/faNumbers'

/**
 * باکسِ کلماتِ ممنوعه + بررسیِ زنده.
 *
 * این بخش قلبِ سؤالِ ۵ است: هدف این نیست که کاربر را متوقف کنیم، بلکه این
 * است که ببینیم وقتی ابزارهای تخصصی را از او می‌گیریم، آیا هنوز می‌تواند
 * توضیح بدهد یا نه. پس تخلف «علامت‌گذاری» می‌شود، نه «مسدود».
 */
export default function ForbiddenWords({ words = [], answer = '' }) {
  const hits = useMemo(() => findForbidden(answer, words), [answer, words])
  const segments = useMemo(() => segmentForbidden(answer, words), [answer, words])
  const wordCount = countWords(answer)

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border-2 border-rose-200 bg-rose-50/70 p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-rose-700" strokeWidth={2.2} aria-hidden="true" />
          <h4 className="text-sm font-extrabold text-rose-900">کلماتِ ممنوعه</h4>
          <span className="rounded-full bg-rose-200/70 px-2 py-0.5 text-[10px] font-bold text-rose-900">
            استفاده نکن!
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {words.map((word) => {
            const used = hits.includes(word)
            return (
              <span
                key={word}
                className={[
                  'rounded-lg px-2.5 py-1 text-xs font-bold transition',
                  used
                    ? 'bg-rose-600 text-white line-through decoration-2'
                    : 'bg-white text-rose-800 ring-1 ring-rose-200',
                ].join(' ')}
              >
                {word}
              </span>
            )
          })}
        </div>
        <p className="mt-2.5 text-[11px] font-medium leading-5 text-rose-800/90">
          این کلمات ابزارِ بیان‌اند، نه خودِ فهم. اگر مجبور شوی بدونِ آن‌ها توضیح بدهی،
          معلوم می‌شود واقعاً فهمیده‌ای یا فقط اصطلاح حفظ کرده‌ای. نوشتنشان مانعِ ارسال
          نیست — ولی ما می‌بینیم.
        </p>
      </div>

      {wordCount > 0 && (
        <div
          className={[
            'flex flex-wrap items-center justify-between gap-2 rounded-xl px-3 py-2 text-[11px] font-bold',
            hits.length ? 'bg-rose-50 text-rose-800 ring-1 ring-rose-200' : 'bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200',
          ].join(' ')}
        >
          <span>
            {hits.length
              ? `⚠️ ${toFarsiNumber(hits.length)} کلمهٔ ممنوعه به کار بردی: ${hits.join('، ')}`
              : '✓ تا اینجا بدونِ کلماتِ ممنوعه توضیح داده‌ای'}
          </span>
          <span className="text-slate-500">{toFarsiNumber(wordCount)} کلمه</span>
        </div>
      )}

      {wordCount > 0 && hits.length > 0 && (
        <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
          <p className="mb-1 text-[10px] font-bold text-slate-500">پیش‌نمایشِ پاسخِ تو:</p>
          <p className="whitespace-pre-wrap text-xs leading-6 text-slate-700">
            {segments.map((part, index) =>
              part.forbidden ? (
                <mark key={index} className="rounded bg-rose-200 px-1 font-bold text-rose-900">
                  {part.text}
                </mark>
              ) : (
                <span key={index}>{part.text}</span>
              ),
            )}
          </p>
        </div>
      )}
    </div>
  )
}
