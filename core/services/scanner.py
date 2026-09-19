import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class SecurityScannerService:
    def __init__(self, rule_dir: str = "core/rules/vibe_coding"):
        self.rule_dir = rule_dir

    def scan_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Runs semgrep on the specified file using the configured rules directory.
        Returns a list of findings.
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        command = [
            "semgrep",
            "--config", self.rule_dir,
            "--json",
            file_path
        ]
        
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

    async def scan_files(self, file_paths: List[Path]) -> List[Dict[str, Any]]:
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

    def calculate_risk_level(self, findings: List[Dict[str, Any]]) -> str:
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
