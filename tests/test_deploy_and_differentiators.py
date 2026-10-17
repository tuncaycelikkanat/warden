"""Tests for Phase 0-3 Deployment Hardening and Vibe-Coding Firewall Differentiators."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import core.api.auth as auth_mod
from core.api.auth import create_access_token
from core.main import app
from core.services.agent_init_service import AgentInitService
from core.services.architecture_boundary import ArchitectureBoundaryEnforcer, BoundaryRule
from core.services.hallucination_detector import HallucinatedAPIDetector
from mcp_server.server import call_tool, list_tools

client = TestClient(app)


class TestPreDeploySecurityHardening:
    """Tests for Faz 0 API security, path traversal protection, and async audit jobs."""

    def test_scan_blocks_forbidden_system_paths(self) -> None:
        resp = client.post("/api/v1/scan", json={"file_path": "/etc/passwd"})
        assert resp.status_code == 400
        assert "yasaklı" in resp.json()["detail"]

    def test_scan_and_audit_enforce_jwt_when_auth_enabled(self, tmp_path: Path) -> None:
        sample = tmp_path / "app.py"
        sample.write_text("x = 1\n", encoding="utf-8")

        prev = auth_mod.AUTH_ENABLED
        auth_mod.AUTH_ENABLED = True
        try:
            # Unauthenticated request should fail with 401
            r1 = client.post("/api/v1/scan", json={"file_path": str(sample)})
            assert r1.status_code == 401

            r2 = client.post("/api/v1/audit", json={"repo_path": str(tmp_path)})
            assert r2.status_code == 401

            # Authenticated request with valid JWT should succeed
            token = create_access_token(subject="ci-bot", role="auditor")
            headers = {"Authorization": f"Bearer {token}"}
            r3 = client.post("/api/v1/scan", json={"file_path": str(sample)}, headers=headers)
            assert r3.status_code == 200
            assert "risk_level" in r3.json()
        finally:
            auth_mod.AUTH_ENABLED = prev

    def test_async_audit_job_lifecycle(self, tmp_path: Path) -> None:
        mock_res = {"scorecard": {"total_score": 92.0, "grade": "A"}}
        with (
            patch("core.services.orchestrator.AuditOrchestrator.run_full_audit", new_callable=AsyncMock) as mock_orch,
            patch("core.services.report.AuditReportService.save_to_db", return_value=77),
            patch("core.services.report.AuditReportService.generate_markdown", return_value="/tmp/rep.md"),
        ):
            mock_orch.return_value = mock_res
            resp = client.post("/api/v1/audit/async", json={"repo_path": str(tmp_path), "incremental": True})
            assert resp.status_code == 202
            data = resp.json()
            job_id = data["job_id"]

            status_resp = client.get(f"/api/v1/audit/jobs/{job_id}")
            assert status_resp.status_code == 200
            job_data = status_resp.json()
            assert job_data["status"] == "completed"
            assert job_data["db_id"] == 77
            assert job_data["scorecard"]["total_score"] == 92.0


class TestAgentInitService:
    """Tests for `warden init --agent` native AI coding assistant bootstrapper."""

    def test_initialize_all_agents(self, tmp_path: Path) -> None:
        service = AgentInitService()
        res = service.initialize(tmp_path, agent="all")

        assert set(res.agents_configured) == {"claude", "cursor", "windsurf"}
        assert (tmp_path / "warden.config.yaml").exists()
        assert (tmp_path / ".claude" / "settings.json").exists()
        assert (tmp_path / ".cursor" / "mcp.json").exists()
        assert (tmp_path / ".cursor" / "rules" / "warden-governance.mdc").exists()
        assert (tmp_path / ".windsurfrules").exists()

        claude_cfg = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert "warden" in claude_cfg["mcpServers"]
        assert "PostToolUse" in claude_cfg["hooks"]

    def test_initialize_invalid_agent_raises(self, tmp_path: Path) -> None:
        service = AgentInitService()
        with pytest.raises(ValueError, match="Desteklenmeyen ajan tipi"):
            service.initialize(tmp_path, agent="unknown-agent")


class TestArchitectureBoundaryEnforcer:
    """Tests for declarative Architecture-as-Code layer boundary enforcement."""

    def test_detects_forbidden_cross_layer_imports(self, tmp_path: Path) -> None:
        api_dir = tmp_path / "core" / "api"
        api_dir.mkdir(parents=True)
        bad_route = api_dir / "users.py"
        bad_route.write_text("import sqlite3\nfrom fastapi import APIRouter\n", encoding="utf-8")

        enforcer = ArchitectureBoundaryEnforcer(
            rules=[
                BoundaryRule(
                    source="core/api/**",
                    forbid_imports=["sqlite3"],
                    reason="API layer cannot import sqlite3 directly.",
                )
            ]
        )
        result = enforcer.check_repository(tmp_path)
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].actual_import == "sqlite3"
        assert result.violations[0].file == "core/api/users.py"

    def test_warden_own_repository_passes_boundary_contracts(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        enforcer = ArchitectureBoundaryEnforcer()
        result = enforcer.check_repository(repo_root)
        assert result.passed, f"Violations found in WARDEN repo: {result.to_dict()}"
        assert result.score == 100.0


class TestHallucinatedAPIDetector:
    """Tests for AI-hallucinated stdlib symbols, methods, and keyword arguments."""

    def test_detects_hallucinated_imports_methods_and_kwargs(self) -> None:
        code = """
import json
import requests
from pathlib import Path
from json import loads_safe

def fetch_data(url: str):
    p = Path("config.json")
    raw = p.read_file()
    resp = requests.get(url, timeout_ms=3000)
    return json.parse(raw)
"""
        detector = HallucinatedAPIDetector()
        findings = detector.analyze_code(code, file_label="ai_generated.py")
        types = {f.hallucination_type for f in findings}
        symbols = {f.symbol for f in findings}

        assert "MISSING_STDLIB_SYMBOL" in types
        assert "json.loads_safe" in symbols
        assert "MISSING_MODULE_ATTR" in types
        assert "json.parse" in symbols
        assert "HALLUCINATED_METHOD" in types
        assert "p.read_file()" in symbols
        assert "HALLUCINATED_KWARG" in types
        assert "requests.get(timeout_ms=...)" in symbols

    def test_clean_code_produces_zero_findings(self) -> None:
        clean_code = """
import json
from pathlib import Path

def load_cfg(path_str: str) -> dict:
    p = Path(path_str)
    return json.loads(p.read_text(encoding="utf-8"))
"""
        detector = HallucinatedAPIDetector()
        findings = detector.analyze_code(clean_code, file_label="clean.py")
        assert findings == []


class TestMCPDifferentiatorTools:
    """Tests for newly exposed MCP server tools."""

    @pytest.mark.asyncio
    async def test_mcp_tools_registered_and_callable(self, tmp_path: Path) -> None:
        tools = await list_tools()
        names = {t.name for t in tools}
        assert "warden_check_boundaries" in names
        assert "warden_check_hallucinations" in names

        (tmp_path / "clean.py").write_text("import json\nx = json.dumps({'a': 1})\n", encoding="utf-8")

        b_res = await call_tool("warden_check_boundaries", {"repo_path": str(tmp_path)})
        b_data = json.loads(b_res[0].text)
        assert b_data["passed"] is True

        h_res = await call_tool("warden_check_hallucinations", {"repo_path": str(tmp_path)})
        h_data = json.loads(h_res[0].text)
        assert h_data["findings_count"] == 0


class TestCLIDispatchNewCommands:
    """Tests CLI parser and dispatcher integration for init, check-boundaries, and check-hallucinations."""

    def test_cli_init_boundaries_and_hallucinations_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from core.cli import build_argument_parser, dispatch_cli

        parser = build_argument_parser()

        # 1. warden init <tmp_path> --agent cursor --json
        args_init = parser.parse_args(["init", str(tmp_path), "--agent", "cursor", "--json"])
        dispatch_cli(args_init)
        init_out = json.loads(capsys.readouterr().out)
        assert init_out["agents_configured"] == ["cursor"]

        # Create a clean python file in tmp_path
        (tmp_path / "app.py").write_text("import json\nx = json.loads('{}')\n", encoding="utf-8")

        # 2. warden check-boundaries <tmp_path> --json
        args_bound = parser.parse_args(["check-boundaries", str(tmp_path), "--json"])
        dispatch_cli(args_bound)
        bound_out = json.loads(capsys.readouterr().out)
        assert bound_out["passed"] is True

        # 3. warden check-hallucinations <tmp_path> --json
        args_halluc = parser.parse_args(["check-hallucinations", str(tmp_path), "--json"])
        dispatch_cli(args_halluc)
        halluc_out = json.loads(capsys.readouterr().out)
        assert halluc_out["findings_count"] == 0

