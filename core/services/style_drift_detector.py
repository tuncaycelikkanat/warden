"""Code Style Drift Detector for WARDEN.

Analyzes Git commit history (up to last 50 commits) to detect abrupt changes
in programming idioms and architectural style, signaling sudden injection of
uncurated AI-generated code or disparate coding assistants:
- Comment density and commentary pattern shifts
- Docstring presence and depth
- Type annotation coverage
- Exception handling specificity (swallowed/generic vs specific exceptions)
- Identifier naming conventions (snake_case consistency, length distribution)
- AST control flow nesting and structural patterns

Computes multi-dimensional stylistic feature vectors and detects drift spikes
using cosine distance against historical baseline profiles.
"""

from __future__ import annotations

import ast
import logging
import math
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_COMMITS = 50
DRIFT_SPIKE_THRESHOLD = 25.0  # Percentage shift indicating an anomalous drift event


@dataclass
class StyleVector:
    """Stylistic and AST feature vector for a codebase state or commit diff."""

    comment_density: float = 0.0
    docstring_ratio: float = 0.0
    type_annotation_ratio: float = 0.0
    naming_snake_ratio: float = 1.0
    avg_identifier_length: float = 8.0
    exception_specificity: float = 1.0
    avg_nesting_depth: float = 1.0

    def to_list(self) -> list[float]:
        """Returns ordered normalized float values for distance computation."""
        return [
            min(1.0, self.comment_density),
            self.docstring_ratio,
            self.type_annotation_ratio,
            self.naming_snake_ratio,
            min(1.0, self.avg_identifier_length / 25.0),
            self.exception_specificity,
            min(1.0, self.avg_nesting_depth / 6.0),
        ]

    def to_dict(self) -> dict[str, float]:
        return {
            "comment_density": round(self.comment_density, 3),
            "docstring_ratio": round(self.docstring_ratio, 3),
            "type_annotation_ratio": round(self.type_annotation_ratio, 3),
            "naming_snake_ratio": round(self.naming_snake_ratio, 3),
            "avg_identifier_length": round(self.avg_identifier_length, 2),
            "exception_specificity": round(self.exception_specificity, 3),
            "avg_nesting_depth": round(self.avg_nesting_depth, 2),
        }


@dataclass
class DriftEvent:
    """Anomalous code style drift detected at a specific commit."""

    commit_hash: str
    author: str
    date: str
    message: str
    drift_score: float  # 0.0 to 100.0
    feature_shifts: dict[str, float] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_hash": self.commit_hash[:10],
            "author": self.author,
            "date": self.date,
            "message": self.message[:80],
            "drift_score": round(self.drift_score, 1),
            "feature_shifts": {k: round(v, 3) for k, v in self.feature_shifts.items()},
            "description": self.description,
        }


@dataclass
class StyleDriftResult:
    """Aggregated style drift analysis across repository commits."""

    analyzed_commits: int
    drift_detected: bool
    overall_drift_score: float  # 0.0 to 100.0
    risk_level: str  # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"
    baseline_metrics: dict[str, float] = field(default_factory=dict)
    drift_events: list[DriftEvent] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyzed_commits": self.analyzed_commits,
            "drift_detected": self.drift_detected,
            "overall_drift_score": round(self.overall_drift_score, 1),
            "risk_level": self.risk_level,
            "baseline_metrics": self.baseline_metrics,
            "drift_events_count": len(self.drift_events),
            "drift_events": [e.to_dict() for e in self.drift_events[:20]],
            "summary": self.summary,
        }


class StyleDriftDetector:
    """Extracts style metrics across Git commits and detects abrupt style drift."""

    def __init__(self, max_commits: int = DEFAULT_MAX_COMMITS) -> None:
        self.max_commits = max_commits

    def compute_style_vector_from_ast(self, code: str) -> StyleVector:
        """Extracts AST and stylistic features from Python source code."""
        if not code.strip():
            return StyleVector()

        dedented_code = textwrap.dedent(code)
        lines = dedented_code.splitlines()
        code_lines = 0
        comment_lines = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                comment_lines += 1
            else:
                code_lines += 1
                if "#" in stripped:
                    comment_lines += 1

        comment_density = comment_lines / max(1, code_lines)

        tree = None
        try:
            tree = ast.parse(dedented_code)
        except SyntaxError:
            # Attempt wrapping in dummy function for snippet lines (e.g. diff hunks)
            try:
                indented = textwrap.indent(dedented_code, "    ")
                tree = ast.parse(f"def _snippet_wrapper():\n{indented}")
            except SyntaxError:
                return StyleVector(comment_density=comment_density)

        functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        # Filter out dummy wrapper if added
        functions = [f for f in functions if f.name != "_snippet_wrapper"]
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]

        # Docstring ratio (exclude dunders like __init__ unless explicitly documented)
        target_funcs = [
            f for f in functions
            if not (f.name.startswith("__") and f.name.endswith("__")) or ast.get_docstring(f)
        ]
        if not target_funcs and functions:
            target_funcs = functions

        documented = sum(1 for f in target_funcs if ast.get_docstring(f))
        docstring_ratio = (documented / max(1, len(target_funcs))) if target_funcs else 0.0

        # Type annotation ratio
        total_args_returns = 0
        annotated_args_returns = 0
        for f in functions:
            # return annotation
            total_args_returns += 1
            if f.returns is not None:
                annotated_args_returns += 1
            # argument annotations
            for arg in f.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                total_args_returns += 1
                if arg.annotation is not None:
                    annotated_args_returns += 1

        type_ratio = annotated_args_returns / max(1, total_args_returns)

        # Naming conventions & identifier length
        func_names = [f.name for f in functions if not (f.name.startswith("__") and f.name.endswith("__"))]
        var_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                var_names.append(node.id)

        target_snake_names = func_names + var_names
        snake_case_count = sum(1 for n in target_snake_names if "_" in n or n.islower())
        naming_snake_ratio = (snake_case_count / max(1, len(target_snake_names))) if target_snake_names else 1.0

        all_names = [f.name for f in functions] + [c.name for c in classes] + var_names
        avg_id_len = sum(len(n) for n in all_names) / max(1, len(all_names)) if all_names else 8.0

        # Exception specificity
        except_handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]
        specific_excepts = 0
        for h in except_handlers:
            if h.type is not None:
                if isinstance(h.type, ast.Name) and h.type.id in ("Exception", "BaseException"):
                    continue
                specific_excepts += 1
        exception_specificity = specific_excepts / max(1, len(except_handlers))

        # Nesting depth calculation
        depths: list[int] = []

        def _calc_depth(node: ast.AST, cur_depth: int) -> None:
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                cur_depth += 1
                depths.append(cur_depth)
            for child in ast.iter_child_nodes(node):
                _calc_depth(child, cur_depth)

        _calc_depth(tree, 0)
        avg_depth = (sum(depths) / max(1, len(depths))) if depths else 1.0

        return StyleVector(
            comment_density=round(comment_density, 3),
            docstring_ratio=round(docstring_ratio, 3),
            type_annotation_ratio=round(type_ratio, 3),
            naming_snake_ratio=round(naming_snake_ratio, 3),
            avg_identifier_length=round(avg_id_len, 2),
            exception_specificity=round(exception_specificity, 3),
            avg_nesting_depth=round(avg_depth, 2),
        )

    def calculate_vector_distance(self, vec_a: StyleVector, vec_b: StyleVector) -> float:
        """Calculates normalized cosine distance (0.0 to 100.0) between two style vectors."""
        a = vec_a.to_list()
        b = vec_b.to_list()

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        cosine_sim = dot / (norm_a * norm_b)
        cosine_sim = max(-1.0, min(1.0, cosine_sim))
        distance = (1.0 - cosine_sim) * 100.0
        return min(100.0, max(0.0, distance))

    def _get_commit_history(self, repo_path: Path) -> list[dict[str, str]]:
        """Retrieves commit metadata from Git log."""
        git_bin = shutil.which("git")
        if not git_bin:
            return []

        cmd = [
            git_bin,
            "log",
            "--no-merges",
            f"-n{self.max_commits}",
            "--pretty=format:%H|%an|%ad|%s",
            "--date=short",
        ]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if res.returncode != 0:
                return []
        except Exception as err:
            logger.warning(f"Error fetching git log: {err}")
            return []

        commits = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3],
                })
        return commits

    def _get_commit_diff(self, repo_path: Path, commit_hash: str) -> str:
        """Retrieves Python file diff for a given commit."""
        git_bin = shutil.which("git")
        if not git_bin:
            return ""

        cmd = [git_bin, "show", commit_hash, "--", "*.py"]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if res.returncode == 0:
                return res.stdout
        except Exception as err:
            logger.warning(f"Error getting commit diff for {commit_hash}: {err}")
        return ""

    def analyze_repository_history(self, repo_path: Path) -> StyleDriftResult:
        """Analyzes Git history for style drift across consecutive commits."""
        repo_path = repo_path.resolve()
        commits = self._get_commit_history(repo_path)

        if len(commits) < 2:
            return StyleDriftResult(
                analyzed_commits=len(commits),
                drift_detected=False,
                overall_drift_score=0.0,
                risk_level="LOW",
                summary="Insufficient commit history to assess style drift (less than 2 commits).",
            )

        # Process commits in chronological order (oldest to newest)
        chronological_commits = list(reversed(commits))
        commit_vectors: list[tuple[dict[str, str], StyleVector]] = []

        for c in chronological_commits:
            diff_text = self._get_commit_diff(repo_path, c["hash"])
            # Extract added/modified lines from diff
            added_lines = [
                line[1:] for line in diff_text.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            ]
            added_code = "\n".join(added_lines)
            if len(added_lines) >= 5:
                vec = self.compute_style_vector_from_ast(added_code)
                commit_vectors.append((c, vec))

        if len(commit_vectors) < 2:
            return StyleDriftResult(
                analyzed_commits=len(commits),
                drift_detected=False,
                overall_drift_score=0.0,
                risk_level="LOW",
                summary=f"Analyzed {len(commits)} commits, but fewer than 2 contained significant Python additions.",
            )

        # Baseline: average of the first 3 commits (or first half)
        baseline_sample_size = max(1, min(5, len(commit_vectors) // 2))
        baseline_lists = [v.to_list() for _, v in commit_vectors[:baseline_sample_size]]
        avg_baseline = [
            sum(vals) / len(vals) for vals in zip(*baseline_lists)
        ]
        baseline_vec = StyleVector(
            comment_density=avg_baseline[0],
            docstring_ratio=avg_baseline[1],
            type_annotation_ratio=avg_baseline[2],
            naming_snake_ratio=avg_baseline[3],
            avg_identifier_length=avg_baseline[4] * 25.0,
            exception_specificity=avg_baseline[5],
            avg_nesting_depth=avg_baseline[6] * 6.0,
        )

        drift_events: list[DriftEvent] = []
        drift_scores: list[float] = []

        for c, vec in commit_vectors[baseline_sample_size:]:
            dist = self.calculate_vector_distance(baseline_vec, vec)
            drift_scores.append(dist)

            if dist >= DRIFT_SPIKE_THRESHOLD:
                # Compute which specific dimensions shifted the most
                v_curr = vec.to_dict()
                v_base = baseline_vec.to_dict()
                shifts = {
                    k: round(v_curr[k] - v_base[k], 3)
                    for k in v_curr
                }
                # Find prominent shift
                sorted_shifts = sorted(shifts.items(), key=lambda x: abs(x[1]), reverse=True)
                top_shift_desc = ", ".join(f"{k}: {v:+.2f}" for k, v in sorted_shifts[:2])

                drift_events.append(
                    DriftEvent(
                        commit_hash=c["hash"],
                        author=c["author"],
                        date=c["date"],
                        message=c["message"],
                        drift_score=dist,
                        feature_shifts=shifts,
                        description=f"Significant stylistic divergence detected ({top_shift_desc})",
                    )
                )

        avg_drift = sum(drift_scores) / max(1, len(drift_scores)) if drift_scores else 0.0
        max_drift = max(drift_scores) if drift_scores else 0.0
        overall_drift_score = min(100.0, round((avg_drift * 0.4) + (max_drift * 0.6), 1))

        if overall_drift_score >= 60.0:
            risk_level = "CRITICAL"
        elif overall_drift_score >= 40.0:
            risk_level = "HIGH"
        elif overall_drift_score >= 20.0:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"

        drift_detected = len(drift_events) > 0 or overall_drift_score >= 30.0

        summary = (
            f"Kod Stili Drift Skoru: %{overall_drift_score} ({risk_level}). "
            f"{len(commits)} commit incelendi, {len(drift_events)} belirgin stil kırılması (spike) tespit edildi."
        )

        return StyleDriftResult(
            analyzed_commits=len(commits),
            drift_detected=drift_detected,
            overall_drift_score=overall_drift_score,
            risk_level=risk_level,
            baseline_metrics=baseline_vec.to_dict(),
            drift_events=drift_events,
            summary=summary,
        )
