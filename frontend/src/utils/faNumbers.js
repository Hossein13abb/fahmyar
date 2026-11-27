/**
 * تبدیل ارقام لاتین به ارقام فارسی — برای نمایش تمام اعداد UI.
 * (طبق قرارداد پروژه: عدد در UI همیشه با ارقام فارسی)
 */
const FA = '۰۱۲۳۴۵۶۷۸۹'
export const toFarsiNumber = (n) => String(n ?? '').replace(/\d/g, (d) => FA[d])

/** برچسب فارسی درس‌ها برای نمایش (جایگزین مقدار فنی لاتین) */
export const SUBJECT_FA = {
  math: 'ریاضی',
  // «mathematics» و «experimental» نامِ **رشته**‌اند، نه درس: وقتی مفهوم از
  // انتخاب‌گرِ کوریکولوم ساخته می‌شود، curriculum_bridge مقدارِ subject را
  // با نامِ رشته پر می‌کند (MAJOR_TO_DB_SUBJECT). بدونِ این دو کلید،
  // subjectFa به مقدارِ خامِ انگلیسی برمی‌گشت و در کارتِ تاریخچه
  // «mathematics» دیده می‌شد.
  mathematics: 'ریاضی',
  experimental: 'علوم تجربی',
  physics: 'فیزیک',
  chemistry: 'شیمی',
  biology: 'زیست‌شناسی',
  literature: 'ادبیات فارسی',
  english: 'زبان انگلیسی',
  arabic: 'عربی',
}
export const subjectFa = (s) => SUBJECT_FA[String(s || '').toLowerCase()] ?? s
