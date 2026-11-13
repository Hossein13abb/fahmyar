import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

const FA_TO_EN_DIGITS = {
  '۰': '0',
  '۱': '1',
  '۲': '2',
  '۳': '3',
  '۴': '4',
  '۵': '5',
  '۶': '6',
  '۷': '7',
  '۸': '8',
  '۹': '9',
}

function toAsciiDigitsInMath(str) {
  return String(str).replace(/[۰-۹]/g, (d) => FA_TO_EN_DIGITS[d] ?? d)
}

/**
 * پیش‌پردازش ایمن روی قطعاتِ خارج از `$ ... $` و `$$ ... $$`
 * تا اگر هوش مصنوعی علامت `$` را فراموش کرده بود، عبارات ریاضی به شکل شکسته یا معکوس (مانند `1-^`) نمایش داده نشوند.
 */
function autoWrapUnwrappedMathSegment(seg) {
  if (!seg) return seg
  let s = seg

  // ۰) احیای بک‌اسلشِ بلعیده‌شده در begin{bmatrix} / end{bmatrix}
  s = s.replace(
    /(?<![\\a-zA-Z])(begin|end)\s*\{([bpvBV]?matrix|array|cases|aligned)\}/g,
    '\\$1{$2}',
  )

  // ۱) تبدیل ماتریس‌های متنی [ a , b | c , d ] به ماتریس استاندارد LaTeX
  s = s.replace(
    /\[\s*([^\[\]|]+(?:\s*\|\s*[^\[\]|]+)+)\s*\]/g,
    (_, inner) => {
      const rows = inner
        .split('|')
        .map((r) =>
          r
            .split(/,|،/)
            .map((c) => c.trim())
            .join(' & '),
        )
        .join(' \\\\ ')
      return `$$\\begin{bmatrix} ${rows} \\end{bmatrix}$$`
    },
  )

  // ۲) ماتریس‌های بدون $$ ... $$
  s = s.replace(
    /\\begin\{([bpvBV]?matrix)\}([\s\S]*?)\\end\{\1\}/g,
    (match) => `$$${match}$$`,
  )

  // ۳) توابع مثلثاتی معکوس بدون $ مانند \cos^{-1}(4/9) یا cos^-1(4/9)
  s = s.replace(
    /\\?(sin|cos|tan|cot|sec|csc)\s*\^\s*\{?\s*(-?[0-9۰-۹]+)\s*\}?\s*\(\s*([^()]+?)\s*\)/g,
    (_, fn, exp, arg) => {
      const cleanExp = toAsciiDigitsInMath(exp)
      const cleanArg = toAsciiDigitsInMath(arg).replace(
        /^([0-9]+)\s*\/\s*([0-9]+)$/,
        '\\frac{$1}{$2}',
      )
      return `$\\${fn}^{${cleanExp}}\\left(${cleanArg}\\right)$`
    },
  )

  // ۴) دستورات LaTeX رها در متن (مانند \frac{a}{b}, \sqrt{x}, \vec{n}_1)
  s = s.replace(
    /\\(?:d|t)?frac\s*\{[^{}]*\}\s*\{[^{}]*\}/g,
    (m) => `$${m}$`,
  )
  s = s.replace(
    /\\sqrt\s*(?:\[[^\[\]]*\])?\s*\{[^{}]*\}/g,
    (m) => `$${m}$`,
  )
  s = s.replace(
    /\\(?:vec|overrightarrow)\s*\{[^{}]*\}(?:_\s*\{?[0-9۰-۹a-zA-Z]+\}?)?/g,
    (m) => `$${m}$`,
  )

  // ۵) توان‌ها و معکوس‌ها خارج از $ مانند T^-1 یا x^2 یا T^{-1}
  s = s.replace(
    /(?<![\\$a-zA-Z])([a-zA-Z])\s*\^\s*(-?[0-9۰-۹]+|\{[^}]+\})(?!\$)/g,
    (_, base, exp) => {
      const cleanExp = exp.startsWith('{') ? exp.slice(1, -1) : exp
      return `$${base}^{${cleanExp}}$`
    },
  )

  // ۶) اندیس‌ها خارج از $ مانند n_1 یا a_2
  s = s.replace(
    /(?<![\\$a-zA-Z])([a-zA-Z])\s*_\s*([0-9۰-۹]+|\{[^}]+\})(?!\$)/g,
    (_, base, sub) => {
      const cleanSub = sub.startsWith('{') ? sub.slice(1, -1) : sub
      return `$${base}_{${cleanSub}}$`
    },
  )

  return s
}

export function normalizeMathDelimiters(rawContent) {
  if (!rawContent) return ''
  let text = String(rawContent)

  // احیای کاراکترهای کنترلی احتمالی (\b -> \b و \f -> \f)
  text = text.replace(/\x08/g, '\\b').replace(/\x0c/g, '\\f')

  // جدا کردن بخش‌های دارای $...$ یا $$...$$ از متن معمولی تا دوبار $$ اضافه نشود
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/g)
  const normalizedParts = parts.map((part) => {
    if (part.startsWith('$$') || part.startsWith('$')) {
      // درون بلوک ریاضی: اطمینان از وجود آکولاد دور توان‌های منفی مثل ^-1 یا ^-۱
      return part.replace(/\^\s*(-[0-9۰-۹]+)/g, '^{$1}')
    }
    return autoWrapUnwrappedMathSegment(part)
  })

  return normalizedParts.join('')
}

export default function MathText({ content, className = '' }) {
  if (content === null || content === undefined || content === '') return null

  const processed = normalizeMathDelimiters(content)

  return (
    <div className={`math-rendered font-vazirmatn dir-rtl inline-block w-full ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false }]]}
      >
        {processed}
      </ReactMarkdown>
    </div>
  )
}
