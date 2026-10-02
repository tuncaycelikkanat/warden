"""Unit and integration tests for Section D1 Mutation Testing Engine."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.services.mutation_tester import (
    ASTMutator,
    MutantCandidate,
    MutationReport,
    MutationTesterService,
)
from core.services.test_quality import FakeTestLocation, TestQualityResult


class TestASTMutatorOperators:
    """Tests that ASTMutator properly identifies and transforms each operator category."""

    def test_comparison_mutations(self):
        code = "def check(a, b):\n    return a == b or a < b or a in b or a is b\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        categories = [c.operator_category for c in mutator.candidates]
        assert "comparison" in categories
        cmp_mutants = [c for c in mutator.candidates if c.operator_category == "comparison"]
        assert len(cmp_mutants) >= 4

        # Test mutating == to != (first comparison)
        eq_mutant = [c for c in cmp_mutants if c.original_op == "=="][0]
        tree2 = ast.parse(code)
        mutator2 = ASTMutator(target_index=eq_mutant.index, file_path="test.py")
        mutated_tree = mutator2.visit(tree2)
        ast.fix_missing_locations(mutated_tree)
        unparsed = ast.unparse(mutated_tree)
        assert "a != b" in unparsed

    def test_arithmetic_mutations(self):
        code = "def calc(x, y):\n    return x + y - (x * y) / 2\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        arith_mutants = [c for c in mutator.candidates if c.operator_category == "arithmetic"]
        assert len(arith_mutants) >= 3

        # Test mutating + to -
        plus_mutant = [c for c in arith_mutants if c.original_op == "+"][0]
        tree2 = ast.parse(code)
        mutator2 = ASTMutator(target_index=plus_mutant.index, file_path="test.py")
        mutated_tree = mutator2.visit(tree2)
        ast.fix_missing_locations(mutated_tree)
        unparsed = ast.unparse(mutated_tree)
        assert "x - y" in unparsed

    def test_logical_mutations(self):
        code = "def check(x, y):\n    return x and y\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        logic_mutants = [c for c in mutator.candidates if c.operator_category == "logical"]
        assert len(logic_mutants) == 1
        assert logic_mutants[0].original_op == "and"
        assert logic_mutants[0].mutated_op == "or"

        tree2 = ast.parse(code)
        mutator2 = ASTMutator(target_index=logic_mutants[0].index, file_path="test.py")
        mutated_tree = mutator2.visit(tree2)
        ast.fix_missing_locations(mutated_tree)
        unparsed = ast.unparse(mutated_tree)
        assert "x or y" in unparsed

    def test_boundary_mutations(self):
        code = "def flags():\n    a = True\n    b = False\n    c = 0\n    d = 1\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        bound_mutants = [c for c in mutator.candidates if c.operator_category == "boundary"]
        assert len(bound_mutants) == 4

        # True -> False
        t_mutant = [c for c in bound_mutants if c.original_op == "True"][0]
        tree_t = ast.parse(code)
        res_t = ASTMutator(target_index=t_mutant.index).visit(tree_t)
        ast.fix_missing_locations(res_t)
        assert "a = False" in ast.unparse(res_t)

        # 0 -> 1
        z_mutant = [c for c in bound_mutants if c.original_op == "0"][0]
        tree_z = ast.parse(code)
        res_z = ASTMutator(target_index=z_mutant.index).visit(tree_z)
        ast.fix_missing_locations(res_z)
        assert "c = 1" in ast.unparse(res_z)

    def test_condition_inversion_mutations(self):
        code = "def check(x):\n    if x > 10:\n        return True\n    if not x:\n        return False\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        cond_mutants = [c for c in mutator.candidates if c.operator_category == "condition_inversion"]
        assert len(cond_mutants) == 2

        # Invert 'if x > 10:' -> 'if not x > 10:'
        tree1 = ast.parse(code)
        res1 = ASTMutator(target_index=cond_mutants[0].index).visit(tree1)
        ast.fix_missing_locations(res1)
        assert "if not x > 10:" in ast.unparse(res1)

        # Invert 'if not x:' -> 'if x:'
        tree2 = ast.parse(code)
        res2 = ASTMutator(target_index=cond_mutants[1].index).visit(tree2)
        ast.fix_missing_locations(res2)
        assert "if x:" in ast.unparse(res2)

    def test_type_annotations_and_imports_ignored(self):
        code = "import os\nfrom pathlib import Path\ndef func(a: int = 1) -> bool:\n    x: int = 0\n    return True\n"
        tree = ast.parse(code)
        mutator = ASTMutator(target_index=None, file_path="test.py")
        mutator.visit(tree)

        # The annotations 'int', 'bool' must NOT be mutated
        for c in mutator.candidates:
            assert c.original_op not in ("int", "bool")


class TestMutationDataModels:
    """Tests dataclasses and serialization for Mutation Testing."""

    def test_mutant_candidate_to_dict(self):
        cand = MutantCandidate(
            id="core/demo.py:10:cmp:0",
            index=0,
            file_path="core/demo.py",
            line_number=10,
            col_offset=4,
            operator_category="comparison",
            original_op="==",
            mutated_op="!=",
            original_snippet="a == b",
            mutated_snippet="a != b",
            status="KILLED",
            killer_test="tests/test_demo.py::test_eq",
            execution_time_seconds=0.123,
        )
        d = cand.to_dict()
        assert d["id"] == "core/demo.py:10:cmp:0"
        assert d["status"] == "KILLED"
        assert d["killer_test"] == "tests/test_demo.py::test_eq"
        assert d["execution_time_seconds"] == 0.123

    def test_mutation_report_to_dict(self):
        cand = MutantCandidate(
            id="core/demo.py:10:cmp:0",
            index=0,
            file_path="core/demo.py",
            line_number=10,
            col_offset=4,
            operator_category="comparison",
            original_op="==",
            mutated_op="!=",
            original_snippet="a == b",
            mutated_snippet="a != b",
            status="KILLED",
        )
        report = MutationReport(
            target_path="core/demo.py",
            total_mutants_discovered=1,
            mutants_tested=1,
            killed=1,
            survived=0,
            timed_out=0,
            errored=0,
            mutation_score=100.0,
            mutants=[cand],
            dry_run=False,
            execution_time_seconds=0.45,
        )
        d = report.to_dict()
        assert d["target_path"] == "core/demo.py"
        assert d["mutation_score"] == 100.0
        assert len(d["mutants"]) == 1
        assert d["mutants"][0]["status"] == "KILLED"


class TestMutationTesterService:
    """Tests the discovery and execution orchestration in MutationTesterService."""

    def test_discover_mutants_valid_file(self, tmp_path: Path):
        file = tmp_path / "math_sample.py"
        file.write_text("def add(a, b):\n    if a > 0:\n        return a + b\n    return 0\n", encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)
        mutants = svc.discover_mutants(file)

        assert len(mutants) >= 3
        categories = {m.operator_category for m in mutants}
        assert "condition_inversion" in categories
        assert "comparison" in categories
        assert "arithmetic" in categories

    def test_discover_mutants_invalid_file(self, tmp_path: Path):
        svc = MutationTesterService(repo_path=tmp_path)
        assert svc.discover_mutants(tmp_path / "nonexistent.py") == []

        bad_syntax = tmp_path / "bad.py"
        bad_syntax.write_text("def broken(: syntax error", encoding="utf-8")
        assert svc.discover_mutants(bad_syntax) == []

    def test_discover_repo_mutants_skips_orchestrator_and_tests(self, tmp_path: Path):
        core = tmp_path / "core" / "services"
        core.mkdir(parents=True)
        (core / "orchestrator.py").write_text("x = 1 + 2\n", encoding="utf-8")
        (core / "test_dummy.py").write_text("y = 1 + 2\n", encoding="utf-8")
        (core / "valid_service.py").write_text("def foo(x):\n    return x == 0\n", encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)
        repo_mutants = svc.discover_repo_mutants(max_mutants=50)

        file_names = {Path(m.file_path).name for m in repo_mutants}
        assert "orchestrator.py" not in file_names
        assert "test_dummy.py" not in file_names
        assert "valid_service.py" in file_names

    def test_resolve_test_file(self, tmp_path: Path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_debt_estimator.py").touch()

        svc = MutationTesterService(repo_path=tmp_path)
        source = tmp_path / "core" / "services" / "debt_estimator.py"
        resolved = svc.resolve_test_file(source)
        assert resolved is not None
        assert resolved.name == "test_debt_estimator.py"

        source_unknown = tmp_path / "core" / "services" / "nonexistent_svc.py"
        assert svc.resolve_test_file(source_unknown) is None

    def test_dry_run_does_not_modify_file_or_run_tests(self, tmp_path: Path):
        sample = tmp_path / "sample.py"
        original_code = "def inc(x):\n    return x + 1\n"
        sample.write_text(original_code, encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)
        report = svc.run_mutation_testing(target_path=sample, dry_run=True)

        assert report.dry_run is True
        assert report.total_mutants_discovered >= 2
        assert report.mutants_tested == 0
        assert sample.read_text(encoding="utf-8") == original_code

    def test_live_mutation_killed_mutant_and_restoration(self, tmp_path: Path):
        """Tests that a mutated operator is killed by pytest, and file is restored cleanly."""
        src_file = tmp_path / "calc.py"
        original_code = "def subtract(a, b):\n    return a - b\n"
        src_file.write_text(original_code, encoding="utf-8")

        # Create a test that expects a - b
        test_file = tmp_path / "test_calc.py"
        test_code = "from calc import subtract\ndef test_subtract():\n    assert subtract(10, 4) == 6\n"
        test_file.write_text(test_code, encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)

        # Mutates '-' to '+'
        report = svc.run_mutation_testing(
            target_path=src_file,
            test_path=test_file,
            max_mutants=1,
            timeout=10.0,
            dry_run=False,
        )

        # File MUST be restored identically
        assert src_file.read_text(encoding="utf-8") == original_code

        # The test asserts 6, but mutated + gives 14 -> Mutant was KILLED!
        assert report.mutants_tested == 1
        assert report.killed == 1
        assert report.survived == 0
        assert report.mutation_score == 100.0
        assert report.mutants[0].status == "KILLED"

    def test_live_mutation_survived_mutant(self, tmp_path: Path):
        """Tests that an unasserted mutation survives (reveals test blind spot)."""
        src_file = tmp_path / "widget.py"
        original_code = "def process(x):\n    flag = True\n    return x\n"
        src_file.write_text(original_code, encoding="utf-8")

        # Test tests return value x, completely ignoring 'flag'
        test_file = tmp_path / "test_widget.py"
        test_code = "from widget import process\ndef test_process():\n    assert process(42) == 42\n"
        test_file.write_text(test_code, encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)
        report = svc.run_mutation_testing(
            target_path=src_file,
            test_path=test_file,
            max_mutants=1,
            timeout=10.0,
            dry_run=False,
        )

        # File is restored
        assert src_file.read_text(encoding="utf-8") == original_code
        # Mutant flag = False survived because test did not assert flag!
        assert report.mutants_tested == 1
        assert report.survived == 1
        assert report.killed == 0
        assert report.mutation_score == 0.0
        assert report.mutants[0].status == "SURVIVED"

    def test_live_mutation_timeout_marked_as_timeout(self, tmp_path: Path):
        """Tests that timeout exception is handled and counted as TIMEOUT."""
        src_file = tmp_path / "loop.py"
        src_file.write_text("def check():\n    return 0\n", encoding="utf-8")

        svc = MutationTesterService(repo_path=tmp_path)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=1.0)):
            report = svc.run_mutation_testing(
                target_path=src_file,
                test_path=tmp_path / "dummy_test.py",
                max_mutants=1,
                timeout=1.0,
                dry_run=False,
            )

        assert report.timed_out == 1
        assert report.mutation_score == 100.0  # Timed out counts as effectively killed


class TestTestQualityIntegration:
    """Tests integration of mutation fields into TestQualityResult."""

    def test_test_quality_result_fields(self):
        tq = TestQualityResult(
            score=95.0,
            total_tests=50,
            fake_tests=0,
            fake_test_ratio=0.0,
            mutation_score=85.5,
            mutation_report={"killed": 17, "survived": 3},
        )
        d = tq.to_dict()
        assert d["mutation_score"] == 85.5
        assert d["mutation_report"] == {"killed": 17, "survived": 3}


class TestCLIMutateCommand:
    """Tests the CLI `warden mutate` command interface."""

    def test_cli_mutate_dry_run(self, capsys):
        from core.main import _run_mutate_command

        _run_mutate_command(
            target="core/services/debt_estimator.py",
            max_mutants=5,
            dry_run=True,
            as_json=False,
        )
        captured = capsys.readouterr()
        assert "WARDEN AST MUTASYON TESTİ — DRY-RUN" in captured.out
        assert "Keşfedilen Mutant" in captured.out
        assert "core/services/debt_estimator.py" in captured.out

    def test_cli_mutate_json_output(self, capsys, tmp_path: Path):
        from core.main import _run_mutate_command

        out_json = tmp_path / "mutant_out.json"
        _run_mutate_command(
            target="core/services/debt_estimator.py",
            max_mutants=5,
            dry_run=True,
            as_json=True,
            output_file=str(out_json),
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["dry_run"] is True
        assert data["total_mutants_discovered"] > 0
        assert out_json.is_file()
