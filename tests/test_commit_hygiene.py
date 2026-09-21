import asyncio
import subprocess
from pathlib import Path

import pytest

from core.services.commit_hygiene import CommitHygieneService
from core.services.scorecard import ScorecardAggregatorService


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_commit_hygiene_current_repo():
    service = CommitHygieneService()
    res = await service.analyze(Path("."))

    assert 0.0 <= res.score <= 100.0
    assert res.total_commits >= 0
    assert res.bad_commits >= 0
    assert isinstance(res.measured, bool)


@pytest.mark.asyncio
async def test_not_a_git_repo_unmeasured(tmp_path: Path):
    service = CommitHygieneService()
    res = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.reason == "not_a_git_repository"
    assert res.score == 100.0
    assert res.total_commits == 0


@pytest.mark.asyncio
async def test_insufficient_commit_sample_unmeasured(tmp_path: Path):
    def _setup_repo():
        _run_git(tmp_path, "init")
        _run_git(tmp_path, "config", "user.name", "Test User")
        _run_git(tmp_path, "config", "user.email", "test@example.com")
        for i in range(5):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            _run_git(tmp_path, "add", str(f))
            _run_git(tmp_path, "commit", "-m", f"feat: add feature {i}")

    await asyncio.to_thread(_setup_repo)

    service = CommitHygieneService()
    res = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.reason == "insufficient_commit_sample"
    assert res.total_commits == 5


def test_conventional_commits_accepted():
    service = CommitHygieneService()
    assert service._is_bad_commit("feat: implement oauth2 login") is False
    assert service._is_bad_commit("fix(core): handle null token gracefully") is False
    assert service._is_bad_commit("chore(deps): bump ruff from 0.4.0 to 0.5.0") is False
    assert service._is_bad_commit("docs: update README installation steps") is False
    assert service._is_bad_commit("refactor(api)!: migrate endpoint signatures") is False


def test_conventional_commit_trivial_desc_rejected():
    service = CommitHygieneService()
    assert service._is_bad_commit("fix: fix") is True
    assert service._is_bad_commit("test: test") is True
    assert service._is_bad_commit("chore: wip") is True
    assert service._is_bad_commit("feat: asdf") is True


def test_meaningful_single_word_accepted():
    service = CommitHygieneService()
    assert service._is_bad_commit("Refactor") is False
    assert service._is_bad_commit("Release") is False
    assert service._is_bad_commit("Hotfix") is False
    assert service._is_bad_commit("Cleanup") is False
    assert service._is_bad_commit("refactor") is False


def test_verbose_filler_gaming_rejected():
    service = CommitHygieneService()
    msg = "This commit contains various changes and updates to the codebase as discussed"
    assert service._is_bad_commit(msg) is True


def test_bad_exact_matches_turkish_and_english():
    service = CommitHygieneService()
    assert service._is_bad_commit("wip") is True
    assert service._is_bad_commit("asdf") is True
    assert service._is_bad_commit("güncelleme") is True
    assert service._is_bad_commit("düzeltme") is True
    assert service._is_bad_commit("deneme") is True


def test_repeated_character_spam():
    service = CommitHygieneService()
    assert service._is_bad_commit("aaaaa") is True
    assert service._is_bad_commit("asdfasdf") is True


def test_bot_commits_filtered_by_metadata():
    service = CommitHygieneService()
    assert service._is_bot_commit("dependabot[bot]", "dependabot@github.com") is True
    assert service._is_bot_commit("renovate[bot]", "renovate@whitesourcesoftware.com") is True
    assert service._is_bot_commit("github-actions[bot]", "actions@github.com") is True
    assert service._is_bot_commit("Alice Engineer", "alice@company.com") is False


def test_legitimate_human_commit_with_merge_word_not_filtered():
    service = CommitHygieneService()
    assert service._is_bot_commit("Bob Developer", "bob@example.com") is False
    assert service._is_bad_commit("merge conflict fix in authentication flow") is False


def test_scorecard_redistribution_when_commit_hygiene_unmeasured():
    aggregator = ScorecardAggregatorService()
    raw_data = {
        "documentation": 80.0,
        "cicd_presence": 100.0,
        "docker_readiness": 90.0,
        "commit_hygiene": {
            "score": 100.0,
            "measured": False,
        },
    }
    member_scores = aggregator._extract_member_scores(raw_data)
    assert "commit_hygiene" not in member_scores

    group_scores = aggregator._calc_group_scores(member_scores)
    # dev_hygiene_devops group has 4 members:
    # documentation (3/7), cicd_presence (2/7), docker_readiness (1/7), commit_hygiene (1/7)
    # Active weights: 3/7 + 2/7 + 1/7 = 6/7
    # Expected weighted score: (80*(3/7) + 100*(2/7) + 90*(1/7)) / (6/7) = (240 + 200 + 90)/6 = 530/6 = 88.33
    assert group_scores["dev_hygiene_devops"] == 88.33


@pytest.mark.asyncio
async def test_full_git_repo_simulation(tmp_path: Path):
    def _setup_repo():
        _run_git(tmp_path, "init")
        _run_git(tmp_path, "config", "user.name", "Developer One")
        _run_git(tmp_path, "config", "user.email", "dev@example.com")
        for i in range(12):
            f = tmp_path / f"code_{i}.py"
            f.write_text(f"x = {i}\n")
            _run_git(tmp_path, "add", str(f))
            _run_git(tmp_path, "commit", "-m", f"feat(service): add module {i} logic")

    await asyncio.to_thread(_setup_repo)

    service = CommitHygieneService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    assert res.total_commits == 12
    assert res.bad_commits == 0
    assert res.bad_ratio == 0.0
    assert res.score == 100.0

