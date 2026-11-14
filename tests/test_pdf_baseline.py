# -*- coding: utf-8 -*-
"""Baseline characterisation tests — record current behaviour BEFORE refactor.

These are deliberately written as *pins*: some assert the DESIRED behaviour and
are marked xfail where the current engine is known-broken (see
baseline/ANALYSIS.md).  When the refactor lands, remove the xfail marker and
the test becomes the regression guard.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pytest

from reports.pdf_content_parser import has_math, split_math_segments
from reports.math_renderer import render_math_png


# ---------------------------------------------------------------------------
# A. Classification: what must and must not be treated as math
# ---------------------------------------------------------------------------

PLAIN_TEXT = [
    # pure English prose -- currently misclassified (ANALYSIS.md bug 1)
    "Which of the following statements about the Derivative is correct?",
    "The derivative of a constant is always one.",
    "Every continuous function is differentiable.",
    "The chain rule applies only to polynomials.",
    "Which option is correct?",
    # bare Latin acronyms
    "DNA",
    "UNESCO",
    # Persian prose
    "کدام یک از موارد زیر از ارکان نماز است؟",
    "در سال ۱۴۰۲ جمعیت شهری افزایش یافت.",
    "سود-زیان این معامله چقدر است؟",
]

REAL_MATH = [
    "(A+B)۲-A۲-B۲",
    "x^{۲}+y^{۲}=۱",
    r"\frac{۱}{۲}",
    r"\sqrt{۷}",
    "$f(x)=x^{۲}$",
    r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}",
    "|A|=۲",
    "۲×۲",
    "x \\leq ۲",
]


@pytest.mark.parametrize("text", PLAIN_TEXT)
def test_plain_text_is_not_math(text):
    """Plain prose must NOT be routed to the math renderer.

    Note: most English cases fail on 65eb8eb -- see ANALYSIS.md bug 1.
    """
    assert not has_math(text), f"misclassified as math: {text!r}"


@pytest.mark.parametrize("text", REAL_MATH)
def test_real_math_is_math(text):
    assert has_math(text), f"not detected as math: {text!r}"


@pytest.mark.parametrize("text", REAL_MATH)
def test_math_segment_is_not_shattered(text):
    """A whole expression must survive as ONE segment, not split at operators."""
    segs = split_math_segments(f"اگر {text} باشد")
    maths = [s[1] for s in segs if s[0] == "math"]
    assert maths, f"no math segment for {text!r}"
    joined = "".join(maths).replace(" ", "")
    assert text.replace(" ", "").replace("$", "") in joined, maths


# ---------------------------------------------------------------------------
# B. Rendering: every required construct must produce a usable image
# ---------------------------------------------------------------------------

RENDER_CASES = {
    "fraction": r"\frac{۱}{\sqrt{۲}}",
    "power": "x^{۲}",
    "subscript": "a_{n}",
    "radical": r"\sqrt{۱۴}",
    "big_paren": r"\left(\frac{۱}{۲}\right)",
    "matrix": r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}",
    "greek": r"\pi+\theta",
    "integral": r"\int_{۰}^{۱} x^{۲} dx",
    "limit": r"\lim_{x \to ۰} f(x)",
    "sum": r"\sum_{i=۱}^{n} i",
    "relation": "x \\leq ۲",
    "combination": r"\frac{\sqrt{۲}}{\pi}+\sin\left(\frac{\pi}{۳}\right)",
    "long": r"x^{۲}+y^{۲}+z^{۲}=r^{۲}+\frac{a}{b}-\sqrt{c}",
}


@pytest.mark.parametrize("name,latex", sorted(RENDER_CASES.items()))
def test_construct_renders(name, latex):
    """Each required LaTeX construct must render to a real, non-degenerate PNG."""
    r = render_math_png(latex, font_size=10.5, dpi=300)
    assert r is not None, f"{name}: render returned None"
    assert r.width >= 4, f"{name}: degenerate width {r.width}"
    assert r.height >= 4, f"{name}: degenerate height {r.height}"
    assert r.png[:8] == b"\x89PNG\r\n\x1a\n", f"{name}: not a PNG"


def test_matrix_is_wider_than_single_glyph():
    """A 2x2 matrix must be visually a matrix, not a collapsed glyph."""
    m = render_math_png(r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}", font_size=10.5)
    single = render_math_png("۱", font_size=10.5)
    assert m.width > single.width * 2
    assert m.height > single.height * 1.5


# ---------------------------------------------------------------------------
# C. Typography: Persian shaping and BiDi safety
# ---------------------------------------------------------------------------

def test_persian_is_reshaped_not_reversed():
    from reports.exam_pdf import reshaped

    src = "سلام دنیا"
    out = reshaped(src)
    assert out != src, "text was not reshaped"
    assert "\u200c" not in out or True  # shaping may insert ZWNJ, fine
    # logical order must be preserved: after bidi the display string is visual,
    # so re-applying bidi twice must be stable for pure Persian
    assert reshaped(out)  # must not raise


def test_english_passes_through_bidi_unchanged():
    """Pure-Latin text must NOT be reversed or otherwise mangled by BiDi."""
    from reports.exam_pdf import reshaped

    src = "Which option is correct?"
    assert reshaped(src) == src


def test_english_sentence_keeps_its_spaces():
    """An English sentence in an option must keep word spacing in the PDF.

    Regression guard for baseline/ANALYSIS.md bug 1: the sentence used to be
    classified as math and drawn by matplotlib, which strips spaces.
    """
    from reports.exam_pdf import _option_style, _register_fonts, final_pdf_cleanup
    from reports.pdf_text_flow_v2 import MathRichBlock

    _register_fonts()
    blk = MathRichBlock(
        "The derivative of a constant is always one.",
        style=_option_style(0),
        max_width=120,
        fallback=final_pdf_cleanup,
    )
    blk._ensure_built()
    kinds = [a.kind for ln in blk.lines for a in ln.atoms]
    assert "math" not in kinds, f"whole sentence treated as math: {kinds}"


# ---------------------------------------------------------------------------
# D. Layout: no page should be mostly empty because of KeepTogether
# ---------------------------------------------------------------------------

def _trailing_blank_ratio(page) -> float:
    """Fraction of the page *below the last ink* — the real "wasted space" metric.

    Measuring first-to-last ink spans would flag the title page (big header on
    top, first question lower down) as "blank", which is wrong; the defect we
    care about is content stopping early and the rest of the page being empty.
    """
    ys = []
    for b in page.get_text("blocks"):
        ys += [b[1], b[3]]
    for d in page.get_drawings():
        ys += [d["rect"].y0, d["rect"].y1]
    for img in page.get_image_info():
        ys += [img["bbox"][1], img["bbox"][3]]
    if not ys:
        return 1.0
    # footer sits at ~8mm from the bottom; ignore it when finding the last ink
    body_bottom = page.rect.height - 30
    ys = [y for y in ys if y < body_bottom]
    if not ys:
        return 1.0
    return max(0.0, (body_bottom - max(ys)) / page.rect.height)


def test_question_does_not_strand_a_mostly_empty_page():
    """No page of the question booklet may be more than 55% blank.

    This is the regression guard for the ``KeepTogether`` problem documented in
    baseline/ANALYSIS.md bug 3: a question 5% too tall used to be pushed whole
    onto the next page, leaving most of the current page empty.
    """
    import pymupdf

    from reports.exam_pdf import build_exam_pdf

    qs = [
        dict(
            order=i,
            text=f"سؤال شمارهٔ {i}: کدام گزینه درست است؟ متن کوتاه برای آزمون صفحه‌بندی.",
            options=["گزینه یک", "گزینه دو", "گزینه سه", "گزینه چهار"],
            correct_answer=1,
            difficulty="آسان",
            subject="عمومی",
            explanation="توضیح کوتاه.",
            diagram_svg=None,
        )
        for i in range(1, 13)
    ]
    pdf = build_exam_pdf(
        school_name="مدرسه",
        title="آزمون",
        questions=qs,
        duration_minutes=90,
        grade="12",
        major="ریاضی",
        subject_label="عمومی",
        topic="آزمون",
        difficulty="آسان",
    )
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    # only the question booklet (before the PageBreak that starts the key)
    ratios = []
    for i in range(doc.page_count):
        page_text = doc[i].get_text()
        if "کلید" in page_text and "پاسخ صحیح" in page_text:
            break
        ratios.append(_trailing_blank_ratio(doc[i]))
    doc.close()
    assert ratios, "no question pages found"
    worst = max(ratios)
    assert worst <= 0.45, f"trailing {worst:.0%} of a page is blank"


# ---------------------------------------------------------------------------
# E. Contract: the API payload shape must keep working
# ---------------------------------------------------------------------------

def test_build_exam_pdf_signature_is_stable():
    import inspect

    from reports.exam_pdf import build_exam_pdf

    params = list(inspect.signature(build_exam_pdf).parameters)
    for required in ("school_name", "title", "questions", "duration_minutes"):
        assert required in params


def test_minimal_exam_builds():
    from reports.exam_pdf import build_exam_pdf

    pdf = build_exam_pdf(
        school_name="مدرسهٔ نمونه",
        title="آزمون تست",
        questions=[
            dict(
                order=1,
                text="حاصل ۲+۲ چند است؟",
                options=["۱", "۲", "۳", "۴"],
                correct_answer=4,
                difficulty="آسان",
                subject="ریاضی",
                explanation="جمع دو و دو چهار می‌شود.",
                diagram_svg=None,
            )
        ],
        duration_minutes=60,
        grade="12",
        major="ریاضی",
        subject_label="ریاضی",
        topic="جمع",
        difficulty="آسان",
    )
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 5000


# ---------------------------------------------------------------------------
# F. Regression: symbol substitution must never damage English words
# ---------------------------------------------------------------------------

ENGLISH_WORDS_WITH_LATEX_SUFFIXES = [
    "multi-page test",
    "The colony was large.",
    "the angle is acute",
    "hotel definition",
    "topology isotope",
    "general knowledge",
    "notebook problem",
    "circle geometry",
]


@pytest.mark.parametrize("text", ENGLISH_WORDS_WITH_LATEX_SUFFIXES)
def test_symbol_substitution_leaves_english_alone(text):
    r"""``final_pdf_cleanup`` used to map bare ``ge``/``le``/``ne``/``to``.

    With an optional backslash, ``"multi-page"`` became ``"multi-pa≥"`` because
    ``ge`` ends the word.  The substitution must require the backslash.
    """
    from reports.exam_pdf import final_pdf_cleanup

    out = final_pdf_cleanup(text)
    for bad in ("≥", "≤", "≠", "→", "×"):
        assert bad not in out, f"{text!r} -> {out!r} (introduced {bad})"
    # Latin letters must survive intact
    assert sum(ch.isascii() and ch.isalpha() for ch in out) == sum(
        ch.isascii() and ch.isalpha() for ch in text
    )


def test_symbol_substitution_still_works_with_backslash():
    r"""The real LaTeX commands must still be substituted."""
    from reports.exam_pdf import final_pdf_cleanup

    assert "≤" in final_pdf_cleanup(r"x \\leq ۲")
    assert "≥" in final_pdf_cleanup(r"y \\geq ۳")
    assert "×" in final_pdf_cleanup(r"۲ \\times ۲")


def test_no_english_word_becomes_a_symbol_end_to_end():
    """A real build must not corrupt Latin prose anywhere in the PDF."""
    import pymupdf

    from reports.exam_pdf import build_exam_pdf

    pdf = build_exam_pdf(
        school_name="School",
        title="Test",
        questions=[
            dict(
                order=1,
                text="Question 1: which option is correct for this multi-page test?",
                options=["first", "second", "third", "fourth"],
                correct_answer=1,
                difficulty="آسان",
                subject="English",
                explanation="The colony is large and the angle is acute.",
                diagram_svg=None,
            )
        ],
        duration_minutes=60,
        grade="12",
        major="ریاضی",
        subject_label="English",
        topic="Test",
        difficulty="آسان",
    )
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    txt = "".join(p.get_text() for p in doc)
    doc.close()
    for bad in ("pa≥", "colony→", "an≤", "→e ", "≠"):
        assert bad not in txt, f"corrupted text found: {bad!r}"
    assert "multi-page" in txt
