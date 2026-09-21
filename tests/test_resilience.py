"""Tests for ResilienceAnalyzerService and scorecard resilience scoring."""

import ast
from pathlib import Path

import pytest

from core.services.resilience import ResilienceAnalyzerService
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_resilience_analyzer_legacy_methods():
    """Verifies backward compatibility of AST detection methods and properties."""
    service = ResilienceAnalyzerService()
    code = (
        "try:\n"
        "    x = 1\n"
        "except:\n"
        "    pass\n"
        "import requests\n"
        "requests.get('https://example.com')\n"
    )
    tree = ast.parse(code)
    bare = service._find_bare_except(tree, Path("dummy.py"))
    assert len(bare) == 1
    assert bare[0].type == "bare_except"
    assert bare[0].rule == "bare_except"

    timeouts = service._find_missing_timeout(tree, Path("dummy.py"))
    assert len(timeouts) == 1
    assert timeouts[0].type == "missing_timeout"
    assert timeouts[0].rule == "missing_timeout"


@pytest.mark.asyncio
async def test_resilience_all_files_broken_unmeasured(tmp_path: Path):
    """When all Python files in the repo fail parsing, returns measured=False rather than silent 100."""
    broken_file = tmp_path / "broken.py"
    broken_file.write_text("def invalid syntax (():\n   pass", encoding="utf-8")

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is False
    assert res.reason == "all_files_failed_to_parse"
    assert len(res.skipped_files) == 1

    # Scorecard should omit resilience_ast so group weight is redistributed
    sc = ScorecardAggregatorService()
    scores = sc.calculate({"resilience": {"measured": False}}, [])
    assert "resilience_ast" not in scores.breakdown.get("member_scores", {})


@pytest.mark.asyncio
async def test_resilience_partial_syntax_error_transparency(tmp_path: Path):
    """When a single file is broken, it is recorded in skipped_files while valid files are scanned."""
    (tmp_path / "broken.py").write_text("class 123Invalid:\n", encoding="utf-8")
    (tmp_path / "valid.py").write_text("import requests\nrequests.get('https://api.com')\n", encoding="utf-8")

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    assert len(res.skipped_files) == 1
    assert res.skipped_files[0].file == "broken.py"
    assert any(d.rule == "missing_timeout" for d in res.defects)


@pytest.mark.asyncio
async def test_resilience_timeout_none_gaming(tmp_path: Path):
    """timeout=None is functionally equivalent to missing timeout and must be flagged as a defect."""
    file = tmp_path / "client.py"
    file.write_text("import requests\nrequests.get('https://api.com', timeout=None)\n", encoding="utf-8")

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    timeout_defects = [d for d in res.defects if d.rule == "missing_timeout"]
    assert len(timeout_defects) == 1
    assert "timeout=None" in timeout_defects[0].detail


@pytest.mark.asyncio
async def test_resilience_absurd_timeout_gaming(tmp_path: Path):
    """timeout=99999 is absurdly long (practically infinite) and must be flagged as a defect."""
    file = tmp_path / "client.py"
    file.write_text("import httpx\nhttpx.post('https://api.com', timeout=99999)\n", encoding="utf-8")

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    timeout_defects = [d for d in res.defects if d.rule == "missing_timeout"]
    assert len(timeout_defects) == 1
    assert "Absurd timeout" in timeout_defects[0].detail


@pytest.mark.asyncio
async def test_resilience_dynamic_timeout_exempt(tmp_path: Path):
    """Dynamic expressions such as config.TIMEOUT or function calls are exempt to avoid false positives."""
    file = tmp_path / "client.py"
    file.write_text(
        "import requests\n"
        "from config import API_TIMEOUT\n"
        "requests.get('https://api.com', timeout=API_TIMEOUT)\n",
        encoding="utf-8",
    )

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    timeout_defects = [d for d in res.defects if d.rule == "missing_timeout"]
    assert len(timeout_defects) == 0


@pytest.mark.asyncio
async def test_resilience_broad_exception_pass(tmp_path: Path):
    """Captures broad 'except Exception: pass' and 'except BaseException: ...' silent swallows."""
    file = tmp_path / "handlers.py"
    file.write_text(
        "def bad_handlers():\n"
        "    try:\n"
        "        do_something()\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        do_something_else()\n"
        "    except BaseException:\n"
        "        ...\n"
        "    try:\n"
        "        legit_handling()\n"
        "    except Exception as e:\n"
        "        print('Handled:', e)\n",
        encoding="utf-8",
    )

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    swallows = [d for d in res.defects if d.rule == "silent_exception_swallow"]
    assert len(swallows) == 2


@pytest.mark.asyncio
async def test_resilience_session_client_timeout(tmp_path: Path):
    """Tracks local Session and Client variables and enforces timeout on their method calls."""
    file = tmp_path / "api_worker.py"
    file.write_text(
        "import requests\n"
        "import httpx\n"
        "session = requests.Session()\n"
        "session.get('https://api.com/users')\n"  # defect: missing timeout
        "with httpx.Client() as client:\n"
        "    client.post('https://api.com/items')\n"  # defect: missing timeout
        "    client.get('https://api.com/health', timeout=5.0)\n",  # safe
        encoding="utf-8",
    )

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    session_defects = [d for d in res.defects if d.rule == "missing_timeout"]
    assert len(session_defects) == 2


@pytest.mark.asyncio
async def test_resilience_resource_leak_open(tmp_path: Path):
    """open() without context manager is flagged, but try...finally f.close() is exempt."""
    file = tmp_path / "files.py"
    file.write_text(
        "def leak():\n"
        "    f = open('data.txt')\n"
        "    return f.read()\n\n"
        "def safe_with():\n"
        "    with open('data.txt') as f:\n"
        "        return f.read()\n\n"
        "def safe_close():\n"
        "    f = open('data.txt')\n"
        "    try:\n"
        "        return f.read()\n"
        "    finally:\n"
        "        f.close()\n",
        encoding="utf-8",
    )

    service = ResilienceAnalyzerService()
    res = await service.analyze(tmp_path)

    assert res.measured is True
    leaks = [d for d in res.defects if d.rule == "resource_leak"]
    assert len(leaks) == 1
    assert leaks[0].line == 2


def test_resilience_density_normalization():
    """Verifies that large and small projects receive fair, normalized scores based on defect density."""
    sc = ScorecardAggregatorService()

    # Small project: 5 files, 4 defects -> density 0.8 -> 0 score
    small_data = {
        "measured": True,
        "file_count": 5,
        "defects": [
            {"rule": "missing_timeout"},
            {"rule": "missing_timeout"},
            {"rule": "bare_except"},
            {"rule": "resource_leak"},
        ],
    }
    small_score = sc._score_resilience(small_data)
    assert small_score == 0.0

    # Large enterprise project: 5000 files, 4 defects -> density 0.0008 -> 99.8 score
    large_data = {
        "measured": True,
        "file_count": 5000,
        "defects": [
            {"rule": "missing_timeout"},
            {"rule": "missing_timeout"},
            {"rule": "bare_except"},
            {"rule": "resource_leak"},
        ],
    }
    large_score = sc._score_resilience(large_data)
    assert large_score >= 99.0
