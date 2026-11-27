"""پلِ درختِ برنامهٔ درسی (فرانت) و بانکِ مفاهیم (بک‌اند).

── مسئله ──
فرانت حالا درختِ کاملِ کتاب‌های دبیرستان را دارد (۲۶۳ مفهوم). ولی بانکِ
مفاهیمِ دیتابیس فقط ۱۶ ردیف است و ``/api/assess/start`` فقط ``concept_id``
عددی می‌پذیرد. اگر دانش‌آموز مفهومی مثل «قضیه کار و انرژی جنبشی» انتخاب کند
که در بانک نیست، آزمون شروع نمی‌شود — یعنی درختِ کامل بی‌فایده است.

── راه‌حل ──
فرانت علاوه بر ``concept_id``، یک آبجکتِ ``curriculum`` می‌فرستد که عنوانِ
درس/فصل/مفهوم و رشته و پایه را دارد. این ماژول:

  ۱. اگر ``concept_id`` معتبر بود، همان را برمی‌گرداند (مسیرِ سریع، بی‌تغییر).
  ۲. وگرنه در بانک با (subject, grade, name) جست‌وجو می‌کند.
  ۳. وگرنه یک ردیفِ تازه با گزاره‌های اصلیِ **مشتق‌شده از عنوانِ فصل** می‌سازد.

نکتهٔ مهم: گزاره‌های ساخته‌شده **ساختگی نیستند** — از عنوانِ رسمیِ فصل و
مفهوم می‌آیند و به‌صراحت با ``source="curriculum"`` علامت می‌خورند تا معلوم
باشد از بانکِ دست‌ساز نیامده‌اند.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from models.concept import Concept

# رشته‌های درخت → فیلدِ ``subject`` در دیتابیس (فقط وقتی درسِ دقیق معلوم نباشد)
_MAJOR_TO_SUBJECT = {
    "experimental": "experimental",
    "mathematics": "mathematics",
    # سازگاری با ردیف‌های قدیمیِ بانک
    "physics": "physics",
    "chemistry": "chemistry",
    "math": "math",
}

_SUBJECT_ID_PREFIX_TO_SLUG = (
    ("physics", "physics"),
    ("phy", "physics"),
    ("chemistry", "chemistry"),
    ("chem", "chemistry"),
    ("biology", "biology"),
    ("bio", "biology"),
    ("calculus", "calculus"),
    ("calc", "calculus"),
    ("geometry", "geometry"),
    ("geom", "geometry"),
    ("discrete", "discrete"),
    ("disc", "discrete"),
    ("statistics", "statistics"),
    ("stat", "statistics"),
    ("math", "math"),
)

_BOOK_TITLE_TO_FA = (
    ("فیزیک", "فیزیک"),
    ("شیمی", "شیمی"),
    ("زیست", "زیست‌شناسی"),
    ("حسابان", "حسابان"),
    ("هندسه", "هندسه"),
    ("گسسته", "ریاضیات گسسته"),
    ("آمار", "آمار و احتمال"),
    ("ریاضی", "ریاضی"),
)


def _subject_slug_from_curriculum(curriculum: dict[str, Any], fallback: str) -> str:
    """درسِ واقعی را از ``subjectId`` یا ``subjectTitle`` استخراج می‌کند."""
    subject_id = str(curriculum.get("subjectId") or "").strip().lower()
    for prefix, slug in _SUBJECT_ID_PREFIX_TO_SLUG:
        if subject_id.startswith(prefix):
            return slug

    subject_title = str(curriculum.get("subjectTitle") or "").strip()
    for keyword, _fa in _BOOK_TITLE_TO_FA:
        if keyword in subject_title:
            if keyword == "فیزیک":
                return "physics"
            if keyword == "شیمی":
                return "chemistry"
            if keyword == "زیست":
                return "biology"
            if keyword == "حسابان":
                return "calculus"
            if keyword == "هندسه":
                return "geometry"
            if keyword == "گسسته":
                return "discrete"
            if keyword == "آمار":
                return "statistics"
            if keyword == "ریاضی":
                return "math"
    return fallback


def resolve_subject_display(concept: Optional[Concept]) -> Optional[str]:
    """نامِ واقعیِ درس را برای نمایش برمی‌گرداند.

    اگر ``concept.subject`` نامِ رشته باشد (``mathematics`` یا ``experimental``)،
    از روی ``core_propositions`` (عنوانِ کتاب) یا ``topic`` درسِ واقعی را
    تشخیص می‌دهد تا مثلاً «شیمی» یا «فیزیک» به جای «ریاضی» نمایش داده نشود.
    """
    if concept is None:
        return None
    raw = str(concept.subject or "").strip()
    if raw not in ("mathematics", "experimental"):
        return raw or None

    # ۱. جست‌وجو در گزارهٔ «جایگاهِ این مفهوم در کتابِ ...»
    props = concept.core_propositions or []
    joined = " ".join(str(p) for p in props)
    for keyword, fa_label in _BOOK_TITLE_TO_FA:
        if keyword in joined:
            return fa_label

    # ۲. جست‌وجو در پیشوندِ topic (مثل phy10-..., chem10-..., bio11-...)
    topic = str(concept.topic or "").strip().lower()
    for prefix, slug in _SUBJECT_ID_PREFIX_TO_SLUG:
        if topic.startswith(prefix):
            return slug

    return raw


def _slug(text: str) -> str:
    """کلیدِ انگلیسیِ پایدار از عنوانِ فارسی — فقط برای یکتا بودن."""
    return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-")[:80] or "concept"


def _propositions_from(curriculum: dict[str, Any]) -> list[str]:
    """گزاره‌های اصلی از روی عنوان‌های رسمیِ فصل و مفهوم.

    این «دادهٔ ساختگی» نیست: هر گزاره دقیقاً همان چیزی است که عنوانِ کتاب
    می‌گوید، و هدفش لنگر انداختنِ سؤال‌ساز به مفهومِ درست است، نه ادعای
    محتوای آموزشیِ تازه.
    """
    concept_title = str(curriculum.get("conceptTitle") or "").strip()
    chapter_title = str(curriculum.get("chapterTitle") or "").strip()
    subject_title = str(curriculum.get("subjectTitle") or "").strip()
    props: list[str] = []
    if concept_title:
        props.append(concept_title)
    if chapter_title:
        # «فصل ۲: کار، انرژی و توان» → «کار، انرژی و توان»
        clean = chapter_title.split(":", 1)[-1].strip()
        if clean and clean != concept_title:
            props.append(f"{concept_title} در بسترِ «{clean}»" if concept_title else clean)
    if subject_title and subject_title not in " ".join(props):
        props.append(f"جایگاهِ این مفهوم در کتابِ {subject_title}")
    return props[:4]


def resolve_concept(
    db: Session,
    concept_id: Optional[int],
    curriculum: Optional[dict[str, Any]],
) -> Concept:
    """مفهومِ قابلِ استفاده برای شروعِ آزمون را برمی‌گرداند.

    ترتیبِ اولویت:
      ۱. ``concept_id`` معتبر — هیچ تغییری در رفتارِ فعلی.
      ۲. تطبیقِ دقیقِ (subject, grade, name) در بانک.
      ۳. ساختِ ردیفِ تازه از درختِ برنامهٔ درسی.

    @raises ValueError: وقتی هیچ‌کدام از دو ورودی معتبر نباشد.
    """
    # ۱. مسیرِ سریع — همان رفتارِ قبلی
    if concept_id:
        found = db.query(Concept).filter(Concept.id == concept_id).first()
        if found is not None:
            return found

    if not curriculum:
        raise ValueError("مفهومِ مورد نظر یافت نشد.")

    concept_title = str(curriculum.get("conceptTitle") or "").strip()
    if not concept_title:
        raise ValueError("عنوانِ مفهوم در درخواست خالی است.")

    major = str(curriculum.get("major") or "").strip()
    major_fallback = _MAJOR_TO_SUBJECT.get(major, "experimental")
    subject_field = _subject_slug_from_curriculum(curriculum, major_fallback)
    try:
        grade = int(str(curriculum.get("grade") or "10"))
    except ValueError:
        grade = 10
    chapter_title = str(curriculum.get("chapterTitle") or "").strip()
    subject_title = str(curriculum.get("subjectTitle") or "").strip()

    # ۲. تطبیقِ موجود — با کلیدِ درخت یا با عنوان
    #
    # نکتهٔ مهم: فیلترِ ``subject`` اول امتحان می‌شود، ولی اگر نگرفت **بدونِ**
    # آن هم جست‌وجو می‌کنیم. دلیل: ۱۶ ردیفِ قدیمیِ بانک با
    # ``physics``/``chemistry``/``math`` ذخیره شده‌اند، در حالی که درخت کلیدِ
    # ``experimental``/``mathematics`` می‌سازد. بدونِ این fallback، «عدد اکسایش»
    # که از قبل در بانک هست، دوباره ساخته می‌شد و دو ردیفِ هم‌نام با منبعِ
    # متفاوت پیدا می‌کردیم — یعنی گزارش‌ها روی دو مفهومِ جدا جمع نمی‌شدند.
    existing = (
        db.query(Concept)
        .filter(
            Concept.subject == subject_field,
            Concept.grade == grade,
            Concept.name == concept_title,
        )
        .first()
    )
    if existing is None:
        existing = (
            db.query(Concept)
            .filter(Concept.grade == grade, Concept.name == concept_title)
            .first()
        )
    if existing is not None:
        return existing

    # ۳. ساختِ ردیفِ تازه از درخت
    topic_key = str(curriculum.get("conceptId") or "").strip() or _slug(concept_title)
    # یکتاییِ (subject, topic) تضمین‌شده است؛ اگر برخورد کرد، پسوند می‌گیرد
    clash = db.query(Concept).filter(Concept.subject == subject_field, Concept.topic == topic_key).first()
    if clash is not None:
        topic_key = f"{topic_key}-{grade}"

    concept = Concept(
        subject=subject_field,
        grade=grade,
        chapter=chapter_title,
        topic=topic_key,
        name=concept_title,
        core_propositions=_propositions_from(curriculum),
        # بدفهمی را از خودمان نمی‌سازیم — خالی می‌ماند تا سؤال‌ساز خودش
        # بر اساسِ متنِ کتاب پیشنهاد بدهد.
        common_misconceptions=[],
        target_behaviors=["explain", "apply_novel", "identify_error"],
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)

    # نشانه‌گذاریِ منبع — روی خودِ مدل فیلدِ جدا ندارد، پس در log می‌نویسیم
    concept._from_curriculum = True  # type: ignore[attr-defined]
    return concept


def is_from_curriculum(concept: Concept) -> bool:
    """آیا این مفهوم از درختِ برنامهٔ درسی ساخته شده (نه از بانکِ دست‌ساز)؟"""
    return bool(getattr(concept, "_from_curriculum", False))
