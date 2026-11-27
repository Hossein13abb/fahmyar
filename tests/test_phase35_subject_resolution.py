"""فاز ۳۵ — تشخیصِ درسِ واقعیِ مفهوم (جلوگیری از نمایشِ «ریاضی» برای فیزیک/شیمی).

── سابقهٔ باگ ──
کاربر دو آزمونِ «ایزوتوپ‌ها...» (شیمی) و «فشار در شارها...» (فیزیک) را در
تاریخچه دید که هر دو برچسبِ «mathematics» (و سپس «ریاضی») گرفته بودند،
چون ``curriculum_bridge.py`` هنگامِ ساختِ مفهوم، ``subject`` را با نامِ
رشته (``mathematics`` / ``experimental``) پر می‌کرد.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from curriculum_bridge import resolve_concept, resolve_subject_display
from models.concept import Concept
from models.database import Base


def _mem_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_resolve_subject_display_extracts_chemistry_and_physics_from_legacy_rows():
    chem = Concept(
        subject="mathematics",
        grade=10,
        chapter="فصل ۱",
        topic="chem10-c1",
        name="ایزوتوپ‌ها، جرم اتمی میانگین و مفهوم مول و عدد آووگادرو",
        core_propositions=[
            "ایزوتوپ‌ها",
            "جایگاهِ این مفهوم در کتابِ شیمی ۱",
        ],
    )
    phy = Concept(
        subject="mathematics",
        grade=10,
        chapter="فصل ۲",
        topic="phy10-c5",
        name="فشار در شاره‌ها و محاسبه فشار در عمق مایعات",
        core_propositions=[
            "فشار در شاره‌ها",
            "جایگاهِ این مفهوم در کتابِ فیزیک ۱",
        ],
    )
    assert resolve_subject_display(chem) == "شیمی"
    assert resolve_subject_display(phy) == "فیزیک"


def test_resolve_subject_display_falls_back_to_topic_prefix():
    bio = Concept(
        subject="experimental",
        grade=10,
        chapter="",
        topic="bio10-ch1-c1",
        name="یاخته",
        core_propositions=[],
    )
    assert resolve_subject_display(bio) == "biology"


def test_resolve_concept_stores_actual_subject_for_new_rows():
    db = _mem_session()
    c_phy = resolve_concept(
        db,
        concept_id=None,
        curriculum={
            "major": "mathematics",
            "grade": "10",
            "subjectId": "physics-10",
            "subjectTitle": "فیزیک ۱",
            "chapterTitle": "فصل ۲: ویژگی‌های فیزیکی مواد",
            "conceptId": "phy10-c5",
            "conceptTitle": "فشار در شاره‌ها و محاسبه فشار در عمق مایعات",
        },
    )
    c_chem = resolve_concept(
        db,
        concept_id=None,
        curriculum={
            "major": "mathematics",
            "grade": "10",
            "subjectId": "chemistry-10",
            "subjectTitle": "شیمی ۱",
            "chapterTitle": "فصل ۱: کیهان زادگاه الفبای هستی",
            "conceptId": "chem10-c3",
            "conceptTitle": "ایزوتوپ‌ها، جرم اتمی میانگین و مفهوم مول و عدد آووگادرو",
        },
    )
    assert c_phy.subject == "physics"
    assert c_chem.subject == "chemistry"
