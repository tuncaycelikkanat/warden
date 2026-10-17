"""CLI commands package organizing all WARDEN CLI subcommands."""

from core.cli.commands.architecture import (
    run_anomaly_command,
    run_check_ck,
    run_check_cycles,
    run_classify_command,
    run_export_pdf,
    run_export_sarif,
    run_forecast_command,
    run_pr_review_command,
    run_query_command,
)
from core.cli.commands.audit import execute_audit, run_audit_command
from core.cli.commands.ops import (
    run_badge_command,
    run_hook_command,
    run_metrics_command,
    run_milestone_command,
    run_serve_command,
    run_watch_command,
)
from core.cli.commands.security import (
    run_check_attack_surface,
    run_check_typosquatting,
    run_generate_sbom,
    run_scan_entropy,
)
from core.cli.commands.testing import (
    run_bdd_command,
    run_generate_property_tests,
    run_mutate_command,
)

__all__ = [
    "execute_audit",
    "run_anomaly_command",
    "run_audit_command",
    "run_badge_command",
    "run_bdd_command",
    "run_check_attack_surface",
    "run_check_ck",
    "run_check_cycles",
    "run_check_typosquatting",
    "run_classify_command",
    "run_export_pdf",
    "run_export_sarif",
    "run_forecast_command",
    "run_generate_property_tests",
    "run_generate_sbom",
    "run_hook_command",
    "run_metrics_command",
    "run_milestone_command",
    "run_mutate_command",
    "run_pr_review_command",
    "run_query_command",
    "run_scan_entropy",
    "run_serve_command",
    "run_watch_command",
]
