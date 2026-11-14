# -*- coding: utf-8 -*-
"""Page-break policy.

The old code wrapped every question in ``KeepTogether(story)``.  That guarantees
a header never sits alone at the bottom of a page, but it also means a question
that is 5% too tall is pushed whole onto the next page, leaving a large blank
area — measured at ~40% of page 1 in ``baseline/before-hard-p1.png``.

It also cannot succeed: when a single block is taller than the frame, ReportLab
has nowhere to move it and the content overflows the margin anyway.

The policy implemented here keeps the useful half of ``KeepTogether`` without
the waste:

*   **Header + first line of the question text** stay together.  A question
    header at the bottom of a page with its body on the next page is the real
    readability failure; a break *after* the first text line is acceptable.
*   **Options stay with at least the last two text lines.**  Splitting the
    option row from its stem is what makes a question unreadable.
*   **Long questions may break**, but never inside an option row.
*   **Answers** may break freely after their key line.

Implemented with ``CondPageBreak`` + a small grouping helper rather than
``KeepTogether``, because ``CondPageBreak`` measures the *available* space and
only forces a break when the next chunk genuinely will not fit.
"""
from __future__ import annotations

from typing import List, Sequence

from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Flowable, KeepTogether, Spacer

__all__ = [
    "guard_header",
    "guard_options",
    "guard_block",
    "guard_group",
    "question_story",
    "answer_story",
    "SPACE_AFTER_QUESTION",
]

SPACE_AFTER_QUESTION = 4.5 * mm

#: Minimum vertical space that must remain for a question header to be worth
#: placing: the header band plus the first line of body text.
HEADER_GUARD_PT = 46.0

#: Minimum space for the option row not to be orphaned from its stem.
OPTIONS_GUARD_PT = 58.0


def guard_header() -> Flowable:
    """Force a page break if less than a header's worth of space is left."""
    return CondPageBreak(HEADER_GUARD_PT)


def guard_options() -> Flowable:
    """Force a page break if the option row would be orphaned."""
    return CondPageBreak(OPTIONS_GUARD_PT)


def question_story(
    header: Sequence[Flowable],
    body: Sequence[Flowable],
    extra: Sequence[Flowable] = (),
    options: Sequence[Flowable] = (),
    tail: Sequence[Flowable] = (),
    keep_header_with_first_line: bool = True,
) -> List[Flowable]:
    """Assemble one question with intelligent break points.

    ``header``   question number band
    ``body``     question stem (may break)
    ``extra``    diagrams / spacers between stem and options
    ``options``  the four-option row (must not be split)
    ``tail``     trailing spacer
    """
    story: List[Flowable] = []
    story.append(guard_header())

    if keep_header_with_first_line and body:
        # header + first body flowable as an atomic unit, the rest flows
        story.append(KeepTogether([*header, body[0]]))
        story.extend(body[1:])
    else:
        story.extend(header)
        story.extend(body)

    story.extend(extra)

    if options:
        story.append(guard_options())
        # The option row itself is a single Flowable, so it can never be split;
        # keeping it with the preceding spacer avoids a stranded gap at a page
        # bottom.
        story.append(KeepTogether(list(options)))

    story.extend(tail)
    return story


def answer_story(
    header: Sequence[Flowable],
    preview: Sequence[Flowable] = (),
    key: Sequence[Flowable] = (),
    explanation: Sequence[Flowable] = (),
    tail: Sequence[Flowable] = (),
) -> List[Flowable]:
    """Assemble one answer-key block.

    Unlike a question, an answer key has no options to keep attached, so a long
    explanation is allowed to break across pages.  Only the header + the key
    line are kept together.
    """
    story: List[Flowable] = [guard_header()]
    story.append(KeepTogether([*header, *key]))
    story.extend(preview)
    story.extend(explanation)
    story.extend(tail)
    return story


def measure_height(flowables: Sequence[Flowable], width: float) -> float:
    """Total wrapped height of ``flowables`` at ``width`` — used by tests."""
    total = 0.0
    for f in flowables:
        try:
            _, h = f.wrap(width, 10_000)
        except Exception:
            h = 0.0
        total += float(h or 0.0)
        total += float(getattr(f, "getSpaceBefore", lambda: 0)() or 0)
        total += float(getattr(f, "getSpaceAfter", lambda: 0)() or 0)
    return total


def guard_block(flowable, wide_width: float = 492.0) -> Flowable:
    """Keep ``flowable`` whole: break the page first if it cannot fit.

    ``CondPageBreak`` needs the height up front; a ``Table`` only knows it after
    ``wrap``, so we measure it here (with a generous width) and emit a break of
    that height.  This is what stops the answer-sheet grid from being split into
    a 7-row sliver followed by an almost-empty page.
    """
    try:
        _, h = flowable.wrap(wide_width, 10_000)
        need = float(h) + 6.0
    except Exception:
        need = 120.0
    return CondPageBreak(min(need, 640.0))


def guard_group(flowables: Sequence[Flowable], width: float = 492.0) -> Flowable:
    """Keep a banner and its table on the same page.

    Returns a ``KeepTogether`` of the measured group *preceded* by a
    ``CondPageBreak`` equal to the group's height, so ReportLab breaks the page
    before drawing anything rather than after the heading is already placed.
    """
    total = 0.0
    for f in flowables:
        try:
            _, h = f.wrap(width, 10_000)
            total += float(h or 0.0)
        except Exception:
            total += 0.0
        total += float(getattr(f, "getSpaceBefore", lambda: 0)() or 0)
        total += float(getattr(f, "getSpaceAfter", lambda: 0)() or 0)
    guard = CondPageBreak(min(total + 6.0, 700.0))

    class _Group(Flowable):
        """CondPageBreak followed by a KeepTogether, as one flowable."""

        def __init__(self) -> None:
            super().__init__()
            self._items = list(flowables)
            self.height = total

        def wrap(self, aw, ah):  # noqa: N802
            return aw, 0.0     # zero height: the guard does the spacing work

        def draw(self) -> None:
            pass

    return _GuardedGroup(guard, KeepTogether(list(flowables)))


class _GuardedGroup(Flowable):
    """Emits a conditional page break, then the grouped flowables."""

    def __init__(self, guard: Flowable, group: Flowable) -> None:
        super().__init__()
        self._guard = guard
        self._group = group

    def wrap(self, aw, ah):  # noqa: N802
        return aw, 0.0

    def draw(self) -> None:
        pass

    def split(self, aw, ah):  # noqa: N802
        return [self._guard, self._group]
