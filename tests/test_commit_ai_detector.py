"""Unit tests for the CommitAIDetector service (B4)."""

import pytest

from core.services.commit_ai_detector import CommitAIClassification, CommitAIDetector


class TestCommitAIDetector:
    @pytest.fixture
    def detector(self) -> CommitAIDetector:
        return CommitAIDetector()

    def test_natural_human_commits_classified_as_human(self, detector: CommitAIDetector) -> None:
        samples = [
            "fix: typo in readme",
            "feat: add login endpoint",
            "chore: update dependencies",
            "test: add unit test for password reset",
            "wip: scratch draft for checkout",
            "refactor: simplify token parsing logic",
            "quick fix for 500 error in billing",
        ]
        for msg in samples:
            res = detector.classify_message(msg)
            assert res.is_ai_generated is False
            assert res.ai_score < 45.0

    def test_formal_buzzword_ai_commits_detected(self, detector: CommitAIDetector) -> None:
        samples = [
            "Refactor authentication flow to adhere to SOLID principles and enhance maintainability",
            "This commit introduces comprehensive error handling across services in order to ensure robustness",
            "Implement seamless integration with database repository to improve scalability and maintainability",
        ]
        for msg in samples:
            res = detector.classify_message(msg)
            assert res.is_ai_generated is True
            assert res.ai_confidence >= 0.6
            assert len(res.indicators) >= 2

    def test_bullet_echo_ai_commit_detected(self, detector: CommitAIDetector) -> None:
        bullet_msg = """
feat: update user management

- Added validation check for new user emails
- Updated repository query to use pagination
- Implemented robust error response handling
- Ensured all tests pass seamlessly
"""
        res = detector.classify_message(bullet_msg)
        assert res.is_ai_generated is True
        assert any("bullet" in ind for ind in res.indicators)

    def test_empty_message_handling(self, detector: CommitAIDetector) -> None:
        res = detector.classify_message("   ")
        assert res.is_ai_generated is False
        assert res.ai_score == 0.0

    def test_analyze_commit_batch(self, detector: CommitAIDetector) -> None:
        commits = [
            "fix: typo in user service",
            "feat: add export button",
            "This commit introduces comprehensive error handling to adhere to clean code principles",
            "chore: update lockfile",
        ]
        batch_res = detector.analyze_commit_batch(commits)
        assert batch_res["total_analyzed"] == 4
        assert batch_res["ai_commits_count"] == 1
        assert batch_res["ai_commits_ratio"] == 0.25
        assert len(batch_res["findings"]) == 1

    def test_to_dict_structure(self, detector: CommitAIDetector) -> None:
        res = detector.classify_message("This commit introduces comprehensive logging")
        data = res.to_dict()
        assert "message" in data
        assert "is_ai_generated" in data
        assert "ai_confidence" in data
        assert "ai_score" in data
        assert "indicators" in data
