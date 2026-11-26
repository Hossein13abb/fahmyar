"""ساخت گزارش کیفی فهم‌یار (به فارسی) — بدون نمره، رتبه یا مقایسه.

ساختار خروجی (دقیقاً مطابق قالب پروژه):
  موضوع بررسی / زمینه / مشاهدات / شواهد / موارد هنوز روشن‌نشده / پیشنهاد اقدام
  + برچسب «⚠️ نمرهٔ آزمون — نه سنجش فهم» در صورت وجود نمرهٔ امتحانی
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from config import settings
from models.concept import Concept
from models.question import AssessmentSession, EvidenceStatus

STATUS_FA_SHORT = {
    "CONFIRMED": "تأییدشده",
    "LIKELY_UNDERSTOOD": "احتمالاً آموخته‌شده",
    "UNCLEAR": "نامشخص (نیاز به گفت‌وگو/مثال‌های بیشتر)",
    "NEEDS_REVIEW": "بدفهمی شناسایی‌شده",
    "INSUFFICIENT_EVIDENCE": "فاقد شواهد کافی",
}

def _aggregate_by_proposition(session: AssessmentSession) -> dict[str, dict[str, Any]]:
    per_prop: dict[str, dict[str, Any]] = {}
    for entry in session.evidence_log or []:
        for ev in entry.get("evidence", []):
            prop = ev.get("proposition_id", "?")
            agg = per_prop.setdefault(
                prop,
                {
                    "statuses": [],
                    "reasonings": [],
                    "needs_teacher_review": False,
                    "error_types": set(),
                    "question_ids": set(),
                },
            )
            agg["statuses"].append(ev.get("status"))
            if ev.get("reasoning"):
                agg["reasonings"].append(ev["reasoning"])
            if ev.get("needs_teacher_review"):
                agg["needs_teacher_review"] = True
            if ev.get("error_type"):
                agg["error_types"].add(ev["error_type"])
            if entry.get("question_id") is not None:
                agg["question_ids"].add(entry["question_id"])
    return per_prop


def _final_prop_status(statuses: list[str]) -> str:
    """وضعیت نهایی یک گزاره بر پایهٔ همهٔ شواهدش (نسخهٔ گزارش)."""
    strong_contra = sum(1 for s in statuses if s == EvidenceStatus.NEEDS_REVIEW.value)
    confirming = sum(1 for s in statuses if s in (EvidenceStatus.CONFIRMED.value, EvidenceStatus.LIKELY_UNDERSTOOD.value))
    unclear = sum(1 for s in statuses if s == EvidenceStatus.UNCLEAR.value)
    if strong_contra and confirming:
        return EvidenceStatus.UNCLEAR.value
    if strong_contra:
        return EvidenceStatus.NEEDS_REVIEW.value
    if confirming >= 2:
        return EvidenceStatus.CONFIRMED.value
    if confirming == 1:
        return EvidenceStatus.LIKELY_UNDERSTOOD.value
    if unclear:
        return EvidenceStatus.UNCLEAR.value
    return EvidenceStatus.INSUFFICIENT_EVIDENCE.value


def _persisted_evaluation(session: AssessmentSession) -> dict[str, Any]:
    """خروجیِ ارزیابِ ذخیره‌شده در خودِ جلسه — اگر کامل باشد.

    ── باگِ «همه‌چیز نامشخص» (فاز ۲۸) ──
    بعضی جلسه‌ها (``trigger_type == "cognitive_assessment"``) نتیجهٔ کاملِ
    ارزیاب را در ``session.cognitive_report["evaluation_report"]`` دارند:
    تیپ، جمع‌بندی، شواهد سؤال‌به‌سؤال، تناقض‌ها. ولی ``build_report`` که
    مسیرِ *غیرِآزمونیِ* ``GET /api/assess/{id}/report`` است، این کلید را
    هرگز نمی‌خواند و بی‌صدا گزارشِ متنیِ قدیمی را می‌ساخت.

    نتیجهٔ آن باگ دقیقاً همان چیزی بود که در کارنامه دیده می‌شد:
    ``concept_name = "نامشخص"``، صفر سؤال، پنج محورِ خالی و نوارهای بدونِ
    داده — درحالی‌که تحلیلِ واقعی در همان ردیفِ دیتابیس نشسته بود.

    این تابع اگر آن خروجی را بیابد و حداقل یک شاهد یا جمع‌بندی داشته باشد،
    همان را برمی‌گرداند؛ وگرنه ``{}`` تا مسیرِ قدیمی دست‌نخورده بماند.
    """
    raw = session.cognitive_report
    if not isinstance(raw, dict):
        return {}
    ev = raw.get("evaluation_report")
    if not isinstance(ev, dict) or not ev:
        return {}
    # فقط وقتی جایگزین می‌شود که چیزی برای گفتن داشته باشد؛ یک دیکشنریِ
    # تقریباً خالی نباید گزارشِ متنیِ معتبر را بپوشاند.
    has_substance = bool(
        ev.get("executive_summary")
        or ev.get("persona_title")
        or ev.get("mastery_status")
        or (ev.get("question_by_question_insight") or [])
        or (ev.get("cross_check_findings") or [])
    )
    return ev if has_substance else {}


def _report_from_persisted_evaluation(
    session: AssessmentSession,
    concept: Concept | None,
    ev: dict[str, Any],
    report_text: str,
) -> dict[str, Any]:
    """گزارشِ کارنامه از خروجیِ ذخیره‌شدهٔ ارزیاب — بدونِ هیچ درخواستِ تازه.

    شکلِ خروجی عمداً با ``exam_report`` یکی است تا ``ReportView`` یک زبانِ
    دادهٔ واحد ببیند و لازم نباشد برای این جلسه‌ها شاخهٔ جدا بسازد.

    قواعدِ سخت:
      • هر کلیدی که در ارزیاب نبوده، **ساخته نمی‌شود**. بخشش در UI خالی
        می‌ماند و خودش را رندر نمی‌کند — نه «نامشخص» به‌عنوان پرکننده.
      • هیچ درصد/امتیاز/رتبه‌ای از شواهدِ کیفی ساخته نمی‌شود.
    """
    from reports.exam_report import build_stage_dimensions  # جلوگیری از import چرخشی

    # ── شواهدِ سؤال‌به‌سؤال ──
    #
    # ⚠️ مهم: در این جلسه‌ها ``evidence_log`` خالی است و پاسخ‌ها هم در
    # ``cognitive_payload.answers`` ذخیره نشده‌اند (باگِ ذخیره‌سازیِ نسخهٔ
    # قدیمی). ولی ارزیاب حکمِ خود را برای **هر پنج سؤال** در
    # ``question_by_question_insight`` نوشته است.
    #
    # پس این‌جا فقط همان حکم منتقل می‌شود. هیچ ``status`` درست/غلط ساخته
    # نمی‌شود، چون شواهدش در دست نیست — و ارزیابی کل‌نگر است، پس از روی
    # حکمِ توصیفی هم نمی‌توان درست/غلط استنتاج کرد.
    insights = ev.get("question_by_question_insight") or []
    payload = session.cognitive_payload if isinstance(session.cognitive_payload, dict) else {}
    payload_questions = payload.get("questions") or []

    # ایندکسِ متنِ سؤال، بر اساسِ idِ سؤال در payload
    qtext_by_id: dict[int, str] = {}
    for q in payload_questions:
        if not isinstance(q, dict):
            continue
        try:
            qtext_by_id[int(q.get("id"))] = str(q.get("question_text") or "")
        except (TypeError, ValueError):
            continue

    per_question: list[dict[str, Any]] = []
    seen_orders: set[int] = set()

    for item in insights:
        if not isinstance(item, dict):
            continue
        try:
            order_i = int(item.get("question_id") or item.get("question_number"))
        except (TypeError, ValueError):
            continue
        if order_i in seen_orders:
            continue
        seen_orders.add(order_i)
        verdict = str(item.get("cognitive_verdict") or "").strip()
        per_question.append({
            "order": order_i,
            "question_text": qtext_by_id.get(order_i, ""),
            # ``status`` عمداً None است: شاهدِ قابلِ اتکا برای درست/غلط نداریم.
            "status": None,
            "cognitive_verdict": verdict,
            # «بینشِ تشخیصی» = همان حکمِ ارزیاب، نه جملهٔ ساخته‌شده.
            "diagnostic_insight": verdict,
            "response": "",
            "options": [],
            "selected_option_index": None,
            "needs_teacher_review": False,
        })

    # اگر جلسه‌ای شواهدِ ساختاریافته داشت، همان‌ها هم اضافه شوند
    # (مسیرِ معمول: ``evidence_log`` پُر است).
    for entry in session.evidence_log or []:
        try:
            order_i = int(entry.get("order"))
        except (TypeError, ValueError):
            continue
        if order_i in seen_orders:
            continue
        seen_orders.add(order_i)
        record = (entry.get("evidence") or [{}])[0] if isinstance(entry.get("evidence"), list) else {}
        per_question.append({
            "question_id": entry.get("question_id"),
            "order": order_i,
            "exam_type": entry.get("exam_type") or "",
            "exam_type_raw": entry.get("exam_type"),
            "status": (record.get("status") or "").upper() or None,
            "cognitive_verdict": record.get("cognitive_verdict"),
            "diagnostic_insight": record.get("diagnostic_insight") or "",
            "question_text": entry.get("question_text") or "",
            "response": entry.get("response") or "",
            "options": entry.get("options") or [],
            "selected_option_index": entry.get("selected_option_index"),
            "needs_teacher_review": bool(record.get("needs_teacher_review", False)),
        })
    per_question.sort(key=lambda q: q.get("order") or 999)

    stage_dimensions = build_stage_dimensions(per_question)

    # ── ابعاد: فقط آن‌چه ارزیاب گفته ──
    # ارزیابِ این مسیر ابعادِ آزاد نمی‌دهد؛ از شواهدِ واقعیِ پنج سؤال ساخته
    # می‌شود و اگر هیچ سؤالی نبود، لیست خالی می‌ماند (نه پنج ردیفِ «نامشخص»).
    # ── ابعاد ──
    # ``build_stage_dimensions`` وضعیت را از خودِ شواهد می‌سازد. اگر سؤالی
    # شاهد نداشته باشد، ``has_evidence=False`` می‌شود و آن ردیف **حذف**
    # می‌شود — نه اینکه با «نامشخص» پر شود.
    dimensions = [
        {"dimension": d["label"], "status": _DIM_STATUS[d["status"]], "finding": d["finding"]}
        for d in stage_dimensions
        if d.get("has_evidence") and str(d.get("finding") or "").strip()
    ]

    cross_check = [
        {
            "title": str(f.get("title") or "").strip(),
            "type": str(f.get("type") or "SYNERGY").upper().strip(),
            "description": str(f.get("description") or "").strip(),
            "resolution": f.get("resolution"),
        }
        for f in (ev.get("cross_check_findings") or [])
        if isinstance(f, dict) and str(f.get("title") or "").strip()
    ]

    # ── نامِ مبحث ──
    # این جلسه‌ها ``concept_id`` ندارند (میراثِ نسخهٔ قدیمی)، ولی موضوعِ
    # واقعی در ``cognitive_payload.topic`` نوشته شده. اگر از قلم بیفتد،
    # عنوانِ کارنامه خالی می‌ماند و دانش‌آموز نمی‌داند کارنامهٔ چه چیزی است.
    topic_name = str(payload.get("topic") or "").strip()
    display_name = concept.name if concept else topic_name

    sections = {
        "موضوع بررسی": display_name,
        "مشاهدات": [p.get("diagnostic_insight") for p in per_question if p.get("diagnostic_insight")],
        "پیشنهاد اقدام برای دانش‌آموز": [s for s in (ev.get("next_step"),) if s],
    }

    return {
        "session_id": session.id,
        "student_id": session.student_id,
        "concept_id": session.concept_id,
        "concept_name": display_name,
        "status": session.status,
        "questions_answered": len(per_question),
        "report_text": report_text,
        "sections": sections,
        "proposition_statuses": {},
        "root_causes": [],
        "needs_teacher_review": bool(ev.get("needs_teacher_review")),
        # ── همان کلیدهای کارنامهٔ آزمونی ──
        "mastery_status": ev.get("mastery_status"),
        "persona_title": ev.get("persona_title"),
        "executive_summary": ev.get("executive_summary"),
        "mastery_note": ev.get("mastery_note"),
        "next_step": ev.get("next_step") or _advice_text(ev.get("actionable_advice")),
        "cross_check_findings": cross_check,
        "per_question": per_question,
        "stage_dimensions": stage_dimensions,
        "dimensions": dimensions,
        "learning_gaps": [],
        "root_cause_chains": [],
        "suggestions": [],
        "needs_clarification": bool(ev.get("needs_clarification")),
        "clarification_data": ev.get("clarification_data"),
        "exam_score_note": "توجه: نمرهٔ آزمون — نه سنجش فهم. این کارنامه نمره/رتبه/درصد ندارد و فقط شواهدِ کیفی را ثبت می‌کند.",
        "generated_at": datetime.utcnow().isoformat(),
    }


# نگاشتِ وضعیتِ شاهد → وضعیتِ بُعد در کارنامه (کلیدهای انگلیسی، تا
# نرمال‌سازِ پایین‌دست آن‌ها را به «نامشخص» برنگرداند — همان باگِ قدیمی).
def _advice_text(advice: Any) -> str:
    """اولین توصیهٔ ارزیاب، به‌صورتِ متن — بدونِ ساختنِ توصیهٔ تازه."""
    if isinstance(advice, str):
        return advice.strip()
    if isinstance(advice, list):
        for item in advice:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                t = str(item.get("advice") or item.get("text") or item.get("title") or "").strip()
                if t:
                    return t
    if isinstance(advice, dict):
        for key in ("advice", "text", "summary"):
            t = str(advice.get(key) or "").strip()
            if t:
                return t
    return ""


_DIM_STATUS = {
    "mastered": "LIKELY_UNDERSTOOD",
    "developing": "LIKELY_UNDERSTOOD",
    "needs_work": "NEEDS_REVIEW",
    "not_assessed": "INSUFFICIENT_EVIDENCE",
}


def build_report(db: Session, session: AssessmentSession) -> dict[str, Any]:
    concept = db.query(Concept).filter(Concept.id == session.concept_id).first() if session.concept_id else None
    concept_name = concept.name if concept else "نامشخص"
    subject = concept.subject if concept else ""
    grade = concept.grade if concept else ""

    if session.trigger_type == "topic_selection":
        زمینه = f"شروع با انتخابِ موضوع/مفهوم ({concept_name})"
    else:
        زمینه = "شروع با پاسخِ غلط به یک سؤال (بررسی ریشهٔ خطا)"

    agg = _aggregate_by_proposition(session)

    # --- مشاهدات ---
    observations: list[str] = []
    for i, entry in enumerate(session.evidence_log or [], start=1):
        response = (entry.get("response") or "").strip().replace("\n", " ")
        quote = response[: settings.REPORT_RESPONSE_QUOTE_CHARS]
        if len(response) > settings.REPORT_RESPONSE_QUOTE_CHARS:
            quote += "…"
        if quote:
            observations.append(f"در پاسخ به سؤالِ {i}: «{quote}»")
        else:
            observations.append(f"سؤالِ {i}: پاسخی ثبت نشد.")
    needs_teacher = any(a["needs_teacher_review"] for a in agg.values())
    if needs_teacher:
        observations.append("در دست‌کم یک پاسخ، تحلیل‌گر خودکار برای قضاوت مطمئن نبود و نیازمند نگاه معلم است.")
    # بدفهمی‌های قطعی — با همان لحن قاطعِ تحلیل‌گر در مشاهدات می‌آیند
    for prop, a in agg.items():
        st = _final_prop_status(a["statuses"])
        if st == EvidenceStatus.NEEDS_REVIEW.value:
            qfs = [e.get("qualitative_feedback") for e in (e for entry in session.evidence_log or [] for e in entry.get("evidence", []))
                   if e.get("proposition_id") == prop and e.get("qualitative_feedback")]
            decisive = qfs[-1] if qfs else ((a["reasonings"] or [""])[-1])
            observations.append(f"بدفهمیِ شناسایی‌شده در گزارهٔ «{prop}»: {decisive}")

    # --- شواهد (گزاره به گزاره) ---
    evidence_lines: list[str] = []
    per_prop_status: dict[str, str] = {}
    for prop, a in agg.items():
        status = _final_prop_status(a["statuses"])
        per_prop_status[prop] = status
        reason = (a["reasonings"] or ["—"])[-1]
        evidence_lines.append(f"گزارهٔ «{prop}»: {STATUS_FA_SHORT.get(status, status)} — {reason}")
    if concept:
        for prop in concept.core_propositions or []:
            if prop not in per_prop_status:
                per_prop_status[prop] = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
                evidence_lines.append(f"گزارهٔ «{prop}»: {STATUS_FA_SHORT['INSUFFICIENT_EVIDENCE']} — در این جلسه دربارهٔ آن شواهدی جمع نشده است.")

    # --- موارد هنوز روشن‌نشده ---
    unclear_items = [
        prop for prop, st in per_prop_status.items()
        if st in (EvidenceStatus.UNCLEAR.value, EvidenceStatus.INSUFFICIENT_EVIDENCE.value)
    ]
    unclear_lines = [
        f"«{prop}» ({STATUS_FA_SHORT[per_prop_status[prop]]})" for prop in unclear_items
    ] or ["موردِ مبهمی باقی نمانده است."]

    # --- فرضیه‌های ریشهٔ خطا (مسیر B) — ساختار‌یافته + خط متنی ---
    _ROOT_STATUS_FA = {"pending": "بررسی‌نشده", "testing": "در حال بررسی", "supported": "تأییدشده",
                       "likely_root_cause": "مشکوک به ریشهٔ خطا", "rejected": "رد شده"}
    root_causes: list[dict[str, Any]] = []
    root_cause_lines: list[str] = []
    for hyp in session.current_hypotheses or []:
        if hyp.get("type") != "root_cause":
            continue
        name = str(hyp.get("concept_name") or hyp.get("concept_topic") or "بدون عنوان")
        status_raw = str(hyp.get("status") or "")
        mark = _ROOT_STATUS_FA.get(status_raw, status_raw or "نامشخص")
        cross = bool(hyp.get("cross_subject"))
        reasoning = str(hyp.get("reason") or hyp.get("reasoning") or "").strip()
        root_causes.append({
            "concept_name": name,
            "area": name,
            "status": status_raw,
            "status_label": mark,
            "reasoning": reasoning or f"وضعیت بررسی: {mark}",
            "cross_subject": cross,
        })
        root_cause_lines.append(f"{name}{' (بین‌درسی)' if cross else ''}: {mark}")

    # --- پیشنهاد اقدام ---
    student_actions: list[str] = []
    teacher_notes: list[str] = []
    for prop, st in per_prop_status.items():
        if st == EvidenceStatus.NEEDS_REVIEW.value:
            student_actions.append(f"بدفهمیِ گزارهٔ «{prop}» را مستقیم هدف بگیرید: ابتدا مثال‌های نقضِ شهودی سپس مسئله‌های ترکیبی.")
        elif st == EvidenceStatus.UNCLEAR.value:
            student_actions.append(f"گفت‌وگو و توضیحِ شفاهی دربارهٔ «{prop}»؛ از دانش‌آموز بخواهید فهمیدگیِ خود را با مثالِ خودش توضیح دهد.")
        elif st == EvidenceStatus.INSUFFICIENT_EVIDENCE.value:
            student_actions.append(f"هنوز دربارهٔ «{prop}» شواهد کافی نداریم؛ یک جلسهٔ دیگر یا تمرینِ تکمیلی لازم است.")
    if not student_actions:
        student_actions.append("عملکرد شما در این مفهوم خوب است؛ برای تثبیت، یک مسئلهٔ ترکیبیِ بین‌درسی حل کنید.")

    if needs_teacher:
        teacher_notes.append("پاسخ‌های بی‌ربط/نامفهوم که با «نیازمند بررسی معلم» علامت خورده‌اند را شخصاً بخوانید؛ تحلیل‌گر خودکار داوری نکرده است.")
    weak_props = [p for p, s in per_prop_status.items() if s == EvidenceStatus.NEEDS_REVIEW.value]
    if weak_props:
        teacher_notes.append("در جلسهٔ بعد ابتدا پیش‌نیازهای همین گزاره‌ها (و در صورت لزوم ابزارهای ریاضی) را مرور کنید.")
    if session.trigger_type == "wrong_answer":
        teacher_notes.append("این جلسه از یک پاسخ غلط شروع شد؛ مفهومِ اصلی و پیش‌نیازهایش با هم مرور شوند — به‌خصوص اگر فرضیهٔ بین‌درسی تأیید شد.")

    # --- متن گزارش (قالب ثابت) ---
    lines = [
        f"موضوع بررسی: {concept_name}" + (f" ({subject} — پایهٔ {grade})" if concept_name != "نامشخص" else ""),
        f"زمینه: {زمینه}",
        "",
        "مشاهدات:",
        *[f"- {o}" for o in (observations or ["پاسخی ثبت نشده است."])],
        "",
        "شواهد:",
        *[f"- {e}" for e in evidence_lines],
    ]
    if root_cause_lines:
        lines += ["", "فرضیه‌های ریشهٔ خطا:", *[f"- {r}" for r in root_cause_lines]]
    lines += [
        "",
        "موارد هنوز روشن‌نشده:",
        *[f"- {u}" for u in unclear_lines],
        "",
        "پیشنهاد اقدام:",
        *[f"- دانش‌آموز: {a}" for a in student_actions],
        *[f"- معلم: {t}" for t in teacher_notes],
        "",
        "⚠️ نمرهٔ آزمون — نه سنجش فهم: اگر در کنار این جلسه نمرهٔ امتحانی وجود دارد، صرفاً یک دادهٔ جداست و با «فهمیدن» یکی نیست؛ این گزارش جایگزینِ نمره‌گذاری نیست.",
    ]
    report_text = "\n".join(lines)

    # ── اگر ارزیابِ کل‌نگر خروجیِ ذخیره‌شده دارد، همان مرجع است ──
    persisted = _persisted_evaluation(session)
    if persisted:
        return _report_from_persisted_evaluation(session, concept, persisted, report_text)

    return {
        "session_id": session.id,
        "student_id": session.student_id,
        "concept_id": session.concept_id,
        "concept_name": concept_name,
        "status": session.status,
        "questions_answered": len(session.evidence_log or []),
        "report_text": report_text,
        "sections": {
            "موضوع بررسی": concept_name,
            "زمینه": زمینه,
            "مشاهدات": observations,
            "شواهد": evidence_lines,
            "فرضیه‌های ریشهٔ خطا": root_cause_lines,
            "موارد هنوز روشن‌نشده": unclear_lines,
            "پیشنهاد اقدام برای دانش‌آموز": student_actions,
            "یادداشت برای معلم": teacher_notes,
        },
        "proposition_statuses": per_prop_status,
        "root_causes": root_causes,
        "needs_teacher_review": needs_teacher,
        "exam_score_note": "توجه: نمرهٔ آزمون — نه سنجش فهم. این کارنامه نمره/رتبه/درصد ندارد و فقط شواهدِ کیفی را ثبت می‌کند.",
        "generated_at": datetime.utcnow().isoformat(),
        # هیچ رتبه/درصد/مقایسه‌ای در خروجی وجود ندارد — عمداً
    }
