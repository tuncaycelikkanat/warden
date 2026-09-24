"""Unit tests for WebhookService and AuditScheduler."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.services.scheduler import AuditScheduler
from core.services.webhook_service import WebhookService


@pytest.mark.asyncio
async def test_webhook_empty_url():
    svc = WebhookService()
    res = await svc.send_audit_notification("", "/path", 80, "B", 80)
    assert res is False


@pytest.mark.asyncio
async def test_webhook_slack_payload():
    svc = WebhookService()
    # 1. With regression
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        success = await svc.send_audit_notification(
            "https://hooks.slack.com/services/xyz",
            "/repo",
            75,
            "C",
            70,
            layer2_score=80,
            regression_warning="Skor düştü!",
        )
        assert success is True
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "blocks" in payload
        assert "🚨" in payload["blocks"][0]["text"]["text"]

    # 2. Without regression, high score (>= 80)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        success = await svc.send_audit_notification(
            "https://hooks.slack.com/services/xyz",
            "/repo",
            95,
            "A",
            95,
            layer2_score=None,
            regression_warning=None,
        )
        assert success is True
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "✅" in payload["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_webhook_discord_payload():
    svc = WebhookService()
    # 1. Low score / regression (color = red 0xef4444)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=204)
        success = await svc.send_audit_notification(
            "https://discord.com/api/webhooks/xyz",
            "/repo",
            50,
            "F",
            50,
            regression_warning="Kritik açıklar tespit edildi",
        )
        assert success is True
        args, kwargs = mock_post.call_args
        embed = kwargs["json"]["embeds"][0]
        assert embed["color"] == 0xef4444

    # 2. Medium score (color = yellow 0xfacc15)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        await svc.send_audit_notification(
            "https://discord.com/api/webhooks/xyz",
            "/repo",
            70,
            "C",
            70,
        )
        args, kwargs = mock_post.call_args
        embed = kwargs["json"]["embeds"][0]
        assert embed["color"] == 0xfacc15


@pytest.mark.asyncio
async def test_webhook_generic_and_failure():
    svc = WebhookService()
    # Generic webhook with HTTP 500
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=500, text="Internal Error")
        success = await svc.send_audit_notification(
            "https://my-webhook.example.com/api",
            "/repo",
            85,
            "B",
            85,
        )
        assert success is False

    # Generic webhook with network exception
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        success = await svc.send_audit_notification(
            "https://my-webhook.example.com/api",
            "/repo",
            85,
            "B",
            85,
        )
        assert success is False


def test_scheduler_add_remove_get_jobs(tmp_path):
    scheduler = AuditScheduler()
    job = scheduler.add_job(tmp_path, interval_seconds=100, full_history=True, webhook_url="https://hooks.slack.com/1")
    assert job.repo_path == str(tmp_path.resolve())
    assert job.interval_seconds == 100

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0]["repo_path"] == str(tmp_path.resolve())

    # Remove job
    assert scheduler.remove_job(tmp_path) is True
    assert scheduler.remove_job(tmp_path) is False
    assert len(scheduler.get_jobs()) == 0


@pytest.mark.asyncio
async def test_scheduler_run_due_jobs_and_webhook(tmp_path):
    scheduler = AuditScheduler()
    job = scheduler.add_job(tmp_path, interval_seconds=10, webhook_url="https://discord.com/api/webhooks/test")

    mock_audit_res = {
        "scorecard": {
            "total_score": 90,
            "grade": "A",
            "layer1_score": 90,
            "layer2_score": 90,
        }
    }

    with patch("core.services.orchestrator.AuditOrchestrator.run_full_audit", return_value=mock_audit_res), \
         patch("core.services.report.AuditReportService.save_to_db", return_value=99), \
         patch("core.services.report.AuditReportService.generate_markdown", return_value="/tmp/rep.md"), \
         patch("core.services.webhook_service.WebhookService.send_audit_notification", new_callable=AsyncMock) as mock_wh:

        # Due job runs
        executed = await scheduler.run_due_jobs()
        assert executed == 1
        assert job.total_runs == 1
        mock_wh.assert_awaited_once()

        # Job not due yet (interval has not elapsed)
        executed_second = await scheduler.run_due_jobs()
        assert executed_second == 0

        # Inactive job should not run
        job.is_active = False
        job.last_run = 0.0
        assert await scheduler.run_due_jobs() == 0


@pytest.mark.asyncio
async def test_scheduler_start_and_stop():
    scheduler = AuditScheduler()
    with patch.object(scheduler, "run_due_jobs", new_callable=AsyncMock) as mock_due:
        # Start in background task and stop after brief interval
        task = asyncio.create_task(scheduler.start(poll_interval_sec=0.01))
        await asyncio.sleep(0.05)
        scheduler.stop()
        await task
        assert mock_due.await_count >= 1
