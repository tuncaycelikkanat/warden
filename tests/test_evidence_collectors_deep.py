"""Comprehensive tests for evidence collectors edge cases."""
from pathlib import Path

from core.services.evidence.collectors import (
    collect_api_evidence,
    collect_concurrency_evidence,
    collect_devops_evidence,
    collect_frontend_evidence,
)


def test_concurrency_sync_snippets_and_plain_coroutines(tmp_path: Path):
    # File with only sync lock, no gather
    sync_file = tmp_path / "lock_handler.py"
    sync_file.write_text("import asyncio\nlock = asyncio.Lock()\nasync def run():\n    async with lock:\n        pass\n")

    files = [sync_file]
    matched, findings, snippets = collect_concurrency_evidence(tmp_path, files)
    assert "lock_handler.py" in matched
    assert any("Synchronization Safety" in f for f in findings)


def test_api_framework_detection(tmp_path: Path):
    # Flask endpoint
    flask_file = tmp_path / "flask_app.py"
    flask_file.write_text("from flask import Flask\napp = Flask(__name__)\n@app.route('/hello')\ndef hello(): return 'ok'\n")

    # Django endpoint
    django_file = tmp_path / "django_views.py"
    django_file.write_text("from rest_framework.views import APIView\nurlpatterns = []\n")

    # Express endpoint
    express_file = tmp_path / "server.js"
    express_file.write_text("const express = require('express');\nconst app = express();\napp.get('/api', (req, res) => res.send('ok'));\n")

    files = [flask_file, django_file, express_file]
    matched, findings, snippets = collect_api_evidence(tmp_path, files)
    assert any("Flask" in f for f in findings)
    assert any("Django" in f for f in findings)
    assert any("Express" in f for f in findings)


def test_devops_dockerfile_simple_base_and_ci_files(tmp_path: Path):
    # Simple Dockerfile without multi-stage or USER
    df = tmp_path / "Dockerfile"
    df.write_text("FROM python:3.12-slim\nRUN pip install -r requirements.txt\n")

    # Single-file CI pattern (Jenkinsfile)
    jf = tmp_path / "Jenkinsfile"
    jf.write_text("pipeline {\n    stages {\n        stage('Build') {}\n    }\n}\n")

    matched, findings, snippets = collect_devops_evidence(tmp_path, [df, jf])
    assert "Dockerfile" in matched
    assert "Jenkinsfile" in matched
    assert any("CI/CD: Found 1 workflow" in f for f in findings)


def test_frontend_empty_file(tmp_path: Path):
    empty_js = tmp_path / "empty.jsx"
    empty_js.touch()

    matched, findings, snippets = collect_frontend_evidence(tmp_path, [empty_js])
    assert len(snippets) == 0 and "empty.jsx" in matched
