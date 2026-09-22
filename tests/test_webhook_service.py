"""Tests for WebhookService."""

import pytest

from core.services.webhook_service import WebhookService


@pytest.fixture
def service() -> WebhookService:
    return WebhookService()


class TestWebhookService:
    def test_empty_url_returns_false(self, service: WebhookService) -> None:
        import asyncio
        res = asyncio.run(service.send_audit_notification("", "repo", 85, "A", 80))
        assert not res

    def test_build_slack_payload(self, service: WebhookService) -> None:
        payload = service._build_slack_payload(
            repo_path="/test/repo",
            total_score=92,
            grade="A",
            l1=90,
            l2=95,
            regression=None,
        )
        assert "blocks" in payload
        assert len(payload["blocks"]) >= 2
        text = str(payload["blocks"])
        assert "92/100" in text
        assert "/test/repo" in text

    def test_build_slack_payload_with_regression(self, service: WebhookService) -> None:
        payload = service._build_slack_payload(
            repo_path="/test/repo",
            total_score=50,
            grade="F",
            l1=45,
            l2=55,
            regression="Total score dropped by 25 points",
        )
        assert any(b.get("type") == "context" for b in payload["blocks"])

    def test_build_discord_payload(self, service: WebhookService) -> None:
        payload = service._build_discord_payload(
            repo_path="/test/repo",
            total_score=85,
            grade="A",
            l1=80,
            l2=90,
            regression=None,
        )
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert embed["color"] == 0x22c55e  # Green
        assert any(f["name"] == "Toplam Skor" for f in embed["fields"])

    def test_build_discord_payload_red_on_regression(self, service: WebhookService) -> None:
        payload = service._build_discord_payload(
            repo_path="/test/repo",
            total_score=60,
            grade="D",
            l1=50,
            l2=70,
            regression="Regression detected",
        )
        embed = payload["embeds"][0]
        assert embed["color"] == 0xef4444  # Red
