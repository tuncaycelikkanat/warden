"""AI-Generated / Vibe-Coding heuristic and semantic detection engine for WARDEN.

Analyzes codebase for markers commonly found in unreviewed LLM/Copilot generated code:
- Obvious / didactic commentary ("# Import necessary libraries", "# Function to...")
- LLM prompt residue and conversational markdown markers
- Over-defensive phantom fallbacks ("# Replace with your production API key")
- Generic swallowed exceptions and repetitive inline patterns
- Semantic AI Slop (TF-IDF + statistical classification)
- Leaked system prompts and prompt injection vulnerabilities
- Git code style drift across historical commits
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.ai_slop_classifier import AISlopClassifier
from core.services.evidence.base import safe_read_file
from core.services.prompt_leak_detector import PromptLeakDetector
from core.services.style_drift_detector import StyleDriftDetector

logger = logging.getLogger(__name__)

# Common AI commentary patterns
_AI_COMMENT_PATTERNS = [
    (re.compile(r"#\s*(import\s+(all\s+)?(necessary|required)\s+(modules|packages|libraries))", re.IGNORECASE), "Didactic import commentary", 3.0),
    (re.compile(r"#\s*(helper\s+function\s+to|function\s+to\s+\w+)", re.IGNORECASE), "Obvious function commentary", 2.0),
    (re.compile(r"#\s*(in\s+production,\s+(you\s+should|replace|use|implement))", re.IGNORECASE), "LLM production disclaimer comment", 4.0),
    (re.compile(r"#\s*(replace\s+(this\s+)?with\s+your\s+(actual\s+)?(api_?key|token|secret|url))", re.IGNORECASE), "Placeholder token commentary", 4.0),
    (re.compile(r"#\s*(note:\s*(this\s+is\s+a\s+(mock|simple|basic)|make\s+sure\s+to))", re.IGNORECASE), "LLM explanatory note", 3.0),
    (re.compile(r"#\s*(step\s+\d+:\s*\w+)", re.IGNORECASE), "Step-by-step procedural commentary", 2.0),
    (re.compile(r"```(?:python|json|bash)?", re.IGNORECASE), "Markdown codeblock residue in code", 5.0),
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
    semantic_slop_summary: dict[str, Any] | None = None
    prompt_leaks_summary: dict[str, Any] | None = None
    style_drift_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        if self.semantic_slop_summary is not None:
            data["semantic_slop"] = self.semantic_slop_summary
        if self.prompt_leaks_summary is not None:
            data["prompt_leaks"] = self.prompt_leaks_summary
        if self.style_drift_summary is not None:
            data["style_drift"] = self.style_drift_summary
        return data


class VibeCodingDetector:
    """Comprehensive engine scanning code for uncurated AI/vibe-coding patterns."""

    def __init__(
        self,
        include_drift: bool = True,
        slop_classifier: AISlopClassifier | None = None,
        prompt_detector: PromptLeakDetector | None = None,
        drift_detector: StyleDriftDetector | None = None,
    ) -> None:
        self.include_drift = include_drift
        self.slop_classifier = slop_classifier or AISlopClassifier()
        self.prompt_detector = prompt_detector or PromptLeakDetector()
        self.drift_detector = drift_detector or StyleDriftDetector()

    def analyze_file(self, file_path: Path, repo_root: Path) -> list[VibeFinding]:
        """Analyzes a single source file for AI/vibe markers across heuristic and semantic dimensions."""
        findings: list[VibeFinding] = []
        rel_path = str(file_path.relative_to(repo_root)) if repo_root in file_path.parents or file_path == repo_root else file_path.name
        content = safe_read_file(file_path)
        if not content:
            return findings

        lines = content.splitlines()

        # 1. Regex checks across lines
        matched_lines: set[int] = set()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            for pattern, rule, weight in _AI_COMMENT_PATTERNS:
                if pattern.search(stripped):
                    matched_lines.add(idx)
                    findings.append(
                        VibeFinding(
                            file=rel_path,
                            line=idx,
                            rule=rule,
                            snippet=stripped[:120],
                            weight=weight,
                        )
                    )

            # 2. Semantic Slop check on comments not already captured by static regex
            if stripped.startswith("#") and idx not in matched_lines:
                slop_res = self.slop_classifier.classify_text(stripped)
                if slop_res.label == "ai_slop" and slop_res.slop_score >= 50.0:
                    matched_lines.add(idx)
                    findings.append(
                        VibeFinding(
                            file=rel_path,
                            line=idx,
                            rule=f"Semantic AI Slop: {', '.join(slop_res.matched_markers[:2])}",
                            snippet=stripped[:120],
                            weight=3.0,
                        )
                    )

        # 3. Prompt Leak and Injection vectors
        leak_findings = self.prompt_detector.analyze_file(file_path, repo_root)
        for lf in leak_findings:
            if lf.line not in matched_lines:
                matched_lines.add(lf.line)
                weight = 4.5 if lf.severity in ("CRITICAL", "HIGH") else 3.0
                findings.append(
                    VibeFinding(
                        file=rel_path,
                        line=lf.line,
                        rule=f"Prompt Security [{lf.leak_type}]: {lf.description}",
                        snippet=lf.snippet,
                        weight=weight,
                    )
                )

        # 4. AST checks for Python files (swallowed exceptions)
        if file_path.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
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
        """Scans source files and Git history in the repository to compute an overall vibe-coding score."""
        repo_path = repo_path.resolve()
        if files is None:
            from core.utils.file_discovery import discover_source_files
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
                try:
                    flagged_files.add(str(f.relative_to(repo_path)))
                except ValueError:
                    flagged_files.add(f.name)

        total_files = len(target_files)
        if total_files == 0:
            return VibeDetectionResult(
                vibe_score=0.0,
                risk_level="LOW",
                total_files_analyzed=0,
                flagged_files_count=0,
                summary="No source files analyzed.",
            )

        # Style drift analysis across Git history
        drift_result = None
        drift_score_contribution = 0.0
        if self.include_drift:
            try:
                drift_result = self.drift_detector.analyze_repository_history(repo_path)
                if drift_result.drift_detected:
                    drift_score_contribution = drift_result.overall_drift_score * 0.15
            except Exception as err:
                logger.warning(f"Error executing style drift detection: {err}")

        # Compute weighted vibe score
        total_weight = sum(f.weight for f in all_findings)
        density = (total_weight / total_files) * 10.0
        combined_score = density + drift_score_contribution
        vibe_score = min(100.0, round(combined_score, 1))

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

        semantic_slop_count = sum(1 for f in all_findings if "Semantic AI Slop" in f.rule)
        prompt_leak_count = sum(1 for f in all_findings if "Prompt Security" in f.rule)

        return VibeDetectionResult(
            vibe_score=vibe_score,
            risk_level=risk_level,
            total_files_analyzed=total_files,
            flagged_files_count=len(flagged_files),
            findings=all_findings,
            summary=summary,
            semantic_slop_summary={
                "slop_findings_count": semantic_slop_count,
            },
            prompt_leaks_summary={
                "leak_findings_count": prompt_leak_count,
            },
            style_drift_summary=drift_result.to_dict() if drift_result else None,
        )
