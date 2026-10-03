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
        vibe_score: float | None = None,
        tech_debt_hours: float | None = None,
        project_type: str | None = None,
        report_url: str | None = None,
        extra_facts: dict[str, Any] | None = None,
    ) -> bool:
        """Sends an audit summary to the specified webhook URL.

        Automatically formats payload for Slack, Discord, or Microsoft Teams if detected in the URL,
        otherwise delivers a clean structured JSON payload.
        """
        if not webhook_url:
            return False

        url = webhook_url.lower()
        if "slack.com" in url:
            payload = self._build_slack_payload(
                repo_path=repo_path,
                total_score=total_score,
                grade=grade,
                l1=layer1_score,
                l2=layer2_score,
                regression=regression_warning,
                vibe_score=vibe_score,
                tech_debt_hours=tech_debt_hours,
                project_type=project_type,
                report_url=report_url,
                extra_facts=extra_facts,
            )
        elif "discord.com" in url:
            payload = self._build_discord_payload(
                repo_path=repo_path,
                total_score=total_score,
                grade=grade,
                l1=layer1_score,
                l2=layer2_score,
                regression=regression_warning,
                vibe_score=vibe_score,
                tech_debt_hours=tech_debt_hours,
                project_type=project_type,
                report_url=report_url,
                extra_facts=extra_facts,
            )
        elif "office.com" in url or "teams.microsoft.com" in url or "webhook.office" in url:
            payload = self._build_teams_payload(
                repo_path=repo_path,
                total_score=total_score,
                grade=grade,
                l1=layer1_score,
                l2=layer2_score,
                regression=regression_warning,
                vibe_score=vibe_score,
                tech_debt_hours=tech_debt_hours,
                project_type=project_type,
                report_url=report_url,
                extra_facts=extra_facts,
            )
        else:
            payload = {
                "event": "warden.audit_completed",
                "repo_path": repo_path,
                "total_score": total_score,
                "grade": grade,
                "layer1_score": layer1_score,
                "layer2_score": layer2_score,
                "vibe_score": vibe_score,
                "tech_debt_hours": tech_debt_hours,
                "project_type": project_type,
                "report_url": report_url,
                "regression": regression_warning,
                "extra_facts": extra_facts or {},
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload, timeout=10.0)
                if resp.status_code in (200, 201, 202, 204):
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
        vibe_score: float | None = None,
        tech_debt_hours: float | None = None,
        project_type: str | None = None,
        report_url: str | None = None,
        extra_facts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Builds a Slack Block Kit payload with rich audit facts and actions."""
        emoji = "🚨" if regression else ("✅" if total_score >= 80 else "⚠️")
        title = f"{emoji} *WARDEN Audit Raporu* — `{repo_path}`"
        fields = [
            {"type": "mrkdwn", "text": f"*Skor:* {total_score}/100 ({grade})"},
            {"type": "mrkdwn", "text": f"*Katman 1:* {l1}/100"},
        ]
        if l2 is not None:
            fields.append({"type": "mrkdwn", "text": f"*Katman 2:* {l2}/100"})
        if vibe_score is not None:
            fields.append({"type": "mrkdwn", "text": f"*Vibe Skoru:* {vibe_score:.1f}/100"})
        if tech_debt_hours is not None:
            fields.append({"type": "mrkdwn", "text": f"*Teknik Borç:* {tech_debt_hours:.1f} saat"})
        if project_type:
            fields.append({"type": "mrkdwn", "text": f"*Proje Tipi:* `{project_type}`"})

        if extra_facts:
            for k, v in list(extra_facts.items())[:4]:
                fields.append({"type": "mrkdwn", "text": f"*{k}:* {v}"})

        blocks: list[dict[str, Any]] = [
            {"type": "section", "text": {"type": "mrkdwn", "text": title}},
            {"type": "section", "fields": fields},
        ]
        if regression:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"⚠️ *Regresyon Uyarısı:* {regression}"}],
            })
        if report_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Detaylı Raporu Aç"},
                        "url": report_url,
                        "style": "primary",
                    }
                ],
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
        vibe_score: float | None = None,
        tech_debt_hours: float | None = None,
        project_type: str | None = None,
        report_url: str | None = None,
        extra_facts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Builds a Discord Webhook embed payload."""
        # Discord color: Green (0x22c55e), Yellow (0xfacc15), Red (0xef4444)
        color = 0xef4444 if regression or total_score < 60 else (0x22c55e if total_score >= 80 else 0xfacc15)

        fields = [
            {"name": "Toplam Skor", "value": f"{total_score}/100 ({grade})", "inline": True},
            {"name": "Katman 1 (Mekanik)", "value": f"{l1}/100", "inline": True},
        ]
        if l2 is not None:
            fields.append({"name": "Katman 2 (LLM Rubrik)", "value": f"{l2}/100", "inline": True})
        if vibe_score is not None:
            fields.append({"name": "Vibe Skoru", "value": f"{vibe_score:.1f}/100", "inline": True})
        if tech_debt_hours is not None:
            fields.append({"name": "Teknik Borç Eforu", "value": f"{tech_debt_hours:.1f} saat", "inline": True})
        if project_type:
            fields.append({"name": "Proje Tipi", "value": project_type, "inline": True})

        if extra_facts:
            for k, v in list(extra_facts.items())[:4]:
                fields.append({"name": str(k), "value": str(v), "inline": True})

        if regression:
            fields.append({"name": "Regresyon Uyarısı", "value": regression, "inline": False})

        embed: dict[str, Any] = {
            "title": f"🛡️ WARDEN Audit Sonucu: {repo_path}",
            "color": color,
            "fields": fields,
            "footer": {"text": "WARDEN Autonomous Governance Engine v0.1.0"},
        }
        if report_url:
            embed["url"] = report_url

        return {"embeds": [embed]}

    def _build_teams_payload(
        self,
        repo_path: str,
        total_score: int,
        grade: str,
        l1: int,
        l2: int | None,
        regression: str | None,
        vibe_score: float | None = None,
        tech_debt_hours: float | None = None,
        project_type: str | None = None,
        report_url: str | None = None,
        extra_facts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Builds a Microsoft Teams Adaptive Card v1.4 payload compatible with Office 365 connectors and Workflows."""
        status_color = "Attention" if (regression or total_score < 60) else ("Good" if total_score >= 80 else "Warning")
        theme_hex = "ef4444" if (regression or total_score < 60) else ("22c55e" if total_score >= 80 else "facc15")

        facts = [
            {"title": "Toplam Skor", "value": f"{total_score}/100 ({grade})"},
            {"title": "Katman 1 (Mekanik)", "value": f"{l1}/100"},
        ]
        if l2 is not None:
            facts.append({"title": "Katman 2 (LLM Rubrik)", "value": f"{l2}/100"})
        if vibe_score is not None:
            facts.append({"title": "Vibe Skoru", "value": f"{vibe_score:.1f}/100"})
        if tech_debt_hours is not None:
            facts.append({"title": "Teknik Borç Eforu", "value": f"{tech_debt_hours:.1f} saat"})
        if project_type:
            facts.append({"title": "Proje Tipi", "value": project_type})

        if extra_facts:
            for k, v in list(extra_facts.items())[:4]:
                facts.append({"title": str(k), "value": str(v)})

        body_elements: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": f"🛡️ WARDEN Audit Raporu: {repo_path}",
                "color": status_color,
            },
            {
                "type": "FactSet",
                "facts": facts,
            },
        ]

        if regression:
            body_elements.append({
                "type": "TextBlock",
                "text": f"⚠️ Regresyon Uyarısı: {regression}",
                "color": "Attention",
                "weight": "Bolder",
                "wrap": True,
            })

        actions: list[dict[str, Any]] = []
        if report_url:
            actions.append({
                "type": "Action.OpenUrl",
                "title": "Detaylı Raporu İncele",
                "url": report_url,
            })

        card_content: dict[str, Any] = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body_elements,
        }
        if actions:
            card_content["actions"] = actions

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": card_content,
                }
            ],
            # Legacy O365 MessageCard fallback headers for backwards compatibility
            "summary": f"WARDEN Audit: {repo_path} ({total_score}/100 - {grade})",
            "themeColor": theme_hex,
        }
