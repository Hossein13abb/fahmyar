import { useEffect, useMemo, useState } from 'react'
import {
  ClipboardEdit,
  Sigma,
  Atom,
  FlaskConical,
  Leaf,
  Shapes,
  Binary,
  Timer,
  Info,
  Smile,
  Meh,
  Flame,
  Rocket,
  Wand2,
  Loader2,
  FileDown,
  FileText,
  ChevronDown,
  Percent,
  Trash2,
  ArrowUp,
  ArrowDown,
  Check,
  CheckCircle2,
  RotateCcw,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import MathText from '../components/MathText'
import { toFarsiNumber } from '../utils/faNumbers'
import client, { friendlyError } from '../api/client'

const FIELDS = [
  { id: 'math', label: 'ریاضی', Icon: Sigma, grad: 'from-indigo-500 to-blue-600' },
  { id: 'tajrobi', label: 'تجربی', Icon: Leaf, grad: 'from-emerald-500 to-green-600' },
]

// لیست دروس — دقیقاً بر اساس ترکیب «رشته × پایه» (محل منبع حقیقتِ UI آزمون‌ساز)
const MATH_SUBJECTS_10 = [
  { id: 'math', label: 'ریاضی', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const MATH_SUBJECTS_11 = [
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'statistics', label: 'آمار و احتمال', Icon: Percent },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const MATH_SUBJECTS_12 = [ // دوازدهم و جامع
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'discrete', label: 'گسسته', Icon: Binary },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const EXPERIMENTAL_SUBJECTS = [ // تجربی — همهٔ پایه‌ها
  { id: 'biology', label: 'زیست‌شناسی', Icon: Leaf },
  { id: 'math', label: 'ریاضیات', Icon: Sigma },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
// «جامع» = اجتماعِ همهٔ دروس دهم، یازدهم و دوازدهمِ همان رشته — بدون تکراری
const COMPREHENSIVE_MATH = [
  { id: 'math', label: 'ریاضی', Icon: Sigma },
  { id: 'calculus', label: 'حسابان', Icon: Sigma },
  { id: 'geometry', label: 'هندسه', Icon: Shapes },
  { id: 'statistics', label: 'آمار و احتمال', Icon: Percent },
  { id: 'discrete', label: 'گسسته', Icon: Binary },
  { id: 'physics', label: 'فیزیک', Icon: Atom },
  { id: 'chemistry', label: 'شیمی', Icon: FlaskConical },
]
const dedupeById = (list) => list.filter((item, i) => list.findIndex((x) => x.id === item.id) === i)
const subjectsFor = (field, grade) => {
  const isComprehensive = grade === 'comprehensive' || grade === 'جامع'
  if (field === 'math' || field === 'ریاضی') {
    if (isComprehensive) {
      return dedupeById([...MATH_SUBJECTS_10, ...MATH_SUBJECTS_11, ...MATH_SUBJECTS_12])
    }
    if (grade === '10' || grade === 'دهم') return MATH_SUBJECTS_10
    if (grade === '11' || grade === 'یازدهم') return MATH_SUBJECTS_11
    return MATH_SUBJECTS_12
  }
  return dedupeById([...EXPERIMENTAL_SUBJECTS, ...EXPERIMENTAL_SUBJECTS, ...EXPERIMENTAL_SUBJECTS])
}

// درخت سرفصل‌های رسمی نظام جدید ایران (پایه -> درس -> فصل -> [مباحث])
const CURRICULUM_TREE = {
  "دوازدهم": {
    "حسابان ۲": {
      "فصل ۱: تابع": ["تبدیل نمودارها", "تابع درجه ۳", "یکنواختی", "بخش‌پذیری"],
      "فصل ۲: مثلثات": ["تناوب", "تابع تانژانت", "معادلات مثلثاتی"],
      "فصل ۳: حد": ["حدهای نامتناهی", "حد در بی‌نهایت"],
      "فصل ۴: مشتق": ["مفهوم مشتق", "مشتق‌پذیری", "آهنگ تغییر"],
      "فصل ۵: کاربرد مشتق": ["اکسترمم‌های تابع", "بهینه‌سازی"]
    },
    "هندسه ۳": {
      "فصل ۱: ماتریس": ["ماتریس و اعمال روی آن", "دترمینان", "دستگاه معادلات خطی"],
      "فصل ۲: مقاطع مخروطی": ["آشنایی با مقاطع", "دایره", "بیضی", "سهمی"],
      "فصل ۳: بردارها": ["معرفی فضای R3", "ضرب داخلی", "ضرب خارجی"]
    },
    "ریاضیات گسسته": {
      "فصل ۱: آشنایی با نظریهٔ اعداد": ["بخش‌پذیری و تقسیم", "هم‌نهشتی", "معادلات سیاله خطی"],
      "فصل ۲: گراف و مدل‌سازی": ["معرفی گراف", "مدل‌سازی با گراف", "گراف‌های اویلری و همیلتونی"],
      "فصل ۳: ترکیبیات (شمارش)": ["مبانی شمارش", "اصل شمول و عدم شمول", "اصل لانهٔ کبوتری"]
    },
    "فیزیک ۳": {
      "فصل ۱: حرکت بر خط راست": ["شناخت حرکت", "حرکت با سرعت ثابت", "حرکت با شتاب ثابت"],
      "فصل ۲: دینامیک": ["قوانین حرکت نیوتون", "معرفی نیروهای خاص", "تکانه و قانون دوم نیوتون"],
      "فصل ۳: نوسان و امواج": ["نوسان دوره‌ای و حرکت هماهنگ ساده", "موج و انواع آن", "بازتاب و شکست موج"],
      "فصل ۴: فیزیک اتمی و هسته‌ای": ["اثر فوتوالکتریک و طیف اتمی", "مدل اتمی بور", "فیزیک هسته‌ای و واپاشی"]
    },
    "شیمی ۳": {
      "فصل ۱: مولکول‌ها در خدمت تندرستی": ["پاک‌کننده‌ها و اسید و باز آرنیوس", "درجهٔ یونش و ثابت تعادل اسیدی", "پی‌اچ و واکنش خنثی‌شدن"],
      "فصل ۲: آسایش و رفاه در سایهٔ شیمی": ["الکتروشیمی و عدد اکسایش", "سلول‌های گالوانی و پتانسیل استاندارد", "الکترولیز، آبکاری و خوردگی"],
      "فصل ۳: شیمی جلوه‌ای از هنر، زیبایی و ماندگاری": ["انواع جامدها (کووالانسی، یونی، مولکولی، فلزی)", "قطبیت مولکولی و نیروهای بین‌مولکولی"],
      "فصل ۴: شیمی، راهی به سوی آینده‌ای روشن‌تر": ["تعادل شیمیایی و اصل لوشاتلیه", "کاتالیزگرها و سنتز آمونیاک"]
    },
    "زیست‌شناسی ۳": {
      "فصل ۱: مولکول‌های اطلاعاتی": ["نوکلئیک‌اسیدها و همانندسازی دنا", "پروتئین‌ها و ساختار آنزیم‌ها"],
      "فصل ۲: جریان اطلاعات در یاخته": ["رونویسی", "ترجمه", "تنظیم بیان ژن"],
      "فصل ۳: انتقال اطلاعات در نسل‌ها": ["مفاهیم پایهٔ وراثت", "الگوهای وراثتی", "بیماری‌های وراثتی"],
      "فصل ۴: تغییر در اطلاعات وراثتی": ["جهش‌های ژنی و کروموزومی", "تغییر در جمعیت‌ها و گونه‌زایی"],
      "فصل ۵: از ماده به انرژی": ["تنفس یاخته‌ای هوازی", "تخمیر و تنفس بی‌هوازی"],
      "فصل ۶: از انرژی به ماده": ["واکنش‌های نوری فتوسنتز", "چرخهٔ کالوین و فتوسنتز در شرایط دشوار"]
    },
    "ریاضی ۳": {
      "فصل ۱: تابع": ["توابع چندجمله‌ای", "ترکیب توابع", "وارون تابع"],
      "فصل ۲: مثلثات": ["تناوب و تابع تانژانت", "معادلات مثلثاتی"],
      "فصل ۳: حد بی‌نهایت و حد در بی‌نهایت": ["حدهای نامتناهی", "حد در بی‌نهایت و مجانب"],
      "فصل ۴: مشتق": ["مفهوم مشتق و خط مماس", "قواعد مشتق‌گیری"],
      "فصل ۵: کاربرد مشتق": ["نقاط بحرانی و اکسترمم‌ها", "بهینه‌سازی"],
      "فصل ۶: هندسه": ["مقاطع مخروطی", "دایره و بیضی"],
      "فصل ۷: احتمال": ["احتمال شرطی", "قانون احتمال کل"]
    }
  },
  "یازدهم": {
    "حسابان ۱": {
      "فصل ۱: جبر و معادله": ["دنباله‌های حسابی و هندسی", "معادلات درجهٔ دوم و گویا", "مجموع جملات دنباله"],
      "فصل ۲: تابع": ["دامنه و برد توابع", "توابع یک‌به‌یک و وارون", "اعمال جبری روی توابع"],
      "فصل ۳: مثلثات": ["واحد رادیان", "نسبت‌های مثلثاتی مجموع و تفاضل", "توابع مثلثاتی"],
      "فصل ۴: نمایی و لگاریتمی": ["تابع نمایی و ویژگی‌ها", "لگاریتم و قوانین آن", "معادلات نمایی و لگاریتمی"],
      "فصل ۵: حد و پیوستگی": ["مفهوم حد و قضایای حد", "رفع ابهام حدی", "پیوستگی تابع"]
    },
    "هندسه ۲": {
      "فصل ۱: دایره": ["زاویه‌ها در دایره", "طول مماس و قوت نقطه", "چهارضلعی محاطی و محیطی"],
      "فصل ۲: تبدیل‌های هندسی و کاربردها": ["انتقال، تقارن و دوران", "تجانس و تشابه"],
      "فصل ۳: روابط طولی در مثلث": ["قضایای سینوس‌ها و کسینوس‌ها", "میانه، نیمساز و ارتفاع در مثلث"]
    },
    "آمار و احتمال": {
      "فصل ۱: آشنایی با مبانی ریاضیات": ["گزاره‌ها و ترکیب گزاره‌ها", "استدلال ریاضی و سورها", "نظریهٔ مجموعه‌ها"],
      "فصل ۲: احتمال": ["فضای نمونه‌ای و پیشامد", "احتمال شرطی و پیشامدهای مستقل", "قانون احتمال کل و قضیهٔ بیز"],
      "فصل ۳: آمار توصیفی": ["شاخص‌های گرایش به مرکز", "شاخص‌های پراکندگی و نمودار جعبه‌ای"],
      "فصل ۴: آمار استنباطی": ["جامعه و نمونه", "فاصلهٔ اطمینان و برآورد"]
    },
    "فیزیک ۲": {
      "فصل ۱: الکتریسیتهٔ ساکن": ["بار الکتریکی و قانون کولن", "میدان الکتریکی", "پتانسیل الکتریکی و خازن"],
      "فصل ۲: جریان الکتریکی و مدارهای جریان مستقیم": ["جریان و مقاومت الکتریکی (قانون اهم)", "نیروی محرکه و توان در مدار", "ترکیب مقاومت‌ها"],
      "فصل ۳: مغناطیس و القای الکترومغناطیسی": ["مغناطیس و نیروی مغناطیسی", "شار مغناطیسی و قانون فارادی", "قانون لنز و جریان متناوب"]
    },
    "شیمی ۲": {
      "فصل ۱: قدر هدایای زمینی را بدانیم": ["الگوها و روندهای تناوبی", "آرایش الکترونی عناصر واسطه", "شیمی آلی و هیدروکربن‌ها"],
      "فصل ۲: در پی غذای سالم": ["ترموشیمی و آنتالپی واکنش", "قانون هس و آنتالپی پیوند", "سینتیک و سرعت واکنش"],
      "فصل ۳: پوشاک، نیازی پایان‌ناپذیر": ["پلیمرها و درشت‌مولکول‌ها", "الکل‌ها، اسیدهای آلی و استرها", "پلی‌استرها و پلی‌آمیدها"]
    },
    "زیست‌شناسی ۲": {
      "فصل ۱: تنظیم عصبی": ["یاخته‌های بافت عصبی و پتانسیل عمل", "دستگاه عصبی مرکزی و محیطی"],
      "فصل ۲: حواس": ["گیرنده‌های حسی", "بینایی، شنوایی و تعادل"],
      "فصل ۳: دستگاه حرکتی": ["استخوان‌ها و اسکلت", "ماهیچه‌ها و مکانیسم انقباض"],
      "فصل ۴: تنظیم شیمیایی": ["غدد درون‌ریز و هورمون‌ها", "بازخوردهای هورمونی"],
      "فصل ۵: ایمنی": ["خطوط دفاع غیراختصاصی", "ایمنی اختصاصی (لنفوسیت‌ها)"],
      "فصل ۶: تقسیم یاخته": ["چرخهٔ یاخته‌ای و میتوز", "میوز و تولید گامت"],
      "فصل ۷: تولیدمثل": ["دستگاه تولیدمثل در انسان", "رشد و نمو جنین"],
      "فصل ۸: تولیدمثل نهاندانگان": ["تولیدمثل غیرجنسی و جنسی در گیاهان", "تشکیل دانه و میوه"]
    },
    "ریاضی ۲": {
      "فصل ۱: هندسهٔ تحلیلی و جبر": ["معادلهٔ خط و فاصله", "معادلات درجهٔ دوم"],
      "فصل ۲: هندسه": ["قضیهٔ تالس و تشابه", "روابط طولی در مثلث"],
      "فصل ۳: تابع": ["توابع گویا و رادیکالی", "توابع یک‌به‌یک و وارون"],
      "فصل ۴: مثلثات": ["رادیان و دایرهٔ مثلثاتی", "نمودارهای مثلثاتی"],
      "فصل ۵: توابع نمایی و لگاریتمی": ["تابع نمایی و ویژگی‌ها", "لگاریتم و معادلات لگاریتمی"],
      "فصل ۶: حد و پیوستگی": ["مفهوم حد", "محاسبهٔ حد توابع", "پیوستگی"],
      "فصل ۷: احتمال": ["احتمال شرطی", "پیشامدهای مستقل"]
    }
  },
  "دهم": {
    "ریاضی ۱": {
      "فصل ۱: مجموعه، الگو و دنباله": ["مجموعه‌های متناهی و نامتناهی", "متمم و اعمال روی مجموعه‌ها", "الگو و دنبالهٔ حسابی و هندسی"],
      "فصل ۲: مثلثات": ["نسبت‌های مثلثاتی زاویه‌های حاده", "دایرهٔ مثلثاتی", "روابط بین نسبت‌های مثلثاتی"],
      "فصل ۳: توان‌های گویا و عبارت‌های جبری": ["ریشه و توان گویا", "اتحادها و تجزیه", "گویا کردن مخرج"],
      "فصل ۴: معادله‌ها و نامعادله‌ها": ["معادلهٔ درجهٔ دوم و روش‌های حل", "سهمی و تعیین علامت", "نامعادله‌ها و قدرمطلق"],
      "فصل ۵: تابع": ["مفهوم تابع و بازنمایی‌ها", "دامنه و برد تابع", "توابع خطی و درجهٔ دوم"],
      "فصل ۶: شمارش، بدون شمردن": ["اصول شمارش (جمع و ضرب)", "جایگشت", "ترکیب"],
      "فصل ۷: آمار و احتمال": ["گردآوری داده‌ها و نمودارها", "فضای نمونه‌ای و محاسبهٔ احتمال"]
    },
    "هندسه ۱": {
      "فصل ۱: ترسیم‌های هندسی و استدلال": ["مکان هندسی و ترسیم‌ها", "استدلال استنتاجی", "هم‌نهشتی مثلث‌ها"],
      "فصل ۲: قضیهٔ تالس، تشابه و کاربردها": ["نسبت و تناسب در هندسه", "قضیهٔ تالس و عکس آن", "تشابه مثلث‌ها"],
      "فصل ۳: چندضلعی‌ها": ["ویژگی‌های زاویه‌ای چندضلعی‌ها", "چهارضلعی‌های خاص", "مساحت چندضلعی‌ها"],
      "فصل ۴: تجسم فضایی": ["خط و صفحه در فضا", "حجم‌های هندسی (منشور، هرم، کره)"]
    },
    "فیزیک ۱": {
      "فصل ۱: فیزیک و اندازه‌گیری": ["مدل‌سازی در فیزیک", "کمیت‌های اصلی و فرعی و تبدیل یکا", "چگالی و دقت اندازه‌گیری"],
      "فصل ۲: ویژگی‌های فیزیکی مواد": ["حالت‌های ماده و نیروهای بین‌مولکولی", "فشار در شاره‌ها و لولهٔ یو شکل", "اصل پاسکال، ارشمیدس و برنولی"],
      "فصل ۳: کار، انرژی و توان": ["انرژی جنبشی و قضیهٔ کار و انرژی", "کار نیروی وزن و انرژی پتانسیل", "پایستگی انرژی مکانیکی و توان"],
      "فصل ۴: دما و گرما": ["دما و دماسنجی", "انبساط گرمایی", "گرما، ظرفیت گرمایی و تغییر حالت", "قانون اول ترمودینامیک"]
    },
    "شیمی ۱": {
      "فصل ۱: کیهان زادگاه الفبای هستی": ["ایزوتوپ و جرم اتمی میانگین", "جدول تناوبی و مول", "طیف نشری خطی و آرایش الکترونی", "پیوند یونی و کووالانسی"],
      "فصل ۲: ردپای گازها در زندگی": ["اجزای هوا و اکسایش", "ساختار لوئیس و استوکیومتری گازها", "اثر گلخانه‌ای و اوزون"],
      "فصل ۳: آب، آهنگ زندگی": ["غلظت محلول‌ها (مولاریته و درصد جرمی)", "انحلال‌پذیری و نیروهای بین‌مولکولی", "خواص غیرعادی آب"]
    },
    "زیست‌شناسی ۱": {
      "فصل ۱: دنیای زنده": ["ویژگی‌های جانداران و سطوح سازمان‌یابی", "مولکول‌های زیستی و یاخته"],
      "فصل ۲: گوارش و جذب مواد": ["ساختار و عملکرد لولهٔ گوارش", "جذب مواد و تنظیم گوارش"],
      "فصل ۳: تبادلات گازی": ["سازوکار دستگاه تنفس در انسان", "حمل گازها در خون"],
      "فصل ۴: گردش مواد در بدن": ["قلب و چرخهٔ ضربان قلب", "رگ‌ها، خون و دستگاه لنفی"],
      "فصل ۵: تنظیم اسمزی و دفع مواد زائد": ["ساختار کلیه و نفرون", "تشکیل ادرار و هم‌ایستایی"],
      "فصل ۶: از یاخته تا گیاه": ["ویژگی‌های یاختهٔ گیاهی", "بافت‌ها و اندام‌های گیاهی"],
      "فصل ۷: جذب و انتقال مواد در گیاهان": ["جذب آب و مواد معدنی در ریشه", "انتقال در آوندهای چوبی و آبکشی"]
    }
  }
}

// نگاشت (پایه، رشته، شناسهٔ درس) به کلیدهای کتاب درسی در CURRICULUM_TREE
const SUBJECT_BOOK_KEYS = {
  '10': {
    math: 'ریاضی ۱',
    geometry: 'هندسه ۱',
    physics: 'فیزیک ۱',
    chemistry: 'شیمی ۱',
    biology: 'زیست‌شناسی ۱',
  },
  '11': {
    calculus: 'حسابان ۱',
    math: 'ریاضی ۲',
    geometry: 'هندسه ۲',
    statistics: 'آمار و احتمال',
    physics: 'فیزیک ۲',
    chemistry: 'شیمی ۲',
    biology: 'زیست‌شناسی ۲',
  },
  '12': {
    calculus: 'حسابان ۲',
    math: 'ریاضی ۳',
    geometry: 'هندسه ۳',
    discrete: 'ریاضیات گسسته',
    physics: 'فیزیک ۳',
    chemistry: 'شیمی ۳',
    biology: 'زیست‌شناسی ۳',
  },
}
const GRADE_ID_TO_FA = { '10': 'دهم', '11': 'یازدهم', '12': 'دوازدهم', دهم: 'دهم', یازدهم: 'یازدهم', دوازدهم: 'دوازدهم' }

const getSubjectChaptersMap = (grade, field, subjectId) => {
  const isComprehensive = grade === 'comprehensive' || grade === 'جامع'
  if (!isComprehensive) {
    const gFa = GRADE_ID_TO_FA[grade] || 'دوازدهم'
    const gKey = gFa === 'دهم' ? '10' : gFa === 'یازدهم' ? '11' : '12'
    const bookKey = SUBJECT_BOOK_KEYS[gKey]?.[subjectId]
    return (bookKey && CURRICULUM_TREE[gFa]?.[bookKey]) || {}
  }
  // در حالت «جامع»، فصول هر سه پایه برای آن درس تجمیع می‌شوند
  const merged = {}
  for (const [gKey, gFa] of [['10', 'دهم'], ['11', 'یازدهم'], ['12', 'دوازدهم']]) {
    if (field === 'math' && subjectId === 'math' && gKey !== '10') continue
    const bookKey = SUBJECT_BOOK_KEYS[gKey]?.[subjectId]
    const chaptersObj = bookKey ? CURRICULUM_TREE[gFa]?.[bookKey] : null
    if (!chaptersObj) continue
    const multiGrade = ['geometry', 'physics', 'chemistry', 'biology', 'calculus'].includes(subjectId) || (field === 'tajrobi' && subjectId === 'math')
    for (const [chTitle, subs] of Object.entries(chaptersObj)) {
      const displayChapter = multiGrade ? `${bookKey} — ${chTitle}` : chTitle
      merged[displayChapter] = subs
    }
  }
  return merged
}

const SUBJECT_DIFFICULTY_OPTIONS = ['آسان', 'متوسط', 'سخت', 'کنکوری']

// تبدیل ارقام انگلیسی/فارسی ورودی به عدد صحیح و نمایش فارسی در فیلدهای عددی
const parseNumericInput = (raw, fallback = 1, min = 1, max = 20) => {
  const ascii = String(raw ?? '')
    .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
    .replace(/[^0-9]/g, '')
  if (!ascii) return fallback
  const n = Number.parseInt(ascii, 10)
  if (Number.isNaN(n)) return fallback
  return Math.max(min, Math.min(max, n))
}

const FIELD_LABELS = { math: 'ریاضی', tajrobi: 'تجربی' }
const FIELD_PRINT_LABELS = { math: 'ریاضی و فیزیک', tajrobi: 'علوم تجربی' }

const GRADES = [
  { id: '10', label: 'دهم' },
  { id: '11', label: 'یازدهم' },
  { id: '12', label: 'دوازدهم' },
  { id: 'comprehensive', label: 'جامع' },
]
const GRADE_LABELS = Object.fromEntries(GRADES.map((g) => [g.id, g.label]))

const QUESTION_TYPES = [
  { id: 'mixed', label: 'نامشخص / ترکیبی' },
  { id: 'conceptual', label: 'مفهومی' },
  { id: 'recall', label: 'حفظی' },
  { id: 'computational', label: 'محاسباتی' },
  { id: 'problem', label: 'مسئله' },
]
const QUESTION_TYPE_LABELS = Object.fromEntries(QUESTION_TYPES.map((t) => [t.id, t.label]))

const TIME_PRESETS = [45, 60, 75, 100, 120]
const DIFFICULTY_OPTIONS = [
  { id: 'easy', label: 'آسان', desc: 'سؤال‌های مستقیم و پایه‌ای', Icon: Smile },
  { id: 'medium', label: 'متوسط', desc: 'استاندارد کنکور', Icon: Meh },
  { id: 'hard', label: 'سخت', desc: 'عمیق و تحلیلی', Icon: Flame },
  { id: 'challenging', label: 'چالش‌برانگیز', desc: 'بالاتر از کنکور', Icon: Rocket },
]
const DIFFICULTY_LABELS = Object.fromEntries(DIFFICULTY_OPTIONS.map((d) => [d.id, d.label]))

const DRAFT_KEY = 'fahmyar_exam_drafts'

const fmtFa = (n) => toFarsiNumber(Number(n).toLocaleString('fa-IR'))
const loadDrafts = () => {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '[]')
  } catch {
    return []
  }
}
const loadGrade = () => {
  try {
    const raw = String(localStorage.getItem('fahmyar_grade') || '11')
    return GRADE_LABELS[raw] ? raw : '11'
  } catch {
    return '11'
  }
}
const loadField = () => {
  try {
    const raw = localStorage.getItem('fahmyar_field') || 'math'
    return raw === 'tajrobi' ? 'tajrobi' : 'math'
  } catch {
    return 'math'
  }
}

export default function ExamBuilder({ embedded = false }) {
  // ── فرم مرحلهٔ ۱ ──
  const [field, setField] = useState(loadField)                // math | tajrobi
  const [grade, setGradeState] = useState(loadGrade)           // 10 | 11 | 12 | comprehensive
  const [selectedSubjects, setSelectedSubjects] = useState(() => subjectsFor(loadField(), loadGrade()).map((x) => x.id))
  // پیکربندیِ هر درس: تعداد سؤال + سطح سوالات + ریز‌مباحث هدف (از درخت سرفصل‌ها)
  const [subjectConfigs, setSubjectConfigs] = useState(() => {
    const init = {}
    subjectsFor(loadField(), loadGrade()).forEach((o) => {
      init[o.id] = { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
    })
    return init
  })
  const [expandedChapters, setExpandedChapters] = useState({})
  const [aiPercentage, setAiPercentage] = useState(100) // درصد سؤالات تولیدی هوش مصنوعی؛ بقیه = بانک آزمون
  const [questionType, setQuestionType] = useState('mixed')
  const [customPrompt, setCustomPrompt] = useState('')
  const [difficulty, setDifficulty] = useState('medium')
  const [duration, setDuration] = useState(75)
  const [title, setTitle] = useState('')
  const [schoolName, setSchoolName] = useState(() => {
    try {
      return localStorage.getItem('fahmyar_school_name') || 'مدرسهٔ نمونه'
    } catch {
      return 'مدرسهٔ نمونه'
    }
  })

  // ── گام دوم: پیش‌نمایش و ویرایش ──
  const [step, setStep] = useState('form')                     // form | preview
  const [questions, setQuestions] = useState([])
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [progressPercent, setProgressPercent] = useState(0)
  const [pdfUrl, setPdfUrl] = useState(null)
  const [notice, setNotice] = useState('')
  const [drafts, setDrafts] = useState(loadDrafts)             // پیش‌نویس‌های قدیمی (فقط مشاهده/حذف)

  const syncConfigs = (ids) =>
    setSubjectConfigs((prev) => {
      const next = {}
      ids.forEach((id) => {
        next[id] = prev[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
      })
      return next
    })

  const setGrade = (g) => {
    setGradeState(g)
    const ids = subjectsFor(field, g).map((x) => x.id)
    setSelectedSubjects(ids)
    syncConfigs(ids)
    try {
      localStorage.setItem('fahmyar_grade', g)
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }
  const setFieldPersist = (f) => {
    setField(f)
    const ids = subjectsFor(f, grade).map((x) => x.id)
    setSelectedSubjects(ids)
    syncConfigs(ids)
    try {
      localStorage.setItem('fahmyar_field', f)
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }

  const availableSubjects = useMemo(() => subjectsFor(field, grade), [field, grade])
  const subjectOptions = availableSubjects
  const selectedOptions = availableSubjects.filter((s) => selectedSubjects.includes(s.id))
  const subjectsLabel = selectedOptions.map((s) => s.label).join('، ')
  const toggleSubject = (id) => {
    const next = selectedSubjects.includes(id) ? selectedSubjects.filter((x) => x !== id) : [...selectedSubjects, id]
    setSelectedSubjects(next)
    syncConfigs(next)
  }
  const updateSubjectCount = (id, raw) =>
    setSubjectConfigs((prev) => {
      const cur = prev[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
      const n = parseNumericInput(raw, cur.count || 2, 1, 20)
      return { ...prev, [id]: { ...cur, count: n } }
    })
  const updateSubjectDifficulty = (id, diff) =>
    setSubjectConfigs((prev) => {
      const cur = prev[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
      return { ...prev, [id]: { ...cur, difficulty: diff } }
    })
  const toggleChapterExpanded = (subjectId, chapterTitle) => {
    const key = `${subjectId}::${chapterTitle}`
    setExpandedChapters((prev) => ({ ...prev, [key]: !(prev[key] ?? true) }))
  }
  const toggleSubTopic = (id, subTopicLabel) =>
    setSubjectConfigs((prev) => {
      const cur = prev[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
      const list = cur.subTopics ?? cur.topics ?? []
      const nextSubs = list.includes(subTopicLabel)
        ? list.filter((t) => t !== subTopicLabel)
        : [...list, subTopicLabel]
      return { ...prev, [id]: { ...cur, subTopics: nextSubs, topics: nextSubs } }
    })
  const toggleWholeChapter = (id, chapterTitle, subtopicsList) =>
    setSubjectConfigs((prev) => {
      const cur = prev[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
      const list = cur.subTopics ?? cur.topics ?? []
      const chapterItems = subtopicsList.map((st) => `${chapterTitle} — ${st}`)
      const allSelected = chapterItems.every((item) => list.includes(item))
      const nextSubs = allSelected
        ? list.filter((item) => !chapterItems.includes(item))
        : [...list, ...chapterItems.filter((item) => !list.includes(item))]
      return { ...prev, [id]: { ...cur, subTopics: nextSubs, topics: nextSubs } }
    })

  // مجموع سؤالات و پیکربندیِ هر درس برای ارسال به بک‌اند
  const subjectConfigsPayload = selectedOptions.map((o) => {
    const cfg = subjectConfigs[o.id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
    const subs = cfg.subTopics ?? cfg.topics ?? []
    return {
      subject: o.id,
      count: Math.max(1, Math.min(20, Number(cfg.count) || 2)),
      difficulty: cfg.difficulty || 'متوسط',
      subTopics: subs,
      topics: subs,
    }
  })
  const allSelectedSubTopics = subjectConfigsPayload.flatMap((c) => c.subTopics)
  const totalCount = subjectConfigsPayload.reduce((sum, c) => sum + c.count, 0)

  // ── شمارندهٔ درصدیِ پیشرفت (منحنیِ مجانبی) ──
  //
  // منطق قبلی یک منحنیِ زمان‌محور بود که در ثانیهٔ ۴۰ به سقفِ ثابتِ ۹۵٪ می‌رسید و
  // می‌ایستاد. منطق جدید «مجانبی» است: در هر تیک، درصد به سقفِ ۹۰ نزدیک‌تر می‌شود
  // ولی هرگز از آن عبور نمی‌کند — یعنی حتی اگر تولید ۳ دقیقه طول بکشد، کاربر
  // پیشرفتِ واقعی می‌بیند و عدد یخ نمی‌زند.
  //
  // نکتهٔ مهم: `Math.round` روی کرانِ بالا نگذارید؛ بعد از یک بازه به خاطرِ
  // گرد کردن عدد بی‌حرکت می‌شود. گرد کردن را در لایهٔ نمایش انجام می‌دهیم.
  useEffect(() => {
    if (!generating) return undefined
    setProgressPercent(5)
    const timer = window.setInterval(() => {
      setProgressPercent((prev) => {
        const next = prev + (90 - prev) * 0.08 // هرچه به ۹۰ نزدیک‌تر، کندتر
        return next > 90 ? 90 : next
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [generating])

  // هر تغییری در لیست سؤال‌ها، PDF قبلی را باطل می‌کند
  useEffect(() => {
    setPdfUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [questions])

  const removeDraft = (id) => {
    const next = drafts.filter((d) => d.id !== id)
    setDrafts(next)
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(next))
    } catch {
      /* فضای ذخیره در دسترس نیست */
    }
  }

  const validate = () => {
    if (selectedSubjects.length === 0) return 'حداقل یک درس را انتخاب کنید.'
    if (totalCount > 60) return 'مجموع سؤالات نباید بیشتر از ۶۰ سؤال باشد.'
    if (totalCount < 1) return 'تعداد سؤالات هر درس حداقل ۱ سؤال است.'
    if (!duration || duration < 10) return 'زمان آزمون باید حداقل ۱۰ دقیقه باشد.'
    return ''
  }

  // ── مرحلهٔ ۱ → تولید پیش‌نمایش (JSON فقط؛ بدون PDF) ──
  const generatePreview = async () => {
    // اعتبارسنجی پیش از باز کردن مودال تا پیام خطا فوراً دیده شود
    if (selectedSubjects.length === 0 || allSelectedSubTopics.length === 0) {
      setNotice('⚠️ لطفاً حداقل یک درس و یک مبحث را انتخاب کنید.')
      return
    }
    const err = validate()
    if (err) {
      setNotice(`⚠️ ${err}`)
      return
    }

    const payload = {
      field,
      grade,
      subjects: selectedSubjects,
      subject_configs: subjectConfigsPayload,
      subTopics: allSelectedSubTopics,
      ai_ratio: aiPercentage,
      ai_percentage: aiPercentage,
      topic: null,
      question_type: questionType,
      difficulty,
      count: totalCount,
      custom_prompt: customPrompt.trim(),
    }
    console.log('Generating exam with payload:', payload)

    // مودال باید بدون تأخیر باز شود
    setNotice('')
    setProgressPercent(5)
    setGenerating(true)
    try {
      const { data } = await client.post(
        '/api/teacher/generate-exam-preview',
        payload,
        { timeout: 180000 },
      )
      const list = Array.isArray(data?.questions) ? data.questions : []
      if (list.length === 0) {
        setNotice('⚠️ هوش مصنوعی سؤالِ معتبری برنگرداند؛ دوباره تلاش کنید.')
        setProgressPercent(0)
        return
      }
      setProgressPercent(100)
      setQuestions(list)
      setStep('preview')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (error) {
      let message = friendlyError(error)
      try {
        if (typeof error?.response?.data?.detail === 'string') message = error.response.data.detail
      } catch {
        /* همان پیام عمومی نمایش داده می‌شود */
      }
      setNotice(`⚠️ ${message}`)
      setProgressPercent(0)
    } finally {
      setGenerating(false)
    }
  }

  // ── ویرایش لیست سؤال‌ها ──
  const removeQuestion = (id) => setQuestions((prev) => prev.filter((q) => q.id !== id))
  const updateQuestionDifficulty = (index, newDifficulty) =>
    setQuestions((prev) =>
      prev.map((item, i) => (i === index ? { ...item, difficulty: newDifficulty } : item)),
    )
  const moveQuestion = (index, delta) =>
    setQuestions((prev) => {
      const target = index + delta
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.splice(target, 0, item)
      return next
    })

  // ── مرحلهٔ ۲ → تأیید و دانلود PDF نهایی (تگ منبع در PDF چاپ نمی‌شود) ──
  const confirmAndDownload = async () => {
    if (questions.length === 0) return setNotice('⚠️ حداقل یک سؤال باید باقی بماند.')
    setNotice('')
    setDownloading(true)
    try {
      const { data } = await client.post(
        '/api/teacher/generate-exam-pdf',
        {
          title: title.trim(),
          school_name: schoolName.trim() || 'مدرسهٔ نمونه',
          grade,
          major: FIELD_PRINT_LABELS[field],
          subject_label: subjectsLabel,
          topic: '',
          duration_minutes: duration,
          difficulty,
          questions: questions.map((q, i) => ({
            id: i + 1,
            text: q.text,
            options: q.options,
            correct_answer: q.correct_answer,
            source_tag: q.source_tag || '',
            explanation: q.explanation || '',
            difficulty: q.difficulty || 'متوسط',
            subject: q.subject || '',
            diagram_svg: q.diagram_svg || null,
          })),
        },
        { responseType: 'blob', timeout: 180000 },
      )
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
      setPdfUrl(URL.createObjectURL(data))
      setNotice('✓ PDF نهایی ساخته شد؛ تگ منابع در آن چاپ نشده است.')
    } catch (error) {
      /* درخواست با responseType:'blob' است، پس بدنهٔ خطا هم Blob می‌آید.
         friendlyError برای Blob چیزی نمی‌فهمد و به پیام عمومی می‌افتد؛ پس
         ابتدا Blob را باز می‌کنیم. detail می‌تواند رشته باشد (اعتبارسنجی
         FastAPI) یا شیءی با message و reason (خطای موتور PDF) — هر دو
         خوانده می‌شوند تا علت واقعی به کاربر برسد، نه «خطایی رخ داد». */
      let message = friendlyError(error)
      try {
        const blob = error?.response?.data
        if (blob instanceof Blob) {
          const parsed = JSON.parse(await blob.text())
          const detail = parsed?.detail
          if (typeof detail === 'string') message = detail
          else if (typeof detail?.message === 'string') message = detail.message
        }
      } catch {
        /* بدنهٔ خطا JSON نبود؛ همان پیام عمومی می‌ماند */
      }
      setNotice(`⚠️ ${message}`)
    } finally {
      setDownloading(false)
    }
  }

  const difficultyLabel = DIFFICULTY_LABELS[difficulty] ?? 'متوسط'
  const questionTypeLabel = QUESTION_TYPE_LABELS[questionType] ?? 'نامشخص / ترکیبی'

  return (
    <div className="animate-fade-up space-y-6">
      {/* ── سربرگ صفحه ── */}
      {!embedded && (
        <section className="relative overflow-hidden rounded-2xl border border-brand-800/50 bg-gradient-to-bl from-brand-800 via-brand-900 to-brand-950 p-6 text-brand-50 shadow-lift sm:p-7">
          <div aria-hidden className="pointer-events-none absolute -left-16 -top-16 h-56 w-56 rounded-full bg-brand-400/20 blur-3xl" />
          <div aria-hidden className="pointer-events-none absolute -bottom-14 left-1/3 h-48 w-48 rounded-full bg-amber-400/10 blur-3xl" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <span className="rounded-2xl bg-white/10 p-3 ring-1 ring-white/15 backdrop-blur">
                <ClipboardEdit className="h-7 w-7 text-amber-200" />
              </span>
              <div>
                <h1 className="text-xl font-black text-white sm:text-2xl">آزمون‌ساز کنکوری</h1>
                <p className="mt-1 text-[12px] font-medium text-brand-100/85">
                  سؤال‌های چهارگزینه‌ایِ سطح کنکور بساز، پیش‌نمایش بگیر، ویرایش کن و PDF نهایی را چاپ کن.
                </p>
              </div>
            </div>
            <div className="rounded-2xl bg-white/10 px-4 py-2.5 text-center ring-1 ring-white/15 backdrop-blur">
              <p className="text-2xl font-black leading-none text-amber-200">{fmtFa(step === 'preview' ? questions.length : totalCount)}</p>
              <p className="mt-1 text-[10px] font-bold text-brand-100/80">سؤال چهارگزینه‌ای</p>
            </div>
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        {/* ════════════════════════ گام ۱ — فرم ════════════════════════ */}
        {step === 'form' && (
          <>
            <div className="space-y-6 lg:col-span-8">
              {/* ── اطلاعات آزمون ── */}
              <section className="card p-5 sm:p-6">
                <label htmlFor="exam-title" className="label">نام آزمون (اختیاری)</label>
                <input
                  id="exam-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="مثلاً: آزمون کنکوری مشتق — دوازدهم ریاضی"
                  className="input"
                />
                <label htmlFor="school-name" className="label mt-4">نام مدرسه/مؤسسه (روی سربرگ PDF)</label>
                <input
                  id="school-name"
                  value={schoolName}
                  onChange={(e) => {
                    setSchoolName(e.target.value)
                    try {
                      localStorage.setItem('fahmyar_school_name', e.target.value)
                    } catch {
                      /* فضای ذخیره در دسترس نیست */
                    }
                  }}
                  placeholder="مثلاً: دبیرستان نمونهٔ اندیشه"
                  className="input"
                />

                {/* رشته — فقط ریاضی و تجربی */}
                <span className="label mt-4 block">رشته</span>
                <div className="mt-1.5 grid grid-cols-2 gap-2.5" role="group" aria-label="رشته">
                  {FIELDS.map(({ id, label, Icon, grad }) => {
                    const active = field === id
                    return (
                      <button
                        key={id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setFieldPersist(id)}
                        className={`flex items-center gap-3 rounded-2xl border p-3.5 transition-all duration-200 ${
                          active
                            ? 'border-transparent bg-gradient-to-br text-white shadow-lift ring-2 ring-brand-300/60 ' + grad
                            : 'border-slate-200/80 bg-slate-50/50 text-slate-600 hover:border-brand-200 hover:bg-white'
                        }`}
                      >
                        <Icon className={`h-7 w-7 ${active ? 'text-white' : 'text-brand-700'}`} strokeWidth={1.8} />
                        <span className="text-[14px] font-black">{label}</span>
                        {active && <Check className="mr-auto h-5 w-5" />}
                      </button>
                    )
                  })}
                </div>

                {/* پایه — دهم تا دوازدهم و جامع */}
                <span className="label mt-4 block">پایه</span>
                <div className="mt-1.5 grid grid-cols-4 gap-2" role="group" aria-label="پایه">
                  {GRADES.map((g) => {
                    const active = grade === g.id
                    return (
                      <button
                        key={g.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setGrade(g.id)}
                        className={`rounded-2xl border py-2.5 text-[12px] font-black transition-all duration-200 ${
                          active
                            ? 'border-transparent bg-emerald-600 text-white shadow-soft'
                            : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-emerald-200 hover:text-emerald-700'
                        }`}
                      >
                        {g.label}
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── انتخاب درس (دینامیک بر اساس رشته) ── */}
              <section className="card p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                    <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۱</span>
                    انتخاب درس (چندگانه)
                  </h2>
                  <div className="flex items-center gap-2">
                    <span className="chip bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200">{toFarsiNumber(selectedSubjects.length)} درس انتخاب شد</span>
                    <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">رشتهٔ {FIELD_LABELS[field]}</span>
                  </div>
                </div>
                <p className="mt-2 text-[11px] font-medium leading-5 text-slate-500">
                  امکان انتخاب/لغو چند درس با کلیک وجود دارد؛ سؤالات به‌طور متوازن بین درس‌های انتخابی تقسیم می‌شوند.
                </p>
                <div className={`mt-4 grid gap-2.5 ${subjectOptions.length > 4 ? 'grid-cols-2 sm:grid-cols-5' : 'grid-cols-2 sm:grid-cols-4'}`}>
                  {subjectOptions.map(({ id, label, Icon }) => {
                    const on = selectedSubjects.includes(id)
                    return (
                      <button
                        key={id}
                        type="button"
                        aria-pressed={on}
                        onClick={() => toggleSubject(id)}
                        className={`relative flex flex-col items-center gap-2 rounded-2xl border p-3.5 transition-all duration-200 ${
                          on
                            ? 'border-transparent bg-gradient-to-br from-brand-600 to-emerald-700 text-white shadow-lift ring-2 ring-brand-300/60'
                            : 'border-slate-200/80 bg-slate-50/50 text-slate-600 hover:border-brand-200 hover:bg-white'
                        }`}
                      >
                        {on && (
                          <span className="absolute left-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-white text-emerald-700 shadow-sm">
                            <Check className="h-3.5 w-3.5" strokeWidth={3} />
                          </span>
                        )}
                        <Icon className={`h-6 w-6 ${on ? 'text-white' : 'text-brand-700'}`} strokeWidth={1.8} />
                        <span className="text-[12px] font-black leading-5">{label}</span>
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── تنظیماتِ هر درس: تعداد سؤال + فصل‌های هدف ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۲</span>
                  تنظیمات سؤالات هر درس
                </h2>
                <p className="mt-1.5 text-[11px] font-medium leading-6 text-slate-500">
                  برای هر درسی که انتخاب کرده‌اید، تعداد سؤال و فصل‌های هدف را مشخص کنید؛ فصل انتخاب‌نشده یعنی پوششِ همهٔ فصول.
                </p>

                <div className="mt-4 space-y-3">
                  {selectedOptions.length === 0 && (
                    <p className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 px-4 py-6 text-center text-[12px] font-bold text-slate-400">
                      ابتدا حداقل یک درس را در بخش ۱ انتخاب کنید.
                    </p>
                  )}
                  {selectedOptions.map(({ id, label, Icon }) => {
                    const cfg = subjectConfigs[id] ?? { count: 2, difficulty: 'متوسط', subTopics: [], topics: [] }
                    const selectedSubs = cfg.subTopics ?? cfg.topics ?? []
                    const chaptersMap = getSubjectChaptersMap(grade, field, id)
                    const chapterEntries = Object.entries(chaptersMap)
                    return (
                      <fieldset key={id} className="rounded-2xl border border-slate-200/80 bg-slate-50/50 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <legend className="sr-only">{label}</legend>
                          <p className="flex items-center gap-2 text-[14px] font-black text-brand-950">
                            <Icon className="h-5 w-5 text-brand-700" strokeWidth={1.8} />
                            {label}
                          </p>
                          <div className="flex flex-wrap items-center gap-3">
                            <div className="flex items-center gap-2">
                              <label htmlFor={`diff-${id}`} className="text-[11px] font-bold text-slate-600">سطح سوالات</label>
                              <select
                                id={`diff-${id}`}
                                value={cfg.difficulty || 'متوسط'}
                                onChange={(e) => updateSubjectDifficulty(id, e.target.value)}
                                className="input w-28 px-2.5 py-1.5 text-[12px] font-black text-brand-950"
                              >
                                {SUBJECT_DIFFICULTY_OPTIONS.map((dOpt) => (
                                  <option key={dOpt} value={dOpt}>{dOpt}</option>
                                ))}
                              </select>
                            </div>
                            <div className="flex items-center gap-2">
                              <label htmlFor={`count-${id}`} className="text-[11px] font-bold text-slate-600">تعداد سوال این درس</label>
                              <input
                                id={`count-${id}`}
                                type="text"
                                inputMode="numeric"
                                dir="ltr"
                                value={toFarsiNumber(cfg.count)}
                                onChange={(e) => updateSubjectCount(id, e.target.value)}
                                className="input w-20 px-3 py-1.5 font-vazirmatn text-right text-[13px] font-black tabular-nums"
                              />
                            </div>
                          </div>
                        </div>

                        {chapterEntries.length > 0 && (
                          <div className="mt-3">
                            <div className="flex items-center justify-between">
                              <p className="text-[11px] font-bold text-slate-600">فصل‌ها و ریز‌مباحث هدف (با باز کردن هر فصل، مباحث را انتخاب کنید)</p>
                              {selectedSubs.length > 0 && (
                                <span className="text-[10px] font-black text-emerald-700">{toFarsiNumber(selectedSubs.length)} مبحث انتخاب شد</span>
                              )}
                            </div>
                            <div className="mt-2 space-y-2 rounded-xl border border-slate-200 bg-white p-2.5">
                              {chapterEntries.map(([chapterTitle, subtopics]) => {
                                const expKey = `${id}::${chapterTitle}`
                                const isExpanded = expandedChapters[expKey] ?? true
                                const chapterKeys = subtopics.map((st) => `${chapterTitle} — ${st}`)
                                const selectedInChapter = chapterKeys.filter((k) => selectedSubs.includes(k)).length
                                const allInChapter = subtopics.length > 0 && selectedInChapter === subtopics.length
                                return (
                                  <div key={chapterTitle} className="rounded-xl border border-slate-100 bg-slate-50/60">
                                    <div className="flex items-center justify-between gap-2 px-3 py-2">
                                      <button
                                        type="button"
                                        onClick={() => toggleChapterExpanded(id, chapterTitle)}
                                        className="flex flex-1 items-center gap-2 text-right text-[12px] font-black text-brand-950"
                                      >
                                        <ChevronDown className={`h-4 w-4 shrink-0 text-brand-700 transition-transform ${isExpanded ? 'rotate-0' : 'rotate-90'}`} />
                                        <span>{toFarsiNumber(chapterTitle)}</span>
                                        {selectedInChapter > 0 && (
                                          <span className="mr-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-black text-emerald-800">
                                            {toFarsiNumber(selectedInChapter)} از {toFarsiNumber(subtopics.length)}
                                          </span>
                                        )}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => toggleWholeChapter(id, chapterTitle, subtopics)}
                                        className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-bold text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700"
                                      >
                                        {allInChapter ? 'لغو فصل' : 'انتخاب کل فصل'}
                                      </button>
                                    </div>
                                    {isExpanded && (
                                      <div className="grid gap-1.5 border-t border-slate-100 bg-white px-3 py-2 sm:grid-cols-2">
                                        {subtopics.map((sub) => {
                                          const fullKey = `${chapterTitle} — ${sub}`
                                          const on = selectedSubs.includes(fullKey)
                                          return (
                                            <label
                                              key={fullKey}
                                              className={`flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] leading-6 transition ${
                                                on ? 'bg-emerald-50 font-bold text-emerald-900 ring-1 ring-emerald-200' : 'text-slate-600 hover:bg-slate-50'
                                              }`}
                                            >
                                              <input
                                                type="checkbox"
                                                checked={on}
                                                onChange={() => toggleSubTopic(id, fullKey)}
                                                className="h-4 w-4 shrink-0 accent-emerald-600"
                                              />
                                              <span>{toFarsiNumber(sub)}</span>
                                            </label>
                                          )
                                        })}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )}
                      </fieldset>
                    )
                  })}
                </div>

                {/* مجموع سؤالات */}
                <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-2.5">
                  <span className="text-[12px] font-black text-brand-900">مجموع سؤالات آزمون</span>
                  <span className={`text-[13px] font-black tabular-nums ${totalCount > 60 ? 'text-rose-600' : 'text-brand-950'}`}>
                    {toFarsiNumber(totalCount)} سؤال
                  </span>
                </div>
              </section>

              {/* ── توزیع منبع سؤالات: هوش مصنوعی در برابر بانک آزمون ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۳</span>
                  درصد سوالات تولیدی هوش مصنوعی
                </h2>
                <p className="mt-1.5 text-[11px] font-medium leading-6 text-slate-500">
                  نسبت «درصد سوالات تولیدی هوش مصنوعی» به «سوالات بانک آزمون» (کنکور / قلم‌چی / گاج) را مشخص کنید.
                </p>
                <div className="mt-4 flex items-center gap-3 text-[10px] font-black text-slate-400">
                  <span className="shrink-0">۰٪</span>
                  <input
                    id="ai-percentage"
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={aiPercentage}
                    onChange={(e) => setAiPercentage(Number(e.target.value))}
                    className="w-full accent-emerald-600"
                    aria-label="درصد سوالات تولیدی هوش مصنوعی"
                  />
                  <span className="shrink-0">۱۰۰٪</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-slate-50 px-4 py-2.5 text-[12px] font-black">
                  <span className="text-emerald-700">درصد سوالات تولیدی هوش مصنوعی: {toFarsiNumber(aiPercentage)}٪</span>
                  <span className="text-slate-600">سوالات بانک آزمون: {toFarsiNumber(100 - aiPercentage)}٪</span>
                </div>
              </section>

              {/* ── سبک سؤال ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">۴</span>
                  سبک سؤال
                </h2>

                <div className="mt-4">
                  <label htmlFor="question-type" className="label">نوع سؤالات</label>
                  <select
                    id="question-type"
                    value={questionType}
                    onChange={(e) => setQuestionType(e.target.value)}
                    className="input mt-1.5"
                  >
                    {QUESTION_TYPES.map((t) => (
                      <option key={t.id} value={t.id}>{t.label}</option>
                    ))}
                  </select>
                </div>

                <label htmlFor="custom-prompt" className="label mt-4">دستورالعمل سفارشی (اختیاری)</label>
                <textarea
                  id="custom-prompt"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  rows={3}
                  maxLength={600}
                  placeholder="مثلاً: از مبحث فلان سخت‌تر باشد و دام‌های تستی آن مبحث را هدف بگیرد…"
                  className="input mt-1.5"
                />
                <p className="mt-1 text-left text-[10px] font-bold tabular-nums text-slate-400">{fmtFa(customPrompt.length)} / ۶۰۰</p>
              </section>

              {/* ── سطح سختی ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <Flame className="h-5 w-5 text-brand-700" /> سطح سختی
                </h2>
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" role="radiogroup" aria-label="سطح سختی آزمون">
                  {DIFFICULTY_OPTIONS.map(({ id, label, desc, Icon }) => {
                    const on = difficulty === id
                    return (
                      <button
                        key={id}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        onClick={() => setDifficulty(id)}
                        className={`rounded-2xl border p-4 text-center transition-all duration-200 ${
                          on
                            ? 'border-brand-500 bg-brand-50 shadow-lift ring-2 ring-brand-200'
                            : 'border-slate-200/80 bg-white hover:-translate-y-0.5 hover:border-brand-200'
                        }`}
                      >
                        <Icon className={`mx-auto h-6 w-6 ${on ? 'text-brand-700' : 'text-slate-400'}`} strokeWidth={1.8} />
                        <span className="mt-2 block text-[13px] font-black text-brand-950">{label}</span>
                        <span className="mt-1 block text-[9px] font-medium leading-4 text-slate-400">{desc}</span>
                      </button>
                    )
                  })}
                </div>
              </section>

              {/* ── زمان آزمون ── */}
              <section className="card p-5 sm:p-6">
                <h2 className="flex items-center gap-2 text-[15px] font-black text-brand-950">
                  <Timer className="h-5 w-5 text-brand-700" /> زمان آزمون
                </h2>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {TIME_PRESETS.map((t) => {
                    const on = duration === t
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setDuration(t)}
                        aria-pressed={on}
                        className={`rounded-2xl border px-4 py-2.5 text-[13px] font-black tabular-nums transition-all ${
                          on
                            ? 'border-transparent bg-brand-700 text-white shadow-lift'
                            : 'border-slate-200 bg-white text-brand-900 shadow-sm hover:border-brand-300 hover:bg-brand-50'
                        }`}
                      >
                        {fmtFa(t)} دقیقه
                      </button>
                    )
                  })}
                </div>
              </section>
            </div>

            {/* ── ستون کنار: خلاصه + دکمهٔ تولید پیش‌نمایش ── */}
            <div className="space-y-6 lg:col-span-4">
              <section className="card overflow-hidden p-0">
                <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3.5">
                  <h2 className="flex items-center gap-2 text-[14px] font-black text-brand-950"><FileText className="h-4 w-4 text-brand-700" /> پیش‌نمایش تنظیمات</h2>
                </div>
                <dl className="space-y-2.5 px-5 py-4 text-[12px] leading-7">
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">رشته</dt>
                    <dd className="font-bold text-brand-950">{FIELD_LABELS[field]}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">پایه</dt>
                    <dd className="font-bold text-brand-950">{grade === 'comprehensive' ? 'جامع (همهٔ پایه‌ها)' : `پایهٔ ${GRADE_LABELS[grade]}`}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">درس‌ها</dt>
                    <dd className="max-w-[62%] truncate text-left font-bold text-brand-950" title={subjectsLabel}>{subjectsLabel || '—'}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">تعداد کل سؤالات</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(totalCount)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">منبع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{toFarsiNumber(aiPercentage)}٪ هوش مصنوعی · {toFarsiNumber(100 - aiPercentage)}٪ بانک آزمون</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">نوع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{questionTypeLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">سطح سختی</dt>
                    <dd className="font-bold text-brand-950">{difficultyLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-slate-500">زمان</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(duration)} دقیقه</dd>
                  </div>
                </dl>
                <div className="border-t border-slate-100 bg-white px-5 py-4">
                  <button
                    onClick={generatePreview}
                    disabled={generating}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-3.5 text-[14px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-wait disabled:opacity-80"
                  >
                    {generating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
                    {generating ? 'در حال تولید پیش‌نمایش…' : 'تولید پیش‌نمایش آزمون'}
                  </button>
                  {notice && (
                    <p className="mt-3 rounded-2xl bg-amber-50 px-4 py-2.5 text-[11px] font-bold leading-6 text-amber-900" role="status">
                      {notice}
                    </p>
                  )}
                </div>
              </section>

              {/* ── پیش‌نویس‌های قدیمی (فقط مشاهده و حذف) ── */}
              {drafts.length > 0 && (
                <section className="card p-5">
                  <h2 className="flex items-center gap-2 text-[13px] font-black text-brand-950">
                    <ChevronDown className="h-4 w-4 rotate-[-90deg] text-brand-700" /> پیش‌نویس‌های قدیمی ({fmtFa(drafts.length)})
                  </h2>
                  <p className="mt-1.5 text-[10px] leading-5 text-slate-500">قالب آزمون‌ساز به کنکوری تغییر کرده است؛ پیش‌نویس‌های قبلی فقط برای مشاهده و حذف نگه داشته شده‌اند.</p>
                  <ul className="mt-3 max-h-72 space-y-2 overflow-auto">
                    {drafts.map((d) => (
                      <li key={d.id} className="flex items-start justify-between gap-2 rounded-2xl border border-slate-100 bg-slate-50/60 p-3">
                        <div className="min-w-0">
                          <p className="truncate text-[12px] font-black text-brand-950">{d.title}</p>
                          <p className="mt-0.5 text-[10px] leading-5 text-slate-500">
                            {fmtFa(d.totalQuestions ?? 0)} سؤال · {fmtFa(d.duration ?? 0)} دقیقه
                          </p>
                        </div>
                        <button onClick={() => removeDraft(d.id)} aria-label="حذف پیش‌نویس" className="shrink-0 rounded-xl p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          </>
        )}

        {/* ════════════════════════ گام ۲ — پیش‌نمایش و ویرایش ════════════════════════ */}
        {step === 'preview' && (
          <>
            <div className="space-y-4 lg:col-span-8">
              <section className="card flex flex-wrap items-center justify-between gap-3 p-5">
                <div>
                  <h2 className="flex items-center gap-2 text-[16px] font-black text-brand-950">
                    <Wand2 className="h-5 w-5 text-brand-700" /> پیش‌نمایش سؤالات
                  </h2>
                  <p className="mt-1 text-[11px] font-medium text-slate-500">قبل از چاپ، سؤال‌ها را ویرایش کن: حذف، بالا/پایین بردن.</p>
                </div>
                <span className="chip bg-brand-50 text-brand-800 ring-1 ring-brand-200">{fmtFa(questions.length)} سؤال</span>
              </section>

              {questions.length === 0 ? (
                <section className="card p-8 text-center">
                  <Info className="mx-auto h-8 w-8 text-amber-500" />
                  <p className="mt-3 text-[13px] font-bold text-slate-600">همهٔ سؤال‌ها حذف شدند.</p>
                  <button onClick={() => setStep('form')} className="mt-4 inline-flex items-center gap-2 rounded-2xl border border-brand-200 bg-white px-5 py-2.5 text-[12px] font-bold text-brand-800 transition hover:bg-brand-50">
                    <RotateCcw className="h-4 w-4" /> بازگشت به فرم
                  </button>
                </section>
              ) : (
                <ol className="space-y-4">
                  {questions.map((q, idx) => (
                    <li key={q.id ?? idx} className="card p-4 sm:p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="flex h-7 w-7 items-center justify-center rounded-xl bg-brand-700 text-[12px] font-black text-white">{fmtFa(idx + 1)}</span>
                          {q.subject && (
                            <span className="chip bg-sky-50 text-sky-800 ring-1 ring-sky-200">{toFarsiNumber(q.subject)}</span>
                          )}
                          <label className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-black text-emerald-800 ring-1 ring-emerald-200 transition hover:bg-emerald-100">
                            <span>سطح:</span>
                            <select
                              aria-label={`تغییر سطح سختی سؤال ${fmtFa(idx + 1)}`}
                              value={['آسان', 'متوسط', 'سخت', 'کنکوری'].includes(q.difficulty) ? q.difficulty : 'متوسط'}
                              onChange={(e) => updateQuestionDifficulty(idx, e.target.value)}
                              className="cursor-pointer bg-transparent font-black text-emerald-900 focus:outline-none"
                            >
                              <option value="آسان">آسان</option>
                              <option value="متوسط">متوسط</option>
                              <option value="سخت">سخت</option>
                              {q.difficulty === 'کنکوری' && <option value="کنکوری">کنکوری</option>}
                            </select>
                          </label>
                          {q.source_tag && (
                            <span className="chip bg-amber-50 text-amber-800 ring-1 ring-amber-200" title="این تگ فقط در پیش‌نمایش دیده می‌شود و در PDF چاپ نمی‌شود">
                              {q.source_tag}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => moveQuestion(idx, -1)}
                            disabled={idx === 0}
                            aria-label="بالا بردن سؤال"
                            title="بالا بردن"
                            className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 transition hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            <ArrowUp className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => moveQuestion(idx, +1)}
                            disabled={idx === questions.length - 1}
                            aria-label="پایین آوردن سؤال"
                            title="پایین آوردن"
                            className="rounded-xl border border-slate-200 bg-white p-2 text-brand-800 transition hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            <ArrowDown className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => removeQuestion(q.id ?? idx)}
                            aria-label="حذف سؤال"
                            title="حذف"
                            className="rounded-xl border border-red-100 bg-red-50/60 p-2 text-red-500 transition hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                      <div className="math-content mt-3 text-[13px] font-bold leading-7 text-brand-950">
                        <MathText content={q.text || q.question_text || q.title || ''} className="text-slate-800 text-base" />
                      </div>
                      {q.diagram_svg && (
                        <figure className="mt-3 overflow-hidden rounded-2xl border border-teal-200/70 bg-white p-3 shadow-inner">
                          <div
                            className="mx-auto max-w-sm"
                            dangerouslySetInnerHTML={{ __html: String(q.diagram_svg) }}
                          />
                        </figure>
                      )}
                      <ol className="mt-3 grid gap-2 sm:grid-cols-2">
                        {(q.options || []).map((opt, oi) => {
                          const correct = oi === Number(q.correct_answer) - 1
                          return (
                            <li
                              key={oi}
                              className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-[12px] leading-6 ${
                                correct
                                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200'
                                  : 'border-slate-200 bg-slate-50/60 text-slate-600'
                              }`}
                            >
                              <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-black ${correct ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-600'}`}>
                                {fmtFa(oi + 1)}
                              </span>
                              <div className="math-inline min-w-0 flex-1">
                                <MathText content={opt || ''} className="text-slate-700 text-sm" />
                              </div>
                              {correct && <Check className="mr-auto h-4 w-4 shrink-0 self-center text-emerald-600" />}
                            </li>
                          )
                        })}
                      </ol>
                    </li>
                  ))}
                </ol>
              )}

              <p className="rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-2.5 text-[10px] font-bold leading-6 text-amber-800">
                «تگ منبع» (مثلاً کنکور ۱۴۰۱، قلم‌چی یا تألیفی AI) فقط در این پیش‌نمایش نمایش داده می‌شود و در PDF نهایی هرگز چاپ نمی‌شود.
              </p>
            </div>

            {/* ── ستون کنار: خلاصهٔ نهایی + تأیید و دانلود ── */}
            <div className="space-y-6 lg:col-span-4">
              <section className="card overflow-hidden p-0 lg:sticky lg:top-6">
                <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-3.5">
                  <h2 className="flex items-center gap-2 text-[14px] font-black text-brand-950"><FileText className="h-4 w-4 text-brand-700" /> خلاصهٔ PDF نهایی</h2>
                </div>
                <dl className="space-y-2.5 px-5 py-4 text-[12px] leading-7">
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">مدرسه</dt>
                    <dd className="max-w-[60%] truncate text-left font-bold text-brand-950" title={schoolName}>{schoolName.trim() || 'مدرسهٔ نمونه'}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">رشته / پایه</dt>
                    <dd className="font-bold text-brand-950">{FIELD_PRINT_LABELS[field]} · {grade === 'comprehensive' ? 'جامع' : `پایهٔ ${GRADE_LABELS[grade]}`}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">درس‌ها / تعداد</dt>
                    <dd className="max-w-[62%] truncate text-left font-bold text-brand-950" title={subjectsLabel}>{subjectsLabel || '—'} · {fmtFa(totalCount)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">نوع سؤالات</dt>
                    <dd className="font-bold text-brand-950">{questionTypeLabel}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 border-b border-dashed border-slate-100 pb-2">
                    <dt className="text-slate-500">تعداد سؤال نهایی</dt>
                    <dd className="font-black tabular-nums text-brand-950">{fmtFa(questions.length)} سؤال</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt className="text-slate-500">زمان / سختی</dt>
                    <dd className="font-bold text-brand-950">{fmtFa(duration)} دقیقه · {difficultyLabel}</dd>
                  </div>
                </dl>
                <div className="border-t border-slate-100 bg-white px-5 py-4">
                  <button
                    onClick={confirmAndDownload}
                    disabled={downloading || questions.length === 0}
                    className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-600 py-4 text-[14px] font-black text-white shadow-lift transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {downloading ? <Loader2 className="h-5 w-5 animate-spin" /> : <CheckCircle2 className="h-5 w-5" />}
                    {downloading ? 'در حال ساخت PDF…' : 'تأیید و دانلود PDF نهایی'}
                  </button>
                  <button
                    onClick={() => setStep('form')}
                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-2xl border border-brand-200 bg-white py-3 text-[12px] font-bold text-brand-800 transition hover:bg-brand-50"
                  >
                    <RotateCcw className="h-4 w-4" /> بازگشت و تغییر تنظیمات
                  </button>
                  {pdfUrl && (
                    <a
                      href={pdfUrl}
                      download="fahmyar-konkur-exam.pdf"
                      className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-700 py-3 text-[13px] font-black text-white shadow-lift transition hover:bg-emerald-800"
                    >
                      <FileDown className="h-5 w-5" />
                      دانلود PDF آزمون و پاسخنامه
                    </a>
                  )}
                  {notice && (
                    <p className={`mt-3 rounded-2xl px-4 py-2.5 text-[11px] font-bold leading-6 ${notice.startsWith('⚠️') ? 'bg-amber-50 text-amber-900' : 'bg-emerald-50 text-emerald-900'}`} role="status">
                      {notice}
                    </p>
                  )}
                </div>
              </section>
            </div>
          </>
        )}
      </div>

      {/* ── پوشش تمام‌صفحهٔ «در حال تولید» ── */}
      {generating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 p-4 backdrop-blur-sm" role="alertdialog" aria-modal="true" aria-label="در حال تولید پیش‌نمایش">
          <div className="w-full max-w-md rounded-3xl border border-emerald-100 bg-white p-8 text-center shadow-lift">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 ring-1 ring-emerald-100">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
            </span>
            <h3 className="mt-5 text-base font-black leading-7 text-slate-800">
              در حال تولید، اعتبارسنجی و رسم اشکال هندسی... (این فرآیند ممکن است ۱ تا ۲ دقیقه زمان ببرد)
            </h3>
            <div
              className="mb-2 text-lg font-bold text-slate-700 tabular-nums font-vazirmatn"
              aria-live="polite"
            >
              {toFarsiNumber(Math.round(progressPercent))}٪
            </div>
            <div
              className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-emerald-100"
              role="progressbar"
              aria-valuenow={Math.round(progressPercent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="درصد پیشرفت تولید آزمون"
            >
              <div
                className="h-full rounded-full bg-gradient-to-l from-emerald-500 to-teal-500 transition-[width] duration-200 ease-out"
                style={{ width: `${Math.round(progressPercent)}%` }}
              />
            </div>
            <p className="mt-3 text-[11px] font-medium text-slate-500">لطفاً صفحه را نبندید؛ سامانه در حال طراحی دقیق سؤالات و اشکال است.</p>
          </div>
        </div>
      )}
    </div>
  )
}
