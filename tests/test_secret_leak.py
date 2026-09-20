import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.secret_leak import (
    IgnoreFileAudit,
    LeakedSecret,
    SecretLeakResult,
    SecretLeakScannerService,
    mask_secret,
)


def test_leaked_secret_masking():
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
    # Must be masked
    assert secret.masked_secret == "sk-1*****7890"
    assert secret.secret == "sk-1*****7890"
    # Ensure raw_value does not exist as an attribute
    assert not hasattr(secret, "raw_value")


def test_mask_secret_helper():
    assert mask_secret("") == ""
    assert mask_secret("short") == "*****"
    assert mask_secret("12345678") == "********"
    assert mask_secret("AKIA" + "IOSFODNN7EXAMPLE") == "AKIA************MPLE"



def test_secret_leak_result():
    res = SecretLeakResult(leaked_secrets=[])
    assert res.leaked_secrets == []
    assert res.scan_scope == "last_6_months"
    assert isinstance(res.ignore_audit, IgnoreFileAudit)


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
            "Secret": "AKIA" + "IOSFODNN7EXAMPLE",

        }
    ]
    mock_run = MagicMock()
    mock_run.stdout = json.dumps(mock_findings)

    # Test with .gitleaksignore present
    (tmp_path / ".gitleaksignore").write_text("# ignore rules\nrule-id-1")

    with patch("subprocess.run", return_value=mock_run):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 1
        assert result.leaked_secrets[0].rule_id == "aws-access-key"
        assert result.leaked_secrets[0].secret == "AKIA************MPLE"


@pytest.mark.asyncio
async def test_scan_history_exception(tmp_path: Path):
    service = SecretLeakScannerService()

    with patch("subprocess.run", side_effect=FileNotFoundError("gitleaks not found")):
        result = await service.scan_history(tmp_path)
        assert len(result.leaked_secrets) == 0


def test_is_false_positive_regression_123456_in_real_key():
    """
    Kritik Regresyon: Test dizini içinde, değişken adı api_key olan
    ve değerinde rastgele 123456 geçen bir anahtar MOCK SAYILMAMALIDIR.
    """
    finding_real_key_with_123456 = {
        "RuleID": "generic-api-key",
        "File": "tests/test_service.py",
        "StartLine": 15,
        "Secret": "sec_p8q9r123456xyz999000",
        "Match": 'api_key = "sec_p8q9r123456xyz999000"',
    }
    # Low confidence '123456' is present, but variable 'api_key' has no mock signal -> False
    assert SecretLeakScannerService.is_false_positive(finding_real_key_with_123456) is False


def test_is_false_positive_multi_signal_mock():
    """
    Doğru Pozitif: Hem değer hem değişken adı mock sinyali taşıyorsa filtrelenmelidir.
    """
    finding_mock_stripe = {
        "RuleID": "stripe-api-key",
        "File": "tests/fixtures/mock_stripe.py",
        "StartLine": 10,
        "Secret": "sk_test_mock123456",
        "Match": 'mock_api_key = "sk_test_mock123456"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_mock_stripe) is True


def test_is_false_positive_live_key_always_fails():
    """
    Canlı anahtar öneki (sk_live_, AKIA, -----BEGIN) test dosyasında olsa bile ASLA filtrelenmez.
    """
    finding_live = {
        "RuleID": "stripe-api-key",
        "File": "tests/test_billing.py",
        "StartLine": 20,
        "Secret": "sk_live_" + "51MzPRODKEY999mock123",
        "Match": 'mock_key = "' + "sk_live_" + '51MzPRODKEY999mock123"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_live) is False

    finding_aws = {
        "RuleID": "aws-access-key",
        "File": "tests/test_aws.py",
        "StartLine": 5,
        "Secret": "AKIA" + "IOSFODNN7REALKEY",
        "Match": 'test_key = "' + "AKIA" + 'IOSFODNN7REALKEY"',
    }
    assert SecretLeakScannerService.is_false_positive(finding_aws) is False



def test_is_false_positive_universal_placeholders():
    """
    Evrensel yer tutucular dosya yolu fark etmeksizin filtrelenir.
    """
    finding_placeholder = {
        "RuleID": "generic-api-key",
        "File": "config/settings.py",
        "StartLine": 20,
        "Secret": "your_api_key_here",
        "Match": "API_KEY = your_api_key_here",
    }
    assert SecretLeakScannerService.is_false_positive(finding_placeholder) is True


@pytest.mark.asyncio
async def test_full_history_flag(tmp_path: Path):
    """
    full_history=False çağrısında --since bayrağı bulunmalı, full_history=True'da bulunmamalı.
    """
    service = SecretLeakScannerService()
    captured_commands = []

    def mock_run(cmd, **kwargs):
        captured_commands.append(cmd)
        mock_obj = MagicMock()
        mock_obj.stdout = "[]"
        return mock_obj

    with patch("subprocess.run", side_effect=mock_run):
        # Default (windowed 6 months)
        res_windowed = await service.scan_history(tmp_path, full_history=False)
        assert res_windowed.scan_scope == "last_6_months"
        assert any("--since=" in arg for arg in captured_commands[0])

        # Full history
        res_full = await service.scan_history(tmp_path, full_history=True)
        assert res_full.scan_scope == "full_history"
        assert not any("--since=" in arg for arg in captured_commands[1])


def test_gitleaksignore_hygiene_audit(tmp_path: Path):
    """
    .gitleaksignore içindeki gerekçeli ve gerekçesiz satırları doğru saymalıdır.
    """
    service = SecretLeakScannerService()

    # Dosya yoksa
    audit_none = service.check_ignore_file_hygiene(tmp_path)
    assert audit_none.exists is False
    assert audit_none.total_entries == 0

    # Dosya varsa
    ignore_content = """# Gerekçeli satır
hash_1234567890abcdef

# Başka bir gerekçeli satır
hash_0987654321fedcba

hash_undocumented_12345
"""
    (tmp_path / ".gitleaksignore").write_text(ignore_content)
    audit = service.check_ignore_file_hygiene(tmp_path)
    assert audit.exists is True
    assert audit.total_entries == 3
    assert audit.undocumented_entries == 1
