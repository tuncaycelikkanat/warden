"""Security scanner service utilizing Semgrep rules for SAST code analysis."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SecurityScannerService:
    """Performs static application security testing using Semgrep and custom rules."""

    def __init__(self, rule_dirs: list[str] | str | None = None) -> None:
        """Initializes scanner with custom Semgrep rule directory path(s)."""
        base_rules_dir = Path(__file__).resolve().parent.parent / "rules"
        if rule_dirs is None:
            vibe_dir = str(base_rules_dir / "vibe_coding")
            sec_dir = str(base_rules_dir / "security_core")
            self.rule_dirs = [vibe_dir, sec_dir] if Path(vibe_dir).exists() else [str(base_rules_dir)]
        elif isinstance(rule_dirs, str):
            self.rule_dirs = [rule_dirs]
        else:
            self.rule_dirs = rule_dirs

    @property
    def rule_dir(self) -> str:
        """Backwards compatibility for single rule dir accessor."""
        return self.rule_dirs[0] if self.rule_dirs else "core/rules"

    def scan_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Runs semgrep on the specified file using the configured rules directory.
        Returns a list of findings.
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        command = ["semgrep"]
        for rd in self.rule_dirs:
            command.extend(["--config", rd])
        command.extend(["--json", file_path])

        
        try:
            # Semgrep returns exit code 1 if it finds issues, so we don't use check=True
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            
            if not result.stdout.strip():
                logger.error(f"Semgrep failed with stderr: {result.stderr}")
                return []
                
            parsed_output = json.loads(result.stdout)
            return parsed_output.get("results", [])
            
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run semgrep: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse semgrep output: {e}")
            return []

    async def scan_files(self, file_paths: list[Path]) -> list[dict[str, Any]]:
        """
        Runs semgrep on multiple files in parallel.
        """
        import asyncio
        
        # Helper to run scan_file in a thread to avoid blocking the event loop
        def scan_sync(path):
            return self.scan_file(str(path))
            
        # Run all scans concurrently
        tasks = [asyncio.to_thread(scan_sync, p) for p in file_paths]
        results = await asyncio.gather(*tasks)
        
        # Flatten the list of findings
        all_findings = []
        for result in results:
            all_findings.extend(result)
            
        return all_findings

    def calculate_risk_level(self, findings: list[dict[str, Any]]) -> str:
        """
        Calculates risk level (high, medium, low) based on Semgrep findings.
        """
        if not findings:
            return "low"
            
        severity_levels = [f.get("extra", {}).get("severity", "INFO") for f in findings]
        
        if "ERROR" in severity_levels:
            return "high"
        elif "WARNING" in severity_levels:
            return "medium"
            
        return "low"
