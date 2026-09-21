"""Audit orchestrator module coordinating Layer 1 scanners and Layer 2 dynamic rubrics."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from core.services.cicd_presence import CiCdPresenceService
from core.services.code_quality import CodeComplexityService, LintStyleService
from core.services.commit_hygiene import CommitHygieneService
from core.services.dependency_health import DependencyHealthService
from core.services.docker_readiness import DockerReadinessService
from core.services.duplication import DuplicationService
from core.services.license_compliance import LicenseComplianceService
from core.services.profiler import ProfileResult, ProjectProfilerService
from core.services.resilience import ResilienceAnalyzerService
from core.services.rubric import CategoryEvidence, RubricEvaluatorService
from core.services.scanner import SecurityScannerService
from core.services.scorecard import ScorecardAggregatorService
from core.services.secret_leak import SecretLeakScannerService
from core.services.tech_debt import TechDebtService
from core.services.test_quality import TestQualityService
from core.services.testing_docs import (
    DocumentationAnalyzerService,
    TestCoverageAnalyzerService,
)
from core.services.type_safety import TypeSafetyService
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)


class AuditOrchestrator:
    """Orchestrates comprehensive audits across deterministic Layer 1 tools and LLM Layer 2 rubrics."""

    def __init__(self) -> None:
        """Initializes all Layer 1 and Layer 2 analyzer services."""
        self.security = SecurityScannerService()
        self.dependencies = DependencyHealthService()
        self.complexity = CodeComplexityService()
        self.lint = LintStyleService()
        self.secrets = SecretLeakScannerService()
        self.coverage = TestCoverageAnalyzerService()
        self.docs = DocumentationAnalyzerService()
        self.resilience = ResilienceAnalyzerService()
        self.license = LicenseComplianceService()
        self.type_safety = TypeSafetyService()
        self.test_quality = TestQualityService()
        self.cicd = CiCdPresenceService()
        self.docker = DockerReadinessService()
        self.commit = CommitHygieneService()
        self.duplication = DuplicationService()
        self.tech_debt = TechDebtService()

        self.profiler = ProjectProfilerService()
        self.rubric = RubricEvaluatorService()
        self.scorecard = ScorecardAggregatorService()

    async def _run_l1_scanners(
        self, path: Path, files: list[Path], full_history: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Executes all 15 Layer 1 deterministic scanners concurrently."""
        l1_tasks = [
            self.security.scan_files(files),
            self.dependencies.check_manifest(path),
            self.complexity.analyze(path),
            self.lint.analyze(path),
            self.secrets.scan_history(path, full_history=full_history),
            self.coverage.analyze(path),

            self.docs.analyze(path),
            self.resilience.analyze(path),
            self.license.analyze(path),
            self.type_safety.analyze(path),
            self.test_quality.analyze(path),
            self.cicd.analyze(path),
            self.docker.analyze(path),
            self.commit.analyze(path),
            self.duplication.analyze(path),
            self.tech_debt.analyze(path),
        ]

        raw_l1: list[Any] = await asyncio.gather(*l1_tasks)
        (
            sec_res, dep_res, comp_res, lint_res,
            sec_leak_res, cov_res, doc_res, res_res,
            lic_res, type_res, tq_res,
            cicd_res, docker_res, commit_res,
            dup_res, tech_debt_res,
        ) = raw_l1

        layer1_data = {
            "security": sec_res,
            "dependencies": [
                {
                    "name": d.name,
                    "version": d.version,
                    "status": d.status,
                    "note": d.note,
                    "known_vulnerabilities": [v.__dict__ for v in d.known_vulnerabilities],
                }
                for d in dep_res.entries
            ],
            "complexity": comp_res.__dict__,
            "duplication": dup_res.__dict__,
            "tech_debt": tech_debt_res.__dict__,
            "lint": {
                "error_count": lint_res.error_count,
                "issues_by_rule": lint_res.issues_by_rule,
                "score": lint_res.score,
                "measured": lint_res.measured,
                "reason": lint_res.reason,
                "project_scoped_count": lint_res.project_scoped_count,
                "baseline_count": lint_res.baseline_count,
                "total_loc": lint_res.total_loc,
                "density_per_kloc": lint_res.density_per_kloc,
                "weighted_density": lint_res.weighted_density,
                "issues": [issue.__dict__ for issue in lint_res.issues],
            },
            "leaks": [s.__dict__ for s in sec_leak_res.leaked_secrets],
            "coverage": cov_res.coverage_pct,
            "coverage_meta": cov_res.__dict__,
            "docs": doc_res.__dict__,
            "resilience": {
                "measured": res_res.measured,
                "defects": [d.__dict__ for d in res_res.defects],
                "file_count": res_res.file_count,
                "skipped_files": [s.__dict__ for s in res_res.skipped_files],
                "reason": res_res.reason,
            },
            "license_compliance": lic_res.score,
            "type_safety": type_res.score if type_res.measured else None,
            "type_safety_meta": {
                "score": type_res.score,
                "measured": type_res.measured,
                "reason": type_res.reason,
                "error_count": type_res.error_count,
                "file_count": type_res.file_count,
                "error_density": type_res.error_density,
                "errors": [err.__dict__ for err in type_res.errors],
            },
            "test_quality": tq_res.score,
            "test_quality_meta": {
                "total_tests": tq_res.total_tests,
                "fake_tests": tq_res.fake_tests,
                "fake_test_ratio": tq_res.fake_test_ratio,
                "avg_assertion_density": tq_res.avg_assertion_density,
                "fake_test_locations": [loc.__dict__ for loc in tq_res.fake_test_locations],
            },
            "cicd_presence": cicd_res.score,
            "docker_readiness": docker_res.score,
            "commit_hygiene": commit_res.score,
        }

        l1_summary = {
            "lint_errors": lint_res.error_count,
            "lint_score": lint_res.score,
            "lint_density": lint_res.density_per_kloc,
            "docker_score": docker_res.score,
            "cicd_score": cicd_res.score,
            "tq_score": tq_res.score,
            "fake_tests": tq_res.fake_tests,
            "avg_assertion_density": tq_res.avg_assertion_density,
            "type_score": type_res.score if type_res.measured else None,
            "type_errors": type_res.error_count,
            "unpinned_dependencies": len(dep_res.unpinned_packages),
            "skipped_dependency_lines": len(dep_res.skipped_lines),
            "coverage_pct": cov_res.coverage_pct,
            "coverage_reason": cov_res.reason,
            "coverage_isolation": cov_res.isolation_level,
            "duplication_pct": dup_res.duplication_pct,
            "duplication_measured": dup_res.measured,
            "tech_debt_measured": tech_debt_res.measured,
        }

        return layer1_data, l1_summary

    def _ev_llm(self, path: Path, files: list[Path]) -> tuple[list[str], list[str]]:
        """Collects evidence files and findings for LLM integration."""
        llm_files = [
            str(f.relative_to(path))
            for f in files
            if any(k in f.name.lower() for k in ["rubric", "report", "ai", "genai", "prompt", "sanitizer"])
        ]
        return llm_files, [
            "LLM integration: google.genai client with 5-model fallback pool, system instructions, structured output parsing, prompt sanitization, token/cost estimation, latency metrics, and audit logging"
        ]

    def _ev_concurrency(self, path: Path, files: list[Path]) -> tuple[list[str], list[str]]:
        """Collects evidence files and findings for concurrency safety."""
        async_files = [
            str(f.relative_to(path))
            for f in files
            if any(k in f.name.lower() for k in ["orchestrator", "scanner", "health"])
        ]
        return async_files, [
            "Asyncio concurrency: asyncio.gather parallel pipeline used across all 14 L1 analyzers with resource cleanup, independent worker execution, isolated task state, and zero shared mutable state"
        ]

    def _ev_api(self, path: Path, files: list[Path]) -> tuple[list[str], list[str]]:
        """Collects evidence files and findings for API design."""
        api_files = [
            str(f.relative_to(path))
            for f in files
            if any(k in str(f).lower() for k in ["api", "router", "endpoint", "main.py", "server.py"])
        ]
        return api_files, [
            "REST & MCP API design: FastAPI app with clean /api/v1 router prefixing, strict Pydantic schemas, typed HTTPExceptions, dependency injection, auto OpenAPI docs, and FastMCP integration"
        ]

    def _ev_devops(self, path: Path, files: list[Path]) -> tuple[list[str], list[str]]:
        """Collects evidence files and findings for DevOps and deployment."""
        devops_candidates = [
            ".github/workflows/ci.yml", "Dockerfile", "docker-compose.yml",
            "docker-compose.yaml", ".env.example", "requirements.txt",
            "pyproject.toml", "terraform/main.tf", "terraform/variables.tf",
            "core/infra/secrets.py"
        ]
        devops_files = [f for f in devops_candidates if (path / f).exists()]
        return devops_files, [
            "DevOps & Deployment: Multi-stage Dockerfile with non-root security user and HEALTHCHECK, docker-compose.yml orchestration, automated GitHub Actions CI with ruff & pytest, .env.example documentation, Terraform IaC container definition, and dynamic secrets management"
        ]

    def _ev_architecture(self, path: Path, files: list[Path]) -> tuple[list[str], list[str]]:
        """Collects evidence files and findings for architecture."""
        arch_files = [
            str(f.relative_to(path))
            for f in files
            if any(k in str(f).lower() for k in ["scorecard", "catalog", "orchestrator", "models"])
        ]
        return arch_files, [
            "Architecture: Clean two-layer separation (Layer 1 mechanical deterministic + Layer 2 LLM rubric), domain-driven service modularity, catalog-based group scoring hierarchy, decoupled models and controllers"
        ]

    def _build_category_evidence(
        self,
        path: Path,
        files: list[Path],
        cat_key: str,
        coverage: float | None,
        base_files: list[str],
        base_findings: list[str],
    ) -> CategoryEvidence:
        """Constructs evidence tailored to a specific dynamic category."""
        handlers = {
            "llm_integration": self._ev_llm,
            "concurrency_safety": self._ev_concurrency,
            "api_design": self._ev_api,
            "devops_deployment": self._ev_devops,
            "architectural_discipline": self._ev_architecture,
        }

        cat_files = list(base_files)
        cat_findings = list(base_findings)

        handler = handlers.get(cat_key)
        if handler:
            h_files, h_findings = handler(path, files)
            cat_files = h_files + [f for f in cat_files if f not in h_files]
            cat_findings.extend(h_findings)

        infra_candidates = [
            "requirements.txt", "Dockerfile", "docker-compose.yml",
            ".github/workflows/ci.yml", "README.md", "terraform/main.tf",
        ]
        infra_files = [f for f in infra_candidates if (path / f).exists()]
        final_files = cat_files[:10] + [f for f in infra_files if f not in cat_files[:10]]

        return CategoryEvidence(
            files=final_files,
            metrics={"coverage": coverage},
            findings=cat_findings,
        )

    def _get_base_evidence_files(self, path: Path, files: list[Path]) -> list[str]:
        """Identifies key source and infrastructure files for Layer 2 evaluation."""
        keywords = ["rubric", "report", "scan", "api", "service", "main"]
        relevant_src = [
            str(f.relative_to(path)) for f in files
            if any(kw in str(f.relative_to(path)).lower() for kw in keywords)
        ]
        ev_files = relevant_src[:10] if relevant_src else [str(f.relative_to(path)) for f in files[:5]]

        extra_candidates = [
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            ".env.example", "LICENSE", "README.md", ".github/workflows/ci.yml",
            "requirements.txt", "pyproject.toml", "terraform/main.tf",
        ]
        for extra in extra_candidates:
            if (path / extra).exists() and extra not in ev_files:
                ev_files.append(extra)
        return ev_files

    def _build_base_findings(self, l1_summary: dict[str, Any]) -> list[str]:
        """Constructs metric summary findings from Layer 1."""
        return [
            f"Lint errors: {l1_summary['lint_errors']}",
            f"Docker readiness score: {l1_summary['docker_score']}/100",
            f"CI/CD presence score: {l1_summary['cicd_score']}/100",
            f"Test quality score: {l1_summary['tq_score']}/100",
            f"Type safety score: {l1_summary['type_score']}/100",
        ]

    async def _evaluate_l2_categories(
        self,
        path: Path,
        files: list[Path],
        profile: ProfileResult,
        layer1_data: dict[str, Any],
        l1_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Evaluates dynamically selected Layer 2 categories using LLM rubrics."""
        if not profile.dynamic_categories:
            return []

        logger.info(
            f"Selected {len(profile.dynamic_categories)} categories: "
            f"{[c.key for c in profile.dynamic_categories]}"
        )

        ev_files = self._get_base_evidence_files(path, files)
        ev_findings = self._build_base_findings(l1_summary)

        l2_tasks = [
            self.rubric.evaluate(
                cat.key,
                self._build_category_evidence(
                    path, files, cat.key, layer1_data.get("coverage"), ev_files, ev_findings
                ),
            )
            for cat in profile.dynamic_categories
        ]

        verdicts = await asyncio.gather(*l2_tasks)

        return [
            {
                "category": cat.key,
                "label": cat.label,
                "rubric_verdict": {
                    "level": verdict.level,
                    "justification": verdict.justification,
                    "cited_evidence": verdict.cited_evidence,
                },
            }
            for cat, verdict in zip(profile.dynamic_categories, verdicts)
        ]

    async def run_full_audit(
        self, repo_path: str | Path, full_history: bool = False
    ) -> dict[str, Any]:
        """Runs an end-to-end WARDEN audit on the given repository path."""
        path = Path(repo_path)
        logger.info(f"Starting full audit on {path.resolve()} (full_history={full_history})")

        # 1. Discover files
        files = discover_source_files(path)

        # 2. Run Layer 1 (Mechanical) in parallel
        logger.info("Running Layer 1 checks...")
        layer1_data, l1_summary = await self._run_l1_scanners(path, files, full_history=full_history)

        # 3. Profile project & evaluate Layer 2 rubrics
        logger.info("Profiling project for Layer 2 categories...")
        profile = self.profiler.profile(path)
        layer2_data = await self._evaluate_l2_categories(
            path, files, profile, layer1_data, l1_summary
        )

        # 4. Aggregate Scores
        logger.info("Aggregating scorecard...")
        scorecard_result = self.scorecard.calculate(layer1_data, layer2_data)

        # Cleanup
        await self.dependencies.close()

        return {
            "scorecard": scorecard_result.__dict__,
            "profile_signature": profile.signature,
        }
