"""Unit and integration tests for Section F1/F2 Chidamber & Kemerer (CK) OO Metrics Suite."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.main import app, _run_check_ck
from core.services.ck_metrics_analyzer import (
    CKMetricsAnalyzer,
    CKMetricsReport,
    ClassCKMetrics,
)


class TestCKMetricsMathematics:
    """Verifies calculation of individual CK metrics from Python AST snippets."""

    def test_wmc_calculation_with_branches(self, tmp_path):
        code = '''
class ComplexMath:
    def simple_add(self, a, b):
        return a + b  # complexity = 1

    def complex_branch(self, x, y):
        # 1 (base) + 2 (ifs) + 1 (while) + 1 (and) = 5
        if x > 0 and y > 0:
            while x < 10:
                x += 1
        elif x < 0:
            return -1
        return x
'''
        test_file = tmp_path / "math_sample.py"
        test_file.write_text(code, encoding="utf-8")

        analyzer = CKMetricsAnalyzer()
        report = analyzer.analyze(tmp_path)

        assert report.total_classes_analyzed == 1
        c = report.classes[0]
        assert c.class_name == "ComplexMath"
        assert c.methods_count == 2
        # simple_add (1) + complex_branch (1 + 1 (if) + 1 (and) + 1 (while) + 1 (elif) = 5) = 6
        assert c.wmc >= 5

    def test_dit_and_noc_hierarchy(self, tmp_path):
        code = '''
class BaseEntity:
    def id(self):
        return 1

class User(BaseEntity):
    def username(self):
        return "admin"

class AdminUser(User):
    def is_superuser(self):
        return True

class StandaloneClass:
    def ping(self):
        return "pong"
'''
        test_file = tmp_path / "hierarchy.py"
        test_file.write_text(code, encoding="utf-8")

        analyzer = CKMetricsAnalyzer()
        report = analyzer.analyze(tmp_path)

        metrics = {c.class_name: c for c in report.classes}

        # BaseEntity: DIT = 1, NOC = 1 (User)
        assert metrics["BaseEntity"].dit == 1
        assert metrics["BaseEntity"].noc == 1

        # User: DIT = 2, NOC = 1 (AdminUser)
        assert metrics["User"].dit == 2
        assert metrics["User"].noc == 1

        # AdminUser: DIT = 3, NOC = 0
        assert metrics["AdminUser"].dit == 3
        assert metrics["AdminUser"].noc == 0

        # StandaloneClass: DIT = 1, NOC = 0
        assert metrics["StandaloneClass"].dit == 1
        assert metrics["StandaloneClass"].noc == 0

    def test_lcom4_cohesive_vs_uncohesive(self, tmp_path):
        code = '''
class CohesiveService:
    def __init__(self):
        self.count = 0
        self.name = ""

    def set_name(self, n):
        self.name = n

    def get_info(self):
        # Accesses both name and count
        return f"{self.name}: {self.count}"

class UncohesiveService:
    def __init__(self):
        self.a = 1
        self.b = 2

    def task_one(self):
        # Operates purely on self.a
        return self.a * 10

    def task_two(self):
        # Operates purely on self.b (disjoint from task_one)
        return self.b + 100
'''
        test_file = tmp_path / "cohesion.py"
        test_file.write_text(code, encoding="utf-8")

        analyzer = CKMetricsAnalyzer()
        report = analyzer.analyze(tmp_path)

        metrics = {c.class_name: c for c in report.classes}

        # CohesiveService: all methods connected via attributes -> LCOM4 = 1
        assert metrics["CohesiveService"].lcom4 == 1

        # UncohesiveService: task_one and task_two share no attributes -> LCOM4 >= 2
        assert metrics["UncohesiveService"].lcom4 >= 2
        assert metrics["UncohesiveService"].lcom_star > 0.0

    def test_cbo_and_rfc_coupling(self, tmp_path):
        code = '''
class DatabaseAdapter:
    def query(self):
        pass

class CacheAdapter:
    def get(self):
        pass

class UserService:
    def __init__(self, db: DatabaseAdapter, cache: CacheAdapter):
        self.db = db
        self.cache = cache

    def find_user(self):
        self.cache.get()
        self.db.query()
'''
        test_file = tmp_path / "coupling.py"
        test_file.write_text(code, encoding="utf-8")

        analyzer = CKMetricsAnalyzer()
        report = analyzer.analyze(tmp_path)

        metrics = {c.class_name: c for c in report.classes}
        user_c = metrics["UserService"]

        # Coupled to DatabaseAdapter and CacheAdapter
        assert user_c.cbo == 2
        # RFC includes own methods + external called methods (query, get)
        assert user_c.rfc >= 4

    def test_architectural_smell_detection(self, tmp_path):
        code = '''
class GodLikeBlob:
    def __init__(self):
        self.f1 = 1
        self.f2 = 2

    def m1(self, x):
        if x > 1: return 1
        return self.f1

    def m2(self, x):
        if x > 2: return 2
        return self.f2

    def m3(self, x):
        for i in range(x):
            if i % 2 == 0: pass
        return x

class SimpleDTO:
    def __init__(self):
        self.val1 = 1
        self.val2 = 2
        self.val3 = 3
        self.val4 = 4
        self.val5 = 5
'''
        test_file = tmp_path / "smells.py"
        test_file.write_text(code, encoding="utf-8")

        analyzer = CKMetricsAnalyzer()
        report = analyzer.analyze(tmp_path)

        metrics = {c.class_name: c for c in report.classes}

        # SimpleDTO has 5 fields and 1 method (low wmc) -> Data Class
        assert "Data Class" in metrics["SimpleDTO"].detected_smells
        assert len(metrics["SimpleDTO"].recommendations) > 0


class TestCKMetricsAPI:
    """Verifies GET /api/v1/dashboard/metrics/ck endpoint."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_get_ck_metrics_summary(self):
        res = self.client.get("/api/v1/dashboard/metrics/ck?target=core/services&top=5")
        assert res.status_code == 200
        data = res.json()

        assert "total_classes_analyzed" in data
        assert "avg_wmc" in data
        assert "classes" in data
        assert len(data["classes"]) <= 5
        assert data["total_classes_analyzed"] > 10

    def test_get_ck_metrics_smells_only(self):
        res = self.client.get("/api/v1/dashboard/metrics/ck?target=core/services&smells_only=true")
        assert res.status_code == 200
        data = res.json()
        assert "classes" in data
        for c in data["classes"]:
            assert len(c["detected_smells"]) > 0 or c["wmc"] >= 30 or c["lcom4"] >= 3


class TestCKMetricsCLI:
    """Verifies warden check-ck CLI command."""

    def test_cli_check_ck_json_output(self, capsys):
        _run_check_ck("core/services", top=3, as_json=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert "avg_wmc" in data
        assert "classes" in data
        assert len(data["classes"]) == 3

    def test_cli_check_ck_output_file(self, tmp_path):
        out_file = tmp_path / "ck_report.json"
        _run_check_ck("core/services", top=5, output_file=str(out_file), as_json=False)

        assert out_file.is_file()
        content = json.loads(out_file.read_text(encoding="utf-8"))
        assert "smells_summary" in content

    def test_cli_check_ck_console_table(self, capsys):
        _run_check_ck("core/services", top=2, as_json=False)
        captured = capsys.readouterr()

        assert "CHIDAMBER & KEMERER" in captured.out
        assert "Sınıf Adı" in captured.out
        assert "WMC" in captured.out
