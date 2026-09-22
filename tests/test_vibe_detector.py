"""Tests for the VibeCodingDetector service."""

from pathlib import Path

import pytest

from core.services.vibe_detector import VibeCodingDetector


@pytest.fixture
def detector() -> VibeCodingDetector:
    return VibeCodingDetector()


class TestVibeCodingDetector:
    def test_clean_file_has_zero_findings(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        clean_file = tmp_path / "domain.py"
        clean_file.write_text("""
class UserEntity:
    def __init__(self, username: str) -> None:
        self.username = username
""")
        findings = detector.analyze_file(clean_file, tmp_path)
        assert len(findings) == 0

    def test_ai_commentary_detected(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        vibe_file = tmp_path / "script.py"
        vibe_file.write_text("""
# Import necessary libraries
import os
import sys

# Function to calculate sum of two integers
def add(a, b):
    # Note: this is a mock implementation
    # In production, you should validate inputs
    return a + b
""")
        findings = detector.analyze_file(vibe_file, tmp_path)
        rules = [f.rule for f in findings]
        assert "Didactic import commentary" in rules
        assert "Obvious function commentary" in rules
        assert "LLM explanatory note" in rules
        assert "LLM production disclaimer comment" in rules

    def test_placeholder_token_commentary(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        token_file = tmp_path / "api.py"
        token_file.write_text("""
# Replace this with your actual api_key
API_KEY = 'YOUR_KEY_HERE'
""")
        findings = detector.analyze_file(token_file, tmp_path)
        assert any("Placeholder token commentary" in f.rule for f in findings)

    def test_markdown_residue_detected(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        md_file = tmp_path / "snippet.py"
        md_file.write_text("""
```python
def example():
    return True
```
""")
        findings = detector.analyze_file(md_file, tmp_path)
        assert any("Markdown codeblock residue" in f.rule for f in findings)

    def test_ast_swallowed_exception_detected(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        except_file = tmp_path / "handler.py"
        except_file.write_text("""
def run():
    try:
        do_work()
    except Exception:
        pass

def run_print():
    try:
        do_work()
    except Exception as e:
        print(e)
""")
        findings = detector.analyze_file(except_file, tmp_path)
        swallowed = [f for f in findings if "swallowed" in f.rule.lower()]
        assert len(swallowed) == 2

    def test_repository_scoring(self, detector: VibeCodingDetector, tmp_path: Path) -> None:
        # File 1: clean
        (tmp_path / "clean.py").write_text("def ok(): return 42\n")
        # File 2: heavy vibe code
        (tmp_path / "vibe.py").write_text("""
# Import necessary libraries
import math

# Step 1: initialize variables
x = 10

# Note: this is a simple example
try:
    y = math.sqrt(x)
except Exception:
    pass
""")
        result = detector.analyze_repository(tmp_path)
        assert result.total_files_analyzed == 2
        assert result.flagged_files_count == 1
        assert result.vibe_score > 0.0
        assert result.risk_level in ("MODERATE", "HIGH", "CRITICAL", "LOW")
        d = result.to_dict()
        assert "vibe_score" in d
        assert len(d["findings"]) > 0
