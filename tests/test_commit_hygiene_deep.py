"""Comprehensive tests for CommitHygieneService edge cases and git log handling."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.commit_hygiene import CommitHygieneService


def test_is_bad_commit_edge_cases():
    analyzer = CommitHygieneService()

    # Empty subject
    assert analyzer._is_bad_commit("") is True
    assert analyzer._is_bad_commit("   ") is True

    # Filler pattern
    assert analyzer._is_bad_commit("various changes and stuff here") is True

    # Character length < 5
    assert analyzer._is_bad_commit("ab") is True
    assert analyzer._is_bad_commit("refactor") is False  # In MEANINGFUL_SINGLE_WORDS!
    assert analyzer._is_bad_commit("ok") is True

    # Bad exact matches
    assert analyzer._is_bad_commit("update") is True
    assert analyzer._is_bad_commit("misc") is True

    # Conventional commit with repetitive or empty description
    assert analyzer._is_bad_commit("feat: a") is True
    assert analyzer._is_bad_commit("fix: aaaaa") is True

    # Valid commits
    assert analyzer._is_bad_commit("feat(auth): add OAuth2 refresh token rotation") is False
    assert analyzer._is_bad_commit("docs: update API setup instructions") is False


@pytest.mark.asyncio
async def test_commit_hygiene_analyzer_git_errors(tmp_path: Path):
    analyzer = CommitHygieneService()

    # Git not found
    with patch("shutil.which", return_value=None):
        res = await analyzer.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "git_not_found"

    # Git timeout
    with patch("shutil.which", return_value="/usr/bin/git"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=30)):
            res = await analyzer.analyze(tmp_path)
            assert res.measured is False
            assert res.reason == "git_log_timeout"

    # Generic exception
    with patch("shutil.which", return_value="/usr/bin/git"):
        with patch("subprocess.run", side_effect=RuntimeError("Subprocess failed")):
            res = await analyzer.analyze(tmp_path)
            assert res.measured is False
            assert res.reason == "git_execution_error"

    # Non-zero returncode (e.g. not a git repo)
    proc_mock = MagicMock(returncode=128, stdout="", stderr="fatal: not a git repository")
    with patch("shutil.which", return_value="/usr/bin/git"), patch("subprocess.run", return_value=proc_mock):
        res = await analyzer.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "not_a_git_repository"


@pytest.mark.asyncio
async def test_commit_hygiene_log_parsing_and_bot_skipping(tmp_path: Path):
    analyzer = CommitHygieneService()

    # Mock stdout with empty lines, malformed lines (<4 parts), and bot commits
    stdout_lines = [
        "",  # empty line
        "invalid_line_without_delimiter",
        "hash1|dependabot[bot]|bot@github.com|bump requests from 2.0 to 2.1",  # bot commit
        "hash2|Alice Dev|alice@example.com|feat: add comprehensive user dashboard",
        "hash3|Bob Dev|bob@example.com|fix: address connection pool exhaustion",
    ]
    proc_mock = MagicMock(returncode=0, stdout="\n".join(stdout_lines), stderr="")

    with patch("shutil.which", return_value="/usr/bin/git"), patch("subprocess.run", return_value=proc_mock):
        res = await analyzer.analyze(tmp_path)
        # Only 2 human commits, so insufficient commits (< 5)
        assert res.measured is False
        assert res.reason == "insufficient_commit_sample"
        assert res.total_commits == 2
