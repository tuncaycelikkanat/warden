"""Tests for GitDiffAnalyzer and incremental audit file selection."""

import subprocess
from pathlib import Path

import pytest

from core.services.git_diff_analyzer import GitDiffAnalyzer


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Initializes a temporary git repository with commits."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@warden.dev"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Warden Test"], cwd=str(tmp_path), capture_output=True, check=True)

    # Initial commit
    file1 = tmp_path / "app.py"
    file1.write_text("print('version 1')\n")
    subprocess.run(["git", "add", "app.py"], cwd=str(tmp_path), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(tmp_path), capture_output=True, check=True)

    return tmp_path


class TestGitDiffAnalyzer:
    def test_no_changes(self, temp_git_repo: Path) -> None:
        analyzer = GitDiffAnalyzer()
        changed = analyzer.get_changed_files(temp_git_repo)
        assert changed == []

    def test_modified_file_detected(self, temp_git_repo: Path) -> None:
        analyzer = GitDiffAnalyzer()
        # Modify app.py
        file1 = temp_git_repo / "app.py"
        file1.write_text("print('version 2 - modified')\n")

        changed = analyzer.get_changed_files(temp_git_repo)
        assert len(changed) == 1
        assert changed[0] == file1.resolve()

    def test_untracked_file_detected(self, temp_git_repo: Path) -> None:
        analyzer = GitDiffAnalyzer()
        # Add new file without git add
        new_file = temp_git_repo / "service.py"
        new_file.write_text("def run(): pass\n")

        changed = analyzer.get_changed_files(temp_git_repo, include_untracked=True)
        assert new_file.resolve() in changed

    def test_since_commit_comparison(self, temp_git_repo: Path) -> None:
        analyzer = GitDiffAnalyzer()

        # Second commit
        file2 = temp_git_repo / "utils.py"
        file2.write_text("def helper(): pass\n")
        subprocess.run(["git", "add", "utils.py"], cwd=str(temp_git_repo), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Add utils.py"], cwd=str(temp_git_repo), capture_output=True, check=True)

        # Compare HEAD against HEAD~1
        changed = analyzer.get_changed_files(temp_git_repo, since_commit="HEAD~1")
        assert len(changed) == 1
        assert changed[0] == file2.resolve()
