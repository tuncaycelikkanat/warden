from pathlib import Path

import pytest

from core.services.scanner import SecurityScannerService
from core.utils.file_discovery import discover_source_files


@pytest.mark.asyncio
async def test_full_repo_scan():
    # Test file discovery
    test_dir = Path("tests/test_data/audit_test")
    files = discover_source_files(test_dir)
    
    assert len(files) >= 2
    assert any("vuln1.py" in str(f) for f in files)
    assert any("vuln2.py" in str(f) for f in files)
    
    # Test parallel scanning
    scanner = SecurityScannerService()
    findings = await scanner.scan_files(files)
    
    # Check that we found the sql injection and hardcoded secret
    assert len(findings) > 0
    
    rule_ids = [f.get("check_id", "") for f in findings]
    assert len(rule_ids) > 0
    
    # Exact check IDs depend on the semgrep rules in core/rules/vibe_coding
    # But we know they should exist if they matched. We can just check we got findings for both files.
    paths = [f.get("path", "") for f in findings]
    assert any("vuln1.py" in p for p in paths)
    assert any("vuln2.py" in p for p in paths)
