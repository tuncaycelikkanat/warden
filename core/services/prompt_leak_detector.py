"""Prompt Injection & Leaked System Prompt Detector for WARDEN.

Scans codebase and configuration files for:
- Leaked or hardcoded LLM system prompts and instructions
- Prompt injection vulnerabilities in prompt templates (unfiltered concatenation)
- Jailbreak markers, evasion techniques, and ChatML/special token residues
- Optional hybrid verification using configured LLM providers
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.evidence.base import safe_read_file

logger = logging.getLogger(__name__)

# Patterns for hardcoded system prompts and role instructions
SYSTEM_PROMPT_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"you\s+are\s+(a|an)?\s*(helpful|expert|senior|autonomous|friendly)?\s*(ai|assistant|model|bot|agent)", re.I),
        "SYSTEM_PROMPT_LEAK",
        "HIGH",
        "Hardcoded LLM assistant role assignment detected.",
    ),
    (
        re.compile(r"(strictly\s+adhere\s+to|must\s+follow)\s+(the\s+following\s+)?(rules|instructions|guidelines)", re.I),
        "SYSTEM_PROMPT_LEAK",
        "MEDIUM",
        "Hardcoded imperative LLM system instruction directive detected.",
    ),
    (
        re.compile(r"(never|do\s+not)\s+reveal\s+(your\s+)?(system\s+prompt|instructions|initial\s+prompt)", re.I),
        "SYSTEM_PROMPT_LEAK",
        "HIGH",
        "Prompt leak defense instruction exposed in source code.",
    ),
    (
        re.compile(r"(respond|output)\s+only\s+in\s+(valid\s+)?(json|xml|yaml|markdown)", re.I),
        "SYSTEM_PROMPT_LEAK",
        "LOW",
        "Strict output formatting constraint characteristic of LLM system prompts.",
    ),
    (
        re.compile(r"<\|im_start\|>system|<<SYS>>|<system_prompt>|\[SYSTEM_PROMPT\]", re.I),
        "SPECIAL_TOKEN_RESIDUE",
        "CRITICAL",
        "Raw ChatML/LLM system token residue detected in source code.",
    ),
]

# Patterns for prompt injection risks and jailbreak traces
INJECTION_RISK_PATTERNS: list[tuple[re.Pattern[str], str, str, str]] = [
    (
        re.compile(r"ignore\s+(all\s+)?(previous|past|prior)\s+(instructions|prompts|directives)", re.I),
        "JAILBREAK_RESIDUE",
        "CRITICAL",
        "Classic 'Ignore previous instructions' jailbreak payload trace detected.",
    ),
    (
        re.compile(r"(dan\s+mode|do\s+anything\s+now|jailbreak\s+mode|developer\s+mode\s+enabled)", re.I),
        "JAILBREAK_RESIDUE",
        "CRITICAL",
        "Known jailbreak persona pattern detected.",
    ),
    (
        re.compile(r"f[\"'].*?(system|prompt|instruction).*?\{[a-zA-Z0-9_]*(user|input|query|prompt|req)[a-zA-Z0-9_]*\}", re.I),
        "PROMPT_INJECTION_VULNERABILITY",
        "HIGH",
        "Direct f-string interpolation of untrusted user input into LLM prompt template without sanitization boundary.",
    ),
    (
        re.compile(r"[\"'].*?(system|instructions?:).*?[\"']\s*\+\s*[a-zA-Z0-9_]*(user|input|query)", re.I),
        "PROMPT_INJECTION_VULNERABILITY",
        "HIGH",
        "Direct string concatenation of user input into system prompt instruction context.",
    ),
]


@dataclass
class PromptLeakFinding:
    """A detected prompt leak or prompt injection vulnerability."""

    file: str
    line: int
    leak_type: str  # "SYSTEM_PROMPT_LEAK" | "PROMPT_INJECTION_VULNERABILITY" | "JAILBREAK_RESIDUE" | "SPECIAL_TOKEN_RESIDUE"
    severity: str   # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    snippet: str
    description: str
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "leak_type": self.leak_type,
            "severity": self.severity,
            "snippet": self.snippet,
            "description": self.description,
            "remediation": self.remediation,
        }


@dataclass
class PromptLeakResult:
    """Aggregated prompt leak and injection scan report."""

    total_files_scanned: int
    leaks_count: int
    critical_count: int
    findings: list[PromptLeakFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files_scanned": self.total_files_scanned,
            "leaks_count": self.leaks_count,
            "critical_count": self.critical_count,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings[:50]],
        }


class PromptLeakDetector:
    """Scans codebases for hardcoded system prompts, prompt leaks, and injection vectors."""

    def __init__(self, llm_provider: Any = None) -> None:
        self.llm_provider = llm_provider

    def analyze_file(self, file_path: Path, repo_root: Path) -> list[PromptLeakFinding]:
        """Analyzes a single file for prompt leak and injection indicators."""
        findings: list[PromptLeakFinding] = []
        rel_path = str(file_path.relative_to(repo_root)) if repo_root in file_path.parents or file_path == repo_root else file_path.name
        content = safe_read_file(file_path)
        if not content:
            return findings

        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            # 1. System Prompt Leak Checks
            for pat, leak_type, severity, desc in SYSTEM_PROMPT_PATTERNS:
                if pat.search(stripped):
                    remediation = (
                        "Externalize system prompts to environment variables or dedicated encrypted config. "
                        "Avoid hardcoding proprietary assistant prompts in client or open repositories."
                    )
                    findings.append(
                        PromptLeakFinding(
                            file=rel_path,
                            line=idx,
                            leak_type=leak_type,
                            severity=severity,
                            snippet=stripped[:120],
                            description=desc,
                            remediation=remediation,
                        )
                    )

            # 2. Prompt Injection Risk Checks
            for pat, leak_type, severity, desc in INJECTION_RISK_PATTERNS:
                if pat.search(stripped):
                    remediation = (
                        "Use parameterized prompts, XML delimiter tags (<user_input>...</user_input>), "
                        "and input sanitization to isolate untrusted user data from system instructions."
                    )
                    findings.append(
                        PromptLeakFinding(
                            file=rel_path,
                            line=idx,
                            leak_type=leak_type,
                            severity=severity,
                            snippet=stripped[:120],
                            description=desc,
                            remediation=remediation,
                        )
                    )

        return findings

    async def verify_finding_with_llm(self, finding: PromptLeakFinding) -> bool:
        """Optionally verifies ambiguous findings with LLM provider if available."""
        if not self.llm_provider:
            return True

        prompt = (
            f"Analyze the following code snippet and confirm if it represents a prompt leak, "
            f"hardcoded system prompt, or prompt injection vulnerability.\n\n"
            f"File: {finding.file}:{finding.line}\n"
            f"Snippet: {finding.snippet}\n"
            f"Suspected Type: {finding.leak_type}\n\n"
            f"Respond with a JSON object containing: 'confirmed': boolean, 'reason': string."
        )

        try:
            res = await self.llm_provider.generate(prompt)
            if res and isinstance(res, dict) and "confirmed" in res:
                return bool(res["confirmed"])
        except Exception as err:
            logger.warning(f"Error during LLM hybrid verification: {err}")

        return True

    def scan_repository(self, repo_path: Path, files: list[Path] | None = None) -> PromptLeakResult:
        """Scans specified files or all source files in repository for prompt leak vulnerabilities."""
        repo_path = repo_path.resolve()
        if files is None:
            from core.services.orchestrator import discover_source_files
            target_files = discover_source_files(repo_path)
        else:
            target_files = files

        all_findings: list[PromptLeakFinding] = []
        for f in target_files:
            if not f.is_file():
                continue
            findings = self.analyze_file(f, repo_path)
            all_findings.extend(findings)

        critical_count = sum(1 for f in all_findings if f.severity in ("CRITICAL", "HIGH"))

        summary = (
            f"Prompt Güvenlik Taraması: {len(target_files)} dosya incelendi. "
            f"{len(all_findings)} potansiyel prompt sızıntısı/açığı tespit edildi ({critical_count} kritik/yüksek riskli)."
        )

        return PromptLeakResult(
            total_files_scanned=len(target_files),
            leaks_count=len(all_findings),
            critical_count=critical_count,
            findings=all_findings,
            summary=summary,
        )
