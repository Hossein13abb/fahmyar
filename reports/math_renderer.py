r"""رندر واقعی ریاضی (کسر، رادیکال، بردار، ماتریس) به تصویر PNG شفاف برای ReportLab.

ReportLab از LaTeX پشتیبانی نمی‌کند؛ بنابراین هر عبارت ریاضی با موتور mathtext
کتابخانهٔ matplotlib به یک تصویر برداری‌گونهٔ PNG با پس‌زمینهٔ شفاف تبدیل می‌شود و
سپس به‌صورت ``RLImage`` در جریان (story) فایل PDF قرار می‌گیرد.

نکات پیاده‌سازی:

* ``mathtext.math_to_image`` خودش «tight bbox» می‌دهد و ``depth`` (فاصلهٔ زیر خط کرسی)
  را برمی‌گرداند؛ همین عمق برای هم‌ترازی صحیح فرمول با متن فارسی حیاتی است.
* ارقام فارسی (۰۱۲۳۴۵۶۷۸۹) توسط mathtext به‌درستی رندر می‌شوند، پس در تبدیل دست
  نمی‌زنیم و فقط اگر رندر شکست خورد به ارقام لاتین برمی‌گردیم.
* ``\begin{bmatrix} ... \end{bmatrix}`` و هم‌خانواده‌هایش در mathtext پشتیبانی
  نمی‌شوند؛ این محیط‌ها با چیدن دستی سلول‌ها + کشیدن کمانه‌ها روی محور رسم می‌شوند.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Optional

try:  # pragma: no cover - وابستگی اختیاری
    import matplotlib

    matplotlib.use("Agg")  # headless
    from matplotlib import mathtext
    from matplotlib.font_manager import FontProperties
    import matplotlib.pyplot as plt

    _HAS_MATPLOTLIB = True
except Exception:  # pragma: no cover
    mathtext = None  # type: ignore[assignment]
    FontProperties = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    _HAS_MATPLOTLIB = False

try:  # pragma: no cover
    from reportlab.platypus import Image as RLImage
except Exception:  # pragma: no cover
    RLImage = None  # type: ignore[assignment]

DEFAULT_DPI = 300
DEFAULT_COLOR = "#0F172A"

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"

# محیط‌های «ماتریس‌گونه» که mathtext از آن‌ها پشتیبانی نمی‌کند
_MATRIX_ENV_RE = re.compile(
    r"\\+begin\s*\{([bpvBV]?matrix|array|cases|aligned|gathered|split)\*?\}"
    r"([\s\S]*?)"
    r"\\+end\s*\{([bpvBV]?matrix|array|cases|aligned|gathered|split)\*?\}"
)

# دستورات پشتیبانی‌نشده در mathtext → معادل یا حذف
# (کلید: الگوی regex، مقدار: جایگزین)
_UNSUPPORTED_SUBS: list[tuple[str, str]] = [
    (r"\\displaystyle\b", ""),
    (r"\\textstyle\b", ""),
    (r"\\scriptstyle\b", ""),
    (r"\\limits\b", ""),
    (r"\\nolimits\b", ""),
    (r"\\boxed\b", ""),
    (r"\\hspace\s*\{[^{}]*\}", r"\,"),
    (r"\\vspace\s*\{[^{}]*\}", r"\,"),
    (r"\\mathstrut\b", ""),
    (r"\\strut\b", ""),
    (r"\\lvert\b", "|"),
    (r"\\rvert\b", "|"),
    (r"\\lVert\b", "|"),
    (r"\\rVert\b", "|"),
    (r"\\mid\b", "|"),
    (r"\\varnothing\b", r"\\emptyset"),
    (r"\\dfrac\b", r"\\frac"),
    (r"\\tfrac\b", r"\\frac"),
    (r"\\cfrac\b", r"\\frac"),
    (r"\\overrightarrow\s*\{", r"\\vec{"),
    (r"\\overleftarrow\s*\{", r"\\vec{"),
    (r"\\color\s*\{[a-zA-Z]+\}", ""),
    (r"\\textcolor\s*\{[a-zA-Z]+\}", ""),
]


@dataclass
class RenderedMath:
    """تصویر رندرشدهٔ یک فرمول ریاضی (PNG شفاف) + ابعاد دقیق بر حسب پوینت."""

    png: bytes
    width: float
    height: float
    depth: float = 0.0

    def scaled(self, factor: float) -> "RenderedMath":
        if factor == 1.0:
            return self
        return RenderedMath(
            png=self.png,
            width=self.width * factor,
            height=self.height * factor,
            depth=self.depth * factor,
        )


# ---------------------------------------------------------------------------
# نرمال‌سازی عبارت
# ---------------------------------------------------------------------------
def normalize_latex(latex_str: Any) -> str:
    """عبارت LaTeX را برای mathtext آماده می‌کند (بدون ``$``)."""
    raw = str(latex_str or "").replace("\x08", r"\b").replace("\x0c", r"\f").strip()
    expr = raw.strip()
    while expr.startswith("$$") and expr.endswith("$$") and len(expr) > 4:
        expr = expr[2:-2].strip()
    while expr.startswith("$") and expr.endswith("$") and len(expr) > 2:
        expr = expr[1:-1].strip()
    # دلارهای باقی‌مانده در وسط عبارت (نویز مدل) حذف می‌شوند
    expr = expr.replace("$", "")

    # دستورات بدون بک‌اسلش (خطای رایج مدل‌های زبانی)
    expr = re.sub(r"(?<![\\a-zA-Z])(frac|sqrt|vec|theta|alpha|beta|gamma|pi|cos|sin|tan|cot|log|ln|deg|circ|infty)\b", r"\\\1", expr)
    expr = re.sub(
        r"(?<![\\a-zA-Z])(begin|end)\s*\{([bpvBV]?matrix|array|cases|aligned|gathered)\}",
        r"\\\1{\2}",
        expr,
    )
    # بک‌اسلشِ دوتایی پیش از نام دستور (نویزِ JSON) → تک‌بک‌اسلش
    expr = re.sub(r"\\\\+(?=[a-zA-Z])", r"\\", expr)

    for old, new in _UNSUPPORTED_SUBS:
        expr = re.sub(old, new, expr)

    # _ و ^ بدون آکولاد اگر چند کاراکتر دارند
    expr = re.sub(r"\^\{?([0-9a-zA-Z\u06F0-\u06F9]{2,})\}?(?!\})", r"^{\1}", expr)
    expr = re.sub(r"\s+", " ", expr).strip()
    return expr


def _to_latin_digits(text: str) -> str:
    return text.translate(str.maketrans(_FA_DIGITS, _EN_DIGITS))


# ---------------------------------------------------------------------------
# رسم ماتریس‌ها (mathtext از bmatrix پشتیبانی نمی‌کند)
# ---------------------------------------------------------------------------
def _render_matrix_png(env: str, body: str, font_size: float, dpi: int, color: str) -> Optional[RenderedMath]:
    if not _HAS_MATPLOTLIB or plt is None:
        return None
    body_clean = re.sub(r"\{[clr]\}", "", body)  # ستون‌های array
    rows = [r.strip() for r in re.split(r"\\\\", body_clean) if r.strip()]
    if not rows:
        return None
    grid = [[c.strip() for c in re.split(r"(?<!\\)&", r)] for r in rows]
    nrows = max(len(grid), 1)
    ncols = max((len(r) for r in grid), default=1)
    fig = None
    try:
        scale = max(0.42, font_size / 11.0)
        fig, ax = plt.subplots(figsize=(max(0.5, 0.62 * ncols) * scale, max(0.34, 0.42 * nrows) * scale))
        ax.set_xlim(0, ncols)
        ax.set_ylim(0, nrows)
        ax.axis("off")
        for ri, row in enumerate(grid):
            y = nrows - ri - 0.5
            for ci, cell in enumerate(row):
                cell_tex = cell.strip().strip("$").strip() or "0"
                try:
                    ax.text(
                        ci + 0.5,
                        y,
                        f"${cell_tex}$",
                        size=font_size * 1.05,
                        ha="center",
                        va="center",
                        color=color,
                    )
                except Exception:
                    ax.text(ci + 0.5, y, cell_tex, size=font_size, ha="center", va="center", color=color)
        # کمانه‌ها / براکت‌ها
        bracket = "[" if "bmatrix" in env else ("(" if "pmatrix" in env else ("|" if "vmatrix" in env else ""))
        if "cases" in env:
            bracket = "{"
        bar = 0.10
        if bracket in "[(":
            left, right = ("[" if bracket == "[" else "("), ("]" if bracket == "[" else ")")
            ax.plot([0.20, 0.05, 0.05, 0.20], [0.05, 0.05, nrows - 0.05, nrows - 0.05], color=color, lw=1.6)
            ax.plot(
                [ncols - 0.20, ncols - 0.05, ncols - 0.05, ncols - 0.20],
                [0.05, 0.05, nrows - 0.05, nrows - 0.05],
                color=color,
                lw=1.6,
            )
            _ = (left, right, bar)
        elif bracket == "|":
            for x in (0.06, ncols - 0.06):
                ax.plot([x, x], [0.05, nrows - 0.05], color=color, lw=1.3)
        elif bracket == "{":
            ax.plot([0.24, 0.08, 0.08, 0.24], [0.04, 0.12, nrows - 0.12, nrows - 0.04], color=color, lw=1.4)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0.02, transparent=True)
        plt.close(fig)
        fig = None
        data = buf.getvalue()
        if not data:
            return None
        width_px, height_px = _png_size(data)
        return RenderedMath(
            png=data,
            width=width_px * 72.0 / dpi,
            height=height_px * 72.0 / dpi,
            depth=0.18 * font_size,
        )
    except Exception:
        if fig is not None:
            try:
                plt.close(fig)
            except Exception:
                pass
        return None


def _png_size(data: bytes) -> tuple[int, int]:
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        pass
    # fallback: خواندن مستقیم IHDR
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    except Exception:
        pass
    return (1, 1)


# ---------------------------------------------------------------------------
# رندر یک عبارت
# ---------------------------------------------------------------------------
def render_math_png(
    latex_str: Any,
    font_size: float = 10.5,
    dpi: int = DEFAULT_DPI,
    color: str = DEFAULT_COLOR,
) -> Optional[RenderedMath]:
    """عبارت LaTeX را به ``RenderedMath`` (PNG شفاف + ابعاد پوینتی) تبدیل می‌کند."""
    if not _HAS_MATPLOTLIB or mathtext is None:
        return None
    raw = str(latex_str or "").strip()
    if not raw:
        return None

    # ماتریس‌ها مسیر جداگانه دارند
    m_mat = _MATRIX_ENV_RE.search(raw)
    if m_mat:
        return _render_matrix_png(m_mat.group(1), m_mat.group(2), font_size, dpi, color)

    expr = normalize_latex(raw)
    if not expr:
        return None

    candidates = [expr]
    # اگر ارقام فارسی مشکل ایجاد کردند، نسخهٔ لاتین را هم امتحان کن
    if any(ch in expr for ch in _FA_DIGITS):
        candidates.append(_to_latin_digits(expr))

    prop = FontProperties(size=font_size)
    parser = mathtext.MathTextParser("path")
    for cand in candidates:
        buf = io.BytesIO()
        try:
            # ابعاد دقیق بر حسب «پوینت» (dpi=72) — همان مقیاسی که ReportLab استفاده می‌کند
            width_pt, height_pt, depth_pt, _, _ = parser.parse(
                f"${cand}$", dpi=72, prop=prop
            )
            mathtext.math_to_image(
                f"${cand}$", buf, prop=prop, dpi=dpi, format="png", color=color
            )
            data = buf.getvalue()
            if not data or width_pt <= 0 or height_pt <= 0:
                continue
            return RenderedMath(
                png=data,
                width=float(width_pt),
                height=float(height_pt),
                depth=float(depth_pt or 0.0),
            )
        except Exception:
            continue

    # آخرین تلاش: حذف دستورات ناشناخته و رندر دوباره
    stripped = re.sub(r"\\[a-zA-Z]+\*?", " ", expr)
    stripped = re.sub(r"[\{\}]", " ", stripped).strip()
    if not stripped:
        return None
    buf = io.BytesIO()
    try:
        width_pt, height_pt, depth_pt, _, _ = parser.parse(f"${stripped}$", dpi=72, prop=prop)
        mathtext.math_to_image(f"${stripped}$", buf, prop=prop, dpi=dpi, format="png", color=color)
        data = buf.getvalue()
        if data and width_pt > 0 and height_pt > 0:
            return RenderedMath(
                png=data,
                width=float(width_pt),
                height=float(height_pt),
                depth=float(depth_pt or 0.0),
            )
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# API سازگار با ReportLab
# ---------------------------------------------------------------------------
def latex_to_image(
    latex_str: Any,
    dpi: int = DEFAULT_DPI,
    font_size: float = 10.5,
    max_width_pt: Optional[float] = None,
) -> Optional["RLImage"]:
    """عبارت LaTeX را به ``reportlab.platypus.Image`` تبدیل می‌کند (برای استفادهٔ مستقل)."""
    rendered = render_math_png(latex_str, font_size=font_size, dpi=dpi)
    if rendered is None or RLImage is None:
        return None
    img = RLImage(io.BytesIO(rendered.png), width=rendered.width, height=rendered.height)
    if max_width_pt and rendered.width > max_width_pt > 0:
        k = max_width_pt / rendered.width
        img.drawWidth = rendered.width * k
        img.drawHeight = rendered.height * k
    # جلوگیری از جمع‌شدن فایل در حافظه: bytes نگه داشته می‌شود
    img._math_png = rendered.png  # type: ignore[attr-defined]
    return img


def math_image_size(latex_str: Any, font_size: float = 10.5) -> tuple[float, float]:
    """ابعاد تقریبی (عرض، ارتفاع) تصویر فرمول بر حسب پوینت — برای چیدمان متن."""
    rendered = render_math_png(latex_str, font_size=font_size)
    if rendered is None:
        return (0.0, 0.0)
    return (rendered.width, rendered.height)


def render_latex_to_image(
    latex_str: Any,
    dpi: int = DEFAULT_DPI,
    font_size: float = 10.5,
    max_width_pt: Optional[float] = None,
    color: str = DEFAULT_COLOR,
) -> Optional["RLImage"]:
    r"""رندر یک عبارت LaTeX به ``reportlab.platypus.Image`` با DPI بالا و پس‌زمینهٔ شفاف.

    این همان تابعِ قراردادیِ سند است؛ بر خلاف پیاده‌سازیِ سادهٔ مبتنی بر
    ``plt.figure(figsize=(0.01, 0.01))`` — که به‌خاطر کلایپِ جعبهٔ محورها همیشه
    تصویرِ خالی می‌دهد — از ``mathtext.math_to_image`` استفاده می‌کند که خودش
    tight-bbox می‌دهد و ابعادِ دقیقِ پوینتی را برمی‌گرداند.

    Parameters
    ----------
    latex_str:
        عبارت LaTeX؛ با یا بدون ``$``/``$$``.
    dpi:
        تفکیک‌پذیری تصویر خروجی (پیش‌فرض ۳۰۰).
    font_size:
        اندازهٔ قلم بر حسب پوینت — هم‌تراز با متنِ اطراف در ReportLab.
    max_width_pt:
        اگر داده شود، تصویر بلندتر از این عرض مقیاس می‌شود.
    """
    rendered = render_math_png(latex_str, font_size=font_size, dpi=dpi, color=color)
    if rendered is None or RLImage is None:
        return None
    img = RLImage(
        io.BytesIO(rendered.png),
        width=rendered.width,
        height=rendered.height,
    )
    if max_width_pt and 0 < max_width_pt < rendered.width:
        k = max_width_pt / rendered.width
        img.drawWidth = rendered.width * k
        img.drawHeight = rendered.height * k
    img.hAlign = "RIGHT"
    # نگه‌داشتن بایت‌ها تا ReportLab در زمان build دوباره بخواند
    img._math_png = rendered.png  # type: ignore[attr-defined]
    img._math_depth = rendered.depth  # type: ignore[attr-defined]
    return img



__all__ = [
    "RenderedMath",
    "render_latex_to_image",
    "render_math_png",
    "latex_to_image",
    "normalize_latex",
    "math_image_size",
    "_HAS_MATPLOTLIB",
]
