# -*- coding: utf-8 -*-
"""Pack captured page images into a PDF.

This is the only place ReportLab is still used, and only for what it does
better than anything else in the dependency set: writing a valid PDF container
with correct page boxes and a small object table.

No text is laid out here.  No formula is drawn.  No Persian is shaped.  Each
page image is placed full-bleed on its own A4 media box, so the PDF is a pure
image document whose pixels came from the browser.
"""
from __future__ import annotations

import io
from typing import List, Optional, Sequence

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .capture import CapturedPage

__all__ = ["pdf_from_images", "MAX_PAGES", "MAX_TOTAL_BYTES"]

#: Hard limits that keep a malicious or buggy client from exhausting memory.
MAX_PAGES = 120
MAX_TOTAL_BYTES = 220 * 1024 * 1024     # 220 MB of PNG before packing

_A4_W_PT, _A4_H_PT = A4


def pdf_from_images(
    pages: Sequence[CapturedPage],
    title: str = "آزمون — فهم‌یار",
    author: str = "فهم‌یار",
) -> bytes:
    """Return a PDF whose pages are exactly ``pages``, in order.

    The captured image may be shorter than A4 when a sheet ran out of content.
    It is drawn at the top of the media box rather than stretched, so the
    aspect ratio is preserved and nothing is distorted.
    """
    if not pages:
        raise ValueError("pdf_from_images: no pages supplied")
    if len(pages) > MAX_PAGES:
        raise ValueError(f"pdf_from_images: {len(pages)} pages exceeds the {MAX_PAGES} limit")
    total = sum(len(p.png) for p in pages)
    if total > MAX_TOTAL_BYTES:
        raise ValueError(
            f"pdf_from_images: {total / 1e6:.0f} MB of images exceeds the "
            f"{MAX_TOTAL_BYTES / 1e6:.0f} MB limit"
        )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    try:
        c.setTitle(title)
        c.setAuthor(author)
        c.setSubject("آزمون چهارگزینه‌ای")
        c.setCreator("Fahmyar browser renderer")
    except Exception:
        pass

    for page in pages:
        reader = ImageReader(io.BytesIO(page.png))
        iw, ih = reader.getSize()
        if iw <= 0 or ih <= 0:
            continue
        # fit inside the A4 box, preserving the aspect ratio
        scale = min(_A4_W_PT / iw, _A4_H_PT / ih)
        w = iw * scale
        h = ih * scale
        x = (_A4_W_PT - w) / 2.0
        y = _A4_H_PT - h          # anchor to the top edge
        c.drawImage(reader, x, y, width=w, height=h, mask="auto")
        c.showPage()

    c.save()
    return buf.getvalue()
