// بررسیِ زندهٔ کلماتِ ممنوعه در پاسخِ سؤالِ فاینمن.
//
// منطق عمداً «مانع» نیست: اگر کاربر کلمهٔ ممنوعه را بنویسد، جلوی ارسال گرفته
// نمی‌شود — فقط با رنگِ قرمز نشان داده می‌شود تا هم چالش جذاب‌تر شود و هم
// اگر تقلب کرد، مدل بتواند مچش را بگیرد. «مانع» فقط آزمون را نابود می‌کرد.

const CHAR_MAP = {
  'ي': 'ی',
  'ك': 'ک',
  'أ': 'ا',
  'إ': 'ا',
  'آ': 'ا',
  'ة': 'ه',
  'ؤ': 'و',
}

export function normalizeFa(text) {
  return String(text ?? '')
    .replace(/[ي ك أ إ آ ة ؤ]/g, (ch) => CHAR_MAP[ch] ?? ch)
    .replace(/[\u064B-\u0652\u0670\u0640]/g, '')
    .replace(/\u200c/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** آیا کلمهٔ ممنوعه در متن آمده؟ با مرزِ کلمه تا «حد» داخلِ «حدس» شمرده نشود. */
export function containsWord(text, word) {
  const w = normalizeFa(word)
  if (!w) return false
  const t = normalizeFa(text)
  const escaped = w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}([^\\p{L}\\p{N}]|$)`, 'u').test(t)
}

export function findForbidden(text, forbidden = []) {
  return forbidden.filter((w) => containsWord(text, w))
}

/**
 * متن را به قطعه‌هایی می‌شکند که کلماتِ ممنوعه در آن‌ها علامت‌گذاری شده باشند.
 * خروجی برای رندرِ امن در React (بدون dangerouslySetInnerHTML):
 *   [{ text, forbidden: boolean }, ...]
 */
export function segmentForbidden(text, forbidden = []) {
  const source = String(text ?? '')
  if (!source || !forbidden.length) return [{ text: source, forbidden: false }]

  const words = forbidden
    .map((w) => normalizeFa(w))
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
  if (!words.length) return [{ text: source, forbidden: false }]

  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`(${escaped.join('|')})`, 'giu')

  const parts = []
  let last = 0
  let match
  while ((match = pattern.exec(source)) !== null) {
    if (match.index > last) {
      parts.push({ text: source.slice(last, match.index), forbidden: false })
    }
    parts.push({ text: match[0], forbidden: true })
    last = match.index + match[0].length
    if (match.index === pattern.lastIndex) pattern.lastIndex += 1
  }
  if (last < source.length) parts.push({ text: source.slice(last), forbidden: false })
  return parts.length ? parts : [{ text: source, forbidden: false }]
}

export function countWords(text) {
  const t = normalizeFa(text)
  return t ? t.split(' ').filter(Boolean).length : 0
}
