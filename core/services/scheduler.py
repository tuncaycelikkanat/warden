"""Periodic and recurring audit scheduler service for WARDEN."""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """A configured recurring audit job."""
    repo_path: str
    interval_seconds: int
    full_history: bool = False
    webhook_url: str | None = None
    last_run: float = 0.0
    total_runs: int = 0
    is_active: bool = True


class AuditScheduler:
    """Manages and executes periodic audits in an asynchronous background loop."""

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def add_job(
        self,
        repo_path: str | Path,
        interval_seconds: int = 3600,
        full_history: bool = False,
        webhook_url: str | None = None,
    ) -> ScheduledJob:
        """Registers or updates a recurring audit job."""
        key = str(Path(repo_path).resolve())
        job = ScheduledJob(
            repo_path=key,
            interval_seconds=max(10, interval_seconds),
            full_history=full_history,
            webhook_url=webhook_url,
        )
        self._jobs[key] = job
        logger.info(f"Scheduled audit job added for {key} every {interval_seconds}s")
        return job

    def remove_job(self, repo_path: str | Path) -> bool:
        """Removes a scheduled audit job."""
        key = str(Path(repo_path).resolve())
        return self._jobs.pop(key, None) is not None

    def get_jobs(self) -> list[dict[str, Any]]:
        """Returns all scheduled audit jobs status."""
        return [
            {
                "repo_path": j.repo_path,
                "interval_seconds": j.interval_seconds,
                "last_run": j.last_run,
                "total_runs": j.total_runs,
                "is_active": j.is_active,
            }
            for j in self._jobs.values()
        ]

    async def run_due_jobs(self) -> int:
        """Checks and executes any jobs whose interval has elapsed. Returns number of executed jobs."""
        now = time.time()
        executed = 0

        for job in list(self._jobs.values()):
            if not job.is_active:
                continue
            if now - job.last_run >= job.interval_seconds:
                job.last_run = now
                job.total_runs += 1
                executed += 1
                try:
                    await self._execute_job(job)
                except Exception as e:
                    logger.error(f"Scheduled audit failed for {job.repo_path}: {e}")

        return executed

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Executes a single audit job and dispatches webhook if configured."""
        from core.services.orchestrator import AuditOrchestrator
        from core.services.report import AuditReportService

        orch = AuditOrchestrator()
        result = await orch.run_full_audit(job.repo_path, full_history=job.full_history)

        reporter = AuditReportService()
        db_id = reporter.save_to_db(job.repo_path, result)
        reporter.generate_markdown(job.repo_path, result, current_id=db_id)

        # Dispatch webhook if configured
        if job.webhook_url:
            from core.services.webhook_service import WebhookService
            sc = result.get("scorecard", {})
            wh_svc = WebhookService()
            await wh_svc.send_audit_notification(
                webhook_url=job.webhook_url,
                repo_path=job.repo_path,
                total_score=sc.get("total_score", 0),
                grade=sc.get("grade", "F"),
                layer1_score=sc.get("layer1_score", 0),
                layer2_score=sc.get("layer2_score"),
            )

    async def start(self, poll_interval_sec: int = 5) -> None:
        """Starts the background scheduler loop."""
        self._running = True
        logger.info("AuditScheduler started.")
        while self._running:
            await self.run_due_jobs()
            await asyncio.sleep(poll_interval_sec)

    def stop(self) -> None:
        """Stops the scheduler loop."""
        self._running = False
        logger.info("AuditScheduler stopped.")
