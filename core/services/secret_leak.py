"""Secret leak detection analyzer across Git history using Gitleaks."""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.config.secret_scan_config import (
    DEFAULT_SINCE_MONTHS,
    HIGH_CONFIDENCE_MOCK_TOKENS,
    LIVE_KEY_PREFIXES,
    LOW_CONFIDENCE_MOCK_TOKENS,
    TEST_DOC_DIRS,
    TEST_FILE_EXTENSIONS,
    TEST_FILE_NAMES,
    UNIVERSAL_PLACEHOLDERS,
)

logger = logging.getLogger(__name__)


def mask_secret(raw_value: str) -> str:
    """Masks a secret string so raw credentials are never persisted or displayed."""
    if not raw_value:
        return ""
    if len(raw_value) <= 8:
        return "*" * len(raw_value)
    return f"{raw_value[:4]}{'*' * (len(raw_value) - 8)}{raw_value[-4:]}"


def _is_in_test_context(file_path: str) -> bool:
    """Checks if file path belongs to test, fixture, or mock directories."""
    path_obj = Path(file_path.lower())
    parts = set(path_obj.parts)
    return (
        bool(parts & TEST_DOC_DIRS)
        or path_obj.name.startswith("test_")
        or path_obj.name.endswith(TEST_FILE_EXTENSIONS)
        or path_obj.name in TEST_FILE_NAMES
    )


def _contains_word(text: str, tokens: set[str]) -> bool:
    """Checks if text contains any token as a delimited word, camelCase segment, or boundary."""
    if not text:
        return False
    lowered = text.lower()
    for t in tokens:
        delim_pattern = rf"(?:^|[_\-./\s0-9]){re.escape(t)}(?:[_\-./\s0-9]|$)"
        if re.search(delim_pattern, lowered):
            return True
        if t in HIGH_CONFIDENCE_MOCK_TOKENS:
            if t in lowered:
                return True
        if t == "test":
            if re.search(r"(?:^|[_\-0-9/]|[a-z])(?:test|Test|TEST)(?=[_\-0-9A-Z/]|$)", text):
                return True
        if t in {"123456", "deadbeef", "000000", "xxxx"}:
            if t in lowered:
                return True
    return False



@dataclass
class LeakedSecret:
    """Represents a hardcoded secret detected in repository files or commits."""
    rule_id: str
    file: str
    line: int
    commit: str
    author: str
    date: str
    message: str
    masked_secret: str

    @property
    def secret(self) -> str:
        """Alias returning the masked secret for backwards compatibility."""
        return self.masked_secret

    @classmethod
    def from_gitleaks(cls, data: dict) -> 'LeakedSecret':
        """Constructs a LeakedSecret instance from Gitleaks JSON record with masked secret."""
        raw_sec = str(data.get("Secret", "") or "")
        return cls(
            rule_id=data.get("RuleID", ""),
            file=data.get("File", ""),
            line=data.get("StartLine", 0),
            commit=data.get("Commit", ""),
            author=data.get("Author", ""),
            date=data.get("Date", ""),
            message=data.get("Message", ""),
            masked_secret=mask_secret(raw_sec),
        )


@dataclass
class IgnoreFileAudit:
    """Audit metrics for repository .gitleaksignore file."""
    exists: bool = False
    total_entries: int = 0
    undocumented_entries: int = 0


@dataclass
class SecretLeakResult:
    """Encapsulates all identified leaked secret findings."""
    leaked_secrets: list[LeakedSecret]
    ignored_test_secrets: list[LeakedSecret] = field(default_factory=list)
    scan_scope: str = "last_6_months"
    ignore_audit: IgnoreFileAudit = field(default_factory=IgnoreFileAudit)


class SecretLeakScannerService:
    """Service to scan Git history and tree for secret keys using Gitleaks."""

    @staticmethod
    def is_false_positive(finding: dict) -> bool:
        """
        Determines if a Gitleaks finding is a dummy, mock, test fixture, or placeholder.
        Uses multi-signal AND logic to avoid suppressing real leaks containing common substrings.
        """
        secret_value = str(finding.get("Secret", "") or "").strip()
        file_path = str(finding.get("File", "") or "").strip()
        match_str = str(finding.get("Match", "") or "").strip()
        variable_name = str(finding.get("variable_name", "") or "").strip()

        # 1. Live key prefix always takes absolute precedence — NEVER ignore
        if secret_value.startswith(LIVE_KEY_PREFIXES) or "BEGIN" in secret_value:
            return False

        # 2. Universal placeholders anywhere in the repository
        secret_lower = secret_value.lower()
        if any(marker in secret_lower for marker in UNIVERSAL_PLACEHOLDERS):
            return True

        # 3. Test/fixture context is a mandatory prerequisite
        if not _is_in_test_context(file_path):
            return False

        # Extract variable name or declaration context (LHS of assignment)
        var_context = variable_name
        if not var_context:
            if "=" in match_str:
                var_context = match_str.split("=")[0].strip()
            elif ":" in match_str:
                var_context = match_str.split(":")[0].strip()
            else:
                var_context = ""

        # 4. High-confidence token: sufficient on its own in test context
        if _contains_word(secret_value, HIGH_CONFIDENCE_MOCK_TOKENS):
            return True
        if var_context and _contains_word(var_context, HIGH_CONFIDENCE_MOCK_TOKENS):
            return True

        # 5. Low-confidence token: NOT sufficient on its own.
        # Only accepted if variable name ALSO has a mock/test signal (two independent signals).
        value_has_low_signal = _contains_word(secret_value, LOW_CONFIDENCE_MOCK_TOKENS)
        all_tokens = HIGH_CONFIDENCE_MOCK_TOKENS | LOW_CONFIDENCE_MOCK_TOKENS
        var_has_signal = bool(var_context and _contains_word(var_context, all_tokens))

        return bool(value_has_low_signal and var_has_signal)



    def check_ignore_file_hygiene(self, repo_path: Path) -> IgnoreFileAudit:
        """Audits .gitleaksignore file to ensure suppressions include rationale."""
        ignore_path = repo_path / ".gitleaksignore"
        if not ignore_path.exists():
            return IgnoreFileAudit(exists=False, total_entries=0, undocumented_entries=0)

        content = ignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        entries = 0
        undocumented = 0
        in_comment_block = False

        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                in_comment_block = False
                continue
            if trimmed.startswith("#"):
                in_comment_block = True
                continue
            entries += 1
            has_inline = "#" in line
            if not (has_inline or in_comment_block):
                undocumented += 1

        return IgnoreFileAudit(exists=True, total_entries=entries, undocumented_entries=undocumented)


    async def scan_history(
        self,
        repo_path: Path,
        full_history: bool = False,
        since_months: int = DEFAULT_SINCE_MONTHS,
    ) -> SecretLeakResult:
        """Runs gitleaks to detect hardcoded secrets across git history or recent window."""
        import asyncio

        ignore_audit = self.check_ignore_file_hygiene(repo_path)
        scan_scope = "full_history" if full_history else f"last_{since_months}_months"

        def run_gitleaks() -> list[dict]:
            cmd = [
                "gitleaks", "detect",
                "--source", str(repo_path),
                "--report-format", "json",
                "--report-path", "/dev/stdout",
                "--exit-code", "0",
            ]
            if not full_history:
                since_date = (datetime.now(UTC) - timedelta(days=30 * since_months)).strftime("%Y-%m-%d")
                cmd.extend(["--log-opts", f"--since={since_date}"])


            ignore_file = repo_path / ".gitleaksignore"
            if ignore_file.exists():
                cmd.extend(["--gitleaks-ignore-path", str(ignore_file)])

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if not result.stdout.strip():
                    return []
                return json.loads(result.stdout)
            except Exception as e:
                logger.error(f"Failed to run gitleaks: {e}")
                return []

        raw_findings = await asyncio.to_thread(run_gitleaks)
        leaks: list[LeakedSecret] = []
        ignored: list[LeakedSecret] = []

        for f in raw_findings:
            secret_obj = LeakedSecret.from_gitleaks(f)
            if self.is_false_positive(f):
                ignored.append(secret_obj)
            else:
                leaks.append(secret_obj)

        if ignored:
            logger.info(
                f"Filtered out {len(ignored)} mock/dummy/test secret fixture(s) "
                f"from security penalty."
            )

        return SecretLeakResult(
            leaked_secrets=leaks,
            ignored_test_secrets=ignored,
            scan_scope=scan_scope,
            ignore_audit=ignore_audit,
        )
