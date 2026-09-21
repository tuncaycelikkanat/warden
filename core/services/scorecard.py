"""Scorecard calculation and aggregation engine for WARDEN audits."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.services.core_group_catalog import CORE_GROUPS, MEMBER_TO_GROUP

logger = logging.getLogger(__name__)


@dataclass
class ScorecardResult:
    """Represents the final aggregated scorecard result and grades."""
    total_score: int
    layer1_score: int
    layer2_score: int
    grade: str  # A+, A, B, C, D, F
    breakdown: dict[str, Any]
    group_scores: dict[str, float] | None = None


class ScorecardAggregatorService:
    """Aggregates Layer 1 member scores and Layer 2 rubrics into hierarchical grades."""

    def __init__(self) -> None:
        """Initializes default layer weights (60% L1, 40% L2)."""
        self.layer1_weight = 0.60
        self.layer2_weight = 0.40

    def calculate(
        self, layer1_data: dict[str, Any], layer2_data: list[dict[str, Any]]
    ) -> ScorecardResult:
        """Calculates final hierarchical scorecard and assigns grade."""
        member_scores = self._extract_member_scores(layer1_data)
        group_scores = self._calc_group_scores(member_scores)
        layer1_score = self._calc_layer1(group_scores)

        if not layer2_data:
            layer2_score = layer1_score
            total = layer1_score
        else:
            layer2_score = self._calc_layer2(layer2_data)
            total = round((layer1_score * self.layer1_weight) + (layer2_score * self.layer2_weight))

        total = max(0, min(100, total))

        return ScorecardResult(
            total_score=total,
            layer1_score=layer1_score,
            layer2_score=layer2_score,
            grade=self._get_grade(total),
            breakdown={
                "layer1_raw": layer1_data,
                "layer2_raw": layer2_data,
                "member_scores": member_scores,
            },
            group_scores=group_scores,
        )

    def _score_security(self, findings: list[dict[str, Any]]) -> float:
        sec_score = 100
        for f in findings:
            sev = f.get("severity", f.get("extra", {}).get("severity", "INFO"))
            if sev == "ERROR":
                sec_score -= 40
            elif sev == "WARNING":
                sec_score -= 10
        return max(0.0, float(sec_score))

    def _score_dependencies(self, entries: list[dict[str, Any]]) -> float:
        dep_score = 100.0
        for d in entries:
            status = d.get("status")
            if status == "failed_check":
                dep_score -= 20.0
            elif status == "version_unpinned":
                dep_score -= 2.0
            dep_score -= len(d.get("known_vulnerabilities", [])) * 5.0
        return max(0.0, min(100.0, float(dep_score)))

    def _score_complexity(self, comp: dict[str, Any]) -> float:
        if not comp:
            return 100.0

        rank_dist = comp.get("rank_distribution")
        if isinstance(rank_dist, dict) and rank_dist:
            total_blocks = sum(rank_dist.values())
            if total_blocks == 0:
                return 100.0

            rank_weights = {"C": 1.0, "D": 2.5, "E": 4.0, "F": 6.0}
            penalty = sum(
                (rank_dist.get(rank, 0) / total_blocks) * weight * 100.0
                for rank, weight in rank_weights.items()
            )
            return max(0.0, min(100.0, round(100.0 - penalty, 2)))

        high_files_val = comp.get("high_complexity_files", [])
        high_files = len(high_files_val) if isinstance(high_files_val, (list, tuple, set)) else int(high_files_val or 0)
        avg = comp.get("avg_complexity", 0.0)
        comp_score = 100.0 - (high_files * 25.0) - (max(0.0, avg - 3.0) * 10.0)
        return max(0.0, min(100.0, round(comp_score, 2)))

    def _score_duplication(self, dup: dict[str, Any]) -> float:
        if not dup:
            return 100.0
        pct = float(dup.get("duplication_pct", 0.0) or 0.0)
        score = max(0.0, 100.0 - (pct * 8.0))
        return max(0.0, min(100.0, round(score, 2)))

    def _score_tech_debt(
        self, debt: Any, complexity: Any = None
    ) -> float:
        if not debt:
            return 100.0

        if isinstance(debt, dict):
            total_commits = int(debt.get("total_commits_in_window", 0) or 1)
            churn_entries = debt.get("churn_entries", [])
            todo_markers = debt.get("todo_markers", [])
        else:
            total_commits = int(getattr(debt, "total_commits_in_window", 0) or 1)
            churn_entries = getattr(debt, "churn_entries", [])
            todo_markers = getattr(debt, "todo_markers", [])

        hotspot_penalty = 0.0

        complex_files: set[str] = set()
        if complexity:
            outlier_blocks = complexity.get("outlier_blocks", []) if isinstance(complexity, dict) else getattr(complexity, "outlier_blocks", [])
            for block in outlier_blocks:
                f = block.get("file") if isinstance(block, dict) else getattr(block, "file", None)
                if f:
                    complex_files.add(str(f))
                    complex_files.add(Path(str(f)).name)

        for entry in churn_entries:
            if isinstance(entry, dict):
                age_days = int(entry.get("age_days", 0) or 0)
                commit_count = int(entry.get("commit_count", 0) or 0)
                entry_file = str(entry.get("file", ""))
            else:
                age_days = int(getattr(entry, "age_days", 0) or 0)
                commit_count = int(getattr(entry, "commit_count", 0) or 0)
                entry_file = str(getattr(entry, "file", ""))

            if age_days < 30:
                continue  # New active feature — exempt from hotspot penalty

            churn_ratio = commit_count / total_commits
            is_complex = entry_file in complex_files or Path(entry_file).name in complex_files

            if is_complex and churn_ratio > 0.05:
                hotspot_penalty += churn_ratio * 40.0

        todo_penalty = min(10.0, len(todo_markers) * 0.2)

        score = max(0.0, min(100.0, round(100.0 - hotspot_penalty - todo_penalty, 2)))
        return score

    def _score_docs(self, d: Any) -> float:
        if not d:
            return 100.0
        if isinstance(d, dict):
            pct = d.get("docstring_coverage_pct", 0.0)
            setup = 25.0 if d.get("has_readme_setup_section") else 0.0
            usage = 25.0 if d.get("has_readme_usage_section") else 0.0
        else:
            pct = getattr(d, "docstring_coverage_pct", 0.0)
            setup = 25.0 if getattr(d, "has_readme_setup_section", False) else 0.0
            usage = 25.0 if getattr(d, "has_readme_usage_section", False) else 0.0

        doc_pct = float(pct or 0.0)
        return round((doc_pct * 0.5) + setup + usage, 2)

    def _score_resilience(self, res_data: Any) -> float:
        """Calculates resilience score normalized by file count."""
        if not res_data:
            return 100.0

        if isinstance(res_data, list):
            cnt = len(res_data)
            return max(0.0, 100.0 - (cnt * 25.0))

        if isinstance(res_data, dict):
            raw_defects = res_data.get("defects", res_data.get("findings", []))
            file_count = int(res_data.get("file_count", 0) or 0)
        else:
            raw_defects = getattr(res_data, "defects", getattr(res_data, "findings", []))
            file_count = int(getattr(res_data, "file_count", 0) or 0)

        defects_list = list(raw_defects) if isinstance(raw_defects, (list, tuple)) else []

        if file_count <= 0:
            file_count = max(1, len(defects_list))

        density = len(defects_list) / file_count
        score = max(0.0, 100.0 - (density / 0.4 * 100.0))
        return max(0.0, min(100.0, round(score, 2)))

    def _extract_sec_derived(self, data: dict[str, Any], scores: dict[str, float]) -> None:
        """Derives security group scores from raw security, leak, and dependency outputs."""
        if "security" in data and "security_semgrep" not in scores:
            scores["security_semgrep"] = self._score_security(data.get("security", []))

        if "leaks" in data and "secret_leak_gitleaks" not in scores:
            leaks = data.get("leaks", [])
            scores["secret_leak_gitleaks"] = max(0.0, 100.0 - (len(leaks) * 50.0))

        if "dependencies" in data and "dependency_osv" not in scores:
            scores["dependency_osv"] = self._score_dependencies(data.get("dependencies", []))

    def _extract_resilience_metrics(self, data: dict[str, Any], scores: dict[str, float]) -> None:
        """Derives documentation and resilience scores."""
        if "docs" in data and "documentation" not in scores:
            docs_val = data.get("docs")
            if isinstance(docs_val, dict):
                if not docs_val.get("measured", True):
                    pass  # unmeasured, weight redistributed
                else:
                    scores["documentation"] = self._score_docs(docs_val)
            elif docs_val is not None:
                if not getattr(docs_val, "measured", True):
                    pass
                else:
                    scores["documentation"] = self._score_docs(docs_val)

        if "resilience" in data and "resilience_ast" not in scores:
            res_val = data.get("resilience")
            if isinstance(res_val, dict):
                if not res_val.get("measured", True):
                    pass  # unmeasured, weight will be redistributed
                else:
                    scores["resilience_ast"] = self._score_resilience(res_val)
            elif isinstance(res_val, list):
                scores["resilience_ast"] = self._score_resilience(res_val)
            elif res_val is not None:
                if not getattr(res_val, "measured", True):
                    pass
                else:
                    scores["resilience_ast"] = self._score_resilience(res_val)

    def _extract_health_derived(self, data: dict[str, Any], scores: dict[str, float]) -> None:
        """Derives code health, test coverage, and complexity scores."""
        if "coverage" in data and "test_coverage" not in scores:
            cov = data.get("coverage")
            if cov is not None:
                scores["test_coverage"] = max(0.0, min(100.0, round((float(cov) / 80.0) * 100.0, 1)))

        if "complexity" in data and "complexity_radon" not in scores:
            comp = data.get("complexity", {})
            if isinstance(comp, dict):
                if not comp.get("measured", True):
                    pass  # Unmeasured, weight will be redistributed
                else:
                    scores["complexity_radon"] = self._score_complexity(comp)

        if "duplication" in data and "duplication_jscpd" not in scores:
            dup = data.get("duplication", {})
            if isinstance(dup, dict):
                if not dup.get("measured", True):
                    pass  # Unmeasured, weight will be redistributed
                else:
                    scores["duplication_jscpd"] = self._score_duplication(dup)

        if "tech_debt" in data and "tech_debt_churn" not in scores:
            debt = data.get("tech_debt", {})
            if isinstance(debt, dict):
                if not debt.get("measured", True):
                    pass  # Unmeasured, weight will be redistributed
                else:
                    comp = data.get("complexity", {})
                    scores["tech_debt_churn"] = self._score_tech_debt(debt, comp)

        if "lint" in data and "lint_style_ruff" not in scores:
            lint = data.get("lint", {})
            if isinstance(lint, dict):
                if not lint.get("measured", True):
                    pass  # Unmeasured, weight will be redistributed
                elif "score" in lint:
                    scores["lint_style_ruff"] = float(lint["score"])
                else:
                    err_count = lint.get("error_count", 0)
                    scores["lint_style_ruff"] = max(0.0, 100.0 - (err_count * 2.0))

        self._extract_resilience_metrics(data, scores)

    def _extract_member_scores(self, data: dict[str, Any]) -> dict[str, float]:
        """Extracts and standardizes 0-100 scores for all measured members."""
        scores: dict[str, float] = {
            k: float(v)
            for k, v in data.items()
            if k in MEMBER_TO_GROUP and isinstance(v, (int, float))
        }
        for k, v in data.items():
            if k in MEMBER_TO_GROUP and k not in scores:
                if isinstance(v, dict) and "score" in v:
                    if v.get("measured", True) and v.get("applicable", True) and v["score"] is not None:
                        scores[k] = float(v["score"])
                elif hasattr(v, "score") and v.score is not None:
                    if getattr(v, "measured", True) and getattr(v, "applicable", True):
                        scores[k] = float(v.score)

        self._extract_sec_derived(data, scores)
        self._extract_health_derived(data, scores)
        return scores

    def _calc_group_scores(self, member_scores: dict[str, float]) -> dict[str, float]:
        """Calculates intra-group weighted averages for active members."""
        group_scores = {}
        for group in CORE_GROUPS:
            total_weight = 0.0
            weighted_score = 0.0
            for member in group.members:
                if member.key in member_scores:
                    total_weight += member.weight
                    weighted_score += member_scores[member.key] * member.weight

            if total_weight > 0:
                group_scores[group.key] = round(weighted_score / total_weight, 2)
            else:
                group_scores[group.key] = 0.0
        return group_scores

    def _calc_layer1(self, group_scores: dict[str, float]) -> int:
        """Calculates Layer 1 total score normalized across active groups."""
        valid_groups = [g for g in CORE_GROUPS if g.key in group_scores]
        total_group_weight = sum(g.weight for g in valid_groups)
        if total_group_weight == 0:
            return 0
        l1_total = sum(group_scores[g.key] * (g.weight / total_group_weight) for g in valid_groups)
        return max(0, min(100, round(l1_total)))

    def _calc_layer2(self, dynamic_categories: list[dict[str, Any]]) -> int:
        """Converts rubric levels (0-10) to 0-100 scale."""
        if not dynamic_categories:
            return 0

        total_levels = sum(
            cat.get("rubric_verdict", {}).get("level", 5) for cat in dynamic_categories
        )
        avg_level = total_levels / len(dynamic_categories)
        return round(avg_level * 10)

    def _get_grade(self, score: int) -> str:
        """Determines letter grade from numeric score."""
        if score >= 95:
            return "A+"
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"
