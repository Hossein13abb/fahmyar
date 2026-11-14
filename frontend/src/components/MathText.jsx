import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

export default function MathText({ content, className = '' }) {
  if (content === null || content === undefined || content === '') return null

  let text = String(content)

  // احیای کاراکترهای کنترلی احتمالی (\b و \f)
  text = text.replace(/\x08/g, '\\b').replace(/\x0c/g, '\\f')

  // Clean up duplicate or escaped dollars like $\$ or \$ or $$$ or $$
  text = text
    .replace(/\$\\\$/g, '$')
    .replace(/\\\$/g, '$')
    .replace(/\$\$\$/g, '$')

  // `$$ … $$` تنها وقتی به ریاضیِ درون‌خطی فروکاسته می‌شود که محیطِ بلوکی
  // نداشته باشد. محیط‌هایی مانند aligned/array/cases/matrix ارتفاعی بیش از
  // ارتفاعِ خط دارند؛ اگر درون‌خطی رندر شوند روی سطرِ بالا و پایین می‌افتند و
  // دستگاه معادله خوانا نیست. این تفکیک باید حفظ شود تا پیش‌نمایش و PDF
  // یکسان دیده شوند.
  text = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, inner) =>
    /\\begin\s*\{/.test(inner) ? match : `$${inner}$`,
  )

  // Auto-add backslashes if AI generated unescaped commands like sqrt{...}, vec{...}, theta, cos^{-1}
  text = text.replace(
    /(?<!\\)\b(sqrt|vec|frac|theta|alpha|beta|pi|cos|sin|tan|deg|circ)\b/g,
    '\\$1',
  )
  text = text.replace(
    /(?<!\\)\b(begin|end)\s*\{([bpvBV]?matrix|array|cases|aligned)\}/g,
    '\\$1{$2}',
  )

  // تضمین وجود آکولاد دور توان‌های منفی مانند ^-1 یا ^-۱
  text = text.replace(/\^\s*(-[0-9۰-۹]+)/g, '^{$1}')

  // اگر بخش‌هایی از متن خارج از $ ... $ دارای دستورات ریاضی باشند، آن‌ها را درون $ ... $ قرار بده
  const parts = text.split(/(\$[^$\n]+\$)/g)
  text = parts
    .map((part) => {
      if (part.startsWith('$') && part.endsWith('$')) {
        const inner = part.slice(1, -1).trim()
        return inner ? `$${inner}$` : ''
      }
      let s = part
      s = s.replace(
        /\\begin\{([bpvBV]?matrix)\}([\s\S]*?)\\end\{\1\}/g,
        (m) => `$${m}$`,
      )
      s = s.replace(
        /\\(?:cos|sin|tan)\s*\^\s*\{-?[0-9۰-۹]+\}\s*(?:\\left)?\([^()]+?\)/g,
        (m) => `$${m}$`,
      )
      s = s.replace(/\\frac\s*\{[^{}]*\}\s*\{[^{}]*\}/g, (m) => `$${m}$`)
      s = s.replace(/\\sqrt\s*(?:\[[^\[\]]*\])?\s*\{[^{}]*\}/g, (m) => `$${m}$`)
      s = s.replace(
        /\\vec\s*\{[^{}]*\}(?:_\s*\{?[0-9۰-۹a-zA-Z]+\}?)?/g,
        (m) => `$${m}$`,
      )
      s = s.replace(
        /(?<![\\$a-zA-Z])([a-zA-Z])\s*\^\s*(\{[^}]+\}|-?[0-9۰-۹]+)(?!\$)/g,
        (_, b, e) => `$${b}^{${e.replace(/^[{}]|[{}]$/g, '')}}$`,
      )
      s = s.replace(
        /(?<![\\$a-zA-Z])([a-zA-Z])\s*_\s*(\{[^}]+\}|[0-9۰-۹]+)(?!\$)/g,
        (_, b, sub) => `$${b}_{${sub.replace(/^[{}]|[{}]$/g, '')}}$`,
      )
      s = s.replace(/\\(?:theta|alpha|beta|pi|circ|deg)\b/g, (m) => `$${m}$`)
      return s
    })
    .join('')

  return (
    <div className={`math-text-container font-vazirmatn inline-block ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false }]]}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
