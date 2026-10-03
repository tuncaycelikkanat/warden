"""Unit tests for FakeTestDetector (D2)."""

import ast
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.fake_test_detector import FakeTestDetail, FakeTestDetector


class TestFakeTestDetector:
    @pytest.fixture
    def detector(self) -> FakeTestDetector:
        return FakeTestDetector()

    def test_tautology_self_equality_detected(self, detector: FakeTestDetector) -> None:
        code = """
def test_tautology():
    x = 10
    assert x == x
"""
        tree = ast.parse(code)
        func = tree.body[0]
        findings = detector.analyze_function(func, "test_file.py", code.splitlines())
        assert len(findings) == 1
        assert findings[0].fake_type == "TAUTOLOGY"
        assert "assert x == x" in findings[0].explanation

    def test_tautology_non_negative_length_detected(self, detector: FakeTestDetector) -> None:
        code = """
def test_length():
    items = [1, 2, 3]
    assert len(items) >= 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        findings = detector.analyze_function(func, "test_file.py", code.splitlines())
        assert len(findings) == 1
        assert findings[0].fake_type == "TAUTOLOGY"
        assert "len(...) >= 0" in findings[0].explanation

    def test_uninvoked_mock_assertion_detected(self, detector: FakeTestDetector) -> None:
        code = """
def test_mock_call():
    service = Mock()
    service.do_something()
    service.assert_called_once
"""
        tree = ast.parse(code)
        func = tree.body[0]
        findings = detector.analyze_function(func, "test_file.py", code.splitlines())
        assert len(findings) == 1
        assert findings[0].fake_type == "UNINVOKED_MOCK_ASSERTION"
        assert "assert_called_once" in findings[0].explanation

    def test_empty_test_flagged_as_no_assertion(self, detector: FakeTestDetector) -> None:
        code = """
def test_nothing():
    pass
"""
        tree = ast.parse(code)
        func = tree.body[0]
        findings = detector.analyze_function(func, "test_file.py", code.splitlines())
        assert len(findings) == 1
        assert findings[0].fake_type == "NO_ASSERTION"

    def test_legitimate_assertions_pass_cleanly(self, detector: FakeTestDetector) -> None:
        code = """
def test_legit():
    mock_service = Mock()
    mock_service.do_work()
    mock_service.assert_called_once()
    assert 2 + 2 == 4
"""
        tree = ast.parse(code)
        func = tree.body[0]
        findings = detector.analyze_function(func, "test_file.py", code.splitlines())
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_verify_with_llm(self) -> None:
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value={"is_fake": True, "confidence": 0.95, "reason": "Placebo test"})
        detector = FakeTestDetector(llm_provider=mock_llm)

        res = await detector.verify_with_llm("def test_dummy(): time.sleep(1)")
        assert res["is_fake"] is True
        assert res["confidence"] == 0.95

    def test_to_dict_structure(self, detector: FakeTestDetector) -> None:
        detail = FakeTestDetail(
            file_path="tests/test_x.py",
            function_name="test_dummy",
            line_number=10,
            fake_type="TAUTOLOGY",
            snippet="assert a == a",
            explanation="Self equality",
            severity="HIGH",
        )
        d = detail.to_dict()
        assert d["file_path"] == "tests/test_x.py"
        assert d["fake_type"] == "TAUTOLOGY"
        assert d["severity"] == "HIGH"
