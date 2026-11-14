import React, { useEffect, useMemo, useState } from 'react'
import MathText from '../components/MathText.jsx'

/**
 * نقطهٔ ورودِ مخصوصِ رندرِ چاپ/PDF.
 *
 * این صفحه در هیچ مسیری از اپ کاربر نیست؛ فقط از بیرون (موتور PDF سمت بک‌اند
 * با Chromium) باز می‌شود تا همان کامپوننت‌هایی را رندر کند که پیش‌نمایش
 * ExamBuilder استفاده می‌کند — به‌ویژه MathText، که خطِ لولهٔ ترمیم LaTeX را
 * دارد. رندرِ مستقل از این کامپوننت‌ها دقیقاً همان چیزی است که باعث می‌شد
 * PDF با پیش‌نمایش فرق کند.
 *
 * داده از window.__EXAM__ خوانده می‌شود؛ موتور PDF آن را پیش از بارگذاری صفحه
 * تزریق می‌کند. هیچ درخواست شبکه‌ای انجام نمی‌شود.
 */

const OPTION_LETTERS = ['الف', 'ب', 'ج', 'د']

const DIFFICULTY_LABELS = {
  easy: 'آسان',
  medium: 'متوسط',
  hard: 'سخت',
  challenging: 'کنکوری',
  konkuri: 'کنکوری',
  آسان: 'آسان',
  متوسط: 'متوسط',
  سخت: 'سخت',
  کنکوری: 'کنکوری',
}

const faDigits = (value) =>
  String(value ?? '').replace(/[0-9]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)])

/**
 * ریاضیِ نمایشیِ چندخطی را به بلوکِ مستقل ارتقا می‌دهد.
 *
 * remark-math فقط وقتی `$$ … $$` را ریاضیِ بلوکی می‌شناسد که در خطِ جدا باشد.
 * اگر وسطِ یک جمله بیاید، آن را ریاضیِ درون‌خطی می‌خواند؛ آن‌گاه aligned/array
 * که ارتفاعشان از جعبهٔ خط بیرون می‌زند روی سطرِ بالا و پایین می‌افتند و دستگاه
 * معادله ناخوانا می‌شود. برای چاپ، بلوکِ ریاضی را با خطِ خالی جدا می‌کنیم.
 * این فقط در نقطهٔ ورودِ چاپ اعمال می‌شود، نه در پیش‌نمایش اپ.
 */
const promoteDisplayMath = (value) =>
  String(value ?? '').replace(/\$\$([\s\S]*?)\$\$/g, (match, inner) =>
    /\\begin\s*\{/.test(inner) ? `\n\n${match}\n\n` : match,
  )

const difficultyLabel = (value) =>
  value ? DIFFICULTY_LABELS[value] || String(value) : ''

/* ── بلوک‌های اتمی برای صفحه‌بند ────────────────────────────────────────────
   data-block : صفحه‌بند این عنصر را یک واحد در نظر می‌گیرد
   data-newpage: پیش از این بلوک صفحهٔ تازه شروع شود
   ─────────────────────────────────────────────────────────────────────── */

function MetaTable({ meta }) {
  const rows = [
    ['پایه', meta.grade_label],
    ['رشته', meta.major],
    ['درس', meta.subject_label],
    ['مبحث', meta.topic],
    ['تعداد سؤال‌ها', `${faDigits(meta.question_count)} سؤال چهارگزینه‌ای`],
    ['زمان آزمون', `${faDigits(meta.duration_minutes)} دقیقه`],
    ['سطح سختی', meta.difficulty],
    ['تاریخ برگزاری', meta.date_label],
  ]
  return (
    <table className="print-meta" data-block>
      <tbody>
        <tr>
          <td className="print-meta-k">نام و نام خانوادگی</td>
          <td className="print-meta-v" colSpan={3} />
        </tr>
        {[0, 2, 4, 6].map((i) => (
          <tr key={i}>
            <td className="print-meta-k">{rows[i][0]}</td>
            <td className="print-meta-v">{rows[i][1] || '—'}</td>
            <td className="print-meta-k">{rows[i + 1][0]}</td>
            <td className="print-meta-v">{rows[i + 1][1] || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Instructions() {
  const items = [
    'هر سؤال فقط یک گزینهٔ صحیح دارد؛ بیش از یک گزینه علامت نزنید.',
    'پاسخ‌ها را فقط با علامت ضربدر (×) در گزینهٔ پاسخنامه علامت بزنید.',
    'همراه داشتن جزوه، کتاب و هرگونه ابزار هوشمند ممنوع است.',
    'حتماً پاسخنامه را مطابق با شمارهٔ سؤال پر کنید.',
  ]
  return (
    <div className="print-instructions" data-block>
      <div className="print-instructions-h">دستورالعمل آزمون:</div>
      <ul>
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  )
}

function QuestionBlock({ q, index }) {
  const text = q.text || q.question_text || q.title || ''
  const options = Array.isArray(q.options) ? q.options.slice(0, 4) : []
  const difficulty = difficultyLabel(q.difficulty)

  return (
    <div className="print-question" data-block>
      <div className="print-q-head">
        <span className="print-q-num">سؤال {faDigits(q.order ?? index)}</span>
        {q.subject ? (
          <>
            <span className="print-dot">·</span>
            <span>{q.subject}</span>
          </>
        ) : null}
        {difficulty ? (
          <>
            <span className="print-dot">·</span>
            <span>سطح: {difficulty}</span>
          </>
        ) : null}
      </div>

      {/* همان کامپوننت پیش‌نمایش — نه یک رندرر مستقل */}
      <div className="print-q-body">
        <MathText content={promoteDisplayMath(text)} className="print-math" />
      </div>

      {q.diagram_svg ? (
        <figure className="print-diagram" data-block>
          <div
            className="print-diagram-inner"
            dangerouslySetInnerHTML={{ __html: String(q.diagram_svg) }}
          />
        </figure>
      ) : null}

      {options.length ? (
        <ol className="print-options">
          {options.map((opt, oi) => (
            <li key={oi} className="print-option">
              <span className="print-option-letter">({OPTION_LETTERS[oi]})</span>
              <span className="print-option-value">
                <MathText content={opt || ''} className="print-math" />
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

function AnswerGrid({ questions }) {
  const CHUNK = 20
  const chunks = useMemo(() => {
    const out = []
    for (let i = 0; i < questions.length; i += CHUNK) {
      out.push(questions.slice(i, i + CHUNK))
    }
    return out
  }, [questions])

  return (
    <>
      {chunks.map((chunk, ci) => (
        <table className="print-grid" key={ci} data-block>
          <thead>
            <tr>
              <th>شمارهٔ سؤال</th>
              {OPTION_LETTERS.map((l) => (
                <th key={l}>{l}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chunk.map((q, qi) => (
              <tr key={qi}>
                <td className="print-grid-n">{faDigits(q.order ?? ci * CHUNK + qi + 1)}</td>
                <td />
                <td />
                <td />
                <td />
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </>
  )
}

function KeyBlock({ q, index }) {
  const ca = Number(q.correct_answer) || 1
  const letter = OPTION_LETTERS[ca - 1] || '—'
  const raw = String(q.text || q.question_text || '')
  const preview = raw.length > 180 ? `${raw.slice(0, 177)}…` : raw
  const explanation =
    String(q.explanation || '').trim() ||
    'استدلال تشریحی برای این سؤال در سامانه ثبت نشده است.'

  return (
    <div className="print-key-item" data-block>
      <div className="print-key-head">کلید {faDigits(q.order ?? index)}</div>
      {preview ? (
        <div className="print-key-q">
          <MathText content={promoteDisplayMath(preview)} className="print-math" />
        </div>
      ) : null}
      <div className="print-key-answer">
        پاسخ صحیح: گزینهٔ {faDigits(ca)} — {letter}
      </div>
      <div className="print-key-expl">
        <MathText content={promoteDisplayMath(explanation)} className="print-math" />
      </div>
    </div>
  )
}

export default function PrintExam() {
  const [doc, setDoc] = useState(null)

  useEffect(() => {
    const data = window.__EXAM__
    if (data) setDoc(data)
    else setDoc({ questions: [] })
  }, [])

  if (!doc) return null

  const { meta = {}, questions = [] } = doc

  return (
    <div id="flow">
      <header className="print-masthead" data-block>
        <div className="print-school">{meta.school_name || 'مدرسهٔ نمونه'}</div>
        <div className="print-school-sub">«فهم‌یار» — سامانهٔ تشخیصی فهم مفهومی</div>
      </header>

      <h1 className="print-title" data-block>
        {meta.title || 'آزمون کنکوری — فهم‌یار'}
      </h1>

      <MetaTable meta={meta} />
      <Instructions />

      <div className="print-section" data-block>
        بخش ۱ — دفترچهٔ سؤالات
      </div>

      {questions.map((q, i) => (
        <QuestionBlock key={i} q={q} index={i + 1} />
      ))}

      <div className="print-section" data-block data-newpage="1">
        پاسخنامهٔ دانش‌آموز
      </div>
      <AnswerGrid questions={questions} />

      <div className="print-secret" data-block data-newpage="1">
        مختص دبیر محترم — کلید آزمون (هرگز در اختیار دانش‌آموز قرار نگیرد)
      </div>

      <div className="print-section" data-block>
        بخش ۲ — کلید و پاسخ تشریحی
      </div>

      {questions.map((q, i) => (
        <KeyBlock key={i} q={q} index={i + 1} />
      ))}
    </div>
  )
}
