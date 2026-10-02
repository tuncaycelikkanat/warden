"""FastAPI entry point and CLI audit runner for WARDEN."""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from core.api.dashboard import router as dashboard_router
from core.api.package import router as package_router
from core.api.rate_limiter import RateLimitMiddleware
from core.api.scan import router as scan_router
from core.infra.database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager initializing database tables."""
    create_db_and_tables()
    yield


app = FastAPI(title="WARDEN API", version="0.1.0", lifespan=lifespan)

# Enforce sliding-window rate limits (120 req/min, exempts /health, /docs, /dashboard)
app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

app.include_router(scan_router)
app.include_router(package_router)
app.include_router(dashboard_router)


import time

_APP_START_TIME = time.time()


from fastapi.responses import RedirectResponse


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to dashboard or docs."""
    return RedirectResponse(url="/dashboard/")


@app.get("/api/v1/health")
async def health_check():

    """Health check endpoint returning system status."""
    return {"status": "ok"}


@app.get("/api/v1/metrics")
async def get_metrics():
    """Observability endpoint providing operational metrics and health status (JSON)."""
    from core.services.metrics_service import MetricsCollectorService

    collector = MetricsCollectorService(start_time=_APP_START_TIME)
    return collector.collect_metrics_data()


@app.get("/metrics", response_class=Response)
@app.get("/api/v1/metrics/prometheus", response_class=Response)
async def get_prometheus_metrics():
    """Observability endpoint providing Prometheus / OpenMetrics plain-text metrics."""
    from core.services.metrics_service import MetricsCollectorService

    collector = MetricsCollectorService(start_time=_APP_START_TIME)
    content = collector.generate_prometheus_exposition()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


# Dashboard frontend (React/Vite build output) — sadece build varsa serve et
_dashboard_dist = Path(__file__).parent.parent / "dashboard" / "dist"
if _dashboard_dist.exists():
    app.mount("/dashboard", StaticFiles(directory=str(_dashboard_dist), html=True), name="dashboard-ui")

def _run_audit_command(
    repo_target: str,
    min_score: int | None = None,
    full_history: bool = False,
    incremental: bool = False,
    since_commit: str | None = None,
) -> None:
    """Executes end-to-end CLI audit, persists report and verifies quality gates."""
    import asyncio
    import sys

    from core.services.orchestrator import AuditOrchestrator
    from core.services.report import AuditReportService
    from core.utils.path_validator import validate_audit_path

    create_db_and_tables()

    try:
        validated_path = validate_audit_path(repo_target)
    except ValueError as exc:
        print(f"[!] Geçersiz audit hedefi: {exc}")
        sys.exit(1)

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
            dims_str = ", ".join(d.dimension for d in anomaly_rep.anomalous_dimensions) if anomaly_rep.anomalous_dimensions else "Genel skor"
            print(f"[🚨] ANOMALİ UYARISI: Tarihsel normal dağılımın dışına çıkıldı ({dims_str} · Risk Skoru: %{round(anomaly_rep.anomaly_score, 1)})")
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
        outliers = comp_data.get("outlier_blocks", []) if isinstance(comp_data, dict) else getattr(comp_data, "outlier_blocks", [])
        est = TechDebtEstimator().estimate(
            todo_markers=td_data.get("todo_markers", []),
            churn_entries=td_data.get("churn_entries", []),
            outlier_blocks=outliers,
        )
        if est.total_hours > 0:
            print(f"[⏱️] Tahmini Teknik Borç Eforu: {est.total_hours:.1f} saat ({est.total_days:.1f} adam/gün)")
    except Exception as err:
        logger.debug(f"Could not compute tech debt estimate in audit: {err}")

    print(f"[+] Saved to DB (ID: {db_id}) and {md_path}")

    if min_score is not None and total_score < min_score:
        print(f"[!] Quality Gate FAILED: Score {total_score} is below required threshold of {min_score}!")
        sys.exit(1)


def cli() -> None:
    """Main CLI entry point for WARDEN."""
    import argparse
    import os
    import sys
    from pathlib import Path

    # Ensure virtualenv bin directory containing bundled analyzers is in PATH
    bin_dir = str(Path(sys.executable).parent)
    if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="warden",
        description="🛡️ WARDEN: Autonomous Security & Architectural Quality Governance Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnek Kullanımlar:
  warden audit .                     # Mevcut dizindeki projeyi denetle
  warden audit /path/to/repo         # Belirtilen dizindeki projeyi denetle
  warden audit . --min-score 85      # Skor 85'in altındaysa hata döndür (CI/CD Quality Gate)
  warden serve --port 8000           # REST API & Swagger UI sunucusunu başlat
  warden --version                   # Sürüm bilgisini göster
        """,
    )
    parser.add_argument("--version", "-v", action="version", version="WARDEN v0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Kullanılabilir komutlar")

    # Subcommand: audit
    audit_parser = subparsers.add_parser(
        "audit",
        help="Hedef projede tam kapsamlı denetim (Layer 1 + Layer 2) çalıştırır ve rapor üretir",
        description="Hedef projede 14 mekanik analizör ve LLM mimari rubriklerini çalıştırır.",
    )
    audit_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Denetlenecek projenin yolu (Varsayılan: mevcut dizin '.')",
    )
    audit_parser.add_argument(
        "--path",
        default=None,
        help="Hedef proje yolu flag alternatifi (örn: --path /path/to/repo)",
    )
    audit_parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="CI/CD için minimum başarı eşiği (Skor bu değerin altındaysa exit code 1 döner)",
    )
    audit_parser.add_argument(
        "--full-history",
        action="store_true",
        default=False,
        help="Git geçmişinin tamamını tara (Varsayılan: son 6 ay)",
    )
    audit_parser.add_argument(
        "--incremental",
        action="store_true",
        default=False,
        help="Sadece değişen veya eklenen dosyaları tara (hızlı artımlı denetim)",
    )
    audit_parser.add_argument(
        "--since-commit",
        default=None,
        help="Artımlı denetim için referans commit veya dal (örn: HEAD~1, origin/main)",
    )

    # Subcommand: serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="FastAPI REST API ve MCP arka uç sunucusunu başlatır",
        description="FastAPI REST API sunucusunu başlatır (Swagger UI: http://localhost:8000/docs).",
    )
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bağlanılacak host adresi (Varsayılan: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Dinlenecek port numarası (Varsayılan: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Canlı yeniden yükleme modunu etkinleştirir")

    # Subcommand: milestone
    milestone_parser = subparsers.add_parser(
        "milestone",
        help="Bir audit raporunu referans baseline olarak işaretler",
        description="Belirtilen audit ID'sini milestone olarak işaretler; karşılaştırma raporlarında bu kullanılır.",
    )
    milestone_parser.add_argument("audit_id", type=int, help="Milestone yapılacak audit rapor ID'si")
    milestone_parser.add_argument("--label", default="baseline", help="Milestone etiketi (Varsayılan: 'baseline')")
    milestone_parser.add_argument("--clear", action="store_true", help="Mevcut milestone işaretini kaldırır")

    # Subcommand: generate-property-tests (D3)
    prop_parser = subparsers.add_parser(
        "generate-property-tests",
        help="Proje AST analizinden Hypothesis tabanlı property-based test taslakları üretir (D3)",
        description="Fonksiyon imzaları ve tip ipuçlarını inceleyerek idempotence, boundedness ve roundtrip testleri sentezler.",
    )
    prop_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Hedef projenin yolu (Varsayılan: '.')",
    )
    prop_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Üretilen test dosyasının kaydedileceği yol (örn: tests/test_properties_generated.py)",
    )
    prop_parser.add_argument(
        "--max-tests",
        type=int,
        default=15,
        help="Maksimum üretilecek property test sayısı (Varsayılan: 15)",
    )

    # Subcommand: generate-sbom (E4)
    sbom_parser = subparsers.add_parser(
        "generate-sbom",
        help="Proje bağımlılıkları için CycloneDX v1.5 JSON SBOM üretir (E4)",
        description="Supply chain güvenliği için CycloneDX v1.5 JSON Software Bill of Materials (SBOM) manifesti üretir.",
    )
    sbom_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Hedef projenin yolu (Varsayılan: '.')",
    )
    sbom_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="SBOM çıktısının kaydedileceği dosya yolu (örn: sbom.json)",
    )

    # Subcommand: scan-entropy (E5)
    entropy_parser = subparsers.add_parser(
        "scan-entropy",
        help="Shannon entropisi ile kaynak kodundaki potansiyel sır ve API anahtarlarını tarar (E5)",
        description="AST analizi ve Shannon entropi metriği ile kod tabanındaki yüksek rastgelelikli sırları tespit eder.",
    )
    entropy_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Hedef projenin yolu (Varsayılan: '.')",
    )
    entropy_parser.add_argument(
        "--max-findings",
        type=int,
        default=25,
        help="Maksimum listelenecek bulgu sayısı (Varsayılan: 25)",
    )

    # Subcommand: check-attack-surface (E1)
    attack_parser = subparsers.add_parser(
        "check-attack-surface",
        help="Proje bağımlılık grafını analiz ederek PageRank kritikliği ve saldırı yüzeyini hesaplar (E1)",
        description="networkx ile bağımlılık grafı kurarak en kritik paketleri, blast radius ve topolojiyi inceler.",
    )
    attack_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Hedef projenin yolu (Varsayılan: '.')",
    )
    attack_parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Listelenecek en kritik paket sayısı (Varsayılan: 10)",
    )

    # Subcommand: check-typosquatting (E2)
    typo_parser = subparsers.add_parser(
        "check-typosquatting",
        help="Paket adını PyPI popüler kütüphanelerine karşı typosquatting testine tabi tutar (E2)",
        description="Jaro-Winkler, Levenshtein, permütasyon ve homoglyph teknikleri ile typosquatting analizi yapar.",
    )
    typo_parser.add_argument(
        "package_name",
        help="Denetlenecek şüpheli paket adı (örn: reqeusts, colorma)",
    )

    # Subcommand: check-cycles (F4)
    cycles_parser = subparsers.add_parser(
        "check-cycles",
        help="Proje modülleri arasındaki döngüsel bağımlılıkları (circular imports) tespit eder (F4)",
        description="networkx ile import grafı kurarak dairesel bağımlılık döngülerini ve çözüm önerilerini raporlar.",
    )
    cycles_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Hedef projenin yolu (Varsayılan: '.')",
    )

    # Subcommand: metrics (G6)
    metrics_parser = subparsers.add_parser(
        "metrics",
        help="WARDEN operasyonel ve kalite metriklerini Prometheus / OpenMetrics formatında çıktılar (G6)",
        description="Prometheus scraping ve izlenebilirlik için metrikleri plain-text veya JSON formatında sunar.",
    )
    metrics_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Metrikleri Prometheus exposition yerine JSON formatında çıktılar",
    )

    # Subcommand: hook (H3)
    hook_parser = subparsers.add_parser(
        "hook",
        help="Git hook (pre-commit & pre-push) kalite kapısı yönetimi (H3)",
        description="Akıllı git kancalarını kurar, kaldırır veya çalıştırır.",
    )
    hook_subparsers = hook_parser.add_subparsers(dest="hook_action", help="Hook eylemi")

    # hook install
    install_parser = hook_subparsers.add_parser("install", help="Git kancalarını .git/hooks dizinine kurar")
    install_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    install_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push", "all"],
        default="all",
        help="Kurulacak hook türü (Varsayılan: all)",
    )
    install_parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Pre-push için minimum kabul skoru (Varsayılan: 80)",
    )

    # hook uninstall
    uninstall_parser = hook_subparsers.add_parser("uninstall", help="Kurulu WARDEN git kancalarını kaldırır")
    uninstall_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    uninstall_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push", "all"],
        default="all",
        help="Kaldırılacak hook türü (Varsayılan: all)",
    )

    # hook run
    run_parser = hook_subparsers.add_parser("run", help="Belirtilen git kancasını manuel çalıştırır")
    run_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    run_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push"],
        required=True,
        help="Çalıştırılacak hook türü",
    )
    run_parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Pre-push için minimum kalite skoru (Varsayılan: 80)",
    )

    # Subcommand: export-sarif (I4)
    sarif_parser = subparsers.add_parser(
        "export-sarif",
        help="Denetim bulgularını OASIS SARIF v2.1.0 formatında dışa aktarır (I4)",
        description="GitHub Code Scanning ve CI/CD için SARIF formatında statik analiz raporu üretir.",
    )
    sarif_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu (Varsayılan: '.')")
    sarif_parser.add_argument(
        "--output",
        "-o",
        default="warden-results.sarif",
        help="Çıktı SARIF dosya yolu (Varsayılan: warden-results.sarif)",
    )
    sarif_parser.add_argument("--audit-id", type=int, default=None, help="Mevcut bir veritabanı audit ID'sinden üret")

    # Subcommand: export-pdf (I1)
    pdf_parser = subparsers.add_parser(
        "export-pdf",
        help="Denetim sonuçları için kurumsal PDF Executive Summary raporu üretir (I1)",
        description="Yönetici düzeyinde renkli rozetler, metrik tabloları ve aksiyon önerileri içeren PDF raporu üretir.",
    )
    pdf_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu (Varsayılan: '.')")
    pdf_parser.add_argument(
        "--output",
        "-o",
        default="warden-executive-report.pdf",
        help="Çıktı PDF dosya yolu (Varsayılan: warden-executive-report.pdf)",
    )
    pdf_parser.add_argument("--audit-id", type=int, default=None, help="Mevcut bir veritabanı audit ID'sinden üret")

    # Subcommand: query (G1)
    query_parser = subparsers.add_parser(
        "query",
        help="Dashboard ve denetim verilerini doğal dil ile sorgular (Text-to-SQL) (G1)",
        description="Doğal dildeki soruları güvenli SQL sorgularına çevirerek veritabanında çalıştırır.",
    )
    query_parser.add_argument("query", help="Sorulacak doğal dil sorusu (örn: 'En düşük skorlu 5 repo')")
    query_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    query_parser.add_argument(
        "--provider",
        default=None,
        help="Kullanılacak LLM sağlayıcısı (gemini, openai, ollama vb.)",
    )

    # Subcommand: mutate (D1)
    mutate_parser = subparsers.add_parser(
        "mutate",
        help="AST Mutasyon Testi ile test paketinin mutant öldürme skorunu ve kör noktalarını analiz eder (D1)",
        description="Kaynak kodda yapay hatalar (mutantlar) türeterek testlerin bu hataları yakalayıp yakalamadığını ölçer.",
    )
    mutate_parser.add_argument("target", nargs="?", default=".", help="Hedef kaynak dosya veya dizin yolu (Varsayılan: '.')")
    mutate_parser.add_argument("--test-path", default=None, help="Koşulacak spesifik test dosyası veya dizini")
    mutate_parser.add_argument("--max-mutants", type=int, default=15, help="Test edilecek maksimum mutant sayısı (Varsayılan: 15)")
    mutate_parser.add_argument("--timeout", type=float, default=8.0, help="Her bir mutant testi için zaman aşımı saniyesi (Varsayılan: 8.0)")
    mutate_parser.add_argument("--dry-run", action="store_true", default=False, help="Testleri çalıştırmadan yalnızca potansiyel mutantları haritala")
    mutate_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    mutate_parser.add_argument("--output", "-o", default=None, help="Sonuç raporunu JSON dosyasına kaydet")

    # Subcommand: classify (C1)
    classify_parser = subparsers.add_parser(
        "classify",
        help="Proje arketipini (FastAPI, Django, CLI, ML, Library) ve dinamik kalite ağırlıklarını analiz eder (C1)",
        description="Deponun mimari özelliklerini analiz ederek proje arketipini ve özelleştirilmiş kalite ağırlıklarını gösterir.",
    )
    classify_parser.add_argument("target", nargs="?", default=".", help="Hedef proje dizini (Varsayılan: '.')")
    classify_parser.add_argument("--weights", action="store_true", default=False, help="Dinamik ağırlıklandırma tablosunu detaylı göster")
    classify_parser.add_argument("--override", action="append", default=None, help="Ağırlık ezme (Örn: --override security_supply_chain=0.40)")
    classify_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "audit":
        repo_target = args.path if args.path else args.target
        _run_audit_command(
            repo_target,
            args.min_score,
            full_history=args.full_history,
            incremental=args.incremental,
            since_commit=args.since_commit,
        )

    elif args.command == "serve":
        import uvicorn
        uvicorn.run("core.main:app", host=args.host, port=args.port, reload=args.reload)

    elif args.command == "milestone":
        _run_milestone_command(args.audit_id, args.label, args.clear)

    elif args.command == "generate-property-tests":
        _run_generate_property_tests(args.target, args.output, args.max_tests)

    elif args.command == "generate-sbom":
        _run_generate_sbom(args.target, args.output)

    elif args.command == "scan-entropy":
        _run_scan_entropy(args.target, args.max_findings)

    elif args.command == "check-attack-surface":
        _run_check_attack_surface(args.target, args.top)

    elif args.command == "check-typosquatting":
        _run_check_typosquatting(args.package_name)

    elif args.command == "check-cycles":
        _run_check_cycles(args.target)

    elif args.command == "metrics":
        _run_metrics_command(args.json)

    elif args.command == "hook":
        _run_hook_command(args)

    elif args.command == "export-sarif":
        _run_export_sarif(args.target, args.output, args.audit_id)

    elif args.command == "export-pdf":
        _run_export_pdf(args.target, args.output, args.audit_id)

    elif args.command == "query":
        _run_query_command(args.query, as_json=args.json, provider=args.provider)

    elif args.command == "mutate":
        _run_mutate_command(
            args.target,
            test_path=args.test_path,
            max_mutants=args.max_mutants,
            timeout=args.timeout,
            dry_run=args.dry_run,
            as_json=args.json,
            output_file=args.output,
        )

    elif args.command == "classify":
        _run_classify_command(
            args.target,
            show_weights=args.weights,
            overrides=args.override,
            as_json=args.json,
        )


def _run_classify_command(
    target: str,
    show_weights: bool = False,
    overrides: list[str] | None = None,
    as_json: bool = False,
) -> None:
    """Executes archetype classification and dynamic weighting analysis."""
    import json
    from pathlib import Path
    from core.services.dynamic_weight_service import DynamicWeightService

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


def _run_mutate_command(
    target: str,
    test_path: str | None = None,
    max_mutants: int = 15,
    timeout: float = 8.0,
    dry_run: bool = False,
    as_json: bool = False,
    output_file: str | None = None,
) -> None:
    """Executes mutation testing or dry-run discovery and displays findings."""
    import json
    from pathlib import Path
    from core.services.mutation_tester import MutationTesterService

    target_path = Path(target)
    test_p = Path(test_path) if test_path else None
    service = MutationTesterService(repo_path=Path("."))

    report = service.run_mutation_testing(
        target_path=target_path,
        test_path=test_p,
        max_mutants=max_mutants,
        timeout=timeout,
        dry_run=dry_run,
    )

    data = report.to_dict()

    if output_file:
        out_p = Path(output_file)
        out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if not as_json:
            print(f"[✓] Mutasyon raporu kaydedildi: {output_file}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    mode_str = "DRY-RUN (Haritalama)" if dry_run else "CANLI İCRA (Öldürme Testi)"
    print("\n" + "=" * 60)
    print(f"🧬 WARDEN AST MUTASYON TESTİ — {mode_str}")
    print("=" * 60)
    print(f"📁 Hedef Yol         : {report.target_path}")
    print(f"🔍 Keşfedilen Mutant : {report.total_mutants_discovered}")
    print(f"🧪 Test Edilen Mutant: {report.mutants_tested}")
    if not dry_run:
        print(f"🎯 Öldürülen (Killed): {report.killed} ✅")
        print(f"⚠️  Kurtulan (Survived): {report.survived} ❌")
        print(f"⏱️  Zaman Aşımı (Timeout): {report.timed_out}")
        print(f"💥 Hata (Errored)    : {report.errored}")
        print(f"🏆 Mutasyon Skoru    : %{report.mutation_score:.1f}")
    print(f"⏱️  Toplam Süre       : {report.execution_time_seconds:.3f} sn")
    print("-" * 60)

    if report.mutants:
        print("📋 Mutant Adayları (Örneklem):")
        for m in report.mutants[:15]:
            status_icon = "⚪" if dry_run else ("✅" if m.status in ("KILLED", "TIMEOUT") else "❌")
            print(f"  {status_icon} [{m.operator_category.upper()}] L{m.line_number}: {m.original_snippet}  -->  {m.mutated_snippet}")
            if not dry_run and m.killer_test:
                print(f"      Öldüren Test: {m.killer_test}")
    print("=" * 60 + "\n")


def _run_query_command(query_text: str, as_json: bool = False, provider: str | None = None) -> None:
    """Executes natural language dashboard query and prints tabular or JSON output."""
    import json
    import sys

    from core.infra.database import create_db_and_tables
    from core.services.nl_query_service import NaturalLanguageQueryService

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

    # Print clean ASCII table
    col_widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in data)) for c in cols}
    header_str = " | ".join(c.ljust(col_widths[c]) for c in cols)
    sep_str = "-+-".join("-" * col_widths[c] for c in cols)

    print(header_str)
    print(sep_str)
    for r in data:
        row_str = " | ".join(str(r.get(c, "")).ljust(col_widths[c]) for c in cols)
        print(row_str)
    print(f"\nToplam {res['row_count']} satır listelendi.")


def _run_export_sarif(target: str, output: str, audit_id: int | None = None) -> None:
    """Runs audit or fetches from DB, then exports findings to OASIS SARIF v2.1.0 JSON."""
    import asyncio
    import sys
    from pathlib import Path

    from sqlmodel import Session, select

    from core.infra.database import create_db_and_tables, engine
    from core.models.audit import AuditReport
    from core.services.sarif_service import SarifReportService

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


def _run_export_pdf(target: str, output: str, audit_id: int | None = None) -> None:
    """Runs audit or fetches from DB, then exports executive summary to PDF."""
    import asyncio
    import sys
    from pathlib import Path

    from sqlmodel import Session, select

    from core.infra.database import create_db_and_tables, engine
    from core.models.audit import AuditReport
    from core.services.pdf_report_service import PdfReportService

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


def _run_hook_command(args) -> None:
    """Dispatches git hook management and execution commands."""
    import sys
    from pathlib import Path

    from core.services.git_hook_service import GitHookService

    service = GitHookService()
    repo_path = Path(args.target).resolve()

    if not getattr(args, "hook_action", None):
        print("[!] Lütfen bir hook eylemi belirtin: install, uninstall, run")
        sys.exit(1)

    if args.hook_action == "install":
        ok = service.install(repo_path, hook_type=args.hook_type, min_score=args.min_score)
        if ok:
            print(f"[✓] WARDEN Git Hook ({args.hook_type}) başarıyla kuruldu: {repo_path}/.git/hooks/")
        else:
            print(f"[!] Git Hook kurulumu başarısız: {repo_path} geçerli bir git deposu mu?")
            sys.exit(1)

    elif args.hook_action == "uninstall":
        ok = service.uninstall(repo_path, hook_type=args.hook_type)
        if ok:
            print(f"[✓] WARDEN Git Hook ({args.hook_type}) kaldırıldı.")
        else:
            print("[!] Hook kaldırılamadı.")
            sys.exit(1)

    elif args.hook_action == "run":
        if args.hook_type == "pre-commit":
            passed, msg = service.run_pre_commit(repo_path)
            print(msg)
            if not passed:
                sys.exit(1)
        elif args.hook_type == "pre-push":
            import asyncio
            passed, msg = asyncio.run(service.run_pre_push(repo_path, min_score=args.min_score))
            print(msg)
            if not passed:
                sys.exit(1)


def _run_metrics_command(as_json: bool = False) -> None:
    """Exports WARDEN operational and quality metrics to stdout."""
    import json
    from core.services.metrics_service import MetricsCollectorService

    create_db_and_tables()
    collector = MetricsCollectorService()
    if as_json:
        data = collector.collect_metrics_data()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(collector.generate_prometheus_exposition())


def _run_check_cycles(target: str) -> None:
    """Detects circular import cycles using networkx AST graph analysis."""
    from pathlib import Path

    from core.services.circular_dependency_detector import CircularDependencyDetector

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


def _run_check_attack_surface(target: str, top: int) -> None:
    """Runs networkx PageRank and blast radius attack surface analysis."""
    from pathlib import Path

    from core.services.dependency_graph_analyzer import DependencyGraphAnalyzer

    p = Path(target).resolve()
    print(f"[*] Analyzing dependency graph and attack surface for {p} using networkx...")
    analyzer = DependencyGraphAnalyzer()
    report = analyzer.analyze(p, top_n=top)

    print(f"[+] Toplam Paket: {report.total_packages} (Doğrudan: {report.direct_packages_count}, Dolaylı: {report.transitive_packages_count})")
    print(f"[+] Bağımlılık Kenarları: {report.total_edges} · Graf Yoğunluğu: %{round(report.graph_density * 100, 2)}")

    print(f"\n--- En Kritik Bağımlılıklar (PageRank Skoru) ---")
    for node in report.critical_dependencies:
        scope_str = "DOĞRUDAN" if node.is_direct else "DOLAYLI"
        print(f"  #{node.criticality_rank} {node.name} ({node.version}) [{scope_str}] - PageRank: {node.pagerank_score:.4f}, Tahribat Yarıçapı (Blast Radius): {node.blast_radius} bileşen")

    print(f"\n--- En Yüksek Tahribat Yarıçapı (En Çok Bileşenin Bağlı Olduğu Paketler) ---")
    for node in report.high_blast_radius_nodes[:5]:
        print(f"  - {node.name}: {node.blast_radius} bileşen bu pakete bağımlı")


def _run_check_typosquatting(package_name: str) -> None:
    """Checks a candidate package name for typosquatting attacks."""
    from core.services.typosquatting_detector import TyposquattingDetector

    print(f"[*] Checking '{package_name}' for typosquatting attacks against top PyPI packages...")
    detector = TyposquattingDetector()
    match = detector.detect(package_name)

    if not match:
        print(f"[✓] '{package_name}' temiz görünüyor (Bilinen bir popüler paket taklidi tespit edilmedi).")
    else:
        print(f"[🚨] TYPOSQUATTING TESPİT EDİLDİ!")
        print(f"    - Şüpheli Paket: {match.suspect_package}")
        print(f"    - Hedef Alınan Popüler Paket: {match.target_package}")
        print(f"    - Benzerlik Skoru: %{round(match.similarity_score * 100, 1)}")
        print(f"    - Kullanılan Teknik: {match.technique}")
        print(f"    - Risk Seviyesi: {match.risk_level}")
        print(f"    - Detay: {match.reason}")


def _run_generate_sbom(target: str, output: str | None) -> None:
    """Generates CycloneDX v1.5 JSON SBOM for the target repository."""
    from pathlib import Path

    from core.services.sbom_generator import SBOMGeneratorService

    p = Path(target).resolve()
    print(f"[*] Analyzing manifests and generating CycloneDX v1.5 SBOM for {p} ...")
    service = SBOMGeneratorService()
    bom = service.generate_sbom(p)
    print(f"[+] CycloneDX SBOM başarıyla oluşturuldu: {len(bom.components)} bileşen tespit edildi.")
    for comp in bom.components[:10]:
        print(f"    - {comp.name} ({comp.version}) [{comp.scope}] -> {comp.purl}")
    if len(bom.components) > 10:
        print(f"    ... ve {len(bom.components) - 10} diğer bileşen")

    if output:
        out_path = Path(output).resolve()
        service.export_json(p, output_path=out_path)
        print(f"[✓] CycloneDX SBOM dosyaya kaydedildi: {out_path}")
    else:
        print("\n--- CycloneDX v1.5 JSON Önizleme ---")
        preview = bom.to_json(indent=2)[:600]
        print(preview + ("\n... [tam çıktıyı kaydetmek için --output belirtin]" if len(bom.to_json()) > 600 else ""))


def _run_scan_entropy(target: str, max_findings: int) -> None:
    """Scans repository files for high-entropy secrets."""
    from pathlib import Path

    from core.services.entropy_analyzer import EntropyAnalyzerService

    p = Path(target).resolve()
    print(f"[*] Scanning {p} using Shannon entropy analysis for potential secrets...")
    analyzer = EntropyAnalyzerService()
    findings = analyzer.scan_repository(p, max_findings=max_findings)

    if not findings:
        print("[✓] Kod tabanında şüpheli yüksek entropili sır bulunamadı (Temiz).")
        return

    print(f"[⚠️] {len(findings)} yüksek entropili dize / potansiyel sır tespit edildi:")
    for f in findings:
        print(f"    - [{f.confidence}] {f.file}:{f.line} -> {f.variable_name} ({f.masked_value}) - H={f.entropy_score:.2f} [{f.charset_type}]")


def _run_generate_property_tests(target: str, output: str | None, max_tests: int) -> None:
    """Scans repository and synthesizes Hypothesis property-based tests."""
    from pathlib import Path

    from core.services.property_test_generator import PropertyTestGenerator

    p = Path(target).resolve()
    print(f"[*] Analyzing Python AST in {p} for Property-Based Test invariants...")
    generator = PropertyTestGenerator()
    report = generator.scan_repository(p, max_templates=max_tests)

    print(f"[+] {report.candidate_functions_count} fonksiyon için Hypothesis property testi üretildi:")
    for t in report.templates:
        print(f"    - {t.target_function} ({t.invariant_type}) -> {t.file_path}")

    if output and report.full_test_suite_code:
        out_path = Path(output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.full_test_suite_code, encoding="utf-8")
        print(f"[✓] Test taslağı dosyaya yazıldı: {out_path}")
    elif not output and report.full_test_suite_code:
        print("\n--- Üretilen Test Taslağı (Önizleme) ---")
        preview = report.full_test_suite_code[:600]
        print(preview + ("\n... [kalanı görmek için --output belirtin]" if len(report.full_test_suite_code) > 600 else ""))


def _run_milestone_command(audit_id: int, label: str, clear: bool) -> None:
    """Marks or clears a milestone flag on a stored audit report."""
    from sqlmodel import Session, select

    from core.infra.database import create_db_and_tables, engine
    from core.models.audit import AuditReport

    create_db_and_tables()
    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == audit_id)).first()
        if not report:
            print(f"[!] Audit ID {audit_id} bulunamadı.")
            import sys
            sys.exit(1)

        if clear:
            report.is_milestone = False
            report.milestone_label = None
            session.add(report)
            session.commit()
            print(f"[✓] Audit #{audit_id} milestone işareti kaldırıldı.")
        else:
            report.is_milestone = True
            report.milestone_label = label
            session.add(report)
            session.commit()
            print(f"[✓] Audit #{audit_id} milestone olarak işaretlendi: '{label}'")
            print("    Karşılaştırma raporları artık bu audit'i referans olarak kullanacak.")


if __name__ == "__main__":
    cli()
