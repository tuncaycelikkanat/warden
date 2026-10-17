"""Command dispatcher routing parsed CLI options to concrete handlers."""

from __future__ import annotations

import logging
import sys
from typing import Any

from core.cli.commands.architecture import (
    run_anomaly_command,
    run_check_boundaries,
    run_check_ck,
    run_check_cycles,
    run_classify_command,
    run_export_pdf,
    run_export_sarif,
    run_forecast_command,
    run_pr_review_command,
    run_query_command,
)
from core.cli.commands.audit import run_audit_command
from core.cli.commands.ops import (
    run_badge_command,
    run_hook_command,
    run_init_command,
    run_metrics_command,
    run_milestone_command,
    run_serve_command,
    run_watch_command,
)
from core.cli.commands.security import (
    run_check_attack_surface,
    run_check_hallucinations,
    run_check_typosquatting,
    run_generate_sbom,
    run_scan_entropy,
)
from core.cli.commands.testing import (
    run_bdd_command,
    run_bench_command,
    run_generate_property_tests,
    run_mutate_command,
)

logger = logging.getLogger(__name__)


def _resolve_handler(legacy_name: str, default_fn: Any) -> Any:
    """Resolves handler function, respecting patches on core.main during testing."""
    main_mod = sys.modules.get("core.main")
    if main_mod is not None:
        return getattr(main_mod, legacy_name, default_fn)
    return default_fn


def dispatch_core_command(args: Any) -> bool:
    """Dispatches core lifecycle commands."""
    if args.command == "audit":
        repo_target = args.path if args.path else args.target
        _resolve_handler("_run_audit_command", run_audit_command)(
            repo_target,
            args.min_score,
            full_history=args.full_history,
            incremental=args.incremental,
            since_commit=args.since_commit,
            fail_on_critical=args.fail_on_critical,
            output_format=args.format,
        )
        return True
    if args.command == "serve":
        _resolve_handler("_run_serve_command", run_serve_command)(
            host=args.host, port=args.port, reload=args.reload
        )
        return True
    if args.command == "milestone":
        _resolve_handler("_run_milestone_command", run_milestone_command)(
            args.audit_id, args.label, args.clear
        )
        return True
    if args.command == "metrics":
        run_metrics_command(args.json)
        return True
    if args.command == "hook":
        run_hook_command(args)
        return True
    if args.command == "watch":
        run_watch_command(args.target, args.min_score, args.debounce)
        return True
    if args.command == "badge":
        run_badge_command(args.score, args.grade, args.label, args.output)
        return True
    if args.command == "init":
        run_init_command(args.target, agent=args.agent, overwrite=args.overwrite, as_json=args.json)
        return True
    return False


def dispatch_testing_command(args: Any) -> bool:
    """Dispatches testing and verification commands."""
    if args.command == "generate-property-tests":
        run_generate_property_tests(args.target, args.output, args.max_tests)
        return True
    if args.command == "mutate":
        run_mutate_command(
            args.target,
            test_path=args.test_path,
            max_mutants=args.max_mutants,
            timeout=args.timeout,
            dry_run=args.dry_run,
            as_json=args.json,
            output_file=args.output,
        )
        return True
    if args.command == "bdd":
        run_bdd_command(
            args.target,
            feature_dir=args.feature_dir,
            output_file=args.output,
            enrich_llm=args.enrich_llm,
            provider=args.provider,
            as_json=args.json,
        )
        return True
    if args.command in ("bench", "benchmark"):
        run_bench_command(output=args.output, as_json=args.json)
        return True
    return False


def dispatch_security_command(args: Any) -> bool:
    """Dispatches supply-chain and security commands."""
    if args.command == "generate-sbom":
        run_generate_sbom(args.target, args.output)
        return True
    if args.command == "scan-entropy":
        run_scan_entropy(args.target, args.max_findings)
        return True
    if args.command == "check-attack-surface":
        run_check_attack_surface(args.target, args.top)
        return True
    if args.command == "check-typosquatting":
        run_check_typosquatting(args.package_name)
        return True
    if args.command == "check-hallucinations":
        run_check_hallucinations(args.target, as_json=args.json)
        return True
    return False


def dispatch_architecture_command(args: Any) -> bool:
    """Dispatches architectural intelligence and analytics commands."""
    if args.command == "check-cycles":
        run_check_cycles(args.target)
        return True
    if args.command == "check-boundaries":
        run_check_boundaries(args.target, as_json=args.json)
        return True
    if args.command == "check-ck":
        run_check_ck(
            args.target,
            top=args.top,
            smells_only=args.smells_only,
            as_json=args.json,
            output_file=args.output,
        )
        return True
    if args.command == "export-sarif":
        run_export_sarif(args.target, args.output, audit_id=args.audit_id)
        return True
    if args.command == "export-pdf":
        run_export_pdf(args.target, args.output, audit_id=args.audit_id)
        return True
    if args.command == "query":
        run_query_command(args.query, as_json=args.json, provider=args.provider)
        return True
    if args.command == "classify":
        run_classify_command(
            args.target,
            show_weights=args.weights,
            overrides=args.override,
            as_json=args.json,
        )
        return True
    if args.command == "forecast":
        run_forecast_command(
            args.target,
            horizon=args.horizon,
            dimension=args.dimension,
            as_json=args.json,
            output_file=args.output,
        )
        return True
    if args.command == "anomaly":
        run_anomaly_command(
            args.target,
            audit_id=args.audit_id,
            method=args.method,
            as_json=args.json,
            output_file=args.output,
        )
        return True
    if args.command == "pr-review":
        run_pr_review_command(
            args.target,
            pr_number=args.pr,
            owner=args.owner,
            repo=args.repo,
            min_score=args.min_score,
            post_to_github=args.post,
            token=args.token,
            output_file=args.output,
            init_workflow=args.init_workflow,
            as_json=args.json,
        )
        return True
    return False


def dispatch_cli(args: Any) -> None:
    """Dispatches parsed CLI command to the appropriate category handler."""
    if dispatch_core_command(args):
        return
    if dispatch_testing_command(args):
        return
    if dispatch_security_command(args):
        return
    dispatch_architecture_command(args)
