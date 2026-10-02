"""Unit tests for WARDEN Model Context Protocol (MCP) server tools."""

import asyncio
import json
from pathlib import Path

import pytest

from mcp_server.server import call_tool, list_tools


class TestMCPServer:
    def test_list_tools_contains_all_nine_tools(self) -> None:
        tools = asyncio.run(list_tools())
        names = {t.name for t in tools}

        expected = {
            "security_scan",
            "check_package",
            "evaluate_agent_action",
            "run_full_audit",
            "warden_risk_score",
            "warden_fix_suggestion",
            "warden_check_cycles",
            "warden_check_entropy",
            "warden_audit",
        }
        assert expected.issubset(names)
        assert len(tools) == 9

    def test_warden_risk_score_clean_code(self) -> None:
        clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        res = asyncio.run(call_tool("warden_risk_score", {"code_snippet": clean_code}))
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert data["risk_score"] < 25.0
        assert data["risk_level"] == "LOW"
        assert data["syntax_valid"] is True

    def test_warden_risk_score_with_secret(self) -> None:
        dirty_code = 'AWS_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYq8194XzpQ"\n'
        res = asyncio.run(call_tool("warden_risk_score", {"code_snippet": dirty_code}))
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert data["secret_findings_count"] >= 1
        assert data["risk_score"] >= 20.0

    def test_warden_risk_score_with_syntax_error(self) -> None:
        invalid_code = "def broken(a, b\n    return\n"
        res = asyncio.run(call_tool("warden_risk_score", {"code_snippet": invalid_code}))
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert data["syntax_valid"] is False
        assert data["risk_score"] >= 50.0

    def test_warden_fix_suggestion_secret(self) -> None:
        res = asyncio.run(
            call_tool(
                "warden_fix_suggestion",
                {
                    "issue_type": "secret_leak",
                    "code_snippet": 'api_key = "AIzaSyD-sample1234567890"',
                },
            )
        )
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert "os.getenv" in data["suggested_fix"]
        assert "ortam değişkeni" in data["explanation"].lower() or "environment" in data["explanation"].lower()

    def test_warden_fix_suggestion_sql_injection(self) -> None:
        res = asyncio.run(
            call_tool(
                "warden_fix_suggestion",
                {
                    "issue_type": "sql_injection",
                    "code_snippet": 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
                },
            )
        )
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert "execute" in data["suggested_fix"]
        assert "parametreli" in data["explanation"].lower()

    def test_warden_fix_suggestion_eval(self) -> None:
        res = asyncio.run(
            call_tool(
                "warden_fix_suggestion",
                {
                    "issue_type": "eval_execution",
                    "code_snippet": "result = eval(user_str)",
                },
            )
        )
        assert len(res) == 1
        data = json.loads(res[0].text)
        assert "ast.literal_eval" in data["suggested_fix"]

    def test_warden_check_cycles_tool(self, tmp_path: Path) -> None:
        # Create a tiny 2-file circular import
        f1 = tmp_path / "mod_a.py"
        f2 = tmp_path / "mod_b.py"
        f1.write_text("import mod_b\n", encoding="utf-8")
        f2.write_text("import mod_a\n", encoding="utf-8")

        res = asyncio.run(call_tool("warden_check_cycles", {"repo_path": str(tmp_path)}))
        assert len(res) == 1
        text = res[0].text
        assert "mod_a" in text
        assert "mod_b" in text

    def test_warden_check_entropy_tool(self, tmp_path: Path) -> None:
        target = tmp_path / "auth.py"
        target.write_text('CLIENT_SECRET = "4eC39HqLyjWDarjtT1zdp7dc"\n', encoding="utf-8")

        res = asyncio.run(call_tool("warden_check_entropy", {"repo_path": str(tmp_path)}))
        assert len(res) == 1
        text = res[0].text
        assert "CLIENT_SECRET" in text or "Clean" in text

    def test_unknown_tool_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            asyncio.run(call_tool("non_existent_tool", {}))
