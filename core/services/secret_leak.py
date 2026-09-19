import json
import subprocess
import logging
from pathlib import Path
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LeakedSecret:
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
    leaked_secrets: List[LeakedSecret]

class SecretLeakScannerService:
    async def scan_history(self, repo_path: Path) -> SecretLeakResult:
        """Runs gitleaks to detect hardcoded secrets in the entire Git history."""
        import asyncio
        
        def run_gitleaks():
            # gitleaks detect --source <path> --report-format json --no-git if not a git repo, but we assume it is
            # We want json output to stdout, but gitleaks writes to file or stdout.
            # gitleaks detect --source . --report-format json --report-path /dev/stdout
            # Actually, `gitleaks detect` returns 1 if leaks are found.
            cmd = ["gitleaks", "detect", "--source", str(repo_path), "--report-format", "json", "--report-path", "/dev/stdout", "--exit-code", "0"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                # If no leaks, gitleaks might output empty array or info to stderr
                if not result.stdout.strip():
                    return []
                return json.loads(result.stdout)
            except Exception as e:
                logger.error(f"Failed to run gitleaks: {e}")
                return []

        raw_findings = await asyncio.to_thread(run_gitleaks)
        leaks = [LeakedSecret.from_gitleaks(f) for f in raw_findings]
        
        return SecretLeakResult(leaked_secrets=leaks)
