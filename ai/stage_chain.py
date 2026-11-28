"""تولیدِ «زنجیرهٔ ۵ مرحله‌ای» آزمون فهم‌سنجی — از کل به جزء و دوباره به کل.

جایگزینِ کاملِ دفترچهٔ ۹ سؤالی. تفاوتِ بنیادی: این آزمون *یک زنجیره* است،
نه پنج سؤالِ مستقل. هر مرحله لایهٔ متفاوتی از ذهن را می‌سنجد و مرحلهٔ بعد
بدونِ مرحلهٔ قبل معنا ندارد — مخصوصاً سؤال ۵ که باید حرفِ سؤال ۲ را نقض کند
یا تأیید و بدونِ آن قابلِ تفسیر نیست.

**قانونِ فرمت‌بندی:** هرگز از `.format()` روی متنِ پرامپت استفاده نکنید.
متنِ پرامپت آکولادِ LaTeX دارد (`\\frac{4}{9}`، `\\cos^{-1}`) و `.format`
آن‌ها را فیلدِ جای‌گذاری می‌بیند و `KeyError: '-1'` می‌دهد. از
`ai.prompt_safe.fill` استفاده کنید.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ai.booklet_cache import booklet_cache_key, get_cached_booklet, put_cached_booklet
from ai.brand_terms import PUBLIC_STAGE_BY_TYPE, PUBLIC_STAGE_TITLES
from ai.json_sanitize import extract_json_object
from ai.model_abstraction import get_router
from ai.prompt_safe import fill

#: ترتیبِ اجباریِ پنج مرحله — همان‌جا که سؤال ساخته می‌شود هم استفاده می‌شود.
STAGE_ORDER: tuple[str, ...] = (
    "philosophy",
    "mask_mcq",
    "perturbation",
    "debugging",
    "feynman_synthesis",
)

#: فاز ۱۱ — هر مرحله **دو** سؤال دارد: ۵ مرحله × ۲ = ۱۰ سؤال.
#: ``order`` در سراسرِ سامانه یکتا و پیوسته (۱..۱۰) است؛ ``stage`` شمارهٔ
#: مرحله (۱..۵) و ``stage_slot`` جای سؤال داخلِ مرحله (۱ یا ۲) است.
QUESTIONS_PER_STAGE = 2
TOTAL_QUESTIONS = len(STAGE_ORDER) * QUESTIONS_PER_STAGE  # ۱۰

#: order → شمارهٔ مرحله. سؤالِ ۱ و ۲ مرحلهٔ ۱ هستند، ۳ و ۴ مرحلهٔ ۲، …
def stage_of_order(order: int) -> int:
    """شمارهٔ مرحله (۱..۵) برای ترتیبِ سؤال (۱..۱۰)."""
    try:
        value = int(order)
    except (TypeError, ValueError):
        return 0
    if value < 1 or value > TOTAL_QUESTIONS:
        return 0
    return (value - 1) // QUESTIONS_PER_STAGE + 1


def orders_of_stage(stage: int) -> tuple[int, ...]:
    """ترتیب‌های سؤالِ یک مرحله — مثلاً مرحلهٔ ۳ ⇒ (۵، ۶)."""
    base = (int(stage) - 1) * QUESTIONS_PER_STAGE
    return tuple(base + i + 1 for i in range(QUESTIONS_PER_STAGE))


def stage_key(order: int) -> str:
    """کلیدِ مرحله برای برچسب‌گذاری: exam_type همان مرحله."""
    stage = stage_of_order(order)
    if stage == 0:
        return ""
    return STAGE_ORDER[stage - 1]


# برچسب‌های رو به کاربر — فقط زبانِ عمومی. اسم‌های متدولوژیکِ داخلی
# («نقاب»، «فاینمن»، «ساعتِ خراب») عمداً این‌جا نیستند: داراییِ فکری
# است و نباید در UI دیده شود. منطقِ سنجش دست‌نخورده است.
STAGE_TITLES: dict[str, str] = {
    "philosophy": PUBLIC_STAGE_BY_TYPE["philosophy"],
    "mask_mcq": PUBLIC_STAGE_BY_TYPE["mask_mcq"],
    "perturbation": PUBLIC_STAGE_BY_TYPE["perturbation"],
    "debugging": PUBLIC_STAGE_BY_TYPE["debugging"],
    "feynman_synthesis": PUBLIC_STAGE_BY_TYPE["feynman_synthesis"],
}

STAGE_TITLES_FA: dict[int, str] = dict(PUBLIC_STAGE_TITLES)


# ---------------------------------------------------------------------------
# قالبِ پرامپت
# ---------------------------------------------------------------------------
_BOOKLET_PROMPT = r"""CRITICAL MATH FORMATTING RULE:
Every mathematical symbol, formula, vector, power or inverse function MUST be enclosed in inline math `$ ... $`.
Examples of CORRECT formatting:
- Inverse trig / functions: `$\cos^{-1}\left(\frac{4}{9}\right)$` (NOT `cos^-1(4/9)`)
- Powers: `$T^{-1}$`, `$x^2$` (NOT `T^-1`)
- Vectors: `$\vec{n}_1 = (1, 2, 2)$`
Never output raw LaTeX commands outside `$ ... $`.
Even inside LaTeX blocks, use Persian numbers (۰۱۲۳۴۵۶۷۸۹): `$۲x + ۵ = ۱۲$`.
CRITICAL JSON ESCAPING RULE: double-escape all LaTeX in the JSON (`\\frac`, `\\sqrt`, `\\theta`, `\\vec`). Never escape the `$` delimiter.

CRITICAL SYLLABUS RULE (نظام جدید ۱۳۹۷ به بعد):
Only generate questions compliant with Iranian high-school textbooks published after 1397.
FORBIDDEN: integrals in حسابان ۲, general equations of ellipse/hyperbola, 3x3 matrix inverses, obsolete pre-1397 physics topics.

═══════════════════════════════════════════════════════════════
شما «طراحِ ارشدِ آزمونِ فهم‌سنجی شناختی» هستید. برای مفهوم «{concept}»
({subject} — پایه {grade}) **یک زنجیرهٔ ۵ مرحله‌ای بسازید که هر مرحله‌اش دو
سؤال دارد — در کل ۱۰ سؤال به‌هم‌پیوسته.**

این آزمون ده سؤالِ مستقل نیست. **پنج مرحله است و هر مرحله دو سؤال دارد؛
هر مرحله لایهٔ متفاوتی از ذهن را می‌سنجد** و مرحلهٔ بعد بدون مرحلهٔ قبل
معنا ندارد. دو سؤالِ یک مرحله باید یک مهارت را از **دو زاویهٔ متفاوت**
بسنجند — نه اینکه دومی تکرارِ اولی با عددِ دیگر باشد.
═══════════════════════════════════════════════════════════════

🔹 مرحله ۱ — «سؤال مفهومی» (exam_type: "philosophy"، ترتیبِ ۱ و ۲)
   **دو سؤالِ تشریحیِ کوتاه، مطلقاً بدونِ هیچ فرمول و عدد.**
   • سؤال ۱: **چراییِ پیدایشِ مفهوم** — انسان پیش از این مفهوم به چه
     بن‌بستِ علمی می‌خورد که مجبور شد آن را بسازد؟
   • سؤال ۲: **تفاوتِ نگاهِ روزمره با نگاهِ تخصصی** — در زندگیِ روزمره این
     پدیده را چطور می‌بینیم و نگاهِ فیزیک/ریاضی/شیمی چه چیزی را عوض می‌کند؟
   دو سؤال نباید پاسخِ هم را لو بدهند و نباید هم‌پوشانیِ کامل داشته باشند.
   **قانونِ یک پرسش:** متنِ این مرحله باید فقط **یک** پرسش باشد، با **یک**
   هدفِ شناختیِ روشن. اگر دو پرسشِ مستقل را با «و» یا «همچنین» به هم بچسبانی،
   دانش‌آموز یکی را جواب می‌دهد و یکی را جا می‌گذارد و سنجش بی‌معنا می‌شود.
   ❌ بد: «تفاوتِ مواد را بگو و ساختارِ درونی را توضیح بده و بگو رسانای اهمی
      یعنی چه و تصویرِ کلان چیست.»
   ✅ خوب: «چرا انسان‌ها برای توصیفِ این پدیده به یک مفهومِ تازه نیاز پیدا
      کردند؟»
   موضوع را یا از فلسفهٔ پیدایشِ مفهوم بگیر یا از مکانیزمِ بنیادیِ پدیده —
   نه هر دو با هم. هدف: شناساییِ کسی که مفهومِ پایه را نمی‌داند و با کلماتِ
   قلمبه‌سلمبه بلوف می‌زند.
   ⛔ **پاسخ را در خودِ سؤال لو نده.** جمله‌هایی مثل «نه ویژگیِ منبع تغذیه»،
   «مستقل از ولتاژ است» یا «مقاومت به جنس و طول بستگی دارد» پاسخ را پیش‌پاافتاده
   می‌کنند و سنجش را بی‌اثر؛ دانش‌آموز باید خودش به آن برسد.
   واژگانِ کتابِ درسی بمان: ویژگیِ «ذاتی» رسانا، نه «محدودکنندهٔ ثابت مسیر».

🔹 مرحله ۲ — «سؤال چهارگزینه‌ای» (exam_type: "mask_mcq"، ترتیبِ ۳ و ۴)
   **دو تستِ ۴ گزینه‌ای.** فیلدهای لازم برای هر کدام: "options" (آرایهٔ ۴
   رشته) و "correct_option_index" (عددِ ۰ تا ۳ — **یک‌پایه نیست، از ۰ شروع
   می‌شود**).
   هر دو سؤال تستِ استانداردِ کتابی دربارهٔ قانونِ اصلی‌اند و هر دو باید
   **یک دادهٔ اضافی** داشته باشند: داده‌ای کاملاً معقول که در
   بافتِ مسئله طبیعی و از نظرِ علمی ممکن است، ولی در محاسبه به کار نمی‌آید.
   دو تست باید **دو قانونِ متفاوت** را بسنجند یا یک قانون را در دو شرایطِ
   متفاوت — نه یک محاسبهٔ تکراری.
   ✅ نمونهٔ درست: «در مداری با ولتاژ $۱۲$ ولت و مقاومتِ $۴$ اهم، جریان چند
      آمپر است؟ طولِ سیمِ رابط $۵۰$ سانتی‌متر است.»
   ❌ نمونهٔ غلط: «حجمِ منبع تغذیه $۲$ لیتر است» — دادهٔ پرت و نامعقول، تلهٔ
      شناختی نمی‌سازد، فقط سؤال را بی‌کیفیت می‌کند.
   ⛔ **مهم‌ترین قاعدهٔ این مرحله — تله نباید لو برود:** هرگز در صورتِ سؤال
   نگو کدام داده مؤثر است و کدام نیست. جمله‌هایی مثل «این داده هیچ نقشی
   ندارد»، «برای گمراه کردن آمده»، «ناچیز و بی‌اثر فرض می‌شود» یا «نه ویژگیِ
   منبع تغذیه» **ممنوع** است؛ با این جمله‌ها تله بی‌معنا می‌شود و دانش‌آموز
   فقط باید جملهٔ آخر را بخواند. دادهٔ اضافی را ساده و بی‌توضیح بیاور؛ خودِ
   دانش‌آموز باید تصمیم بگیرد به محاسبه مربوط است یا نه.
   هدف: ثبتِ اینکه قانونِ رسمی را می‌داند یا نه، تا در مرحله ۵ با شهودش
   مقایسه شود.

🔹 مرحله ۳ — «پیش‌بینی رفتار پدیده» (exam_type: "perturbation"، ترتیبِ ۵ و ۶)
   **دو سؤالِ تشریحیِ تحلیلی و مطلقاً بدونِ عدد و فرمول.**
   در هر سؤال یک سناریوی پویا هست که در آن تغییر **در ابتدای زنجیرهٔ علّی**
   اعمال می‌شود و دانش‌آموز باید اتفاقِ نهاییِ سیستم را پیش‌بینی کند: اول چه
   عوض می‌شود، بعدش چه، و سرانجام خروجی چه تغییری می‌کند و **چرا**.
   دو سؤال باید دو نقطهٔ متفاوتِ زنجیره را دستکاری کنند (مثلاً یکی ورودی و
   یکی شرایطِ محیط) تا پیش‌بینیِ پدیده از دو جهت سنجیده شود.
   در صورتِ سؤال شرط‌ها را صریح بگذار («با ثابت ماندنِ ولتاژِ منبع»، «با
   نادیده گرفتنِ تغییرِ دما») تا فقط یک پاسخِ درست وجود داشته باشد.

🔹 مرحله ۴ — «بررسی استدلال علمی» (exam_type: "debugging"، ترتیبِ ۷ و ۸)
   **شاه‌کلیدِ تشخیص — دو سؤالِ نقدِ استدلال.**
   در هر سؤال یک دانش‌آموزِ فرضی (امیر یا سارا - برای هر سؤال نامِ متفاوت)
   استدلالی مطرح می‌کند که ظاهرش بسیار منطقی و علمی است اما نتیجه‌اش غلط.
   دو سؤال باید **دو بدفهمیِ متفاوت** را هدف بگیرند (از فهرستِ بدفهمی‌های
   همین مفهوم)، تا نقدِ دانش‌آموز از دو زاویه سنجیده شود. این استدلال
   باید بر پایهٔ این بدفهمیِ رایج ساخته شود: «{misconception}»
   از دانش‌آموز بپرس: «استدلالِ او دقیقاً در کدام نقطه می‌شکند و سوتیِ
   منطقی‌اش کجاست؟» نامِ دانش‌آموزِ فرضی و یک نقلِ‌قولِ مستقیم از او در متن بیاور.
   **دقتِ علمیِ نقد:** شرطِ فیزیکی را در صورتِ سؤال روشن کن (دما و شرایط
   ثابت). خودِ استدلالِ دانش‌آموزِ فرضی باید یک بدفهمیِ **واقعی** باشد، نه
   چیزی که در واقع درست است. نمونهٔ خطای رایج: نوشتنِ «مقاومتِ سیم مطلقاً و
   در همهٔ اجزا مستقل از ولتاژ است» — این جمله پیش‌فرضِ ساده‌سازی‌شده است،
   نه قانونِ طبیعت؛ استدلالِ غلط باید به همین پیش‌فرض تکیه کند، نه اینکه
   خودِ سؤال آن را قانونِ مطلق جا بزند.

🔹 مرحله ۵ — «توضیح ساده و شهودی» (exam_type: "feynman_synthesis"، ترتیبِ ۹ و ۱۰)
   **دو سؤال.** از دانش‌آموز بخواه **دو جنبهٔ اصلیِ متفاوتِ مفهوم** را برای
   یک **بچهٔ ۱۰ ساله** توضیح دهد (مرتبط با منطقِ مرحلهٔ ۲).
   **قانونِ حیاتی:** فیلد "forbidden_words" باید برای **هر سؤال جداگانه**
   آرایه‌ای از **۴ تا ۶** کلمهٔ تخصصی و فرمولیِ همان جنبه باشد که دانش‌آموز
   حق ندارد در پاسخش به کار ببرد. دو فهرستِ ممنوعه باید با هم **متفاوت**
   باشند و هر کدام به همان جنبهٔ سؤالِ خودش مربوط باشد — نه یک فهرستِ
   تکراری برای هر دو.
   این کلمات باید **دقیقاً همان واژه‌هایی** باشند که در متنِ سؤال و در
   توضیحِ کتابیِ مبحث می‌آیند (نه واژه‌های عمومی مثل «علم» یا «چیز»)، وگرنه
   مقایسهٔ مرحله ۲ با مرحله ۵ بی‌معنا می‌شود.
   (نمونه — فشار: ["فرمول", "چگالی", "ارتفاع", "جاذبه"]؛ مشتق: ["شیب", "حد",
   "خط مماس", "فرمول"]). هدف: خلعِ سلاحِ حافظهٔ طوطی‌وار تا ببینیم آیا حرفِ
   درستِ خودش در مرحله ۲ را نقض می‌کند یا نه.

───────────────────────────────────────────────────────────────
قواعدِ قطعیِ خروجی
───────────────────────────────────────────────────────────────
۱. فقط JSON معتبر برگردانید — هیچ متنِ توضیحی قبل یا بعد از آن، حتی یک کلمه.
۲. تمام متن‌ها ۱۰۰٪ فارسیِ روان. اصطلاحاتِ ریاضی را ترجمه یا آوانویسی نکنید
   («فنکشن» و «مشduc» ممنوع)؛ از نمادِ LaTeX استفاده کنید.
۲.۱. **واژگانِ کتابِ درسی الزامی است.** «مدارِ الکتریکی» را «مدار» بنویس، نه
   «دایره». واژهٔ «دایره» فقط برای شکلِ هندسی به کار می‌رود. در فیزیک:
   «مدار»، «جریان»، «مقاومت»، «رسانا» — همان‌طور که در کتابِ درسی آمده است.
۳. فقط سؤال‌های ۳ و ۴ (مرحلهٔ ۲) "options" دارند. سؤال‌های ۱، ۲، ۵، ۶، ۷،
   ۸، ۹ و ۱۰ باید "options": null داشته باشند.
۴. برای هر سؤال فیلد "expected_logic" را پر کنید: هستهٔ استدلالی که پاسخِ
   درست باید به آن اشاره کند. این فیلد فقط برای ارزیاب استفاده می‌شود و به
   دانش‌آموز نشان داده نمی‌شود.
۵. **دقیقاً ۱۰ سؤال** با شماره‌گذاریِ پیوستهٔ order از ۱ تا ۱۰ و exam_type
   دقیقاً مطابقِ این نگاشت:
   ۱،۲ → philosophy | ۳،۴ → mask_mcq | ۵،۶ → perturbation |
   ۷،۸ → debugging | ۹،۱۰ → feynman_synthesis
۶. هر دو سؤالِ یک مرحله باید **مستقل** باشند: پاسخِ یکی نباید پاسخِ دیگری
   را لو بدهد و نباید عیناً تکرار شود.

ساختارِ خروجی (دقیقاً ۱۰ سؤال، به همین ترتیب):
{
  "concept_blueprint": {
    "core_mechanism": "منطقِ اصلیِ مبحث در دو خط",
    "target_misconceptions": ["بدفهمی ۱", "بدفهمی ۲", "بدفهمی ۳"]
  },
  "questions": [
    {"order": 1, "exam_type": "philosophy", "stage_title": "سؤال مفهومی",
     "text": "چراییِ پیدایشِ مفهوم...", "difficulty": "medium", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 2, "exam_type": "philosophy", "stage_title": "سؤال مفهومی",
     "text": "تفاوتِ نگاهِ روزمره با نگاهِ علمی...", "difficulty": "medium", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 3, "exam_type": "mask_mcq", "stage_title": "سؤال چهارگزینه‌ای",
     "text": "...", "difficulty": "medium", "cognitive_type": "computational",
     "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"], "correct_option_index": 1,
     "forbidden_words": [], "expected_logic": "...", "mapped_propositions": []},

    {"order": 4, "exam_type": "mask_mcq", "stage_title": "سؤال چهارگزینه‌ای",
     "text": "...", "difficulty": "medium", "cognitive_type": "computational",
     "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"], "correct_option_index": 2,
     "forbidden_words": [], "expected_logic": "...", "mapped_propositions": []},

    {"order": 5, "exam_type": "perturbation", "stage_title": "پیش‌بینی رفتار پدیده",
     "text": "...", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 6, "exam_type": "perturbation", "stage_title": "پیش‌بینی رفتار پدیده",
     "text": "...", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 7, "exam_type": "debugging", "stage_title": "بررسی استدلال علمی",
     "text": "امیر می‌گوید: «...» — سوتیِ او کجاست؟", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 8, "exam_type": "debugging", "stage_title": "بررسی استدلال علمی",
     "text": "سارا می‌گوید: «...» — سوتیِ او کجاست؟", "difficulty": "hard", "cognitive_type": "conceptual",
     "options": null, "correct_option_index": null, "forbidden_words": [],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 9, "exam_type": "feynman_synthesis", "stage_title": "توضیح ساده و شهودی",
     "text": "جنبهٔ اول را برای بچهٔ ۱۰ ساله توضیح بده...", "difficulty": "hard", "cognitive_type": "combined",
     "options": null, "correct_option_index": null,
     "forbidden_words": ["کلمه ۱", "کلمه ۲", "کلمه ۳", "کلمه ۴"],
     "expected_logic": "...", "mapped_propositions": []},

    {"order": 10, "exam_type": "feynman_synthesis", "stage_title": "توضیح ساده و شهودی",
     "text": "جنبهٔ دوم را برای بچهٔ ۱۰ ساله توضیح بده...", "difficulty": "hard", "cognitive_type": "combined",
     "options": null, "correct_option_index": null,
     "forbidden_words": ["کلمه ۵", "کلمه ۶", "کلمه ۷", "کلمه ۸"],
     "expected_logic": "...", "mapped_propositions": []}
  ]
}

<<<CONCEPT>>>{concept}<<<END>>>
<<<PROPOSITION>>>{proposition}<<<END>>>
<<<MISCONCEPTION>>>{misconception}<<<END>>>
<<<WRONG_ANSWER>>>{wrong_answer}<<<END>>>
"""

#: پنج سؤالِ اضطراری — اگر مدل در سه تلاش نتوانست بسازد.
#: عمداً برای هر مرحله یک متنِ کامل وجود دارد تا آزمونِ ناقص به دانش‌آموز نرسد.
_FALLBACK_STAGES: tuple[dict[str, Any], ...] = (
    # ── مرحله ۱: فلسفه و تصویر کلان (order ۱ و ۲) ──
    {
        "order": 1,
        "exam_type": "philosophy",
        "text": (
            "بدونِ هیچ فرمول و عددی: پیش از آن‌که «{concept}» ساخته شود، انسان "
            "در توصیفِ این پدیده به چه بن‌بستی می‌خورد؟ این مفهوم دقیقاً چه "
            "مشکلی را حل کرد که پیش از آن حل‌شدنی نبود؟"
        ),
        "difficulty": "medium",
        "cognitive_type": "conceptual",
        "expected_logic": "بیانِ بن‌بستِ پیشین و کارکردِ واقعیِ مفهوم",
    },
    {
        "order": 2,
        "exam_type": "philosophy",
        "text": (
            "در زندگیِ روزمره، همهٔ ما با پدیدهٔ «{concept}» سروکار داریم و "
            "شهودی درباره‌اش حرف می‌زنیم. نگاهِ علمی به همین پدیده چه چیزی را "
            "عوض می‌کند که نگاهِ روزمره نمی‌بیند؟"
        ),
        "difficulty": "medium",
        "cognitive_type": "conceptual",
        "expected_logic": "تمایزِ شهودِ روزمره از نگاهِ کمّی/علّی",
    },
    # ── مرحله ۲: تستِ لایهٔ نقاب (order ۳ و ۴) ──
    {
        "order": 3,
        "exam_type": "mask_mcq",
        "text": (
            "دربارهٔ «{concept}» و رابطه‌ای که در کلاس خوانده‌ای، کدام گزاره از "
            "نظرِ علمی درست است؟ گزینه‌ای را انتخاب کن که با رفتارِ واقعیِ "
            "سیستم در شرایطِ یکسان جور دربیاید."
        ),
        "difficulty": "medium",
        "cognitive_type": "conceptual",
        "options": [
            "فقط متغیرِ اصلیِ رابطه تعیین‌کننده است و بقیهٔ کمیت‌ها نتیجه را عوض نمی‌کنند.",
            "با بزرگ‌تر شدنِ هر کمیتِ دیگری که در صورتِ مسئله آمده، نتیجه هم بزرگ‌تر می‌شود.",
            "هیچ‌کدام از کمیت‌ها به‌تنهایی تعیین‌کننده نیست و باید میانگین گرفت.",
            "نمی‌توان گفت؛ چون کمیت‌های صورتِ مسئله با هم در تضادند.",
        ],
        "correct_option_index": 0,
        "expected_logic": "شناساییِ متغیرِ مؤثر و کنارگذاشتنِ دادهٔ نامرتبط",
    },
    {
        "order": 4,
        "exam_type": "mask_mcq",
        "text": (
            "برای سنجشِ دقتِ محاسبه در «{concept}»: اگر کمیتِ اصلیِ رابطه "
            "دوبرابر شود، نتیجه‌اش — بر اساسِ همان رابطه‌ای که در کتاب آمده — "
            "چه تغییری می‌کند؟"
        ),
        "difficulty": "medium",
        "cognitive_type": "computational",
        "options": [
            "دوبرابر می‌شود.",
            "نصف می‌شود.",
            "تغییری نمی‌کند.",
            "چهار برابر می‌شود.",
        ],
        "correct_option_index": 0,
        "expected_logic": "کاربردِ مستقیمِ رابطه در یک تغییرِ ساده",
    },
    # ── مرحله ۳: مونتاژ ذهنی و دستکاریِ سیستم (order ۵ و ۶) ──
    {
        "order": 5,
        "exam_type": "perturbation",
        "text": (
            "بدونِ هیچ عددی: فرض کن سیستمِ «{concept}» را از محیطِ همیشگی‌اش "
            "برمی‌داریم و در محیطی با شرایط متفاوت قرار می‌دهیم. زنجیرهٔ "
            "تغییرات را پیش‌بینی کن: اول چه چیزی عوض می‌شود؟ بعدش چه اتفاقی "
            "می‌افتد؟ و در نهایت خروجیِ نهایی چه تغییری می‌کند و چرا؟"
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
        "expected_logic": "زنجیرهٔ علّیِ کامل از تغییرِ ورودی تا خروجی",
    },
    {
        "order": 6,
        "exam_type": "perturbation",
        "text": (
            "باز هم بدونِ عدد: اگر همان متغیرِ ورودی در «{concept}» به‌جای "
            "بزرگ‌شدن، کوچک شود، کدام حلقهٔ میانیِ زنجیره اول واکنش نشان "
            "می‌دهد و نتیجهٔ نهایی چه می‌شود؟ جهتِ تغییر را با دلیل بگو."
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
        "expected_logic": "زنجیرهٔ علّی معکوس با جهتِ درستِ تغییرات",
    },
    # ── مرحله ۴: بررسی استدلال علمی (order ۷ و ۸) ──
    {
        "order": 7,
        "exam_type": "debugging",
        "text": (
            "امیر می‌گوید: «طبقِ آنچه در کلاس خواندیم، دربارهٔ «{concept}» "
            "قطعاً این‌طور باید باشد و این با تجربهٔ روزمره‌ام هم جور است.» "
            "او یک استدلالِ سه‌مرحله‌ای می‌آورد که هر مرحله‌اش به‌تنهایی درست "
            "به نظر می‌رسد. سوتیِ منطقیِ استدلالِ امیر دقیقاً کجاست؟ یک جمله‌ای "
            "از او را داخلِ گیومه نقل کن و بگو چرا آن جمله می‌لنگد."
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
        "expected_logic": "پیدا کردنِ فرضِ نادرست در استدلالِ ظاهراً درست",
    },
    {
        "order": 8,
        "exam_type": "debugging",
        "text": (
            "سارا برای حلِ یک مسئلهٔ «{concept}» راه‌حلی می‌نویسد که جوابِ "
            "نهایی‌اش درست از آب درمی‌آید، اما یکی از فرض‌های میانی‌اش غلط است. "
            "چطور می‌شود که استدلال غلط باشد ولی جواب درست شود؟ کدام فرضِ "
            "سارا می‌لنگد و اگر شرایط عوض می‌شد، کجا جوابش می‌شکست؟"
        ),
        "difficulty": "hard",
        "cognitive_type": "conceptual",
        "expected_logic": "تفکیکِ درستیِ نتیجه از درستیِ استدلال",
    },
    # ── مرحله ۵: چالشِ فاینمن (order ۹ و ۱۰) ──
    {
        "order": 9,
        "exam_type": "feynman_synthesis",
        "text": (
            "جنبهٔ اولِ «{concept}» را برای یک بچهٔ ۱۰ ساله توضیح بده: این "
            "پدیده در زندگیِ روزمره چطور اثر می‌گذارد و چرا؟ توضیحت باید طوری "
            "باشد که بچه خودش بتواند آن را برای دوستش تعریف کند."
        ),
        "difficulty": "hard",
        "cognitive_type": "combined",
        "forbidden_words": ["فرمول", "قانون", "تعریف", "اصطلاح"],
        "expected_logic": "تمثیلِ روزمره با نگاشتِ درست به سازوکار",
    },
    {
        "order": 10,
        "exam_type": "feynman_synthesis",
        "text": (
            "جنبهٔ دومِ «{concept}» را — این بار از زاویهٔ «چه چیزی این پدیده "
            "را تغییر می‌دهد» — برای همان بچهٔ ۱۰ ساله توضیح بده و بگو اگر "
            "شرایط عوض شود چه اتفاقی می‌افتد."
        ),
        "difficulty": "hard",
        "cognitive_type": "combined",
        "forbidden_words": ["متغیر", "رابطه", "معادله", "محاسبه"],
        "expected_logic": "توضیحِ جهتِ تغییر بدونِ واژگانِ تخصصی",
    },
)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


MATH_SUBJECT_IDS = frozenset({
    "math-10",       # ریاضی ۱
    "geometry-10",   # هندسه ۱
    "math-11-exp",   # ریاضی ۲ تجربی
    "calculus-11",   # حسابان ۱
    "geometry-11",   # هندسه ۲
    "statistics-11", # آمار و احتمال
    "math-12-exp",   # ریاضی ۳ تجربی
    "calculus-12",   # حسابان ۲
    "geometry-12",   # هندسه ۳
    "discrete-12",   # ریاضیات گسسته
})

_MATH_KEYWORDS = ("ریاضی", "هندسه", "حسابان", "گسسته", "آمار")
_MATH_SUBJECT_SLUGS = frozenset({"math", "calculus", "geometry", "discrete", "statistics"})


def is_math_subject(subject_id: str = "", subject_name: str = "") -> bool:
    """تشخیصِ اینکه آیا درس از خانوادهٔ ریاضیات و هندسهٔ صوری است یا علوم تجربی."""
    sid = str(subject_id or "").strip().lower()
    if sid in MATH_SUBJECT_IDS or sid in _MATH_SUBJECT_SLUGS:
        return True
    sname = str(subject_name or "").strip()
    return any(kw in sname for kw in _MATH_KEYWORDS)


_MATH_BOOKLET_PROMPT = """
تو یک طراح ارشد المپیاد و کنکور سراسری ریاضیات ایران هستی.
تسک: برای مبحث «{concept}» از درس «{subject}» پایه «{grade}»، یک آزمون سنجش عمق درک ریاضی شامل دقیقاً ۱۰ سوال چهارگزینه‌ای طراحی کن.
اکیداً از پرسیدن تاریخچه علم یا سوالاتی مثل «انسان‌ها به چه بن‌بست علمی خوردند» یا تمثیلِ «توضیح برای کودک ۱۰ ساله» خودداری کن. سوالات باید بر مبنای منطق صوری، هندسه تحلیلی، جبر و تجسم فضایی باشند.

اطلاعاتِ مبحث:
- گزارهٔ کلیدی: {proposition}
- بدفهمیِ رایج: {misconception}
- خطای قبلیِ دانش‌آموز (در صورت وجود): {wrong_answer}

ساختار دقیق ۱۰ سوال (۵ ایستگاه ۲ سوالی):

۱. سوالات ۱ و ۲ (کالبدشکافی قیود و تمایز مفاهیم دوقلو):
- تفکیک دو مفهوم هندسی/ریاضی نزدیک به هم (مثلاً تفاوت کمان و زاویه مرکزی، پیوستگی و حد، شرط لازم و کافی).
- بدون محاسبات سنگین؛ تمرکز روی فرضیات و قیود قضیه (چرا فلان شرط در صورت قضیه ضروری است و با حذف آن قضیه نقض می‌شود؟).

۲. سوالات ۳ و ۴ (حل مسئله استاندارد با متغیر انحرافی یا تله محاسباتی):
- مسئله تستی تحلیلی در سطح کنکور سراسری با چهار گزینه استاندارد، شامل متغیرهای بی‌اثر یا تله‌های رایج دامنه تعریف.

۳. سوالات ۵ و ۶ (رفتار پویا، شرایط مرزی و حالت‌های حدی):
- تحلیل رفتار سیستم ریاضی در شرایط حدی (میل کردن به صفر، بی‌نهایت، انطباق دو نقطه، تماس وتر با قطر دایره، زاویه دید از بی‌نهایت).

۴. سوالات ۷ و ۸ (شکار مغالطه ریاضی و ارائه مثال نقض):
- ارائه یک استدلال یا اثبات ریاضی ظاهراً درست ولی دارای خطای پنهان منطقی، یا یافتن مثال نقض برای یک گزاره عمومی وسوسه‌انگیز اما غلط.

۵. سوالات ۹ و ۱۰ (مدل‌سازی فضایی، کاربرد واقعی و بازسازی هندسی):
- مدلسازی ملموس هندسی یا جبری در دنیای واقعی (مانند زاویه دید در ناوبری، یافتن مرکز دایره با گونیای ۹۰ درجه، بازتاب نور، بهینه‌سازی مسافت).

فقط و فقط JSON خالص برگردان (بدون Markdown یا متن اضافی) با ساختار دقیق:
{{
  "stages": [
    {{
      "order": 1,
      "stage": 1,
      "question_text": "متن شفاف، دقیق و علمی سوال...",
      "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"],
      "correct_index": 0,
      "explanation": "استدلال منطقی و حل کامل برای درستی گزینه"
    }}
  ]
}}
""".strip()


def build_booklet_prompt(
    concept,
    propositions: list[str],
    misconceptions: list[str],
    wrong_answer: dict | None = None,
) -> str:
    """پرامپتِ نهایی — با `fill`، نه `.format`."""
    wrong_text = ""
    if wrong_answer:
        wrong_text = (
            f"مسئله: {wrong_answer.get('problem_text', '')} | "
            f"پاسخِ غلطِ دانش‌آموز: {wrong_answer.get('student_answer', '')}"
        )
    subject_hint = " ".join([
        str(getattr(concept, "subject", "") or ""),
        str(getattr(concept, "topic", "") or ""),
        " ".join(str(p) for p in (propositions or [])),
    ])
    template = (
        _MATH_BOOKLET_PROMPT
        if is_math_subject(getattr(concept, "subject", ""), subject_hint)
        else _BOOKLET_PROMPT
    )
    return fill(
        template,
        concept=concept.name,
        subject=concept.subject,
        grade=concept.grade,
        proposition=propositions[0] if propositions else "گزارهٔ هدف",
        misconception=misconceptions[0] if misconceptions else "بدفهمیِ رایجِ این مفهوم",
        wrong_answer=wrong_text or "—",
    )


# ---------------------------------------------------------------------------
# نرمال‌سازیِ خروجیِ مدل
# ---------------------------------------------------------------------------
def _coerce_options(raw: Any) -> Optional[list[str]]:
    if not isinstance(raw, list):
        return None
    options = [str(x).strip() for x in raw if str(x).strip()]
    return options if len(options) >= 2 else None


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _coerce_index(raw: Any, options_count: int, *, one_based: bool = False) -> int:
    """اندیسِ گزینه را ۰-پایه و در محدودهٔ معتبر برمی‌گرداند.

    ``one_based=True`` یعنی سؤال صریحاً گفته «۱ تا ۴» — پس ۱ ⇒ اندیس ۰.
    بدونِ این پرچم، ۱ در بازهٔ ۰..۳ هم معتبر است و مبهم می‌ماند؛ تصمیمِ
    محافظه‌کارانه: مقدار را همان‌طور که آمده بپذیر.
    """
    text = str(raw).strip().translate(_DIGITS)
    try:
        value = int(text)
    except (TypeError, ValueError):
        return 0
    if one_based:
        value -= 1
    if 0 <= value < options_count:
        return value
    if value == options_count:  # مدل یک‌پایه داده (۴ برای چهار گزینه)
        return options_count - 1
    return 0


_WORD_SPLIT = re.compile(r"[,،;؛|\n]")


def _coerce_forbidden(raw: Any) -> list[str]:
    """کلماتِ ممنوعه — هم لیست، هم رشتهٔ جداشده با ویرگول را می‌پذیرد."""
    if isinstance(raw, str):
        raw = [p for p in _WORD_SPLIT.split(raw)]
    if not isinstance(raw, (list, tuple)):
        return []
    words: list[str] = []
    for item in raw:
        word = _stringify(item)
        if word and word not in words:
            words.append(word)
    return words


# ---------------------------------------------------------------------------
# گاردهای کیفیتِ متنِ سؤال — روی خروجیِ مدل، نه روی پرامپت
# ---------------------------------------------------------------------------
# پرامپت می‌تواند نادیده گرفته شود (مدل ضعیف، پاسخی که با نصفِ دستور جور است).
# این گاردها همان قواعد را روی متنِ نهایی اعمال می‌کنند تا سؤالِ بی‌کیفیت به
# دانش‌آموز نرسد. هر گارد فقط «تشخیص» می‌دهد؛ تصمیمِ اصلاح/تولیدِ مجدد
# بالاتر گرفته می‌شود.

#: تعدادِ نشانه‌های پرسشی که بیش از آن یعنی متن چند سؤالِ مستقل است.
_MAX_QUESTION_MARKS = 1

# نشانهٔ فرمولِ *واقعی*: ریاضیِ درون‌خطی، یا یک انتسابِ نمادین مثل «I=V/R».
# پیش‌تر هر عبارتی که با «فرمول/رابطه/معادله» شروع می‌شد علامت می‌خورد و
# واژهٔ سادهٔ «رابطه‌ای» در یک سؤالِ کاملاً مفهومی، سؤال را رد می‌کرد.
_FORMULA_HINT = re.compile(
    r"\$[^$]+\$"
    r"|[A-Za-z]\s*=\s*[^\s،.]"          # I=V/R ، P = VI
    r"|(?:فرمول|معادلهٔ)\s*[A-Za-z0-9۰-۹$]"   # «فرمول I» / «معادلهٔ ۲»
)
_NUMBER_HINT = re.compile(r"[0-9۰-۹]")

#: «دایره» در بافتِ الکتریکی غلط است؛ در هندسه درست است.
_CIRCUIT_CONTEXT = re.compile(
    r"مدار|جریان|مقاوم|ولتاژ|باتری|الکتر|رسانا|آمپر|اهم|سیم|لامپ|کلید\s+برق"
)
_GEOMETRY_CONTEXT = re.compile(
    r"هندسه|شعاع|قطر|محیط|مساحت|کمان|وتر|زاویه|دایرهٔ?\s*(?:واحد|مثلثی)"
)
_WRONG_TERM = re.compile(r"دایره")


def fix_terminology(text: str) -> str:
    """«دایره» را فقط در بافتِ مدارِ الکتریکی به «مدار» تبدیل می‌کند.

    جایگزینیِ سراسری عمداً انجام نمی‌شود: در هندسه «دایره» درست است و
    تغییرِ آن سؤال را خراب می‌کند. اگر متن هر دو بافت را داشت، دست نمی‌زنیم.
    """
    if not text or not _WRONG_TERM.search(text):
        return text
    if not _CIRCUIT_CONTEXT.search(text) or _GEOMETRY_CONTEXT.search(text):
        return text
    return _WRONG_TERM.sub("مدار", text)


def question_quality_issues(
    item: dict[str, Any], concept_name: str = ""
) -> list[str]:
    """ایرادهای کیفیتِ یک مرحله را برمی‌گرداند (فهرستِ خالی = سالم)."""
    issues: list[str] = []
    exam_type = item.get("exam_type")
    text = str(item.get("text") or "")
    order = item.get("order")

    if not text.strip():
        return ["empty_text"]

    # ── مرحله ۱: یک پرسش، یک هدف؛ بدونِ عدد و فرمول ──
    if exam_type == "philosophy":
        if text.count("؟") + text.count("?") > _MAX_QUESTION_MARKS:
            issues.append("philosophy_multi_question")
        if _FORMULA_HINT.search(text):
            issues.append("philosophy_has_formula")
        if _NUMBER_HINT.search(text):
            issues.append("philosophy_has_number")

    # ── مرحله ۳: زنجیرهٔ علّی، بدونِ عدد و فرمول ──
    if exam_type == "perturbation":
        if _FORMULA_HINT.search(text):
            issues.append("perturbation_has_formula")
        if _NUMBER_HINT.search(text):
            issues.append("perturbation_has_number")

    # ── مرحله ۲: چهار گزینهٔ مستقل + یک کلیدِ معتبر ──
    if exam_type == "mask_mcq":
        options = item.get("options") or []
        if not isinstance(options, list) or len(options) != 4:
            issues.append("mcq_needs_four_options")
        else:
            cleaned = [re.sub(r"\s+", " ", str(o)).strip() for o in options]
            if any(not o for o in cleaned):
                issues.append("mcq_empty_option")
            elif len({o for o in cleaned}) != 4:
                # گزینهٔ تکراری، تست را به «کدام درست است» تبدیل نمی‌کند
                issues.append("mcq_duplicate_options")
        index = item.get("correct_option_index")
        if index is None or not isinstance(index, int) or not 0 <= index <= 3:
            issues.append("mcq_missing_key")
        elif isinstance(options, list) and len(options) == 4:
            # کلید باید با محاسبهٔ مستقل از متن بخواند، نه با ادعای مدل.
            ok, reason = verify_mcq_key(text, [str(o) for o in options], index)
            if not ok and reason:
                issues.append(reason)

    # ── مرحله ۵: کلماتِ ممنوعهٔ دقیق ──
    if exam_type == "feynman_synthesis":
        words = item.get("forbidden_words") or []
        if not 4 <= len(words) <= 6:
            issues.append("feynman_forbidden_word_count")
        generic = {"علم", "چیز", "مفهوم", "موضوع", "کلمه", "سؤال"}
        if words and all(str(w).strip() in generic for w in words):
            issues.append("feynman_generic_forbidden_words")

    # ── لو رفتنِ تله یا پاسخ ──
    if leaked_phrases(text, philosophy=(exam_type == "philosophy")):
        issues.append("question_leaks_answer")

    # ── اصطلاح‌شناسی: «دایره» در بافتِ الکتریکی ──
    if "دایره" in text and (
        _CIRCUIT_CONTEXT.search(text) and not _GEOMETRY_CONTEXT.search(text)
    ):
        issues.append("wrong_terminology_daere")

    return issues


#: گاردهایی که فقط با تولیدِ مجدد یا قالبِ قطعی حل می‌شوند (اصلاحِ متن ممکن نیست).
#: عبارت‌هایی که تلهٔ مرحله ۲ یا پاسخِ مرحله ۱ را لو می‌دهند.
#: اگر در متنِ سؤال بیایند، سنجش بی‌اثر می‌شود — نه «کیفیتِ پایین»، بلکه
#: «سنجشِ نامعتبر». پس در گاردِ کشنده می‌نشینند و سؤال دور ریخته می‌شود.
LEAKY_PHRASES: tuple[str, ...] = (
    "هیچ نقشی",
    "هیچ تأثیری",
    "بی‌تأثیر",
    "بی اثر",
    "برای گمراه",
    "گمراه کردن",
    "نه ویژگی منبع",
    "ویژگی منبع تغذیه نیست",
    "ناچیز و بی‌اثر",
    "ناچیز و بی اثر",
    "در محاسبه به کار نمی‌رود",
    "در محاسبه نقشی ندارد",
    "ربطی به جواب ندارد",
)

#: پاسخ‌های لو‌دهنده در صورتِ سؤالِ مرحله ۱.
ANSWER_LEAKS: tuple[str, ...] = (
    "نه ویژگی منبع",
    "به ولتاژ بستگی ندارد",
    "مستقل از ولتاژ",
    "ویژگی ذاتی رسانا",
    "خودش را تنظیم نمی‌کند",
)


def leaked_phrases(text: str, *, philosophy: bool = False) -> list[str]:
    """عبارت‌های لو‌دهندهٔ موجود در متن را برمی‌گرداند."""
    body = str(text or "")
    found = [p for p in LEAKY_PHRASES if p in body]
    if philosophy:
        found += [p for p in ANSWER_LEAKS if p in body]
    return found


FATAL_QUALITY_ISSUES = frozenset(
    {
        "empty_text",
        "mcq_needs_four_options",
        "mcq_empty_option",
        "mcq_duplicate_options",
        "mcq_missing_key",
        # سؤالی که تله یا پاسخش را لو می‌دهد، سنجش را بی‌اعتبار می‌کند.
        "question_leaks_answer",
        # کلیدِ نادرست یا گزینهٔ تکراری، درست‌زدنِ دانش‌آموز را نادرست ثبت می‌کند.
        "mcq_key_mismatch",
        "mcq_key_duplicated",
    }
)


def apply_quality_fixes(item: dict[str, Any]) -> dict[str, Any]:
    """اصلاح‌های ایمن و موضعی؛ هیچ‌کدام محتوای علمی را بازنویسی نمی‌کند."""
    for key in ("text", "expected_logic", "stage_title"):
        if isinstance(item.get(key), str):
            item[key] = fix_terminology(item[key])
    if isinstance(item.get("options"), list):
        item["options"] = [
            fix_terminology(str(o)) if isinstance(o, str) else o
            for o in item["options"]
        ]
    if isinstance(item.get("forbidden_words"), list):
        item["forbidden_words"] = [
            fix_terminology(str(w)) for w in item["forbidden_words"]
        ]
    return item


# ---------------------------------------------------------------------------
# اعتبارسنجیِ کلیدِ تست — تطبیقِ گزینهٔ صحیح با محاسبهٔ واقعی
# ---------------------------------------------------------------------------
# مدل کلید را «اعلام» می‌کند، ولی هیچ‌کس آن را حساب نمی‌کند. یک کلیدِ غلط
# بدترین نوع خرابی است: دانش‌آموزِ درست را نادرست ثبت می‌کند. این‌جا برای
# سؤال‌هایی که یک محاسبهٔ سادهٔ دو-کمیتی دارند، عدد از خودِ متن حساب می‌شود و
# با گزینهٔ کلید مقایسه می‌گردد.

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

#: عددِ داخلِ متن، با پشتیبانی از ارقامِ فارسی و اعشارِ «٫/».
_NUM = r"[0-9۰-۹]+(?:[./][0-9۰-۹]+)?"
# اعراب و کشیده بینِ واژه و عدد می‌نشینند («مقاومتِ ۴»)؛ باید نادیده گرفته شوند.
_DIACRITICS = "[\u064B-\u0652\u0640\u200c]?"
_OHM_PATTERN = re.compile(
    rf"(?:ولتاژ|اختلاف{_DIACRITICS}\s*پتانسیل|V)\s*{_DIACRITICS}\s*"
    rf"(?:برابر{_DIACRITICS}?|=\s*)?\s*({_NUM})\s*"
    rf"(?:ولت|V)?"
    rf"[\s،,؛;.:]*?"
    rf"(?:و\s*)?(?:مقاومت|R)\s*{_DIACRITICS}\s*"
    rf"(?:برابر{_DIACRITICS}?|=\s*)?\s*({_NUM})\s*(?:اهم|Ω|ohm)?",
    re.IGNORECASE,
)


def _to_float(token: str) -> Optional[float]:
    text = str(token or "").strip().translate(_FA_DIGITS).replace("٫", ".").replace("/", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _option_numbers(options: list[str]) -> list[Optional[float]]:
    """عددِ اصلیِ هر گزینه (اولین عددی که در متنش آمده)."""
    out: list[Optional[float]] = []
    for option in options:
        match = re.search(_NUM, str(option or "").translate(_FA_DIGITS))
        out.append(_to_float(match.group(0)) if match else None)
    return out


def verify_mcq_key(
    text: str, options: list[str], correct_index: Optional[int]
) -> tuple[bool, Optional[str]]:
    """آیا گزینهٔ کلید با محاسبهٔ مستقل از متن می‌خواند؟

    برمی‌گرداند ``(ok, reason)``. ``ok=False`` یعنی سؤال باید رد شود.
    اگر سؤال محاسبهٔ قابلِ‌بازسازی نداشته باشد (مفهومی محض)، ``(True, None)``
    برمی‌گردد — این تابع فقط وقتی حکم می‌دهد که بتواند خودش حساب کند.
    """
    opts = [str(o or "") for o in (options or [])]
    if len(opts) != 4:
        return False, "mcq_needs_four_options"
    if correct_index is None or not (0 <= int(correct_index) < 4):
        return False, "mcq_missing_key"

    key_number = _option_numbers(opts)[int(correct_index)]
    if key_number is None:
        return True, None  # گزینهٔ کلید عددی نیست ⇒ محاسبهٔ عددی در کار نیست

    # قانون اهم: I = V / R
    match = _OHM_PATTERN.search(str(text or "").translate(_FA_DIGITS))
    if not match:
        return True, None
    voltage = _to_float(match.group(1))
    resistance = _to_float(match.group(2))
    if not voltage or not resistance or resistance == 0:
        return True, None

    expected = voltage / resistance
    tolerance = max(abs(expected) * 0.02, 0.01)
    if abs(key_number - expected) > tolerance:
        return False, "mcq_key_mismatch"
    # هیچ گزینهٔ غلطی نباید با کلید برابر باشد
    for index, value in enumerate(_option_numbers(opts)):
        if index == int(correct_index) or value is None:
            continue
        if abs(value - key_number) <= tolerance:
            return False, "mcq_key_duplicated"
    return True, None


def normalize_stage_items(items: Any) -> list[dict[str, Any]]:
    """خروجیِ خامِ مدل را به **۱۰ سؤالِ قطعی** (دو سؤال در هر مرحله) تبدیل می‌کند.

    مقاوم در برابرِ انحراف‌های رایج: بی‌ترتیبی، type اشتباه، گزینهٔ کم،
    ایندکسِ یک‌پایه، forbidden_words غایب، و — مهم‌تر از همه — مدلی که فقط
    ۵ سؤال می‌دهد (یک سؤال در هر مرحله). در آن حالت هر سؤال در اسلاتِ اولِ
    مرحلهٔ خودش می‌نشیند و اسلاتِ دوم با ``None`` می‌ماند تا لایهٔ بالاتر
    جای خالی را از قالبِ اضطراری پر کند.
    """
    if isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list):
        return []

    #: اسلات‌ها به ترتیبِ order (۰..۹). هر مرحله ``QUESTIONS_PER_STAGE`` اسلات دارد.
    slots: list[Optional[dict]] = [None] * TOTAL_QUESTIONS
    #: آیتم‌های بی‌نوع/بی‌ترتیب که بعداً در اسلات‌های خالی می‌نشینند.
    spare: list[dict] = []
    #: شمارندهٔ پرشدنِ هر مرحله — برای وقتی مدل order درست نداده باشد.
    stage_fill: dict[str, int] = {t: 0 for t in STAGE_ORDER}

    for position, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        exam_type = _stringify(raw.get("exam_type") or raw.get("type")).lower()
        if exam_type not in STAGE_ORDER:
            # آیتمِ بی‌نوع: فقط وقتی به کار می‌آید که اسلاتِ خالی بماند.
            spare.append(raw)
            continue

        order = raw.get("order")
        try:
            order_num = int(order) if order is not None else 0
        except (TypeError, ValueError):
            order_num = 0

        slot: Optional[int] = None
        # ۱) اگر order صریح و در محدودهٔ همین مرحله است، همان اسلات.
        if 1 <= order_num <= TOTAL_QUESTIONS and stage_key(order_num) == exam_type:
            if slots[order_num - 1] is None:
                slot = order_num - 1
        # ۲) وگرنه اولین اسلاتِ خالیِ همین مرحله (ترتیبِ ورود حفظ می‌شود).
        if slot is None:
            base = STAGE_ORDER.index(exam_type) * QUESTIONS_PER_STAGE
            for candidate in range(base, base + QUESTIONS_PER_STAGE):
                if slots[candidate] is None:
                    slot = candidate
                    break

        if slot is not None:
            slots[slot] = raw
            stage_fill[exam_type] += 1
        # سؤالِ سومِ یک مرحله (مدل بیشتر از دو تا داده) دور ریخته می‌شود؛
        # نباید جای مرحلهٔ دیگری را بگیرد و برچسبِ اشتباه بخورد.

    for slot, value in enumerate(slots):
        if value is None and spare:
            slots[slot] = spare.pop(0)

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(slots):
        if not isinstance(raw, dict):
            continue
        order = index + 1
        exam_type = stage_key(order)
        stage = stage_of_order(order)
        text = _stringify(raw.get("text") or raw.get("question_text"))
        if not text:
            continue

        item: dict[str, Any] = {
            "order": order,
            "stage": stage,
            "stage_slot": (order - 1) % QUESTIONS_PER_STAGE + 1,
            "exam_type": exam_type,
            "stage_title": _stringify(raw.get("stage_title")) or STAGE_TITLES[exam_type],
            "text": text,
            "difficulty": _stringify(raw.get("difficulty")).lower() or "medium",
            "cognitive_type": _stringify(raw.get("cognitive_type")).lower() or "conceptual",
            "options": None,
            "correct_option_index": None,
            "forbidden_words": _coerce_forbidden(raw.get("forbidden_words")),
            "expected_logic": _stringify(raw.get("expected_logic")),
            "mapped_propositions": [
                p for p in (raw.get("mapped_propositions") or []) if isinstance(p, str) and p.strip()
            ],
        }
        if item["difficulty"] not in {"easy", "medium", "hard"}:
            item["difficulty"] = "medium"
        if item["cognitive_type"] not in {"recall", "conceptual", "computational", "combined"}:
            item["cognitive_type"] = "conceptual"

        if exam_type == "mask_mcq":
            options = _coerce_options(raw.get("options"))
            if options:
                item["options"] = options[:4]
                # پرامپت صریحاً می‌گوید «۰ تا ۳ — از ۰ شروع می‌شود»، پس ایندکسِ
                # مدل صفرمبناست. پیش‌تر این‌جا one_based=True بود و هر کلید یک
                # واحد جابه‌جا می‌شد: گزینهٔ «۳ آمپر» (اندیس ۱) به «۰/۳۳»
                # (اندیس ۰) تبدیل می‌شد و سؤالِ درست هم رد می‌شد.
                item["correct_option_index"] = _coerce_index(
                    raw.get("correct_option_index"), len(item["options"])
                )
        elif exam_type == "feynman_synthesis" and len(item["forbidden_words"]) < 3:
            item["forbidden_words"] = ["فرمول", "قانون", "تعریف", "اصطلاح"]

        normalized.append(apply_quality_fixes(item))

    return normalized


def fallback_stages(concept) -> list[dict[str, Any]]:
    """ده سؤالِ اضطراریِ کامل — هرگز آزمونِ ناقص به دانش‌آموز نمی‌رسد."""
    out: list[dict[str, Any]] = []
    for template in _FALLBACK_STAGES:
        item = dict(template)
        item["text"] = fill(item["text"], concept=concept.name)
        item["stage_title"] = STAGE_TITLES[item["exam_type"]]
        item["stage"] = stage_of_order(int(item.get("order") or 0))
        item["stage_slot"] = (int(item.get("order") or 1) - 1) % QUESTIONS_PER_STAGE + 1
        item.setdefault("options", None)
        item.setdefault("correct_option_index", None)
        item.setdefault("forbidden_words", [])
        item.setdefault("expected_logic", "")
        item.setdefault("mapped_propositions", [])
        out.append(item)
    return out


def fallback_item_for_order(concept, order: int) -> Optional[dict[str, Any]]:
    """قالبِ اضطراریِ همان ترتیب — برای پر کردنِ یک اسلاتِ خالی."""
    for template in _FALLBACK_STAGES:
        if int(template.get("order") or 0) == int(order):
            item = dict(template)
            item["text"] = fill(item["text"], concept=concept.name)
            item["stage_title"] = STAGE_TITLES[item["exam_type"]]
            item["stage"] = stage_of_order(order)
            item["stage_slot"] = (order - 1) % QUESTIONS_PER_STAGE + 1
            item.setdefault("options", None)
            item.setdefault("correct_option_index", None)
            item.setdefault("forbidden_words", [])
            item.setdefault("expected_logic", "")
            item.setdefault("mapped_propositions", [])
            return item
    return None


def items_to_questions(concept, items: list[dict[str, Any]], model_name: str, cost: float) -> list:
    """آیتم‌های پنج‌گانه را به ردیف‌های ``Question`` تبدیل می‌کند.

    اطلاعاتِ اختصاصیِ هر مرحله داخلِ ستونِ JSONِ ``rubric`` می‌رود تا نیازی
    به تغییرِ ستون‌های جدول نباشد.
    """
    from ai.question_generator import _sanitize_diagram_svg
    from models.question import Question

    propositions = [_stringify(p) for p in (getattr(concept, "core_propositions", None) or [])]
    propositions = [p for p in propositions if p]
    fallback_prop = propositions[0] if propositions else "گزارهٔ هدف"

    rows: list[Question] = []
    for item in items:
        exam_type = item["exam_type"]
        text = item["text"]
        diagram_svg = _sanitize_diagram_svg(item.get("diagram_svg"))
        mapped = item.get("mapped_propositions") or [fallback_prop]

        rubric = {
            "exam_type": exam_type,
            # مرحله و اسلاتِ داخلِ مرحله — برای جمع‌بندیِ دو سؤالی
            "stage": item.get("stage") or stage_of_order(int(item.get("order") or 0)),
            "stage_slot": item.get("stage_slot")
            or ((int(item.get("order") or 1) - 1) % QUESTIONS_PER_STAGE + 1),
            "stage_title": item.get("stage_title") or STAGE_TITLES[exam_type],
            "options": item.get("options") if exam_type == "mask_mcq" else None,
            "correct_option_index": item.get("correct_option_index") if exam_type == "mask_mcq" else None,
            "forbidden_words": item.get("forbidden_words") or [],
            "expected_logic": item.get("expected_logic") or "",
            "diagram_svg": diagram_svg,
        }
        rows.append(
            Question(
                concept_id=getattr(concept, "id", None),
                text=text,
                question_type=exam_type,
                difficulty=item.get("difficulty") or "medium",
                cognitive_type=item.get("cognitive_type") or "conceptual",
                rubric=rubric,
                mapped_propositions=mapped,
                mapped_misconceptions=[],
                source="ai_generated",
                approval_status="pending",
                ai_model_used=model_name,
                generation_cost_usd=cost,
            )
        )
    return rows


async def generate_stage_chain(
    concept, wrong_answer: dict | None = None
) -> tuple[list[Any], str, float]:
    """زنجیرهٔ ۱۰ سؤالی (۵ مرحله × ۲) را در **یک درخواست** تولید می‌کند.

    اصولِ فاز ۱۱:
      • **یک Request واحد** — شناسنامهٔ مفهوم و هر ده سؤال با هم خواسته
        می‌شوند تا هزینهٔ توکن و تأخیر کم شود.
      • **کش** بر اساسِ کلیدِ مفهومی (نام/درس/پایه + بدفهمی) — مبحثِ تکراری
        دوباره از مدل پرسیده نمی‌شود.
      • اگر هیچ تلاشی ده سؤالِ سالم نداد، آزمونِ **ناقص** تحویل نمی‌شود:
        اسلات‌های خالی با قالبِ قطعیِ همان ترتیب پر می‌شوند.
    """
    propositions = [_stringify(p) for p in (getattr(concept, "core_propositions", None) or [])]
    propositions = [p for p in propositions if p]
    misconceptions = [_stringify(m) for m in (getattr(concept, "common_misconceptions", None) or [])]
    misconceptions = [m for m in misconceptions if m]

    # ── کش: مبحثِ تکراری دوباره تولید نمی‌شود ──
    cache_key = booklet_cache_key(concept, wrong_answer)
    cached = get_cached_booklet(cache_key)
    if cached is not None:
        items, cached_model, cached_cost = cached
        print(
            f"[StageChain] cache hit for {cache_key[:12]}… "
            f"({len(items)} questions, model={cached_model})"
        )
        return (
            items_to_questions(concept, items, cached_model, 0.0),
            cached_model,
            0.0,  # هزینهٔ این آزمون صفر است؛ تولید قبلاً هزینه شده
        )

    prompt = build_booklet_prompt(concept, propositions, misconceptions, wrong_answer)
    router = get_router()

    model_name, cost = "", 0.0
    best_items: list[dict[str, Any]] = []

    for attempt in range(3):
        try:
            resp = await router.generate(prompt, "generate_test_booklet", temperature=0.7)
            model_name, cost = resp.model_name, resp.total_cost_usd
            data = extract_json_object(resp.text)
            items = normalize_stage_items(
                (data or {}).get("questions") if isinstance(data, dict) else None
            )
            # سؤالی که ایرادِ کشنده دارد (مثلاً MCQ با سه گزینه) حذف می‌شود تا
            # جایش با قالبِ قطعیِ همان ترتیب پر شود؛ سؤالِ بی‌کیفیت تحویل نمی‌شود.
            kept: list[dict[str, Any]] = []
            for candidate in items:
                issues = question_quality_issues(candidate, concept.name)
                fatal = [i for i in issues if i in FATAL_QUALITY_ISSUES]
                if fatal:
                    print(
                        f"[StageChain] Q{candidate.get('order')} rejected: {fatal}"
                    )
                    continue
                if issues:
                    print(
                        f"[StageChain] Q{candidate.get('order')} quality notes: {issues}"
                    )
                kept.append(candidate)
            items = kept
            # معیارِ پذیرش: هر پنج مرحله دست‌کم یک سؤالِ سالم داشته باشند و
            # هر دو MCQ موجود باشند. ده سؤالِ کامل بهتر است ولی هفت/هشت سؤالِ
            # سالم هم بهتر از دور ریختنِ کلِ خروجی و برگشت به قالب است.
            covered = {stage_of_order(int(i.get("order") or 0)) for i in items}
            mcq_count = sum(
                1 for i in items if i["exam_type"] == "mask_mcq" and i["options"]
            )
            if len(covered) >= len(STAGE_ORDER) and mcq_count >= 1:
                if len(items) > len(best_items):
                    best_items = items
                if len(items) == TOTAL_QUESTIONS:
                    break
            print(
                f"[StageChain] attempt {attempt + 1}/3 gave {len(items)} usable "
                f"questions across {len(covered)}/{len(STAGE_ORDER)} stages "
                f"(model={resp.model_name})"
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            print(f"[StageChain] attempt {attempt + 1}/3 failed: {message[:200]}")
            # ۴۲۹ یعنی سرویس‌دهنده سیر است. تلاشِ بعدی فقط کاربر را معطل می‌کند.
            # توجه: این «بازگشت به قالبِ قطعی» است، نه سوییچ به مدلِ دیگر.
            if "429" in message or "rate-limited" in message:
                print("[StageChain] upstream rate limit — deterministic chain instead of retrying")
                break

    # ── پر کردنِ اسلات‌های خالی با قالبِ قطعیِ همان ترتیب ──
    by_order = {int(i.get("order") or 0): i for i in best_items}
    merged: list[dict[str, Any]] = []
    filled = 0
    for order in range(1, TOTAL_QUESTIONS + 1):
        existing = by_order.get(order)
        if existing is not None:
            merged.append(existing)
            continue
        template = fallback_item_for_order(concept, order)
        if template is not None:
            merged.append(template)
            filled += 1
    if filled:
        print(
            f"[StageChain] {filled} question(s) filled from the deterministic "
            "template bank (no partial exam is delivered)"
        )
        model_name = model_name or "template-fallback"

    best_items = merged
    if not model_name:
        model_name = "template-fallback"

    # کش فقط برای خروجیِ قابلِ‌اتکا (نه وقتی همه‌چیز از قالب آمده) تا قالبِ
    # اضطراری به‌عنوان «تولیدِ موفق» برای آزمون‌های بعدی تکرار نشود.
    if any(int(i.get("order") or 0) and i.get("expected_logic") for i in best_items):
        put_cached_booklet(cache_key, best_items, model_name, cost)

    return (
        items_to_questions(concept, best_items, model_name, cost),
        model_name,
        cost,
    )
