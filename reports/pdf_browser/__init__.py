# -*- coding: utf-8 -*-
"""Browser-based exam PDF production.

Replaces the ReportLab drawing engine.  A headless Chromium renders the exam
through the app's own React print entry point (``frontend/print.html`` →
``PrintExam.jsx`` → the shared ``MathText`` component), we capture one PNG per
A4 sheet, and ReportLab is used only to write the PDF container.

Entry point kept stable for callers::

    from reports.pdf_browser import build_exam_pdf_browser

    pdf_bytes = build_exam_pdf_browser(**same_kwargs_as_build_exam_pdf)
"""
from __future__ import annotations

from .build import build_exam_pdf_browser, BrowserRenderError
from .capture import CaptureError, browser_available
from .packer import pdf_from_images

__all__ = [
    "build_exam_pdf_browser",
    "BrowserRenderError",
    "CaptureError",
    "browser_available",
    "pdf_from_images",
]
