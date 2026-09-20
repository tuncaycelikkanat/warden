"""FastAPI entry point and CLI audit runner for WARDEN."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.api.package import router as package_router
from core.api.scan import router as scan_router
from core.infra.database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager initializing database tables."""
    create_db_and_tables()
    yield


app = FastAPI(title="warden API", lifespan=lifespan)

app.include_router(scan_router)
app.include_router(package_router)


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint returning system status."""
    return {"status": "ok"}

def _run_audit_command(
    repo_target: str, min_score: int | None = None, full_history: bool = False
) -> None:
    """Executes end-to-end CLI audit, persists report and verifies quality gates."""
    import asyncio
    import sys

    from core.services.orchestrator import AuditOrchestrator
    from core.services.report import AuditReportService

    create_db_and_tables()

    mode_str = "tüm geçmiş" if full_history else "son 6 ay"
    print(f"[*] Starting full audit on {repo_target} (Kapsam: {mode_str}) ...")
    orch = AuditOrchestrator()
    res = asyncio.run(orch.run_full_audit(repo_target, full_history=full_history))


    reporter = AuditReportService()
    db_id = reporter.save_to_db(repo_target, res)
    md_path = reporter.generate_markdown(repo_target, res, current_id=db_id)

    total_score = res["scorecard"]["total_score"]
    grade = res["scorecard"]["grade"]
    print(f"[+] Audit complete! Score: {total_score}/100 (Grade: {grade})")
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

    # Subcommand: serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="FastAPI REST API ve MCP arka uç sunucusunu başlatır",
        description="FastAPI REST API sunucusunu başlatır (Swagger UI: http://localhost:8000/docs).",
    )
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bağlanılacak host adresi (Varsayılan: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Dinlenecek port numarası (Varsayılan: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Canlı yeniden yükleme modunu etkinleştirir")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "audit":
        repo_target = args.path if args.path else args.target
        _run_audit_command(repo_target, args.min_score, full_history=args.full_history)

    elif args.command == "serve":

        import uvicorn
        uvicorn.run("core.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    cli()
