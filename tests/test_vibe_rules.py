"""Unit tests for Semgrep SAST rules, Taint tracking, and Vibe-Coding signatures."""

from pathlib import Path

import pytest

from core.services.scanner import SecurityScannerService


@pytest.fixture
def scanner() -> SecurityScannerService:
    return SecurityScannerService()


def test_sql_taint_positive(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies that unparameterized input flowing to execute() is caught."""
    bad_code = """
def handle_request(request, cursor):
    user_id = request.args.get("id")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
"""
    f = tmp_path / "app.py"
    f.write_text(bad_code)

    findings = scanner.scan_file(str(f))
    sql_findings = [f for f in findings if "sql" in f.get("check_id", "").lower()]
    assert len(sql_findings) >= 1
    assert sql_findings[0]["extra"]["severity"] == "ERROR"


def test_sql_taint_negative_parameterized(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies that parameterized queries are NOT flagged as SQL injection."""
    good_code = """
def handle_request(request, cursor):
    user_id = request.args.get("id")
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, (user_id,))
"""
    f = tmp_path / "app.py"
    f.write_text(good_code)

    findings = scanner.scan_file(str(f))
    sql_findings = [f for f in findings if "sql" in f.get("check_id", "").lower()]
    assert len(sql_findings) == 0


def test_sql_comment_no_false_positive(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies that SQL keywords in comments are NOT flagged."""
    comment_code = """
# TODO: SELECT * FROM users WHERE id = {user_input}
# Note: select all items where id = {x}
def safe_func():
    return 42
"""
    f = tmp_path / "app.py"
    f.write_text(comment_code)

    findings = scanner.scan_file(str(f))
    sql_findings = [f for f in findings if "sql" in f.get("check_id", "").lower()]
    assert len(sql_findings) == 0


def test_sql_multiline_taint(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies that multiline f-strings flowing to execute are caught."""
    multiline_code = '''
def query_users(request, db):
    name = request.json.get("name")
    sql = f"""
        SELECT *
        FROM users
        WHERE name = '{name}'
    """
    db.execute(sql)
'''
    f = tmp_path / "app.py"
    f.write_text(multiline_code)

    findings = scanner.scan_file(str(f))
    sql_findings = [f for f in findings if "sql" in f.get("check_id", "").lower()]
    assert len(sql_findings) >= 1


def test_vibe_ssl_verify_disabled(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies that disabling SSL verification triggers an ERROR."""
    bad_ssl = """
import requests
import httpx

def fetch_data(url):
    r1 = requests.get(url, verify=False)
    client = httpx.Client(verify=False)
    return r1.text
"""
    f = tmp_path / "service.py"
    f.write_text(bad_ssl)

    findings = scanner.scan_file(str(f))
    ssl_findings = [f for f in findings if "ssl" in f.get("check_id", "").lower()]
    assert len(ssl_findings) >= 1
    assert any(f["extra"]["severity"] == "ERROR" for f in ssl_findings)


def test_vibe_cors_wildcard_severity(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies wildcard CORS severity: ERROR with credentials, WARNING without."""
    bad_cors_credentials = """
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
)
"""
    f1 = tmp_path / "cors_crit.py"
    f1.write_text(bad_cors_credentials)

    findings1 = scanner.scan_file(str(f1))
    cors1 = [f for f in findings1 if "cors" in f.get("check_id", "").lower()]
    assert len(cors1) >= 1
    assert any(f["extra"]["severity"] == "ERROR" for f in cors1)

    bad_cors_only = """
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
)
"""
    f2 = tmp_path / "cors_warn.py"
    f2.write_text(bad_cors_only)

    findings2 = scanner.scan_file(str(f2))
    cors2 = [f for f in findings2 if "cors" in f.get("check_id", "").lower()]
    assert len(cors2) >= 1
    assert any(f["extra"]["severity"] == "WARNING" for f in cors2)


def test_vibe_debug_mode_exclusion(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies debug=True triggers ERROR in production code, but excluded in test files."""
    prod_code = """
from flask import Flask
app = Flask(__name__)
if __name__ == "__main__":
    app.run(debug=True)
"""
    f_prod = tmp_path / "server.py"
    f_prod.write_text(prod_code)

    findings_prod = scanner.scan_file(str(f_prod))
    debug_findings = [f for f in findings_prod if "debug" in f.get("check_id", "").lower()]
    assert len(debug_findings) >= 1
    assert debug_findings[0]["extra"]["severity"] == "ERROR"

    # In a test file, it should be excluded
    f_test = tmp_path / "test_server.py"
    f_test.write_text(prod_code)

    findings_test = scanner.scan_file(str(f_test))
    debug_in_test = [f for f in findings_test if "debug" in f.get("check_id", "").lower()]
    assert len(debug_in_test) == 0


def test_vibe_suppression_abuse(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies bare suppression is flagged, while justified suppression is allowed."""
    bare_code = """
def do_something():
    x = 1  # nosemgrep
    y = 2  # noqa
"""
    f_bare = tmp_path / "bare.py"
    f_bare.write_text(bare_code)

    findings_bare = scanner.scan_file(str(f_bare))
    supp_findings = [f for f in findings_bare if "suppression" in f.get("check_id", "").lower()]
    assert len(supp_findings) >= 1
    assert supp_findings[0]["extra"]["severity"] == "WARNING"

    justified_code = """
def do_something():
    x = 1  # nosemgrep: test fixture input, safe in isolated unit test
    y = 2  # noqa: reason explained here
"""
    f_justified = tmp_path / "justified.py"
    f_justified.write_text(justified_code)

    findings_justified = scanner.scan_file(str(f_justified))
    supp_justified = [f for f in findings_justified if "suppression" in f.get("check_id", "").lower()]
    assert len(supp_justified) == 0


def test_command_injection_and_deserialization(tmp_path: Path, scanner: SecurityScannerService):
    """Verifies shell=True and pickle.loads trigger ERROR."""
    insecure_code = """
import subprocess
import pickle

def run_cmd(user_cmd):
    subprocess.Popen(user_cmd, shell=True)

def load_payload(blob):
    return pickle.loads(blob)
"""
    f = tmp_path / "insecure.py"
    f.write_text(insecure_code)

    findings = scanner.scan_file(str(f))
    severities = [f["extra"]["severity"] for f in findings]
    assert severities.count("ERROR") >= 2
