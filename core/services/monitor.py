"""Monitor service for evaluating agent actions and commands against security policies."""

import re
from typing import Any


# Tehlikeli komut kategorileri ve desenleri
# Her tuple: (regex_pattern, human_readable_reason, severity)
_DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    # ── Remote code execution ─────────────────────────────────────────────────
    (r"curl\s+.*?\|\s*(bash|sh|python3?)", "Direct execution of remote scripts via curl | bash", "CRITICAL"),
    (r"wget\s+.*?\|\s*(bash|sh|python3?)", "Direct execution of remote scripts via wget | bash", "CRITICAL"),
    (r"curl\s+.*?-O\s+.*&&\s*(bash|sh|chmod)", "Remote binary download + execution", "CRITICAL"),

    # ── Destructive filesystem ops ─────────────────────────────────────────────
    (r"rm\s+-r[fF]?\s+(/|/\*|~|~\*|/home|/root|/etc|/var)", "Destructive deletion of critical directory", "CRITICAL"),
    (r"\brm\b.*--no-preserve-root", "Forced root filesystem deletion", "CRITICAL"),
    (r"mkfs\b", "Formatting filesystems", "CRITICAL"),
    (r">\s*/dev/sd[a-z]", "Direct write to block device", "CRITICAL"),
    (r"dd\s+if=.*of=/dev/sd[a-z]", "Raw disk write via dd", "CRITICAL"),

    # ── Overly permissive file permissions ────────────────────────────────────
    (r"chmod\s+(777|a\+rwx|0777)", "Setting globally writable permissions (777)", "HIGH"),
    (r"chown\s+.*:.*\s+/", "Changing ownership of root filesystem", "HIGH"),

    # ── Credential / secret exfiltration ──────────────────────────────────────
    (r"cat\s+(~/.ssh/id_rsa|~/.ssh/id_ed25519|~/.aws/credentials|~/.aws/config)", "Reading SSH/AWS credential files", "HIGH"),
    (r"env\b.*\|\s*(grep|cut|awk).*\b(TOKEN|SECRET|KEY|PASSWORD|API_KEY)\b", "Environment variable exfiltration", "HIGH"),
    (r"printenv\b.*\b(TOKEN|SECRET|KEY|PASSWORD)\b", "Environment secret dump", "HIGH"),

    # ── Destructive SQL ────────────────────────────────────────────────────────
    (r"DROP\s+(TABLE|DATABASE|SCHEMA)\b", "Destructive SQL DDL operation", "HIGH"),
    (r"TRUNCATE\s+TABLE\b", "Table truncation (all data deleted)", "MEDIUM"),

    # ── Dangerous git ops ──────────────────────────────────────────────────────
    (r"git\s+push\s+.*--force(?!-with-lease)", "Force push without lease (history rewrite)", "MEDIUM"),
    (r"git\s+reset\s+--hard\s+HEAD", "Hard git reset (local changes destroyed)", "MEDIUM"),

    # ── Privilege escalation ──────────────────────────────────────────────────
    (r"\bsudo\s+su\b|\bsudo\s+-s\b|\bsudo\s+bash\b", "Root shell escalation via sudo", "HIGH"),

    # ── Container / sandbox escape ─────────────────────────────────────────────
    (r"docker\s+run\s+.*--privileged", "Privileged Docker container (potential sandbox escape)", "HIGH"),
    (r"docker\s+run\s+.*-v\s+/:/", "Docker container with full host filesystem mount", "CRITICAL"),

    # ── Network exfiltration ───────────────────────────────────────────────────
    (r"nc\s+.*-e\s+(/bin/bash|/bin/sh)", "Reverse shell via netcat", "CRITICAL"),
    (r"\bpython\b.*socket.*connect\b.*exec", "Python reverse shell pattern", "CRITICAL"),
]


class AgentActionMonitor:
    """Evaluates agent CLI actions against security policies and dangerous shell patterns.

    Uses a multi-severity pattern library to detect potentially dangerous commands
    before they are executed. Designed to be used as a pre-execution guard in
    agentic workflows (e.g., via the MCP server's evaluate_agent_action tool).
    """

    def __init__(self) -> None:
        """Compiles regex patterns for efficient repeated evaluation."""
        self._compiled: list[tuple[re.Pattern[str], str, str]] = [
            (re.compile(pattern, re.IGNORECASE), reason, severity)
            for pattern, reason, severity in _DANGEROUS_PATTERNS
        ]

    def evaluate_action(self, command: str) -> dict[str, Any]:
        """Evaluates a shell command against known dangerous patterns.

        Args:
            command: Raw shell command string to evaluate.

        Returns:
            Dict with keys:
                - requires_confirmation (bool): True if any pattern matched
                - reasons (list[str]): Human-readable reasons for each match
                - severity (str): Highest matched severity ("CRITICAL" | "HIGH" | "MEDIUM" | "LOW")
                - command (str): The original command (for logging)
                - matched_patterns (int): Number of patterns matched
        """
        reasons: list[str] = []
        severities: list[str] = []

        for compiled_re, reason, severity in self._compiled:
            if compiled_re.search(command):
                reasons.append(reason)
                severities.append(severity)

        # Highest severity wins
        severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        top_severity = next(
            (s for s in severity_order if s in severities), "NONE"
        )

        return {
            "requires_confirmation": bool(reasons),
            "reasons": reasons,
            "severity": top_severity,
            "command": command,
            "matched_patterns": len(reasons),
        }
