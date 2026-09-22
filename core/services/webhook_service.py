"""Webhook dispatch service for Slack, Discord, and generic endpoints."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebhookService:
    """Dispatches formatted audit reports and regression alerts to webhook endpoints."""

    async def send_audit_notification(
        self,
        webhook_url: str,
        repo_path: str,
        total_score: int,
        grade: str,
        layer1_score: int,
        layer2_score: int | None = None,
        regression_warning: str | None = None,
    ) -> bool:
        """Sends an audit summary to the specified webhook URL.

        Automatically formats payload for Slack or Discord if detected in the URL,
        otherwise delivers a clean JSON payload.
        """
        if not webhook_url:
            return False

        url = webhook_url.lower()
        if "slack.com" in url:
            payload = self._build_slack_payload(
                repo_path, total_score, grade, layer1_score, layer2_score, regression_warning
            )
        elif "discord.com" in url:
            payload = self._build_discord_payload(
                repo_path, total_score, grade, layer1_score, layer2_score, regression_warning
            )
        else:
            payload = {
                "event": "warden.audit_completed",
                "repo_path": repo_path,
                "total_score": total_score,
                "grade": grade,
                "layer1_score": layer1_score,
                "layer2_score": layer2_score,
                "regression": regression_warning,
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                if resp.status_code in (200, 204):
                    logger.info(f"Webhook delivered successfully to {webhook_url[:30]}...")
                    return True
                else:
                    logger.warning(f"Webhook delivery failed with HTTP {resp.status_code}: {resp.text[:100]}")
                    return False
        except Exception as e:
            logger.warning(f"Failed to dispatch webhook: {e}")
            return False

    def _build_slack_payload(
        self,
        repo_path: str,
        total_score: int,
        grade: str,
        l1: int,
        l2: int | None,
        regression: str | None,
    ) -> dict[str, Any]:
        emoji = "🚨" if regression else ("✅" if total_score >= 80 else "⚠️")
        title = f"{emoji} *WARDEN Audit Raporu* — `{repo_path}`"
        fields = [
            {"type": "mrkdwn", "text": f"*Skor:* {total_score}/100 ({grade})"},
            {"type": "mrkdwn", "text": f"*Katman 1:* {l1}/100"},
        ]
        if l2 is not None:
            fields.append({"type": "mrkdwn", "text": f"*Katman 2:* {l2}/100"})

        blocks: list[dict[str, Any]] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title}},
            {"type": "section", "fields": fields},
        ]
        if regression:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"⚠️ *Regresyon Uyarısı:* {regression}"}],
            })

        return {"blocks": blocks}

    def _build_discord_payload(
        self,
        repo_path: str,
        total_score: int,
        grade: str,
        l1: int,
        l2: int | None,
        regression: str | None,
    ) -> dict[str, Any]:
        # Discord color: Green (0x22c55e), Yellow (0xfacc15), Red (0xef4444)
        color = 0xef4444 if regression or total_score < 60 else (0x22c55e if total_score >= 80 else 0xfacc15)

        fields = [
            {"name": "Toplam Skor", "value": f"{total_score}/100 ({grade})", "inline": True},
            {"name": "Katman 1 (Mekanik)", "value": f"{l1}/100", "inline": True},
        ]
        if l2 is not None:
            fields.append({"name": "Katman 2 (LLM Rubrik)", "value": f"{l2}/100", "inline": True},)

        if regression:
            fields.append({"name": "Regresyon Uyarısı", "value": regression, "inline": False})

        embed = {
            "title": f"🛡️ WARDEN Audit Sonucu: {repo_path}",
            "color": color,
            "fields": fields,
            "footer": {"text": "WARDEN Autonomous Governance Engine v0.1.0"},
        }

        return {"embeds": [embed]}
