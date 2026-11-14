r"""چیدمان متن فارسیِ ترکیبی با فرمول‌های ریاضیِ تصویری برای ReportLab.

ReportLab نه LaTeX می‌فهمد و نه دوجهته‌نویسی (BiDi) دارد؛ بنابراین:

1. متن به قطعه‌های «متن» و «ریاضی» تقسیم می‌شود.
2. هر قطعهٔ ریاضی با :mod:`reports.math_renderer` به تصویر PNG شفاف تبدیل می‌شود
   (کسر واقعی، رادیکال، بردار، ماتریس…).
3. هر خط از راست به چپ چیده می‌شود: واژه‌های فارسی با ``arabic_reshaper`` + ``get_display``
   و فرمول‌ها به‌صورت تصویر، دقیقاً سرِ جای خود در جریان متن.

این ماژول هیچ متنی را «به واژه تبدیل» نمی‌کند؛ فقط وقتی رندر تصویری شکست بخورد
از تابع ``fallback`` (پاک‌سازی متنی) استفاده می‌کند.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import arabic_reshaper
from bidi.algorithm import get_display

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

from reports.math_renderer import RenderedMath, render_math_png

# ---------------------------------------------------------------------------
# تقسیم متن به قطعه‌های متن/ریاضی
# ---------------------------------------------------------------------------
_DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_RE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.DOTALL)

# دستورات LaTeXِ «بدون $ » (خطای رایج مدل‌ها)
#
# نکته: ``\frac`` و ``\sqrt[n]`` می‌توانند دو گروه آکولاد داشته باشند
# (``frac{۱}{۲}``). نسخهٔ قبلی فقط یک گروه را می‌گرفت و در نتیجه ``frac{۱}{۲}``
# به «ریاضی=frac{۱}» + «متن={۲}» تجزیه می‌شد و در PDF به‌صورت «{۲}۱» چاپ می‌شد.
#: دستوراتِ ریاضی که «آرگومان» می‌گیرند (``\frac{۱}{۲}``، ``\sqrt{۷}``).
_LATEX_ARG_CMDS = (
    r"[dt]?frac|sqrt|vec|overrightarrow|widehat|overline|hat|bar|tilde|"
    r"text|mathrm|mathbf|operatorname"
)

#: دستوراتِ «نمادی» که آرگومان نمی‌گیرند و فقط یک نماد می‌سازند
#: (``2 \times 2``، ``a \cdot b``، ``x \leq y``). این‌ها پیش‌تر در هیچ الگویی
#: نبودند؛ نتیجه این بود که متنی مثل «ماتریسی ۲ \times ۲» هیچ فرمولی برایش
#: شناسایی نمی‌شد، ``has_math`` مقدار ``False`` می‌گرفت و کلِ سؤال از مسیرِ
#: رندر تصویری بیرون می‌افتاد و به ``final_pdf_cleanup`` (ترجمهٔ متنی) می‌رفت.
_LATEX_SYMBOL_CMDS = (
    r"times|cdot|div|pm|mp|ast|star|circ|bullet|"
    r"leq|le|geq|ge|neq|ne|approx|equiv|sim|cong|propto|"
    r"rightarrow|leftarrow|leftrightarrow|Rightarrow|Leftarrow|"
    r"Leftrightarrow|to|gets|mapsto|"
    r"in|notin|subset|subseteq|supset|supseteq|cup|cap|setminus|"
    r"forall|exists|nexists|partial|nabla|infty|"
    r"theta|alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|"
    r"lambda|mu|nu|xi|rho|sigma|tau|phi|varphi|chi|psi|omega|"
    r"Gamma|Delta|Theta|Lambda|Xi|Sigma|Phi|Psi|Omega|"
    r"pi|angle|degree|perp|parallel|triangle|square|"
    r"left|right|quad|qquad|,|;|!| "
)

_BARE_LATEX_RE = re.compile(
    # ۱) دستوراتِ آرگومان‌دار (با یا بدونِ آکولاد)
    rf"(?:\\+)?\b(?:{_LATEX_ARG_CMDS})\b"
    r"\s*(?:\[[^\[\]]*\]\s*)?(?:\{[^{}]*\})?(?:\s*\{[^{}]*\})?"
    # ۲) دستوراتِ نمادی — تک‌تک، چون آرگومان ندارند
    rf"|(?:\\+)(?:{_LATEX_SYMBOL_CMDS})(?![a-zA-Z])"
    # ۳) محیط‌های ماتریسی بدونِ $
    r"|(?:\\+)?\b(?:begin)\s*\{[bpvBV]?(?:matrix|array|cases)\}"
    r"[\s\S]*?(?:\\+)?\b(?:end)\s*\{[bpvBV]?(?:matrix|array|cases)\}",
)

_TOKEN_RE = re.compile(
    r"\$\$(?P<display>.+?)\$\$"
    r"|(?<!\\)\$(?!\$)(?P<inline>.+?)(?<!\\)\$",
    re.DOTALL,
)

Segment = tuple  # ("text", str) | ("math", str, is_display)


# کاراکترهای مجاز در یک عبارت ریاضی (حروف فارسی اینجا نیستند)
#: کاراکترهای مجاز در یک «کاندیدِ ریاضی»ِ بدونِ ``$``.
#:
#: نکتهٔ مهم: بک‌اسلش (``\\``) هم باید در مجموعه باشد، وگرنه دستوراتی مثل
#: ``2 \times 2`` یا ``a \cdot b`` هرگز به‌عنوان یک عبارتِ واحد دیده نمی‌شوند و
#: به تکه‌های پراکنده («۲ » + «\times» + « ۲») می‌شکنند؛ ``\times`` تنها یک
#: تصویرِ ۸ پوینتی می‌شد و نتیجه در PDF مثلِ «۲۲» دیده می‌شد.
_MATH_CHARS = (
    "A-Za-z0-9"
    "\u06F0-\u06F9"                      # ارقام فارسی
    "\\\\^_=+\\-*/()\\[\\]{}.,<>|:'\"&"
    "\u066B\u066C\u00D7\u00F7\u221A\u2264\u2265\u2260\u00B1"
)
_MATH_SIGNAL_RE = re.compile(r"[\\^_=<>|]")
_FUNC_CALL_RE = re.compile(r"^[A-Za-z]\s*\(\s*[^()]{0,30}\)$")
_MATH_CANDIDATE_RE = re.compile(rf"[{_MATH_CHARS}]+(?:\s+[{_MATH_CHARS}]+)*")


_COORD_CALL_RE = re.compile(r"^[A-Za-z]\s*\(\s*-?\d+(?:\s*,\s*-?\d+){1,3}\s*\)$")


def _looks_math(group_text: str) -> bool:
    """آیا این رشتهٔ «ریاضی‌نما» واقعاً یک عبارت ریاضی است (نه یک واژهٔ لاتین)؟"""
    g = group_text.strip()
    if not g or len(g) > 140:
        return False
    if "," in g and any(ch.isalpha() for ch in g):
        # مجموعه‌ای از مختصات نقطه‌ها:  B(2,0,0), D(0,2,0), E(0,0,2)
        parts = re.findall(r"[A-Za-z]\s*\([^()]*\)", g)
        rest = re.sub(r"[A-Za-z]\s*\([^()]*\)", "", g)
        if (
            len(parts) >= 2
            and not re.sub(r"[,،\s]", "", rest)
            and all(_COORD_CALL_RE.match(p.strip()) for p in parts)
        ):
            return True
    if _MATH_SIGNAL_RE.search(g):
        return True
    if _FUNC_CALL_RE.match(g) or _COORD_CALL_RE.match(g):
        return True
    # دستورِ LaTeX (با یا بدونِ بک‌اسلش — مدل‌ها هر دو را تولید می‌کنند)
    has_cmd = bool(re.search(r"\\?[a-zA-Z]{2,}", g))
    if "\\" in g or has_cmd:
        # دستورِ تنها (مثلِ «\times» یا «frac» بی‌آرگومان) فرمولِ کاملی نیست؛
        # اگر چیزِ دیگری جز همان یک دستور در کاندید نباشد آن را «واژه» بگذار تا
        # به تصویرِ بی‌معنا (یک علامتِ ۸ پوینتی) تبدیل نشود.
        residue = re.sub(r"\\\\?[a-zA-Z]+|[\s{}]", "", g)
        return bool(residue)
    return False


def _wrap_bare_math(chunk: str) -> List[Segment]:
    r"""عبارت‌های ریاضیِ بدون ``$`` را شناسایی و به قطعهٔ ریاضی تبدیل می‌کند.

    مثال: ``اگر f(x) = x^2 - 3x + 2 باشد`` → [متن، ریاضی، متن]
    فاصله‌ها و ترتیب متن بدون تغییر باقی می‌مانند (برش روی رشتهٔ اصلی).
    """
    if not chunk:
        return []
    out: List[Segment] = []
    pos = 0
    for m in _MATH_CANDIDATE_RE.finditer(chunk):
        cand = m.group(0)
        if not _looks_math(cand):
            continue
        if m.start() > pos:
            out.append(("text", chunk[pos : m.start()]))
        expr = re.sub(r"\s+", " ", cand).strip()
        expr = re.sub(r"\s+([()\[\],])", r"\1", expr)
        out.append(("math", expr, False))
        pos = m.end()
    if pos < len(chunk):
        out.append(("text", chunk[pos:]))
    return out


#: کاراکترهای کنترلی‌ای که ``json.loads`` روی «\\b» و «\\f» تولید می‌کند.
#: اگر احیا نشوند، ``\begin`` به ``egin`` و ``\frac`` به ``rac`` تبدیل می‌شود.
_CONTROL_REPAIRS = (
    ("\x08", "\\b"),
    ("\x0c", "\\f"),
    ("\x07", "\\a"),
    ("\x0b", "\\v"),
    ("\r", " "),
    ("\t", " "),
)


def repair_control_chars(text: str) -> str:
    r"""بازگرداندن بک‌اسلش‌هایی که ``json.loads`` خورده است.

    JSON یک escape معتبر برای ``\b`` و ``\f`` دارد؛ بنابراین رشتهٔ ``"\\begin"``
    به ``"\x08egin"`` و ``"\\frac"`` به ``"\x0crac"`` تبدیل می‌شود. با بازگرداندن
    این دو کاراکتر، دستور اصلی دقیقاً احیا می‌شود (``\x08`` → ``\\b`` و ``\x0c`` → ``\\f``).
    """
    if not text:
        return ""
    out = str(text)
    if "\x08" in out:
        out = out.replace("\x08", "\\b")
    if "\x0c" in out:
        out = out.replace("\x0c", "\\f")
    for bad, good in (("\x07", "\\a"), ("\x0b", "\\v"), ("\r", " "), ("\t", " ")):
        if bad in out:
            out = out.replace(bad, good)
    return out


def split_math_segments(text: Any) -> List[Segment]:
    """متن را به قطعه‌های ``("text", s)`` و ``("math", latex, display)`` می‌شکند."""
    raw = repair_control_chars(str(text or ""))
    if not raw.strip():
        return []

    segments: List[Segment] = []
    pos = 0
    for m in _TOKEN_RE.finditer(raw):
        if m.start() > pos:
            segments.append(("text", raw[pos : m.start()]))
        if m.group("display") is not None:
            segments.append(("math", m.group("display").strip(), True))
        else:
            segments.append(("math", m.group("inline").strip(), False))
        pos = m.end()
    if pos < len(raw):
        segments.append(("text", raw[pos:]))

    # دستورات LaTeXِ بدون $ را هم به قطعهٔ ریاضی تبدیل کن.
    #
    # ترتیب مهم است: اول ``_wrap_bare_math`` روی کلِ تکه اجرا می‌شود تا
    # عبارت‌های چندجزئی (``۲ \times ۲``، ``x^2 + y^2``، ``f(x) = x - ۳``) به
    # صورتِ **یک** قطعهٔ ریاضی در بیایند. اگر اول ``_BARE_LATEX_RE`` اجرا شود،
    # دستورِ وسطِ عبارت بریده می‌شود و به سه تکهٔ بی‌ربط («۲ » + «\times» + « ۲»)
    # می‌شکند — همان چیزی که در PDF به‌صورتِ «۲۲» دیده می‌شد.
    enriched: List[Segment] = []
    for seg in segments:
        if seg[0] != "text":
            enriched.append(seg)
            continue
        enriched.extend(_wrap_bare_math(seg[1]))
    return enriched


def has_math(text: Any) -> bool:
    """آیا متن دست‌کم یک قطعهٔ ریاضی دارد؟"""
    return any(seg[0] == "math" for seg in split_math_segments(text))


# ---------------------------------------------------------------------------
# اتم‌های چیدمان
# ---------------------------------------------------------------------------
@dataclass
class _Atom:
    kind: str  # "word" | "math" | "display"
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
    depth: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    line_height: float = 0.0
    baseline: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.atoms


# ---------------------------------------------------------------------------
# بلوک متنیِ ترکیبی
# ---------------------------------------------------------------------------
class MathRichBlock(Flowable):
    """پاراگراف راست‌چین فارسی با فرمول‌های ریاضیِ تصویریِ درون‌خطی."""

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
        self.math_scale = math_scale
        self.font = getattr(style, "fontName", None) or "Helvetica"
        self.size = float(getattr(style, "fontSize", 10.5) or 10.5)
        self.leading = float(getattr(style, "leading", self.size * 1.9) or self.size * 1.9)
        self.color = getattr(style, "textColor", None)
        self.align = getattr(style, "alignment", TA_RIGHT)
        self.space_w = stringWidth(" ", self.font, self.size)
        self.lines: List[_Line] = []
        self._built = False
        self.width = self.max_width
        self.height = self.leading

    # -- آماده‌سازی ---------------------------------------------------------
    def _shape(self, word: str) -> str:
        return get_display(arabic_reshaper.reshape(word))

    def _build_atoms(self) -> List[_Atom]:
        atoms: List[_Atom] = []
        segments = split_math_segments(self.text)
        pending_space = False  # آیا پیش از اتمِ بعدی فاصله هست؟
        for seg in segments:
            if seg[0] == "text":
                chunk = str(seg[1])
                if not chunk:
                    continue
                lead_space = chunk[:1].isspace()
                parts = chunk.split()
                for idx, word in enumerate(parts):
                    visual = self._shape(word)
                    space_before = (lead_space if idx == 0 else True) or (idx == 0 and pending_space)
                    atoms.append(
                        _Atom(
                            kind="word",
                            text=word,
                            visual=visual,
                            width=stringWidth(visual, self.font, self.size),
                            height=self.size,
                            depth=0.0,
                            space_before=bool(atoms and space_before),
                        )
                    )
                    pending_space = False
                if parts and chunk[-1:].isspace():
                    pending_space = True
            else:
                latex, is_display = str(seg[1]), bool(seg[2])
                rendered = render_math_png(latex, font_size=self.size, color="#0F172A")
                if rendered is None:
                    # رندر تصویری ناموفق → تبدیل متنیِ ایمن
                    plain = self.fallback(latex) if self.fallback else latex
                    for idx, word in enumerate(str(plain).split()):
                        visual = self._shape(word)
                        atoms.append(
                            _Atom(
                                kind="word",
                                text=word,
                                visual=visual,
                                width=stringWidth(visual, self.font, self.size),
                                height=self.size,
                                space_before=bool(atoms and (idx > 0 or pending_space)),
                            )
                        )
                    pending_space = True
                    continue
                scaled = rendered.scaled(self.math_scale)
                if scaled.width > self.max_width:
                    k = self.max_width / scaled.width
                    scaled = scaled.scaled(k)
                atoms.append(
                    _Atom(
                        kind="display" if is_display else "math",
                        rendered=scaled,
                        width=scaled.width,
                        height=scaled.height,
                        depth=scaled.depth,
                        space_before=bool(atoms and pending_space),
                    )
                )
                pending_space = False
        return atoms

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
                self._flush(disp)
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
            self.lines = [_Line(atoms=[], width=0.0, height=self.size)]
        self._built = True

    def _flush(self, line: _Line) -> None:
        text_ascent = self.size * 0.80
        text_descent = self.size * 0.24
        ascent = text_ascent
        descent = text_descent
        for atom in line.atoms:
            ascent = max(ascent, atom.height - atom.depth)
            descent = max(descent, atom.depth)
        line.ascent = ascent
        line.descent = descent
        line.line_height = max(self.leading, ascent + descent + 2.5)
        self.lines.append(line)

    def _ensure_built(self) -> None:
        if not self._built:
            self._build_lines()

    # -- API مربوط به Flowable ---------------------------------------------
    def wrap(self, availWidth, availHeight):  # noqa: N802
        self.width = max(20.0, min(float(availWidth), self.max_width))
        self._ensure_built()
        total = sum(line.line_height for line in self.lines) or self.leading
        self.height = max(total, self.leading)
        # مختصات ReportLab از پایین به بالا رشد می‌کند؛ خط‌ها را از بالا می‌چینیم
        y = self.height
        for line in self.lines:
            y -= line.line_height
            line.baseline = y + line.descent
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        if self.color is not None:
            try:
                c.setFillColor(self.color)
            except Exception:
                pass
        c.setFont(self.font, self.size)
        char_space = 0.0  # فاصلهٔ حروف مطابق اندازه‌گیریِ stringWidth در ReportLab
        for line in self.lines:
            if line.is_empty:
                continue
            if len(line.atoms) == 1 and line.atoms[0].kind == "display":
                atom = line.atoms[0]
                x = (self.width - atom.width) / 2.0
                if atom.rendered is not None:
                    _draw_math_image(c, atom.rendered, x, line.baseline)
                continue
            # چیدمان راست‌به‌چپ: مکان‌نما از لبهٔ راست شروع و به چپ حرکت می‌کند
            if self.align == TA_CENTER:
                cursor = (self.width + line.width) / 2.0
            elif self.align == TA_LEFT:
                cursor = line.width
            else:
                cursor = self.width
            for atom in line.atoms:
                if atom.space_before:
                    cursor -= self.space_w
                if atom.kind == "word":
                    cursor -= atom.width
                    c.setFont(self.font, self.size)
                    c.drawString(cursor, line.baseline, atom.visual, charSpace=char_space)
                elif atom.kind == "math" and atom.rendered is not None:
                    cursor -= atom.width
                    _draw_math_image(c, atom.rendered, cursor, line.baseline)
        c.restoreState()


def _draw_math_image(c, rendered: RenderedMath, x: float, baseline: float) -> None:
    """تصویر فرمول را طوری بکشد که خط کرسی‌اش با خط کرسی متن یکی باشد."""
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


def _image_reader(rendered: RenderedMath):
    """بایت‌های PNG را به ImageReader قابل‌استفاده در کانواس تبدیل می‌کند."""
    from io import BytesIO

    from reportlab.lib.utils import ImageReader

    return ImageReader(BytesIO(rendered.png))


def math_paragraph_flowables(
    text: Any,
    style: ParagraphStyle,
    max_width: float,
    fallback: Optional[Callable[[str], str]] = None,
) -> list:
    """متن را به یک بلوک ریاضی‌فهمِ ReportLab تبدیل می‌کند.

    فرمول‌های ``$$...$$`` درون همان بلوک به‌صورت خطِ جداگانه و وسط‌چین چیده می‌شوند
    تا صورت سؤال هرگز بین دو صفحه تکه‌تکه نشود.
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    return [MathRichBlock(raw, style=style, max_width=max_width, fallback=fallback)]


class OptionsRow(Flowable):
    r"""ردیفِ چهارگزینه‌ای کنکوری که تمام‌عرض صفحه پخش می‌شود (راست‌به‌چپ).

    هر گزینه یک :class:`MathRichBlock` است؛ بنابراین فرمول‌های داخل گزینه‌ها
    (مثل $\frac{5\sqrt{14}}{14}$) به‌صورت تصویر واقعی رندر می‌شوند.
    """

    def __init__(
        self,
        cells: List[tuple],
        width: float,
        fallback: Optional[Callable[[str], str]] = None,
        pad: float = 8.0,
    ) -> None:
        super().__init__()
        self.cells = list(cells)  # [(text, style), ...]
        self.width = float(width)
        self.fallback = fallback
        self.pad = pad
        self.blocks: List[MathRichBlock] = []
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

    def draw(self):
        c = self.canv
        c.saveState()
        n = max(len(self.blocks), 1)
        col_w = (self.width - self.pad * (n - 1)) / n
        for idx, blk in enumerate(self.blocks):
            # گزینهٔ اول در سمت راست، گزینهٔ چهارم در سمت چپ
            x_left = self.width - (idx + 1) * col_w - idx * self.pad
            c.saveState()
            c.translate(max(x_left, 0.0), 0)
            blk.drawOn(c, 0, self.height - float(getattr(blk, "height", 0.0)))
            c.restoreState()
        c.restoreState()


def parse_mixed_text_and_math(content: Any) -> List[Segment]:
    """تحلیل‌گرِ محتوای ترکیبی (متن + فرمول) — همان قراردادِ ``parse_mixed_text_and_math``.

    خروجی یک لیست مرتب از قطعه‌هاست::

        [("text", "اگر "), ("math", "\\frac{۱}{۲}", False), ("text", " باشد")]

    * ``$ ... $``  → قطعهٔ ریاضیِ درون‌خطی (``display=False``)
    * ``$$ ... $$`` → قطعهٔ ریاضیِ نمایشی (``display=True``)
    * LaTeXِ بدون دلار (مثل ``sqrt{۷}`` یا ``f(x) = x^2``) هم به قطعهٔ ریاضی تبدیل می‌شود
    * بقیهٔ متن دست‌نخورده می‌ماند تا با ``arabic_reshaper`` + ``bidi`` آماده شود.
    """
    return split_math_segments(content)


def build_mixed_flowables(
    content: Any,
    style: ParagraphStyle,
    max_width: float,
    fallback: Optional[Callable[[str], str]] = None,
) -> list:
    """محتوای ترکیبی را به لیست Flowableهای ReportLab تبدیل می‌کند.

    هر قطعهٔ متن → پاراگرافِ RTL (reshape + bidi) و هر قطعهٔ ریاضی → تصویرِ PNG
    شفاف با DPI بالا. این تابع همان چیزی است که صورت سؤال و گزینه‌ها را می‌سازد.
    """
    return math_paragraph_flowables(
        content, style=style, max_width=max_width, fallback=fallback
    )



__all__ = [
    "MathRichBlock",
    "OptionsRow",
    "math_paragraph_flowables",
    "split_math_segments",
    "parse_mixed_text_and_math",
    "build_mixed_flowables",
    "has_math",
]
