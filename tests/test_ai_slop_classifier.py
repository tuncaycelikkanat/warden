"""Unit tests for the AISlopClassifier service (B1)."""

import pytest

from core.services.ai_slop_classifier import AISlopClassifier


class TestAISlopClassifier:
    @pytest.fixture
    def classifier(self) -> AISlopClassifier:
        return AISlopClassifier(use_sklearn=True)

    @pytest.fixture
    def pure_python_classifier(self) -> AISlopClassifier:
        return AISlopClassifier(use_sklearn=False)

    def test_human_comments_classified_as_human(self, classifier: AISlopClassifier) -> None:
        human_samples = [
            "# TODO: investigate sporadic timeout under high load",
            "# Workaround for upstream issue in openssl 3.0",
            "# Bitmask flag for read/write access",
            "# Cache key expires after 3600 seconds",
            "# Ref: https://tools.ietf.org/html/rfc7231#section-6.5.3",
        ]
        for sample in human_samples:
            res = classifier.classify_text(sample)
            assert res.label == "human"
            assert res.slop_score < 25.0
            assert res.confidence > 0.7

    def test_didactic_ai_comments_detected(self, classifier: AISlopClassifier) -> None:
        ai_samples = [
            "# Import necessary libraries",
            "# Helper function to calculate interest",
            "# Step 1: Initialize database connection",
            "# Step 2: Loop through the items and process each record",
            "# Create an instance of the UserService class",
        ]
        for sample in ai_samples:
            res = classifier.classify_text(sample)
            assert res.label in ("ai_slop", "mixed")
            assert res.slop_score >= 25.0
            assert len(res.matched_markers) > 0

    def test_conversational_and_disclaimer_detected(self, classifier: AISlopClassifier) -> None:
        chat_samples = [
            "# Here is the updated code with error handling",
            "# Feel free to modify this to suit your requirements",
            "# I hope this helps! Let me know if you have questions",
            "# In production, replace this with your actual api_key",
            "# Note: this is a mock implementation for demonstration purposes",
        ]
        for sample in chat_samples:
            res = classifier.classify_text(sample)
            assert res.label == "ai_slop"
            assert res.slop_score >= 50.0

    def test_echo_redundancy_detection(self, classifier: AISlopClassifier) -> None:
        comment = "# get user by id"
        surrounding_code = "def get_user_by_id(user_id: int):"
        res = classifier.classify_text(comment, surrounding_code=surrounding_code)
        assert res.features.get("echo_redundancy", 0.0) >= 0.75
        assert "echo_redundancy" in res.matched_markers
        assert res.label in ("ai_slop", "mixed")

    def test_empty_comment_handling(self, classifier: AISlopClassifier) -> None:
        res = classifier.classify_text("")
        assert res.label == "human"
        assert res.slop_score == 0.0
        assert res.confidence == 1.0

    def test_pure_python_fallback_works_consistently(self, pure_python_classifier: AISlopClassifier) -> None:
        assert pure_python_classifier._sklearn_available is False
        res = pure_python_classifier.classify_text("# Import necessary libraries")
        assert res.label in ("ai_slop", "mixed")
        assert res.slop_score >= 25.0

    def test_analyze_source_content(self, classifier: AISlopClassifier) -> None:
        source_code = '''
# Import necessary libraries
import sys
import os

# Helper function to add numbers
def add(a, b):
    # In production, replace this with your actual validation
    return a + b

# Real human domain logic below
def compute_hash(val):
    return hash(val)
'''
        report = classifier.analyze_source_content(source_code, filename="service.py")
        assert report["filename"] == "service.py"
        assert report["total_comments"] >= 4
        assert report["slop_comments_count"] >= 2
        assert report["slop_ratio"] > 0.3
        assert len(report["findings"]) >= 2

    def test_to_dict_structure(self, classifier: AISlopClassifier) -> None:
        res = classifier.classify_text("# Step 1: Initialize modules")
        data = res.to_dict()
        assert "label" in data
        assert "confidence" in data
        assert "slop_score" in data
        assert "features" in data
        assert "matched_markers" in data
        assert "explanation" in data
