# -*- coding: utf-8 -*-
"""Unified table renderer for every multi-row LaTeX environment.

Why one renderer instead of four
--------------------------------
matplotlib's mathtext does not draw ``bmatrix``/``pmatrix``/``vmatrix``,
``cases``, ``array`` or ``aligned``.  Historically each was handled by its own
ad-hoc function (and one of them drew a 26x26 blob for ``cases``), which meant
four separate sets of bugs around cell width, vertical rhythm and RTL prefixes.

This module replaces all of them with a single layout engine:

    1. split the body into rows on ``\\\\`` (and its JSON-damaged variants)
    2. split each row into cells on ``&``
    3. decide a column role per cell: ordinary, alignment-anchor, or operator
    4. measure every cell with mathtext's own metrics
    5. size the columns from those measurements
    6. draw each cell at its computed baseline
    7. draw the frame: brackets (matrix), brace (cases), or rules (array)

The result is one code path with one set of metrics, so a fix to vertical
rhythm helps every environment at once.

``aligned`` gets an extra step: cells are split further at alignment anchors
(``&``) and operators (``=``, ``\\leq``, ...) so that the anchor column lines
up vertically and the operator sits at a consistent x across rows.  That is
the visual contract of ``aligned``.

Everything here works in *points*; matplotlib figures are created at
``figsize = points / 72`` so cell sizes track ``font_size`` exactly.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser

from reports.math_renderer import RenderedMath, _to_latin_digits
from reports.pdf_typography import has_rtl, shape, visual

__all__ = [
    "TableSpec",
    "Cell",
    "Row",
    "ENV_KINDS",
    "parse_array_spec",
    "detect_kind",
    "render_table",
]

# ---------------------------------------------------------------------------
# Environment taxonomy
# ---------------------------------------------------------------------------

#: env name -> (frame style, default column spec, alignment behaviour)
#:   "bracket" : [ ]      "paren": ( )     "bar": | |
#:   "brace"   : {  (right side, RTL)
#:   "none"    : no frame (aligned / gathered / split)
ENV_KINDS = {
    "matrix": ("none", None, "center"),
    "bmatrix": ("bracket", None, "center"),
    "pmatrix": ("paren", None, "center"),
    "vmatrix": ("bar", None, "center"),
    "Vmatrix": ("double_bar", None, "center"),
    "Bmatrix": ("brace_pair", None, "center"),
    "smallmatrix": ("none", None, "center"),
    "array": ("none", None, "spec"),
    "cases": ("brace", None, "left"),
    "dcases": ("brace", None, "left"),
    "rcases": ("brace_left", None, "left"),
    "aligned": ("none", None, "anchor"),
    "align": ("none", None, "anchor"),
    "align*": ("none", None, "anchor"),
    "alignedat": ("none", None, "anchor"),
    "gathered": ("none", None, "center"),
    "split": ("none", None, "anchor"),
    "eqnarray": ("none", None, "anchor"),
}

_MATRIX_FAMILY = ("matrix", "bmatrix", "pmatrix", "vmatrix", "Vmatrix", "Bmatrix", "smallmatrix")
_FRAMED = {"bracket", "paren", "bar", "double_bar", "brace_pair", "brace", "brace_left"}


def detect_kind(env: str) -> Tuple[str, Optional[str], str]:
    """Return ``(frame, spec, align_mode)`` for an environment name."""
    e = (env or "").strip().rstrip("*")
    # alignment suffixes such as ``aligned*`` keep their base behaviour
    if e in ENV_KINDS:
        return ENV_KINDS[e]
    for base in ("aligned", "align", "gathered", "split"):
        if e.startswith(base):
            return ENV_KINDS.get(base, ("none", None, "anchor"))
    if e.endswith("matrix"):
        return ENV_KINDS.get(e, ("none", None, "center"))
    return ("none", None, "center")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_array_spec(spec: str) -> Tuple[List[str], List[int]]:
    r"""Parse a column spec like ``{l c c | r}`` into roles and rule columns.

    Returns ``(columns, rules)`` where ``columns`` is a list of ``"l"``/``"c"``/
    ``"r"`` and ``rules`` holds the *boundary indices* that draw a vertical line
    (e.g. ``1`` means "between column 0 and column 1").

    Supports ``l``, ``c``, ``r``, ``|`` and ignores ``@{}`` / ``p{..}`` noise by
    falling back to ``l``.
    """
    s = (spec or "").strip().strip("{}")
    columns: List[str] = []
    rules: List[int] = []
    pending_rule = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in " \t":
            i += 1
            continue
        if ch == "|":
            pending_rule = True
            i += 1
            continue
        if ch in "lcr":
            if pending_rule and columns:
                rules.append(len(columns))
            pending_rule = False
            columns.append(ch)
            i += 1
            continue
        if ch in "pmbX@":
            # p{2cm} / @{...} — consume the brace group, treat as left-aligned
            depth = 0
            j = i
            while j < len(s):
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            if pending_rule and columns:
                rules.append(len(columns))
            pending_rule = False
            columns.append("l")
            i = j
            continue
        i += 1
    if pending_rule and columns:
        rules.append(len(columns))
    return (columns or ["c"]), rules


#: ``\hline`` / ``\cline{..}`` / ``\toprule`` etc. inside array bodies
_HLINE_RE = re.compile(r"\\(?:hline|cline\s*\{[^}]*\}|toprule|midrule|bottomrule|hdashline)\b")

#: operators that ``aligned`` aligns on
_ALIGN_OP_RE = re.compile(
    r"^(<=|>=|==|:=|=|<|>|\\le|\\leq|\\ge|\\geq|\\ne|\\neq|\\approx|\\equiv|\\sim|\\propto|"
    r"\\rightarrow|\\leftarrow|\\Rightarrow|\\Leftarrow|\\implies|\\iff|"
    r"\+|-|\\pm|\\mp|\\times|\\div|\\cdot|/|%|\\cup|\\cap|\\subset|\\in)\b"
)
_LEADING_OP_RE = re.compile(
    r"^\s*(=|\\leq|\\geq|\\le|\\ge|\\ne|\\neq|<|>|\\approx|\\equiv|\\sim|"
    r"\+|-|\\pm|\\mp|\\times|\\cdot|\\div|\\rightarrow|\\Rightarrow|\\implies|\\iff|"
    r"\\leftarrow|\\Leftarrow)\s*"
)

#: a bare ``{l}`` that follows ``\begin{array}`` should not become a cell
_ARRAY_SPEC_RE = re.compile(r"^\s*\{([^{}]*)\}\s*", re.S)


def split_rows(body: str) -> List[str]:
    r"""Split an environment body into rows on ``\\``.

    ``\\`` is a *double* backslash in the LaTeX source.  JSON escaping can
    deliver four of them (``\\\\``), which the naive ``re.split`` above turned
    into a literal ``\\`` inside a single row — so "۲ & ۳ \\\\ ۴ & ۵" became one
    row whose cells contained a stray backslash.  We normalise any run of two or
    more backslashes to exactly two first, then split on that.

    Also handles ``\cr``, ``\newline`` and a literal newline, all of which
    language models emit.
    """
    s = str(body or "")
    # A row separator in the LaTeX source is TWO literal backslashes.  The
    # pattern is assembled from chr(92) so no layer of string escaping can
    # silently turn it into "a single backslash" (which never matches and
    # collapsed every row into one cell).
    B = chr(92)
    two = B * 2
    s = re.compile(B + "{2,}").sub(two, s)      # 3+ backslashes -> exactly 2
    pattern = (
        re.escape(two)
        + "|" + re.escape(B + "cr") + r"\b"
        + "|" + re.escape(B + "newline") + r"\b"
        + r"|\r?\n"
    )
    parts = re.split(pattern, s)
    return [p for p in (x.strip() for x in parts) if p]


def split_cells(row: str) -> List[str]:
    """Split a row on unescaped ``&``."""
    return [c.strip() for c in re.split(r"(?<!\\)&", str(row or ""))]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    """One drawn fragment inside a row."""

    tex: str = ""
    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    #: column index this cell occupies
    col: int = 0
    #: how to place it inside its column
    align: str = "c"          # l | c | r
    #: x offset within the column, filled in by layout
    x: float = 0.0
    #: draw at the anchor line (used by aligned so the operator is flush)
    anchored: bool = False


@dataclass
class Row:
    cells: List[Cell] = field(default_factory=list)
    height: float = 0.0
    depth: float = 0.0
    #: extra vertical gap before this row (``\\hline`` or an explicit ``\\[...]``)
    gap_before: float = 0.0
    #: horizontal rules drawn under *previous* rows at these column boundaries
    hline_after_previous: bool = False


@dataclass
class TableSpec:
    """Fully measured plan for one table image."""

    frame: str = "none"
    align_mode: str = "center"
    columns: List[str] = field(default_factory=lambda: ["c"])
    col_w: List[float] = field(default_factory=list)
    v_rules: List[int] = field(default_factory=list)
    rows: List[Row] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    prefix: str = ""
    suffix: str = ""
    prefix_w: float = 0.0
    suffix_w: float = 0.0


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

#: ``\text{...}`` / ``\mathrm{...}`` holding Persian.  mathtext draws each
#: glyph in isolation and never applies Arabic shaping or BiDi, so "مرحله"
#: came out as "هلحرم" with disconnected letters.  We reshape and reorder the
#: run here and hand mathtext an already-visual string wrapped in \mathrm so it
#: at least renders the correct glyph shapes in the correct order.
_TEXT_CMD_RE = re.compile(r"\\(?:text|textrm|mathrm|operatorname)\s*\{([^{}]*)\}")


def _normalise_persian_text_cells(tex: str) -> str:
    r"""Prepare Persian inside ``\text{...}`` for mathtext.

    Returns a string where each Persian ``\text{}`` argument has been shaped
    (contextual letter joining) and BiDi-reordered, then re-emitted as a plain
    ``\mathrm{...}`` run.  Non-Persian arguments are left untouched so ordinary
    ``\text{and}`` keeps working.
    """

    def _fix(m: re.Match) -> str:
        inner = m.group(1)
        if not has_rtl(inner):
            return m.group(0)
        # shape() joins the letters, visual() reorders them right-to-left
        prepared = visual(inner)
        return r"\mathrm{" + prepared + "}"

    return _TEXT_CMD_RE.sub(_fix, tex)


_PARSER = MathTextParser("path")
_MEASURE_CACHE: dict = {}


def _measure(tex: str, font_size: float) -> Tuple[float, float, float]:
    """Return ``(width, height, depth)`` of ``$tex$`` in points."""
    key = (tex, round(font_size, 2))
    hit = _MEASURE_CACHE.get(key)
    if hit is not None:
        return hit
    w = h = d = 0.0
    if tex.strip():
        try:
            parsed = _PARSER.parse(
                f"${tex}$", dpi=72, prop=FontProperties(size=font_size)
            )
            if isinstance(parsed, tuple):
                w, h, d = float(parsed[0]), float(parsed[1]), float(parsed[2])
            else:
                w = float(parsed.width)
                h = float(parsed.height)
                d = float(parsed.depth)
        except Exception:
            # fall back to a rough estimate so layout still works
            w = len(tex) * font_size * 0.55
            h = font_size * 0.72
            d = font_size * 0.18
    out = (w, h, d)
    if len(_MEASURE_CACHE) < 8192:
        _MEASURE_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _split_aligned_pieces(cell_text: str) -> List[Tuple[str, bool]]:
    """Split one aligned cell into ``(fragment, is_operator)`` pieces.

    ``x+y &= ۵`` arrives here as two cells already split on ``&``: ``x+y`` and
    ``= ۵``.  We further separate a leading operator so it can be placed in its
    own narrow column, which is what makes the ``=`` of every row line up.
    """
    s = (cell_text or "").strip()
    if not s:
        return []
    m = _LEADING_OP_RE.match(s)
    if m:
        op = m.group(1)
        rest = s[m.end():].strip()
        out = [(op, True)]
        if rest:
            out.append((rest, False))
        return out
    return [(s, False)]


def plan_table(
    env: str,
    body: str,
    font_size: float,
    prefix: str = "",
    suffix: str = "",
) -> Optional[TableSpec]:
    """Measure everything and return a drawable plan (no rendering yet)."""
    fs = float(font_size)
    frame, spec_from_env, align_mode = detect_kind(env)

    text = str(body or "")
    has_hline = bool(_HLINE_RE.search(text))
    text = _HLINE_RE.sub(" ", text)

    # ``\begin{array}{lcr}`` — the spec belongs to the environment, not to row 0
    columns: List[str] = []
    v_rules: List[int] = []
    if env.strip().rstrip("*") in ("array", "alignedat", "eqnarray"):
        m = _ARRAY_SPEC_RE.match(text)
        if m:
            columns, v_rules = parse_array_spec(m.group(1))
            text = text[m.end():]

    raw_rows = split_rows(text)
    if not raw_rows:
        return None

    rows: List[Row] = []
    for ri, raw in enumerate(raw_rows):
        cells_text = split_cells(raw)
        row = Row()
        ci = 0
        for ct in cells_text:
            ct = _to_latin_digits(ct.strip())
            ct = _normalise_persian_text_cells(ct)
            if align_mode == "anchor":
                pieces = _split_aligned_pieces(ct)
                if not pieces:
                    ci += 1
                    continue
                for frag, is_op in pieces:
                    w, h, d = _measure(frag, fs)
                    row.cells.append(
                        Cell(tex=frag, width=w, height=h, depth=d, col=ci, anchored=is_op)
                    )
                    ci += 1
            else:
                w, h, d = _measure(ct, fs)
                row.cells.append(Cell(tex=ct, width=w, height=h, depth=d, col=ci))
                ci += 1
        if not row.cells:
            continue
        row.height = max(c.height for c in row.cells) if row.cells else fs
        row.depth = max(c.depth for c in row.cells) if row.cells else 0.0
        if has_hline and ri > 0:
            row.hline_after_previous = True
        rows.append(row)

    if not rows:
        return None

    ncols = max((c.col for r in rows for c in r.cells), default=0) + 1

    # ---- column widths ---------------------------------------------------
    if align_mode == "spec" and columns:
        # respect the LaTeX column spec; widths come from content
        pass
    elif align_mode == "anchor":
        columns = ["r"] * ncols
    else:
        columns = ["c"] * ncols
    while len(columns) < ncols:
        columns.append("c")

    col_w = [0.0] * ncols
    for row in rows:
        for c in row.cells:
            if c.col < ncols:
                col_w[c.col] = max(col_w[c.col], c.width)

    # alignment: shift cells inside their column boxes
    for row in rows:
        for c in row.cells:
            if c.col >= ncols:
                continue
            box = col_w[c.col]
            mode = columns[c.col] if c.col < len(columns) else "c"
            if mode == "l":
                c.x = 0.0
            elif mode == "r":
                c.x = box - c.width
            else:
                c.x = (box - c.width) / 2.0

    # ---- row metrics -----------------------------------------------------
    pad = fs * 0.20
    for row in rows:
        row.height = max((c.height for c in row.cells), default=fs * 0.72)
        row.depth = max((c.depth for c in row.cells), default=fs * 0.18)

    # leading/trailing spacing so fractions don't touch neighbours
    row_gap = fs * 0.34
    total_cells_h = sum(r.height + r.depth for r in rows) + row_gap * max(len(rows) - 1, 0)

    # Column separation: LaTeX uses 2 x arraycolsep (~0.55em each side) for
    # matrix-like grids, which is what makes a 2x2 matrix read as a matrix
    # rather than two glued digits.  Aligned/array grids stay tighter.
    if align_mode in ("center",) and frame in _FRAMED:
        col_sep = fs * 1.10
    elif align_mode == "anchor":
        col_sep = fs * 0.72
    else:
        col_sep = fs * 0.80
    inner_w = sum(col_w) + col_sep * max(ncols - 1, 0)

    # ---- frame / prefix sizing ------------------------------------------
    prefix_w = _measure(prefix, fs)[0] + fs * 0.35 if prefix else 0.0
    suffix_w = _measure(suffix, fs)[0] + fs * 0.35 if suffix else 0.0

    br_w = 0.0
    if frame in ("bracket", "paren"):
        br_w = fs * 0.30
    elif frame == "bar":
        br_w = fs * 0.16
    elif frame == "double_bar":
        br_w = fs * 0.30
    elif frame in ("brace_pair",):
        br_w = fs * 0.30
    elif frame in ("brace", "brace_left"):
        br_w = fs * 0.95

    total_w = inner_w + 2 * (pad + br_w) + prefix_w + suffix_w
    total_h = total_cells_h + 2 * pad

    return TableSpec(
        frame=frame,
        align_mode=align_mode,
        columns=columns,
        col_w=col_w,
        v_rules=v_rules,
        rows=rows,
        width=total_w,
        height=total_h,
        # The image's bottom edge already contains `pad`, so the distance from
        # the baseline down to that edge is just the last row's descent.  Using
        # max(row.depth)+pad (the old value) pushed the image ~2pt too high and
        # made inline arrays sit above the surrounding text.
        depth=rows[-1].depth,
        prefix=prefix,
        suffix=suffix,
        prefix_w=prefix_w,
        suffix_w=suffix_w,
    )


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _draw_brace(ax, x: float, top: float, bot: float, width: float, color: str, lw: float, mirrored: bool = False) -> None:
    r"""Draw a tall ``{`` (or ``}`` when ``mirrored``) at ``x``."""
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    mid = (top + bot) / 2.0
    sgn = -1.0 if not mirrored else 1.0
    verts = [
        (x, top),
        (x + sgn * width * 0.75, top),
        (x + sgn * width * 0.32, top - (top - bot) * 0.18),
        (x + sgn * width * 0.32, mid + (top - mid) * 0.10),
        (x + sgn * width * 0.95, mid),
        (x + sgn * width * 0.32, mid - (mid - bot) * 0.10),
        (x + sgn * width * 0.32, bot + (top - bot) * 0.18),
        (x + sgn * width * 0.75, bot),
        (x, bot),
    ]
    codes = [
        MplPath.MOVETO, MplPath.CURVE3, MplPath.CURVE3,
        MplPath.LINETO, MplPath.CURVE3,
        MplPath.LINETO, MplPath.CURVE3, MplPath.CURVE3, MplPath.MOVETO,
    ]
    ax.add_patch(PathPatch(MplPath(verts, codes), fill=False, edgecolor=color, lw=lw))


def render_table(
    env: str,
    body: str,
    font_size: float,
    dpi: int,
    color: str,
    prefix: str = "",
    suffix: str = "",
) -> Optional[RenderedMath]:
    """Draw a multi-row environment to a transparent PNG sized in points."""
    import matplotlib.pyplot as plt

    plan = plan_table(env, body, font_size, prefix=prefix, suffix=suffix)
    if plan is None:
        return None

    fs = float(font_size)
    fig = None
    try:
        fig = plt.figure(figsize=(plan.width / 72.0, plan.height / 72.0), dpi=dpi)
        fig.patch.set_alpha(0.0)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, plan.width)
        ax.set_ylim(0, plan.height)
        ax.set_axis_off()

        pad = fs * 0.20
        br_w = 0.0
        if plan.frame in ("bracket", "paren", "brace_pair", "double_bar"):
            br_w = fs * 0.30
        elif plan.frame == "bar":
            br_w = fs * 0.16
        elif plan.frame in ("brace", "brace_left"):
            br_w = fs * 0.95

        # geometry: x grows left->right; prefix sits at the LEFT of the drawing
        # because in the RTL document ``A=`` appears before the matrix.
        content_left = pad + br_w + plan.suffix_w
        content_top = plan.height - pad
        row_gap = fs * 0.34

        # column x offsets
        if plan.align_mode == "center" and plan.frame in _FRAMED:
            col_sep = fs * 1.10
        elif plan.align_mode == "anchor":
            col_sep = fs * 0.72
        else:
            col_sep = fs * 0.80
        col_x = []
        x = content_left
        for w in plan.col_w:
            col_x.append(x)
            x += w + col_sep
        inner_w = max(x - content_left - col_sep, 0.0) if plan.col_w else 0.0

        # rows top->bottom
        y = content_top
        row_tops: List[float] = []
        row_bottoms: List[float] = []
        for row in plan.rows:
            row_tops.append(y)
            baseline = y - row.height
            for c in row.cells:
                if c.col >= len(col_x):
                    continue
                cw = plan.col_w[c.col] if c.col < len(plan.col_w) else c.width
                mode = plan.columns[c.col] if c.col < len(plan.columns) else "c"
                if c.anchored:
                    xpos = col_x[c.col]
                elif mode == "l":
                    xpos = col_x[c.col]
                elif mode == "r":
                    xpos = col_x[c.col] + (cw - c.width)
                else:
                    xpos = col_x[c.col] + (cw - c.width) / 2.0
                if c.tex.strip():
                    try:
                        ax.text(
                            xpos, baseline, f"${c.tex}$",
                            size=fs, color=color, ha="left", va="baseline",
                        )
                    except Exception:
                        ax.text(
                            xpos, baseline, c.tex,
                            size=fs, color=color, ha="left", va="baseline",
                        )
            y = baseline - row.depth - row_gap
            row_bottoms.append(y + row_gap)

        # ---- frame ---------------------------------------------------
        top = content_top + fs * 0.10
        bot = min(row_bottoms) if row_bottoms else pad
        bot = max(bot - fs * 0.05, pad * 0.4)
        lw = max(0.9, fs * 0.085)
        left = content_left - br_w * 0.35
        right = content_left + inner_w + br_w * 0.35

        if plan.frame == "bracket":
            arm = br_w * 0.85
            ax.plot([left + arm, left, left, left + arm], [top, top, bot, bot], color=color, lw=lw, solid_capstyle="butt")
            ax.plot([right - arm, right, right, right - arm], [top, top, bot, bot], color=color, lw=lw, solid_capstyle="butt")
        elif plan.frame == "paren":
            arm = br_w * 0.85
            for xx, sgn in ((left, 1.0), (right, -1.0)):
                ax.plot(
                    [xx + sgn * arm, xx + sgn * arm * 0.5, xx + sgn * arm * 0.5, xx + sgn * arm],
                    [top, top - (top - bot) * 0.18, bot + (top - bot) * 0.18, bot],
                    color=color, lw=lw, solid_capstyle="round",
                )
        elif plan.frame == "bar":
            for xx in (left, right):
                ax.plot([xx, xx], [top, bot], color=color, lw=lw, solid_capstyle="butt")
        elif plan.frame == "double_bar":
            for xx in (left - lw * 0.9, left + lw * 0.9, right - lw * 0.9, right + lw * 0.9):
                ax.plot([xx, xx], [top, bot], color=color, lw=lw, solid_capstyle="butt")
        elif plan.frame == "brace_pair":
            _draw_brace(ax, left + br_w * 0.95, top, bot, br_w, color, lw, mirrored=True)
            _draw_brace(ax, right - br_w * 0.05, top, bot, br_w, color, lw, mirrored=False)
        elif plan.frame == "brace":
            # RTL: the brace belongs on the RIGHT of the equation block
            _draw_brace(ax, right + br_w * 0.55, top, bot, br_w, color, lw, mirrored=False)
        elif plan.frame == "brace_left":
            _draw_brace(ax, left + br_w * 0.95, top, bot, br_w, color, lw, mirrored=True)

        # ---- vertical rules (array ``|``) ----------------------------
        if plan.v_rules:
            for boundary in plan.v_rules:
                if 0 < boundary <= len(col_x):
                    if boundary < len(col_x):
                        vx = col_x[boundary] - fs * 0.30
                    else:
                        last = plan.rows[0]
                        vx = content_left + inner_w + fs * 0.12
                    ax.plot([vx, vx], [top, bot], color=color, lw=lw * 0.8, solid_capstyle="butt")

        # ---- horizontal rules (array ``\hline``) --------------------
        if any(r.hline_after_previous for r in plan.rows):
            for i, row in enumerate(plan.rows):
                if row.hline_after_previous and i > 0:
                    hy = (row_bottoms[i - 1] + row_tops[i]) / 2.0
                    ax.plot(
                        [content_left - fs * 0.1, content_left + inner_w + fs * 0.1],
                        [hy, hy], color=color, lw=lw * 0.7, solid_capstyle="butt",
                    )

        # ---- prefix / suffix ----------------------------------------
        mid_y = plan.height / 2.0 - fs * 0.30
        if plan.prefix:
            # RTL documents write ``A =`` before the matrix; in the LTR drawing
            # that means the prefix goes to the far LEFT.
            ax.text(
                pad, mid_y, f"${plan.prefix}$",
                size=fs, color=color, ha="left", va="baseline",
            )
        if plan.suffix:
            ax.text(
                plan.width - pad, mid_y, f"${plan.suffix}$",
                size=fs, color=color, ha="right", va="baseline",
            )

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, transparent=True, pad_inches=0)
        plt.close(fig)
        fig = None
        data = buf.getvalue()
        if not data:
            return None
        return RenderedMath(
            png=data,
            width=plan.width,
            height=plan.height,
            depth=plan.depth,
        )
    except Exception:
        if fig is not None:
            try:
                plt.close(fig)
            except Exception:
                pass
        return None
