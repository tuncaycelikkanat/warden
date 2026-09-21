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
from core.services.resilience import ResilienceAnalyzerService
from core.services.rubric import CategoryEvidence, CodeSnippet, RubricEvaluatorService
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
            "docker_readiness": docker_res.score if (docker_res.applicable and docker_res.measured) else None,
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
            },
            "commit_hygiene": commit_res.score if commit_res.measured else None,
            "commit_hygiene_meta": {
                "score": commit_res.score,
                "measured": commit_res.measured,
                "reason": commit_res.reason,
                "total_commits": commit_res.total_commits,
                "bad_commits": commit_res.bad_commits,
                "bad_ratio": commit_res.bad_ratio,
                "avg_length": commit_res.avg_length,
            },
        }

        l1_summary = {
            "lint_errors": lint_res.error_count,
            "lint_score": lint_res.score,
            "lint_density": lint_res.density_per_kloc,
            "docker_score": docker_res.score if (docker_res.applicable and docker_res.measured) else None,
            "commit_score": commit_res.score if commit_res.measured else None,
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

    @staticmethod
    def _safe_read_file(file_path: Path, max_chars: int = 150000) -> str:
        """Safely reads file content as string."""
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""

    @staticmethod
    def _extract_snippet(
        file_rel: str,
        content: str,
        match_pattern: re.Pattern[str],
        context: str,
        max_lines: int = 15,
    ) -> CodeSnippet | None:
        """Extracts a focused code snippet around the first pattern match."""
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if match_pattern.search(line):
                start = max(0, idx - 2)
                end = min(len(lines), start + max_lines)
                snippet_code = "\n".join(lines[start:end])
                return CodeSnippet(
                    file=file_rel,
                    line_start=start + 1,
                    line_end=end,
                    code=snippet_code,
                    context=context,
                )
        return None

    def _ev_llm(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for LLM integration, prompt defense, and resilience."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        llm_providers: set[str] = set()
        has_sanitization = False
        has_resilience = False
        has_cost_latency = False

        provider_pattern = re.compile(
            r"\b(google\.genai|genai\.Client|openai|Anthropic|langchain|llama_index|litellm|transformers)\b",
            re.IGNORECASE,
        )
        sanitizer_pattern = re.compile(
            r"\b(PromptSanitizer|sanitize.*prompt|injection.*defense|guardrails|nemo_guardrails|promptfoo)\b",
            re.IGNORECASE,
        )
        resilience_pattern = re.compile(
            r"\b(models_to_try|fallback|retry|tenacity|Backoff)\b",
            re.IGNORECASE,
        )
        tracking_pattern = re.compile(
            r"\b(total_tokens|prompt_tokens|usage_metadata|latency_sec|audit_log)\b",
            re.IGNORECASE,
        )

        for f in files:
            rel = str(f.relative_to(path))
            content = self._safe_read_file(f)
            if not content:
                continue

            matches = provider_pattern.findall(content)
            if matches:
                matched_files.append(rel)
                for m in matches:
                    llm_providers.add(m)

            if sanitizer_pattern.search(content):
                has_sanitization = True
                matched_files.append(rel)
                if not any(s.context == "LLM Prompt Sanitization / Guardrail" for s in snippets):
                    snip = self._extract_snippet(
                        rel, content, sanitizer_pattern, "LLM Prompt Sanitization / Guardrail"
                    )
                    if snip:
                        snippets.append(snip)

            if resilience_pattern.search(content) and (
                matches or any(k in rel.lower() for k in ["llm", "rubric", "ai", "model"])
            ):
                has_resilience = True
                matched_files.append(rel)

            if tracking_pattern.search(content) and (
                matches or any(k in rel.lower() for k in ["llm", "rubric", "ai", "model"])
            ):
                has_cost_latency = True
                matched_files.append(rel)

            if len(snippets) == 0 and matches:
                snip = self._extract_snippet(rel, content, provider_pattern, "LLM Client invocation")
                if snip:
                    snippets.append(snip)

        if llm_providers:
            findings.append(
                f"LLM Providers: Detected SDK integrations ({', '.join(sorted(llm_providers))}) in {len(matched_files)} files"
            )
        if has_sanitization:
            findings.append("LLM Security: Prompt sanitization, input filtering, or guardrail mechanisms detected")
        elif llm_providers:
            findings.append("LLM Security: No dedicated prompt sanitization or injection guardrails observed")

        if has_resilience:
            findings.append("LLM Resilience: Multi-model fallback, retry loops, or backoff error handling detected")
        if has_cost_latency:
            findings.append("LLM Observability: Token usage metrics, latency tracking, or structured LLM audit logging detected")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_concurrency(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for concurrency safety, async loops, and locks."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        concurrency_primitives: set[str] = set()
        sync_mechanisms: set[str] = set()

        gather_pattern = re.compile(
            r"\b(asyncio\.gather|asyncio\.create_task|TaskGroup|ThreadPoolExecutor|ProcessPoolExecutor)\b"
        )
        sync_pattern = re.compile(
            r"\b(asyncio\.Lock|threading\.Lock|RLock|Semaphore|Queue|asyncio\.Queue)\b"
        )

        for f in files:
            rel = str(f.relative_to(path))
            content = self._safe_read_file(f)
            if not content:
                continue

            prims = gather_pattern.findall(content)
            syncs = sync_pattern.findall(content)

            if prims or syncs or "async def " in content:
                matched_files.append(rel)
                for p in prims:
                    concurrency_primitives.add(p)
                for s in syncs:
                    sync_mechanisms.add(s)

                if len(snippets) == 0 and prims:
                    snip = self._extract_snippet(rel, content, gather_pattern, "Concurrency coordination primitive")
                    if snip:
                        snippets.append(snip)
                elif len(snippets) < 2 and syncs:
                    snip = self._extract_snippet(rel, content, sync_pattern, "Concurrency synchronization lock/queue")
                    if snip:
                        snippets.append(snip)

        if concurrency_primitives:
            findings.append(
                f"Concurrency Primitives: Detected async/parallel execution ({', '.join(sorted(concurrency_primitives))}) across {len(matched_files)} files"
            )
        elif matched_files:
            findings.append(f"Asynchronous Execution: Asynchronous coroutines (async def) present across {len(matched_files)} files")

        if sync_mechanisms:
            findings.append(f"Synchronization Safety: Thread/task synchronization primitives detected ({', '.join(sorted(sync_mechanisms))})")
        elif concurrency_primitives:
            findings.append("Synchronization Safety: Zero explicit locks or synchronization primitives detected (verify shared state isolation)")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_api(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for API design, routes, schema validation, and error handling."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        frameworks: set[str] = set()
        has_schemas = False
        has_typed_exceptions = False
        has_auth_or_ratelimit = False

        route_pattern = re.compile(
            r"(@\w+\.(get|post|put|delete|patch|options|head)|urlpatterns\s*=|@api_view|app\.(get|post|put|delete)\()",
            re.IGNORECASE,
        )
        schema_pattern = re.compile(r"(class\s+\w+\(.*(?:BaseModel|Schema).*\):|@dataclass)", re.IGNORECASE)
        exc_pattern = re.compile(r"(raise\s+HTTPException|status_code\s*=|status\.HTTP_)", re.IGNORECASE)
        sec_pattern = re.compile(r"\b(Depends|HTTPBearer|OAuth2|rate_limit|Limiter|slowapi)\b", re.IGNORECASE)

        for f in files:
            rel = str(f.relative_to(path))
            if not any(
                k in rel.lower()
                for k in ["api", "router", "endpoint", "controller", "view", "server", "main", "app", "schema", "route"]
            ):
                continue

            content = self._safe_read_file(f)
            if not content:
                continue

            file_has_api = False
            if "fastapi" in content.lower() or "apirouter" in content.lower():
                frameworks.add("FastAPI")
                file_has_api = True
            elif "flask" in content.lower() or "blueprint" in content.lower():
                frameworks.add("Flask")
                file_has_api = True
            elif "django" in content.lower() or "rest_framework" in content.lower():
                frameworks.add("Django REST")
                file_has_api = True
            elif "express" in content.lower():
                frameworks.add("Express")
                file_has_api = True

            if route_pattern.search(content):
                file_has_api = True

            if schema_pattern.search(content):
                has_schemas = True
                file_has_api = True

            if exc_pattern.search(content):
                has_typed_exceptions = True
                file_has_api = True

            if sec_pattern.search(content):
                has_auth_or_ratelimit = True
                file_has_api = True

            if file_has_api:
                matched_files.append(rel)
                if len(snippets) == 0 and route_pattern.search(content):
                    snip = self._extract_snippet(rel, content, route_pattern, "API route endpoint declaration")
                    if snip:
                        snippets.append(snip)

        if frameworks:
            findings.append(
                f"API Framework: {', '.join(sorted(frameworks))} routing detected across {len(matched_files)} files"
            )
        elif matched_files:
            findings.append(f"API Routing: Endpoints and handlers detected across {len(matched_files)} files")

        if has_schemas:
            findings.append("API Validation: Structured schema validation (Pydantic BaseModel / Dataclass / Serializers) detected")
        if has_typed_exceptions:
            findings.append("API Error Handling: Explicit HTTP status codes and typed HTTPException responses detected")
        if has_auth_or_ratelimit:
            findings.append("API Security: Authentication dependencies, security guards, or rate limiting detected")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_devops(
        self,
        path: Path,
        files: list[Path],
        layer1_data: dict[str, Any] | None = None,
        l1_summary: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for DevOps, containerization, CI/CD, and IaC deployment."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        # 1. Docker / Containerization
        docker_candidates = [
            "Dockerfile", "Dockerfile.prod", "Dockerfile.dev",
            "docker-compose.yml", "docker-compose.yaml", "compose.yaml"
        ]
        for c in docker_candidates:
            if (path / c).exists():
                matched_files.append(c)

        dockerfile_path = path / "Dockerfile"
        if dockerfile_path.exists():
            df_content = self._safe_read_file(dockerfile_path)
            has_multistage = len(re.findall(r"^FROM\s+", df_content, re.MULTILINE | re.IGNORECASE)) > 1
            has_user = bool(re.search(r"^USER\s+(?!root\b)\S+", df_content, re.MULTILINE | re.IGNORECASE))
            has_health = bool(re.search(r"^HEALTHCHECK\s+(?!NONE\b)", df_content, re.MULTILINE | re.IGNORECASE))
            findings.append(
                f"Containerization: Dockerfile present (multi-stage={has_multistage}, non-root-user={has_user}, healthcheck={has_health})"
            )
            snip = self._extract_snippet(
                "Dockerfile", df_content,
                re.compile(r"^(USER|HEALTHCHECK|FROM\s+.*\s+AS)\b", re.MULTILINE | re.IGNORECASE),
                "Dockerfile security/stage directive"
            )
            if not snip:
                snip = self._extract_snippet(
                    "Dockerfile", df_content,
                    re.compile(r"^FROM\s+", re.MULTILINE | re.IGNORECASE),
                    "Dockerfile base image"
                )
            if snip:
                snippets.append(snip)

        # 2. CI/CD Pipelines
        ci_patterns = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".circleci", "azure-pipelines.yml"]
        ci_found: list[str] = []
        for pat in ci_patterns:
            target = path / pat
            if target.is_dir():
                for ci_file in target.glob("*.y*ml"):
                    rel = str(ci_file.relative_to(path))
                    ci_found.append(rel)
                    matched_files.append(rel)
            elif target.is_file():
                rel = str(target.relative_to(path))
                ci_found.append(rel)
                matched_files.append(rel)

        if ci_found:
            findings.append(f"CI/CD: Found {len(ci_found)} workflow pipeline(s): {', '.join(ci_found[:3])}")
            first_ci = path / ci_found[0]
            ci_content = self._safe_read_file(first_ci)
            snip = self._extract_snippet(
                ci_found[0], ci_content,
                re.compile(r"^\s*(jobs|steps|stages):", re.MULTILINE),
                "CI pipeline workflow definition"
            )
            if snip:
                snippets.append(snip)

        # 3. Infrastructure as Code (IaC) & Cloud
        iac_files: list[str] = []
        for f in files:
            rel = str(f.relative_to(path))
            if f.suffix in [".tf", ".hcl"] or (
                any(k in rel.lower() for k in ["k8s", "kubernetes", "helm"]) and f.suffix in [".yaml", ".yml"]
            ):
                iac_files.append(rel)
                matched_files.append(rel)

        if iac_files:
            findings.append(f"IaC: Infrastructure-as-Code detected ({len(iac_files)} file(s)): {', '.join(iac_files[:3])}")
            iac_sample = path / iac_files[0]
            iac_content = self._safe_read_file(iac_sample)
            snip = self._extract_snippet(
                iac_files[0], iac_content,
                re.compile(r'^\s*(resource|module|variable|apiVersion)\b', re.MULTILINE),
                "IaC resource configuration"
            )
            if snip:
                snippets.append(snip)

        # 4. Secrets & Configuration
        env_files = [e for e in [".env.example", ".env.template", ".env.dist"] if (path / e).exists()]
        if env_files:
            matched_files.extend(env_files)
            findings.append(f"Configuration: Environment variable template present ({', '.join(env_files)})")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_architecture(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for layered architecture, modularity, and interfaces."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        recognized_layers = ["domain", "models", "services", "repositories", "controllers", "api", "infra", "infrastructure", "adapters"]
        detected_layers: set[str] = set()

        interface_pattern = re.compile(r"(class\s+\w+\(.*(?:ABC|Protocol).*\):|@abstractmethod)", re.IGNORECASE)

        for f in files:
            rel = str(f.relative_to(path))
            parts = [p.lower() for p in Path(rel).parts]
            for layer in recognized_layers:
                if layer in parts:
                    detected_layers.add(layer)
                    matched_files.append(rel)

            content = self._safe_read_file(f)
            if interface_pattern.search(content):
                matched_files.append(rel)
                if len(snippets) == 0:
                    snip = self._extract_snippet(rel, content, interface_pattern, "Architectural boundary / Interface contract")
                    if snip:
                        snippets.append(snip)

        if detected_layers:
            findings.append(f"Layered Architecture: Clear separation into domain layers ({', '.join(sorted(detected_layers))})")
        if snippets:
            findings.append("Modularity & Inversion: Abstract base classes / typing Protocols defined for boundary decoupling")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_frontend_ux(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for Frontend UX, state management, components, and a11y."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        component_extensions = {".tsx", ".jsx", ".vue", ".svelte"}
        ui_files = [str(f.relative_to(path)) for f in files if f.suffix in component_extensions or f.name == "package.json"]
        matched_files.extend(ui_files)

        state_tools: set[str] = set()
        a11y_matches = 0
        state_pattern = re.compile(r"\b(useDispatch|createSlice|create\(|defineStore|useContext|useState|useReducer)\b")
        a11y_pattern = re.compile(r"(aria-[a-z]+|role=|<main>|<nav>|<header>|<footer>|alt=)", re.IGNORECASE)

        for f in files:
            if f.suffix not in component_extensions and f.suffix not in {".html", ".js", ".ts"}:
                continue
            rel = str(f.relative_to(path))
            content = self._safe_read_file(f)
            if not content:
                continue

            states = state_pattern.findall(content)
            for s in states:
                state_tools.add(s)

            a11y_count = len(a11y_pattern.findall(content))
            a11y_matches += a11y_count

            if len(snippets) == 0 and (states or a11y_count > 0):
                target_pat = state_pattern if states else a11y_pattern
                snip = self._extract_snippet(rel, content, target_pat, "Frontend state / UI component")
                if snip:
                    snippets.append(snip)

        if ui_files:
            findings.append(f"UI Components: Detected {len(ui_files)} component/frontend files")
        if state_tools:
            findings.append(f"State Management: Predictable state hooks / store patterns detected ({', '.join(sorted(state_tools)[:4])})")
        if a11y_matches > 0:
            findings.append(f"Accessibility (a11y): {a11y_matches} semantic HTML elements or aria attributes detected")

        return list(dict.fromkeys(matched_files)), findings, snippets

    def _ev_quantitative_logic(self, path: Path, files: list[Path]) -> tuple[list[str], list[str], list[CodeSnippet]]:
        """Collects dynamic evidence for quantitative modeling, validation, backtesting, and risk metrics."""
        matched_files: list[str] = []
        findings: list[str] = []
        snippets: list[CodeSnippet] = []

        metrics_found: set[str] = set()
        validation_found: set[str] = set()

        metric_pattern = re.compile(r"\b(sharpe|sortino|max_drawdown|drawdown|calmar|cagr|win_rate)\b", re.IGNORECASE)
        val_pattern = re.compile(r"\b(train_test_split|TimeSeriesSplit|cross_val_score|walk_forward|out_of_sample|KFold)\b", re.IGNORECASE)
        bt_pattern = re.compile(r"\b(backtest|backtrader|zipline|vectorbt|ccxt|simulate)\b", re.IGNORECASE)

        for f in files:
            rel = str(f.relative_to(path))
            content = self._safe_read_file(f)
            if not content:
                continue

            m_metrics = metric_pattern.findall(content)
            m_val = val_pattern.findall(content)
            m_bt = bt_pattern.findall(content)

            if m_metrics or m_val or m_bt:
                matched_files.append(rel)
                for m in m_metrics:
                    metrics_found.add(m.lower())
                for v in m_val:
                    validation_found.add(v)

                if len(snippets) == 0:
                    pat = metric_pattern if m_metrics else (val_pattern if m_val else bt_pattern)
                    snip = self._extract_snippet(rel, content, pat, "Quantitative metric / validation logic")
                    if snip:
                        snippets.append(snip)

        if bt_pattern and matched_files:
            findings.append(f"Quantitative Modeling: Algorithmic simulation / calculation files detected ({len(matched_files)} files)")
        if metrics_found:
            findings.append(f"Risk & Performance Metrics: Quantitative performance metrics computed ({', '.join(sorted(metrics_found))})")
        if validation_found:
            findings.append(f"Statistical Validation: Overfitting prevention & validation splits detected ({', '.join(sorted(validation_found))})")

        return list(dict.fromkeys(matched_files)), findings, snippets

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
