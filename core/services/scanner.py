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
