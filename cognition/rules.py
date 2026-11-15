"""چهار قانونِ شناختی — اجرای قطعیِ همان قواعدی که به مدل هم سپرده شده‌اند.

**چرا در کد هم اجرا می‌شوند؟** چون مدل ممکن است تناقضی را که خودش دیده
نادیده بگیرد، یا برعکس تناقضی بسازد که در داده نیست. قواعدِ زیر ارزان،
قطعی و قابلِ آزمون‌اند؛ خروجی‌شان به‌عنوانِ *شاهد* به مدل داده می‌شود و
همچنین به‌عنوانِ تورِ ایمنی روی حکمِ نهایی اعمال می‌شود.

قانون ۱ — تضادِ نقاب و شهود:  پاسخِ درستِ تستِ Q2 اما نقضِ همان در Q5.
قانون ۲ — حاکمیتِ عیب‌یابی:    Q3 و Q4 قوی ⇒ حکم نباید «نفهمیده» باشد.
قانون ۳ — اعتیاد به ادبیات:    استفاده از کلماتِ ممنوعه در Q5.
قانون ۴ — بی‌دقتی/کج‌فهمی:    تشریحیِ درست + تستِ متضاد ⇒ بازپرسی.
"""
from __future__ import annotations

import re
from typing import Any, Optional

RULE_LABELS = {
    1: "تضادِ نقاب و شهود",
    2: "حاکمیتِ عیب‌یابی",
    3: "اعتیاد به ادبیاتِ کتاب",
    4: "بی‌دقتی در برابر کج‌فهمی",
}


# ---------------------------------------------------------------------------
# کمکی‌های متنی
# ---------------------------------------------------------------------------
_CHAR_MAP = str.maketrans({
    "ي": "ی",
    "ك": "ک",
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ة": "ه",
    "ؤ": "و",
})


def _normalize(text: str) -> str:
    """یکسان‌سازیِ نویسه‌های عربی/فارسی و حذفِ اعراب برای تطبیقِ مطمئن."""
    s = (text or "").translate(_CHAR_MAP)
    s = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", s)  # اعراب و کشیده
    s = s.replace("\u200c", " ")  # نیم‌فاصله → فاصله
    return re.sub(r"\s+", " ", s).strip()


def _word_present(word: str, text: str) -> bool:
    """آیا کلمه در متن آمده؟ با مرزِ کلمه تا «حد» داخلِ «حدس» شمرده نشود."""
    w = _normalize(word)
    if not w:
        return False
    t = _normalize(text)
    # کلماتِ چندبخشی و ترکیبی را هم بگیر
    pattern = r"(?<![\wآ-ی])" + re.escape(w) + r"(?![\wآ-ی])"
    return re.search(pattern, t) is not None


# ---------------------------------------------------------------------------
# قانون ۳ — نقضِ کلماتِ ممنوعه
# ---------------------------------------------------------------------------
def find_forbidden_words(answer: str, forbidden: list[str]) -> list[str]:
    """کلماتِ ممنوعه‌ای که دانش‌آموز در پاسخش به کار برده است."""
    return [w for w in (forbidden or []) if _word_present(w, answer)]


def detect_jargon_violation(answers: dict[int, str], questions: list[dict[str, Any]]) -> dict[str, Any]:
    """قانون ۳ — آیا در سؤالِ فاینمن از کلماتِ ممنوعه استفاده شده؟
    """
    q5 = _question(questions, 5) or {}
    forbidden = list(q5.get("forbidden_words") or [])
    answer = answers.get(5, "")
    hits = find_forbidden_words(answer, forbidden)
    return {
        "rule": 3,
        "violated": bool(hits),
        "hits": hits,
        "forbidden": forbidden,
        "word_count": len(_normalize(answer).split()) if answer else 0,
    }


# ---------------------------------------------------------------------------
# کمکی‌های ساختاری
# ---------------------------------------------------------------------------
def _question(questions: list[dict[str, Any]], qid: int) -> Optional[dict[str, Any]]:
    for q in questions or []:
        if int(q.get("id") or 0) == qid:
            return q
    return None


def _is_answered(answers: dict[int, str], qid: int) -> bool:
    return bool(_normalize(answers.get(qid, "")))


def _chosen_option(answers: dict[int, str], q2: dict[str, Any]) -> Optional[int]:
    """اندیسِ گزینه‌ای که کاربر انتخاب کرده.

    **قرارداد:** فرانت‌اند *متنِ گزینه* را می‌فرستد، نه شمارهٔ آن. دلیلش این
    است که عددِ خالی ذاتاً مبهم است: «۲» می‌تواند گزینهٔ دوم (شمارشِ انسانی)
    یا گزینهٔ سوم (اندیسِ صفرپایه) باشد، و همین ابهام یک بار باعث شد آزمونِ
    درست، «نادرست» شمرده شود.

    اگر ورودی عدد بود (کلاینتِ قدیمی یا تستِ دستی)، **یک‌پایه** تفسیر می‌شود،
    چون گزینه‌ها در UI از ۱ تا ۴ شماره می‌خورند.
    """
    raw = answers.get(2, "")
    if raw is None or raw == "":
        return None
    options = q2.get("options") or []
    text = _normalize(str(raw))

    for index, option in enumerate(options):
        if _normalize(option) == text:
            return index

    stripped = str(raw).strip()
    if stripped.isdigit():
        value = int(stripped)
        if 1 <= value <= len(options):
            return value - 1
    return None


def _looks_substantive(answer: str, min_words: int = 8) -> bool:
    return len(_normalize(answer).split()) >= min_words


# ---------------------------------------------------------------------------
# قانون ۱ — تضادِ نقاب و شهود (Q2 در برابر Q5)
# ---------------------------------------------------------------------------
def detect_mask_intuition_conflict(
    answers: dict[int, str], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """آیا در تست درست پاسخ داد اما در توضیحِ ساده حرفِ خودش را نقض کرد؟

    تشخیصِ «نقض» به‌طورِ کامل به مدل سپرده می‌شود (قضاوتِ معنایی است)، اما
    *پیش‌شرطِ* منطقی‌اش در کد بررسی می‌شود: تست درست + توضیحِ موجود.
    این تابع برای مدل شاهد می‌سازد، نه حکم.
    """
    q2 = _question(questions, 2) or {}
    chosen = _chosen_option(answers, q2)
    correct = q2.get("correct_option_index")
    mcq_correct = chosen is not None and correct is not None and int(chosen) == int(correct)
    q5_answer = answers.get(5, "")

    candidate = bool(mcq_correct and _looks_substantive(q5_answer, min_words=6))
    return {
        "rule": 1,
        # «در معرضِ خطر» یعنی شرایطِ شک وجود دارد؛ حکمِ قطعی با مدل است.
        "at_risk": candidate,
        "mcq_correct": mcq_correct,
        "chosen_option": chosen,
        "correct_option": correct,
        "q5_answer_present": bool(_normalize(q5_answer)),
        "note": (
            "تست را درست زد و توضیحِ فاینمن را هم نوشت — بررسی کن آیا در توضیح، "
            "حرفِ خودش را نقض کرده است یا نه."
            if candidate
            else "شرایطِ تضادِ نقاب و شهود برقرار نیست."
        ),
    }


# ---------------------------------------------------------------------------
# قانون ۲ — حاکمیتِ عیب‌یابی (Q3 و Q4)
# ---------------------------------------------------------------------------
def debugging_supremacy_signal(
    answers: dict[int, str], questions: list[dict[str, Any]], *, model_verdicts: Optional[dict[int, bool]] = None
) -> dict[str, Any]:
    """قانون ۲ — آیا Q3 و Q4 آن‌قدر قوی‌اند که حکمِ «نفهمیده» نادرست باشد؟

    «قوی» بودن را مدل تعیین می‌کند (`model_verdicts`)، چون سنجشِ عمقِ
    استدلال کارِ کد نیست. اگر حکمی از مدل نرسیده باشد، تنها *حضورِ*
    پاسخِ مفصل به‌عنوانِ سیگنالِ ضعیف در نظر گرفته می‌شود.
    """
    verdicts = model_verdicts or {}
    q3_ok = verdicts.get(3)
    q4_ok = verdicts.get(4)
    if q3_ok is None:
        q3_ok = _looks_substantive(answers.get(3, ""), min_words=12)
    if q4_ok is None:
        q4_ok = _looks_substantive(answers.get(4, ""), min_words=12)

    strong = bool(q3_ok and q4_ok)
    return {
        "rule": 2,
        "strong": strong,
        "q3_ok": bool(q3_ok),
        "q4_ok": bool(q4_ok),
        "note": (
            "سؤال ۳ و ۴ قوی‌اند: حکمِ «نفهمیده» نادرست خواهد بود. اگر سؤال ۵ "
            "ضعیف بود، علتش بی‌حوصلگی یا ضعفِ بیان است نه نبودِ فهم."
            if strong
            else "حاکمیتِ عیب‌یابی برقرار نیست."
        ),
    }


# ---------------------------------------------------------------------------
# قانون ۴ — بی‌دقتی در برابر کج‌فهمی (بازپرسی)
# ---------------------------------------------------------------------------
def detect_slip_candidate(
    answers: dict[int, str], questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """تشریحیِ پرمحتوا + تستِ متضاد ⇒ احتمال بی‌دقتی.

    تضادِ *معنایی* را مدل باید تشخیص بدهد؛ اما سیگنالِ ساختاری (پاسخِ
    تشریحیِ مفصل در کنارِ انتخابِ گزینه‌ای که با حکمِ مدل نمی‌خواند)
    این‌جا ساخته می‌شود.
    """
    descriptive_ids = (1, 3, 4)
    substantive = {
        qid: _looks_substantive(answers.get(qid, ""), min_words=10) for qid in descriptive_ids
    }
    return {
        "rule": 4,
        "substantive_answers": substantive,
        "any_substantive": any(substantive.values()),
        "note": "اگر تست با توضیحِ تشریحیِ خودش در تضاد بود، بازپرسی لازم است.",
    }


# ---------------------------------------------------------------------------
# جمع‌بندی
# ---------------------------------------------------------------------------
def rule_summary(answers: dict[int, str], questions: list[dict[str, Any]]) -> dict[str, Any]:
    """همهٔ سیگنال‌های قطعی در یک بسته — به مدل داده می‌شود و در لاگ می‌ماند."""
    jargon = detect_jargon_violation(answers, questions)
    mask = detect_mask_intuition_conflict(answers, questions)
    return {
        "jargon": jargon,
        "mask_vs_intuition": mask,
        "debugging_supremacy": debugging_supremacy_signal(answers, questions),
        "slip_candidate": detect_slip_candidate(answers, questions),
        "answered_questions": sorted(qid for qid in answers if _normalize(answers.get(qid, ""))),
    }


def apply_supremacy_override(report: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    """قانون ۲ را روی حکمِ نهایی اعمال می‌کند.

    مدل گاهی سؤالِ ۵ را ضعیف می‌بیند و حکمِ «نفهمیده» می‌دهد، در حالی که
    سؤالِ عیب‌یابی را درست حل کرده. این تابع جلوی آن را می‌گیرد.
    """
    supremacy = signals.get("debugging_supremacy") or {}
    if not supremacy.get("strong"):
        return report

    status = (report.get("evaluation_report") or {}).get("mastery_status")
    if status in ("UNSTRUCTURED", "PARTIAL_FRAGMENTED"):
        evaluation = report.setdefault("evaluation_report", {})
        evaluation["mastery_status"] = "MASTERED"
        findings = evaluation.setdefault("cross_check_findings", [])
        title = "پیروزیِ عیب‌یابی بر بیانِ ضعیف"
        # اگر مدل خودش همین یافته را داده، تکرارش کردن کارتِ تکراری می‌سازد
        # و گزارش را بی‌اعتبار نشان می‌دهد.
        already = any(
            f.get("title") == title or (f.get("type") == "SYNERGY" and "عیب‌یابی" in str(f.get("title", "")))
            for f in findings
        )
        if not already:
            findings.insert(
                0,
                {
                    "title": title,
                    "type": "SYNERGY",
                    "description": (
                        "استدلالِ تو در سؤال‌های دستکاری و عیب‌یابی درست و منسجم بود. "
                        "ساعت را بسته‌ای؛ اگر در توضیحِ ساده کوتاه آمدی، نشانهٔ نفهمیدن نیست."
                    ),
                },
            )
    return report


def apply_jargon_flag(report: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    """قانون ۳ را در یافته‌ها تضمین می‌کند: اگر کلمهٔ ممنوعه استفاده شده، حتماً ذکر شود."""
    jargon = signals.get("jargon") or {}
    if not jargon.get("violated"):
        return report
    evaluation = report.setdefault("evaluation_report", {})
    findings = evaluation.setdefault("cross_check_findings", [])
    already = any(f.get("type") == "JARGON_VIOLATION" for f in findings)
    if not already:
        hits = "، ".join(jargon.get("hits") or [])
        findings.append(
            {
                "title": "شکستنِ قانونِ کلماتِ ممنوعه",
                "type": "JARGON_VIOLATION",
                "description": (
                    f"در توضیحِ ساده از «{hits}» استفاده کردی — همان کلماتی که قرار بود "
                    "کنار بگذاری. یعنی توضیحت به کلماتِ کتاب تکیه داشت، نه به شهودِ خودت."
                ),
            }
        )
    return report


def dedupe_findings(report: dict[str, Any]) -> dict[str, Any]:
    """یافته‌های تکراری را حذف می‌کند (بر اساسِ نوع + عنوان)."""
    evaluation = report.setdefault("evaluation_report", {})
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for finding in evaluation.get("cross_check_findings") or []:
        key = (str(finding.get("type", "")), str(finding.get("title", "")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    evaluation["cross_check_findings"] = unique
    return report
