# -*- coding: utf-8 -*-
"""Content parser — one pipeline, one classification rule.

The old ``pdf_text_flow._looks_math`` decided "is this math?" by looking for
either a *signal character* (``^ _ = < > |``) OR *a Latin word of 2+ letters*.
The second half was a heuristic for spotting bare LaTeX commands such as
``frac`` or ``sqrt``, but it also matched every ordinary English word, so
``"Which option is correct?"`` was sent to matplotlib and printed with all its
spaces removed.

This module replaces that with an explicit, ordered decision:

    1. Explicit delimiters (``$...$`` / ``$$...$$``)   -> math, no questions asked
    2. Explicit LaTeX commands (``\\frac``, ``\\sqrt``, ``\\begin{...}``) -> math
    3. Signal characters (``^ _ = < > |``) inside a run with NO Persian letters
       AND no 3+ letter Latin word run that reads as prose -> math
    4. Structural arithmetic (operand OP operand)
    5. A short Latin token that matplotlib can actually typeset as a formula
       (``DNA`` -> no; ``x`` -> yes) -> math
    6. Otherwise -> text

The key invariant: **a string that contains 3+ whitespace-separated Latin
words is prose, never math.**  Real formulas written by the model that are that
long always carry an operator or a delimiter, so rules 1-4 catch them first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

__all__ = [
    "Segment",
    "split_math_segments",
    "has_math",
    "looks_math",
    "wrap_bare_math",
    "repair_control_chars",
    "PERSIAN_DIGITS",
    "LATIN_WORDS_RE",
]

# ---------------------------------------------------------------------------
# Character classes
# ---------------------------------------------------------------------------

#: Persian digits ۰-۹ and Arabic-Indic ٠-٩
PERSIAN_DIGITS = "\u06F0\u06F1\u06F2\u06F3\u06F4\u06F5\u06F6\u06F7\u06F8\u06F9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"

#: Three or more whitespace-separated runs that are pure Latin words => prose.
#: ``The derivative of`` matches; ``x + y`` does not (``+`` is not a word).
LATIN_WORDS_RE = re.compile(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])")

#: RTL letters — a candidate containing any of these is Persian prose, unless
#: it also contains an explicit delimiter or LaTeX command (handled earlier).
#: RTL *letters* — deliberately excludes Arabic-Indic (U+0660-9) and Persian
#: (U+06F0-9) DIGITS.  They live inside the Arabic block but are direction
#: neutral, exactly like Latin digits.  Treating them as letters made every
#: expression using Persian digits ("۲×۲", "(A+B)۲-A۲-B۲") look like prose.
_RTL_LETTER_RE = re.compile(
    "["
    "\u0600-\u065F"      # Arabic, minus the Arabic-Indic digits
    "\u066A-\u06EF"      # Arabic, minus the Persian digits
    "\u06FA-\u06FF"
    "\u0750-\u077F\u08A0-\u08FF"
    "\uFB50-\uFDFF\uFE70-\uFEFF"
    "]"
)
_RTL_DIGIT_RE = re.compile(r"[\u0660-\u0669\u06F0-\u06F9]")

#: Characters that may appear inside a bare (undelimited) math candidate.
_MATH_CHARS = (
    "A-Za-z0-9"
    "\\u06F0-\\u06F9\\u0660-\\u0669"
    "\\\\^_=+\\-*/()\\[\\]{}.,<>|:'\"&;"
    "\\u066B\\u066C\\u00D7\\u00F7\\u221A\\u2264\\u2265\\u2260\\u00B1\\u2212\\u221E"
    "\\u00B2\\u00B3\\u00B9\\u2070-\\u2079"     # ²³¹⁰..⁹
    "\\u03B1-\\u03C9\\u0391-\\u03A9"           # Greek letters (α..ω, Α..Ω)
)
_MATH_CANDIDATE_RE = re.compile(rf"[{_MATH_CHARS}]+(?:\s+[{_MATH_CHARS}]+)*")

#: ``$ ... $`` or ``$$ ... $$`` (the display variant wins on equal start)
_DELIM_RE = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$\n]+?\$")

#: A LaTeX control sequence that means "this is really LaTeX", not a word.
#: ``\frac``, ``\sqrt``, ``\begin``, ``\times``, ... but NOT a random English
#: word: the leading backslash is required.
_LATEX_CMD_RE = re.compile(
    r"\\(?:[a-zA-Z]{2,}|[{}%$&#_])"
)

#: Commands that are meaningful even when the model forgot the backslash.
#: These are the ones that actually appear in Fahmyar content.
_BARE_LATEX_CMDS = (
    "frac", "sqrt", "bmatrix", "pmatrix", "vmatrix", "Bmatrix", "Vmatrix",
    "matrix", "cases", "array", "begin", "end", "times", "cdot", "div",
    "pm", "mp", "leq", "geq", "neq", "approx", "equiv", "infty", "sum",
    "int", "lim", "sin", "cos", "tan", "cot", "log", "ln", "exp",
    "alpha", "beta", "gamma", "delta", "theta", "lambda", "mu", "pi",
    "sigma", "phi", "omega", "vec", "hat", "bar", "overline", "underline",
    "left", "right", "mathrm", "displaystyle", "operatorname",
    "angle", "triangle", "parallel", "perp", "cong", "sim", "subset",
    "cup", "cap", "notin", "forall", "exists", "partial", "nabla",
    "rightarrow", "leftarrow", "Rightarrow", "Leftarrow",
    "quad", "qquad", "space", "hspace", "phantom", "binom", "choose",
)
_BARE_CMD_RE = re.compile(
    r"(?<![A-Za-z\\])(?:" + "|".join(sorted(_BARE_LATEX_CMDS, key=len, reverse=True)) + r")(?![A-Za-z])"
)

#: Signal characters that are unambiguous *inside math* and rare in prose.
_SIGNAL_RE = re.compile(r"[\^_=<>|]")

#: Structural arithmetic: operand, operator, operand (one or more times).
_SUP = r"[\u00B2\u00B3\u00B9\u2070-\u2079]"
_OPERAND = (
    r"(?:[A-Za-z]" + _SUP + r"?"
    r"|\\(?:[a-zA-Z]+)(?:\{[^{}]*\})?"
    r"|[0-9]+"
    r"|[\u06F0-\u06F9\u0660-\u0669]+"
    r"|\\(?:left|right)?[(\[][^()\[\]]*\\(?:left|right)?[)\]]"
    r"|\([^()]*\)" + _SUP + r"?"
    r"|[A-Za-z]\s*\^\s*\{?[0-9\u06F0-\u06F9\u0660-\u0669]+\}?"
    r"|[A-Za-z]\s*_\s*\{?[A-Za-z0-9\u06F0-\u06F9]+\}?)"
)
_OPERATOR = r"[+\-*/=\u00D7\u00F7\u00B7\u2212\u00B1\u2264\u2265\u2260]"
_OPERAND_OP_RE = re.compile(rf"{_OPERAND}(?:\s*{_OPERATOR}\s*{_OPERAND})+")

#: A capture that looks like a brace-grouped quantity: ``{...}``.
_BRACE_GROUP_RE = re.compile(r"\{[^{}]*\}")


# ---------------------------------------------------------------------------
# Segment type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Segment:
    """One piece of parsed content.

    ``kind`` is ``"text"`` or ``"math"``.  For math, ``payload`` is the LaTeX
    source **without** dollar delimiters and ``display`` says whether it was
    ``$$...$$``.
    """

    kind: str
    payload: str
    display: bool = False

    # -- backwards compatibility with the old ``(kind, payload, display)`` tuple
    def __iter__(self):
        yield self.kind
        yield self.payload
        yield self.display

    def __getitem__(self, idx):
        return (self.kind, self.payload, self.display)[idx]

    def __len__(self) -> int:
        return 3

    def __eq__(self, other):
        if isinstance(other, Segment):
            return (self.kind, self.payload, self.display) == (
                other.kind,
                other.payload,
                other.display,
            )
        if isinstance(other, tuple):
            return (self.kind, self.payload, self.display) == other
        return NotImplemented

    def __hash__(self):
        return hash((self.kind, self.payload, self.display))


# ---------------------------------------------------------------------------
# Core classification
# ---------------------------------------------------------------------------

def _strip_delimiters(raw: str) -> Tuple[str, bool]:
    s = raw.strip()
    if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
        return s[2:-2].strip(), True
    if s.startswith("$") and s.endswith("$") and len(s) > 2:
        return s[1:-1].strip(), False
    return s, False


def looks_math(candidate: str) -> bool:
    """Decide whether ``candidate`` (no delimiters) is a formula.

    See the module docstring for the ordered rules.
    """
    g = str(candidate or "").strip()
    if not g:
        return False
    if len(g) > 400:
        return False

    # ---- Rule 0: explicit LaTeX command wins outright -------------------
    if _LATEX_CMD_RE.search(g):
        return True
    if _BARE_CMD_RE.search(g):
        return True

    # ---- Rule 1: prose guard -------------------------------------------
    # Any Persian letter means this is Persian text (formulas never contain
    # Persian letters — only Persian *digits*, which are a different range).
    if _RTL_LETTER_RE.search(g):
        return False

    # Three or more 2+ letter Latin words = prose, regardless of the odd
    # hyphen or colon that happens to be present ("multi-page test").
    words = LATIN_WORDS_RE.findall(g)
    if len(words) >= 3:
        letters = sum(1 for ch in g if ch.isalpha())
        symbols = sum(1 for ch in g if ch in "+-*/=×÷·−±≤≥≠^_<>|")
        # Real formulas are symbol-dense; prose is not.  10 words and one
        # hyphen is prose; "x^{۲}+y^{۲}=۱" has 4 letters and 5 symbols.
        if symbols == 0 or letters > symbols * 4:
            return False
    has_operator = bool(_OPERATOR_STR_RE.search(g)) or bool(_SIGNAL_RE.search(g))

    # ---- Rule 2: signal characters -------------------------------------
    if _SIGNAL_RE.search(g):
        # ``x=1`` yes; ``a < b`` yes; but a long sentence containing ``<`` in
        # prose is still prose — require that the candidate isn't wordy.
        return len(words) <= 6

    # ---- Rule 3: structural arithmetic ---------------------------------
    if _OPERAND_OP_RE.search(g):
        return True

    # ---- Rule 4: single short Latin token that is a real symbol --------
    # ``x``, ``A``, ``AB`` -> plausible; ``DNA``, ``UNESCO`` -> acronyms.
    if re.fullmatch(r"[A-Za-z]{1,2}", g):
        return True

    # ---- Rule 5: coordinate / function-call shorthand -------------------
    if re.fullmatch(r"[A-Za-z]\s*\(\s*-?\d+\s*(?:,\s*-?\d+\s*){1,3}\)", g):
        return True

    # ---- Rule 6: a lone number is NOT math (renderer adds no value) -----
    return False


_OPERATOR_STR_RE = re.compile(_OPERATOR)


def has_math(text) -> bool:
    """True if ``text`` contains at least one math segment."""
    return any(seg.kind == "math" for seg in split_math_segments(text))


# ---------------------------------------------------------------------------
# Bare-LaTeX wrapping
# ---------------------------------------------------------------------------

def wrap_bare_math(chunk: str) -> str:
    """Wrap undelimited LaTeX commands in ``$...$`` so the splitter sees them.

    ``\\frac{1}{2}`` -> ``$\\frac{1}{2}$``; ``۲ \\times ۲`` -> ``$۲ \\times ۲$``.
    Already-delimited input is returned unchanged.
    """
    s = str(chunk or "")
    if not s or "$" in s:
        return s

    out = s
    # 1) commands with brace arguments: \frac{a}{b}, \sqrt{x}, \vec{v}
    pattern = re.compile(
        r"\\?(?:" + "|".join(
            ("frac", "dfrac", "tfrac", "binom")
        ) + r")\s*(?:\{[^{}]*\}\s*){1,2}"
    )
    out = pattern.sub(lambda m: f"${m.group(0)}$", out)
    if out != s:
        return out

    # 2) \sqrt{...} or \sqrt[n]{...}
    pattern = re.compile(r"\\?sqrt\s*(?:\[[^\[\]]*\]\s*)?\{[^{}]*\}")
    out = pattern.sub(lambda m: f"${m.group(0)}$", out)
    if out != s:
        return out

    # 3) environments: \begin{bmatrix} ... \end{bmatrix}
    pattern = re.compile(r"\\?begin\s*\{[bpvBVm]?matrix\*?\}[\s\S]*?\\?end\s*\{[bpvBVm]?matrix\*?\}")
    out = pattern.sub(lambda m: f"${m.group(0)}$", out)
    if out != s:
        return out

    # 4) inline expressions with a bare command + surrounding operands
    if _BARE_CMD_RE.search(s) or _LATEX_CMD_RE.search(s):
        # take the largest math-character run that contains the command
        def _wrap_run(m: re.Match) -> str:
            run = m.group(0)
            if _BARE_CMD_RE.search(run) or _LATEX_CMD_RE.search(run):
                return f"${run.strip()}$"
            return run

        out = _MATH_CANDIDATE_RE.sub(_wrap_run, s)
        if out != s:
            return out

    return s


#: JSON parsers turn "\\begin" into backspace + "egin" and "\\frac" into
#: form-feed + "rac".  Both must be restored before anything else looks at the
#: text, otherwise the LaTeX command is silently destroyed.
_CONTROL_REPAIRS = {
    "\x08": "\\b",   # \b  (backspace)  -> \begin, \bmatrix
    "\x0c": "\\f",   # \f  (form feed)  -> \frac
    "\x07": "\\a",   # \a               -> \alpha
    "\x0b": "\\v",   # \v               -> \vec
    "\x0d": " ",      # CR
}


def repair_control_chars(text: str) -> str:
    """Undo JSON's control-character damage and drop illegal C0/C1 bytes."""
    s = str(text or "")
    for bad, good in _CONTROL_REPAIRS.items():
        if bad in s:
            s = s.replace(bad, good)
    return "".join(ch for ch in s if ch in "\n\t" or ord(ch) >= 0x20)


# ---------------------------------------------------------------------------
# The splitter
# ---------------------------------------------------------------------------

def split_math_segments(text) -> List[Segment]:
    """Split mixed Persian/English/math content into ordered segments.

    Order of operations matters (ANALYSIS.md bug: running the bare-LaTeX regex
    before wrapping shatters ``۲ \\times ۲`` into three pieces):

        1. repair control chars
        2. wrap undelimited LaTeX   <-- must happen BEFORE any regex split
        3. split on $...$ / $$...$$
        4. sweep the text pieces for remaining bare math runs
    """
    s = repair_control_chars(str(text or ""))
    if not s:
        return []

    # Any math at all?
    if "$" not in s and not _LATEX_CMD_RE.search(s) and not _BARE_CMD_RE.search(s) \
            and not _MATH_CANDIDATE_RE.search(s):
        return [Segment("text", s)]

    s = wrap_bare_math(s)

    out: List[Segment] = []

    def _push_text(chunk: str) -> None:
        """Sweep a text chunk for bare math runs that survived wrapping."""
        if not chunk:
            return
        pos = 0
        for m in _MATH_CANDIDATE_RE.finditer(chunk):
            before = chunk[pos:m.start()]
            if before:
                out.append(Segment("text", before))
            run = m.group(0)
            if looks_math(run):
                out.append(Segment("math", run.strip(), False))
            else:
                out.append(Segment("text", run))
            pos = m.end()
        tail = chunk[pos:]
        if tail:
            out.append(Segment("text", tail))

    pos = 0
    for m in _DELIM_RE.finditer(s):
        _push_text(s[pos:m.start()])
        inner, display = _strip_delimiters(m.group(0))
        if inner:
            out.append(Segment("math", inner, display))
        pos = m.end()
    _push_text(s[pos:])

    # merge adjacent text segments (they read better as one paragraph)
    merged: List[Segment] = []
    for seg in out:
        if merged and seg.kind == "text" and merged[-1].kind == "text":
            merged[-1] = Segment("text", merged[-1].payload + seg.payload)
        else:
            merged.append(seg)
    return merged or [Segment("text", s)]


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def math_segments(text) -> List[Segment]:
    return [s for s in split_math_segments(text) if s.kind == "math"]


def text_of(text) -> str:
    return "".join(s.payload for s in split_math_segments(text) if s.kind == "text")
