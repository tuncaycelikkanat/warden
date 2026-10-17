"""Agent Native Guardrails & MCP Bootstrapper for WARDEN.

Configures zero-friction guardrails for AI coding agents:
- Claude Code: `.claude/settings.json` (MCP server + PreToolUse/PostToolUse hooks)
- Cursor: `.cursor/mcp.json` and `.cursor/rules/warden-governance.mdc`
- Windsurf: `.windsurfrules`
- Default `warden.config.yaml` with `architecture_boundaries`
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURSOR_MDC_TEMPLATE = """---
description: WARDEN Autonomous Vibe-Coding & Architectural Governance Rules
globs: "**/*"
alwaysApply: true
---

# 🛡️ WARDEN AI Agent Governance Contract

When generating or modifying code in this repository, you MUST strictly adhere to these engineering invariants enforced by WARDEN:

1. **No Silent Exception Swallowing:** Never write `except:` or `except Exception: pass` / `print()`. Catch specific exceptions and log or re-raise with context.
2. **Mandatory Network Timeouts:** Every `requests.*` or `httpx.*` call MUST include an explicit `timeout=` argument.
3. **Real Unit Test Assertions:** Never write placebo tests (`assert True`, `assert len(x) >= 0`, `assert x == x`) or uninvoked mock checks (`mock.assert_called_once` without `()`).
4. **No Hallucinated APIs or Slopsquatting:** Verify that imported symbols and keyword arguments exist in the target library before committing.
5. **Respect Architectural Boundaries:** Check `warden.config.yaml` `architecture_boundaries` rules. Never bypass service layers from API routes.
6. **Self-Verification via MCP:** Before concluding a coding task, call the `warden_audit` (with `incremental: true`), `warden_check_boundaries`, or `warden_check_hallucinations` MCP tools to verify zero regressions.
"""

DEFAULT_WARDEN_CONFIG_TEMPLATE = """# WARDEN — Central Quality & Vibe-Coding Governance Configuration
version: 1
profile: auto

scoring:
  layer1_weight: 0.60
  layer2_weight: 0.40
  min_score_gate: 75

thresholds:
  min_coverage: 80.0
  max_complexity: 10.0
  max_duplication_pct: 5.0
  min_docstring_pct: 80.0

# Architecture-as-Code Layer Boundary Contracts
architecture_boundaries:
  - source: "core/api/**"
    forbid_imports:
      - "sqlite3"
    reason: "API routes must not execute raw SQLite queries directly; delegate to core/services."
  - source: "core/cli/**"
    forbid_imports:
      - "fastapi"
    reason: "CLI layer must remain decoupled from FastAPI HTTP transport."

ignore:
  paths:
    - .venv/
    - build/
    - dist/
    - node_modules/
    - fixtures/
  rules: []
"""


@dataclass
class AgentInitResult:
    """Summary of files created or updated during agent initialization."""

    target_dir: str
    agents_configured: list[str] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_dir": self.target_dir,
            "agents_configured": self.agents_configured,
            "files_written": self.files_written,
        }


class AgentInitService:
    """Generates native MCP configs, agent hooks, and governance rules for AI coding assistants."""

    SUPPORTED_AGENTS = ("claude", "cursor", "windsurf", "all")

    def initialize(
        self,
        repo_path: Path | str,
        agent: str = "all",
        overwrite: bool = False,
    ) -> AgentInitResult:
        """Initializes agent guardrails in the target repository."""
        root = Path(repo_path).resolve()
        root.mkdir(parents=True, exist_ok=True)

        agent_norm = agent.lower().strip()
        if agent_norm not in self.SUPPORTED_AGENTS:
            raise ValueError(
                f"Desteklenmeyen ajan tipi: '{agent}'. Geçerli değerler: {', '.join(self.SUPPORTED_AGENTS)}"
            )

        targets = ["claude", "cursor", "windsurf"] if agent_norm == "all" else [agent_norm]
        result = AgentInitResult(target_dir=str(root), agents_configured=targets)

        python_cmd = sys.executable or "python3"

        # 1. Ensure warden.config.yaml exists
        config_file = root / "warden.config.yaml"
        if not config_file.exists() or overwrite:
            config_file.write_text(DEFAULT_WARDEN_CONFIG_TEMPLATE, encoding="utf-8")
            result.files_written.append(str(config_file.relative_to(root)))

        # 2. Configure Claude Code (.claude/settings.json)
        if "claude" in targets:
            claude_dir = root / ".claude"
            claude_dir.mkdir(parents=True, exist_ok=True)
            settings_file = claude_dir / "settings.json"

            existing: dict[str, Any] = {}
            if settings_file.exists() and not overwrite:
                try:
                    existing = json.loads(settings_file.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}

            mcp_servers = existing.setdefault("mcpServers", {})
            mcp_servers["warden"] = {
                "command": python_cmd,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(root),
            }

            hooks = existing.setdefault("hooks", {})
            hooks["PostToolUse"] = [
                {
                    "matcher": "Write|Edit|MultiEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "warden check-boundaries . && warden check-hallucinations .",
                        }
                    ],
                }
            ]

            settings_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            result.files_written.append(str(settings_file.relative_to(root)))

        # 3. Configure Cursor (.cursor/mcp.json & .cursor/rules/warden-governance.mdc)
        if "cursor" in targets:
            cursor_dir = root / ".cursor"
            rules_dir = cursor_dir / "rules"
            rules_dir.mkdir(parents=True, exist_ok=True)

            mcp_file = cursor_dir / "mcp.json"
            mcp_data: dict[str, Any] = {}
            if mcp_file.exists() and not overwrite:
                try:
                    mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
                except Exception:
                    mcp_data = {}

            mcp_data.setdefault("mcpServers", {})["warden"] = {
                "command": python_cmd,
                "args": ["-m", "mcp_server.server"],
                "cwd": str(root),
            }
            mcp_file.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8")
            result.files_written.append(str(mcp_file.relative_to(root)))

            mdc_file = rules_dir / "warden-governance.mdc"
            if not mdc_file.exists() or overwrite:
                mdc_file.write_text(CURSOR_MDC_TEMPLATE, encoding="utf-8")
                result.files_written.append(str(mdc_file.relative_to(root)))

        # 4. Configure Windsurf (.windsurfrules)
        if "windsurf" in targets:
            ws_file = root / ".windsurfrules"
            if not ws_file.exists() or overwrite:
                ws_file.write_text(CURSOR_MDC_TEMPLATE, encoding="utf-8")
                result.files_written.append(str(ws_file.relative_to(root)))

        return result
