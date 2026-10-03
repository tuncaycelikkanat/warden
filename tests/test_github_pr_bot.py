"""Unit and integration tests for Section G4 GitHub PR Review Bot & Automated Commenter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from core.main import _run_pr_review_command, app
from core.services.github_pr_bot import (
    BOT_SIGNATURE,
    GitHubAPIClient,
    GitHubPRReviewBot,
    InlineReviewComment,
)


class TestGitHubAPIClient:
    """Verifies GitHub REST API client behavior, comment discovery, and upsert logic."""

    @patch("httpx.Client.get")
    def test_get_pull_request_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"number": 42, "head": {"sha": "abc1234"}}
        mock_get.return_value = mock_resp

        client = GitHubAPIClient(token="fake_token")
        pr_data = client.get_pull_request("testowner", "testrepo", 42)

        assert pr_data.get("number") == 42
        assert pr_data.get("head", {}).get("sha") == "abc1234"

    @patch("httpx.Client.get")
    def test_find_existing_warden_comment(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 101, "body": "Normal user comment"},
            {"id": 102, "body": f"Some preamble\n{BOT_SIGNATURE}\n## Scorecard"},
        ]
        mock_get.return_value = mock_resp

        client = GitHubAPIClient(token="fake_token")
        comment_id = client.find_existing_warden_comment("testowner", "testrepo", 42)
        assert comment_id == 102

    @patch.object(GitHubAPIClient, "find_existing_warden_comment", return_value=102)
    @patch("httpx.Client.patch")
    def test_upsert_existing_comment_triggers_patch(self, mock_patch, mock_find):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_patch.return_value = mock_resp

        client = GitHubAPIClient(token="fake_token")
        c_id, was_updated = client.upsert_summary_comment("owner", "repo", 42, "Updated body")

        assert c_id == 102
        assert was_updated is True
        mock_patch.assert_called_once()

    @patch.object(GitHubAPIClient, "find_existing_warden_comment", return_value=None)
    @patch("httpx.Client.post")
    def test_upsert_new_comment_triggers_post(self, mock_post, mock_find):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 205}
        mock_post.return_value = mock_resp

        client = GitHubAPIClient(token="fake_token")
        c_id, was_updated = client.upsert_summary_comment("owner", "repo", 42, "New body")

        assert c_id == 205
        assert was_updated is False
        mock_post.assert_called_once()

    @patch("httpx.Client.post")
    def test_post_pull_request_review(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 777, "state": "APPROVED"}
        mock_post.return_value = mock_resp

        client = GitHubAPIClient(token="fake_token")
        comments = [
            InlineReviewComment(
                path="core/utils.py",
                line=15,
                body="Critical vulnerability",
                severity="CRITICAL",
            )
        ]
        res = client.post_pull_request_review(
            owner="owner",
            repo="repo",
            pull_number=42,
            commit_sha="abc1234",
            body="Review summary",
            event="APPROVE",
            comments=comments,
        )

        assert res.get("id") == 777
        assert res.get("state") == "APPROVED"


class TestGitHubPRReviewBot:
    """Verifies markdown formatting, inline comment extraction, and quality gate decisions."""

    def test_format_pr_scorecard_markdown_passed(self):
        bot = GitHubPRReviewBot()
        scorecard = {
            "total_score": 88.0,
            "grade": "B",
            "layer1_score": 85.0,
            "layer2_score": 90.0,
        }
        md = bot.format_pr_scorecard_markdown(scorecard, min_score=80, pr_number=12)

        assert BOT_SIGNATURE in md
        assert "PR #12" in md
        assert "Quality Gate Passed" in md
        assert "88.0 / 100" in md
        assert "Quality_Gate-PASSED-brightgreen" in md

    def test_format_pr_scorecard_markdown_failed(self):
        bot = GitHubPRReviewBot()
        scorecard = {
            "total_score": 65.0,
            "grade": "D",
            "layer1_score": 60.0,
            "layer2_score": 70.0,
        }
        findings = [
            {
                "file": "core/auth.py",
                "line": 42,
                "severity": "CRITICAL",
                "message": "Hardcoded secret key detected",
            }
        ]
        md = bot.format_pr_scorecard_markdown(scorecard, findings=findings, min_score=80)

        assert "Quality Gate Failed" in md
        assert "Quality_Gate-FAILED-red" in md
        assert "Tespit Edilen Bulgular" in md
        assert "Hardcoded secret key detected" in md

    def test_extract_inline_comments(self):
        bot = GitHubPRReviewBot()
        findings = [
            {
                "path": "core/sec.py",
                "line": 25,
                "severity": "CRITICAL",
                "message": "SQL Injection vulnerability",
                "rule": "security_cve",
            },
            {
                "path": "core/ignored.py",
                "line": 10,
                "severity": "INFO",
                "message": "Minor style issue",
            },
        ]
        # Restrict to changed files
        inline = bot.extract_inline_comments(findings, changed_files={"core/sec.py"})

        assert len(inline) == 1
        assert inline[0].path == "core/sec.py"
        assert inline[0].line == 25
        assert inline[0].severity == "CRITICAL"
        assert "SQL Injection vulnerability" in inline[0].body

    def test_review_pull_request_logic(self):
        bot = GitHubPRReviewBot()
        # Passing scorecard
        pass_card = {"total_score": 85.0, "grade": "B"}
        rep_pass = bot.review_pull_request(pass_card, "owner", "repo", 5, min_score=80)
        assert rep_pass.passed_quality_gate is True
        assert rep_pass.action_event == "APPROVE"

        # Failing scorecard (low score)
        fail_card = {"total_score": 70.0, "grade": "C"}
        rep_fail = bot.review_pull_request(fail_card, "owner", "repo", 5, min_score=80)
        assert rep_fail.passed_quality_gate is False
        assert rep_fail.action_event == "REQUEST_CHANGES"

    def test_generate_github_actions_workflow(self):
        bot = GitHubPRReviewBot()
        wf = bot.generate_github_actions_workflow(min_score=85)
        assert "name: WARDEN Quality Gate & PR Review Bot" in wf
        assert "pull_request:" in wf
        assert "--min-score 85" in wf
        assert "GITHUB_TOKEN" in wf


class TestGitHubApiEndpoints:
    """Verifies dashboard REST API endpoints for PR review and GitHub Webhook."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_post_pr_review_endpoint(self):
        payload = {
            "owner": "tuncaycelikkanat",
            "repo": "warden",
            "pull_number": 99,
            "min_score": 80,
            "post_to_github": False,
            "scorecard": {
                "total_score": 92.0,
                "grade": "A",
                "layer1_score": 90.0,
                "layer2_score": 94.0,
            },
        }
        res = self.client.post("/api/v1/dashboard/pr-review", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["owner"] == "tuncaycelikkanat"
        assert data["pull_number"] == 99
        assert data["passed_quality_gate"] is True
        assert data["action_event"] == "APPROVE"
        assert BOT_SIGNATURE in data["summary_markdown"]

    def test_post_github_webhook_pull_request_opened(self):
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 105,
                "head": {"sha": "def5678"},
            },
            "repository": {
                "name": "warden",
                "owner": {"login": "tuncaycelikkanat"},
            },
        }
        res = self.client.post("/api/v1/dashboard/github/webhook", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "processed"
        assert data["pr_number"] == 105
        assert data["action"] == "opened"

    def test_post_github_webhook_ignored_action(self):
        payload = {
            "action": "closed",
            "pull_request": {"number": 105},
        }
        res = self.client.post("/api/v1/dashboard/github/webhook", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ignored"


class TestGitHubCLICommand:
    """Verifies warden pr-review CLI command."""

    def test_cli_pr_review_json(self, capsys):
        _run_pr_review_command(".", pr_number=15, owner="myorg", repo="myrepo", as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["pull_number"] == 15
        assert data["owner"] == "myorg"
        assert data["repo"] == "myrepo"
        assert "summary_markdown" in data

    def test_cli_pr_review_output_file(self, tmp_path):
        out_file = tmp_path / "pr_review.md"
        _run_pr_review_command(".", output_file=str(out_file), as_json=False)
        assert out_file.is_file()
        assert BOT_SIGNATURE in out_file.read_text(encoding="utf-8")

    def test_cli_init_workflow(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        _run_pr_review_command(".", init_workflow=True, min_score=85)
        captured = capsys.readouterr()
        assert "GitHub Actions PR Review workflow dosyası oluşturuldu" in captured.out

        wf_path = tmp_path / ".github/workflows/warden-pr-review.yml"
        assert wf_path.is_file()
        assert "--min-score 85" in wf_path.read_text(encoding="utf-8")
