"""GitHub PR Review Bot & Automated Commenter for WARDEN (Section G4).

Provides autonomous code quality governance for GitHub Pull Requests:
1. Formats executive Markdown Scorecards with SVG badges and quality gate status.
2. Identifies critical diff findings and prepares inline code review comments.
3. Automatically creates or updates (upsert) PR summary comments via GitHub REST API.
4. Posts batch Pull Request Reviews ('APPROVE', 'REQUEST_CHANGES', 'COMMENT').
5. Generates turnkey GitHub Actions CI/CD workflows for PR quality gates.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BOT_SIGNATURE = "<!-- WARDEN_PR_REVIEW_BOT -->"


@dataclass
class InlineReviewComment:
    """A line-level review comment attached to a changed file in a Pull Request."""

    path: str
    line: int
    body: str
    severity: str = "MEDIUM"  # "CRITICAL" | "HIGH" | "MEDIUM" | "INFO"
    side: str = "RIGHT"

    def to_github_payload(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "side": self.side,
            "body": self.body,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PRReviewReport:
    """Summary of a Pull Request review execution and quality gate verdict."""

    owner: str
    repo: str
    pull_number: int
    commit_sha: str | None
    total_score: float
    grade: str
    passed_quality_gate: bool
    min_score: int
    action_event: str  # "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
    summary_markdown: str
    inline_comments: list[InlineReviewComment] = field(default_factory=list)
    comment_id: int | None = None
    review_id: int | None = None
    is_updated: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["inline_comments"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.inline_comments]
        return data


class GitHubAPIClient:
    """Interacts with GitHub REST API v3/v4 for Pull Request reviews and comments."""

    def __init__(self, token: str | None = None, base_url: str = "https://api.github.com") -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=30.0)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "WARDEN-Governance-Bot/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_pull_request(self, owner: str, repo: str, pull_number: int) -> dict[str, Any]:
        """Fetches PR metadata including head commit SHA and base branch."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        res = self.client.get(url, headers=self._get_headers())
        if res.status_code != 200:
            logger.warning(f"GitHub API get_pull_request failed ({res.status_code}): {res.text}")
            return {}
        return res.json()

    def get_pull_request_files(self, owner: str, repo: str, pull_number: int) -> list[dict[str, Any]]:
        """Fetches list of changed files in the Pull Request."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        res = self.client.get(url, headers=self._get_headers())
        if res.status_code != 200:
            logger.warning(f"GitHub API get_pull_request_files failed ({res.status_code}): {res.text}")
            return []
        return res.json()

    def find_existing_warden_comment(self, owner: str, repo: str, pull_number: int) -> int | None:
        """Finds previously posted WARDEN comment ID by checking for BOT_SIGNATURE."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        res = self.client.get(url, headers=self._get_headers())
        if res.status_code != 200:
            return None

        comments = res.json()
        if isinstance(comments, list):
            for c in comments:
                if BOT_SIGNATURE in c.get("body", ""):
                    return c.get("id")
        return None

    def upsert_summary_comment(self, owner: str, repo: str, pull_number: int, body: str) -> tuple[int | None, bool]:
        """Creates or edits the WARDEN issue summary comment to avoid comment clutter."""
        existing_id = self.find_existing_warden_comment(owner, repo, pull_number)

        if existing_id is not None:
            # Edit existing comment
            url = f"{self.base_url}/repos/{owner}/{repo}/issues/comments/{existing_id}"
            res = self.client.patch(url, headers=self._get_headers(), json={"body": body})
            if res.status_code in (200, 201):
                return existing_id, True
            logger.warning(f"Failed to patch GitHub comment {existing_id}: {res.text}")

        # Post new comment
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        res = self.client.post(url, headers=self._get_headers(), json={"body": body})
        if res.status_code in (200, 201):
            return res.json().get("id"), False

        logger.warning(f"Failed to create GitHub comment: {res.text}")
        return None, False

    def post_pull_request_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_sha: str,
        body: str,
        event: str = "COMMENT",
        comments: list[InlineReviewComment] | None = None,
    ) -> dict[str, Any]:
        """Submits a formal GitHub Pull Request Review with optional inline comments."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        payload: dict[str, Any] = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }

        if comments:
            payload["comments"] = [c.to_github_payload() for c in comments[:30]]  # GitHub caps review comments

        res = self.client.post(url, headers=self._get_headers(), json=payload)
        if res.status_code in (200, 201):
            return res.json()

        logger.warning(f"Failed to post GitHub PR review ({res.status_code}): {res.text}")
        return {}


class GitHubPRReviewBot:
    """Coordinates PR quality audits, markdown formatting, inline reviews, and bot actions."""

    def __init__(self, token: str | None = None, api_client: GitHubAPIClient | None = None) -> None:
        self.api_client = api_client or GitHubAPIClient(token=token)

    def format_pr_scorecard_markdown(
        self,
        scorecard: dict[str, Any],
        findings: list[dict[str, Any]] | None = None,
        min_score: int = 80,
        repo_name: str = "repository",
        pr_number: int = 1,
    ) -> str:
        """Constructs an executive GitHub Markdown table with badges and collapsible findings."""
        card = scorecard.get("scorecard", scorecard)
        total_score = float(card.get("total_score", 0.0))
        grade = str(card.get("grade", "C"))
        layer1 = float(card.get("layer1_score", 0.0))
        layer2_raw = card.get("layer2_score")
        layer2 = float(layer2_raw) if layer2_raw not in (None, -1) else None

        groups = card.get("groups", card.get("group_scores", {})) or {}

        def _get_val(k1: str, k2: str) -> float:
            v = groups.get(k1)
            if v is None:
                v = groups.get(k2)
            if v is None:
                return 75.0
            try:
                return float(v)
            except (ValueError, TypeError):
                return 75.0

        sec = _get_val("security", "security_supply_chain")
        code_h = _get_val("code_health", "code_health_test")
        struct = _get_val("structural", "structural_health")
        resil = _get_val("resilience", "resilience_performance")
        hygiene = _get_val("dev_hygiene", "dev_hygiene_devops")

        all_findings = findings or []
        critical_count = sum(1 for f in all_findings if str(f.get("severity", "")).upper() == "CRITICAL")
        sum(1 for f in all_findings if str(f.get("severity", "")).upper() == "HIGH")

        passed_gate = (total_score >= min_score) and (critical_count == 0)

        # SVG Badges
        badge_color = "brightgreen" if total_score >= 85 else ("green" if total_score >= 70 else ("yellow" if total_score >= 60 else "red"))
        gate_color = "brightgreen" if passed_gate else "red"
        gate_status = "PASSED" if passed_gate else "FAILED"

        score_badge = f"https://img.shields.io/badge/WARDEN_Score-{int(total_score)}%2F100_{grade}-{badge_color}?style=for-the-badge&logo=shield"
        gate_badge = f"https://img.shields.io/badge/Quality_Gate-{gate_status}-{gate_color}?style=for-the-badge"

        verdict_banner = (
            f"> ### ✅ Quality Gate Passed\n> Bu PR, belirlenen minimum kalite eşiğini (**{min_score}/100**) başarıyla aştı ve kritik güvenlik riski içermiyor."
            if passed_gate
            else f"> ### 🚨 Quality Gate Failed\n> Bu PR'ın genel kalite skoru (**{int(total_score)}/100**) asgari eşiğin (**{min_score}/100**) altında veya kritik zafiyet tespit edildi!"
        )

        layer2_str = f"**{layer2:.1f}** / 100" if layer2 is not None else "*Atlandı (Mekanik)*"

        lines = [
            BOT_SIGNATURE,
            f"## 🛡️ WARDEN Automated Quality Gate — PR #{pr_number}",
            "",
            f"[![Quality Gate]({gate_badge})](https://github.com/tuncaycelikkanat/warden) [![WARDEN Score]({score_badge})](https://github.com/tuncaycelikkanat/warden)",
            "",
            verdict_banner,
            "",
            "### 📊 Kalite Boyutları ve Skor Dağılımı",
            "",
            "| Metrik / Boyut | Skor | Durum | Öncelik / Açıklama |",
            "|---|---|---|---|",
            f"| 🎯 **Genel Skor (Total Score)** | **{total_score:.1f} / 100** | `{grade}` | Ağırlıklı genel mimari ve kod sağlığı |",
            f"| ⚙️ **Layer 1: Mekanik & Statik** | **{layer1:.1f} / 100** | — | Linter, Tip, Test Kapsamı, Güvenlik, Karmaşıklık |",
            f"| 🧠 **Layer 2: LLM Mimari Rubric** | {layer2_str} | — | Mimari tutarlılık, clean code, modülerlik |",
            f"| 🔒 **Güvenlik & Bağımlılık (Security)** | **{sec:.1f} / 100** | {'✅' if sec >= 75 else '⚠️'} | CVE, SBOM, Shannon Entropi, Typosquatting |",
            f"| 🧪 **Test & Kod Sağlığı (Code Health)** | **{code_h:.1f} / 100** | {'✅' if code_h >= 75 else '⚠️'} | Coverage, Fake Test, AST Mutasyon Skoru |",
            f"| 🏛️ **Yapısal Mimari (Structural)** | **{struct:.1f} / 100** | {'✅' if struct >= 75 else '⚠️'} | Döngüsel bağımlılıklar, SQALE teknik borcu |",
            f"| ⚡ **Resilience & Güvenilirlik** | **{resil:.1f} / 100** | {'✅' if resil >= 75 else '⚠️'} | Hata yakalama, mock sızıntıları, dayanıklılık |",
            f"| 🧹 **Geliştirici Hijyeni (Dev Hygiene)** | **{hygiene:.1f} / 100** | {'✅' if hygiene >= 75 else '⚠️'} | Docstring oranı, commit düzeni, AI slop tespiti |",
            "",
        ]

        # Collapsible findings section
        if all_findings:
            lines.append(f"<details><summary><b>🔍 Tespit Edilen Bulgular ve İnceleme Notları ({len(all_findings)} adet — Tıklayıp Genişletin)</b></summary>")
            lines.append("")
            lines.append("| Seviye | Dosya | Satır | Kural / Açıklama |")
            lines.append("|---|---|---|---|")
            for f in all_findings[:25]:
                sev = str(f.get("severity", "MEDIUM")).upper()
                icon = "🚨" if sev == "CRITICAL" else ("⚠️" if sev == "HIGH" else "ℹ️")
                path_s = str(f.get("file", f.get("path", "-")))
                line_s = str(f.get("line", "-"))
                desc = str(f.get("message", f.get("description", "-"))).replace("\n", " ")
                lines.append(f"| {icon} `{sev}` | `{Path(path_s).name}` | `{line_s}` | {desc} |")
            if len(all_findings) > 25:
                lines.append(f"| ... | *ve {len(all_findings) - 25} diğer bulgu* | — | — |")
            lines.append("</details>")
            lines.append("")

        lines.extend([
            "---",
            "<sub>🤖 *Bu yorum [WARDEN Autonomous Governance Engine](https://github.com/tuncaycelikkanat/warden) tarafından PR denetimi sonucunda otomatik olarak oluşturulmuştur.*</sub>",
        ])

        return "\n".join(lines)

    def extract_inline_comments(
        self,
        findings: list[dict[str, Any]],
        changed_files: set[str] | None = None,
    ) -> list[InlineReviewComment]:
        """Filters high/critical severity findings and constructs inline review comments."""
        inline_comments: list[InlineReviewComment] = []

        for f in findings:
            file_path = str(f.get("file", f.get("path", "")))
            if not file_path:
                continue

            # If changed_files filter is given, verify file was touched in PR
            if changed_files is not None:
                norm_file = Path(file_path).as_posix()
                if not any(cf.endswith(norm_file) or norm_file.endswith(cf) for cf in changed_files):
                    continue

            try:
                line_no = int(f.get("line", 1))
            except (ValueError, TypeError):
                line_no = 1

            line_no = max(line_no, 1)

            sev = str(f.get("severity", "MEDIUM")).upper()
            msg = str(f.get("message", f.get("description", "Quality or security issue detected.")))
            rule = str(f.get("rule", f.get("analyzer", "WARDEN")))

            body = (
                f"🛡️ **WARDEN [{sev}] `{rule}`**\n\n"
                f"{msg}\n\n"
                f"💡 *Öneri: Güvenlik ve kalite kapısını geçebilmek için bu bulguyu düzeltiniz.*"
            )

            inline_comments.append(
                InlineReviewComment(
                    path=file_path,
                    line=line_no,
                    body=body,
                    severity=sev,
                )
            )

        # Sort so CRITICAL and HIGH come first
        inline_comments.sort(key=lambda c: 0 if c.severity == "CRITICAL" else (1 if c.severity == "HIGH" else 2))
        return inline_comments

    def review_pull_request(
        self,
        scorecard: dict[str, Any],
        owner: str,
        repo: str,
        pull_number: int,
        findings: list[dict[str, Any]] | None = None,
        min_score: int = 80,
        commit_sha: str | None = None,
        post_to_github: bool = False,
    ) -> PRReviewReport:
        """Executes full PR quality gate evaluation, builds report, and posts to GitHub if enabled."""
        card = scorecard.get("scorecard", scorecard)
        total_score = float(card.get("total_score", 0.0))
        grade = str(card.get("grade", "C"))
        all_findings = findings or []

        critical_count = sum(1 for f in all_findings if str(f.get("severity", "")).upper() == "CRITICAL")
        passed_gate = (total_score >= min_score) and (critical_count == 0)

        # Determine action event
        if passed_gate:
            action_event = "APPROVE"
        elif total_score < min_score or critical_count > 0:
            action_event = "REQUEST_CHANGES"
        else:
            action_event = "COMMENT"

        # Generate summary markdown
        summary_md = self.format_pr_scorecard_markdown(
            scorecard=card,
            findings=all_findings,
            min_score=min_score,
            repo_name=repo,
            pr_number=pull_number,
        )

        # Extract inline comments
        inline_comments = self.extract_inline_comments(all_findings)

        comment_id: int | None = None
        review_id: int | None = None
        is_updated: bool = False

        if post_to_github:
            # 1. Upsert summary comment
            comment_id, is_updated = self.api_client.upsert_summary_comment(
                owner=owner,
                repo=repo,
                pull_number=pull_number,
                body=summary_md,
            )

            # 2. If commit SHA provided, submit review with inline comments
            target_sha = commit_sha
            if not target_sha:
                pr_meta = self.api_client.get_pull_request(owner, repo, pull_number)
                target_sha = pr_meta.get("head", {}).get("sha")

            if target_sha:
                review_resp = self.api_client.post_pull_request_review(
                    owner=owner,
                    repo=repo,
                    pull_number=pull_number,
                    commit_sha=target_sha,
                    body=summary_md if not comment_id else f"WARDEN Quality Gate: **{action_event}**",
                    event=action_event,
                    comments=inline_comments if inline_comments else None,
                )
                review_id = review_resp.get("id")

        return PRReviewReport(
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            commit_sha=commit_sha,
            total_score=total_score,
            grade=grade,
            passed_quality_gate=passed_gate,
            min_score=min_score,
            action_event=action_event,
            summary_markdown=summary_md,
            inline_comments=inline_comments,
            comment_id=comment_id,
            review_id=review_id,
            is_updated=is_updated,
        )

    @staticmethod
    def generate_github_actions_workflow(min_score: int = 80) -> str:
        """Generates ready-to-use GitHub Actions workflow YAML for PR quality gates."""
        return f"""name: WARDEN Quality Gate & PR Review Bot

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write
  issues: write

jobs:
  warden-audit:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install Dependencies
        run: uv sync

      - name: Run WARDEN PR Review Quality Gate
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
        run: |
          uv run warden pr-review . \\
            --pr ${{{{ github.event.pull_request.number }}}} \\
            --owner ${{{{ github.repository_owner }}}} \\
            --repo ${{{{ github.event.repository.name }}}} \\
            --min-score {min_score} \\
            --post
"""
