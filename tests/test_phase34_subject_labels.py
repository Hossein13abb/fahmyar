"""فاز ۳۴ — نامِ درس در UI نباید انگلیسی باشد.

── سابقهٔ باگ (گزارشِ واقعیِ کاربر) ──
در کارتِ «تاریخچهٔ آزمون‌های من» این دیده می‌شد:

    mathematics · فشار در شارها و محاسبه فشار در عمق مایعات

درحالی‌که باید فارسی بود («ریاضی»). علت: وقتی مفهوم از انتخاب‌گرِ
کوریکولوم ساخته می‌شود، ``curriculum_bridge.py`` مقدارِ ``subject`` را با
**نامِ رشته** پر می‌کند (``mathematics`` / ``experimental``)، ولی نگاشتِ
برچسبِ فارسی در فرانت (``SUBJECT_FA``) و بک‌اند (``_SUBJECT_LABELS``) فقط
``math`` را می‌شناخت. پس تابعِ ترجمه به مقدارِ خامِ انگلیسی برمی‌گشت.

── درسِ این فایل ──
هر مقدارِ ``subject`` که سیستم می‌تواند بسازد باید برچسبِ فارسی داشته
باشد. این تست، مقادیرِ واقعیِ پلِ کوریکولوم را می‌خواند و هر دو نگاشت
(فرانت و بک‌اند) را در برابرشان چک می‌کند — تا اگر روزی رشتهٔ تازه‌ای
اضافه شد، تست بلافاصله بگوید.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bridge_subject_values() -> set[str]:
    """مقادیرِ ``subject`` که پلِ کوریکولوم می‌تواند در دیتابیس بگذارد."""
    import curriculum_bridge

    return set(curriculum_bridge._MAJOR_TO_SUBJECT.values())


def _seed_subject_values() -> set[str]:
    """مقادیرِ ``subject`` در دادهٔ اولیهٔ دیتابیس (seed)."""
    src = (ROOT / "models" / "database.py").read_text(encoding="utf-8")
    return set(re.findall(r'subject="([a-z_]+)"', src))


def _frontend_subject_keys() -> set[str]:
    """کلیدهای نگاشتِ ``SUBJECT_FA`` در فایلِ JS فرانت."""
    src = (ROOT / "frontend" / "src" / "utils" / "faNumbers.js").read_text(encoding="utf-8")
    block = re.search(r"SUBJECT_FA\s*=\s*\{(.*?)\}", src, re.DOTALL)
    assert block, "نگاشتِ SUBJECT_FA در faNumbers.js پیدا نشد"
    return set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.MULTILINE))


def _all_possible_subjects() -> set[str]:
    """همهٔ مقادیرِ subject که در عمل می‌توانند در دیتابیس باشند."""
    return _bridge_subject_values() | _seed_subject_values() | {
        "physics",
        "chemistry",
        "biology",
    }


# ─────────────────────────────────────────────────────────────────────────
# بک‌اند
# ─────────────────────────────────────────────────────────────────────────
def test_backend_labels_every_possible_subject():
    """``_subject_label`` نباید هیچ‌وقت مقدارِ خامِ انگلیسی برگرداند."""
    from ai.model_abstraction import _subject_label

    missing = []
    for slug in sorted(_all_possible_subjects()):
        label = _subject_label(slug)
        if label == slug:  # یعنی fallback به مقدارِ خام
            missing.append(slug)
    assert not missing, (
        f"این درس‌ها برچسبِ فارسی ندارند و انگلیسی می‌مانند: {missing}"
    )


def test_backend_labels_are_persian():
    """برچسب‌ها باید واقعاً فارسی باشند، نه یک رشتهٔ لاتینِ دیگر."""
    from ai.model_abstraction import _subject_label

    for slug in sorted(_all_possible_subjects()):
        label = _subject_label(slug)
        assert re.search(r"[؀-ۿ]", label), (
            f"برچسبِ «{slug}» فارسی نیست: {label!r}"
        )


def test_mathematics_and_experimental_are_covered():
    """دو مقدارِ خاصِ این باگ — صریح و بدونِ واسطه."""
    from ai.model_abstraction import _subject_label

    assert _subject_label("mathematics") == "ریاضی"
    assert _subject_label("experimental") == "علوم تجربی"


# ─────────────────────────────────────────────────────────────────────────
# فرانت
# ─────────────────────────────────────────────────────────────────────────
def test_frontend_covers_bridge_subject_values():
    """نگاشتِ فرانت باید همهٔ مقادیرِ پلِ کوریکولوم را بشناسد."""
    keys = _frontend_subject_keys()
    missing = _bridge_subject_values() - keys
    assert not missing, (
        f"SUBJECT_FA این‌ها را ندارد و در UI انگلیسی می‌مانند: {sorted(missing)}"
    )


def test_frontend_covers_seed_subject_values():
    """نگاشتِ فرانت باید مقادیرِ seed را هم بشناسد."""
    keys = _frontend_subject_keys()
    missing = _seed_subject_values() - keys
    assert not missing, (
        f"SUBJECT_FA این‌ها را ندارد: {sorted(missing)}"
    )


def test_frontend_has_mathematics_and_experimental():
    """دو کلیدِ خاصِ این باگ — صریح و بدونِ واسطه."""
    keys = _frontend_subject_keys()
    assert "mathematics" in keys
    assert "experimental" in keys


def test_subjectfa_fallback_is_not_silent():
    """مستندسازیِ قرارداد: اگر کلید نباشد، مقدارِ خام برمی‌گردد.

    این همان مکانیزمی است که باگ را ساخت. اگر روزی خواستیم به‌جای آن
    «—» برگردانیم، این تست باید عوض شود — آگاهانه، نه تصادفی.
    """
    src = (ROOT / "frontend" / "src" / "utils" / "faNumbers.js").read_text(encoding="utf-8")
    assert "?? s" in src, "fallbackِ subjectFa عوض شده؛ این تست را بازبینی کن"
