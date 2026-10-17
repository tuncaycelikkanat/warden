"""Main entry point for WARDEN platform: exports FastAPI app and CLI runner.

This module serves as the root gateway, delegating API logic to :mod:`core.api.app`
and command-line operations to :mod:`core.cli`.
"""

from __future__ import annotations

# Re-export FastAPI application and factory
from core.api.app import app, create_app
from core.cli import build_argument_parser, cli, dispatch_cli, ensure_venv_path
from core.cli.commands.architecture import (
    run_anomaly_command as _run_anomaly_command,
)
from core.cli.commands.architecture import (
    run_check_ck as _run_check_ck,
)
from core.cli.commands.architecture import (
    run_check_cycles as _run_check_cycles,
)
from core.cli.commands.architecture import (
    run_classify_command as _run_classify_command,
)
from core.cli.commands.architecture import (
    run_export_pdf as _run_export_pdf,
)
from core.cli.commands.architecture import (
    run_export_sarif as _run_export_sarif,
)
from core.cli.commands.architecture import (
    run_forecast_command as _run_forecast_command,
)
from core.cli.commands.architecture import (
    run_pr_review_command as _run_pr_review_command,
)
from core.cli.commands.architecture import (
    run_query_command as _run_query_command,
)

# Backward-compatibility aliases for legacy internal imports and test patches
from core.cli.commands.audit import (
    execute_audit as _execute_audit,
)
from core.cli.commands.audit import (
    run_audit_command as _run_audit_command,
)
from core.cli.commands.ops import (
    run_badge_command as _run_badge_command,
)
from core.cli.commands.ops import (
    run_hook_command as _run_hook_command,
)
from core.cli.commands.ops import (
    run_metrics_command as _run_metrics_command,
)
from core.cli.commands.ops import (
    run_milestone_command as _run_milestone_command,
)
from core.cli.commands.ops import (
    run_serve_command as _run_serve_command,
)
from core.cli.commands.ops import (
    run_watch_command as _run_watch_command,
)
from core.cli.commands.security import (
    run_check_attack_surface as _run_check_attack_surface,
)
from core.cli.commands.security import (
    run_check_typosquatting as _run_check_typosquatting,
)
from core.cli.commands.security import (
    run_generate_sbom as _run_generate_sbom,
)
from core.cli.commands.security import (
    run_scan_entropy as _run_scan_entropy,
)
from core.cli.commands.testing import (
    run_bdd_command as _run_bdd_command,
)
from core.cli.commands.testing import (
    run_generate_property_tests as _run_generate_property_tests,
)
from core.cli.commands.testing import (
    run_mutate_command as _run_mutate_command,
)

_ensure_venv_path = ensure_venv_path
_build_argument_parser = build_argument_parser
_dispatch_cli = dispatch_cli

__all__ = [
    "_build_argument_parser",
    "_dispatch_cli",
    "_ensure_venv_path",
    "_execute_audit",
    "_run_anomaly_command",
    "_run_audit_command",
    "_run_badge_command",
    "_run_bdd_command",
    "_run_check_attack_surface",
    "_run_check_ck",
    "_run_check_cycles",
    "_run_check_typosquatting",
    "_run_classify_command",
    "_run_export_pdf",
    "_run_export_sarif",
    "_run_forecast_command",
    "_run_generate_property_tests",
    "_run_generate_sbom",
    "_run_hook_command",
    "_run_metrics_command",
    "_run_milestone_command",
    "_run_mutate_command",
    "_run_pr_review_command",
    "_run_query_command",
    "_run_scan_entropy",
    "_run_serve_command",
    "_run_watch_command",
    "app",
    "cli",
    "create_app",
]

if __name__ == "__main__":
    cli()
