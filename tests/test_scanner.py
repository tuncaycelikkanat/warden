import os
from core.services.scanner import SecurityScannerService

def test_scanner_finds_hardcoded_secret():
    # Use the dummy_test.py that we created earlier
    test_file = "dummy_test.py"
    
    assert os.path.exists(test_file), "dummy_test.py must exist for this test"
    
    scanner = SecurityScannerService()
    findings = scanner.scan_file(test_file)
    
    # The custom rule should catch the 2 hardcoded secrets in dummy_test.py
    assert len(findings) >= 2
    
    rule_ids = [finding["check_id"] for finding in findings]
    assert "core.rules.vibe_coding.vibe-hardcoded-secret" in rule_ids
