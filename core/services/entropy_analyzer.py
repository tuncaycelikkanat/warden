"""Shannon Entropy-based Secret Detection Analyzer.

Computes Shannon entropy H(X) = -sum(P(x) * log2(P(x))) over string literals
extracted from codebase AST and config files. Identifies high-entropy cryptographic
tokens, API keys, private keys, and credentials, eliminating false positives using
character set heuristics and assignment context analysis.
"""

from __future__ import annotations

import ast
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Keywords indicating sensitive variable names / keys
SENSITIVE_VAR_KEYWORDS = {
    "key",
    "token",
    "secret",
    "password",
    "passwd",
    "auth",
    "api",
    "credential",
    "priv",
    "private",
    "jwt",
    "bearer",
    "webhook",
    "signing",
    "access",
}

# Universal placeholders and mock signals to ignore
PLACEHOLDER_WORDS = {
    "example",
    "placeholder",
    "dummy",
    "sample",
    "xxxx",
    "000000",
    "123456",
}

TEST_DIR_PARTS = {"tests", "test", "fixtures", "mocks"}


@dataclass
class EntropyFinding:
    """Represents a high-entropy secret finding in a codebase file."""

    file: str
    line: int
    variable_name: str
    masked_value: str
    entropy_score: float
    charset_type: str  # "hex" | "base64" | "alphanumeric" | "ascii"
    confidence: str    # "HIGH" | "MEDIUM" | "LOW"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "variable_name": self.variable_name,
            "masked_value": self.masked_value,
            "entropy_score": round(self.entropy_score, 2),
            "charset_type": self.charset_type,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def mask_secret(raw_value: str) -> str:
    """Masks a secret string so raw credentials are never persisted or displayed."""
    if not raw_value:
        return ""
    if len(raw_value) <= 8:
        return "*" * len(raw_value)
    return f"{raw_value[:4]}{'*' * (len(raw_value) - 8)}{raw_value[-4:]}"


class EntropyAnalyzerService:
    """Service to evaluate string literal entropy and detect potential secret leaks."""

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculates Shannon entropy in bits per character for a given string."""
        if not text:
            return 0.0

        length = len(text)
        counts = Counter(text)
        entropy = 0.0

        for count in counts.values():
            p_x = count / length
            entropy -= p_x * math.log2(p_x)

        return entropy

    @staticmethod
    def detect_charset(text: str) -> str:
        """Determines predominant character set of a string (hex, base64, alphanumeric)."""
        hex_chars = set("0123456789abcdefABCDEF")
        b64_special = set("+/=")
        b64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")

        text_chars = set(text)
        if text_chars.issubset(hex_chars):
            return "hex"
        if any(c in b64_special for c in text_chars) and text_chars.issubset(b64_chars):
            return "base64"
        if text.isalnum():
            return "alphanumeric"
        if text_chars.issubset(b64_chars):
            return "base64"
        return "ascii"

    def _is_obvious_non_secret(self, val: str) -> bool:
        """Identifies standard text, paths, format strings, or placeholders."""
        lowered = val.lower()

        # Whitespace check: cryptographic keys do not contain internal spaces
        if " " in val or "\n" in val or "\t" in val:
            return True

        # Universal placeholders
        for p in PLACEHOLDER_WORDS:
            if p in lowered:
                return True
        if re.search(r"(?:^|[_\-./\s0-9])(?:test|mock|fake)(?:[_\-./\s0-9]|$)", lowered):
            return True

        # Common web/filesystem paths
        if lowered.startswith(("http://", "https://", "file://", "ftp://", "ssh://")):
            # Unless it embeds credentials (e.g. user:token@host)
            if "@" not in lowered:
                return True
        if lowered.startswith(("/", "./", "../", "c:\\", "c:/", "\\")):
            return True

        # File extensions or MIME types
        if re.search(r"\.(py|json|yaml|yml|md|txt|html|css|js|png|jpg|svg|gz|tar|zip)$", lowered):
            return True
        if "/" in lowered and any(lowered.endswith(ext) for ext in (".json", ".txt", ".csv")):
            return True

        # Repeated characters (e.g. "AAAAAAAAAAAAAAAA")
        return len(set(val)) <= 3

    def scan_code(self, source_code: str, file_path: str = "") -> list[EntropyFinding]:
        """Scans Python source code using AST to find high-entropy string literals."""
        findings: list[EntropyFinding] = []

        try:
            tree = ast.parse(source_code, filename=file_path)
        except Exception:
            return findings

        # Track variable names from assignments and dict keys
        for node in ast.walk(tree):
            # Assignment: x = "secret"
            if isinstance(node, ast.Assign):
                var_names: list[str] = []
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_names.append(target.id)
                    elif isinstance(target, ast.Attribute):
                        var_names.append(target.attr)

                var_context = "_".join(var_names) if var_names else ""
                val_node = node.value

                if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                    finding = self._evaluate_literal(
                        val_node.value,
                        var_context,
                        file_path,
                        getattr(val_node, "lineno", 1),
                    )
                    if finding:
                        findings.append(finding)

            # Dictionary literal: {"api_key": "secret"}
            elif isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    key_name = ""
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        key_name = k.value
                    elif isinstance(k, ast.Name):
                        key_name = k.id

                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        finding = self._evaluate_literal(
                            v.value,
                            key_name,
                            file_path,
                            getattr(v, "lineno", 1),
                        )
                        if finding:
                            findings.append(finding)

            # Function call keywords: client.init(api_key="secret")
            elif isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        finding = self._evaluate_literal(
                            kw.value.value,
                            kw.arg,
                            file_path,
                            getattr(kw.value, "lineno", 1),
                        )
                        if finding:
                            findings.append(finding)

        return findings

    def _evaluate_literal(
        self,
        literal_val: str,
        var_context: str,
        file_path: str,
        line_no: int,
    ) -> EntropyFinding | None:
        """Evaluates whether a string literal qualifies as a high-entropy secret finding."""
        trimmed = literal_val.strip()
        length = len(trimmed)

        # Minimum plausible secret length (UUID without hyphens is 32, API keys usually >= 16)
        if length < 16:
            return None

        if self._is_obvious_non_secret(trimmed):
            return None

        entropy = self.calculate_entropy(trimmed)
        charset = self.detect_charset(trimmed)

        var_lower = var_context.lower()
        has_sensitive_keyword = any(kw in var_lower for kw in SENSITIVE_VAR_KEYWORDS)

        # Theoretical bounds: Hex max is 4.0, Base64 max is 6.0
        # If variable name indicates sensitive data, lower threshold to catch subtle keys
        if has_sensitive_keyword:
            min_entropy = 3.2 if charset == "hex" else 3.8
            if entropy >= min_entropy:
                return EntropyFinding(
                    file=file_path,
                    line=line_no,
                    variable_name=var_context,
                    masked_value=mask_secret(trimmed),
                    entropy_score=entropy,
                    charset_type=charset,
                    confidence="HIGH" if entropy >= 4.2 else "MEDIUM",
                    reason=f"High entropy ({entropy:.2f}) with sensitive variable name '{var_context}'",
                )
        else:
            # Without sensitive naming, require higher entropy and sufficient length to prevent FPs
            min_entropy = 3.8 if charset == "hex" else 4.6
            if entropy >= min_entropy and length >= 20:
                return EntropyFinding(
                    file=file_path,
                    line=line_no,
                    variable_name=var_context,
                    masked_value=mask_secret(trimmed),
                    entropy_score=entropy,
                    charset_type=charset,
                    confidence="MEDIUM",
                    reason=f"Very high Shannon entropy ({entropy:.2f}) detected in literal",
                )

        return None

    def scan_file(self, file_path: Path) -> list[EntropyFinding]:
        """Scans a single file for high-entropy secrets."""
        file_path = file_path.resolve()
        # Skip test directories
        if any(part.lower() in TEST_DIR_PARTS for part in file_path.parts):
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return self.scan_code(content, str(file_path))
        except Exception as err:
            logger.debug(f"Could not read {file_path} for entropy analysis: {err}")
            return []

    def scan_repository(self, repo_path: Path, max_findings: int = 50) -> list[EntropyFinding]:
        """Scans Python files in repository for high-entropy secrets."""
        repo_path = repo_path.resolve()
        findings: list[EntropyFinding] = []

        from core.utils.file_discovery import discover_source_files

        source_files = discover_source_files(repo_path)
        for sf in source_files:
            if sf.suffix.lower() == ".py":
                file_findings = self.scan_file(sf)
                findings.extend(file_findings)
                if len(findings) >= max_findings:
                    break

        return findings[:max_findings]
