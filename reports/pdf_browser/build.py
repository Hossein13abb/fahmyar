# -*- coding: utf-8 -*-
"""The public entry point for the browser-based PDF engine.

``build_exam_pdf_browser`` accepts exactly the keyword arguments of the old
``reports.exam_pdf.build_exam_pdf`` so the API route does not change.  It:

1.  turns those arguments into the render payload (labels, Persian date),
2.  builds the HTML document,
3.  captures it in Chromium,
4.  packs the pages into a PDF.

Any failure raises :class:`BrowserRenderError`, which the route maps to an
HTTP error.  There is no silent fallback to the old engine: the old engine is
gone, and a quiet degraded PDF is worse than a clear failure.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from .capture import CaptureError, capture_exam
from .packer import pdf_from_images

__all__ = ["build_exam_pdf_browser", "BrowserRenderError", "build_payload"]


class BrowserRenderError(RuntimeError):
    """The browser could not produce a PDF."""


_GRADE_LABELS = {
    "10": "دهم",
    "11": "یازدهم",
    "12": "دوازدهم",
    "comprehensive": "جامع",
}

_SUBJECT_LABELS = {
    "math": "ریاضی",
    "physics": "فیزیک",
    "chemistry": "شیمی",
    "biology": "زیست‌شناسی",
    "english": "انگلیسی",
    "calculus": "حسابان",
    "geometry": "هندسه",
}


def _fa_date() -> str:
    """Today's date in the Persian calendar, Persian digits."""
    try:
        import jdatetime

        d = jdatetime.date.today()
        raw = f"{d.year}/{d.month:02d}/{d.day:02d}"
    except Exception:
        raw = datetime.date.today().strftime("%Y/%m/%d")
    return raw.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def build_payload(
    title: str,
    school_name: str,
    questions: List[Dict[str, Any]],
    duration_minutes: int,
    difficulty: str,
    grade: Optional[Any] = None,
    major: Optional[str] = None,
    subject_label: str = "",
    topic: str = "",
) -> Dict[str, Any]:
    """Map the legacy call signature onto the renderer's payload."""
    grade_key = str(grade).strip() if grade is not None else ""
    meta = {
        "title": (title or "").strip() or "آزمون کنکوری — فهم‌یار",
        "school_name": (school_name or "").strip() or "مدرسهٔ نمونه",
        "grade_label": _GRADE_LABELS.get(grade_key, grade_key or "—"),
        "major": (major or "").strip() or "—",
        "subject_label": (subject_label or "").strip() or "—",
        "topic": (topic or "").strip() or "—",
        "question_count": len(questions),
        "duration_minutes": int(duration_minutes or 0),
        "difficulty": (difficulty or "").strip() or "—",
        "date_label": _fa_date(),
    }
    return {
        "meta": meta,
        "footer": (
            f"فهم‌یار · آزمون کنکوری · {meta['difficulty']} · {meta['date_label']}"
        ),
        "questions": [
            {
                "order": q.get("order") or i,
                "text": q.get("text") or q.get("question_text") or "",
                "options": list(q.get("options") or []),
                "correct_answer": q.get("correct_answer"),
                "difficulty": q.get("difficulty") or "",
                "subject": q.get("subject") or "",
                "explanation": q.get("explanation") or "",
                "diagram_svg": q.get("diagram_svg"),
            }
            for i, q in enumerate(questions, start=1)
        ],
    }


def build_exam_pdf_browser(
    school_name: str,
    title: str,
    questions: List[Dict[str, Any]],
    duration_minutes: int,
    difficulty: str,
    grade: Optional[Any] = None,
    major: Optional[str] = None,
    subject_label: str = "",
    topic: str = "",
    *,
    scale: float = 2.0,
    timeout_ms: int = 30_000,
) -> bytes:
    """Render the exam in Chromium and return PDF bytes."""
    if not questions:
        raise BrowserRenderError("no questions supplied")

    payload = build_payload(
        title=title,
        school_name=school_name,
        questions=questions,
        duration_minutes=duration_minutes,
        difficulty=difficulty,
        grade=grade,
        major=major,
        subject_label=subject_label,
        topic=topic,
    )

    try:
        captured = capture_exam(payload, scale=scale, timeout_ms=timeout_ms)
    except CaptureError as exc:
        raise BrowserRenderError(str(exc)) from exc
    except Exception as exc:
        raise BrowserRenderError(f"chromium capture failed: {exc}") from exc

    if not captured.pages:
        raise BrowserRenderError("chromium produced no pages")

    try:
        return pdf_from_images(captured.pages, title=payload["meta"]["title"])
    except Exception as exc:
        raise BrowserRenderError(f"pdf packing failed: {exc}") from exc
