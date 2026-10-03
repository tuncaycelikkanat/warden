"""Unit tests for EntropyAnalyzerService (Shannon Entropy secret detection)."""

from __future__ import annotations

import math
from pathlib import Path

from core.services.entropy_analyzer import EntropyAnalyzerService


class TestEntropyAnalyzer:
    """Tests for Shannon entropy calculation and secret detection."""

    def setup_method(self):
        self.service = EntropyAnalyzerService()

    def test_calculate_entropy_basics(self):
        """Test fundamental Shannon entropy math properties."""
        # Empty string
        assert self.service.calculate_entropy("") == 0.0

        # Uniform repetition: "aaaa" has 0 entropy
        assert self.service.calculate_entropy("aaaa") == 0.0

        # Two equally distributed symbols: "abab" has 1 bit entropy
        assert math.isclose(self.service.calculate_entropy("abab"), 1.0, abs_tol=1e-5)

        # Standard English sentence has moderate entropy ~3.0 - 4.5
        eng_entropy = self.service.calculate_entropy("the quick brown fox jumps over the lazy dog")
        assert 3.0 <= eng_entropy <= 4.5

        # High-entropy random cryptographic token (base64)
        high_entropy_token = "dGhpcy1pcy1hLXZlcnktc2VjdXJlLXRva2VuLXZhbHVlLTEyMzQ1Njc4OTA="
        rand_entropy = self.service.calculate_entropy(high_entropy_token)
        assert rand_entropy > 4.5

    def test_detect_charset(self):
        """Test charset classification."""
        assert self.service.detect_charset("0123456789abcdefABCDEF") == "hex"
        assert self.service.detect_charset("a1b2c3d4e5f6") == "hex"
        assert self.service.detect_charset("dGhpcy1pcy1hLXNlY3JldA==") == "base64"
        assert self.service.detect_charset("HelloWorld123") == "alphanumeric"

    def test_scan_code_detects_sensitive_assignment(self):
        """Test detection of high-entropy string assigned to sensitive variable."""
        code = (
            '# Config\n'
            'api_key = "9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c"\n'
            'normal_title = "Welcome to our application home page"\n'
        )
        findings = self.service.scan_code(code, "config.py")
        assert len(findings) == 1
        f = findings[0]
        assert f.variable_name == "api_key"
        assert f.charset_type == "hex"
        assert f.confidence in ("HIGH", "MEDIUM")
        assert "*" in f.masked_value

    def test_scan_code_detects_dict_secret(self):
        """Test detection of high-entropy key inside dictionary."""
        code = (
            'credentials = {\n'
            '    "stripe_webhook_secret": "whsec_b2a8f4c91d3e7a0f5c6b8d2e4a1f3c7e",\n'
            '    "app_name": "MyBillingApp"\n'
            '}\n'
        )
        findings = self.service.scan_code(code, "billing.py")
        assert len(findings) == 1
        assert "webhook_secret" in findings[0].variable_name

    def test_scan_code_detects_function_keyword_secret(self):
        """Test detection of secret in keyword argument."""
        code = 'client = ThirdPartyAPI(token="ghp_ab7C9dE1fGhIjKlMnOpQrStUvWxYz012345")'
        findings = self.service.scan_code(code, "client.py")
        assert len(findings) == 1
        assert findings[0].variable_name == "token"

    def test_ignores_non_secrets_and_placeholders(self):
        """Test that URLs, paths, and placeholders are ignored."""
        code = (
            'url = "https://api.github.com/repos/owner/repo/pulls"\n'
            'path = "/usr/local/share/application/data/manifest.json"\n'
            'dummy_key = "SAMPLE_KEY_FOR_TESTING_PURPOSES_123456789"\n'
            'doc = "This is a simple documentation string without any secret"\n'
        )
        findings = self.service.scan_code(code, "utils.py")
        assert len(findings) == 0

    def test_scan_repository(self, tmp_path: Path):
        """Test repository scanning with test directory exclusion."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Secret in src
        (src_dir / "auth.py").write_text(
            'private_key = "3b8a1c9e7d5f2a4b6c8d0e1f3a5b7c9d"\n',
            encoding="utf-8",
        )
        # Mock in tests directory should be skipped
        (test_dir / "test_auth.py").write_text(
            'private_key = "3b8a1c9e7d5f2a4b6c8d0e1f3a5b7c9d"\n',
            encoding="utf-8",
        )

        findings = self.service.scan_repository(tmp_path)
        assert len(findings) == 1
        assert "auth.py" in findings[0].file
        assert "test_auth.py" not in findings[0].file
