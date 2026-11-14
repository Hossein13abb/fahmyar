# -*- coding: utf-8 -*-
"""Mixed text + math flowables — the ONE renderer for question/option bodies.

This replaces the old ``pdf_text_flow`` module.  Two things changed:

1.  **Classification moved out.**  It now lives in ``pdf_content_parser``,
    which never mistakes a prose sentence for a formula.  Before, the block
    renderer called ``split_math_segments`` which used a heuristic matching any
    two-letter Latin word, so ``"The derivative of a constant is always one."``
    became one mathtext image with every space removed.

2.  **Word spacing is drawn, not just measured.**  The old ``draw()`` advanced
    the cursor by ``space_w`` but emitted no space character, so text extracted
    from the PDF read ``Whichofthefollowing...``.  Here the space is part of the
    drawn string run, which keeps both the pixels and the text layer correct.

Dependency direction: ``pdf_content_parser`` + ``pdf_math`` + ``pdf_typography``
-> this module -> ``pdf_components`` -> ``exam_pdf``.  No cycles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Callable, List, Optional

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

from reports import pdf_math
from reports.math_renderer import RenderedMath
from reports.pdf_content_parser import Segment, has_math, split_math_segments
from reports.pdf_typography import has_latin, has_rtl, shape, strip_invisibles, visual

__all__ = [
    "MathRichBlock",
    "OptionsRow",
    "math_paragraph_flowables",
    "simple_text_flowables",
    "split_math_segments",
    "has_math",
    "Segment",
]


# ---------------------------------------------------------------------------
# Atoms and lines
# ---------------------------------------------------------------------------

@dataclass
class _Atom:
    kind: str                  # "word" | "math" | "display" | "space"
    text: str = ""
    visual: str = ""
    rendered: Optional[RenderedMath] = None
    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    space_before: bool = False


@dataclass
class _Line:
    atoms: List[_Atom] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    line_height: float = 0.0
    baseline: float = 0.0
    runs: List["_Run"] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.atoms


# ---------------------------------------------------------------------------
# Word runs — the unit BiDi actually sees
# ---------------------------------------------------------------------------

@dataclass
class _Run:
    """A maximal sequence of word atoms drawn as ONE BiDi-processed string.

    Bidi must never be applied per word: in a right-to-left paragraph the visual
    order of English words is left-to-right, so reversing word order while also
    right-aligning them yields "correct? is Derivative the about ...".  Running
    ``get_display`` over the whole logical run and then placing that run as a
    single unit is what makes a mixed sentence read correctly.
    """

    text: str = ""          # logical text, words joined by single spaces
    visual: str = ""        # shaped + bidi result, ready to draw
    width: float = 0.0
    space_before: bool = False
    atoms: List["_Atom"] = field(default_factory=list)


def _group_runs(atoms: List[_Atom]) -> List[_Run]:
    """Collapse consecutive word atoms into runs; math atoms stay standalone."""
    runs: List[_Run] = []
    current: List[_Atom] = []

    def _flush_run() -> None:
        nonlocal current
        if not current:
            return
        logical = " ".join(a.text for a in current)
        vis = visual(logical)  # BiDi over the WHOLE run, not per word
        runs.append(
            _Run(
                text=logical,
                visual=vis,
                width=0.0,  # measured by the caller, which knows the font
                space_before=current[0].space_before,
                atoms=list(current),
            )
        )
        current = []

    for atom in atoms:
        if atom.kind == "word":
            current.append(atom)
        else:
            _flush_run()
            runs.append(_Run(atoms=[atom], width=atom.width, space_before=atom.space_before))
    _flush_run()

    return runs


# ---------------------------------------------------------------------------
# The block
# ---------------------------------------------------------------------------

class MathRichBlock(Flowable):
    """A right-to-left paragraph whose inline formulas are real images."""

    def __init__(
        self,
        text: Any,
        style: ParagraphStyle,
        max_width: float,
        fallback: Optional[Callable[[str], str]] = None,
        math_scale: float = 1.0,
    ) -> None:
        super().__init__()
        self.text = str(text or "")
        self.style = style
        self.max_width = float(max_width)
        self.fallback = fallback
        self.math_scale = float(math_scale)
        self.font = getattr(style, "fontName", None) or "Helvetica"
        self.size = float(getattr(style, "fontSize", 10.5) or 10.5)
        self.leading = float(getattr(style, "leading", self.size * 1.9) or self.size * 1.9)
        self.color = getattr(style, "textColor", None)
        # A ParagraphStyle that was never given an alignment reports TA_LEFT (0),
        # which is indistinguishable from "explicitly left".  For RTL content the
        # default must be TA_RIGHT; callers that really want left/centre set it.
        _align = getattr(style, "alignment", None)
        self.align = TA_RIGHT if _align in (None, TA_LEFT) else _align
        self.space_w = stringWidth(" ", self.font, self.size)
        self.lines: List[_Line] = []
        self._built = False
        self.width = self.max_width
        self.height = self.leading

    # -- atom construction -------------------------------------------------
    def _word_atom(self, word: str, space_before: bool) -> _Atom:
        """A logical word; its width is measured on the shaped form.

        Shaping is applied per word only to *measure* it correctly; the string
        actually drawn is produced later by running BiDi over the whole line,
        because a pure-Latin sentence must keep its word order.
        """
        clean = strip_invisibles(word)
        vis = shape(clean) if has_rtl(clean) else clean
        return _Atom(
            kind="word",
            text=clean,
            visual=vis,
            width=stringWidth(vis, self.font, self.size),
            height=self.size,
            space_before=space_before,
        )

    def _build_atoms(self) -> List[_Atom]:
        atoms: List[_Atom] = []
        pending_space = False
        segments = split_math_segments(self.text)

        for seg in segments:
            if seg.kind == "text":
                chunk = seg.payload
                if not chunk:
                    continue
                lead_space = chunk[:1].isspace()
                words = chunk.split()
                for idx, word in enumerate(words):
                    first = idx == 0
                    space_before = bool(atoms) and ((lead_space and first) or not first or pending_space)
                    atoms.append(self._word_atom(word, space_before))
                    pending_space = False
                if words and chunk[-1:].isspace():
                    pending_space = True
                continue

            # -- math ------------------------------------------------------
            latex, is_display = seg.payload, seg.display
            rendered = pdf_math.render_cached(latex, font_size=self.size, color="#0F172A")
            if rendered is None:
                # Deliberate degradation: print the source, never a blank box.
                plain = self.fallback(latex) if self.fallback else latex
                for idx, word in enumerate(str(plain).split()):
                    atoms.append(self._word_atom(word, bool(atoms) and (idx > 0 or pending_space)))
                pending_space = True
                continue

            scaled = rendered.scaled(self.math_scale) if self.math_scale != 1.0 else rendered
            if scaled.width > self.max_width:
                scaled = scaled.scaled(self.max_width / scaled.width)
            atoms.append(
                _Atom(
                    kind="display" if is_display else "math",
                    rendered=scaled,
                    width=scaled.width,
                    height=scaled.height,
                    depth=scaled.depth,
                    space_before=bool(atoms) and pending_space,
                )
            )
            pending_space = True   # the next text run needs a gap too
            pending_space = False

        return atoms

    # -- line breaking -----------------------------------------------------
    def _build_lines(self) -> None:
        atoms = self._build_atoms()
        self.lines = []
        line = _Line()

        for atom in atoms:
            if atom.kind == "display":
                if not line.is_empty:
                    self._flush(line)
                    line = _Line()
                disp = _Line(atoms=[atom], width=atom.width, height=atom.height)
                disp.ascent = atom.height - atom.depth
                disp.descent = atom.depth
                disp.line_height = max(self.leading, atom.height)
                self.lines.append(disp)
                continue

            extra = self.space_w if (atom.space_before and not line.is_empty) else 0.0
            if not line.is_empty and line.width + extra + atom.width > self.max_width:
                self._flush(line)
                line = _Line()
                extra = 0.0
            if extra:
                line.width += extra
            atom.space_before = bool(extra)
            line.atoms.append(atom)
            line.width += atom.width
            line.height = max(line.height, atom.height + atom.depth)

        if not line.is_empty:
            self._flush(line)
        if not self.lines:
            self.lines = [_Line()]
            self.lines[0].ascent = self.size * 0.8
            self.lines[0].descent = self.size * 0.24
            self.lines[0].line_height = self.leading
        self._built = True

    def _flush(self, line: _Line) -> None:
        ascent = self.size * 0.80
        descent = self.size * 0.24
        for atom in line.atoms:
            ascent = max(ascent, atom.height - atom.depth)
            descent = max(descent, atom.depth)
        line.ascent = ascent
        line.descent = descent
        line.line_height = max(self.leading, ascent + descent + 2.5)
        line.runs = _group_runs(line.atoms)
        for run in line.runs:
            if run.atoms and run.atoms[0].kind == "word":
                run.width = stringWidth(run.visual, self.font, self.size)
        line.width = sum(
            r.width + (self.space_w if r.space_before else 0.0) for r in line.runs
        )
        self.lines.append(line)

    def _ensure_built(self) -> None:
        if not self._built:
            self._build_lines()

    # -- Flowable API ------------------------------------------------------
    def wrap(self, availWidth, availHeight):  # noqa: N802
        self.width = max(20.0, min(float(availWidth), self.max_width))
        self._ensure_built()
        total = sum(line.line_height for line in self.lines) or self.leading
        self.height = max(total, self.leading)
        y = self.height
        for line in self.lines:
            y -= line.line_height
            line.baseline = y + line.descent
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        if self.color is not None:
            try:
                c.setFillColor(self.color)
            except Exception:
                pass
        c.setFont(self.font, self.size)

        for line in self.lines:
            if line.is_empty:
                continue

            # A lone display formula is centred on its own line.
            if len(line.atoms) == 1 and line.atoms[0].kind == "display":
                atom = line.atoms[0]
                if atom.rendered is not None:
                    _draw_math_image(
                        c, atom.rendered, (self.width - atom.width) / 2.0, line.baseline
                    )
                continue

            if self.align == TA_CENTER:
                cursor = (self.width + line.width) / 2.0
            elif self.align == TA_LEFT:
                cursor = line.width
            else:
                cursor = self.width

            # Runs are placed right-to-left.  Inside one run the string is
            # already in visual order (BiDi ran over the whole run), so its
            # internal spaces are real characters and English keeps its order.
            for run in line.runs:
                if run.space_before:
                    cursor -= self.space_w
                cursor -= run.width
                if run.atoms and run.atoms[0].kind == "word":
                    c.setFont(self.font, self.size)
                    c.drawString(cursor, line.baseline, run.visual)
                else:
                    atom = run.atoms[0] if run.atoms else None
                    if atom is not None and atom.rendered is not None:
                        _draw_math_image(c, atom.rendered, cursor, line.baseline)

        c.restoreState()


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _image_reader(rendered: RenderedMath) -> ImageReader:
    return ImageReader(BytesIO(rendered.png))


def _draw_math_image(c, rendered: RenderedMath, x: float, baseline: float) -> None:
    """Place a formula image so its baseline coincides with the text baseline."""
    try:
        c.drawImage(
            _image_reader(rendered),
            x,
            baseline - rendered.depth,
            width=rendered.width,
            height=rendered.height,
            mask="auto",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def math_paragraph_flowables(
    text: Any,
    style: ParagraphStyle,
    max_width: float,
    fallback: Optional[Callable[[str], str]] = None,
) -> List[Flowable]:
    """A paragraph that may contain inline/display formulas."""
    src = str(text or "")
    if not src.strip():
        return []
    return [MathRichBlock(src, style=style, max_width=max_width, fallback=fallback)]


def simple_text_flowables(
    text: Any,
    style: ParagraphStyle,
    max_width: float,
) -> List[Flowable]:
    """A paragraph with NO formulas — same renderer, zero math overhead.

    Keeping one renderer for both cases removes the old split where a text-only
    question went through ReportLab's ``Paragraph`` (no math support at all)
    while a math question went through ``MathRichBlock``.
    """
    src = str(text or "")
    if not src.strip():
        return []
    return [MathRichBlock(src, style=style, max_width=max_width)]


# ---------------------------------------------------------------------------
# Four-column option row
# ---------------------------------------------------------------------------

class OptionsRow(Flowable):
    """Four options laid out right-to-left across the full text width."""

    def __init__(
        self,
        cells: List[tuple],
        width: float,
        fallback: Optional[Callable[[str], str]] = None,
        pad: float = 8.0,
    ) -> None:
        super().__init__()
        self.cells = list(cells)          # [(text, style), ...]
        self.width = float(width)
        self.fallback = fallback
        self.pad = pad
        self.blocks: List[MathRichBlock] = []
        self.col_w = 0.0
        self.height = 0.0

    def wrap(self, availWidth, availHeight):  # noqa: N802
        n = max(len(self.cells), 1)
        col_w = (self.width - self.pad * (n - 1)) / n
        self.col_w = col_w
        self.blocks = []
        max_h = 0.0
        for text, style in self.cells:
            blk = MathRichBlock(text, style=style, max_width=col_w, fallback=self.fallback)
            _, h = blk.wrap(col_w, availHeight)
            max_h = max(max_h, h)
            self.blocks.append(blk)
        self.height = max(max_h, 12.0)
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        n = max(len(self.blocks), 1)
        col_w = (self.width - self.pad * (n - 1)) / n
        for idx, blk in enumerate(self.blocks):
            # option 0 sits at the far right, option 3 at the far left
            x_left = self.width - (idx + 1) * col_w - idx * self.pad
            c.saveState()
            c.translate(max(x_left, 0.0), 0)
            blk.drawOn(c, 0, self.height - float(getattr(blk, "height", 0.0)))
            c.restoreState()
        c.restoreState()
