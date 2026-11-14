# -*- coding: utf-8 -*-
"""Compatibility shim — the text flow module was split up.

The old module mixed three concerns: classifying text vs. math, laying out a
paragraph with inline formulas, and drawing the four-option row.  Those now
live in:

    reports/pdf_content_parser.py   classification + splitting
    reports/pdf_text_flow_v2.py     rendering + options row
    reports/pdf_typography.py       shaping / BiDi

This file exists only so older imports (``from reports.pdf_text_flow import
split_math_segments``) keep working.  New code should import from the modules
above directly.  Do not add logic here.
"""
from __future__ import annotations

from reports.pdf_content_parser import (  # noqa: F401
    Segment,
    has_math,
    looks_math,
    repair_control_chars,
    split_math_segments,
    wrap_bare_math,
)
from reports.pdf_text_flow_v2 import (  # noqa: F401
    MathRichBlock,
    OptionsRow,
    math_paragraph_flowables,
    simple_text_flowables,
)

__all__ = [
    "Segment",
    "has_math",
    "looks_math",
    "repair_control_chars",
    "split_math_segments",
    "wrap_bare_math",
    "MathRichBlock",
    "OptionsRow",
    "math_paragraph_flowables",
    "simple_text_flowables",
]
