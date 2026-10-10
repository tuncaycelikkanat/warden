"""Unit and integration tests for BadgeGeneratorService and LiveWatcherService."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from core.main import app
from core.services.badge_service import BadgeGeneratorService
from core.services.watcher import LiveWatcherService, _AuditChangeHandler

client = TestClient(app)


def test_badge_generator_service_svg_output():
    """Tests SVG rendering format and color assignments."""
    svg = BadgeGeneratorService.generate_svg(label="WARDEN", score=95, grade="A+")
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "WARDEN" in svg
    assert "95/100 · A+" in svg
    assert "#2ea44f" in svg  # A+ emerald green

    # Test F grade color
    svg_f = BadgeGeneratorService.generate_svg(label="AUDIT", score=45, grade="F")
    assert "AUDIT" in svg_f
    assert "45/100 · F" in svg_f
    assert "#d73a49" in svg_f

    # Test custom message
    svg_msg = BadgeGeneratorService.generate_svg(label="STATUS", message="Passing", color="#3fb950")
    assert "Passing" in svg_msg
    assert "#3fb950" in svg_msg


def test_badge_api_endpoints():
    """Tests GET /api/v1/badge and GET /badge.svg HTTP responses."""
    resp = client.get("/api/v1/badge?score=92&grade=A")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in resp.text
    assert "92/100 · A" in resp.text

    # Test root alias /badge.svg
    resp_alias = client.get("/badge.svg?score=65&grade=D")
    assert resp_alias.status_code == 200
    assert resp_alias.headers["content-type"].startswith("image/svg+xml")
    assert "65/100 · D" in resp_alias.text

    # Test dashboard router endpoint /api/v1/dashboard/badge
    resp_dash = client.get("/api/v1/dashboard/badge?label=MYPROJECT&score=85&grade=B")
    assert resp_dash.status_code == 200
    assert "MYPROJECT" in resp_dash.text
    assert "85/100 · B" in resp_dash.text


def test_watcher_event_handler_filtering():
    """Tests filesystem event filtering in _AuditChangeHandler."""
    watcher = LiveWatcherService(target_path=".", debounce_seconds=0.1)
    handler = _AuditChangeHandler(watcher)

    # Ignored directories
    assert "node_modules" in handler.IGNORE_DIRS
    assert ".venv" in handler.IGNORE_DIRS
    assert ".git" in handler.IGNORE_DIRS

    # Watched extensions
    assert ".py" in handler.WATCHED_EXTENSIONS
    assert ".ts" in handler.WATCHED_EXTENSIONS
    assert "Dockerfile" in handler.WATCHED_EXTENSIONS


def test_watcher_incremental_pass_mocked():
    """Tests that watcher execution calls orchestrator and updates score tracking."""
    watcher = LiveWatcherService(target_path=".", min_score=80, debounce_seconds=0.1)

    mock_audit_result = {
        "scorecard": {
            "total_score": 91.5,
            "grade": "A",
            "layer1_score": 90.0,
            "layer2_score": 93.0,
        },
        "vibe_coding": {
            "total_findings_count": 0,
        },
    }

    with patch.object(watcher.orchestrator, "run_full_audit", return_value=mock_audit_result):
        watcher.run_incremental_pass(trigger_file="test_mod.py")
        assert watcher.last_score == 91.5
        assert watcher.last_grade == "A"
        assert watcher.audit_count == 1
