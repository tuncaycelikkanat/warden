"""Secret leak detection analyzer across Git history using Gitleaks."""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

TEST_DOC_DIRS = {
    "test", "tests", "testing", "fixtures", "fixture",
    "mocks", "mock", "__tests__", "spec", "specs",
    "sample", "samples", "example", "examples", "docs", "doc",
    "test_data", "testdata",
}

TEST_FILE_EXTENSIONS = (
    "_test.py", ".test.ts", ".test.js", ".spec.ts", ".spec.js",
    ".test.jsx", ".test.tsx", ".spec.jsx", ".spec.tsx",
)

TEST_FILE_NAMES = {
    "conftest.py", "mock.py", "fixture.py", "fixtures.py", "test.py", "tests.py",
}

UNIVERSAL_DUMMY_MARKERS = (
    "placeholder",
    "dummy_key",
    "dummy_secret",
    "dummy_token",
    "fake_secret",
    "fake_key",
    "your_api_key",
    "your-api-key",
    "your_secret",
    "replace_me",
    "change_me",
    "insert_here",
    "my_secret_key",
    "sample_key",
    "example_key",
    "example_token",
    "sk_test_",
    "pk_test_",
    "sk-test-",
    "pk-test-",
)

TEST_CONTEXT_MARKERS = (
    "test",
    "dummy",
    "mock",
    "fake",
    "sample",
    "example",
    "placeholder",
    "fixture",
    "stub",
    "123456",
    "abcdef",
    "000000",
    "xxxxxx",
    "qwerty",
)


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
    secret: str

    @classmethod
    def from_gitleaks(cls, data: dict) -> 'LeakedSecret':
        """Constructs a LeakedSecret instance from Gitleaks JSON record."""
        return cls(
            rule_id=data.get("RuleID", ""),
            file=data.get("File", ""),
            line=data.get("StartLine", 0),
            commit=data.get("Commit", ""),
            author=data.get("Author", ""),
            date=data.get("Date", ""),
            message=data.get("Message", ""),
            secret=data.get("Secret", "")
        )


@dataclass
class SecretLeakResult:
    """Encapsulates all identified leaked secret findings."""
    leaked_secrets: list[LeakedSecret]
    ignored_test_secrets: list[LeakedSecret] = field(default_factory=list)


class SecretLeakScannerService:
    """Service to scan entire Git history and tree for secret keys using Gitleaks."""

    @staticmethod
    def is_false_positive(finding: dict) -> bool:
        """Determines if a Gitleaks finding is a dummy, mock, test fixture, or placeholder."""
        secret = str(finding.get("Secret", "")).strip()
        file_path = str(finding.get("File", "")).strip()
        match_str = str(finding.get("Match", "")).strip()

        secret_lower = secret.lower()
        file_lower = file_path.lower()
        match_lower = match_str.lower()

        # 1. Universal dummy indicators (applies to all files across the repo)
        if any(marker in secret_lower for marker in UNIVERSAL_DUMMY_MARKERS):
            return True

        # 2. Check if file resides in test, fixture, mock, sample, or documentation paths
        path_obj = Path(file_lower)
        parts = set(path_obj.parts)
        is_test_or_doc = (
            bool(parts & TEST_DOC_DIRS)
            or path_obj.name.startswith("test_")
            or path_obj.name.endswith(TEST_FILE_EXTENSIONS)
            or path_obj.name in TEST_FILE_NAMES
        )

        if is_test_or_doc:
            # If the secret explicitly claims to be a live secret (e.g. sk_live_...), do not auto-ignore
            if secret_lower.startswith(("sk_live_", "pk_live_", "ak_live_")):
                return False

            # In test/fixture context, filter out findings with dummy/test markers in secret or match line
            if any(marker in secret_lower for marker in TEST_CONTEXT_MARKERS):
                return True
            if any(marker in match_lower for marker in TEST_CONTEXT_MARKERS):
                return True

        return False

    async def scan_history(self, repo_path: Path) -> SecretLeakResult:
        """Runs gitleaks to detect hardcoded secrets in the entire Git history."""
        import asyncio
        
        def run_gitleaks():
            cmd = ["gitleaks", "detect", "--source", str(repo_path), "--report-format", "json", "--report-path", "/dev/stdout", "--exit-code", "0"]
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

        return SecretLeakResult(leaked_secrets=leaks, ignored_test_secrets=ignored)

