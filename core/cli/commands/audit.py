"""Audit command handler executing end-to-end WARDEN quality evaluations."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
from typing import Any

from core.infra.database import create_db_and_tables
from core.services.orchestrator import AuditOrchestrator
from core.services.quality_gate import CriticalFindings, ExitCode, evaluate_gate
from core.services.report import AuditReportService
from core.utils.path_validator import validate_audit_path

logger = logging.getLogger(__name__)


def run_audit_command(
    repo_target: str,
    min_score: int | None = None,
    full_history: bool = False,
    incremental: bool = False,
    since_commit: str | None = None,
    fail_on_critical: bool = False,
    output_format: str = "text",
) -> None:
    """Executes end-to-end CLI audit, persists report and enforces the quality gate.

    Exit codes follow :class:`core.services.quality_gate.ExitCode`. In ``json``
    mode all human-readable output is redirected to stderr so stdout is a single
    machine-parseable JSON document, safe to pipe into CI tooling.
    """
    real_stdout = sys.stdout
    human_out = sys.stderr if output_format == "json" else sys.stdout

    with contextlib.redirect_stdout(human_out):
        try:
            res, db_id = execute_audit(repo_target, full_history, incremental, since_commit)
        except SystemExit:
            raise
        except Exception as exc:  # top-level boundary: map any failure to a stable exit code
            logger.exception("Audit execution failed")
            print(f"[!] Audit execution error: {exc}")
            sys.exit(ExitCode.EXECUTION_ERROR)

        critical = CriticalFindings(**{
            k: v for k, v in res.get("critical_findings", {}).items() if k != "total"
        })
        decision = evaluate_gate(
            res["scorecard"]["total_score"], critical, min_score, fail_on_critical
        )
        for reason in decision.reasons:
            print(f"[!] Quality Gate FAILED: {reason}")

    if output_format == "json":
        payload = {
            "audit_id": db_id,
            "exit_code": int(decision.exit_code),
            "gate_reasons": decision.reasons,
            "scorecard": res["scorecard"],
            "critical_findings": critical.to_dict(),
            "vibe_coding": res.get("vibe_coding"),
            "profile_signature": res.get("profile_signature"),
        }
        json.dump(payload, real_stdout, default=str, ensure_ascii=False)
        real_stdout.write("\n")

    if not decision.passed:
        sys.exit(decision.exit_code)


def execute_audit(
    repo_target: str,
    full_history: bool,
    incremental: bool,
    since_commit: str | None,
) -> tuple[dict[str, Any], int]:
    """Runs the audit pipeline, persists the report and prints the human summary."""
    create_db_and_tables()

    try:
        validated_path = validate_audit_path(repo_target)
    except ValueError as exc:
        print(f"[!] Geçersiz audit hedefi: {exc}")
        sys.exit(3)

    mode_parts = []
    if full_history:
        mode_parts.append("tüm geçmiş")
    else:
        mode_parts.append("son 6 ay")
    if incremental:
        mode_parts.append("artımlı")
    if since_commit:
        mode_parts.append(f"since {since_commit}")
    mode_str = ", ".join(mode_parts)

    print(f"[*] Starting full audit on {validated_path} (Kapsam: {mode_str}) ...")
    orch = AuditOrchestrator()
    res = asyncio.run(
        orch.run_full_audit(
            str(validated_path),
            full_history=full_history,
            incremental=incremental,
            since_commit=since_commit,
        )
    )

    reporter = AuditReportService()
    db_id = reporter.save_to_db(str(validated_path), res)
    md_path = reporter.generate_markdown(str(validated_path), res, current_id=db_id)

    total_score = res["scorecard"]["total_score"]
    grade = res["scorecard"]["grade"]
    print(f"[+] Audit complete! Score: {total_score}/100 (Grade: {grade})")

    vibe = res.get("vibe_coding")
    if vibe:
        v_score = vibe.get("vibe_score", 0)
        v_level = vibe.get("risk_level", "LOW")
        v_count = vibe.get("findings_count", 0)
        print(f"[🤖] Vibe-Coding Oranı: %{v_score} AI İzi ({v_level} risk · {v_count} gösterge)")

    # Project Archetype (C5)
    try:
        from core.services.project_classifier import ProjectTypeClassifier

        archetype = ProjectTypeClassifier().classify(validated_path)
        print(f"[📁] Proje Tipi: {archetype.label} (%{int(archetype.confidence * 100)} güven)")
    except Exception as err:
        logger.debug(f"Could not classify project archetype: {err}")

    # Anomaly Detection (C2)
    try:
        from core.services.anomaly_detector import AnomalyDetector

        anomaly_rep = AnomalyDetector().detect_anomalies(res.get("scorecard", {}))
        if anomaly_rep.is_anomaly:
            dims_str = (
                ", ".join(d.dimension for d in anomaly_rep.anomalous_dimensions)
                if anomaly_rep.anomalous_dimensions
                else "Genel skor"
            )
            print(
                f"[🚨] ANOMALİ UYARISI: Tarihsel normal dağılımın dışına çıkıldı ({dims_str} · Risk Skoru: %{round(anomaly_rep.anomaly_score, 1)})"
            )
    except Exception as err:
        logger.debug(f"Could not run anomaly detection: {err}")

    # Test Quality & Fake Tests (D2)
    tq = res.get("test_quality_meta", {})
    fake_count = tq.get("fake_tests", 0)
    if fake_count > 0:
        print(f"[⚠️] Sahte/Trivial Test Uyarısı: {fake_count} assertion'sız test tespit edildi!")

    # Technical Debt Remediation Effort (F3)
    try:
        from core.services.debt_estimator import TechDebtEstimator

        td_data = res.get("tech_debt", {})
        comp_data = res.get("complexity", {})
        outliers = (
            comp_data.get("outlier_blocks", [])
            if isinstance(comp_data, dict)
            else getattr(comp_data, "outlier_blocks", [])
        )
        est = TechDebtEstimator().estimate(
            todo_markers=td_data.get("todo_markers", []),
            churn_entries=td_data.get("churn_entries", []),
            outlier_blocks=outliers,
        )
        if est.total_hours > 0:
            print(f"[⏱️] Tahmini Teknik Borç Eforu: {est.total_hours:.1f} saat ({est.total_days:.1f} adam/gün)")
    except Exception as err:
        logger.debug(f"Could not compute tech debt estimate in audit: {err}")

    crit = res.get("critical_findings", {})
    if crit.get("total"):
        print(
            f"[🔴] Kritik Bulgular: {crit['secret_leaks']} secret sızıntısı, "
            f"{crit['sast_errors']} SAST hatası, {crit['vulnerable_dependencies']} zafiyetli bağımlılık"
        )

    print(f"[+] Saved to DB (ID: {db_id}) and {md_path}")
    return res, db_id
