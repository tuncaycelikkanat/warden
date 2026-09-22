"""AI-Generated / Vibe-Coding heuristic detection service for WARDEN.

Analyzes codebase for markers commonly found in unreviewed LLM/Copilot generated code:
- Obvious / didactic commentary ("# Import necessary libraries", "# Function to...")
- LLM prompt residue and conversational markdown markers
- Over-defensive phantom fallbacks ("# Replace with your production API key")
- Generic swallowed exceptions and repetitive inline patterns
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.evidence.base import safe_read_file

logger = logging.getLogger(__name__)

# Common AI commentary patterns
_AI_COMMENT_PATTERNS = [
    (re.compile(r"#\s*(import\s+(all\s+)?(necessary|required)\s+(modules|packages|libraries))", re.I), "Didactic import commentary", 3.0),
    (re.compile(r"#\s*(helper\s+function\s+to|function\s+to\s+\w+)", re.I), "Obvious function commentary", 2.0),
    (re.compile(r"#\s*(in\s+production,\s+(you\s+should|replace|use|implement))", re.I), "LLM production disclaimer comment", 4.0),
    (re.compile(r"#\s*(replace\s+(this\s+)?with\s+your\s+(actual\s+)?(api_?key|token|secret|url))", re.I), "Placeholder token commentary", 4.0),
    (re.compile(r"#\s*(note:\s*(this\s+is\s+a\s+(mock|simple|basic)|make\s+sure\s+to))", re.I), "LLM explanatory note", 3.0),
    (re.compile(r"#\s*(step\s+\d+:\s*\w+)", re.I), "Step-by-step procedural commentary", 2.0),
    (re.compile(r"```(?:python|json|bash)?", re.I), "Markdown codeblock residue in code", 5.0),
]


@dataclass
class VibeFinding:
    """A detected vibe-coding indicator in a source file."""
    file: str
    line: int
    rule: str
    snippet: str
    weight: float


@dataclass
class VibeDetectionResult:
    """Aggregated vibe-coding / AI-generated code detection report."""
    vibe_score: float  # 0.0 (handcrafted) to 100.0 (heavy vibe-coded)
    risk_level: str    # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"
    total_files_analyzed: int
    flagged_files_count: int
    findings: list[VibeFinding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "vibe_score": round(self.vibe_score, 1),
            "risk_level": self.risk_level,
            "total_files_analyzed": self.total_files_analyzed,
            "flagged_files_count": self.flagged_files_count,
            "findings_count": len(self.findings),
            "summary": self.summary,
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "rule": f.rule,
                    "snippet": f.snippet,
                    "weight": f.weight,
                }
                for f in self.findings[:50]  # Cap top 50 in summary
            ],
        }


class VibeCodingDetector:
    """Scans code files for markers of uncurated AI/vibe-coding patterns."""

    def analyze_file(self, file_path: Path, repo_root: Path) -> list[VibeFinding]:
        """Analyzes a single source file for AI/vibe markers."""
        findings: list[VibeFinding] = []
        rel_path = str(file_path.relative_to(repo_root))
        content = safe_read_file(file_path)
        if not content:
            return findings

        lines = content.splitlines()

        # 1. Regex checks across lines
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            for pattern, rule, weight in _AI_COMMENT_PATTERNS:
                if pattern.search(stripped):
                    findings.append(
                        VibeFinding(
                            file=rel_path,
                            line=idx,
                            rule=rule,
                            snippet=stripped[:120],
                            weight=weight,
                        )
                    )

        # 2. AST checks for Python files
        if file_path.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    # Check for generic exception swallowing: except Exception: pass / print
                    if isinstance(node, ast.ExceptHandler):
                        if node.type is None or (isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")):
                            is_swallowed = False
                            if len(node.body) == 1:
                                stmt = node.body[0]
                                if isinstance(stmt, ast.Pass):
                                    is_swallowed = True
                                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                                    func = stmt.value.func
                                    if isinstance(func, ast.Name) and func.id == "print":
                                        is_swallowed = True

                            if is_swallowed:
                                findings.append(
                                    VibeFinding(
                                        file=rel_path,
                                        line=getattr(node, "lineno", 1),
                                        rule="Generic exception swallowed (except Exception: pass/print)",
                                        snippet=lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else "except Exception:",
                                        weight=3.5,
                                    )
                                )
            except SyntaxError:
                pass

        return findings

    def analyze_repository(self, repo_path: Path, files: list[Path] | None = None) -> VibeDetectionResult:
        """Scans all source files in the repository and computes a vibe-coding score."""
        repo_path = repo_path.resolve()
        if files is None:
            from core.services.orchestrator import discover_source_files
            target_files = discover_source_files(repo_path)
        else:
            target_files = files

        all_findings: list[VibeFinding] = []
        flagged_files: set[str] = set()

        for f in target_files:
            if not f.is_file():
                continue
            findings = self.analyze_file(f, repo_path)
            if findings:
                all_findings.extend(findings)
                flagged_files.add(str(f.relative_to(repo_path)))

        total_files = len(target_files)
        if total_files == 0:
            return VibeDetectionResult(
                vibe_score=0.0,
                risk_level="LOW",
                total_files_analyzed=0,
                flagged_files_count=0,
                summary="No source files analyzed.",
            )

        # Compute weighted vibe score
        total_weight = sum(f.weight for f in all_findings)
        # Normalize by codebase size (findings per file density)
        density = (total_weight / total_files) * 10.0
        vibe_score = min(100.0, round(density, 1))

        if vibe_score >= 60.0:
            risk_level = "CRITICAL"
        elif vibe_score >= 40.0:
            risk_level = "HIGH"
        elif vibe_score >= 20.0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        summary = (
            f"Vibe-Coding Oranı: %{vibe_score} ({risk_level}). "
            f"{total_files} dosyanın {len(flagged_files)} tanesinde toplam "
            f"{len(all_findings)} AI/vibe göstergesi tespit edildi."
        )

        return VibeDetectionResult(
            vibe_score=vibe_score,
            risk_level=risk_level,
            total_files_analyzed=total_files,
            flagged_files_count=len(flagged_files),
            findings=all_findings,
            summary=summary,
        )
