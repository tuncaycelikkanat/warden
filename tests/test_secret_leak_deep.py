"""Comprehensive tests for SecretLeakScannerService edge cases and false-positive filter logic."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.services.secret_leak import (
    SecretLeakScannerService,
    _contains_word,
    _is_in_test_context,
    HIGH_CONFIDENCE_MOCK_TOKENS,
)


def test_contains_word_edge_cases():
    assert _contains_word("", {"token"}) is False
    assert _contains_word("dummy_secret_here", HIGH_CONFIDENCE_MOCK_TOKENS) is True
    assert _contains_word("some_deadbeef_value", {"deadbeef"}) is True
    assert _contains_word("test_api_key", {"test"}) is True
    assert _contains_word("api_TEST_value", {"test"}) is True
    assert _contains_word("totally_clean_production_val", {"mock"}) is False


def test_is_in_test_context():
    assert _is_in_test_context("tests/conftest.py") is True
    assert _is_in_test_context("src/test_core.py") is True
    assert _is_in_test_context("src/core/main.py") is False


def test_false_positive_heuristics_contexts():
    analyzer = SecretLeakScannerService()

    # Outside of test context, without universal placeholders, it is a real leak (False for is_false_positive)
    prod_finding = {
        "File": "src/api/auth.py",
        "Secret": "production_secret_key_987654321",
        "Match": "api_key = production_secret_key_987654321",
    }
    assert analyzer.is_false_positive(prod_finding) is False

    # Inside test context with colon in match string
    colon_finding = {
        "File": "tests/test_auth.py",
        "Secret": "deadbeef12345678",
        "Match": "mock_token: deadbeef12345678",
    }
    assert analyzer.is_false_positive(colon_finding) is True

    # Inside test context with neither = nor : in match string
    plain_finding = {
        "File": "tests/test_auth.py",
        "Secret": "dummy_secret_value",
        "Match": "dummy_secret_value",
    }
    assert analyzer.is_false_positive(plain_finding) is True

    # High-confidence token in variable context
    var_finding = {
        "File": "tests/test_api.py",
        "Secret": "random_characters_xyz_12345",
        "Match": "mock_credential = random_characters_xyz_12345",
    }
    assert analyzer.is_false_positive(var_finding) is True


@pytest.mark.asyncio
async def test_secret_leak_analyzer_run_and_log(tmp_path: Path):
    analyzer = SecretLeakScannerService()

    # Test empty stdout from gitleaks
    mock_res = MagicMock(returncode=0, stdout="   \n", stderr="")
    with patch("subprocess.run", return_value=mock_res):
        res = await analyzer.scan_history(tmp_path)
        assert len(res.leaked_secrets) == 0
        assert len(res.ignored_test_secrets) == 0

    # Test ignored test secrets logging
    mock_findings = [
        {
            "Description": "Generic API Key",
            "File": "tests/fixture.py",
            "Secret": "fake_test_key_mock",
            "Match": "test_token = fake_test_key_mock",
            "StartLine": 5,
            "EndLine": 5,
            "Commit": "abc1234",
            "Author": "dev",
            "Email": "dev@example.com",
            "Date": "2026-01-01",
        }
    ]
    import json
    mock_res2 = MagicMock(returncode=1, stdout=json.dumps(mock_findings), stderr="")
    with patch("subprocess.run", return_value=mock_res2):
        res2 = await analyzer.scan_history(tmp_path)
        assert len(res2.leaked_secrets) == 0
        assert len(res2.ignored_test_secrets) == 1
