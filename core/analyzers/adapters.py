"""Built-in analyzer adapters conforming core service classes to AnalyzerPlugin."""

from __future__ import annotations

import logging

from core.analyzers.protocol import AnalysisContext, AnalyzerOutput, AnalyzerPlugin
from core.services.cicd_presence import CiCdPresenceService
from core.services.code_quality import CodeComplexityService, LintStyleService
from core.services.commit_hygiene import CommitHygieneService
from core.services.dependency_health import DependencyHealthService
from core.services.docker_readiness import DockerReadinessService
from core.services.duplication import DuplicationService
from core.services.license_compliance import LicenseComplianceService
from core.services.resilience import ResilienceAnalyzerService
from core.services.scanner import SecurityScannerService
from core.services.secret_leak import SecretLeakScannerService
from core.services.tech_debt import TechDebtService
from core.services.test_quality import TestQualityService
from core.services.testing_docs import (
    DocumentationAnalyzerService,
    TestCoverageAnalyzerService,
)
from core.services.type_safety import TypeSafetyService

logger = logging.getLogger(__name__)


class SecurityAnalyzer(AnalyzerPlugin):
    """SAST scanner running semgrep rules."""

    key = "security"
    display_name = "Security SAST"

    def __init__(self, service: SecurityScannerService | None = None) -> None:
        self.service = service or SecurityScannerService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        findings = await self.service.scan_files(ctx.source_files)
        return AnalyzerOutput(key=self.key, data=findings)


class DependencyAnalyzer(AnalyzerPlugin):
    """Manifest dependency and OSV vulnerability scanner."""

    key = "dependencies"
    display_name = "Dependency Health & OSV"

    def __init__(self, service: DependencyHealthService | None = None) -> None:
        self.service = service or DependencyHealthService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        dep_res = await self.service.check_manifest(ctx.repo_path)
        data = [
            {
                "name": d.name,
                "version": d.version,
                "status": d.status,
                "note": d.note,
                "known_vulnerabilities": [v.__dict__ for v in d.known_vulnerabilities],
            }
            for d in dep_res.entries
        ]
        summary = {
            "unpinned_dependencies": len(dep_res.unpinned_packages),
            "skipped_dependency_lines": len(dep_res.skipped_lines),
        }
        return AnalyzerOutput(key=self.key, data=data, summary=summary)


class ComplexityAnalyzer(AnalyzerPlugin):
    """Radon McCabe cyclomatic complexity scanner."""

    key = "complexity"
    display_name = "Cyclomatic Complexity"

    def __init__(self, service: CodeComplexityService | None = None) -> None:
        self.service = service or CodeComplexityService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        res = await self.service.analyze(ctx.repo_path)
        return AnalyzerOutput(key=self.key, data=res.__dict__)


class LintAnalyzer(AnalyzerPlugin):
    """Ruff static code linter and baseline conformance scanner."""

    key = "lint"
    display_name = "Lint & Code Health"

    def __init__(self, service: LintStyleService | None = None) -> None:
        self.service = service or LintStyleService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        lint_res = await self.service.analyze(ctx.repo_path)
        data = {
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
        }
        summary = {
            "lint_errors": lint_res.error_count,
            "lint_score": lint_res.score,
            "lint_density": lint_res.density_per_kloc,
        }
        return AnalyzerOutput(key=self.key, data=data, summary=summary, measured=lint_res.measured)


class SecretLeakAnalyzer(AnalyzerPlugin):
    """Gitleaks secret detection across git commits."""

    key = "leaks"
    display_name = "Secret Leak Scanner"

    def __init__(self, service: SecretLeakScannerService | None = None) -> None:
        self.service = service or SecretLeakScannerService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        sec_leak_res = await self.service.scan_history(ctx.repo_path, full_history=ctx.full_history)
        data = [s.__dict__ for s in sec_leak_res.leaked_secrets]
        return AnalyzerOutput(key=self.key, data=data)


class CoverageAnalyzer(AnalyzerPlugin):
    """Sandboxed coverage analyzer."""

    key = "coverage"
    display_name = "Test Coverage Analyzer"

    def __init__(self, service: TestCoverageAnalyzerService | None = None) -> None:
        self.service = service or TestCoverageAnalyzerService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        cov_res = await self.service.analyze(ctx.repo_path)
        summary = {
            "coverage_pct": cov_res.coverage_pct,
            "coverage_reason": cov_res.reason,
            "coverage_isolation": cov_res.isolation_level,
        }
        # Also produces coverage_meta
        return AnalyzerOutput(
            key=self.key,
            data=cov_res.coverage_pct,
            summary=summary,
            extra_data={"coverage_meta": cov_res.__dict__},
            measured=cov_res.measured,
        )


class DocumentationAnalyzer(AnalyzerPlugin):
    """Interrogate docstring coverage scanner."""

    key = "docs"
    display_name = "Documentation Coverage"

    def __init__(self, service: DocumentationAnalyzerService | None = None) -> None:
        self.service = service or DocumentationAnalyzerService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        doc_res = await self.service.analyze(ctx.repo_path)
        return AnalyzerOutput(key=self.key, data=doc_res.__dict__, measured=doc_res.measured)


class ResilienceAnalyzer(AnalyzerPlugin):
    """AST resilience & timeout analyzer."""

    key = "resilience"
    display_name = "Resilience & Defensive Timeouts"

    def __init__(self, service: ResilienceAnalyzerService | None = None) -> None:
        self.service = service or ResilienceAnalyzerService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        res_res = await self.service.analyze(ctx.repo_path)
        data = {
            "measured": res_res.measured,
            "defects": [d.__dict__ for d in res_res.defects],
            "file_count": res_res.file_count,
            "skipped_files": [s.__dict__ for s in res_res.skipped_files],
            "reason": res_res.reason,
        }
        return AnalyzerOutput(key=self.key, data=data, measured=res_res.measured)


class LicenseAnalyzer(AnalyzerPlugin):
    """Open-source software license compliance scanner."""

    key = "license_compliance"
    display_name = "License Compliance"

    def __init__(self, service: LicenseComplianceService | None = None) -> None:
        self.service = service or LicenseComplianceService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        lic_res = await self.service.analyze(ctx.repo_path)
        return AnalyzerOutput(key=self.key, data=lic_res.score)


class TypeSafetyAnalyzer(AnalyzerPlugin):
    """Mypy type safety scanner."""

    key = "type_safety"
    display_name = "Type Safety (Mypy)"

    def __init__(self, service: TypeSafetyService | None = None) -> None:
        self.service = service or TypeSafetyService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        type_res = await self.service.analyze(ctx.repo_path)
        summary = {
            "type_score": type_res.score if type_res.measured else None,
            "type_errors": type_res.error_count,
        }
        extra_data = {
            "type_safety_meta": {
                "score": type_res.score,
                "measured": type_res.measured,
                "reason": type_res.reason,
                "error_count": type_res.error_count,
                "file_count": type_res.file_count,
                "error_density": type_res.error_density,
                "errors": [err.__dict__ for err in type_res.errors],
            }
        }
        return AnalyzerOutput(
            key=self.key,
            data=type_res.score if type_res.measured else None,
            summary=summary,
            extra_data=extra_data,
            measured=type_res.measured,
        )


class TestQualityAnalyzer(AnalyzerPlugin):
    """Test assertion density and fake test detector."""

    key = "test_quality"
    display_name = "Test Quality & Assertion Density"

    def __init__(self, service: TestQualityService | None = None) -> None:
        self.service = service or TestQualityService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        tq_res = await self.service.analyze(ctx.repo_path)
        summary = {
            "tq_score": tq_res.score,
            "fake_tests": tq_res.fake_tests,
            "avg_assertion_density": tq_res.avg_assertion_density,
        }
        extra_data = {
            "test_quality_meta": {
                "total_tests": tq_res.total_tests,
                "fake_tests": tq_res.fake_tests,
                "fake_test_ratio": tq_res.fake_test_ratio,
                "avg_assertion_density": tq_res.avg_assertion_density,
                "fake_test_locations": [loc.__dict__ for loc in tq_res.fake_test_locations],
            }
        }
        return AnalyzerOutput(
            key=self.key,
            data=tq_res.score,
            summary=summary,
            extra_data=extra_data,
        )


class CiCdAnalyzer(AnalyzerPlugin):
    """CI/CD workflow existence and hygiene scanner."""

    key = "cicd_presence"
    display_name = "CI/CD Pipeline Presence"

    def __init__(self, service: CiCdPresenceService | None = None) -> None:
        self.service = service or CiCdPresenceService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        cicd_res = await self.service.analyze(ctx.repo_path)
        return AnalyzerOutput(
            key=self.key,
            data=cicd_res.score,
            summary={"cicd_score": cicd_res.score},
        )


class DockerAnalyzer(AnalyzerPlugin):
    """Dockerfile and container readiness scanner."""

    key = "docker_readiness"
    display_name = "Docker Readiness"

    def __init__(self, service: DockerReadinessService | None = None) -> None:
        self.service = service or DockerReadinessService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        docker_res = await self.service.analyze(ctx.repo_path)
        score = docker_res.score if (docker_res.applicable and docker_res.measured) else None
        extra_data = {
            "docker_readiness_meta": {
                "score": docker_res.score,
                "applicable": docker_res.applicable,
                "measured": docker_res.measured,
                "reason": docker_res.reason,
                "has_dockerfile": docker_res.has_dockerfile,
                "has_healthcheck": docker_res.has_healthcheck,
                "has_non_root_user": docker_res.has_non_root_user,
                "has_multistage": docker_res.has_multistage,
                "has_env_example": docker_res.has_env_example,
                "has_docker_compose": docker_res.has_docker_compose,
                "dockerfile_path": docker_res.dockerfile_path,
            }
        }
        return AnalyzerOutput(
            key=self.key,
            data=score,
            summary={"docker_score": score},
            extra_data=extra_data,
            measured=docker_res.measured,
        )


class CommitHygieneAnalyzer(AnalyzerPlugin):
    """Git commit convention and hygiene scanner."""

    key = "commit_hygiene"
    display_name = "Commit Hygiene"

    def __init__(self, service: CommitHygieneService | None = None) -> None:
        self.service = service or CommitHygieneService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        commit_res = await self.service.analyze(ctx.repo_path)
        score = commit_res.score if commit_res.measured else None
        extra_data = {
            "commit_hygiene_meta": {
                "score": commit_res.score,
                "measured": commit_res.measured,
                "reason": commit_res.reason,
                "total_commits": commit_res.total_commits,
                "bad_commits": commit_res.bad_commits,
                "bad_ratio": commit_res.bad_ratio,
                "avg_length": commit_res.avg_length,
            }
        }
        return AnalyzerOutput(
            key=self.key,
            data=score,
            summary={"commit_score": score},
            extra_data=extra_data,
            measured=commit_res.measured,
        )


class DuplicationAnalyzer(AnalyzerPlugin):
    """JSCPD code duplication scanner."""

    key = "duplication"
    display_name = "Code Duplication (DRY)"

    def __init__(self, service: DuplicationService | None = None) -> None:
        self.service = service or DuplicationService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        dup_res = await self.service.analyze(ctx.repo_path)
        summary = {
            "duplication_pct": dup_res.duplication_pct,
            "duplication_measured": dup_res.measured,
        }
        return AnalyzerOutput(
            key=self.key,
            data=dup_res.__dict__,
            summary=summary,
            measured=dup_res.measured,
        )


class TechDebtAnalyzer(AnalyzerPlugin):
    """Technical debt and churn scanner."""

    key = "tech_debt"
    display_name = "Technical Debt & Churn"

    def __init__(self, service: TechDebtService | None = None) -> None:
        self.service = service or TechDebtService()

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        tech_debt_res = await self.service.analyze(ctx.repo_path)
        data = {
            "measured": tech_debt_res.measured,
            "total_commits_in_window": tech_debt_res.total_commits_in_window,
            "reason": tech_debt_res.reason,
            "note": tech_debt_res.note,
            "churn_entries": [
                {
                    "file": e.file,
                    "commit_count": e.commit_count,
                    "lines_changed": e.lines_changed,
                    "first_commit_date": e.first_commit_date.isoformat() if e.first_commit_date else None,
                    "last_commit_date": e.last_commit_date.isoformat() if e.last_commit_date else None,
                    "age_days": e.age_days,
                }
                for e in tech_debt_res.churn_entries
            ],
            "todo_markers": [
                {
                    "file": m.file,
                    "line": m.line,
                    "marker": m.marker,
                    "text": m.text,
                }
                for m in tech_debt_res.todo_markers
            ],
        }
        return AnalyzerOutput(
            key=self.key,
            data=data,
            summary={"tech_debt_measured": tech_debt_res.measured},
            measured=tech_debt_res.measured,
        )
