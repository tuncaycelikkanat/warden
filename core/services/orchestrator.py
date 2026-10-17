"""Audit orchestrator module coordinating Layer 1 scanners and Layer 2 dynamic rubrics."""

import asyncio
import logging
import re
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
from core.services.quality_gate import CriticalFindings
from core.services.resilience import ResilienceAnalyzerService
from core.services.rubric import (
    CategoryEvidence,
    CodeSnippet,
    RubricEvaluatorService,
    RubricVerdict,
)
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


from core.analyzers import AnalysisContext, AnalyzerRegistry, create_default_registry


class AuditOrchestrator:
    """Orchestrates comprehensive audits across deterministic Layer 1 tools and LLM Layer 2 rubrics."""

    def __init__(self, registry: AnalyzerRegistry | None = None) -> None:
        """Initializes all Layer 1 analyzers via registry and Layer 2 services."""
        self.registry = registry or create_default_registry()

        # Backward compatibility service handles
        self.security = getattr(self.registry.get("security"), "service", SecurityScannerService())
        self.dependencies = getattr(self.registry.get("dependencies"), "service", DependencyHealthService())
        self.complexity = getattr(self.registry.get("complexity"), "service", CodeComplexityService())
        self.lint = getattr(self.registry.get("lint"), "service", LintStyleService())
        self.secrets = getattr(self.registry.get("leaks"), "service", SecretLeakScannerService())
        self.coverage = getattr(self.registry.get("coverage"), "service", TestCoverageAnalyzerService())
        self.docs = getattr(self.registry.get("docs"), "service", DocumentationAnalyzerService())
        self.resilience = getattr(self.registry.get("resilience"), "service", ResilienceAnalyzerService())
        self.license = getattr(self.registry.get("license_compliance"), "service", LicenseComplianceService())
        self.type_safety = getattr(self.registry.get("type_safety"), "service", TypeSafetyService())
        self.test_quality = getattr(self.registry.get("test_quality"), "service", TestQualityService())
        self.cicd = getattr(self.registry.get("cicd_presence"), "service", CiCdPresenceService())
        self.docker = getattr(self.registry.get("docker_readiness"), "service", DockerReadinessService())
        self.commit = getattr(self.registry.get("commit_hygiene"), "service", CommitHygieneService())
        self.duplication = getattr(self.registry.get("duplication"), "service", DuplicationService())
        self.tech_debt = getattr(self.registry.get("tech_debt"), "service", TechDebtService())

        self.profiler = ProjectProfilerService()
        self.rubric = RubricEvaluatorService()
        self.scorecard = ScorecardAggregatorService()

    async def _run_l1_scanners(
        self, path: Path, files: list[Path], full_history: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Executes all registered Layer 1 deterministic scanners concurrently via AnalyzerRegistry."""
        ctx = AnalysisContext(repo_path=path, source_files=files, full_history=full_history)
        return await self.registry.run_all(ctx)

    @staticmethod
    def _safe_read_file(file_path: Path, max_chars: int = 150000) -> str:
        """Safely reads file content as string."""
        from core.services.evidence.base import safe_read_file
        return safe_read_file(file_path, max_chars)

    @staticmethod
    def _extract_snippet(
        file_rel: str,
        content: str,
        match_pattern: re.Pattern[str],
        context: str,
        max_lines: int = 15,
    ) -> CodeSnippet | None:
        """Extracts a focused code snippet around the first pattern match."""
        from core.services.evidence.base import extract_snippet
        return extract_snippet(file_rel, content, match_pattern, context, max_lines)

    def _ev_llm(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for LLM integration, prompt defense, and resilience."""
        from core.services.evidence.collectors import collect_llm_evidence
        return collect_llm_evidence(path, files)

    def _ev_concurrency(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for concurrency safety, async loops, and locks."""
        from core.services.evidence.collectors import collect_concurrency_evidence
        return collect_concurrency_evidence(path, files)

    def _ev_api(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for API design, routes, schema validation, and error handling."""
        from core.services.evidence.collectors import collect_api_evidence
        return collect_api_evidence(path, files)

    def _ev_devops(
        self,
        path: Path,
        files: list[Path],
        layer1_data: dict[str, Any] | None = None,
        l1_summary: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for DevOps, containerization, CI/CD, and IaC deployment."""
        from core.services.evidence.collectors import collect_devops_evidence
        return collect_devops_evidence(path, files, layer1_data=layer1_data, l1_summary=l1_summary)

    def _ev_architecture(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for layered architecture, modularity, and interfaces."""
        from core.services.evidence.collectors import collect_architecture_evidence
        return collect_architecture_evidence(path, files)

    def _ev_frontend_ux(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for Frontend UX, state management, components, and a11y."""
        from core.services.evidence.collectors import collect_frontend_evidence
        return collect_frontend_evidence(path, files)

    def _ev_quantitative_logic(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for quantitative modeling, validation, backtesting, and risk metrics."""
        from core.services.evidence.collectors import collect_quantitative_evidence
        return collect_quantitative_evidence(path, files)

    def _build_category_evidence(
        self,
        path: Path,
        files: list[Path],
        cat_key: str,
        coverage: float | None,
        base_files: list[str],
        base_findings: list[str],
        layer1_data: dict[str, Any] | None = None,
        l1_summary: dict[str, Any] | None = None,
    ) -> CategoryEvidence:
        """Constructs evidence tailored to a specific dynamic category."""
        handlers = {
            "llm_integration": self._ev_llm,
            "concurrency_safety": self._ev_concurrency,
            "api_design": self._ev_api,
            "devops_deployment": lambda p, fs: self._ev_devops(
                p, fs, layer1_data=layer1_data, l1_summary=l1_summary
            ),
            "architectural_discipline": self._ev_architecture,
            "frontend_ux": self._ev_frontend_ux,
            "quantitative_logic": self._ev_quantitative_logic,
        }

        cat_files = list(base_files)
        cat_findings = list(base_findings)
        cat_snippets: list[CodeSnippet] = []
        collection_errors: list[str] = []
        status = "ok"

        handler = handlers.get(cat_key)
        if handler:
            try:
                h_files, h_findings, h_snippets = handler(path, files)
                cat_files = h_files + [f for f in cat_files if f not in h_files]
                cat_findings.extend(h_findings)
                cat_snippets.extend(h_snippets)
                if not h_files and not h_findings:
                    status = "no_evidence_found"
                    cat_findings.append(
                        f"No concrete evidence or patterns found for category '{cat_key}' in analyzed repository."
                    )
            except Exception as exc:
                logger.exception(f"Error collecting evidence for {cat_key}")
                status = "partial_error"
                collection_errors.append(f"Collector exception: {exc}")
        else:
            status = "partial_error"
            collection_errors.append(f"No collector registered for category: {cat_key}")

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
            code_snippets=cat_snippets,
            evidence_collection_status=status,
            collection_errors=collection_errors,
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
        findings = []
        if "lint_errors" in l1_summary:
            findings.append(f"Lint errors: {l1_summary.get('lint_errors')}")
        if "docker_score" in l1_summary and l1_summary["docker_score"] is not None:
            findings.append(f"Docker score: {l1_summary.get('docker_score')}")
        if "cicd_score" in l1_summary and l1_summary["cicd_score"] is not None:
            findings.append(f"CI/CD score: {l1_summary.get('cicd_score')}")
        if "tq_score" in l1_summary:
            findings.append(
                f"Test quality: {l1_summary.get('tq_score')} "
                f"(fake tests: {l1_summary.get('fake_tests', 0)}, "
                f"assertion density: {l1_summary.get('avg_assertion_density', 0.0)})"
            )
        if "type_score" in l1_summary:
            findings.append(
                f"Type safety score: {l1_summary.get('type_score')} "
                f"(errors: {l1_summary.get('type_errors', 0)})"
            )
        if "unpinned_dependencies" in l1_summary:
            findings.append(f"Unpinned dependencies: {l1_summary.get('unpinned_dependencies')}")
        if "coverage_pct" in l1_summary:
            findings.append(
                f"Test coverage: {l1_summary.get('coverage_pct')}% "
                f"({l1_summary.get('coverage_reason')}, {l1_summary.get('coverage_isolation')})"
            )
        if "duplication_pct" in l1_summary:
            findings.append(
                f"Code duplication: {l1_summary.get('duplication_pct')}% "
                f"(measured: {l1_summary.get('duplication_measured')})"
            )
        if "tech_debt_measured" in l1_summary:
            findings.append(f"Tech debt measured: {l1_summary.get('tech_debt_measured')}")
        return findings

    async def _evaluate_category_with_limit(
        self,
        semaphore: asyncio.Semaphore,
        category_key: str,
        evidence: CategoryEvidence,
    ) -> RubricVerdict:
        """Evaluates a dynamic category under concurrency limiting with exponential backoff retry."""
        import secrets

        async with semaphore:
            for attempt in range(3):
                try:
                    return await self.rubric.evaluate(category_key, evidence)
                except Exception as exc:
                    err_str = str(exc).lower()
                    if "429" in err_str or "rate" in err_str or "quota" in err_str:
                        backoff = (2 ** attempt) + secrets.SystemRandom().uniform(0.1, 0.5)
                        logger.warning(
                            f"Rate limit hit evaluating '{category_key}', retrying in {backoff:.2f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    return RubricVerdict(
                        level=None,
                        justification=None,
                        evaluated=False,
                        reason=f"evaluation_error: {exc}",
                    )
            return RubricVerdict(
                level=None,
                justification=None,
                evaluated=False,
                reason="rate_limit_exhausted",
            )

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

        concurrency_limit = asyncio.Semaphore(2)
        l2_tasks = [
            self._evaluate_category_with_limit(
                concurrency_limit,
                cat.key,
                self._build_category_evidence(
                    path,
                    files,
                    cat.key,
                    layer1_data.get("coverage"),
                    ev_files,
                    ev_findings,
                    layer1_data=layer1_data,
                    l1_summary=l1_summary,
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
                    "evaluated": verdict.evaluated,
                    "reason": verdict.reason,
                    "citation_warning": verdict.citation_warning,
                },
            }
            for cat, verdict in zip(profile.dynamic_categories, verdicts, strict=False)
        ]

    async def run_full_audit(
        self,
        repo_path: str | Path,
        full_history: bool = False,
        incremental: bool = False,
        since_commit: str | None = None,
    ) -> dict[str, Any]:
        """Runs an end-to-end WARDEN audit on the given repository path."""
        path = Path(repo_path)
        logger.info(f"Starting full audit on {path.resolve()} (full_history={full_history}, incremental={incremental})")

        try:
            # 1. Discover files (full repo or incremental diff)
            if incremental or since_commit:
                from core.services.git_diff_analyzer import GitDiffAnalyzer
                diff_analyzer = GitDiffAnalyzer()
                changed_files = diff_analyzer.get_changed_files(path, since_commit=since_commit)
                all_discovered = set(discover_source_files(path))
                files = [f for f in changed_files if f in all_discovered]
                logger.info(f"Incremental mode: {len(files)} changed source files detected (out of {len(all_discovered)} total)")
                if not files:
                    # Fallback to all files if no git changes detected
                    files = list(all_discovered)
            else:
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

            # 4. Load config and aggregate Scores
            from core.config.warden_config import WardenConfig
            config = WardenConfig.load_from_repo(path)
            self.scorecard.layer1_weight = config.scoring.layer1_weight
            self.scorecard.layer2_weight = config.scoring.layer2_weight

            logger.info("Aggregating scorecard...")
            scorecard_result = self.scorecard.calculate(
                layer1_data, layer2_data, category_weights=config.scoring.category_weights
            )

            # 5. Detect AI / Vibe-Coding indicators
            from core.services.vibe_detector import VibeCodingDetector
            vibe_detector = VibeCodingDetector()
            vibe_result = vibe_detector.analyze_repository(path, files=files)

            return {
                "scorecard": scorecard_result.__dict__,
                "profile_signature": profile.signature,
                "matched_categories": [c.key for c in profile.dynamic_categories],
                "confidence": getattr(profile, "confidence", getattr(profile, "profiling_confidence", "normal")),
                "min_score_gate": config.scoring.min_score_gate,
                "vibe_coding": vibe_result.to_dict(),
                "critical_findings": CriticalFindings.from_layer1(layer1_data).to_dict(),
                "test_quality_meta": layer1_data.get("test_quality_meta", {}),
                "tech_debt": layer1_data.get("tech_debt", {}),
                "complexity": layer1_data.get("complexity", {}),
            }
        finally:
            # Always ensure dependency health client is closed
            await self.dependencies.close()
