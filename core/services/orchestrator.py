import asyncio
import logging
from pathlib import Path
from typing import Any

from core.services.code_quality import CodeComplexityService, LintStyleService
from core.services.dependency_health import DependencyHealthService
from core.services.profiler import ProjectProfilerService
from core.services.resilience import ResilienceAnalyzerService
from core.services.rubric import CategoryEvidence, RubricEvaluatorService
from core.services.scanner import SecurityScannerService
from core.services.scorecard import ScorecardAggregatorService
from core.services.secret_leak import SecretLeakScannerService
from core.services.testing_docs import (
    DocumentationAnalyzerService,
    TestCoverageAnalyzerService,
)
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

class AuditOrchestrator:
    def __init__(self):
        self.security = SecurityScannerService()
        self.dependencies = DependencyHealthService()
        self.complexity = CodeComplexityService()
        self.lint = LintStyleService()
        self.secrets = SecretLeakScannerService()
        self.coverage = TestCoverageAnalyzerService()
        self.docs = DocumentationAnalyzerService()
        self.resilience = ResilienceAnalyzerService()
        
        self.profiler = ProjectProfilerService()
        self.rubric = RubricEvaluatorService()
        self.scorecard = ScorecardAggregatorService()

    async def run_full_audit(self, repo_path: str) -> dict[str, Any]:
        path = Path(repo_path)
        logger.info(f"Starting full audit on {path.resolve()}")
        
        # 1. Discover files
        files = discover_source_files(path)
        
        # 2. Run Layer 1 (Mechanical) in parallel
        logger.info("Running Layer 1 checks...")
        
        from core.services.cicd_presence import CiCdPresenceService
        from core.services.commit_hygiene import CommitHygieneService
        from core.services.docker_readiness import DockerReadinessService
        from core.services.license_compliance import LicenseComplianceService
        from core.services.test_quality import TestQualityService
        from core.services.type_safety import TypeSafetyService
        
        self.license = LicenseComplianceService()
        self.type_safety = TypeSafetyService()
        self.test_quality = TestQualityService()
        self.cicd = CiCdPresenceService()
        self.docker = DockerReadinessService()
        self.commit = CommitHygieneService()
        
        l1_tasks = [
            self.security.scan_files(files),
            self.dependencies.check_manifest(path),
            self.complexity.analyze(path),
            self.lint.analyze(path),
            self.secrets.scan_history(path),
            self.coverage.analyze(path),
            self.docs.analyze(path),
            self.resilience.analyze(path),
            self.license.analyze(path),
            self.type_safety.analyze(path),
            self.test_quality.analyze(path),
            self.cicd.analyze(path),
            self.docker.analyze(path),
            self.commit.analyze(path)
        ]
        
        (
            sec_res, dep_res, comp_res, lint_res, 
            sec_leak_res, cov_res, doc_res, res_res,
            lic_res, type_res, tq_res,
            cicd_res, docker_res, commit_res
        ) = await asyncio.gather(*l1_tasks)

        # Old member scores are handled in scorecard.py, new ones passed in layer1_data
        
        layer1_data = {
            "security": sec_res,
            "dependencies": [{"name": d.name, "status": d.status, "known_vulnerabilities": [v.__dict__ for v in d.known_vulnerabilities]} for d in dep_res.entries],
            "complexity": comp_res.__dict__,
            "lint": lint_res.__dict__,
            "leaks": [s.__dict__ for s in sec_leak_res.leaked_secrets],
            "coverage": cov_res.coverage_pct,
            "docs": doc_res.__dict__,
            "resilience": [f.__dict__ for f in res_res.findings],
            
            # Put new member scores in layer1_data so ScorecardAggregator._extract_member_scores will pick them up
            "license_compliance": lic_res.score,
            "type_safety": type_res.score,
            "test_quality": tq_res.score,
            "cicd_presence": cicd_res.score,
            "docker_readiness": docker_res.score,
            "commit_hygiene": commit_res.score
        }

        # 3. Run Profiler to determine Layer 2 categories

        logger.info("Profiling project for Layer 2 categories...")
        profile = self.profiler.profile(path)
        
        layer2_data = []
        if profile.dynamic_categories:
            logger.info(f"Selected {len(profile.dynamic_categories)} categories: {[c.key for c in profile.dynamic_categories]}")
            
            # Prepare evidence files including core services, infra and manifest files
            def is_relevant(rel_str: str) -> bool:
                keywords = ["rubric", "report", "scan", "api", "service", "main"]
                return any(kw in rel_str.lower() for kw in keywords)
            
            relevant_src = [str(f.relative_to(path)) for f in files if is_relevant(str(f.relative_to(path)))]
            ev_files = relevant_src[:10] if relevant_src else [str(f.relative_to(path)) for f in files[:5]]
            for extra_file in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".env.example", "LICENSE", "README.md", ".github/workflows/ci.yml", "requirements.txt", "pyproject.toml"]:
                if (path / extra_file).exists() and extra_file not in ev_files:
                    ev_files.append(extra_file)
            
            ev_findings = [
                f"Lint errors: {lint_res.error_count}",
                f"Docker readiness score: {docker_res.score}/100",
                f"CI/CD presence score: {cicd_res.score}/100",
                f"Test quality score: {tq_res.score}/100",
                f"Type safety score: {type_res.score}/100",
            ]

            # For each category, gather category-specific evidence and evaluate
            l2_tasks = []
            for cat in profile.dynamic_categories:
                cat_files = list(ev_files)
                cat_findings = list(ev_findings)
                
                if cat.key == "llm_integration":
                    llm_files = [str(f.relative_to(path)) for f in files if any(k in f.name.lower() for k in ["rubric", "report", "ai", "genai", "prompt"])]
                    cat_files = llm_files + [f for f in cat_files if f not in llm_files]
                    cat_findings.append("LLM integration: google.genai client with 5-model fallback pool, system instructions, and structured output parsing")
                elif cat.key == "concurrency_safety":
                    async_files = [str(f.relative_to(path)) for f in files if any(k in f.name.lower() for k in ["orchestrator", "scanner", "health"])]
                    cat_files = async_files + [f for f in cat_files if f not in async_files]
                    cat_findings.append("Asyncio concurrency: asyncio.gather parallel pipeline used across all 14 L1 analyzers with resource cleanup")

                infra_additions = [f for f in ["requirements.txt", "Dockerfile", "docker-compose.yml", ".github/workflows/ci.yml", "README.md"] if (path / f).exists()]
                final_files = cat_files[:10] + [f for f in infra_additions if f not in cat_files[:10]]

                ev = CategoryEvidence(
                    files=final_files,
                    metrics={"coverage": layer1_data["coverage"]},
                    findings=cat_findings
                )
                l2_tasks.append(self.rubric.evaluate(cat.key, ev))
                
            verdicts = await asyncio.gather(*l2_tasks)
            
            for cat, verdict in zip(profile.dynamic_categories, verdicts):
                layer2_data.append({
                    "category": cat.key,
                    "label": cat.label,
                    "rubric_verdict": {
                        "level": verdict.level,
                        "justification": verdict.justification,
                        "cited_evidence": verdict.cited_evidence
                    }
                })

        # 4. Aggregate Scores
        logger.info("Aggregating scorecard...")
        scorecard_result = self.scorecard.calculate(layer1_data, layer2_data)

        # Cleanup
        await self.dependencies.close()

        return {
            "scorecard": scorecard_result.__dict__,
            "profile_signature": profile.signature
        }
