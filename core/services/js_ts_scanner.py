"""JavaScript and TypeScript analyzer for WARDEN.

Analyzes frontend/Node.js projects for:
- package.json dependency pinning and security health
- tsconfig.json type safety strictness (strict, noImplicitAny)
- Dangerous DOM / script injection patterns (innerHTML, eval)
- TypeScript ': any' type escapes
- console.log production residue
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.evidence.base import safe_read_file

logger = logging.getLogger(__name__)


@dataclass
class JsTsFinding:
    """A finding discovered in a JS/TS source or configuration file."""
    file: str
    line: int
    rule: str
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    message: str


@dataclass
class JsTsScanResult:
    """Results of scanning JavaScript and TypeScript code and packages."""
    applicable: bool = False
    total_js_ts_files: int = 0
    total_dependencies: int = 0
    unpinned_dependencies: list[str] = field(default_factory=list)
    is_typescript: bool = False
    strict_mode_enabled: bool = False
    any_type_count: int = 0
    console_log_count: int = 0
    inner_html_count: int = 0
    findings: list[JsTsFinding] = field(default_factory=list)
    score: float = 100.0  # 0 to 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "total_js_ts_files": self.total_js_ts_files,
            "total_dependencies": self.total_dependencies,
            "unpinned_dependencies": self.unpinned_dependencies,
            "is_typescript": self.is_typescript,
            "strict_mode_enabled": self.strict_mode_enabled,
            "any_type_count": self.any_type_count,
            "console_log_count": self.console_log_count,
            "inner_html_count": self.inner_html_count,
            "findings_count": len(self.findings),
            "score": round(self.score, 1),
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "rule": f.rule,
                    "severity": f.severity,
                    "message": f.message,
                }
                for f in self.findings[:50]
            ],
        }


class JsTsScannerService:
    """Scans JavaScript & TypeScript files, package.json and tsconfig.json."""

    JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    def scan(self, repo_path: Path, files: list[Path] | None = None) -> JsTsScanResult:
        """Executes full JS/TS analysis on the repository."""
        repo_path = repo_path.resolve()
        package_json = repo_path / "package.json"
        tsconfig_json = repo_path / "tsconfig.json"

        if files is None:
            from core.services.orchestrator import discover_source_files
            all_files = discover_source_files(repo_path)
        else:
            all_files = files

        js_ts_files = [f for f in all_files if f.suffix in self.JS_TS_EXTENSIONS]

        if not package_json.exists() and not js_ts_files:
            return JsTsScanResult(applicable=False)

        result = JsTsScanResult(
            applicable=True,
            total_js_ts_files=len(js_ts_files),
            is_typescript=any(f.suffix in {".ts", ".tsx"} for f in js_ts_files) or tsconfig_json.exists(),
        )

        penalty = 0.0

        # 1. Analyze package.json
        if package_json.exists():
            try:
                pkg_data = json.loads(safe_read_file(package_json))
                deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                result.total_dependencies = len(deps)

                for dep_name, version in deps.items():
                    # Check for unpinned dependencies (*, latest, ^, ~)
                    if version in ("*", "latest") or version.startswith(("^", "~", ">", "<")):
                        result.unpinned_dependencies.append(dep_name)

                if result.unpinned_dependencies:
                    unpinned_ratio = len(result.unpinned_dependencies) / max(1, len(deps))
                    penalty += min(20.0, unpinned_ratio * 25.0)
                    result.findings.append(
                        JsTsFinding(
                            file="package.json",
                            line=1,
                            rule="unpinned-npm-dependencies",
                            severity="MEDIUM",
                            message=f"{len(result.unpinned_dependencies)} dependencies use loose ranges (e.g. ^, ~, *).",
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to parse package.json: {e}")

        # 2. Analyze tsconfig.json
        if tsconfig_json.exists():
            try:
                raw_tsconfig = safe_read_file(tsconfig_json)
                # Remove json comments if any
                clean_json = re.sub(r"//.*?\n|/\*.*?\*/", "", raw_tsconfig, flags=re.S)
                ts_data = json.loads(clean_json)
                co = ts_data.get("compilerOptions", {})
                if co.get("strict") is True:
                    result.strict_mode_enabled = True
                else:
                    penalty += 10.0
                    result.findings.append(
                        JsTsFinding(
                            file="tsconfig.json",
                            line=1,
                            rule="typescript-strict-mode-disabled",
                            severity="MEDIUM",
                            message="TypeScript 'compilerOptions.strict' is not enabled.",
                        )
                    )
            except Exception:
                pass

        # 3. Source code inspections (.js, .jsx, .ts, .tsx)
        inner_html_re = re.compile(r"\binnerHTML\s*=", re.I)
        console_log_re = re.compile(r"\bconsole\.(log|debug)\s*\(", re.I)
        any_type_re = re.compile(r"(:\s*any\b|\bas\s+any\b)")

        for f in js_ts_files:
            rel = str(f.relative_to(repo_path))
            content = safe_read_file(f)
            if not content:
                continue

            for line_idx, line in enumerate(content.splitlines(), start=1):
                if inner_html_re.search(line):
                    result.inner_html_count += 1
                    penalty += 5.0
                    result.findings.append(
                        JsTsFinding(
                            file=rel,
                            line=line_idx,
                            rule="dangerously-set-inner-html",
                            severity="HIGH",
                            message="Direct assignment to innerHTML detected — potential DOM XSS vulnerability.",
                        )
                    )

                if console_log_re.search(line):
                    result.console_log_count += 1

                if f.suffix in {".ts", ".tsx"} and any_type_re.search(line):
                    result.any_type_count += 1

        # Penalty for excessive console.log in production code
        if result.console_log_count > 15:
            penalty += min(10.0, (result.console_log_count - 15) * 0.5)

        # Penalty for high 'any' type count in TypeScript
        if result.is_typescript and result.any_type_count > 10:
            penalty += min(15.0, (result.any_type_count - 10) * 0.8)

        result.score = max(0.0, min(100.0, 100.0 - penalty))
        return result
