import { useState } from 'react'
import {
  School,
  GraduationCap,
  ArrowLeft,
  Sparkles,
  ShieldCheck,
  Compass,
  Brain,
  Cpu,
  CheckCircle2,
  Building2,
  BookOpenCheck,
  Wand2,
  FileText,
  GitBranch,
  Bot,
  ListChecks,
  Network,
  ChevronDown,
  ArrowDown,
} from 'lucide-react'
import LoginModal from '../components/LoginModal'

// ── تصویر ذهنیِ «فهمیدن» — لامپ با شبکهٔ عصبی (SVG درون‌خطی) ──
function HeroArt() {
  return (
    <svg viewBox="0 0 420 360" className="mx-auto w-full max-w-sm sm:max-w-md" role="img" aria-label="تصویر ذهنیِ فهمیدن">
      <defs>
        <radialGradient id="glow" cx="50%" cy="38%" r="60%">
          <stop offset="0%" stopColor="#fde9c8" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#fde9c8" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="bulb" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff7e0" />
          <stop offset="100%" stopColor="#f6d493" />
        </linearGradient>
      </defs>
      <circle cx="210" cy="150" r="150" fill="url(#glow)" />
      <g className="origin-[210px_150px] animate-breathe">
        <path
          d="M210 62c-46 0-78 30-78 72 0 24 11 39 21 52 7 9 10 15 10 24h94c0-9 3-15 10-24 10-13 21-28 21-52 0-42-32-72-78-72z"
          fill="url(#bulb)" stroke="#1f6a55" strokeWidth="5" strokeLinejoin="round"
        />
        <path d="M188 238h44M192 254h36M199 270h22" stroke="#1f6a55" strokeWidth="6" strokeLinecap="round" />
        {[[210, 118], [178, 142], [242, 142], [196, 168], [226, 168], [210, 190]].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="4.6" fill="#1f6a55" opacity="0.85" />
        ))}
        <path d="M210 118 L178 142 M210 118 L242 142 M178 142 L196 168 M242 142 L226 168 M178 142 L226 168 M242 142 L196 168 M196 168 L210 190 M226 168 L210 190"
              stroke="#1f6a55" strokeWidth="2.4" opacity="0.55" />
      </g>
      {[[118, 96], [302, 108], [330, 214]].map(([x, y], i) => (
        <path key={i} d={`M${x} ${y - 9} L${x + 2.4} ${y - 2.4} L${x + 9} ${y} L${x + 2.4} ${y + 2.4} L${x} ${y + 9} L${x - 2.4} ${y + 2.4} L${x - 9} ${y} L${x - 2.4} ${y - 2.4} Z`}
              fill="#7ed4b5" opacity="0.9" />
      ))}
    </svg>
  )
}

// ── سه ستون مزایا ──
const PILLARS = [
  {
    key: 'schools',
    Icon: Building2,
    tint: 'bg-indigo-50 text-indigo-700 ring-indigo-100',
    title: 'برای مدارس',
    headline: 'آزمون‌ساز پیشرفتهٔ کنکوری و گزارش‌های تحلیلی کلاس',
    bullets: [
      { Icon: ListChecks, text: 'ساخت دفترچهٔ ترکیبی از چند درس (انتخاب چندگانهٔ درس‌ها) با بانک سؤال‌های معتبر و هوش مصنوعی' },
      { Icon: Wand2, text: 'پیش‌نمایش، ویرایش و چیدمان سؤال‌ها قبل از چاپ — خروجی PDF استاندارد با پاسخنامهٔ کلیدی' },
      { Icon: FileText, text: 'گزارش‌های تحلیلی کیفیِ کلاس: چه کسی «نیازمند بازبینی» است و کجا مداخله لازم است' },
    ],
  },
  {
    key: 'students',
    Icon: GraduationCap,
    tint: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
    title: 'برای دانش‌آموزان',
    headline: 'سنجش عمیق مفهومی بدون استرس و نمره',
    bullets: [
      { Icon: ShieldCheck, text: 'هیچ نمره، رتبه یا مقایسه‌ای در کار نیست — فقط شواهد کیفی از فهمیدنِ تو ثبت می‌شود' },
      { Icon: Brain, text: 'ریشه‌یابی بدفهمی‌ها؛ حتی وقتی ریشهٔ خطا در درسِ دیگری است (مثلاً فیزیک با ریشهٔ ریاضی)' },
      { Icon: BookOpenCheck, text: 'کارنامهٔ کیفی با «مسیرِ اثر» و طرح جبرانیِ گام‌به‌گام برای هر ضعف شناسایی‌شده' },
    ],
  },
  {
    key: 'tech',
    Icon: Cpu,
    tint: 'bg-amber-50 text-amber-800 ring-amber-100',
    title: 'تکنولوژی',
    headline: 'هوش مصنوعی برای تولید سؤال استاندارد و تحلیل کیفی',
    bullets: [
      { Icon: Bot, text: 'تولید سؤالات چهارگزینه‌ای سطح کنکور با دام‌های هدفمندِ بدفهمی‌ها — قابل ویرایش توسط کادر مدرسه' },
      { Icon: Network, text: 'مدل تشخیص شناختی ECD: تحلیل گزاره‌به‌گزارهٔ فهم، نه تشخیص ظاهری و سطحی' },
      { Icon: GitBranch, text: 'گراف وابستگی مفاهیم و گزارش PDF راست‌چین — آمادهٔ چاپ و آرشیو مدرسه' },
    ],
  },
]

const scrollToId = (id) => {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export default function Home() {
  const [portal, setPortal] = useState(null) // null | 'staff' | 'student'

  return (
    <div className="relative overflow-hidden">
      {/* ── پس‌زمینهٔ دکوراتیو ── */}
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -right-24 top-10 h-80 w-80 rounded-full bg-brand-200/40 blur-3xl" />
        <div className="absolute -left-20 top-64 h-80 w-80 rounded-full bg-amber-200/40 blur-3xl" />
        <div className="absolute right-1/4 top-[46rem] h-72 w-72 rounded-full bg-emerald-100/50 blur-3xl" />
        <svg className="absolute left-1/2 top-40 h-96 w-96 -translate-x-1/2 opacity-[0.05]" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="96" stroke="currentColor" strokeWidth="2" strokeDasharray="4 6" className="text-brand-900" />
          <circle cx="100" cy="100" r="64" stroke="currentColor" strokeWidth="2" strokeDasharray="3 5" className="text-brand-900" />
        </svg>
      </div>

      {/* ══════════ بخش ۱ — Hero ══════════ */}
      <section className="mx-auto grid max-w-6xl items-center gap-8 py-6 sm:py-10 lg:grid-cols-2 lg:gap-12">
        <div className="text-center lg:text-right">
          <span className="chip bg-white text-brand-800 shadow-soft ring-1 ring-brand-100">
            <Sparkles className="h-3.5 w-3.5 text-amber-500" /> سامانهٔ فهم‌سنجی تشخیصی · فهم عمیق، نه حفظیات
          </span>
          <h1 className="mt-5 text-3xl font-black leading-[1.4] text-brand-950 sm:text-[44px] sm:leading-[1.3]">
            فهم‌یار؛{' '}
            <span className="bg-gradient-to-l from-brand-600 via-brand-700 to-brand-900 bg-clip-text text-transparent">
              پلتفرم نوین ارزیابی عمیق آموزشی
            </span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-[15px] leading-8 text-slate-600 lg:mx-0">
            فهم‌یار به‌جای تصحیح مکانیکی و نمره دادن، مثل یک معلمِ صبور کنار دانش‌آموز می‌نشیند:
            فهمیدن را با شواهدِ کیفی می‌سنجد، ریشهٔ بدفهمی‌ها را — حتی اگر در درسِ دیگری پنهان باشد — پیدا می‌کند
            و برای کادر مدرسه، آزمون‌های کنکوریِ دقیق و گزارش‌های تحلیلی می‌سازد.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
            <button
              onClick={() => scrollToId('gateway')}
              className="inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-6 py-3.5 text-[14px] font-black text-white shadow-lift transition hover:bg-brand-800"
            >
              ورود / شروع رایگان
              <ArrowDown className="h-5 w-5" />
            </button>
            <button
              onClick={() => scrollToId('features')}
              className="inline-flex items-center gap-2 rounded-2xl border border-brand-200 bg-white px-6 py-3.5 text-[14px] font-black text-brand-800 shadow-soft transition hover:border-brand-300 hover:bg-brand-50"
            >
              مزایای فهم‌یار
              <ChevronDown className="h-5 w-5" />
            </button>
          </div>
          <ul className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] font-bold text-slate-500 lg:justify-start">
            <li className="inline-flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-emerald-600" /> بدون نمره و مقایسه</li>
            <li className="inline-flex items-center gap-1.5"><Compass className="h-4 w-4 text-brand-600" /> نقشهٔ روشن از فهم</li>
            <li className="inline-flex items-center gap-1.5"><Brain className="h-4 w-4 text-amber-600" /> ریشه‌یابی بدفهمی‌ها</li>
          </ul>
        </div>
        <div className="relative">
          <HeroArt />
          {/* دو نشان شناور */}
          <div className="absolute right-2 top-6 rounded-2xl border border-emerald-100 bg-white/90 px-3.5 py-2 text-[11px] font-black text-emerald-800 shadow-lift backdrop-blur sm:right-6">
            <span className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4" /> شواهد کیفی، نه نمره</span>
          </div>
          <div className="absolute bottom-8 left-2 rounded-2xl border border-amber-100 bg-white/90 px-3.5 py-2 text-[11px] font-black text-amber-800 shadow-lift backdrop-blur sm:left-6">
            <span className="flex items-center gap-1.5"><GitBranch className="h-4 w-4" /> ریشهٔ بین‌درسیِ خطا</span>
          </div>
        </div>
      </section>

      {/* ══════════ بخش ۲ — Features / Benefits ══════════ */}
      <section id="features" className="scroll-mt-24 py-8 sm:py-12" aria-labelledby="features-title">
        <div className="text-center">
          <span className="chip bg-emerald-50 text-emerald-800 ring-1 ring-emerald-100">چرا فهم‌یار؟</span>
          <h2 id="features-title" className="mt-3 text-2xl font-black text-brand-950 sm:text-3xl">
            یک سامانه، سه دنیای متفاوت
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-[13px] leading-7 text-slate-500">
            از ساختن آزمون تا فهمیدنِ دانش‌آموز — همه‌چیز حول یک هدف: فهم عمیق.
          </p>
        </div>

        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {PILLARS.map(({ key, Icon, tint, title, headline, bullets }) => (
            <article
              key={key}
              className="group flex flex-col rounded-3xl border border-slate-200/80 bg-white p-6 shadow-soft transition-all duration-300 hover:-translate-y-1 hover:border-brand-200 hover:shadow-lift"
            >
              <span className={`inline-flex w-fit rounded-2xl p-3 ring-1 ${tint}`}>
                <Icon className="h-7 w-7" strokeWidth={1.7} />
              </span>
              <p className="mt-4 text-[11px] font-black uppercase tracking-wide text-slate-400">{title}</p>
              <h3 className="mt-1 text-[16px] font-black leading-7 text-brand-950">{headline}</h3>
              <ul className="mt-4 space-y-2.5">
                {bullets.map(({ Icon: BIcon, text }, i) => (
                  <li key={i} className="flex items-start gap-2 text-[12px] leading-6 text-slate-600">
                    <BIcon className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" strokeWidth={1.9} />
                    <span>{text}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      {/* ── نوار شعار ── */}
      <div className="mx-auto max-w-6xl">
        <p className="rounded-2xl border border-brand-100 bg-gradient-to-l from-brand-50 via-white to-emerald-50 px-6 py-3 text-center text-[12px] font-black text-brand-900 shadow-soft">
          هیچ نمره‌ای نیست &nbsp;·&nbsp; هیچ مقایسه‌ای نیست &nbsp;·&nbsp; فقط فهمیدن
        </p>
      </div>

      {/* ══════════ بخش ۳ — Call to Action: درگاه‌های ورود ══════════ */}
      <section id="gateway" className="scroll-mt-24 py-10 sm:py-14" aria-labelledby="gateway-title">
        <div className="text-center">
          <span className="chip bg-white text-brand-800 shadow-soft ring-1 ring-brand-100">
            <School className="h-3.5 w-3.5 text-brand-600" /> ورود به فهم‌یار
          </span>
          <h2 id="gateway-title" className="mt-3 text-2xl font-black text-brand-950 sm:text-3xl">از کدام درگاه وارد می‌شوی؟</h2>
          <p className="mx-auto mt-2 max-w-md text-[13px] leading-7 text-slate-500">
            هر درگاه حساب و دسترسی خودش را دارد — ورود از درگاه اشتباه ممکن نیست.
          </p>
        </div>

        <div className="mx-auto mt-8 grid max-w-4xl gap-5 md:grid-cols-2">
          {/* کارت کادر مدرسه */}
          <button
            onClick={() => setPortal('staff')}
            className="group relative overflow-hidden rounded-2xl border border-brand-800/60 bg-gradient-to-bl from-brand-800 via-brand-900 to-brand-950 p-6 text-right text-brand-50 shadow-lift transition-transform duration-300 hover:-translate-y-1 sm:p-7"
          >
            <div aria-hidden className="pointer-events-none absolute -left-10 -top-10 h-40 w-40 rounded-full bg-amber-400/15 blur-3xl transition group-hover:bg-amber-400/25" />
            <div className="relative">
              <span className="inline-flex rounded-2xl bg-white/10 p-3.5 ring-1 ring-white/15 backdrop-blur">
                <School className="h-9 w-9 text-amber-200" strokeWidth={1.6} />
              </span>
              <h3 className="mt-4 text-xl font-black text-white sm:text-2xl">ورود کادر مدرسه</h3>
              <p className="mt-1 text-[13px] font-bold text-amber-200/90">دبیر · مدیر · کادر مدرسه</p>
              <ul className="mt-4 space-y-2 text-[12px] leading-6 text-brand-100/90">
                <li className="flex items-center gap-2"><BookOpenCheck className="h-4 w-4 shrink-0 text-brand-300" /> آزمون‌ساز کنکوری با انتخاب چندگانهٔ درس‌ها</li>
                <li className="flex items-center gap-2"><ListChecks className="h-4 w-4 shrink-0 text-brand-300" /> پیش‌نمایش و ویرایش سؤالات AI + PDF و پاسخنامه</li>
                <li className="flex items-center gap-2"><FileText className="h-4 w-4 shrink-0 text-brand-300" /> گزارش‌های تحلیلی کلاس با علامت‌گذاری نیازمند بازبینی</li>
              </ul>
              <span className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-amber-300 px-5 py-3 text-[13px] font-black text-brand-950 shadow transition group-hover:bg-amber-200">
                ورود به پنل کادر مدرسه
                <ArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
              </span>
            </div>
          </button>

          {/* کارت دانش‌آموز */}
          <button
            onClick={() => setPortal('student')}
            className="group relative overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-6 text-right text-brand-950 shadow-lift transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_24px_56px_rgba(13,39,31,0.22)] sm:p-7"
          >
            <div aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-brand-100/60 blur-3xl transition group-hover:bg-brand-100" />
            <div className="relative">
              <span className="inline-flex rounded-2xl bg-brand-50 p-3.5 ring-1 ring-brand-100">
                <GraduationCap className="h-9 w-9 text-brand-700" strokeWidth={1.6} />
              </span>
              <h3 className="mt-4 text-xl font-black text-brand-950 sm:text-2xl">ورود دانش‌آموز</h3>
              <p className="mt-1 text-[13px] font-bold text-brand-700">فهم‌سنجی بدون نمره و استرس</p>
              <ul className="mt-4 space-y-2 text-[12px] leading-6 text-slate-600">
                <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 shrink-0 text-brand-600" /> فهم‌سنجی ۹ سؤالیِ انطباقی — هیچ نمره‌ای در کار نیست</li>
                <li className="flex items-center gap-2"><Brain className="h-4 w-4 shrink-0 text-brand-600" /> ریشه‌یابی بدفهمی‌ها، حتی بین‌درسی</li>
                <li className="flex items-center gap-2"><BookOpenCheck className="h-4 w-4 shrink-0 text-brand-600" /> کارنامهٔ کیفی با مسیرِ اثر و پیشنهاد جبران</li>
              </ul>
              <span className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-brand-700 px-5 py-3 text-[13px] font-black text-white shadow-lift transition group-hover:bg-brand-800">
                ورود به فهم‌سنجی من
                <ArrowLeft className="h-5 w-5 transition-transform group-hover:-translate-x-1" />
              </span>
            </div>
          </button>
        </div>
      </section>

      {/* ── مدال ورود — تنها درگاه ورود فهم‌یار ── */}
      {portal && <LoginModal portal={portal} onClose={() => setPortal(null)} />}
    </div>
  )
}
