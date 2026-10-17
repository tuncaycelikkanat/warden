"""FastAPI application factory and HTTP routing setup for WARDEN."""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.api.dashboard import get_badge
from core.api.dashboard import router as dashboard_router
from core.api.package import router as package_router
from core.api.rate_limiter import RateLimitMiddleware
from core.api.scan import router as scan_router
from core.infra.database import create_db_and_tables

load_dotenv()
logger = logging.getLogger(__name__)

_APP_START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager initializing database tables."""
    create_db_and_tables()
    yield


def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    app = FastAPI(title="WARDEN API", version="0.1.0", lifespan=lifespan)

    # Enforce sliding-window rate limits (120 req/min, exempts /health, /docs, /dashboard)
    app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

    app.include_router(scan_router)
    app.include_router(package_router)
    app.include_router(dashboard_router)

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

    @app.get("/badge.svg", response_class=Response, include_in_schema=False)
    @app.get("/api/v1/badge", response_class=Response)
    async def root_badge(
        repo_path: str | None = None,
        score: float | None = None,
        grade: str | None = None,
        label: str = "WARDEN",
    ) -> Response:
        """Dynamic SVG badge generation endpoint for README integration."""
        return await get_badge(repo_path=repo_path, score=score, grade=grade, label=label)

    # Dashboard frontend (SPA build output) — mount if exists
    dashboard_dist = Path(__file__).resolve().parent.parent.parent / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/dashboard", StaticFiles(directory=str(dashboard_dist), html=True), name="dashboard-ui")

    return app


# Default singleton instance for uvicorn import ("core.api.app:app")
app = create_app()
