import re
from typing import Dict, Any, List

class AgentActionMonitor:
    def __init__(self):
        # Define dangerous command patterns
        self.dangerous_patterns = [
            (r"curl\s+.*?\|\s*bash", "Direct execution of remote scripts via curl | bash"),
            (r"wget\s+.*?\|\s*bash", "Direct execution of remote scripts via wget | bash"),
            (r"rm\s+-r[fF]?\s+(/|/\*|~|~\*)", "Destructive deletion of root or home directory"),
            (r"chmod\s+(777|a\+rwx)", "Setting overly permissive file permissions (777)"),
            (r">\s*/dev/sda", "Direct writing to block devices"),
            (r"mkfs", "Formatting filesystems")
        ]
        
    def evaluate_action(self, command: str) -> Dict[str, Any]:
        """
        Evaluates a shell command against known dangerous patterns.
        Returns a dict indicating if confirmation is required and the reason.
        """
        reasons = []
        requires_confirmation = False
        
        for pattern, reason in self.dangerous_patterns:
            if re.search(pattern, command):
                requires_confirmation = True
                reasons.append(reason)
                
        return {
            "requires_confirmation": requires_confirmation,
            "reasons": reasons,
            "command": command
        }
