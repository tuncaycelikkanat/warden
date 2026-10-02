"""OASIS SARIF v2.1.0 (Static Analysis Results Interchange Format) export service for WARDEN.

Generates standard SARIF JSON reports compatible with GitHub Security Code Scanning,
Azure DevOps, and IDE SARIF viewers.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
SARIF_VERSION = "2.1.0"

WARDEN_RULES = [
    {
        "id": "WARDEN-SEC-001",
        "name": "HighEntropySecret",
        "shortDescription": {"text": "High entropy secret or API key detected in source code."},
        "fullDescription": {
            "text": "Shannon entropy analysis identified a high-randomness string literal matching credential or cryptographic key patterns."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Do not hardcode secrets. Store credentials in environment variables or a secure secret manager."},
        "properties": {"tags": ["security", "secrets", "cwe-798"]},
    },
    {
        "id": "WARDEN-SEC-002",
        "name": "SecurityVulnerability",
        "shortDescription": {"text": "Static code analysis detected a security vulnerability."},
        "fullDescription": {
            "text": "Semgrep or static pattern analyzer found potential security risk (SQLi, command injection, insecure eval, etc.)."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Review finding details and replace vulnerable construct with a safe, parameterized API."},
        "properties": {"tags": ["security", "vulnerability"]},
    },
    {
        "id": "WARDEN-SUPPLY-001",
        "name": "TyposquattingRisk",
        "shortDescription": {"text": "Dependency name is suspiciously similar to a popular package (typosquatting)."},
        "fullDescription": {
            "text": "Jaro-Winkler string similarity and homoglyph detection flagged a potential malicious package substitution."
        },
        "defaultConfiguration": {"level": "error"},
        "help": {"text": "Verify the package spelling against official PyPI repository before installing."},
        "properties": {"tags": ["supply-chain", "security", "cwe-1357"]},
    },
    {
        "id": "WARDEN-ARCH-001",
        "name": "CircularDependency",
        "shortDescription": {"text": "Circular import dependency cycle detected between modules."},
        "fullDescription": {
            "text": "Modules have recursive import loops creating tight coupling and runtime initialization risks."
        },
        "defaultConfiguration": {"level": "warning"},
        "help": {"text": "Refactor shared interfaces into a separate module or use dependency injection to form an Acyclic DAG."},
        "properties": {"tags": ["architecture", "maintainability"]},
    },
    {
        "id": "WARDEN-QUAL-001",
        "name": "HighCyclomaticComplexity",
        "shortDescription": {"text": "Function cyclomatic complexity exceeds threshold (CC > 10)."},
        "fullDescription": {
            "text": "Functions with high cyclomatic complexity have too many branching paths, reducing maintainability and testability."
        },
        "defaultConfiguration": {"level": "warning"},
        "help": {"text": "Apply guard clauses, early returns, or extract sub-routines into helper functions."},
        "properties": {"tags": ["code-quality", "complexity"]},
    },
    {
        "id": "WARDEN-VIBE-001",
        "name": "AISlopPattern",
        "shortDescription": {"text": "AI code generation artifact or vibe-coding style drift detected."},
        "fullDescription": {
            "text": "Layer 1.5 classifier flagged excessive repetitive comments, defensive pass-through blocks, or hallucinated patterns."
        },
        "defaultConfiguration": {"level": "note"},
        "help": {"text": "Clean up verbose AI-generated boilerplate and adhere to idiomatic coding conventions."},
        "properties": {"tags": ["ai-slop", "vibe-coding", "maintainability"]},
    },
]


class SarifReportService:
    """Exports WARDEN audit findings into OASIS SARIF v2.1.0 standard JSON."""

    def generate_sarif(self, audit_data: dict[str, Any], repo_path: str = "") -> dict[str, Any]:
        """Converts audit findings and metrics into a standard SARIF v2.1.0 document."""
        results: list[dict[str, Any]] = []

        repo_base = Path(repo_path).resolve() if repo_path else Path.cwd()

        # 1. Parse secrets from raw_data or layer1
        results.extend(self._extract_secret_findings(audit_data, repo_base))

        # 2. Parse security scanner findings
        results.extend(self._extract_security_findings(audit_data, repo_base))

        # 3. Parse circular dependency cycles
        results.extend(self._extract_circular_findings(audit_data, repo_base))

        # 4. Parse complexity / tech debt findings
        results.extend(self._extract_complexity_findings(audit_data, repo_base))

        # 5. Parse typosquatting / supply chain findings
        results.extend(self._extract_supply_chain_findings(audit_data, repo_base))

        # 6. Parse AI slop findings
        results.extend(self._extract_ai_slop_findings(audit_data, repo_base))

        sarif_doc: dict[str, Any] = {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "WARDEN",
                            "version": "0.1.0",
                            "semanticVersion": "0.1.0",
                            "informationUri": "https://github.com/tuncaycelikkanat/warden",
                            "rules": WARDEN_RULES,
                        }
                    },
                    "results": results,
                }
            ],
        }

        return sarif_doc

    def export_to_file(self, audit_data: dict[str, Any], output_path: Path, repo_path: str = "") -> Path:
        """Generates SARIF document and writes it to the specified output file."""
        sarif_data = self.generate_sarif(audit_data, repo_path=repo_path)
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(sarif_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return output_path

    def _normalize_uri(self, file_path: str | Path, repo_base: Path) -> str:
        """Converts file path to relative URI with forward slashes for SARIF."""
        p = Path(file_path)
        if p.is_absolute():
            try:
                rel = p.relative_to(repo_base)
                return str(rel).replace("\\", "/")
            except ValueError:
                return p.name
        return str(p).replace("\\", "/")

    def _create_location(self, uri: str, start_line: int = 1, start_col: int = 1) -> list[dict[str, Any]]:
        """Helper to create a standard SARIF physical location object."""
        return [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": uri,
                        "uriBaseId": "%SRCROOT%",
                    },
                    "region": {
                        "startLine": max(1, start_line),
                        "startColumn": max(1, start_col),
                    },
                }
            }
        ]

    def _extract_secret_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts high-entropy secrets and Gitleaks findings."""
        results: list[dict[str, Any]] = []

        # Check in layer1 -> entropy / secrets
        layer1 = data.get("layer1", {})
        entropy_items = layer1.get("entropy", {}).get("findings", [])
        if not entropy_items:
            # Check raw_data or top-level findings
            entropy_items = data.get("entropy_findings", [])

        for item in entropy_items:
            file_path = item.get("file", "unknown")
            line = item.get("line", 1)
            var_name = item.get("variable_name") or item.get("variable", "unknown")
            masked = item.get("masked_value", "***")
            entropy = item.get("entropy_score") or item.get("entropy", 0.0)

            results.append({
                "ruleId": "WARDEN-SEC-001",
                "level": "error",
                "message": {
                    "text": f"High-entropy secret detected in variable '{var_name}' ({masked}) - H={entropy:.2f}"
                },
                "locations": self._create_location(self._normalize_uri(file_path, repo_base), line),
            })

        return results

    def _extract_security_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts Semgrep / SAST security findings."""
        results: list[dict[str, Any]] = []

        layer1 = data.get("layer1", {})
        sec_findings = layer1.get("security", {}).get("findings", [])
        if not sec_findings:
            sec_findings = data.get("security_findings", [])

        for item in sec_findings:
            path = item.get("path") or item.get("file", "unknown")
            start = item.get("start", {})
            line = start.get("line") if isinstance(start, dict) else item.get("line", 1)
            check_id = item.get("check_id") or item.get("rule_id", "security-issue")
            extra = item.get("extra", {})
            msg = extra.get("message") if isinstance(extra, dict) else item.get("message", "Security vulnerability found")

            results.append({
                "ruleId": "WARDEN-SEC-002",
                "level": "error",
                "message": {"text": f"[{check_id}] {msg}"},
                "locations": self._create_location(self._normalize_uri(path, repo_base), line),
            })

        return results

    def _extract_circular_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts circular dependency cycles."""
        results: list[dict[str, Any]] = []

        cycles = (
            data.get("layer1", {}).get("circular_dependencies", {}).get("cycles", [])
            or data.get("circular_cycles", [])
        )

        for c in cycles:
            path_list = c.get("cycle_path", []) if isinstance(c, dict) else getattr(c, "cycle_path", [])
            cycle_str = " -> ".join(path_list)
            first_module = path_list[0] if path_list else "module.py"

            results.append({
                "ruleId": "WARDEN-ARCH-001",
                "level": "warning",
                "message": {"text": f"Circular import dependency cycle detected: {cycle_str}"},
                "locations": self._create_location(first_module, 1),
            })

        return results

    def _extract_complexity_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts high cyclomatic complexity findings."""
        results: list[dict[str, Any]] = []

        td = data.get("layer1", {}).get("tech_debt", {})
        hotspots = td.get("hotspots", []) or data.get("complexity_hotspots", [])

        for h in hotspots:
            file_name = h.get("file") or h.get("file_path", "unknown")
            cc = h.get("complexity") or h.get("cc", 0)
            func_name = h.get("function_name") or h.get("name", "function")
            line = h.get("line", 1)

            if cc > 10:
                results.append({
                    "ruleId": "WARDEN-QUAL-001",
                    "level": "warning",
                    "message": {
                        "text": f"Function '{func_name}' has high cyclomatic complexity ({cc} > 10)"
                    },
                    "locations": self._create_location(self._normalize_uri(file_name, repo_base), line),
                })

        return results

    def _extract_supply_chain_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts typosquatting and supply chain risks."""
        results: list[dict[str, Any]] = []

        typo_items = (
            data.get("layer1", {}).get("dependency_health", {}).get("typosquatting_warnings", [])
            or data.get("typosquatting_findings", [])
        )

        for t in typo_items:
            pkg = t.get("package", "unknown")
            target = t.get("target_package", "unknown")
            score = t.get("similarity_score", 0.0)

            results.append({
                "ruleId": "WARDEN-SUPPLY-001",
                "level": "error",
                "message": {
                    "text": f"Suspicious dependency '{pkg}' may typosquat popular package '{target}' (Similarity: {score:.2f})"
                },
                "locations": self._create_location("pyproject.toml", 1),
            })

        return results

    def _extract_ai_slop_findings(self, data: dict[str, Any], repo_base: Path) -> list[dict[str, Any]]:
        """Extracts AI slop and style drift warnings."""
        results: list[dict[str, Any]] = []

        vibe_data = data.get("layer1_5", {}) or data.get("vibe", {})
        slop_findings = vibe_data.get("slop_findings", []) or data.get("ai_slop_findings", [])

        for sf in slop_findings:
            fpath = sf.get("file", "unknown")
            msg = sf.get("pattern_description") or sf.get("reason", "AI Slop code pattern flagged")
            line = sf.get("line", 1)

            results.append({
                "ruleId": "WARDEN-VIBE-001",
                "level": "note",
                "message": {"text": f"AI Slop Pattern: {msg}"},
                "locations": self._create_location(self._normalize_uri(fpath, repo_base), line),
            })

        return results
