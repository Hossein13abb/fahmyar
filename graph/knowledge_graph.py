"""گراف دانش فهم‌یار — DAG جهت‌دار با NetworkX برای وابستگی‌های بین‌درسی.

یال‌ها از پیش‌نیاز به سمت مفهوم هدف هستند؛ یعنی برای یافتن «ریشهٔ احتمالی خطا»
باید از گرهٔ مفهومی که دانش‌آموز در آن خطا کرده، به سمت عقب (predecessors) برویم.
"""
from __future__ import annotations

from typing import Any, Optional

import networkx as nx
from sqlalchemy.orm import Session

from models.concept import Concept, ConceptDependency

# اولویت نوع وابستگی برای انواع خطا (برای ریشه‌یابی)
_ERROR_PRIORITY = {
    "computational": {"tool": 0, "prerequisite": 1, "related": 2},
    "procedural": {"tool": 0, "prerequisite": 1, "related": 2},
    "conceptual": {"prerequisite": 0, "related": 1, "tool": 2},
    "misconception": {"prerequisite": 0, "related": 1, "tool": 2},
}


def _concept_to_node(concept: Concept) -> dict[str, Any]:
    return {
        "id": concept.id,
        "subject": concept.subject,
        "grade": concept.grade,
        "chapter": concept.chapter,
        "topic": concept.topic,
        "name": concept.name,
        "core_propositions": list(concept.core_propositions or []),
        "common_misconceptions": list(concept.common_misconceptions or []),
        "target_behaviors": list(concept.target_behaviors or []),
    }


class KnowledgeGraph:
    """گراف جهت‌دار مفاهیم. معمولاً از دیتابیس بارگذاری می‌شود و فقط‌خواندنی است."""

    def __init__(self) -> None:
        self.G = nx.DiGraph()

    # ---------- ساخت ----------
    def add_concept(self, db: Session, concept_data: dict) -> Concept:
        """یک مفهوم را در دیتابیس می‌سازد/به‌روزرسانی می‌کند و گره‌اش را در گراف می‌گذارد.

        کلید یکتا: (subject, topic)
        """
        concept = (
            db.query(Concept)
            .filter(Concept.subject == concept_data["subject"], Concept.topic == concept_data["topic"])
            .first()
        )
        if concept is None:
            concept = Concept(
                subject=concept_data["subject"],
                topic=concept_data["topic"],
            )
        concept.grade = concept_data.get("grade", 10)
        concept.chapter = concept_data.get("chapter", "")
        concept.name = concept_data.get("name", concept_data["topic"])
        concept.core_propositions = concept_data.get("core_propositions", [])
        concept.common_misconceptions = concept_data.get("common_misconceptions", [])
        concept.target_behaviors = concept_data.get("target_behaviors", [])
        db.add(concept)
        db.flush()
        self.G.add_node(concept.id, **_concept_to_node(concept))
        return concept

    def add_dependency(
        self,
        db: Session,
        source_concept_id: int,
        target_concept_id: int,
        dependency_type: str = "prerequisite",
        cross_subject: bool = False,
    ) -> ConceptDependency:
        if dependency_type not in {"prerequisite", "tool", "related"}:
            raise ValueError(f"dependency_type نامعتبر: {dependency_type}")
        dep = (
            db.query(ConceptDependency)
            .filter(
                ConceptDependency.source_concept_id == source_concept_id,
                ConceptDependency.target_concept_id == target_concept_id,
                ConceptDependency.dependency_type == dependency_type,
            )
            .first()
        )
        if dep is None:
            dep = ConceptDependency(
                source_concept_id=source_concept_id,
                target_concept_id=target_concept_id,
                dependency_type=dependency_type,
                cross_subject=cross_subject,
            )
            db.add(dep)
            db.flush()
        self.G.add_edge(
            source_concept_id,
            target_concept_id,
            dependency_type=dependency_type,
            cross_subject=bool(cross_subject),
        )
        return dep

    def load_from_db(self, db: Session) -> "KnowledgeGraph":
        self.G.clear()
        for concept in db.query(Concept).all():
            self.G.add_node(concept.id, **_concept_to_node(concept))
        for dep in db.query(ConceptDependency).all():
            self.G.add_edge(
                dep.source_concept_id,
                dep.target_concept_id,
                dependency_type=dep.dependency_type,
                cross_subject=bool(dep.cross_subject),
            )
        return self

    # ---------- پرس‌وجو ----------
    def concept(self, concept_id: int) -> Optional[dict[str, Any]]:
        if concept_id in self.G:
            return dict(self.G.nodes[concept_id])
        return None

    def get_prerequisites(self, concept_id: int, depth: int = 2) -> list[dict[str, Any]]:
        """همهٔ مفاهیم بالادستی (پیش‌نیازها، ابزارها) را با BFS برمی‌گرداند.

        خروجی هر آیتم: {id, subject, topic, name, depth, dependency_type, cross_subject, path}
        """
        if concept_id not in self.G:
            return []
        results: list[dict[str, Any]] = []
        seen: set[int] = set()
        # هر سطح: (node_id, current_depth, path_edges, path_nodes)
        queue: list[tuple[int, int, list[tuple[str, bool]], list[int]]] = [
            (concept_id, 0, [], [concept_id])
        ]
        while queue:
            node, d, edges, path = queue.pop(0)
            if d >= depth:
                continue
            for pred in self.G.predecessors(node):
                if pred in path or pred in seen:
                    continue
                edge = self.G.edges[pred, node]
                new_edges = edges + [(edge.get("dependency_type", "prerequisite"), bool(edge.get("cross_subject", False)))]
                attr = self.G.nodes[pred]
                results.append(
                    {
                        "id": pred,
                        "subject": attr.get("subject"),
                        "grade": attr.get("grade"),
                        "topic": attr.get("topic"),
                        "name": attr.get("name"),
                        "depth": d + 1,
                        "dependency_type": edge.get("dependency_type", "prerequisite"),
                        "cross_subject": bool(edge.get("cross_subject", False)),
                        "path": [self.G.nodes[p].get("topic") for p in path + [pred]],
                    }
                )
                seen.add(pred)
                queue.append((pred, d + 1, new_edges, path + [pred]))
        # مرتب‌سازی: ابتدا نزدیک‌ترین و میان‌درسی
        results.sort(key=lambda c: (not c["cross_subject"], c["depth"]))
        return results

    def get_root_cause_candidates(
        self, concept_id: int, error_type: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """با توجه به مفهومِ ناموفق، کاندیداهای ریشهٔ خطا را برمی‌گرداند.

        error_type: "conceptual" | "computational" | "procedural" | "misconception" | None
        خطای محاسباتی → ابزارهای ریاضی زودتر بررسی می‌شوند؛ خطای مفهومی → پیش‌نیازهای هم‌درس.
        """
        candidates = self.get_prerequisites(concept_id, depth=3)
        priority = _ERROR_PRIORITY.get((error_type or "").lower(), {"prerequisite": 0, "tool": 1, "related": 2})
        candidates.sort(
            key=lambda c: (
                priority.get(c["dependency_type"], 1),
                0 if c["cross_subject"] else 1,
                c["depth"],
            )
        )
        return candidates

    def get_isolating_question_target(
        self, failed_concept_id: int, passed_prerequisites: list[int]
    ) -> Optional[dict[str, Any]]:
        """کدام پیش‌نیاز را بعد بررسی کنیم تا ریشهٔ خطا ایزوله شود؟

        پیش‌نیازهای قبول‌نشده (تست‌نشده یا رد‌شده) اولویت دارند؛
        ابزارهای بین‌درسی و کم‌عمق‌ترها مقدم‌اند.
        """
        passed = set(passed_prerequisites or [])
        candidates = self.get_prerequisites(failed_concept_id, depth=2)
        remaining = [c for c in candidates if c["id"] not in passed]
        if not remaining:
            return None
        remaining.sort(key=lambda c: (0 if c["cross_subject"] else 1, c["depth"]))
        return remaining[0]


def load_graph(db: Session) -> KnowledgeGraph:
    """گراف را از دیتابیس می‌سازد و برمی‌گرداند."""
    return KnowledgeGraph().load_from_db(db)
