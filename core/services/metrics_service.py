"""Prometheus and OpenMetrics metrics collection and exposition service for WARDEN."""

import importlib.util
import logging
import shutil
import time
from typing import Any

from sqlmodel import Session, select

from core.infra.cache import get_cache
from core.infra.database import engine
from core.models.audit import AuditReport

logger = logging.getLogger(__name__)


class MetricsCollectorService:
    """Collects operational, database, and analyzer metrics and formats them

    for Prometheus / OpenMetrics scraping.
    """

    def __init__(self, start_time: float | None = None) -> None:
        self.start_time = start_time if start_time is not None else time.time()

    def get_uptime_seconds(self) -> float:
        """Returns uptime in seconds since service initialization."""
        return max(0.0, round(time.time() - self.start_time, 2))

    def get_tool_status(self) -> dict[str, int]:
        """Checks availability of external CLI tools and core analysis libraries."""
        tools = {
            "gitleaks": 1 if shutil.which("gitleaks") is not None else 0,
            "semgrep": 1 if shutil.which("semgrep") is not None else 0,
            "jscpd": 1 if shutil.which("jscpd") is not None else 0,
            "trivy": 1 if shutil.which("trivy") is not None else 0,
            "hypothesis": 1 if importlib.util.find_spec("hypothesis") is not None else 0,
        }
        return tools

    def get_database_metrics(self) -> dict[str, Any]:
        """Queries the database to compute aggregate audit counts and scores."""
        metrics: dict[str, Any] = {
            "total_audits": 0,
            "average_score": 0.0,
            "last_score": 0.0,
            "latest_layer1_score": 0.0,
            "latest_layer2_score": 0.0,
            "latest_tech_debt_hours": 0.0,
            "grades": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
        }

        try:
            with Session(engine) as session:
                reports = session.exec(
                    select(AuditReport).order_by(AuditReport.id.desc())
                ).all()

                if not reports:
                    return metrics

                metrics["total_audits"] = len(reports)
                scores = [r.total_score for r in reports]
                metrics["average_score"] = round(sum(scores) / len(scores), 1)

                latest = reports[0]
                metrics["last_score"] = float(latest.total_score)
                metrics["latest_layer1_score"] = float(latest.layer1_score)
                metrics["latest_layer2_score"] = float(latest.layer2_score if latest.layer2_score >= 0 else 0.0)

                # Count grades
                for r in reports:
                    g = (r.grade or "F").upper()
                    if g in metrics["grades"]:
                        metrics["grades"][g] += 1
                    else:
                        metrics["grades"]["F"] += 1

                # Extract tech debt hours if present in raw_data
                raw = latest.raw_data or {}
                if isinstance(raw, dict):
                    # Check in scorecard or layer1 or tech_debt
                    td = raw.get("scorecard", {}).get("tech_debt") or raw.get("tech_debt")
                    if isinstance(td, dict) and "remediation_estimate" in td:
                        rem = td.get("remediation_estimate")
                        if isinstance(rem, dict) and "total_hours" in rem:
                            metrics["latest_tech_debt_hours"] = float(rem["total_hours"])
        except Exception as e:
            logger.warning(f"Failed to query database metrics: {e}")

        return metrics

    def get_cache_backend_name(self) -> str:
        """Returns the name of the active caching provider."""
        try:
            return get_cache().__class__.__name__
        except Exception:
            return "Unknown"

    def collect_metrics_data(self, uptime_override: float | None = None) -> dict[str, Any]:
        """Gathers all operational metrics into a structured Python dictionary."""
        uptime = uptime_override if uptime_override is not None else self.get_uptime_seconds()
        db_stats = self.get_database_metrics()
        tool_status = self.get_tool_status()
        cache_backend = self.get_cache_backend_name()

        return {
            "status": "healthy",
            "version": "0.1.0",
            "uptime_seconds": uptime,
            "database": {
                "dialect": engine.dialect.name,
                "total_audits": db_stats["total_audits"],
                "average_score": db_stats["average_score"],
                "last_score": db_stats["last_score"],
                "grades": db_stats["grades"],
            },
            "latest_audit": {
                "score": db_stats["last_score"],
                "layer1_score": db_stats["latest_layer1_score"],
                "layer2_score": db_stats["latest_layer2_score"],
                "tech_debt_hours": db_stats["latest_tech_debt_hours"],
            },
            "cache": {
                "backend": cache_backend,
            },
            "tools": tool_status,
        }

    def generate_prometheus_exposition(self, uptime_override: float | None = None) -> str:
        """Renders standard Prometheus / OpenMetrics plain-text exposition format."""
        uptime = uptime_override if uptime_override is not None else self.get_uptime_seconds()
        db_stats = self.get_database_metrics()
        tool_status = self.get_tool_status()
        cache_backend = self.get_cache_backend_name()

        lines: list[str] = [
            "# HELP warden_uptime_seconds WARDEN system uptime in seconds",
            "# TYPE warden_uptime_seconds gauge",
            f"warden_uptime_seconds {uptime}",
            "",
            "# HELP warden_total_audits_count Total number of completed audit reports in database",
            "# TYPE warden_total_audits_count counter",
            f"warden_total_audits_count {db_stats['total_audits']}",
            "",
            "# HELP warden_average_audit_score Historical average quality audit score across all runs (0-100)",
            "# TYPE warden_average_audit_score gauge",
            f"warden_average_audit_score {db_stats['average_score']}",
            "",
            "# HELP warden_last_audit_score Quality audit score of the most recent audit (0-100)",
            "# TYPE warden_last_audit_score gauge",
            f"warden_last_audit_score {db_stats['last_score']}",
            "",
            "# HELP warden_latest_layer1_score Mechanical Layer 1 score of the most recent audit (0-100)",
            "# TYPE warden_latest_layer1_score gauge",
            f"warden_latest_layer1_score {db_stats['latest_layer1_score']}",
            "",
            "# HELP warden_latest_layer2_score LLM Architectural Rubric Layer 2 score of the most recent audit (0-100)",
            "# TYPE warden_latest_layer2_score gauge",
            f"warden_latest_layer2_score {db_stats['latest_layer2_score']}",
            "",
            "# HELP warden_latest_tech_debt_hours Estimated technical debt remediation effort in hours from the latest audit",
            "# TYPE warden_latest_tech_debt_hours gauge",
            f"warden_latest_tech_debt_hours {db_stats['latest_tech_debt_hours']}",
            "",
            "# HELP warden_audits_by_grade_total Total count of audit reports categorized by assigned letter grade",
            "# TYPE warden_audits_by_grade_total counter",
        ]

        for grade in ["A", "B", "C", "D", "F"]:
            count = db_stats["grades"].get(grade, 0)
            lines.append(f'warden_audits_by_grade_total{{grade="{grade}"}} {count}')

        lines.extend([
            "",
            "# HELP warden_tool_availability Operational availability of analyzer binaries and libraries (1=available, 0=missing)",
            "# TYPE warden_tool_availability gauge",
        ])
        for tool, status in sorted(tool_status.items()):
            lines.append(f'warden_tool_availability{{tool="{tool}"}} {status}')

        lines.extend([
            "",
            "# HELP warden_cache_backend_info Active cache backend provider info",
            "# TYPE warden_cache_backend_info gauge",
            f'warden_cache_backend_info{{backend="{cache_backend}"}} 1',
            "",
            "# HELP warden_build_info Build and version metadata for WARDEN",
            "# TYPE warden_build_info gauge",
            f'warden_build_info{{version="0.1.0",dialect="{engine.dialect.name}"}} 1',
            "",
        ])

        return "\n".join(lines)
