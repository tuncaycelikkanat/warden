"""Architecture-as-Code Layer Boundary Enforcer for WARDEN.

Prevents architectural erosion caused by AI vibe-coding (e.g., API routes
directly importing database engines or CLI modules importing HTTP frameworks)
by enforcing declarative import boundary rules from `warden.config.yaml`.
"""

from __future__ import annotations

import ast
import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.evidence.base import safe_read_file
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)


@dataclass
class BoundaryRule:
    """Declarative architectural boundary rule."""

    source: str
    forbid_imports: list[str]
    reason: str = "Architectural layer boundary violation."


@dataclass
class BoundaryViolation:
    """A detected violation of an architectural boundary rule."""

    file: str
    line: int
    source_pattern: str
    forbidden_import: str
    actual_import: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "source_pattern": self.source_pattern,
            "forbidden_import": self.forbidden_import,
            "actual_import": self.actual_import,
            "reason": self.reason,
        }


@dataclass
class BoundaryCheckResult:
    """Result of evaluating architectural boundary rules across a repository."""

    passed: bool
    score: float
    files_checked: int
    rules_evaluated: int
    violations: list[BoundaryViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": round(self.score, 1),
            "files_checked": self.files_checked,
            "rules_evaluated": self.rules_evaluated,
            "violations_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
        }


DEFAULT_BOUNDARY_RULES: list[BoundaryRule] = [
    BoundaryRule(
        source="core/api/**",
        forbid_imports=["sqlite3"],
        reason="API katmanı doğrudan raw sqlite3 sorgusu çalıştıramaz; servis katmanını kullanın.",
    ),
    BoundaryRule(
        source="core/cli/**",
        forbid_imports=["fastapi"],
        reason="CLI katmanı FastAPI HTTP nesnelerine doğrudan bağımlı olmamalıdır.",
    ),
]


class ArchitectureBoundaryEnforcer:
    """Evaluates Python AST imports against declarative layer boundary contracts."""

    def __init__(self, rules: list[BoundaryRule] | None = None) -> None:
        self.custom_rules = rules

    def load_rules(self, repo_path: Path) -> list[BoundaryRule]:
        """Loads `architecture_boundaries` from `warden.config.yaml` or falls back to defaults."""
        if self.custom_rules is not None:
            return self.custom_rules

        config_path = repo_path / "warden.config.yaml"
        if config_path.exists():
            try:
                import yaml

                raw = yaml.safe_load(safe_read_file(config_path)) or {}
                cfg_rules = raw.get("architecture_boundaries", [])
                if isinstance(cfg_rules, list) and cfg_rules:
                    parsed: list[BoundaryRule] = []
                    for item in cfg_rules:
                        if isinstance(item, dict) and "source" in item and "forbid_imports" in item:
                            forbid = item["forbid_imports"]
                            if isinstance(forbid, str):
                                forbid = [forbid]
                            parsed.append(
                                BoundaryRule(
                                    source=str(item["source"]),
                                    forbid_imports=[str(x) for x in forbid],
                                    reason=str(
                                        item.get(
                                            "reason",
                                            f"Layer '{item['source']}' cannot import {forbid}",
                                        )
                                    ),
                                )
                            )
                    if parsed:
                        return parsed
            except Exception as exc:
                logger.warning("Failed to parse architecture_boundaries from config: %s", exc)

        return list(DEFAULT_BOUNDARY_RULES)

    @staticmethod
    def _matches_source(rel_path: str, pattern: str) -> bool:
        """Checks if a normalized relative file path matches a glob pattern."""
        norm_rel = rel_path.replace("\\", "/")
        norm_pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(norm_rel, norm_pat):
            return True
        if norm_pat.endswith("/**"):
            prefix = norm_pat[:-3].rstrip("/") + "/"
            if norm_rel.startswith(prefix):
                return True
        return False

    @staticmethod
    def _matches_import(actual_import: str, forbidden_pattern: str) -> bool:
        """Checks if an imported module path matches a forbidden module pattern."""
        norm_actual = actual_import.strip(".")
        norm_forbid = forbidden_pattern.replace("/", ".").replace(".*", "").replace("**", "").strip(".")
        if not norm_forbid:
            return False
        return (
            norm_actual == norm_forbid
            or norm_actual.startswith(norm_forbid + ".")
            or fnmatch.fnmatch(norm_actual, forbidden_pattern.replace("/", "."))
        )

    @staticmethod
    def _extract_imports(content: str, filename: str = "<unknown>") -> list[tuple[int, str]]:
        """Extracts `(line_number, module_name)` pairs from Python source via AST."""
        imports: list[tuple[int, str]] = []
        try:
            tree = ast.parse(content, filename=filename)
        except SyntaxError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((getattr(node, "lineno", 1), alias.name))
            elif isinstance(node, ast.ImportFrom):
                base_mod = node.module or ""
                lineno = getattr(node, "lineno", 1)
                if base_mod:
                    imports.append((lineno, base_mod))
                for alias in node.names:
                    full_name = f"{base_mod}.{alias.name}".strip(".") if base_mod else alias.name
                    imports.append((lineno, full_name))
        return imports

    def check_repository(
        self, repo_path: Path | str, files: list[Path] | None = None
    ) -> BoundaryCheckResult:
        """Evaluates all Python files in the repository against boundary rules."""
        root = Path(repo_path).resolve()
        rules = self.load_rules(root)
        source_files = files if files is not None else discover_source_files(root)
        py_files = [f for f in source_files if f.suffix == ".py"]

        violations: list[BoundaryViolation] = []

        for py_file in py_files:
            try:
                rel_path = str(py_file.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel_path = py_file.name

            applicable_rules = [r for r in rules if self._matches_source(rel_path, r.source)]
            if not applicable_rules:
                continue

            content = safe_read_file(py_file)
            if not content:
                continue

            file_imports = self._extract_imports(content, filename=rel_path)
            seen_on_line: set[tuple[int, str]] = set()

            for rule in applicable_rules:
                for lineno, imp_name in file_imports:
                    for forbidden in rule.forbid_imports:
                        if self._matches_import(imp_name, forbidden):
                            key = (lineno, forbidden)
                            if key not in seen_on_line:
                                seen_on_line.add(key)
                                violations.append(
                                    BoundaryViolation(
                                        file=rel_path,
                                        line=lineno,
                                        source_pattern=rule.source,
                                        forbidden_import=forbidden,
                                        actual_import=imp_name,
                                        reason=rule.reason,
                                    )
                                )

        score = max(0.0, 100.0 - (len(violations) * 15.0))
        return BoundaryCheckResult(
            passed=len(violations) == 0,
            score=score,
            files_checked=len(py_files),
            rules_evaluated=len(rules),
            violations=violations,
        )
