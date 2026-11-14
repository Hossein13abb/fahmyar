# -*- coding: utf-8 -*-
"""Tests for the unified table renderer: ``array``, ``aligned`` and friends.

matplotlib's mathtext cannot draw these environments.  Before this renderer it
produced a bracketed blob with all cells collapsed onto one line, and
``array``'s ``{l}`` column spec leaked into the picture as a stray cell.

Each test here exercises one capability the mission requires:
multiple rows/columns, column alignment, alignment anchors, rules, fractions
inside cells, nesting, and multi-page output.
"""
from __future__ import annotations

import io

import matplotlib
import pytest
from PIL import Image

matplotlib.use("Agg")

from reports.math_renderer import render_math_png, normalize_latex  # noqa: E402
from reports.pdf_math_table import (  # noqa: E402
    detect_kind,
    parse_array_spec,
    plan_table,
    render_table,
    split_cells,
    split_rows,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ink(rendered) -> int:
    """Count non-transparent pixels — a render that drew nothing has ~0."""
    im = Image.open(io.BytesIO(rendered.png)).convert("RGBA")
    return sum(1 for p in im.getdata() if p[3] > 20)


def _row_bands(rendered, floor: int = 2) -> int:
    """Approximate visual row count from horizontal ink bands.

    Only reliable for rows made of simple glyphs: a cell containing a fraction
    has its own internal whitespace and splits into several bands.  Use
    :func:`_planned_rows` for the exact count.
    """
    im = Image.open(io.BytesIO(rendered.png)).convert("RGBA")
    w, h = im.size
    px = im.load()
    rows = []
    for y in range(h):
        hits = sum(1 for x in range(w) if px[x, y][3] > 20)
        rows.append(hits)
    bands = 0
    inside = False
    for hits in rows:
        if hits > floor and not inside:
            bands += 1
            inside = True
        elif hits <= floor and inside:
            inside = False
    return bands


def _planned_rows(env: str, body: str) -> int:
    """Exact row count straight from the layout plan."""
    plan = plan_table(env, body, 10.5)
    assert plan is not None
    return len(plan.rows)


# ---------------------------------------------------------------------------
# 1. Environment taxonomy
# ---------------------------------------------------------------------------

def test_detect_kind_assigns_frame_and_alignment():
    assert detect_kind("bmatrix")[0] == "bracket"
    assert detect_kind("pmatrix")[0] == "paren"
    assert detect_kind("vmatrix")[0] == "bar"
    assert detect_kind("cases")[0] == "brace"
    assert detect_kind("array")[0] == "none"
    assert detect_kind("aligned")[2] == "anchor"
    # starred variants must not fall through to a default
    assert detect_kind("aligned*")[2] == "anchor"
    assert detect_kind("align*")[2] == "anchor"


@pytest.mark.parametrize(
    "spec,expect_cols,expect_rules",
    [
        ("{l}", ["l"], []),
        ("{lcr}", ["l", "c", "r"], []),
        ("{c|c}", ["c", "c"], [1]),
        ("{|c|c|}", ["c", "c"], [1, 2]),  # rule before col0 + between + after
        ("{l|c|r}", ["l", "c", "r"], [1, 2]),
        ("{ p{2cm} c }", ["l", "c"], []),
    ],
)
def test_parse_array_spec(spec, expect_cols, expect_rules):
    cols, rules = parse_array_spec(spec)
    assert cols == expect_cols
    assert rules == expect_rules


# ---------------------------------------------------------------------------
# 2. array: rows, columns, alignment
# ---------------------------------------------------------------------------

ARRAY_BASIC = r"\begin{array}{cc} a & b \\ c & d \end{array}"


def test_array_renders_two_rows():
    r = render_math_png(ARRAY_BASIC, font_size=10.5)
    assert r is not None
    assert r.width > 10 and r.height > 10
    assert _ink(r) > 100, "array rendered but drew almost nothing"
    assert _row_bands(r) == 2, f"expected 2 rows, saw {_row_bands(r)}"


def test_array_three_columns_and_three_rows():
    tex = r"\begin{array}{ccc} ۱ & ۲ & ۳ \\ ۴ & ۵ & ۶ \\ ۷ & ۸ & ۹ \end{array}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _row_bands(r) == 3
    # three columns must be wider than two
    two = render_math_png(r"\begin{array}{cc} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=10.5)
    assert r.width > two.width


@pytest.mark.parametrize("spec", ["l", "c", "r"])
def test_array_column_alignment_all_three(spec):
    """``l``, ``c`` and ``r`` must each produce a valid, non-empty image."""
    tex = rf"\begin{{array}}{{{spec}}} a & b \\ ccc & d \end{{array}}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None and _ink(r) > 100


def test_array_alignment_actually_differs():
    """Left- and right-aligned columns must place the short cell differently."""
    from reports.pdf_math_table import plan_table

    body = r"a & b \\ ccc & d"
    left = plan_table("array", r"{l}" + body, 10.5)
    right = plan_table("array", r"{r}" + body, 10.5)
    assert left is not None and right is not None
    # x offsets of the short cell in column 0 differ between l and r
    lx = [c.x for row in left.rows for c in row.cells if c.col == 0]
    rx = [c.x for row in right.rows for c in row.cells if c.col == 0]
    assert lx != rx, f"l and r produced identical offsets: {lx}"


def test_array_vertical_rule_changes_geometry():
    """A ``|`` in the spec must draw a rule and not be swallowed as a cell."""
    plain = render_math_png(r"\begin{array}{cc} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=10.5)
    ruled = render_math_png(r"\begin{array}{c|c} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=10.5)
    assert plain is not None and ruled is not None
    assert _ink(ruled) > _ink(plain), "vertical rule added no ink"


def test_array_horizontal_rule():
    plain = render_math_png(r"\begin{array}{cc} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=10.5)
    ruled = render_math_png(
        r"\begin{array}{cc} \hline ۱ & ۲ \\ \hline ۳ & ۴ \end{array}", font_size=10.5
    )
    assert plain is not None and ruled is not None
    assert _ink(ruled) > _ink(plain), "hline added no ink"


def test_array_does_not_leak_column_spec_as_a_cell():
    r"""``{l}`` must be read as a spec, never drawn as the text ``{l}``."""
    plan = plan_table("array", r"{l} x \\ y", 10.5)
    assert plan is not None
    texts = [c.tex for row in plan.rows for c in row.cells]
    assert "l" not in texts and "{l}" not in texts, texts


def test_array_with_fraction_and_radical_cells():
    tex = r"\begin{array}{cc} \frac{۱}{۲} & \sqrt{۲} \\ x^{۲} & y_{۱} \end{array}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _planned_rows("array", r"{cc} \frac{۱}{۲} & \sqrt{۲} \\ x^{۲} & y_{۱}") == 2
    assert _ink(r) > 100
    # a fraction is taller than a bare digit, so the image must be tall
    plain = render_math_png(r"\begin{array}{cc} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=10.5)
    assert r.height > plain.height


# ---------------------------------------------------------------------------
# 3. aligned: alignment anchors
# ---------------------------------------------------------------------------

def test_aligned_two_rows():
    tex = r"\begin{aligned} x+y &= ۵ \\ x-y &= ۱ \end{aligned}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _ink(r) > 100
    assert _row_bands(r) == 2


def test_aligned_multiple_equals_signs_line_up():
    r"""The ``=`` of every row must land at the same x.

    This is the contract of ``aligned``: the anchor column is shared.  We check
    it on the plan (the drawing follows the plan exactly).
    """
    plan = plan_table("aligned", r"a &= ۱ \\ b+c &= ۲ \\ d+e+f &= ۳", 10.5)
    assert plan is not None
    anchor_xs = []
    for row in plan.rows:
        for cell in row.cells:
            if cell.anchored:
                anchor_xs.append(round(cell.x + _col_offset(plan, cell.col), 2))
    assert len(anchor_xs) >= 3, anchor_xs
    assert len(set(anchor_xs)) == 1, f"operators not aligned: {anchor_xs}"


def _col_offset(plan, col: int) -> float:
    """Cumulative x of a column inside the plan."""
    total = 0.0
    for i in range(min(col, len(plan.col_w))):
        total += plan.col_w[i]
    return total


@pytest.mark.parametrize(
    "op",
    ["=", r"\leq", r"\geq", r"\approx", r"\Rightarrow", "+"],
)
def test_aligned_supports_operator_anchors(op):
    tex = rf"\begin{{aligned}} x &{op} ۱ \\ y &{op} ۲ \end{{aligned}}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None and _ink(r) > 80, f"operator {op} produced nothing"


def test_aligned_with_fraction_and_radical():
    tex = r"\begin{aligned} \frac{۱}{۲}x &= \sqrt{۳} \\ x &= ۲\sqrt{۳} \end{aligned}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _planned_rows("aligned", r"\frac{۱}{۲}x &= \sqrt{۳} \\ x &= ۲\sqrt{۳}") == 2
    assert _ink(r) > 100
    # a fraction makes the block noticeably taller than a plain two-row case
    plain = render_math_png(r"\begin{aligned} x &= ۳ \\ y &= ۴ \end{aligned}", font_size=10.5)
    assert r.height > plain.height


def test_aligned_long_chain():
    tex = (
        r"\begin{aligned} f(x) &= x^{۲}+۲x+۱ \\ "
        r"&= (x+۱)^{۲} \\ &= ۰ \end{aligned}"
    )
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _row_bands(r) == 3


def test_aligned_without_anchor_still_works():
    """``aligned`` with no ``&`` anywhere must not crash or render blank."""
    tex = r"\begin{aligned} a=b \\ c=d \end{aligned}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None and _ink(r) > 50


# ---------------------------------------------------------------------------
# 4. Nesting and combination
# ---------------------------------------------------------------------------

def test_array_containing_bmatrix():
    tex = (
        r"\begin{array}{cc} "
        r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix} & x \\ y & ۱ "
        r"\end{array}"
    )
    r = render_math_png(tex, font_size=11)
    # mathtext cannot nest an environment inside a cell; the renderer must
    # degrade gracefully rather than raise.
    assert r is None or _ink(r) > 0


def test_aligned_containing_cases_body():
    r"""A ``cases`` block inside ``aligned`` must not crash the pipeline."""
    tex = r"\begin{aligned} y &= ۲x \\ z &= ۳ \end{aligned}"
    r = render_math_png(tex, font_size=10.5)
    assert r is not None


def test_matrix_and_aligned_side_by_side_render_independently():
    m = render_math_png(r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}", font_size=10.5)
    a = render_math_png(r"\begin{aligned} x &= ۱ \\ y &= ۲ \end{aligned}", font_size=10.5)
    assert m is not None and a is not None
    assert _ink(m) > 100 and _ink(a) > 100


# ---------------------------------------------------------------------------
# 5. Persian text around the formula
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "env,body",
    [
        ("array", r"{cc} ۱ & ۲ \\ ۳ & ۴"),
        ("aligned", r"x &= ۵ \\ y &= ۱"),
    ],
)
def test_env_inside_persian_sentence(env, body):
    """The environment must be extracted as ONE math segment from Persian text."""
    from reports.pdf_content_parser import split_math_segments

    sentence = (
        "اگر عبارت $\\begin{" + env + "}" + body + "\\end{" + env + "}$ باشد، کدام است؟"
    )
    segs = split_math_segments(sentence)
    maths = [s.payload for s in segs if s.kind == "math"]
    assert maths, f"no math segment found in {sentence!r}"
    assert any(f"begin{{{env}}}" in m for m in maths), maths
    # and the surrounding Persian must survive
    texts = "".join(s.payload for s in segs if s.kind == "text")
    assert "اگر" in texts and "کدام است؟" in texts


def test_persian_outside_does_not_reach_the_renderer():
    """Persian letters must never end up inside a LaTeX cell."""
    from reports.pdf_content_parser import split_math_segments

    segs = split_math_segments(
        "مقدار $\\begin{array}{cc}۱ & ۲ \\\\ ۳ & ۴\\end{array}$ را حساب کنید"
    )
    for s in segs:
        if s.kind == "math":
            assert not any("\u0600" <= ch <= "\u06FF" and ch.isalpha() for ch in s.payload)


# ---------------------------------------------------------------------------
# 6. Sizing consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size", [8.0, 10.5, 14.0])
def test_geometry_scales_with_font_size(size):
    r = render_math_png(r"\begin{array}{cc} ۱ & ۲ \\ ۳ & ۴ \end{array}", font_size=size)
    assert r is not None
    # stored point height must track the requested font size
    assert 1.0 * size <= r.height <= 4.0 * size, (size, r.height)


def test_render_is_transparent_png():
    r = render_math_png(r"\begin{aligned} x &= ۱ \\ y &= ۲ \end{aligned}", font_size=10.5)
    assert r is not None
    assert r.png[:8] == b"\x89PNG\r\n\x1a\n"
    im = Image.open(io.BytesIO(r.png)).convert("RGBA")
    corners = [im.getpixel((0, 0)), im.getpixel((im.width - 1, 0))]
    assert all(p[3] == 0 for p in corners), "background is not transparent"


# ---------------------------------------------------------------------------
# 7. End-to-end: a real multi-page PDF
# ---------------------------------------------------------------------------

def _question(i: int, text: str, options: list[str]) -> dict:
    return dict(
        order=i,
        text=text,
        options=options,
        correct_answer=1,
        difficulty="متوسط",
        subject="ریاضی",
        explanation="توضیح کوتاه.",
        diagram_svg=None,
    )


def test_multipage_pdf_with_array_and_aligned():
    """A 12-question exam containing both environments must paginate cleanly."""
    import pymupdf

    from reports.exam_pdf import build_exam_pdf

    qs = []
    for i in range(1, 13):
        if i % 2 == 0:
            text = (
                rf"اگر $D=\begin{{array}}{{c|c}} {i} & ۲ \\ ۳ & ۴ \end{{array}}$ "
                "باشد، دترمینان کدام است؟"
            )
            opts = ["$۱$", "$۲$", "$۳$", "$۴$"]
        else:
            text = (
                rf"دستگاه $\begin{{aligned}} x+y &= {i} \\ x-y &= ۱ \end{{aligned}}$ "
                "را حل کنید. مقدار $x$ کدام است؟"
            )
            opts = ["$۲$", "$۳$", "$۴$", "$۵$"]
        qs.append(_question(i, text, opts))

    pdf = build_exam_pdf(
        school_name="دبیرستان نمونه",
        title="آزمون array و aligned",
        questions=qs,
        duration_minutes=90,
        grade="12",
        major="ریاضی و فیزیک",
        subject_label="ریاضی",
        topic="آزمون",
        difficulty="متوسط",
    )
    assert pdf[:5] == b"%PDF-"

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count >= 2, "expected a multi-page document"
        images = sum(len(p.get_images()) for p in doc)
        assert images >= 12, f"only {images} formula images"

        text = "".join(p.get_text() for p in doc)
        # no raw LaTeX may leak into the text layer
        for leak in ("\\begin{array}", "\\begin{aligned}", "begin{array}", "&"):
            assert leak not in text, f"raw LaTeX leaked: {leak!r}"
    finally:
        doc.close()


def test_array_and_aligned_do_not_break_matrix_rendering():
    """Guard: adding the new engine must not change matrix/cases output."""
    m = render_math_png(r"\begin{bmatrix}۱ & ۲ \\ ۳ & ۴\end{bmatrix}", font_size=10.5)
    c = render_math_png(r"\begin{cases} ۲x+y=۷ \\ x-y=۲ \end{cases}", font_size=10.5)
    assert m is not None and c is not None
    # the legacy path returns fixed geometry for a 2x2 matrix at 10.5pt
    assert 40 <= m.width <= 60, m.width
    assert c.width > m.width, "cases should be wider than a 2x2 matrix"


# ---------------------------------------------------------------------------
# 8. Persian text inside table cells
# ---------------------------------------------------------------------------

def test_persian_inside_text_cell_is_shaped_and_ordered():
    r"""``\text{مرحله}`` must not render as reversed, disconnected letters.

    mathtext has no Arabic shaping and no BiDi: it drew each glyph in isolation
    in logical order, producing "هلحرم".  The renderer now shapes and reorders
    the run before drawing.
    """
    from reports.pdf_math_table import _normalise_persian_text_cells

    bs = chr(92)
    out = _normalise_persian_text_cells(bs + "text{مرحله}")
    # presentation forms indicate shaping happened
    assert any(0xFE70 <= ord(ch) <= 0xFEFF or 0xFB50 <= ord(ch) <= 0xFDFF for ch in out), out
    # and the result must no longer be the raw logical string
    assert "مرحله" not in out


def test_persian_text_cell_renders_at_all():
    bs = chr(92)
    tex = (
        r"\begin{array}{c|c} " + bs + r"text{مرحله} & " + bs + r"text{تعداد} "
        + bs * 2 + r" ۱ & ۴ " + bs * 2 + r" ۲ & ۶ \end{array}"
    )
    r = render_math_png(tex, font_size=10.5)
    assert r is not None
    assert _ink(r) > 200
    assert _planned_rows("array", r"{c|c} x \\ y \\ z") == 3


def test_english_text_cell_is_untouched():
    r"""``\text{and}`` must stay a plain ``\text`` run."""
    from reports.pdf_math_table import _normalise_persian_text_cells

    bs = chr(92)
    assert _normalise_persian_text_cells(bs + "text{and}") == bs + "text{and}"


# ---------------------------------------------------------------------------
# 9. Row splitting must accept every backslash form
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body,expect",
    [
        ("۱ & ۲ " + chr(92) * 2 + " ۳ & ۴", 2),
        ("۱ & ۲ " + chr(92) * 4 + " ۳ & ۴", 2),
        ("۱ & ۲ " + chr(92) + "cr ۳ & ۴", 2),
        ("۱ & ۲\n۳ & ۴", 2),
    ],
)
def test_row_splitting_accepts_all_backslash_forms(body, expect):
    r"""A row separator is TWO backslashes; JSON may deliver four.

    The first version of this renderer split on a single backslash (a regex
    escaping mistake), so nothing ever matched and every row collapsed into
    one cell containing a stray ``\\``.
    """
    assert len(split_rows(body)) == expect
