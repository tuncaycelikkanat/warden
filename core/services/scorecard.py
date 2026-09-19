import logging
from dataclasses import dataclass
from typing import Any

from core.services.core_group_catalog import CORE_GROUPS, MEMBER_TO_GROUP

logger = logging.getLogger(__name__)

@dataclass
class ScorecardResult:
    total_score: int
    layer1_score: int
    layer2_score: int
    grade: str  # A+, A, B, C, D, F
    breakdown: dict[str, Any]
    group_scores: dict[str, float] = None

class ScorecardAggregatorService:
    def __init__(self):
        self.layer1_weight = 0.60
        self.layer2_weight = 0.40

    def calculate(self, layer1_data: dict[str, Any], layer2_data: list[dict[str, Any]]) -> ScorecardResult:
        """
        Calculates the final scorecard.
        Layer 1 max score = 100.
        Layer 2 max score = 100.
        Total = Layer 1 * 60% + Layer 2 * 40%.
        """
        member_scores = self._extract_member_scores(layer1_data)
        group_scores = self._calc_group_scores(member_scores)
        
        layer1_score = self._calc_layer1(group_scores)
        
        if not layer2_data:
            layer2_score = layer1_score
            total = layer1_score
        else:
            layer2_score = self._calc_layer2(layer2_data)
            total = round((layer1_score * self.layer1_weight) + (layer2_score * self.layer2_weight))
        
        # Ensure bounds
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
            group_scores=group_scores
        )

    def _extract_member_scores(self, data: dict[str, Any]) -> dict[str, float]:
        scores = {}
        
        # In case member scores are provided directly
        for k, v in data.items():
            if k in MEMBER_TO_GROUP and isinstance(v, (int, float)):
                scores[k] = float(v)
                
        if "security" in data and "security_semgrep" not in scores:
            sec_score = 100
            for f in data.get("security", []):
                sev = f.get("severity", f.get("extra", {}).get("severity", "INFO"))
                if sev == "ERROR":
                    sec_score -= 40
                elif sev == "WARNING":
                    sec_score -= 10
            scores["security_semgrep"] = max(0, sec_score)
            
        if "leaks" in data and "secret_leak_gitleaks" not in scores:
            leaks = data.get("leaks", [])
            scores["secret_leak_gitleaks"] = max(0, 100 - (len(leaks) * 50))
            
        if "dependencies" in data and "dependency_osv" not in scores:
            dep_score = 100
            for d in data.get("dependencies", []):
                if d.get("status") == "failed_check":
                    dep_score -= 20
                dep_score -= len(d.get("known_vulnerabilities", [])) * 5
            scores["dependency_osv"] = max(0, dep_score)
            
        if "coverage" in data and "test_coverage" not in scores:
            cov = data.get("coverage")
            if cov is not None:
                cov_val = float(cov)
                scores["test_coverage"] = max(0.0, min(100.0, round((cov_val / 80.0) * 100.0, 1)))
            # If cov is None -> unmeasured, omitted so weight redistributes to remaining members
            
        if "complexity" in data and "complexity_radon" not in scores:
            comp = data.get("complexity", {})
            if isinstance(comp, dict) and comp:
                high_files = len(comp.get("high_complexity_files", []))
                avg = comp.get("avg_complexity", 0.0)
                comp_score = 100.0 - (high_files * 25.0) - (max(0.0, avg - 3.0) * 10.0)
                scores["complexity_radon"] = max(0.0, min(100.0, round(comp_score, 2)))
            else:
                scores["complexity_radon"] = 100.0
            
        if "lint" in data and "lint_style_ruff" not in scores:
            lint = data.get("lint", {})
            if isinstance(lint, dict) and "error_count" in lint:
                err_count = lint.get("error_count", 0)
                scores["lint_style_ruff"] = max(0.0, 100.0 - (err_count * 2.0))
            else:
                scores["lint_style_ruff"] = 100.0
            
        if "docs" in data and "documentation" not in scores:
            d = data.get("docs", {})
            if isinstance(d, dict) and d:
                pct = d.get("docstring_coverage_pct", 0.0)
                setup = 25.0 if d.get("has_readme_setup_section") else 0.0
                usage = 25.0 if d.get("has_readme_usage_section") else 0.0
                scores["documentation"] = round((pct * 0.5) + setup + usage, 2)
            else:
                scores["documentation"] = 100.0
            
        if "resilience" in data and "resilience_ast" not in scores:
            res_list = data.get("resilience", [])
            if isinstance(res_list, list):
                scores["resilience_ast"] = max(0.0, 100.0 - (len(res_list) * 25.0))
            else:
                scores["resilience_ast"] = 100.0

        return scores

    def _calc_group_scores(self, member_scores: dict[str, float]) -> dict[str, float]:
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
        """
        Calculates Layer 1 total score using group scores and their weights.
        """
        valid_groups = [g for g in CORE_GROUPS if g.key in group_scores]
        total_group_weight = sum(g.weight for g in valid_groups)
        if total_group_weight == 0:
            return 0
        l1_total = sum(group_scores[g.key] * (g.weight / total_group_weight) for g in valid_groups)
        return max(0, min(100, round(l1_total)))

    def _calc_layer2(self, dynamic_categories: list[dict[str, Any]]) -> int:
        """
        Average of evaluated rubric levels (0-10) converted to 100 scale.
        """
        if not dynamic_categories:
            return 0  # Default if no dynamic categories apply
            
        total_levels = 0
        for cat in dynamic_categories:
            # rubric level is 0 to 10
            level = cat.get("rubric_verdict", {}).get("level", 5)
            total_levels += level
            
        avg_level = total_levels / len(dynamic_categories)
        return round(avg_level * 10)

    def _get_grade(self, score: int) -> str:
        if score >= 95: return "A+"
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
