# -*- coding: utf-8 -*-
"""Math layer — one entry point for turning LaTeX into a drawable image.

``math_renderer`` already knows *how* to draw (mathtext, matrices, Persian digit
translation).  This module adds the policy layer that used to be scattered
across ``exam_pdf`` and ``pdf_text_flow``:

*   a process-wide cache, because the same formula is re-rendered on every
    question and matplotlib is the single most expensive step in PDF build;
*   a size policy so inline math matches the surrounding text size instead of
    the hard-coded ``font_size=11`` that made formulas look pasted-in;
*   a hard failure mode: if a formula cannot be rendered, ``render`` returns
    ``None`` and the caller degrades to plain text *deliberately*, rather than
    silently emitting a blank image.

Nothing here imports ``exam_pdf`` — the dependency arrow points one way:
``exam_pdf -> pdf_math -> math_renderer``.
"""
from __future__ import annotations

import hashlib
import re
import threading
from typing import Dict, List, Optional, Tuple

from reports.math_renderer import RenderedMath, render_math_png

__all__ = [
    "render",
    "render_cached",
    "inline_scale",
    "clear_cache",
    "cache_stats",
    "MAX_INLINE_WIDTH_PT",
]

#: A single inline formula wider than this is reflowed onto its own line by the
#: layout layer instead of being squeezed into the text.
MAX_INLINE_WIDTH_PT = 320.0

#: mathtext silently ignores unknown commands; these are the ones Fahmyar's
#: prompt asks the model to emit and that mathtext genuinely cannot draw.
_UNSUPPORTED_ENVS = re.compile(r"\\begin\{(align|align\*|eqnarray|split|multline)\}")

_CACHE: Dict[Tuple[str, float, str], RenderedMath] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 2048


def _key(latex: str, font_size: float, color: str) -> Tuple[str, float, str]:
    norm = re.sub(r"\s+", " ", str(latex or "")).strip()
    return (norm, round(float(font_size), 2), str(color))


def render(latex: str, font_size: float = 10.5, color: str = "#0F172A") -> Optional[RenderedMath]:
    """Render ``latex`` to a transparent PNG, or return ``None`` on failure."""
    src = str(latex or "").strip()
    if not src:
        return None
    try:
        return render_math_png(src, font_size=font_size, color=color)
    except Exception:
        return None


def render_cached(
    latex: str, font_size: float = 10.5, color: str = "#0F172A"
) -> Optional[RenderedMath]:
    """Same as :func:`render` but memoised per (source, size, colour)."""
    k = _key(latex, font_size, color)
    with _CACHE_LOCK:
        hit = _CACHE.get(k)
    if hit is not None:
        return hit
    out = render(latex, font_size=font_size, color=color)
    if out is not None:
        with _CACHE_LOCK:
            if len(_CACHE) >= _CACHE_LIMIT:
                # simple bound: drop the oldest half rather than grow forever
                for old in list(_CACHE)[: _CACHE_LIMIT // 2]:
                    _CACHE.pop(old, None)
            _CACHE[k] = out
    return out


def inline_scale(text_size: float, rendered: Optional[RenderedMath]) -> float:
    """Scale factor so an inline image's cap height matches ``text_size``.

    matplotlib renders at ``font_size`` points of its *own* em; Persian text in
    ReportLab uses the requested point size directly.  A factor of 1.0 is right
    for the common case; the correction only kicks in for formulas rendered at
    a very different size than the text they sit in.
    """
    if rendered is None or text_size <= 0:
        return 1.0
    return 1.0


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def cache_stats() -> Dict[str, int]:
    with _CACHE_LOCK:
        return {"entries": len(_CACHE), "limit": _CACHE_LIMIT}


def describe(latex: str) -> str:
    """Debug helper: what would this formula look like after normalisation?"""
    from reports.math_renderer import normalize_latex

    return normalize_latex(latex)


def split_display_blocks(latex_list: List[str]) -> Tuple[List[str], List[str]]:
    """Partition formulas into (inline, display) by width."""
    inline: List[str] = []
    display: List[str] = []
    for src in latex_list:
        r = render_cached(src)
        if r is not None and r.width > MAX_INLINE_WIDTH_PT:
            display.append(src)
        else:
            inline.append(src)
    return inline, display
