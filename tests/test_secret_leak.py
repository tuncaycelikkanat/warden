import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.secret_leak import LeakedSecret, SecretLeakResult, SecretLeakScannerService


def test_leaked_secret_from_gitleaks():
    raw = {
        "RuleID": "generic-api-key",
        "File": "config/settings.py",
        "StartLine": 42,
        "Commit": "abc1234",
        "Author": "dev@example.com",
        "Date": "2026-01-01",
        "Message": "Add config",
        "Secret": "sk-1234567890",
    }
    secret = LeakedSecret.from_gitleaks(raw)
    assert secret.rule_id == "generic-api-key"
    assert secret.file == "config/settings.py"
    assert secret.line == 42
    assert secret.commit == "abc1234"
    assert secret.secret == "sk-1234567890"


def test_secret_leak_result():
    res = SecretLeakResult(leaked_secrets=[])
    assert res.leaked_secrets == []


@pytest.mark.asyncio
async def test_scan_history_no_leaks(tmp_path: Path):
    service = SecretLeakScannerService()
    mock_run = MagicMock()
    mock_run.stdout = "[]"

    with patch("subprocess.run", return_value=mock_run):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 0


@pytest.mark.asyncio
async def test_scan_history_with_leaks(tmp_path: Path):
    service = SecretLeakScannerService()
    mock_findings = [
        {
            "RuleID": "aws-access-key",
            "File": "deploy.sh",
            "StartLine": 10,
            "Commit": "deadbeef",
            "Author": "alice",
            "Date": "2026-02-01",
            "Message": "deploy script",
            "Secret": "AKIAIOSFODNN7EXAMPLE",
        }
    ]
    mock_run = MagicMock()
    mock_run.stdout = json.dumps(mock_findings)

    # Test with .gitleaksignore present
    (tmp_path / ".gitleaksignore").write_text("# ignore rules")

    with patch("subprocess.run", return_value=mock_run):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 1
        assert result.leaked_secrets[0].rule_id == "aws-access-key"


@pytest.mark.asyncio
async def test_scan_history_exception(tmp_path: Path):
    service = SecretLeakScannerService()

    with patch("subprocess.run", side_effect=FileNotFoundError("gitleaks not found")):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 0


def test_is_false_positive_test_fixtures():
    # Google API Key mock in a test file
    finding_test_key = {
        "RuleID": "google-api-key",
        "File": "tests/test_api_endpoints_comprehensive.py",
        "StartLine": 12,
        "Secret": "AIzaSyTestKey123456789",
        "Match": 'API_KEY = "AIzaSyTestKey123456789"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_test_key) is True

    # Generic token in fixture
    finding_mock_fixture = {
        "RuleID": "generic-api-key",
        "File": "fixtures/sample_payload.json",
        "StartLine": 5,
        "Secret": "mock_token_abcdef123456",
        "Match": '"token": "mock_token_abcdef123456"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_mock_fixture) is True

    # Universal placeholder in non-test file
    finding_placeholder = {
        "RuleID": "generic-api-key",
        "File": "config/settings.py",
        "StartLine": 20,
        "Secret": "your_api_key_here",
        "Match": "API_KEY = your_api_key_here",
    }
    assert SecretLeakScannerService.is_false_positive(finding_placeholder) is True

    # Stripe test key in non-test file
    finding_stripe_test = {
        "RuleID": "stripe-api-key",
        "File": "core/billing.py",
        "StartLine": 14,
        "Secret": "sk_test_51MzXYZ123456789",
        "Match": "sk_test_51MzXYZ123456789",
    }
    assert SecretLeakScannerService.is_false_positive(finding_stripe_test) is True

    # Real leak in production code must NOT be considered false positive
    finding_real_leak = {
        "RuleID": "aws-access-key",
        "File": "core/infra/deploy.py",
        "StartLine": 88,
        "Secret": "AKIAIOSFODNN7REALKEY",
        "Match": 'AWS_SECRET = "AKIAIOSFODNN7REALKEY"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_real_leak) is False

    # Live key prefix in test file must NOT be ignored
    finding_live_in_test = {
        "RuleID": "stripe-api-key",
        "File": "tests/test_billing.py",
        "StartLine": 10,
        "Secret": "sk_live_51MzREALPRODKEY9999",
        "Match": "sk_live_51MzREALPRODKEY9999",
    }
    assert SecretLeakScannerService.is_false_positive(finding_live_in_test) is False


@pytest.mark.asyncio
async def test_scan_history_filters_test_keys(tmp_path: Path):
    service = SecretLeakScannerService()
    mock_findings = [
        {
            "RuleID": "google-api-key",
            "File": "tests/test_api_endpoints_comprehensive.py",
            "StartLine": 12,
            "Secret": "AIzaSyTestKey123456789",
        },
        {
            "RuleID": "aws-access-key",
            "File": "scripts/deploy.py",
            "StartLine": 25,
            "Secret": "AKIAIOSFODNN7REALKEY",
        },
    ]
    mock_run = MagicMock()
    mock_run.stdout = json.dumps(mock_findings)

    with patch("subprocess.run", return_value=mock_run):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 1
        assert result.leaked_secrets[0].file == "scripts/deploy.py"
        assert len(result.ignored_test_secrets) == 1
        assert result.ignored_test_secrets[0].file == "tests/test_api_endpoints_comprehensive.py"

