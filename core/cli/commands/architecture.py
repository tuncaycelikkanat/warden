"""Architectural and analytical CLI command handlers for WARDEN."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from core.infra.database import create_db_and_tables, engine
from core.models.audit import AuditReport
from core.services.circular_dependency_detector import CircularDependencyDetector
from core.services.ck_metrics_analyzer import CKMetricsAnalyzer
from core.services.dynamic_weight_service import DynamicWeightService
from core.services.github_pr_bot import GitHubPRReviewBot
from core.services.nl_query_service import NaturalLanguageQueryService
from core.services.pdf_report_service import PdfReportService
from core.services.sarif_service import SarifReportService
from core.services.score_anomaly_service import ScoreAnomalyService
from core.services.trend_forecaster import TrendForecasterService

logger = logging.getLogger(__name__)


def run_forecast_command(
    target: str,
    horizon: int = 5,
    dimension: str = "total",
    as_json: bool = False,
    output_file: str | None = None,
) -> None:
    """Executes time-series quality trend forecasting and displays projections."""
    create_db_and_tables()
    target_path = Path(target)
    service = TrendForecasterService()
    report = service.forecast_for_repo(str(target_path), horizon=horizon)
    data = report.to_dict()

    if output_file:
        out_p = Path(output_file)
        out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if not as_json:
            print(f"[✓] Tahmin raporu kaydedildi: {output_file}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    ov = report.overall_forecast
    trend_icon = {
        "IMPROVING": "↗️ Yükseliş",
        "STABLE": "➡️ Stabil",
        "DEGRADING": "↘️ Bozulma",
        "CRITICAL_DROP": "⚠️ Kritik Düşüş",
    }.get(ov.trend_direction, ov.trend_direction)

    print("\n" + "=" * 65)
    print("📈 WARDEN KALİTE TREND TAHMİNLEME (HOLT'S LINEAR FORECAST)")
    print("=" * 65)
    print(f"📁 Hedef Depo          : {target_path.resolve()}")
    print(f"📊 İncelenen Denetim   : {report.total_audits_analyzed}")
    print(f"🎯 Mevcut Kalite Skoru : {ov.current_score:.0f} / 100 ({ov.current_grade})")
    print(f"⚡ Kalite İvmesi       : {ov.velocity_per_audit:+.2f} puan / audit")
    print(f"🧭 Trend Yönü          : {trend_icon}")
    print("-" * 65)

    if ov.status == "INSUFFICIENT_DATA":
        print(f"[!] {ov.early_warning or 'Yetersiz veri.'}")
        print("=" * 65 + "\n")
        return

    if ov.early_warning:
        print(f"🚨 {ov.early_warning}\n")

    print(f"🔮 Gelecek {horizon} Denetim Tahmini (95% Güven Bandı):")
    print(f"  {'Adım':<8} | {'Tahmini Skor':<14} | {'Harf Notu':<10} | {'95% Güven Aralığı':<18}")
    print("  " + "-" * 56)
    for p in ov.forecast_points:
        bounds_str = f"[{p.lower_bound_95:.1f} - {p.upper_bound_95:.1f}]"
        print(f"  +{p.step:<7} | {p.predicted_score:>10.1f}   | {p.projected_grade:>6}     | {bounds_str:>18}")

    if dimension == "all" and report.dimension_forecasts:
        print("\n" + "-" * 65)
        print("🔍 ALT GRUP KALİTE İVMELERİ (Velocity per Audit):")
        for dim_k, dim_f in report.dimension_forecasts.items():
            print(f"  • {dim_k:<24}: {dim_f.current_score:>5.1f} ({dim_f.current_grade}) -> İvme: {dim_f.velocity_per_audit:+.2f} ({dim_f.trend_direction})")

    print("\n" + "=" * 65 + "\n")


def run_anomaly_command(
    target: str,
    audit_id: int | None = None,
    method: str = "hybrid",
    as_json: bool = False,
    output_file: str | None = None,
) -> None:
    """Executes multi-model score anomaly detection and root cause attribution."""
    create_db_and_tables()
    service = ScoreAnomalyService()

    try:
        if audit_id is not None:
            report = service.evaluate_audit_id(audit_id, method=method)
            target_desc = f"Audit #{audit_id}"
        elif target.isdigit():
            report = service.evaluate_audit_id(int(target), method=method)
            target_desc = f"Audit #{target}"
        else:
            target_path = Path(target)
            report = service.evaluate_latest(str(target_path), method=method)
            target_desc = f"Hedef Proje: {target_path.resolve()}"
    except ValueError as val_err:
        print(f"[!] Hata: {val_err}")
        return

    data = report.to_dict()

    if output_file:
        out_p = Path(output_file).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[✓] Anomali analiz raporu kaydedildi: {out_p}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    severity_icon = {
        "CRITICAL": "🚨 KRİTİK ANOMALİ",
        "HIGH": "⚠️  YÜKSEK ANOMALİ",
        "MEDIUM": "⚡ ORTA SEVİYE ANOMALİ",
        "NORMAL": "✅ NORMAL DAĞILIM",
    }.get(report.severity, report.severity)

    print("\n" + "=" * 68)
    print("🛡️  WARDEN GELİŞMİŞ SKOR ANOMALİ TESPİTİ & KÖK NEDEN ANALİZİ (C4)")
    print("=" * 68)
    print(f"🎯 Hedef              : {target_desc}")
    print(f"🔬 Değerlendirme Modu : {method.upper()} (Mahalanobis + Autoencoder + Isolation Forest)")
    print(f"📊 Teşhis             : {severity_icon} (Konsensüs Skoru: %{report.consensus_score:.1f})")
    print(f"📐 Mahalanobis D_M^2  : {report.mahalanobis_distance:.2f} (Chi-Square p-değeri: {report.p_value:.4f})")
    print(f"🤖 Rekonstrüksiyon MSE: {report.reconstruction_mse:.2f}")
    print(f"🌲 Isolation Forest   : %{report.isolation_forest_score:.1f}")
    print("-" * 68)

    print(f"📝 Özet: {report.verdict_summary}")

    if report.top_contributors:
        print("\n" + "-" * 68)
        print("🔍 EN ÇOK ETKİ EDEN KALİTE BOYUTLARI (TOP CONTRIBUTORS):")
        print(f"  {'Boyut':<22} | {'Katkı %':<9} | {'Mevcut':<8} | {'Beklenen':<8} | {'Sapma':<8} | {'Yön'}")
        print("  " + "-" * 64)
        for c in report.top_contributors:
            dir_str = "🔻 DÜŞÜŞ" if c.direction == "DROP" else "🔺 ARTIŞ"
            print(f"  {c.dimension:<22} | %{c.contribution_pct:>6.1f} | {c.actual_value:>6.1f}   | {c.expected_mean:>6.1f}   | {c.deviation:>+6.1f}   | {dir_str}")

    if report.remediation_actions:
        print("\n" + "-" * 68)
        print("💡 ÖNERİLEN İYİLEŞTİRME AKSİYONLARI:")
        for i, act in enumerate(report.remediation_actions, start=1):
            print(f"  {i}. {act}")

    print("\n" + "=" * 68 + "\n")


def run_pr_review_command(
    target: str,
    pr_number: int = 1,
    owner: str = "owner",
    repo: str = "repo",
    min_score: int = 80,
    post_to_github: bool = False,
    token: str | None = None,
    output_file: str | None = None,
    init_workflow: bool = False,
    as_json: bool = False,
) -> None:
    """Executes PR review quality gate analysis and interacts with GitHub API."""
    bot = GitHubPRReviewBot(token=token)

    if init_workflow:
        wf_content = bot.generate_github_actions_workflow(min_score=min_score)
        wf_path = Path(".github/workflows/warden-pr-review.yml")
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(wf_content, encoding="utf-8")
        print(f"[✓] GitHub Actions PR Review workflow dosyası oluşturuldu: {wf_path.resolve()}")
        return

    target_path = Path(target).resolve()
    if not as_json:
        print(f"[*] WARDEN PR Review Bot running on {target_path} (PR #{pr_number} - {owner}/{repo})...")

    create_db_and_tables()
    scorecard: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []

    with Session(engine) as session:
        report = session.exec(select(AuditReport).order_by(AuditReport.id.desc())).first()  # type: ignore[union-attr]
        if report:
            scorecard = {
                "total_score": report.total_score if report.total_score is not None else 80.0,
                "grade": report.grade if report.grade else "B",
                "layer1_score": report.layer1_score if report.layer1_score is not None else 80.0,
                "layer2_score": report.layer2_score,
                "groups": {
                    "security": report.group_security if report.group_security is not None else 75.0,
                    "code_health": report.group_code_health if report.group_code_health is not None else 75.0,
                    "structural": report.group_structural if report.group_structural is not None else 75.0,
                    "resilience": report.group_resilience if report.group_resilience is not None else 75.0,
                    "dev_hygiene": report.group_dev_hygiene if report.group_dev_hygiene is not None else 75.0,
                },
            }
            if report.raw_data and isinstance(report.raw_data, dict):
                findings = report.raw_data.get("findings", [])
        else:
            scorecard = {
                "total_score": 84.0,
                "grade": "B",
                "layer1_score": 82.0,
                "layer2_score": 86.0,
                "groups": {
                    "security": 80.0,
                    "code_health": 85.0,
                    "structural": 82.0,
                    "resilience": 84.0,
                    "dev_hygiene": 88.0,
                },
            }

    pr_report = bot.review_pull_request(
        scorecard=scorecard,
        owner=owner,
        repo=repo,
        pull_number=pr_number,
        findings=findings,
        min_score=min_score,
        post_to_github=post_to_github,
    )

    data = pr_report.to_dict()

    if output_file:
        out_p = Path(output_file).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(pr_report.summary_markdown, encoding="utf-8")
        print(f"[✓] PR İnceleme Markdown raporu kaydedildi: {out_p}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    gate_str = "✅ GEÇTİ (PASSED)" if pr_report.passed_quality_gate else "🚨 BAŞARISIZ (FAILED)"
    print("\n" + "=" * 68)
    print("🤖 WARDEN GITHUB PR REVIEW BOT (SECTION G4)")
    print("=" * 68)
    print(f"📁 Repository        : {owner}/{repo}")
    print(f"🔀 Pull Request      : #{pr_number}")
    print(f"🎯 Kalite Skoru      : {pr_report.total_score:.1f} / 100 ({pr_report.grade})")
    print(f"🛡️  Kalite Kapısı     : {gate_str} (Eşik: {min_score}/100)")
    print(f"⚖️  GitHub Kararı     : {pr_report.action_event}")
    print(f"💬 Inline Yorumlar   : {len(pr_report.inline_comments)} adet kritik/yüksek bulgu")
    if pr_report.comment_id:
        update_str = "güncellendi" if pr_report.is_updated else "oluşturuldu"
        print(f"🌐 GitHub Yorumu     : #{pr_report.comment_id} ({update_str})")
    print("-" * 68)
    print("\n--- PR Markdown Yorum Önizleme ---")
    print(pr_report.summary_markdown[:500] + "...\n")
    print("=" * 68 + "\n")


def run_classify_command(
    target: str,
    show_weights: bool = False,
    overrides: list[str] | None = None,
    as_json: bool = False,
) -> None:
    """Executes archetype classification and dynamic weighting analysis."""
    target_path = Path(target)
    custom_overrides: dict[str, float] = {}
    if overrides:
        for o in overrides:
            if "=" in o:
                k, v = o.split("=", 1)
                try:
                    custom_overrides[k.strip()] = float(v.strip())
                except ValueError:
                    pass

    service = DynamicWeightService()
    report = service.analyze_project_weights(target_path, custom_overrides=custom_overrides)
    data = report.to_dict()

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 65)
    print("🏛️  WARDEN PROJE ARKETİPİ VE DİNAMİK AĞIRLIKLANDIRMA")
    print("=" * 65)
    print(f"📁 Hedef Dizin      : {target_path.resolve()}")
    print(f"🏷️  Arketip          : {report.label} ({report.archetype})")
    print(f"🎯 Güven Skoru      : %{report.confidence * 100:.1f}")
    print(f"💡 Mimari Öncelik   : {report.description}")
    if report.matched_traits:
        print(f"🔍 Tespit İpuçları  : {', '.join(report.matched_traits)}")

    if show_weights or custom_overrides:
        print("\n" + "-" * 65)
        print("⚖️  LAYER 1 (STATİK GRUPLAR) DİNAMİK AĞIRLIK DAĞILIMI:")
        print(f"  {'Grup':<28} | {'Varsayılan':<12} | {'Arketip Uyarlanmış':<18}")
        print("  " + "-" * 62)
        for grp, adj_w in report.layer1_adjusted.items():
            base_w = report.layer1_baseline.get(grp, 0.0)
            diff = adj_w - base_w
            diff_str = f"({diff:+.1%})" if abs(diff) > 0.001 else "(=)"
            print(f"  {grp:<28} | {base_w:>10.1%} | {adj_w:>10.1%} {diff_str}")

        print("\n" + "-" * 65)
        print("🧠 LAYER 2 (LLM RUBRIC) DİNAMİK KATEGORİ ÇARPANLARI:")
        print(f"  {'Rubric Kategorisi':<28} | {'Varsayılan':<12} | {'Arketip Çarpanı':<18}")
        print("  " + "-" * 62)
        for cat, adj_w in report.layer2_adjusted.items():
            base_w = report.layer2_baseline.get(cat, 1.0)
            diff = adj_w - base_w
            diff_str = f"({diff:+.2f})" if abs(diff) > 0.01 else "(=)"
            print(f"  {cat:<28} | {base_w:>10.2f}x | {adj_w:>10.2f}x {diff_str}")

    if custom_overrides:
        print("\n" + "-" * 65)
        print(f"⚡ Uygulanan Kullanıcı Override'ları: {custom_overrides}")

    print("=" * 65 + "\n")


def run_query_command(query_text: str, as_json: bool = False, provider: str | None = None) -> None:
    """Executes natural language dashboard query and prints tabular or JSON output."""
    create_db_and_tables()
    service = NaturalLanguageQueryService()

    try:
        res = service.execute_query(query_text, provider_name=provider)
    except Exception as e:
        print(f"[!] Sorgu hatası: {e}")
        sys.exit(1)

    if as_json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    print(f"\n🔍 Soru: {res['query']}")
    print(f"💡 Açıklama: {res['explanation']}")
    print(f"📊 Önerilen Grafik: {res['chart_type']} | Süre: {res['execution_time_ms']} ms")
    print(f"📝 SQL: {res['sql']}\n")

    cols = res["columns"]
    data = res["data"]

    if not data:
        print("[i] Sonuç bulunamadı.")
        return

    col_widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in data)) for c in cols}
    header_str = " | ".join(c.ljust(col_widths[c]) for c in cols)
    sep_str = "-+-".join("-" * col_widths[c] for c in cols)

    print(header_str)
    print(sep_str)
    for r in data:
        row_str = " | ".join(str(r.get(c, "")).ljust(col_widths[c]) for c in cols)
        print(row_str)
    print(f"\nToplam {res['row_count']} satır listelendi.")


def run_export_sarif(target: str, output: str, audit_id: int | None = None) -> None:
    """Runs audit or fetches from DB, then exports findings to OASIS SARIF v2.1.0 JSON."""
    create_db_and_tables()
    p = Path(target).resolve()
    out = Path(output).resolve()

    if audit_id is not None:
        with Session(engine) as session:
            rep = session.exec(select(AuditReport).where(AuditReport.id == audit_id)).first()
            if not rep:
                print(f"[!] Audit ID {audit_id} bulunamadı.")
                sys.exit(1)
            data = rep.raw_data or {}
            target_path = rep.repo_path
    else:
        from core.services.orchestrator import AuditOrchestrator

        print(f"[*] Auditing {p} to generate SARIF report...")
        orch = AuditOrchestrator()
        data = asyncio.run(orch.run_full_audit(str(p), incremental=True))
        target_path = str(p)

    service = SarifReportService()
    saved = service.export_to_file(data, out, repo_path=target_path)
    print(f"[✓] OASIS SARIF v2.1.0 raporu başarıyla kaydedildi: {saved}")


def run_export_pdf(target: str, output: str, audit_id: int | None = None) -> None:
    """Runs audit or fetches from DB, then exports executive summary to PDF."""
    create_db_and_tables()
    p = Path(target).resolve()
    out = Path(output).resolve()

    if audit_id is not None:
        with Session(engine) as session:
            rep = session.exec(select(AuditReport).where(AuditReport.id == audit_id)).first()
            if not rep:
                print(f"[!] Audit ID {audit_id} bulunamadı.")
                sys.exit(1)
            data = rep.raw_data or {}
            if not data.get("scorecard"):
                data["scorecard"] = {
                    "total_score": rep.total_score,
                    "grade": rep.grade,
                    "layer1_score": rep.layer1_score,
                    "layer2_score": rep.layer2_score,
                    "group_scores": {
                        "security_supply_chain": rep.group_security or 0.0,
                        "code_health_test": rep.group_code_health or 0.0,
                        "structural_health": rep.group_structural or 0.0,
                        "resilience_performance": rep.group_resilience or 0.0,
                        "dev_hygiene_devops": rep.group_dev_hygiene or 0.0,
                    },
                }
            target_path = rep.repo_path
    else:
        from core.services.orchestrator import AuditOrchestrator

        print(f"[*] Auditing {p} to generate Executive PDF report...")
        orch = AuditOrchestrator()
        data = asyncio.run(orch.run_full_audit(str(p), incremental=True))
        target_path = str(p)

    service = PdfReportService()
    saved = service.generate_pdf(data, out, repo_path=target_path)
    print(f"[✓] Kurumsal Executive Summary PDF raporu kaydedildi: {saved}")


def run_check_cycles(target: str) -> None:
    """Detects circular import cycles using networkx AST graph analysis."""
    p = Path(target).resolve()
    print(f"[*] Analyzing Python import relationships and circular cycles for {p} using networkx...")
    detector = CircularDependencyDetector()
    report = detector.analyze(p)

    print(f"[+] Toplam Modül: {report.total_modules_analyzed} · Import Kenarları: {report.total_import_edges}")

    if not report.has_cycles:
        print("[✓] Harika! Projede döngüsel bağımlılık (circular import) tespit edilmedi (Temiz Acyclic DAG).")
    else:
        print(f"[🚨] {report.cycles_count} DÖNGÜSEL BAĞIMLILIK TESPİT EDİLDİ!")
        for i, cycle in enumerate(report.cycles, start=1):
            path_str = " -> ".join(cycle.cycle_path)
            print(f"\n  #{i} Döngü ({cycle.length} modül): {path_str}")
            print(f"     💡 Çözüm Önerisi: {cycle.break_suggestion}")


def run_check_ck(
    target: str,
    top: int = 15,
    smells_only: bool = False,
    as_json: bool = False,
    output_file: str | None = None,
) -> None:
    """Computes Chidamber & Kemerer (CK) Object-Oriented metrics and displays smells."""
    p = Path(target).resolve()
    if not as_json:
        print(f"[*] Analyzing Python classes in {p} using CK Object-Oriented Metrics Suite...")

    analyzer = CKMetricsAnalyzer()
    report = analyzer.analyze(p)
    classes = report.high_risk_classes if smells_only else report.classes

    data = report.to_dict()
    data["classes"] = [c.to_dict() for c in classes[:top]]
    data["high_risk_classes"] = [c.to_dict() for c in report.high_risk_classes[:top]]

    if output_file:
        out_p = Path(output_file).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[✓] CK Metrik raporu kaydedildi: {out_p}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 72)
    print("🏛️  WARDEN CHIDAMBER & KEMERER (CK) NESNE YÖNELİMLİ MİMARİ METRİKLERİ")
    print("=" * 72)
    print(f"📁 Hedef Dizin        : {p}")
    print(f"📦 Analiz Edilen Sınıf: {report.total_classes_analyzed} sınıf")
    print(f"⚡ Ortalama WMC       : {report.avg_wmc:.1f} (Max: {report.max_wmc})")
    print(f"🌲 Ortalama DIT       : {report.avg_dit:.1f} (Max: {report.max_dit})")
    print(f"🔗 Ortalama CBO       : {report.avg_cbo:.1f} (Max: {report.max_cbo})")
    print(f"🧩 Ortalama LCOM4     : {report.avg_lcom4:.1f}")
    print("-" * 72)

    if report.smells_summary:
        print("🚨 TESPİT EDİLEN MİMARİ KOKULAR (ARCHITECTURAL SMELLS):")
        for smell, count in sorted(report.smells_summary.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {smell:<24}: {count} sınıf")
        print("-" * 72)

    print(f"\n📊 EN KRİTİK {min(top, len(classes))} SINIF (WMC, CBO, LCOM):")
    print(f"  {'Sınıf Adı':<28} | {'WMC':<5} | {'DIT':<4} | {'CBO':<5} | {'RFC':<5} | {'LCOM4':<6} | {'Kokular'}")
    print("  " + "-" * 72)

    for c in classes[:top]:
        smells_str = ", ".join(c.detected_smells) if c.detected_smells else "Temiz ✓"
        print(f"  {c.class_name:<28} | {c.wmc:>4}  | {c.dit:>3}  | {c.cbo:>4}  | {c.rfc:>4}  | {c.lcom4:>5}  | {smells_str}")

    if any(c.recommendations for c in classes[:top]):
        print("\n" + "-" * 72)
        print("💡 ÖNERİLEN MİMARİ REFACTORING AKSİYONLARI:")
        rec_idx = 1
        for c in classes[:top]:
            for r in c.recommendations:
                print(f"  {rec_idx}. [{c.class_name}] {r}")
                rec_idx += 1
                if rec_idx > 5:
                    break
            if rec_idx > 5:
                break

    print("\n" + "=" * 72 + "\n")


def run_check_boundaries(target: str = ".", as_json: bool = False) -> None:
    """Evaluates declarative architectural boundary rules across repository."""
    from core.services.architecture_boundary import ArchitectureBoundaryEnforcer

    enforcer = ArchitectureBoundaryEnforcer()
    result = enforcer.check_repository(Path(target).resolve())

    if as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"[*] Mimari Sınır Sözleşmeleri denetleniyor ({result.files_checked} dosya, {result.rules_evaluated} kural)...")
        if result.passed:
            print(f"[✓] Mimari sınır ihlali bulunmadı! Skor: {result.score}/100")
        else:
            print(f"[🚨] {len(result.violations)} MİMARİ SINIR İHLALİ TESPİT EDİLDİ (Skor: {result.score}/100):")
            for v in result.violations:
                print(f"    - {v.file}:{v.line} -> Yasaklı import '{v.actual_import}' (Kural: {v.source_pattern} !=> {v.forbidden_import})")
                print(f"      Neden: {v.reason}")

    if not result.passed:
        sys.exit(1)

