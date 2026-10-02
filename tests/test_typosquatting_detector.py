"""Unit tests for TyposquattingDetector."""

from __future__ import annotations

from core.services.typosquatting_detector import (
    TyposquattingDetector,
    is_transposition,
    jaro_distance,
    jaro_winkler_similarity,
    normalize_homoglyphs,
)


class TestTyposquattingDetector:
    """Tests for typosquatting detection algorithms."""

    def setup_method(self):
        self.detector = TyposquattingDetector()
        self.detector.set_top_packages({
            "requests",
            "urllib3",
            "pydantic",
            "fastapi",
            "colorama",
            "python-dateutil",
            "cryptography",
            "numpy",
        })

    def test_jaro_and_jaro_winkler(self):
        """Test Jaro and Jaro-Winkler metric basics."""
        assert jaro_distance("", "") == 0.0
        assert jaro_distance("requests", "requests") == 1.0
        assert jaro_winkler_similarity("requests", "requests") == 1.0

        # Prefix similarity boost
        jw = jaro_winkler_similarity("requestss", "requests")
        assert jw > 0.95

    def test_transposition_helper(self):
        """Test detection of adjacent character transposition."""
        assert is_transposition("reqeusts", "requests") is True
        assert is_transposition("fastpai", "fastapi") is True
        assert is_transposition("requests", "requests") is False
        assert is_transposition("rquestes", "requests") is False

    def test_homoglyph_normalization(self):
        """Test homoglyph substitution normalization."""
        assert normalize_homoglyphs("urllib4") == "urlliba"
        assert normalize_homoglyphs("c0l0rma") == "colorma"

    def test_detect_transposition(self):
        """Test detection of swapped adjacent characters in popular library."""
        match = self.detector.detect("reqeusts")
        assert match is not None
        assert match.target_package == "requests"
        assert match.technique == "transposition"
        assert match.risk_level == "HIGH"

    def test_detect_separator_trick(self):
        """Test detection of hyphen vs underscore trick."""
        match = self.detector.detect("python_dateutil")
        assert match is not None
        assert match.target_package == "python-dateutil"
        assert match.technique == "separator"
        assert match.risk_level == "HIGH"

    def test_detect_omission_or_insertion(self):
        """Test single-character omission or insertion."""
        # Omission: reqests (missing 'u')
        match_omission = self.detector.detect("reqests")
        assert match_omission is not None
        assert match_omission.target_package == "requests"

        # Insertion: requestss (extra 's')
        match_insertion = self.detector.detect("requestss")
        assert match_insertion is not None
        assert match_insertion.target_package == "requests"

    def test_detect_homoglyph_trick(self):
        """Test homoglyph replacement (e.g. 0 for o)."""
        match = self.detector.detect("c0l0rama")
        assert match is not None
        assert match.target_package == "colorama"
        assert match.technique == "homoglyph"

    def test_legitimate_exact_package_not_flagged(self):
        """Test that legitimate top packages are not flagged as typosquatting."""
        assert self.detector.detect("requests") is None
        assert self.detector.detect("FastAPI") is None
        assert self.detector.detect("numpy") is None

    def test_unrelated_package_not_flagged(self):
        """Test that completely unrelated names are not flagged."""
        assert self.detector.detect("my-custom-internal-crm") is None
        assert self.detector.detect("django-auth-ldap") is None
