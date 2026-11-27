"""فاز ۳۲ — سازگاریِ سینتکس با پایتون ۳.۱۱.

سابقهٔ باگ (خطای واقعیِ محیطِ کاربر):
یک لاگِ عیب‌یابی در ``ai/cross_check.py`` نوشته شد با این شکل:

    f"head={ (resp.text or '')[:120]!r }"

کوتیشنِ بیرونی ``"`` بود و داخلِ ``{}`` هم ``''`` می‌آمد. پایتون ۳.۱۲
(پیشنهادِ PEP 701) این را مجاز می‌کند؛ **۳.۱۱ نه**. نتیجه:

    SyntaxError: f-string: expecting '}'

و چون خطا در زمانِ *ایمپورت* بود، کلِ اپ بالا نمی‌آمد — نه یک endpoint
خراب، بلکه کلِ سرور.

── چرا نگهبانِ سادهٔ ``feature_version`` کافی نیست ──
اولین تلاشم این بود که از ``ast.parse(..., feature_version=(3, 11))``
استفاده کنم. اما روی پایتون ۳.۱۳ این تابع همان کدِ باگ‌دار را **می‌پذیرد**:

    >>> ast.parse(BAD, feature_version=(3, 11))   # SyntaxError نمی‌دهد!

دلیل: تفاوت این‌جا در مرحلهٔ *توکنیزه‌شدن* است، نه در گرامر. آرگومانِ
``feature_version`` فقط تولیدِ AST را محدود می‌کند و به توکنایزر نمی‌رسد.
پس تنها سنجهٔ معتبر، اجرای واقعیِ یک مفسرِ ۳.۱۱ است. همین کار را می‌کنیم
و اگر چنین مفسری نبود، تست **skip** می‌شود نه اینکه سبزِ دروغین بدهد.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _python_files() -> list[Path]:
    """همهٔ فایل‌های پایتونِ پروژه، بدونِ venv و پوشه‌های ساخته‌شده."""
    skip = {"venv", ".venv", "__pycache__", ".git", "node_modules", "build", "dist", ".tox"}
    out = []
    for path in ROOT.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        out.append(path)
    return sorted(out)


def _find_python311() -> str | None:
    """مسیرِ یک مفسرِ واقعیِ ۳.۱۱ که **وابستگی‌ها را هم دارد**.

    نکتهٔ مهم: المپیِ مفسرِ خالی به کار نمی‌آید — ``import main`` بدونِ
    fastapi/sqlalchemy شکست می‌خورد و تست، شکستِ محیط را به‌جای شکستِ کد
    گزارش می‌کند. پس اول محیط‌هایی را امتحان می‌کنیم که هم ۳.۱۱ باشند هم
    وابسته‌ها را داشته باشند.
    """
    import os

    candidates: list[str] = []

    # ۱) اگر خودمان داخلِ محیطِ ۳.۱۱ اجرا می‌شویم، همان بهترین گزینه است.
    if sys.version_info[:2] == (3, 11):
        candidates.append(sys.executable)

    # ۲) محیط‌هایی که ممکن است کاربر ساخته باشد.
    candidates += [
        str(ROOT / "venv" / "Scripts" / "python.exe"),   # ویندوز
        str(ROOT / "venv" / "bin" / "python"),           # لینوکس/مک
        str(ROOT / ".venv" / "Scripts" / "python.exe"),
        str(ROOT / ".venv" / "bin" / "python"),
        "/tmp/venv311/bin/python",
    ]

    # ۳) مفسرهای خالی — فقط اگر وابستگی داشته باشند.
    for name in ("python3.11", "python311"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates += [
        str(Path.home() / ".local" / "bin" / "python3.11"),
        "/usr/bin/python3.11",
    ]

    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        try:
            probe = subprocess.run(
                [candidate, "-c", "import sys, fastapi; assert sys.version_info[:2]==(3,11)"],
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return candidate
    return None


PY311 = _find_python311()
ALL_FILES = _python_files()
FILE_IDS = [str(p.relative_to(ROOT)) for p in ALL_FILES]

needs_py311 = pytest.mark.skipif(
    PY311 is None,
    reason=(
        "مفسرِ پایتون ۳.۱۱ با وابستگی‌های نصب‌شده پیدا نشد؛ "
        "برای اجرا: uv venv venv --python 3.11 && uv pip install -r requirements.txt"
    ),
)


def test_we_found_source_files():
    """اگر این تست صفر فایل ببیند، بقیهٔ تست‌های این فایل بی‌معنا سبز می‌شوند."""
    assert len(ALL_FILES) > 20, f"فقط {len(ALL_FILES)} فایل پیدا شد"


# ─────────────────────────────────────────────────────────────────────────
# سنجهٔ اصلی: کامپایل با مفسرِ واقعیِ ۳.۱۱
# ─────────────────────────────────────────────────────────────────────────
@needs_py311
def test_entire_project_compiles_with_real_python311():
    """کلِ پروژه باید با یک مفسرِ **واقعیِ** ۳.۱۱ کامپایل شود.

    یک فراخوانی برای همهٔ فایل‌ها — سریع‌تر از صدها subprocess و همان چیزی
    که کاربر موقعِ ``uvicorn main:app`` تجربه می‌کند.
    """
    script = (
        "import sys, py_compile\n"
        "bad = []\n"
        "for path in sys.argv[1:]:\n"
        "    try:\n"
        "        py_compile.compile(path, cfile=None, doraise=True)\n"
        "    except py_compile.PyCompileError as exc:\n"
        "        bad.append(str(exc))\n"
        "print('\\n'.join(bad))\n"
        "sys.exit(1 if bad else 0)\n"
    )
    result = subprocess.run(
        [PY311, "-c", script, *[str(p) for p in ALL_FILES]],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        "این فایل‌ها با پایتون ۳.۱۱ کامپایل نمی‌شوند:\n" + result.stdout[-3000:]
    )


@needs_py311
def test_main_module_boots_under_python311():
    """``main.py`` باید با ۳.۱۱ کامل ایمپورت شود — نقطهٔ شکستِ کاربر."""
    script = "import main; print('routes', len(main.app.routes))"
    result = subprocess.run(
        [PY311, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"main.py زیرِ پایتون ۳.۱۱ بالا نمی‌آید:\n{result.stderr[-2500:]}"
    )
    assert "routes" in result.stdout


@needs_py311
def test_the_original_bug_is_reproduced_by_python311():
    """نگهبان باید ثابت کند همان الگو را واقعاً می‌گیرد.

    بدونِ این تست، ممکن بود کلِ نگهبان بی‌اثر باشد و هیچ‌وقت نفهمیم.
    این تست همان یک خطِ باگ‌دارِ اصلی را به مفسرِ ۳.۱۱ می‌دهد و انتظارِ
    ``SyntaxError`` دارد.
    """
    buggy = 'x = ""\nprint(f"head={ (x or \'\')[:1]!r }")\n'
    result = subprocess.run(
        [PY311, "-c", buggy], capture_output=True, text=True, timeout=60
    )
    assert result.returncode != 0
    assert "SyntaxError" in result.stderr


def test_feature_version_alone_is_not_enough():
    """مستندسازیِ همان دام: ``feature_version`` این باگ را نمی‌گیرد.

    روی مفسرِ ۳.۱۲+ این فراخوانی بدونِ استثنا برمی‌گردد. اگر روزی پایتون
    رفتارش را عوض کرد و این تست شکست، یعنی می‌توانیم نگهبان را ساده‌تر
    کنیم — و آن هم خبرِ خوبی است.
    """
    import ast

    if sys.version_info < (3, 12):
        pytest.skip("این دام مخصوصِ مفسرهای ۳.۱۲+ است")

    buggy = 'x = ""\nf"head={ (x or \'\')[:1]!r }"\n'
    # عمداً انتظارِ موفقیت داریم — چون این دقیقاً همان چیزی است که
    # نگهبانِ سادهٔ feature_version را بی‌فایده می‌کرد.
    ast.parse(buggy, feature_version=(3, 11))


def test_fixed_pattern_is_accepted_everywhere():
    """شکلِ اصلاح‌شده (محاسبه بیرون از f-string) باید همه‌جا قبول شود."""
    import ast

    fixed = 'raw = ""\nhead = raw[:120]\nlength = len(raw)\nf"len={length} | head={head!r}"\n'
    ast.parse(fixed, feature_version=(3, 11))
    compile(fixed, "<t>", "exec")
