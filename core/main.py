"""FastAPI entry point and CLI audit runner for WARDEN."""

from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


from fastapi import FastAPI
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
    """Observability endpoint providing operational metrics and health status."""
    import shutil
    from sqlmodel import Session, select
    from core.infra.cache import get_cache
    from core.infra.database import engine
    from core.models.audit import AuditReport

    # DB Stats
    total_audits = 0
    try:
        with Session(engine) as session:
            reports = session.exec(select(AuditReport.total_score)).all()
            total_audits = len(reports)
            avg_score = round(sum(reports) / max(1, total_audits), 1) if reports else 0
    except Exception:
        avg_score = 0

    # Cache type
    cache_backend = get_cache().__class__.__name__

    return {
        "status": "healthy",
        "version": "0.1.0",
        "uptime_seconds": round(time.time() - _APP_START_TIME, 1),
        "database": {
            "dialect": engine.dialect.name,
            "total_audits": total_audits,
            "average_score": avg_score,
        },
        "cache": {
            "backend": cache_backend,
        },
        "tools": {
            "gitleaks": shutil.which("gitleaks") is not None,
            "semgrep": shutil.which("semgrep") is not None,
            "jscpd": shutil.which("jscpd") is not None,
        },
    }


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
            print(f"    Karşılaştırma raporları artık bu audit'i referans olarak kullanacak.")


if __name__ == "__main__":
    cli()
