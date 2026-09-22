from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.orchestrator import AuditOrchestrator
from core.services.profiler import MatchedCategory, ProjectProfile
from core.services.rubric import RubricVerdict


def test_orchestrator_ev_helpers(tmp_path: Path):
    orch = AuditOrchestrator()
    f1 = tmp_path / "rubric.py"
    f1.write_text("import google.genai\nfrom google.genai import types\nclient = genai.Client()\n")
    f2 = tmp_path / "api.py"
    f2.write_text("from fastapi import FastAPI, APIRouter\nrouter = APIRouter()\n@router.get('/health')\ndef health(): return {'status': 'ok'}\n")
    f3 = tmp_path / "worker.py"
    f3.write_text("import asyncio\nasync def run():\n    await asyncio.gather()\n")
    f4 = tmp_path / "Dockerfile"
    f4.write_text("FROM python:3.12-slim\nUSER appuser\nHEALTHCHECK CMD curl http://localhost/health\n")
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    f5 = models_dir / "user.py"
    f5.write_text("from abc import ABC, abstractmethod\nclass UserInterface(ABC):\n    @abstractmethod\n    def get_id(self): pass\n")

    files = [f1, f2, f3, f4, f5]

    llm_files, llm_findings, llm_snippets = orch._ev_llm(tmp_path, files)
    assert any("rubric.py" in f for f in llm_files)
    assert len(llm_findings) > 0
    assert len(llm_snippets) > 0

    api_files, api_findings, api_snippets = orch._ev_api(tmp_path, files)
    assert any("api.py" in f for f in api_files)
    assert len(api_findings) > 0
    assert len(api_snippets) > 0

    conc_files, conc_findings, conc_snippets = orch._ev_concurrency(tmp_path, files)
    assert any("worker.py" in f for f in conc_files)
    assert len(conc_findings) > 0
    assert len(conc_snippets) > 0

    devops_files, devops_findings, devops_snippets = orch._ev_devops(tmp_path, files)
    assert any("Dockerfile" in f for f in devops_files)
    assert len(devops_findings) > 0
    assert len(devops_snippets) > 0

    arch_files, arch_findings, arch_snippets = orch._ev_architecture(tmp_path, files)
    assert any("user.py" in f for f in arch_files)
    assert len(arch_findings) > 0
    assert len(arch_snippets) > 0


def test_orchestrator_build_category_evidence(tmp_path: Path):
    orch = AuditOrchestrator()
    f1 = tmp_path / "main.py"
    f1.touch()
    files = [f1]

    categories = [
        "llm_integration",
        "api_design",
        "concurrency_safety",
        "devops_deployment",
        "architectural_discipline",
        "frontend_ux",
        "quantitative_logic",
    ]

    for cat in categories:
        evidence = orch._build_category_evidence(
            tmp_path,
            files,
            cat,
            coverage=85.0,
            base_files=["main.py"],
            base_findings=["Base finding"],
        )
        assert hasattr(evidence, "files")
        assert hasattr(evidence, "metrics")
        assert hasattr(evidence, "findings")
        assert hasattr(evidence, "code_snippets")
        assert hasattr(evidence, "evidence_collection_status")
        # Empty repo with only empty main.py has no evidence for specific categories
        assert evidence.evidence_collection_status in ["ok", "no_evidence_found"]


@pytest.mark.asyncio
async def test_orchestrator_run_full_audit_mocked(tmp_path: Path):
    orch = AuditOrchestrator()
    f1 = tmp_path / "app.py"
    f1.write_text("print('hello')")

    # Mock L1 scanners
    mock_l1_data = {
        "security": [],
        "dependencies": [],
        "complexity": {"average_complexity": 2.0, "high_complexity_files": 0},
        "lint": {"error_count": 0},
        "leaks": [],
        "coverage": 85.0,
        "docs": {"docstring_coverage": 90.0},
        "resilience": [],
        "license_compliance": 100.0,
        "type_safety": 100.0,
        "test_quality": 100.0,
        "cicd_presence": 100.0,
        "docker_readiness": 100.0,
        "commit_hygiene": 100.0,
    }
    mock_l1_summary = {
        "lint_errors": 0,
        "docker_score": 100.0,
        "cicd_score": 100.0,
        "tq_score": 100.0,
        "type_score": 100.0,
    }

    mock_profile = ProjectProfile(
        dynamic_categories=[
            MatchedCategory(key="api_design", label="API Design", evidence=[]),
            MatchedCategory(key="devops_deployment", label="DevOps", evidence=[]),
        ],
        signature="abc12345",
        catalog_version="v1.0",
    )

    mock_verdict = RubricVerdict(
        level=9,
        justification="Excellent architecture",
        cited_evidence=["app.py"],
    )

    with patch.object(orch, "_run_l1_scanners", new_callable=AsyncMock) as mock_run_l1, \
         patch.object(orch.profiler, "profile", return_value=mock_profile), \
         patch.object(orch.rubric, "evaluate", new_callable=AsyncMock) as mock_eval:

        mock_run_l1.return_value = (mock_l1_data, mock_l1_summary)
        mock_eval.return_value = mock_verdict

        result = await orch.run_full_audit(tmp_path)

        assert "profile_signature" in result
        assert "scorecard" in result
        assert result["scorecard"]["total_score"] >= 80
        assert result["scorecard"]["layer1_score"] >= 80
        assert result["scorecard"]["layer2_score"] >= 80


@pytest.mark.asyncio
async def test_orchestrator_incremental_audit(tmp_path: Path):
    orch = AuditOrchestrator()
    f1 = tmp_path / "changed.py"
    f1.write_text("a = 1")
    f2 = tmp_path / "unchanged.py"
    f2.write_text("b = 2")

    mock_profile = ProjectProfile(dynamic_categories=[], signature="sig1", catalog_version="v1.0")

    with patch("core.services.git_diff_analyzer.GitDiffAnalyzer.get_changed_files", return_value=[f1]), \
         patch.object(orch, "_run_l1_scanners", new_callable=AsyncMock) as mock_l1, \
         patch.object(orch.profiler, "profile", return_value=mock_profile):
        mock_l1.return_value = ({"coverage": 100.0}, {})
        res = await orch.run_full_audit(tmp_path, incremental=True, since_commit="HEAD~1")
        assert "scorecard" in res
        # Check that changed file was passed to _run_l1_scanners
        passed_files = mock_l1.call_args[0][1]
        assert len(passed_files) == 1
        assert passed_files[0] == f1


@pytest.mark.asyncio
async def test_orchestrator_eval_cat_rate_limit_and_error():
    import asyncio
    orch = AuditOrchestrator()
    sem = asyncio.Semaphore(1)

    # 1. Non-rate-limit evaluation error
    with patch.object(orch.rubric, "evaluate", side_effect=ValueError("Syntax parsing failed")):
        verdict = await orch._evaluate_category_with_limit(sem, "api_design", MagicMock())
        assert verdict.evaluated is False
        assert "evaluation_error" in verdict.reason

    # 2. Rate limit retry recovery
    mock_success = RubricVerdict(level=8, justification="Good", cited_evidence=[])
    with patch.object(orch.rubric, "evaluate", side_effect=[Exception("429 Too Many Requests"), mock_success]):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            verdict = await orch._evaluate_category_with_limit(sem, "api_design", MagicMock())
            assert verdict.level == 8

    # 3. Rate limit exhausted after 3 attempts
    with patch.object(orch.rubric, "evaluate", side_effect=Exception("quota exceeded")):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            verdict = await orch._evaluate_category_with_limit(sem, "api_design", MagicMock())
            assert verdict.evaluated is False
            assert verdict.reason == "rate_limit_exhausted"

