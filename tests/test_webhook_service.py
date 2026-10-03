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

    def test_build_teams_payload(self, service: WebhookService) -> None:
        payload = service._build_teams_payload(
            repo_path="/test/repo",
            total_score=88,
            grade="B",
            l1=85,
            l2=90,
            regression=None,
        )
        assert payload["type"] == "message"
        assert len(payload["attachments"]) == 1
        att = payload["attachments"][0]
        assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
        card = att["content"]
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"
        assert payload["themeColor"] == "22c55e"
        assert "88/100" in payload["summary"]

        # Check facts in body
        fact_blocks = [b for b in card["body"] if b.get("type") == "FactSet"]
        assert len(fact_blocks) == 1
        facts = fact_blocks[0]["facts"]
        assert any(f["title"] == "Toplam Skor" and "88/100" in f["value"] for f in facts)

    def test_build_teams_payload_with_regression_and_extras(self, service: WebhookService) -> None:
        payload = service._build_teams_payload(
            repo_path="/test/repo",
            total_score=55,
            grade="F",
            l1=50,
            l2=60,
            regression="Critical drop in security score",
            vibe_score=68.5,
            tech_debt_hours=14.2,
            project_type="FastAPI Web Backend",
            report_url="https://warden.example.com/reports/123",
            extra_facts={"CircularCycles": "2 cycles"},
        )
        card = payload["attachments"][0]["content"]
        assert payload["themeColor"] == "ef4444"

        # Check regression block
        body = card["body"]
        reg_block = [b for b in body if b.get("text", "").startswith("⚠️ Regresyon")]
        assert len(reg_block) == 1
        assert reg_block[0]["color"] == "Attention"

        # Check facts
        facts = body[1]["facts"]
        assert any(f["title"] == "Vibe Skoru" and "68.5/100" in f["value"] for f in facts)
        assert any(f["title"] == "Teknik Borç Eforu" and "14.2 saat" in f["value"] for f in facts)
        assert any(f["title"] == "CircularCycles" and "2 cycles" in f["value"] for f in facts)

        # Check Action button
        assert "actions" in card
        assert card["actions"][0]["type"] == "Action.OpenUrl"
        assert card["actions"][0]["url"] == "https://warden.example.com/reports/123"

    def test_build_slack_payload_with_extras(self, service: WebhookService) -> None:
        payload = service._build_slack_payload(
            repo_path="/test/repo",
            total_score=92,
            grade="A",
            l1=90,
            l2=95,
            regression=None,
            vibe_score=91.5,
            tech_debt_hours=2.5,
            project_type="CLI Tool",
            report_url="https://warden.example.com/audit/99",
            extra_facts={"Branch": "main"},
        )
        blocks = payload["blocks"]
        fields = blocks[1]["fields"]
        assert any("*Vibe Skoru:* 91.5/100" in f["text"] for f in fields)
        assert any("*Teknik Borç:* 2.5 saat" in f["text"] for f in fields)
        assert any("*Branch:* main" in f["text"] for f in fields)

        # Action button
        action_block = [b for b in blocks if b.get("type") == "actions"]
        assert len(action_block) == 1
        btn = action_block[0]["elements"][0]
        assert btn["type"] == "button"
        assert btn["url"] == "https://warden.example.com/audit/99"

    def test_build_discord_payload_with_extras(self, service: WebhookService) -> None:
        payload = service._build_discord_payload(
            repo_path="/test/repo",
            total_score=85,
            grade="A",
            l1=80,
            l2=90,
            regression=None,
            vibe_score=88.0,
            tech_debt_hours=4.0,
            project_type="Library",
            report_url="https://warden.example.com/report/1",
        )
        embed = payload["embeds"][0]
        assert embed["url"] == "https://warden.example.com/report/1"
        assert any(f["name"] == "Vibe Skoru" and "88.0/100" in f["value"] for f in embed["fields"])
        assert any(f["name"] == "Teknik Borç Eforu" and "4.0 saat" in f["value"] for f in embed["fields"])

    def test_send_audit_notification_routing(self, service: WebhookService, monkeypatch: pytest.MonkeyPatch) -> None:
        import asyncio

        captured_urls: list[str] = []
        captured_payloads: list[dict] = []

        class DummyResponse:
            status_code = 200
            text = "ok"

        class DummyClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            async def post(self, url: str, json: dict, **kwargs):
                captured_urls.append(url)
                captured_payloads.append(json)
                return DummyResponse()

        monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: DummyClient())

        # Test MS Teams URL detection
        res = asyncio.run(
            service.send_audit_notification(
                webhook_url="https://subdomain.webhook.office.com/webhookb2/teams-channel",
                repo_path="/repo/teams",
                total_score=85,
                grade="A",
                layer1_score=80,
            )
        )
        assert res is True
        assert captured_urls[0].startswith("https://subdomain.webhook.office.com")
        assert captured_payloads[0]["type"] == "message"
        assert captured_payloads[0]["attachments"][0]["content"]["type"] == "AdaptiveCard"

        # Test Generic URL
        res2 = asyncio.run(
            service.send_audit_notification(
                webhook_url="https://api.example.com/custom/webhook",
                repo_path="/repo/generic",
                total_score=75,
                grade="C",
                layer1_score=70,
                vibe_score=80.0,
                tech_debt_hours=6.5,
            )
        )
        assert res2 is True
        assert captured_payloads[1]["event"] == "warden.audit_completed"
        assert captured_payloads[1]["vibe_score"] == 80.0
        assert captured_payloads[1]["tech_debt_hours"] == 6.5
