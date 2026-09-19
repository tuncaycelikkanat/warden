import logging
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ScorecardResult:
    total_score: int
    layer1_score: int
    layer2_score: int
    grade: str  # A+, A, B, C, D, F
    breakdown: Dict[str, Any]

class ScorecardAggregatorService:
    def __init__(self):
        self.layer1_weight = 0.60
        self.layer2_weight = 0.40

    def calculate(self, layer1_data: Dict[str, Any], layer2_data: List[Dict[str, Any]]) -> ScorecardResult:
        """
        Calculates the final scorecard.
        Layer 1 max score = 100.
        Layer 2 max score = 100.
        Total = Layer 1 * 60% + Layer 2 * 40%.
        """
        layer1_score = self._calc_layer1(layer1_data)
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
                "layer2_raw": layer2_data
            }
        )

    def _calc_layer1(self, data: Dict[str, Any]) -> int:
        """
        Deduction based formula starting from 100.
        """
        score = 100
        
        # Deductions
        # Security (-5 per high, -2 per medium)
        sec_findings = data.get("security", [])
        for f in sec_findings:
            if f.get("severity") == "ERROR":
                score -= 5
            elif f.get("severity") == "WARNING":
                score -= 2

        # Leaks (-20 per leak)
        leaks = data.get("leaks", [])
        score -= len(leaks) * 20
        
        # Dependencies (-5 per high vuln, -20 if failed integrity)
        deps = data.get("dependencies", [])
        for d in deps:
            if d.get("status") == "failed_check":
                score -= 20
            score -= len(d.get("known_vulnerabilities", [])) * 5
            
        # Coverage (if < 80%, deduct up to 20 points)
        cov = data.get("coverage", 0.0)
        if cov < 80:
            score -= round((80 - cov) * 0.5)
            
        return max(0, score)

    def _calc_layer2(self, dynamic_categories: List[Dict[str, Any]]) -> int:
        """
        Average of evaluated rubric levels (0-10) converted to 100 scale.
        """
        if not dynamic_categories:
            return 100  # Default if no dynamic categories apply
            
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
