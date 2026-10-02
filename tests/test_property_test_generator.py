"""Unit tests for PropertyTestGenerator (Hypothesis property-based test generator)."""

from __future__ import annotations

import ast
from pathlib import Path

from core.services.property_test_generator import (
    PropertyTestGenerator,
    PropertyTestReport,
    PropertyTestTemplate,
)


class TestPropertyTestGenerator:
    """Tests for PropertyTestGenerator."""

    def setup_method(self):
        self.generator = PropertyTestGenerator()

    def test_type_annotation_to_strategy_primitives(self):
        """Test primitive type annotation mapping."""
        tree = ast.parse("def f(a: int, b: float, c: str, d: bool): pass")
        func_def = tree.body[0]
        args = func_def.args.args

        strat_int = self.generator._type_annotation_to_strategy(args[0].annotation, args[0].arg)
        assert "st.integers" in strat_int

        strat_float = self.generator._type_annotation_to_strategy(args[1].annotation, args[1].arg)
        assert "st.floats" in strat_float

        strat_str = self.generator._type_annotation_to_strategy(args[2].annotation, args[2].arg)
        assert "st.text" in strat_str

        strat_bool = self.generator._type_annotation_to_strategy(args[3].annotation, args[3].arg)
        assert "st.booleans" in strat_bool

    def test_type_annotation_to_strategy_containers(self):
        """Test container type annotation mapping (list, dict)."""
        tree = ast.parse("def f(items: list[int], mapping: dict[str, int]): pass")
        func_def = tree.body[0]
        args = func_def.args.args

        strat_list = self.generator._type_annotation_to_strategy(args[0].annotation, args[0].arg)
        assert "st.lists" in strat_list
        assert "st.integers" in strat_list

        strat_dict = self.generator._type_annotation_to_strategy(args[1].annotation, args[1].arg)
        assert "st.dictionaries" in strat_dict

    def test_type_annotation_fallback_heuristics(self):
        """Test fallback heuristic mapping when type annotation is omitted."""
        strat_count = self.generator._type_annotation_to_strategy(None, "user_count")
        assert "st.integers" in strat_count

        strat_score = self.generator._type_annotation_to_strategy(None, "confidence_score")
        assert "st.floats" in strat_score

        strat_flag = self.generator._type_annotation_to_strategy(None, "is_valid")
        assert "st.booleans" in strat_flag

        strat_other = self.generator._type_annotation_to_strategy(None, "unknown_field")
        assert "st.text" in strat_other

    def test_analyze_idempotent_function(self):
        """Test property test generation for idempotent function naming."""
        tree = ast.parse("def normalize_text(text: str) -> str: return text.strip()")
        func_def = tree.body[0]

        template = self.generator.analyze_function(func_def, "sample_module", "sample.py")
        assert template is not None
        assert template.invariant_type == "idempotence"
        assert template.target_function == "normalize_text"
        assert "first = normalize_text(text)" in template.test_code
        assert "second = normalize_text(first)" in template.test_code
        assert "assert first == second" in template.test_code

    def test_analyze_bounded_function(self):
        """Test property test generation for bounded invariant naming."""
        tree = ast.parse("def calculate_score(weight: float) -> float: return weight * 10")
        func_def = tree.body[0]

        template = self.generator.analyze_function(func_def, "sample_module", "sample.py")
        assert template is not None
        assert template.invariant_type == "boundedness"
        assert "0.0 <= float(result) <= 100.0" in template.test_code

    def test_analyze_exception_safety_function(self):
        """Test property test generation for general function invariant."""
        tree = ast.parse("def transform_payload(data: str) -> dict: return {}")
        func_def = tree.body[0]

        template = self.generator.analyze_function(func_def, "sample_module", "sample.py")
        assert template is not None
        assert template.invariant_type == "exception_safety"
        assert "assert result is not None" in template.test_code

    def test_skip_private_and_test_functions(self):
        """Test that private and test functions are skipped."""
        tree = ast.parse(
            "def _internal_helper(x: int): pass\n"
            "def test_example(): pass\n"
            "def no_args(): pass\n"
            "def too_many_args(a: int, b: int, c: int, d: int, e: int): pass\n"
        )
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                assert self.generator.analyze_function(node, "mod", "f.py") is None

    def test_scan_repository(self, tmp_path: Path):
        """Test repository scan and full suite generation."""
        pkg_dir = tmp_path / "mypkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        code = (
            "def sanitize_string(val: str) -> str:\n"
            "    return val.strip()\n\n"
            "def compute_ratio(a: int, b: int) -> float:\n"
            "    return float(a) / (b or 1)\n"
        )
        (pkg_dir / "utils.py").write_text(code, encoding="utf-8")

        report = self.generator.scan_repository(tmp_path, max_templates=5)
        assert isinstance(report, PropertyTestReport)
        assert report.candidate_functions_count >= 2
        assert len(report.templates) >= 2
        assert "from hypothesis import given" in report.full_test_suite_code

        # Test to_dict methods
        d = report.to_dict()
        assert d["candidate_functions_count"] >= 2
        assert d["templates_count"] >= 2
        assert len(d["templates"]) >= 2
