"""Unit tests for TechDebtService and scorecard hotspot scoring."""

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from core.services.scorecard import ScorecardAggregatorService
from core.services.shared.scan_exclusions import get_generated_files_from_gitattributes
from core.services.tech_debt import TechDebtService


def _setup_git_repo(path: Path) -> None:
    """Initializes a minimal git repository for testing."""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Warden Tester"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "tester@warden.dev"], cwd=str(path), capture_output=True, check=True)


def _git_commit(path: Path, filename: str, content: str, date_iso: str | None = None) -> None:
    """Writes a file and creates a git commit with an optional custom author date."""
    file_path = path / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

    subprocess.run(["git", "add", filename], cwd=str(path), capture_output=True, check=True)

    env = os.environ.copy()
    if date_iso:
        env["GIT_AUTHOR_DATE"] = date_iso
        env["GIT_COMMITTER_DATE"] = date_iso

    subprocess.run(
        ["git", "commit", "-m", f"update {filename}"],
        cwd=str(path),
        capture_output=True,
        check=True,
        env=env,
    )


@pytest.mark.asyncio
async def test_tech_debt_shallow_clone_unmeasured(tmp_path: Path):
    """Shallow git clones return measured=False rather than silent 100."""
    _setup_git_repo(tmp_path)
    _git_commit(tmp_path, "sample.py", "print('hello')\n")
    # Simulate shallow clone marker
    (tmp_path / ".git" / "shallow").touch()

    service = TechDebtService()
    res = await service.analyze(tmp_path)
    assert res.measured is False
    assert res.reason == "git_history_unavailable_or_shallow"

    # Scorecard should omit tech_debt_churn and redistribute weight
    sc = ScorecardAggregatorService()
    scores = sc.calculate({"tech_debt": {"measured": False}}, [])
    assert "tech_debt_churn" not in scores.breakdown.get("member_scores", {})


@pytest.mark.asyncio
async def test_tech_debt_missing_git_unmeasured(tmp_path: Path):
    """Directories without .git repository return measured=False."""
    service = TechDebtService()
    res = await service.analyze(tmp_path)
    assert res.measured is False
    assert res.reason == "git_history_unavailable_or_shallow"


@pytest.mark.asyncio
async def test_tech_debt_real_hotspot(tmp_path: Path):
    """An old file with high churn and high cyclomatic complexity receives hotspot penalty."""
    _setup_git_repo(tmp_path)
    # Initial commit 60 days ago
    _git_commit(tmp_path, "hotspot.py", "def f(): pass\n", date_iso="2024-01-01T10:00:00Z")
    # Multiple edits
    for i in range(5):
        _git_commit(tmp_path, "hotspot.py", f"def f(): return {i}\n", date_iso=f"2024-01-0{i+2}T10:00:00Z")

    service = TechDebtService()
    sc = ScorecardAggregatorService()

    # Pass empty window so our old commits are captured in testing
    with patch.object(service, "WINDOW", "--all"):
        res = await service.analyze(tmp_path)

    assert res.measured is True
    assert len(res.churn_entries) >= 1

    entry = res.churn_entries[0]
    assert entry.file == "hotspot.py"
    assert entry.age_days >= 30

    comp_hotspot = {"outlier_blocks": [{"file": "hotspot.py", "complexity": 25}]}
    score = sc._score_tech_debt(res.__dict__, comp_hotspot)
    assert score < 100.0
    assert score <= 70.0


@pytest.mark.asyncio
async def test_tech_debt_new_feature_exempt_from_hotspot(tmp_path: Path):
    """A recently created active feature (< 30 days) is exempt from hotspot penalty despite high churn."""
    _setup_git_repo(tmp_path)
    now_iso = datetime.now(UTC).isoformat()
    _git_commit(tmp_path, "new_feature.py", "def new_work(): pass\n", date_iso=now_iso)
    for i in range(4):
        _git_commit(tmp_path, "new_feature.py", f"def new_work(): return {i}\n", date_iso=now_iso)

    service = TechDebtService()
    sc = ScorecardAggregatorService()

    res = await service.analyze(tmp_path)
    assert res.measured is True
    assert len(res.churn_entries) >= 1

    entry = res.churn_entries[0]
    assert entry.file == "new_feature.py"
    assert entry.age_days < 30  # Active new feature

    comp_new = {"outlier_blocks": [{"file": "new_feature.py", "complexity": 25}]}
    score = sc._score_tech_debt(res.__dict__, comp_new)
    # Must be 100 because it's exempt from hotspot penalty!
    assert score == 100.0


@pytest.mark.asyncio
async def test_tech_debt_word_boundary_and_comment_filtering(tmp_path: Path):
    """Words containing hack/attack or TODO in docstrings do not produce false positive markers."""
    (tmp_path / "hackathon_utils.py").write_text('''
def participate_hackathon():
    """We won the hackathon last year. Attack surface is low."""
    hack = "whitehat"
    return hack
''', encoding="utf-8")

    (tmp_path / "real_todo.py").write_text('''
# TODO: Refactor this database connection
def query():
    # FIXME: Handle timeout error properly
    pass
''', encoding="utf-8")

    service = TechDebtService()
    markers = service._scan_todo_markers(tmp_path)
    # Only real_todo.py should match
    files_with_markers = {m.file for m in markers}
    assert any("real_todo.py" in f for f in files_with_markers)
    assert not any("hackathon_utils.py" in f for f in files_with_markers)


@pytest.mark.asyncio
async def test_tech_debt_lockfile_churn_noise_excluded(tmp_path: Path):
    """Package manager lockfiles are excluded from churn calculation."""
    _setup_git_repo(tmp_path)
    _git_commit(tmp_path, "package-lock.json", '{"name": "test", "version": "1.0.0"}\n')
    _git_commit(tmp_path, "package-lock.json", '{"name": "test", "version": "1.0.1"}\n')
    _git_commit(tmp_path, "app.py", "print('app running')\n")

    service = TechDebtService()
    res = await service.analyze(tmp_path)
    assert res.measured is True
    files_in_churn = [e.file for e in res.churn_entries]
    assert "package-lock.json" not in files_in_churn
    assert "app.py" in files_in_churn


def test_gitattributes_gaming_resistance(tmp_path: Path):
    """Arbitrary Python files marked as linguist-generated in .gitattributes are not trusted blindly."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text("critical_spaghetti.py linguist-generated=true\nmodels_pb2.py linguist-generated=true\n")

    trusted = get_generated_files_from_gitattributes(tmp_path)
    # models_pb2.py matches GENERATED_FILE_PATTERNS so it's trusted
    assert "models_pb2.py" in trusted
    # critical_spaghetti.py does NOT match and is rejected as a gaming attempt
    assert "critical_spaghetti.py" not in trusted


@pytest.mark.asyncio
async def test_tech_debt_unmeasured_on_timeout(tmp_path: Path):
    """Timeout during git log results in measured=False."""
    service = TechDebtService()
    with patch.object(service, "_has_sufficient_history", return_value=True), \
         patch.object(service, "_run_git_churn", side_effect=subprocess.TimeoutExpired(cmd="git log", timeout=60)):
        res = await service.analyze(tmp_path)
        assert res.measured is False
        assert res.reason == "git_log_timeout"
