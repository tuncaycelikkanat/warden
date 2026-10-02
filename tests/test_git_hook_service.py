"""Unit tests for GitHookService and CLI hook commands."""

import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.services.git_hook_service import GitHookService


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Initializes a temporary git repository with user config."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), capture_output=True, check=True)
    return tmp_path


class TestGitHookService:
    def test_install_all_hooks(self, git_repo: Path) -> None:
        service = GitHookService()
        ok = service.install(git_repo, hook_type="all", min_score=85)
        assert ok is True

        pre_commit = git_repo / ".git" / "hooks" / "pre-commit"
        pre_push = git_repo / ".git" / "hooks" / "pre-push"

        assert pre_commit.exists()
        assert pre_push.exists()

        # Check executable bit
        assert os.stat(pre_commit).st_mode & stat.S_IXUSR
        assert os.stat(pre_push).st_mode & stat.S_IXUSR

        # Check min_score in pre-push
        content = pre_push.read_text(encoding="utf-8")
        assert "MIN_SCORE=85" in content

    def test_install_invalid_repo_returns_false(self, tmp_path: Path) -> None:
        service = GitHookService()
        non_git = tmp_path / "not_a_repo"
        non_git.mkdir()
        ok = service.install(non_git, hook_type="pre-commit")
        assert ok is False

    def test_uninstall_hooks(self, git_repo: Path) -> None:
        service = GitHookService()
        service.install(git_repo, hook_type="all")

        pre_commit = git_repo / ".git" / "hooks" / "pre-commit"
        assert pre_commit.exists()

        ok = service.uninstall(git_repo, hook_type="pre-commit")
        assert ok is True
        assert not pre_commit.exists()

    def test_run_pre_commit_clean(self, git_repo: Path) -> None:
        service = GitHookService()
        # Stage a clean file
        code_file = git_repo / "clean.py"
        code_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        subprocess.run(["git", "add", "clean.py"], cwd=str(git_repo), check=True)

        passed, msg = service.run_pre_commit(git_repo)
        assert passed is True
        assert "temiz" in msg.lower() or "başarıyla" in msg.lower()

    def test_run_pre_commit_detects_secret(self, git_repo: Path) -> None:
        service = GitHookService()
        secret_file = git_repo / "secrets.py"
        secret_file.write_text('API_SECRET_TOKEN = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYq8194XzpQ"\n', encoding="utf-8")
        subprocess.run(["git", "add", "secrets.py"], cwd=str(git_repo), check=True)

        passed, msg = service.run_pre_commit(git_repo)
        assert passed is False
        assert "Secret Leak" in msg
        assert "API_SECRET_TOKEN" in msg

    def test_run_pre_commit_detects_syntax_error(self, git_repo: Path) -> None:
        service = GitHookService()
        broken_file = git_repo / "broken.py"
        broken_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "broken.py"], cwd=str(git_repo), check=True)

        passed, msg = service.run_pre_commit(git_repo)
        assert passed is False
        assert "SyntaxError" in msg

    def test_run_pre_commit_detects_env_file(self, git_repo: Path) -> None:
        service = GitHookService()
        env_file = git_repo / ".env"
        env_file.write_text("DATABASE_URL=postgres://user:pass@localhost/db\n", encoding="utf-8")
        subprocess.run(["git", "add", ".env"], cwd=str(git_repo), check=True)

        passed, msg = service.run_pre_commit(git_repo)
        assert passed is False
        assert "Sensitive File" in msg

    @pytest.mark.asyncio
    async def test_run_pre_push_pass_and_fail(self, git_repo: Path) -> None:
        service = GitHookService()

        # Mock orchestrator
        mock_orch = AsyncMock()
        mock_orch.run_full_audit.return_value = {
            "scorecard": {"total_score": 85, "grade": "B"}
        }

        with patch("core.services.orchestrator.AuditOrchestrator", return_value=mock_orch):
            # min_score = 80 -> should pass
            passed, msg = await service.run_pre_push(git_repo, min_score=80)
            assert passed is True
            assert "GEÇTİ" in msg

            # min_score = 90 -> should fail
            failed, fail_msg = await service.run_pre_push(git_repo, min_score=90)
            assert failed is False
            assert "BAŞARISIZ" in fail_msg


class TestCLIHookCommand:
    def test_cli_hook_install(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        from core.main import _run_hook_command

        class Args:
            target = str(git_repo)
            hook_action = "install"
            hook_type = "pre-commit"
            min_score = 80

        _run_hook_command(Args())
        captured = capsys.readouterr()
        assert "başarıyla kuruldu" in captured.out
        assert (git_repo / ".git" / "hooks" / "pre-commit").exists()

    def test_cli_hook_uninstall(self, git_repo: Path, capsys: pytest.CaptureFixture) -> None:
        from core.main import _run_hook_command

        class InstallArgs:
            target = str(git_repo)
            hook_action = "install"
            hook_type = "pre-commit"
            min_score = 80

        class UninstallArgs:
            target = str(git_repo)
            hook_action = "uninstall"
            hook_type = "pre-commit"

        _run_hook_command(InstallArgs())
        _run_hook_command(UninstallArgs())
        captured = capsys.readouterr()
        assert "kaldırıldı" in captured.out
        assert not (git_repo / ".git" / "hooks" / "pre-commit").exists()
