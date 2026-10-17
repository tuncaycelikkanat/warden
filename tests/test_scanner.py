from pathlib import Path

from core.services.scanner import SecurityScannerService

SAMPLE = Path(__file__).parent / "fixtures" / "vulnerable_samples" / "insecure_crypto_exec.py"


def test_scanner_finds_hardcoded_secret():
    findings = SecurityScannerService().scan_file(str(SAMPLE))

    # The custom rule should catch the 2 hardcoded secrets in the sample
    assert len(findings) >= 2

    rule_ids = [finding["check_id"] for finding in findings]
    assert "core.rules.vibe_coding.vibe-hardcoded-secret" in rule_ids
