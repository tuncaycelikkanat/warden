"""Technical Debt Remediation Effort & Time Estimation Engine.

Estimates the engineering time (hours and person-days) required to resolve
codebase technical debt using an empirical SQALE-inspired model across:
- Cyclomatic Complexity Debt: Refactoring high-complexity functions (CC > 10).
- Code Hygiene Markers: Resolving FIXME, TODO, HACK, and XXX comments.
- Git Churn Hotspots: Stabilizing and adding test coverage to high-frequency churn files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Standard engineering remediation hours per marker type
MARKER_EFFORT_MAP: dict[str, float] = {
    "FIXME": 1.0,
    "HACK": 1.5,
    "XXX": 1.5,
    "TODO": 0.5,
}


@dataclass
class RemediationPriorityItem:
    """Represents a specific high-ROI technical debt refactoring target."""

    category: str      # "complexity" | "marker" | "hotspot"
    location: str      # file:line or file:function
    description: str
    effort_hours: float
    priority_rank: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "location": self.location,
            "description": self.description,
            "effort_hours": round(self.effort_hours, 1),
            "priority_rank": self.priority_rank,
        }


@dataclass
class TechDebtRemediationEstimate:
    """Aggregated estimate of technical debt remediation time and effort."""

    total_hours: float
    total_days: float
    complexity_hours: float
    markers_hours: float
    churn_hotspot_hours: float
    breakdown: dict[str, float] = field(default_factory=dict)
    priority_items: list[RemediationPriorityItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_hours": round(self.total_hours, 1),
            "total_days": round(self.total_days, 1),
            "complexity_hours": round(self.complexity_hours, 1),
            "markers_hours": round(self.markers_hours, 1),
            "churn_hotspot_hours": round(self.churn_hotspot_hours, 1),
            "breakdown": {k: round(v, 1) for k, v in self.breakdown.items()},
            "priority_items": [item.to_dict() for item in self.priority_items[:10]],
        }


class TechDebtEstimator:
    """Calculates remediation effort from technical debt metrics and complexity."""

    def estimate(
        self,
        todo_markers: list[Any] | None = None,
        churn_entries: list[Any] | None = None,
        outlier_blocks: list[dict[str, Any]] | None = None,
    ) -> TechDebtRemediationEstimate:
        """Computes comprehensive remediation hours and top priority targets."""
        todo_markers = todo_markers or []
        churn_entries = churn_entries or []
        outlier_blocks = outlier_blocks or []

        candidate_items: list[RemediationPriorityItem] = []

        # 1. Calculate Code Marker Effort
        markers_hours = 0.0
        for marker in todo_markers:
            m_type = getattr(marker, "marker", "").upper() if hasattr(marker, "marker") else str(marker.get("marker", "")).upper()
            m_file = getattr(marker, "file", "") if hasattr(marker, "file") else str(marker.get("file", ""))
            m_line = getattr(marker, "line", 0) if hasattr(marker, "line") else marker.get("line", 0)
            m_text = getattr(marker, "text", "") if hasattr(marker, "text") else str(marker.get("text", ""))

            effort = MARKER_EFFORT_MAP.get(m_type, 0.5)
            markers_hours += effort

            if m_type in ("FIXME", "HACK", "XXX"):
                candidate_items.append(
                    RemediationPriorityItem(
                        category="marker",
                        location=f"{m_file}:{m_line}",
                        description=f"Resolve {m_type}: {m_text[:60]}",
                        effort_hours=effort,
                    )
                )

        # 2. Calculate Cyclomatic Complexity Effort
        complexity_hours = 0.0
        for block in outlier_blocks:
            cc = block.get("complexity", 0)
            file_name = block.get("file", "unknown")
            block_name = block.get("name", "function")
            line = block.get("line", 1)

            if cc > 10:
                # 0.5 base hours + 0.15 hours per point above 10
                effort = 0.5 + 0.15 * (cc - 10)
                complexity_hours += effort

                candidate_items.append(
                    RemediationPriorityItem(
                        category="complexity",
                        location=f"{file_name}:{line} ({block_name})",
                        description=f"Refactor high-complexity block (CC={cc})",
                        effort_hours=effort,
                    )
                )

        # 3. Calculate Churn Hotspot Stabilization Effort
        churn_hours = 0.0
        for entry in churn_entries:
            file_name = getattr(entry, "file", "") if hasattr(entry, "file") else str(entry.get("file", ""))
            commits = getattr(entry, "commit_count", 0) if hasattr(entry, "commit_count") else entry.get("commit_count", 0)
            age = getattr(entry, "age_days", 0) if hasattr(entry, "age_days") else entry.get("age_days", 0)

            # Hotspot criteria: frequent modifications in an aged file
            if commits >= 8 and age >= 14:
                effort = min(4.0, 1.0 + 0.1 * commits)
                churn_hours += effort

                candidate_items.append(
                    RemediationPriorityItem(
                        category="hotspot",
                        location=file_name,
                        description=f"Stabilize high-churn hotspot ({commits} commits over {age} days)",
                        effort_hours=effort,
                    )
                )

        total_hours = markers_hours + complexity_hours + churn_hours
        total_days = total_hours / 8.0

        # Sort candidate priorities by effort descending
        candidate_items.sort(key=lambda x: x.effort_hours, reverse=True)
        for i, item in enumerate(candidate_items, start=1):
            item.priority_rank = i

        breakdown = {
            "complexity": complexity_hours,
            "markers": markers_hours,
            "churn_hotspots": churn_hours,
        }

        return TechDebtRemediationEstimate(
            total_hours=total_hours,
            total_days=total_days,
            complexity_hours=complexity_hours,
            markers_hours=markers_hours,
            churn_hotspot_hours=churn_hours,
            breakdown=breakdown,
            priority_items=candidate_items[:10],
        )
