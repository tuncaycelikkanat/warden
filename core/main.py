from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.infra.database import create_db_and_tables
from core.api.scan import router as scan_router
from core.api.package import router as package_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(title="warden API", lifespan=lifespan)

app.include_router(scan_router)
app.include_router(package_router)

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import sys
    import asyncio
    
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        from dotenv import load_dotenv
        load_dotenv()
        
        import argparse
        parser = argparse.ArgumentParser(description="Run WARDEN full audit")
        parser.add_argument("audit", help="Run audit command")
        parser.add_argument("--path", default=".", help="Path to repository")
        args = parser.parse_args()
        
        async def run_cli_audit():
            from core.services.orchestrator import AuditOrchestrator
            from core.services.report import AuditReportService
            create_db_and_tables()
            
            print(f"[*] Starting full audit on {args.path} ...")
            orch = AuditOrchestrator()
            res = await orch.run_full_audit(args.path)
            
            reporter = AuditReportService()
            db_id = reporter.save_to_db(args.path, res)
            md_path = reporter.generate_markdown(args.path, res)
            
            print(f"[+] Audit complete! Score: {res['scorecard']['total_score']}/100 (Grade: {res['scorecard']['grade']})")
            print(f"[+] Saved to DB (ID: {db_id}) and {md_path}")
            
        asyncio.run(run_cli_audit())
    else:
        import uvicorn
        uvicorn.run("core.main:app", host="0.0.0.0", port=8000, reload=True)
