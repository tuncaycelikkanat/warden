"""Coverage-targeted tests for StyleDriftDetector — git integration paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.style_drift_detector import (
    StyleDriftDetector,
    StyleVector,
)


class TestStyleDriftDetectorCoverage:
    """Covers previously uncovered StyleDriftDetector branches."""

    @pytest.fixture
    def detector(self) -> StyleDriftDetector:
        return StyleDriftDetector(max_commits=10)

    # ── compute_style_vector_from_ast edge cases ─────────────────────────────

    def test_empty_code_returns_default_vector(self, detector: StyleDriftDetector) -> None:
        vec = detector.compute_style_vector_from_ast("")
        assert vec.comment_density == 0.0
        assert vec.docstring_ratio == 0.0

    def test_syntax_error_snippet_wrapped_successfully(self, detector: StyleDriftDetector) -> None:
        snippet = "x = 1\nreturn x\n"
        vec = detector.compute_style_vector_from_ast(snippet)
        assert isinstance(vec, StyleVector)

    def test_double_syntax_error_returns_partial_vector(self, detector: StyleDriftDetector) -> None:
        bad_code = "def f(:\n    !!not valid!!\n"
        vec = detector.compute_style_vector_from_ast(bad_code)
        assert isinstance(vec, StyleVector)

    def test_functions_all_dunders_fallback(self, detector: StyleDriftDetector) -> None:
        code = "class Foo:\n    def __init__(self): pass\n    def __str__(self): pass\n"
        vec = detector.compute_style_vector_from_ast(code)
        assert isinstance(vec, StyleVector)

    # ── calculate_vector_distance zero-norm edge case ────────────────────────

    def test_distance_zero_norm_returns_zero(self, detector: StyleDriftDetector) -> None:
        zero_vec = StyleVector(
            comment_density=0.0,
            docstring_ratio=0.0,
            type_annotation_ratio=0.0,
            naming_snake_ratio=0.0,
            avg_identifier_length=0.0,
            exception_specificity=0.0,
            avg_nesting_depth=0.0,
        )
        dist = detector.calculate_vector_distance(zero_vec, zero_vec)
        assert dist == 0.0

    # ── _get_commit_history paths ────────────────────────────────────────────

    def test_get_commit_history_no_git_returns_empty(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            result = detector._get_commit_history(tmp_path)
        assert result == []

    def test_get_commit_history_nonzero_returncode(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("shutil.which", return_value="/usr/bin/git"):
            with patch("subprocess.run", return_value=mock_result):
                result = detector._get_commit_history(tmp_path)
        assert result == []

    def test_get_commit_history_subprocess_exception(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        with patch("shutil.which", return_value="/usr/bin/git"):
            with patch("subprocess.run", side_effect=OSError("no git")):
                result = detector._get_commit_history(tmp_path)
        assert result == []

    # ── _get_commit_diff paths ───────────────────────────────────────────────

    def test_get_commit_diff_no_git_returns_empty(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            result = detector._get_commit_diff(tmp_path, "abc123")
        assert result == ""

    def test_get_commit_diff_subprocess_exception(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        with patch("shutil.which", return_value="/usr/bin/git"):
            with patch("subprocess.run", side_effect=OSError("broken")):
                result = detector._get_commit_diff(tmp_path, "abc123")
        assert result == ""

    def test_get_commit_diff_successful(self, detector: StyleDriftDetector, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "+def new_func(): pass\n"
        with patch("shutil.which", return_value="/usr/bin/git"):
            with patch("subprocess.run", return_value=mock_result):
                result = detector._get_commit_diff(tmp_path, "abc123")
        assert "+def new_func" in result

    # ── analyze_repository_history: fewer than 2 commit vectors ──────────────

    def test_analyze_repository_with_single_commit_vector(
        self, detector: StyleDriftDetector, tmp_path: Path
    ) -> None:
        mock_commits = [
            {"hash": "c2", "author": "Alice", "date": "2026-10-02", "message": "feat: add feature"},
            {"hash": "c1", "author": "Alice", "date": "2026-10-01", "message": "init: project"},
        ]

        def mock_diff(_path: Path, commit_hash: str) -> str:
            if commit_hash == "c2":
                return "+x = 1\n"
            return ""

        with patch.object(detector, "_get_commit_history", return_value=mock_commits):
            with patch.object(detector, "_get_commit_diff", side_effect=mock_diff):
                result = detector.analyze_repository_history(tmp_path)
        assert result.drift_detected is False
        assert "fewer than 2" in result.summary

    # ── HIGH / CRITICAL / MODERATE risk levels ───────────────────────────────

    def test_analyze_repository_high_risk_level(
        self, detector: StyleDriftDetector, tmp_path: Path
    ) -> None:
        mock_commits = [
            {"hash": f"c{i}", "author": "Bob", "date": f"2026-10-0{i+1}", "message": f"commit {i}"}
            for i in range(6)
        ]
        diff_code = "+def f():\n+    return 1\n+    # comment\n+    # more\n+    pass\n"

        with patch.object(detector, "_get_commit_history", return_value=mock_commits):
            with patch.object(detector, "_get_commit_diff", return_value=diff_code):
                with patch.object(detector, "calculate_vector_distance", return_value=75.0):
                    result = detector.analyze_repository_history(tmp_path)
                    assert result.risk_level in ("HIGH", "CRITICAL")
                    assert result.drift_detected is True

    # ── StyleVector.to_dict round-trip ───────────────────────────────────────

    def test_style_vector_to_dict_roundtrip(self, detector: StyleDriftDetector) -> None:
        vec = StyleVector(
            comment_density=0.2,
            docstring_ratio=0.8,
            type_annotation_ratio=0.9,
            naming_snake_ratio=1.0,
            avg_identifier_length=11.0,
            exception_specificity=1.0,
            avg_nesting_depth=1.5,
        )
        d = vec.to_dict()
        expected_keys = {
            "comment_density", "docstring_ratio", "type_annotation_ratio",
            "naming_snake_ratio", "avg_identifier_length", "exception_specificity",
            "avg_nesting_depth",
        }
        assert expected_keys == set(d.keys())
