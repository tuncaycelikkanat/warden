"""Advanced Typosquatting Detection Engine for Python/PyPI packages.

Identifies malicious packages designed to mimic popular open-source libraries
via Jaro-Winkler similarity, Damerau-Levenshtein transpositions, separator tricks
(hyphen vs underscore), homoglyphs, and omission/insertion patterns.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HOMOGLYPH_MAP: dict[str, str] = {
    "0": "o",
    "1": "l",
    "3": "e",
    "4": "a",
    "5": "s",
    "8": "b",
}


@dataclass
class TyposquattingMatch:
    """Represents an identified typosquatting mimicry finding."""

    suspect_package: str
    target_package: str
    similarity_score: float  # 0.0 to 1.0
    technique: str           # "transposition" | "separator" | "homoglyph" | "omission_insertion" | "edit_distance"
    risk_level: str          # "HIGH" | "MEDIUM" | "LOW"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspect_package": self.suspect_package,
            "target_package": self.target_package,
            "similarity_score": round(self.similarity_score, 3),
            "technique": self.technique,
            "risk_level": self.risk_level,
            "reason": self.reason,
        }


def jaro_distance(s1: str, s2: str) -> float:
    """Computes Jaro similarity between two strings."""
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    if s1 == s2:
        return 1.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    t = transpositions / 2.0
    return (matches / len1 + matches / len2 + (matches - t) / matches) / 3.0


def jaro_winkler_similarity(s1: str, s2: str, prefix_scale: float = 0.1) -> float:
    """Computes Jaro-Winkler similarity, prioritizing common prefixes."""
    jaro_sim = jaro_distance(s1, s2)
    prefix_len = 0
    for c1, c2 in zip(s1[:4], s2[:4]):
        if c1 == c2:
            prefix_len += 1
        else:
            break
    return jaro_sim + prefix_len * prefix_scale * (1.0 - jaro_sim)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Computes classic Levenshtein edit distance."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row
    return prev_row[-1]


def is_transposition(s1: str, s2: str) -> bool:
    """Checks if s1 and s2 differ by exactly one swapped adjacent character."""
    if len(s1) != len(s2) or len(s1) < 2:
        return False
    diffs = [i for i in range(len(s1)) if s1[i] != s2[i]]
    if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
        return s1[diffs[0]] == s2[diffs[1]] and s1[diffs[1]] == s2[diffs[0]]
    return False


def normalize_homoglyphs(s: str) -> str:
    """Replaces common numbers/homoglyphs with their letter equivalents."""
    chars = [HOMOGLYPH_MAP.get(c, c) for c in s.lower()]
    return "".join(chars)


class TyposquattingDetector:
    """Detector for typosquatting attacks against PyPI top packages."""

    def __init__(self, top_packages_path: Path | None = None) -> None:
        self._top_packages: set[str] = set()
        self._load_top_packages(top_packages_path)

    def _load_top_packages(self, custom_path: Path | None = None) -> None:
        candidates = [
            custom_path,
            Path(__file__).resolve().parent.parent / "data" / "top_pypi_packages.json",
            Path("core/data/top_pypi_packages.json"),
        ]
        for p in candidates:
            if p and p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        self._top_packages = set(json.load(f))
                        return
                except Exception as err:
                    logger.debug(f"Failed to load top packages from {p}: {err}")
        self._top_packages = set()

    def set_top_packages(self, packages: set[str]) -> None:
        """Manually sets reference top package set for testing."""
        self._top_packages = packages

    def detect(self, candidate_name: str, threshold: float = 0.88) -> TyposquattingMatch | None:
        """Inspects candidate package name against top packages for typosquatting signals."""
        pkg_clean = candidate_name.strip().lower()
        if not pkg_clean or not self._top_packages:
            return None

        # Exact match is legitimate
        for popular in self._top_packages:
            if pkg_clean == popular.lower():
                return None

        best_match: TyposquattingMatch | None = None
        highest_score = 0.0

        for popular in self._top_packages:
            pop_clean = popular.lower()

            # 1. Separator trick: python_dateutil vs python-dateutil
            pop_norm_sep = pop_clean.replace("-", "_").replace(".", "_")
            pkg_norm_sep = pkg_clean.replace("-", "_").replace(".", "_")
            if pop_norm_sep == pkg_norm_sep and pop_clean != pkg_clean:
                return TyposquattingMatch(
                    suspect_package=candidate_name,
                    target_package=popular,
                    similarity_score=0.99,
                    technique="separator",
                    risk_level="HIGH",
                    reason=f"Separator trick: matches '{popular}' with hyphen/underscore variation",
                )

            # 2. Adjacent Transposition: reqeusts vs requests
            if is_transposition(pkg_clean, pop_clean):
                return TyposquattingMatch(
                    suspect_package=candidate_name,
                    target_package=popular,
                    similarity_score=0.98,
                    technique="transposition",
                    risk_level="HIGH",
                    reason=f"Character transposition: swapped adjacent letters mimicking '{popular}'",
                )

            # 3. Homoglyph trick: urllib4 vs urllib3 or c0l0rma vs colorma
            if normalize_homoglyphs(pkg_clean) == normalize_homoglyphs(pop_clean):
                return TyposquattingMatch(
                    suspect_package=candidate_name,
                    target_package=popular,
                    similarity_score=0.95,
                    technique="homoglyph",
                    risk_level="HIGH",
                    reason=f"Homoglyph mimicry: visual character substitution mimicking '{popular}'",
                )

            # 4. Single-character omission or insertion on medium/long names
            dist = levenshtein_distance(pkg_clean, pop_clean)
            if dist == 1 and len(pop_clean) >= 5:
                score = 0.94
                if score > highest_score:
                    highest_score = score
                    best_match = TyposquattingMatch(
                        suspect_package=candidate_name,
                        target_package=popular,
                        similarity_score=score,
                        technique="omission_insertion",
                        risk_level="HIGH",
                        reason=f"One-character typo/insertion mimicking popular package '{popular}'",
                    )
                continue

            # 5. Jaro-Winkler Similarity
            jw_score = jaro_winkler_similarity(pkg_clean, pop_clean)
            if jw_score >= threshold and jw_score > highest_score:
                # Require edit distance <= 2 to prevent coincidental false positives
                if dist <= 2:
                    highest_score = jw_score
                    best_match = TyposquattingMatch(
                        suspect_package=candidate_name,
                        target_package=popular,
                        similarity_score=jw_score,
                        technique="edit_distance",
                        risk_level="HIGH" if jw_score >= 0.92 else "MEDIUM",
                        reason=f"High lexical similarity ({jw_score:.1%}) to popular package '{popular}'",
                    )

        return best_match
