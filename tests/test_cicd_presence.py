"""Unit tests for CiCdPresenceService and tiered CI/CD scoring."""

from pathlib import Path

import pytest

from core.services.cicd_presence import CiCdPresenceService
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_cicd_no_files_found(tmp_path: Path):
    """Empty repository returns score=0.0 and has_file=False."""
    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)
    assert res.score == 0.0
    assert res.has_file is False
    assert res.has_valid_content is False
    assert res.has_automatic_trigger is False


@pytest.mark.asyncio
async def test_cicd_comment_only_gaming(tmp_path: Path):
    """Comment-only file with 'run' or 'job' keywords does NOT get 100 points."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "empty_ci.yml").write_text(
        "# TODO: add your run step here\n"
        "# stage pipeline definition coming soon\n",
        encoding="utf-8",
    )

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    assert res.has_file is True
    assert res.has_valid_content is False
    # File exists but has no valid job mapping -> partial 25.0
    assert res.score == 25.0


@pytest.mark.asyncio
async def test_cicd_manual_dispatch_only(tmp_path: Path):
    """Workflow with valid jobs but only workflow_dispatch gets 60.0 (dead pipeline)."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "manual.yml").write_text(
        "name: Manual Deploy\n"
        "on:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  deploy:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo deploy\n",
        encoding="utf-8",
    )

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    assert res.has_file is True
    assert res.has_valid_content is True
    assert res.has_automatic_trigger is False
    assert res.score == 60.0


@pytest.mark.asyncio
async def test_cicd_valid_automatic_trigger(tmp_path: Path):
    """Workflow with valid jobs and automatic triggers (push/pr) gets 100.0."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "test.yml").write_text(
        "name: CI\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "  pull_request:\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: pytest\n",
        encoding="utf-8",
    )

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    assert res.has_file is True
    assert res.has_valid_content is True
    assert res.has_automatic_trigger is True
    assert res.score == 100.0


@pytest.mark.asyncio
async def test_cicd_unquoted_on_keyword(tmp_path: Path):
    """Verifies PyYAML boolean True quirk for unquoted 'on: push' is resolved cleanly."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "push.yml").write_text(
        "name: Auto CI\n"
        "on: push\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: pytest\n",
        encoding="utf-8",
    )

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    assert res.has_automatic_trigger is True
    assert res.score == 100.0


@pytest.mark.asyncio
async def test_cicd_vendored_example_excluded(tmp_path: Path):
    """CI files located inside examples or vendor directories are excluded."""
    ex_wf = tmp_path / "examples" / "template" / ".github" / "workflows"
    ex_wf.mkdir(parents=True)
    (ex_wf / "ci.yml").write_text(
        "name: Example CI\n"
        "on: push\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    # Excluded -> treated as if no CI file exists
    assert res.has_file is False
    assert res.score == 0.0


@pytest.mark.asyncio
async def test_cicd_modern_systems_detected(tmp_path: Path):
    """Verifies modern CI configurations (Bitbucket, Azure, Drone, Jenkinsfile) are recognized."""
    service = CiCdPresenceService()

    # 1. Bitbucket Pipelines
    bb_path = tmp_path / "bb_repo"
    bb_path.mkdir()
    (bb_path / "bitbucket-pipelines.yml").write_text(
        "pipelines:\n"
        "  default:\n"
        "    - step:\n"
        "        script:\n"
        "          - pytest\n",
        encoding="utf-8",
    )
    res_bb = await service.analyze(bb_path)
    assert res_bb.score == 100.0

    # 2. Azure Pipelines
    az_path = tmp_path / "az_repo"
    az_path.mkdir()
    (az_path / "azure-pipelines.yml").write_text(
        "trigger:\n"
        "  - main\n"
        "jobs:\n"
        "  - job: Test\n"
        "    steps:\n"
        "      - script: pytest\n",
        encoding="utf-8",
    )
    res_az = await service.analyze(az_path)
    assert res_az.score == 100.0

    # 3. Jenkinsfile
    jk_path = tmp_path / "jk_repo"
    jk_path.mkdir()
    (jk_path / "Jenkinsfile").write_text(
        "pipeline {\n"
        "  agent any\n"
        "  stages {\n"
        "    stage('Test') {\n"
        "      steps { sh 'pytest' }\n"
        "    }\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    res_jk = await service.analyze(jk_path)
    assert res_jk.score == 100.0


@pytest.mark.asyncio
async def test_cicd_invalid_yaml_handled(tmp_path: Path):
    """Malformed YAML is caught gracefully without unhandled exception."""
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "broken.yml").write_text("jobs: [this is malformed yaml ::::\n", encoding="utf-8")

    service = CiCdPresenceService()
    res = await service.analyze(tmp_path)

    assert res.has_file is True
    assert res.has_valid_content is False
    assert res.score == 25.0
    assert len(res.files) == 1
    assert res.files[0].valid_yaml is False


def test_cicd_scorecard_integration():
    """Scorecard handles CiCdResult and dict scores properly."""
    sc = ScorecardAggregatorService()

    # Manual dispatch -> 60.0
    scores_manual = sc.calculate({"cicd_presence": 60.0}, [])
    assert scores_manual.breakdown["member_scores"]["cicd_presence"] == 60.0

    # Full CI -> 100.0
    scores_full = sc.calculate({"cicd_presence": 100.0}, [])
    assert scores_full.breakdown["member_scores"]["cicd_presence"] == 100.0


@pytest.mark.asyncio
async def test_cicd_gitlab_and_circleci(tmp_path: Path):
    service = CiCdPresenceService()

    # GitLab
    gl_path = tmp_path / "gl_repo"
    gl_path.mkdir()
    (gl_path / ".gitlab-ci.yml").write_text(
        "stages:\n  - test\ntest_job:\n  stage: test\n  script: echo 1\n",
        encoding="utf-8",
    )
    res_gl = await service.analyze(gl_path)
    assert res_gl.score == 100.0

    # CircleCI
    cc_path = tmp_path / "cc_repo"
    (cc_path / ".circleci").mkdir(parents=True)
    (cc_path / ".circleci" / "config.yml").write_text(
        "version: 2.1\njobs:\n  build:\n    docker:\n      - image: cimg/base:stable\n",
        encoding="utf-8",
    )
    res_cc = await service.analyze(cc_path)
    assert res_cc.score == 100.0

    # GitHub with on: [push, pull_request, true]
    gh_path = tmp_path / "gh_repo"
    (gh_path / ".github" / "workflows").mkdir(parents=True)
    (gh_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: CI\non: ['push', 'pull_request', true]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo 1\n",
        encoding="utf-8",
    )
    res_gh = await service.analyze(gh_path)
    assert res_gh.score == 100.0


def test_cicd_file_read_error(tmp_path: Path):
    from unittest.mock import patch

    service = CiCdPresenceService()
    f = tmp_path / "ci.yml"
    f.write_text("dummy")

    with patch("pathlib.Path.read_text", side_effect=OSError("Read error")):
        res = service._analyze_ci_file(f, tmp_path)
        assert res.valid_yaml is False
        assert "read_error" in res.reason

