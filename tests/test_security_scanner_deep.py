"""Unit tests for SecurityScannerService Semgrep integration and risk calculation."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.services.scanner import SecurityScannerService


def test_scanner_init_and_properties(tmp_path):
    s1 = SecurityScannerService(rule_dirs=str(tmp_path))
    assert s1.rule_dirs == [str(tmp_path)]
    assert s1.rule_dir == str(tmp_path)

    s2 = SecurityScannerService(rule_dirs=["/dir1", "/dir2"])
    assert s2.rule_dirs == ["/dir1", "/dir2"]
    assert s2.rule_dir == "/dir1"

    s3 = SecurityScannerService(rule_dirs=[])
    assert s3.rule_dir == "core/rules"

    s4 = SecurityScannerService(rule_dirs=None)
    assert len(s4.rule_dirs) >= 1


def test_scan_file_not_found():
    scanner = SecurityScannerService()
    with pytest.raises(FileNotFoundError):
        scanner.scan_file("/nonexistent/file/path.py")


def test_scan_file_empty_and_errors(tmp_path):
    scanner = SecurityScannerService()
    test_file = tmp_path / "foo.py"
    test_file.write_text("print('hello')", encoding="utf-8")

    # 1. Empty stdout
    with patch("subprocess.run", return_value=MagicMock(stdout="  ", stderr="error")):
        assert scanner.scan_file(str(test_file)) == []

    # 2. SubprocessError
    with patch("subprocess.run", side_effect=subprocess.SubprocessError("Semgrep crashed")):
        assert scanner.scan_file(str(test_file)) == []

    # 3. Invalid JSON
    with patch("subprocess.run", return_value=MagicMock(stdout="not json", stderr="")):
        assert scanner.scan_file(str(test_file)) == []


def test_scan_file_success(tmp_path):
    scanner = SecurityScannerService(rule_dirs="/dummy/rules")
    test_file = tmp_path / "foo.py"
    test_file.write_text("eval(x)", encoding="utf-8")

    semgrep_output = {
        "results": [
            {
                "check_id": "python.lang.security.audit.eval",
                "extra": {"severity": "ERROR", "message": "Use of eval"},
            }
        ]
    }

    with patch("subprocess.run", return_value=MagicMock(stdout=json.dumps(semgrep_output), stderr="")):
        findings = scanner.scan_file(str(test_file))
        assert len(findings) == 1
        assert findings[0]["check_id"] == "python.lang.security.audit.eval"


@pytest.mark.asyncio
async def test_scan_files_parallel(tmp_path):
    scanner = SecurityScannerService()
    f1 = tmp_path / "f1.py"
    f2 = tmp_path / "f2.py"
    f1.write_text("x = 1", encoding="utf-8")
    f2.write_text("y = 2", encoding="utf-8")

    with patch.object(scanner, "scan_file", side_effect=[[{"id": "find1"}], [{"id": "find2"}]]):
        findings = await scanner.scan_files([f1, f2])
        assert len(findings) == 2


def test_calculate_risk_level():
    scanner = SecurityScannerService()

    # Empty findings
    assert scanner.calculate_risk_level([]) == "low"

    # Info only
    assert scanner.calculate_risk_level([{"extra": {"severity": "INFO"}}]) == "low"

    # Warning
    assert scanner.calculate_risk_level([{"extra": {"severity": "WARNING"}}]) == "medium"

    # Error
    assert scanner.calculate_risk_level([
        {"extra": {"severity": "WARNING"}},
        {"extra": {"severity": "ERROR"}},
    ]) == "high"
