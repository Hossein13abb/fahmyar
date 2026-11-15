"""موتورِ mock برای آزمونِ شناختی — پاسخِ قطعی و قابلِ پیش‌بینی بدونِ شبکه.

**چرا این لازم است؟** بدونِ کلیدِ API نمی‌توان زنجیرهٔ
تولید → پاسخ → ارزیابی → بازپرسی → کارنامه را آزمود. mock اجازه می‌دهد
هر پنج مرحله در CI و روی ماشینِ کاربر اجرا شود و UI واقعاً تمرین شود.

mock رفتارِ یک مدل را *تقلید* می‌کند، ولی سعی نمی‌کند هوشمند باشد:
پاسخ‌ها را با قواعدِ ساختاری می‌سنجد تا نتیجه قابلِ پیش‌بینی باشد.
"""
from __future__ import annotations

import json
from typing import Any

from .contract import QUESTION_TITLES


# ---------------------------------------------------------------------------
# مرحلهٔ ۱ — تولیدِ آزمون
# ---------------------------------------------------------------------------
def mock_generation(prompt: str) -> str:
    """یک آزمونِ پنج‌سؤالیِ منسجم دربارهٔ فشار در مایعات (نمونهٔ استاندارد).

    موضوعِ درخواستی از پرامپت خوانده می‌شود تا آزمون با مبحث هم‌خوان باشد.
    """
    topic = _extract_topic(prompt) or "فشار در مایعات"
    return json.dumps(
        {
            "topic_blueprint": {
                "core_mechanism": (
                    "فشار در درونِ شاره از وزنِ ستونِ مایعِ بالای هر نقطه می‌آید؛ "
                    "پس تنها به عمق و چگالی و گرانش بسته است، نه به حجم یا شکلِ ظرف."
                ),
                "target_misconceptions": [
                    "فشار به حجمِ آب بستگی دارد (ظرفِ پهن‌تر = فشار بیشتر)",
                    "هرچه آب بیشتر باشد فشار روی دیواره‌ها بیشتر می‌شود",
                    "فشار به شکلِ ظرف وابسته است",
                ],
            },
            "questions": [
                {
                    "id": 1,
                    "type": "philosophy",
                    "title": QUESTION_TITLES["philosophy"],
                    "question_text": (
                        f"چرا در مبحثِ «{topic}» اصلاً مفهومی به نامِ فشار تعریف می‌کنیم؟ "
                        "اگر بخواهیم بگوییم آب در عمقِ زیاد چه اثری روی دیواره دارد، چرا "
                        "«نیرو» کافی نیست و باید آن را بر «سطح» تقسیم کنیم؟ "
                        "بدونِ فرمول توضیح بده."
                    ),
                    "options": None,
                    "forbidden_words": [],
                    "expected_logic": (
                        "نیرو به‌تنهایی وقتی سطحِ تماس تغییر کند معنای مقایسه‌ای ندارد؛ "
                        "فشار همان نیرو بر واحدِ سطح است تا بتوان دو وضعیت با سطح‌های "
                        "متفاوت را مقایسه کرد."
                    ),
                },
                {
                    "id": 2,
                    "type": "mask_mcq",
                    "title": QUESTION_TITLES["mask_mcq"],
                    "question_text": (
                        "دو ظرف داریم: ظرف A با سطحِ مقطعِ پهن و ظرف B با سطحِ مقطعِ باریک. "
                        "هر دو تا ارتفاعِ ۲ متر از آب پر شده‌اند و جنسِ هر دو از شیشهٔ ۵ میلی‌متری است. "
                        "آبِ ظرف A در یک کولرِ گازی ۳۰ دقیقه خنک شده و آبِ ظرف B در سایه مانده است. "
                        "فشارِ آب در کفِ کدام ظرف بیشتر است؟"
                    ),
                    "options": [
                        "فشار در کفِ ظرف A بیشتر است، چون آبِ بیشتری دارد.",
                        "فشار در کفِ هر دو ظرف برابر است.",
                        "فشار در کفِ ظرف B بیشتر است، چون سطحِ کمتر یعنی نیروی متمرکزتر.",
                        "با اطلاعاتِ داده‌شده نمی‌شود گفت، چون دمای آب‌ها متفاوت است.",
                    ],
                    "correct_option_index": 1,
                    "forbidden_words": [],
                    "expected_logic": (
                        "فشار فقط تابعِ عمق است: p = ρgh. حجم، پهنیِ ظرف، دما و مدتِ "
                        "خنک‌شدن اطلاعاتِ انحرافی‌اند."
                    ),
                },
                {
                    "id": 3,
                    "type": "perturbation",
                    "title": QUESTION_TITLES["perturbation"],
                    "question_text": (
                        "یک ظرفِ مکعبی تا نیمه آب دارد. بدونِ اضافه‌کردن یا برداشتنِ آب، "
                        "ظرف را به شکلِ یک استوانهٔ باریک و بلند در می‌آوریم، طوری که سطحِ آب "
                        "بالا برود اما مقدارِ آب همان بماند. فشار در کفِ ظرف چه می‌شود و چرا؟ "
                        "پاسخ را زنجیرهٔ علّی بنویس."
                    ),
                    "options": None,
                    "forbidden_words": [],
                    "expected_logic": (
                        "سطحِ آب بالا می‌رود ← عمق زیاد می‌شود ← فشار در کف زیاد می‌شود، "
                        "هرچند مقدارِ آب ثابت است. زنجیره: شکل ← عمق ← فشار."
                    ),
                },
                {
                    "id": 4,
                    "type": "debugging",
                    "title": QUESTION_TITLES["debugging"],
                    "question_text": (
                        "امیر می‌گوید: «من دو سطلِ هم‌ارتفاع دارم؛ یکی باریک و یکی خیلی پهن. "
                        "چون در سطلِ پهن آبِ بیشتری روی کف نشسته، وزنِ ستونِ آب بیشتر است و "
                        "پس فشارِ کفِ سطلِ پهن قطعاً بیشتر است. این دقیقاً همان چیزی است که "
                        "در شیرِ آبِ منزل هم می‌بینیم: مخزنِ بزرگ‌تر، فشارِ بیشتر.» "
                        "خطایِ منطقیِ استدلالِ امیر دقیقاً کجاست؟ یک جملهٔ او را نقل کن و بگو کجای آن می‌لنگد."
                    ),
                    "options": None,
                    "forbidden_words": [],
                    "expected_logic": (
                        "امیر «وزنِ کلِ آب» را با «وزنِ ستونِ مایعِ بالای واحدِ سطح» قاطی کرده. "
                        "در ظرفِ پهن، وزنِ بیشتر روی سطحِ بیشتری پخش می‌شود و نسبت ثابت می‌ماند. "
                        "مثالِ مخزن هم اشتباه است: در خانه فشار از ارتفاعِ مخزن می‌آید، نه از حجمش."
                    ),
                },
                {
                    "id": 5,
                    "type": "feynman_synthesis",
                    "title": QUESTION_TITLES["feynman_synthesis"],
                    "question_text": (
                        "برای یک بچهٔ ۱۰ ساله توضیح بده چرا وقتی در استخر فرو می‌روی و به کفِ "
                        "استخر نزدیک می‌شوی، گوشت درد می‌گیرد ولی در سطحِ آب درد نمی‌گیرد. "
                        "توضیحت باید طوری باشد که بچه خودش بتواند آن را برای دوستش تعریف کند."
                    ),
                    "options": None,
                    "forbidden_words": ["فشار", "چگالی", "ارتفاع", "فرمول", "قانون", "ستون"],
                    "expected_logic": (
                        "آبِ بالای سر وزن دارد و این وزن روی گوشِ تو می‌نشیند؛ هرچه پایین‌تر "
                        "بروی آبِ بیشتری بالای سرت است، پس سنگین‌تر می‌شود."
                    ),
                },
            ],
        },
        ensure_ascii=False,
    )


def _extract_topic(prompt: str) -> str:
    for line in (prompt or "").splitlines():
        if line.strip().startswith("- موضوع:"):
            return line.split(":", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# مرحلهٔ ۲ — ارزیابیِ کل‌نگر
# ---------------------------------------------------------------------------
def mock_evaluation(prompt: str) -> str:
    """ارزیابیِ ساختاری: همان قواعدِ کد، بدونِ درکِ معنایی.

    نتیجه قابلِ پیش‌بینی است و برای آزمودنِ مسیرهای UI کافی است:
    * پاسخِ تستیِ نادرست + تشریحیِ مفصل  ⇒ بازپرسی (قانون ۴)
    * کلمهٔ ممنوعه در Q5                ⇒ JARGON_DEPENDENT
    * تست درست + توضیحِ متناقض          ⇒ ILLUSION_OF_COMPETENCE
    * Q3/Q4 قوی                         ⇒ MASTERED
    """
    packet, signals = _parse_packet(prompt)
    questions = {int(q.get("id") or 0): q for q in (packet.get("questions") or [])}
    answers = {int(k): v for k, v in (packet.get("student_answers") or {}).items()}

    jargon = (signals.get("jargon") or {}) if signals else {}
    mask = (signals.get("mask_vs_intuition") or {}) if signals else {}
    # سیگنال‌ها یک بار JSON شده و برگشته‌اند، پس کلیدهای عددی به رشته تبدیل
    # شده‌اند. بدونِ این تبدیل، substantive.get(1) هرگز پیدا نمی‌شود و قانونِ
    # چهارم بی‌صدا از کار می‌افتد.
    substantive = {
        int(k): v
        for k, v in ((signals.get("slip_candidate") or {}).get("substantive_answers") or {}).items()
        if str(k).isdigit()
    }

    q2 = questions.get(2) or {}
    chosen = _chosen(answers.get(2), q2)
    correct = q2.get("correct_option_index")
    mcq_correct = chosen is not None and correct is not None and chosen == int(correct)

    q5_words = len(str(answers.get(5, "")).split())
    q3_words = len(str(answers.get(3, "")).split())
    q4_words = len(str(answers.get(4, "")) .split())

    findings: list[dict[str, Any]] = []
    needs_clarification = False
    mirror = ""

    # قانون ۴ — بی‌دقتی؟ (تشریحیِ مفصل در کنارِ تستِ نادرست)
    if substantive and (substantive.get(1) or substantive.get(4)) and chosen is not None and not mcq_correct:
        needs_clarification = True
        picked = (q2.get("options") or [""] * 4)[chosen] if chosen < len(q2.get("options") or []) else ""
        # نقلِ قول از خودِ دانش‌آموز — «آینه» یعنی حرفِ خودش، نه توصیفِ کلی.
        quote_source = ""
        for qid in (4, 1, 3):
            text = str(answers.get(qid, "")).strip()
            if len(text.split()) >= 6:
                quote_source = text
                quote_qid = qid
                break
        else:
            quote_qid = 1
        if len(quote_source) > 160:
            quote_source = quote_source[:160].rstrip() + "…"

        mirror = (
            "یک لحظه صبر کن — بینِ دو جوابِ خودت تناقض هست. "
            + (f"در سؤال {_fa(quote_qid)} نوشتی: «{quote_source}» " if quote_source else "در پاسخِ تشریحی‌ات ")
            + "اما در تستِ سؤال ۲ "
            f"گزینهٔ «{picked}» را انتخاب کردی که با آن حرف جور نیست. "
            "کدام‌یک نظرِ واقعیِ توست؟ در تست بی‌دقتی کردی و دستت خورد، "
            "یا واقعاً همان گزینه را درست می‌دانی؟ کوتاه توضیح بده."
        )

    # قانون ۳ — کلماتِ ممنوعه
    if jargon.get("violated"):
        findings.append({
            "title": "شکستنِ قانونِ کلماتِ ممنوعه",
            "type": "JARGON_VIOLATION",
            "description": "در توضیحِ ساده از «" + "، ".join(jargon.get("hits") or []) + "» استفاده کردی.",
        })

    # قانون ۲ — حاکمیتِ عیب‌یابی
    supremacy = q3_words >= 12 and q4_words >= 12
    if supremacy:
        findings.append({
            "title": "عیب‌یابیِ درست، بیانِ کم‌حوصله",
            "type": "SYNERGY",
            "description": "استدلالِ تو در سؤال‌های دستکاری و عیب‌یابی منسجم بود؛ ساعت را بسته‌ای.",
        })
    elif mcq_correct:
        findings.append({
            "title": "تستِ درست",
            "type": "SYNERGY",
            "description": "لایهٔ نقاب را با موفقیت رد کردی؛ فرمول و قانونِ رسمی را می‌دانی.",
        })

    # قانون ۱ — تضادِ نقاب و شهود
    if mask.get("at_risk") and jargon.get("violated"):
        conflict_type = "CONTRADICTION"
        findings.append({
            "title": "تناقضِ نقاب و شهود",
            "type": conflict_type,
            "description": "تست را درست زدی اما در توضیحِ ساده از کلماتِ ممنوعه استفاده کردی.",
        })

    if jargon.get("violated"):
        status = "JARGON_DEPENDENT"
        persona = "معتاد به ادبیاتِ کتاب"
    elif needs_clarification:
        status = "PARTIAL_FRAGMENTED"
        persona = "استادِ بی‌دقت (احتمالِ Slip)"
    elif supremacy:
        status = "MASTERED"
        persona = "معماری که ساعت را بست"
    elif mcq_correct:
        status = "ILLUSION_OF_COMPETENCE"
        persona = "گرفتارِ تضادِ فرمول و شهود"
    else:
        status = "UNSTRUCTURED"
        persona = "نقشهٔ ذهنیِ نامنظم"

    insights = []
    for qid in range(1, 6):
        text = str(answers.get(qid, ""))
        words = len(text.split())
        insights.append({
            "question_id": qid,
            "cognitive_verdict": "پاسخِ مفصلی دادی." if words >= 12 else ("پاسخِ کوتاه بود." if words else "پاسخ ندادی."),
            "missing_gear": None if words >= 12 else "عمقِ استدلال",
        })

    return json.dumps(
        {
            "needs_clarification": needs_clarification,
            "clarification_data": {
                "contradicting_questions": [1, 2] if needs_clarification else [],
                "mirror_prompt": mirror,
            },
            "evaluation_report": {
                "mastery_status": status,
                "persona_title": persona,
                "executive_summary": (
                    f"در این آزمون {_fa(sum(1 for q in (1,2,3,4,5) if str(answers.get(q,'')).strip()))} سؤال پاسخ دادی. "
                    "الگوی پاسخ‌هایت یک تصویرِ روشن از مدلِ ذهنی‌ات می‌سازد."
                ),
                "cross_check_findings": findings,
                "question_by_question_insight": insights,
                "actionable_advice": (
                    "همان پدیده را برای یک بچهٔ ۱۰ ساله، بدونِ هیچ کلمهٔ تخصصی، بازگو کن."
                    if jargon.get("violated")
                    else "یک زنجیرهٔ سه‌مرحله‌ای بساز: اگر این تغییر کند، بعدش چه می‌شود و چرا؟"
                ),
            },
        },
        ensure_ascii=False,
    )


def _fa(value) -> str:
    """ارقامِ لاتین را به فارسی تبدیل می‌کند تا متنِ گزارش یکدست باشد."""
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _parse_packet(prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """بستهٔ آزمون و سیگنال‌ها را از متنِ پرامپت بیرون می‌کشد."""
    packet: dict[str, Any] = {}
    signals: dict[str, Any] = {}
    decoder = json.JSONDecoder()
    text = prompt or ""
    idx = 0
    while True:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, dict):
            if "questions" in obj and "student_answers" in obj:
                packet = packet or obj
            elif any(k in obj for k in ("jargon", "mask_vs_intuition", "slip_candidate")):
                signals = signals or obj
        idx = end
    return packet, signals


def _chosen(raw: Any, q2: dict[str, Any]) -> int | None:
    """همان قراردادِ rules._chosen_option: متنِ گزینه اولویت دارد، عدد یک‌پایه است."""
    if raw in (None, ""):
        return None
    options = q2.get("options") or []
    text = str(raw).strip()
    for index, option in enumerate(options):
        if str(option).strip() == text:
            return index
    if text.isdigit():
        value = int(text)
        if 1 <= value <= len(options):
            return value - 1
    return None


# ---------------------------------------------------------------------------
# مرحلهٔ ۳ — بازپرسی
# ---------------------------------------------------------------------------
def mock_clarify(prompt: str) -> str:
    """پس از بازپرسی، حکم را با یک یافتهٔ SLIP_RESOLVED نرم می‌کند."""
    previous = _extract_previous_report(prompt)
    evaluation = previous.get("evaluation_report") or {}
    findings = list(evaluation.get("cross_check_findings") or [])
    findings.insert(0, {
        "title": "بی‌دقتیِ حل‌شده",
        "type": "SLIP_RESOLVED",
        "description": "با توضیحِ تو روشن شد که در تست بی‌دقتی کرده بودی؛ فهمِ اصلی‌ات درست بود.",
    })
    evaluation["cross_check_findings"] = findings
    if evaluation.get("mastery_status") in ("PARTIAL_FRAGMENTED", "UNSTRUCTURED"):
        evaluation["mastery_status"] = "MASTERED"
        evaluation["persona_title"] = "معماری که یک لحظه دستش لرزید"
    return json.dumps(
        {
            "needs_clarification": False,
            "clarification_data": {"contradicting_questions": [], "mirror_prompt": ""},
            "evaluation_report": evaluation,
        },
        ensure_ascii=False,
    )


def _extract_previous_report(prompt: str) -> dict[str, Any]:
    """حکمِ قبلی را از پرامپتِ بازپرسی بیرون می‌کشد."""
    marker = "حکمِ قبلیِ تو"
    start = (prompt or "").find(marker)
    if start == -1:
        return {}
    brace = prompt.find("{", start)
    if brace == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(prompt, brace)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}
