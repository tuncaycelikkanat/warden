"""Tests for AuditScheduler."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.services.scheduler import AuditScheduler


@pytest.fixture
def scheduler() -> AuditScheduler:
    return AuditScheduler()


class TestAuditScheduler:
    def test_add_and_remove_job(self, scheduler: AuditScheduler, tmp_path: Path) -> None:
        job = scheduler.add_job(tmp_path, interval_seconds=120)
        assert job.interval_seconds == 120
        assert str(tmp_path.resolve()) == job.repo_path

        jobs = scheduler.get_jobs()
        assert len(jobs) == 1

        removed = scheduler.remove_job(tmp_path)
        assert removed
        assert len(scheduler.get_jobs()) == 0

    @pytest.mark.asyncio
    async def test_run_due_jobs_executes_eligible_jobs(self, scheduler: AuditScheduler, tmp_path: Path) -> None:
        scheduler.add_job(tmp_path, interval_seconds=10)

        with patch.object(scheduler, "_execute_job", new_callable=AsyncMock) as mock_exec:
            executed = await scheduler.run_due_jobs()
            assert executed == 1
            mock_exec.assert_awaited_once()

            # Running immediately again should execute 0 (interval not yet elapsed)
            executed_again = await scheduler.run_due_jobs()
            assert executed_again == 0

    def test_stop_scheduler(self, scheduler: AuditScheduler) -> None:
        scheduler._running = True
        scheduler.stop()
        assert not scheduler._running
