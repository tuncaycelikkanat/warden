"""Unit tests for the StyleDriftDetector service (B2)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.style_drift_detector import (
    StyleDriftDetector,
    StyleVector,
)


class TestStyleDriftDetector:
    @pytest.fixture
    def detector(self) -> StyleDriftDetector:
        return StyleDriftDetector(max_commits=50)

    def test_compute_style_vector_idiomatic_code(self, detector: StyleDriftDetector) -> None:
        code = '''
"""Module docstring."""

class UserService:
    """Service to handle user entities."""

    def __init__(self, db_client: object) -> None:
        self.db_client = db_client

    def fetch_user_by_id(self, user_id: int) -> dict[str, str]:
        """Fetches user details by user ID."""
        try:
            return {"id": str(user_id)}
        except KeyError:
            return {}
'''
        vec = detector.compute_style_vector_from_ast(code)
        assert vec.docstring_ratio == 1.0
        assert vec.type_annotation_ratio > 0.7
        assert vec.naming_snake_ratio >= 0.8
        assert vec.exception_specificity == 1.0

    def test_compute_style_vector_unstructured_code(self, detector: StyleDriftDetector) -> None:
        code = '''
# Import necessary libraries
import sys

# Step 1: define function
def doWork(x, y, z):
    # Step 2: do calculation
    try:
        res = x + y + z
        return res
    except Exception:
        pass
'''
        vec = detector.compute_style_vector_from_ast(code)
        assert vec.docstring_ratio == 0.0
        assert vec.type_annotation_ratio == 0.0
        assert vec.comment_density > 0.3
        assert vec.exception_specificity == 0.0

    def test_calculate_vector_distance_identical_is_zero(self, detector: StyleDriftDetector) -> None:
        vec_a = StyleVector(
            comment_density=0.1,
            docstring_ratio=0.8,
            type_annotation_ratio=0.9,
            naming_snake_ratio=1.0,
            avg_identifier_length=10.0,
            exception_specificity=1.0,
            avg_nesting_depth=1.5,
        )
        vec_b = StyleVector(
            comment_density=0.1,
            docstring_ratio=0.8,
            type_annotation_ratio=0.9,
            naming_snake_ratio=1.0,
            avg_identifier_length=10.0,
            exception_specificity=1.0,
            avg_nesting_depth=1.5,
        )
        dist = detector.calculate_vector_distance(vec_a, vec_b)
        assert round(dist, 2) == 0.0

    def test_calculate_vector_distance_divergent_is_high(self, detector: StyleDriftDetector) -> None:
        vec_clean = StyleVector(
            comment_density=0.05,
            docstring_ratio=1.0,
            type_annotation_ratio=1.0,
            naming_snake_ratio=1.0,
            avg_identifier_length=12.0,
            exception_specificity=1.0,
            avg_nesting_depth=1.2,
        )
        vec_drifted = StyleVector(
            comment_density=0.9,
            docstring_ratio=0.0,
            type_annotation_ratio=0.0,
            naming_snake_ratio=0.1,
            avg_identifier_length=4.0,
            exception_specificity=0.0,
            avg_nesting_depth=4.5,
        )
        dist = detector.calculate_vector_distance(vec_clean, vec_drifted)
        assert dist > 20.0

    def test_analyze_repository_insufficient_commits(
        self, detector: StyleDriftDetector, tmp_path: Path
    ) -> None:
        with patch.object(detector, "_get_commit_history", return_value=[]):
            result = detector.analyze_repository_history(tmp_path)
            assert result.analyzed_commits == 0
            assert result.drift_detected is False
            assert result.overall_drift_score == 0.0
            assert "Insufficient commit history" in result.summary

    def test_analyze_repository_detects_drift_event(
        self, detector: StyleDriftDetector, tmp_path: Path
    ) -> None:
        mock_commits = [
            {"hash": "c5", "author": "Alice", "date": "2026-10-05", "message": "feat: vibe code drop"},
            {"hash": "c4", "author": "Alice", "date": "2026-10-04", "message": "feat: standard module"},
            {"hash": "c3", "author": "Bob", "date": "2026-10-03", "message": "refactor: domain entities"},
            {"hash": "c2", "author": "Alice", "date": "2026-10-02", "message": "feat: user service"},
            {"hash": "c1", "author": "Alice", "date": "2026-10-01", "message": "init: initial project layout"},
        ]

        def mock_diff(_path: Path, commit_hash: str) -> str:
            if commit_hash == "c5":
                # Radical shift: lots of comments, zero types, broad except
                return """
+ # Step 1: run vibe script
+ # Step 2: do calculation
+ def runScript(a, b, c):
+     # Step 3: loop
+     try:
+         return a + b + c
+     except Exception:
+         pass
"""
            # Standard commits
            return """
+ def calculate_total(amount: float, tax: float) -> float:
+     \"\"\"Calculates total with tax.\"\"\"
+     try:
+         return amount + tax
+     except ValueError:
+         return 0.0
"""

        with patch.object(detector, "_get_commit_history", return_value=mock_commits):
            with patch.object(detector, "_get_commit_diff", side_effect=mock_diff):
                res = detector.analyze_repository_history(tmp_path)
                assert res.analyzed_commits == 5
                assert res.overall_drift_score > 0.0
                assert len(res.drift_events) >= 1
                assert res.drift_events[0].commit_hash == "c5"
                d = res.to_dict()
                assert "drift_detected" in d
                assert "drift_events" in d
