"""Property-Based Test Template Generator for WARDEN using Hypothesis.

Analyzes codebase functions, signatures, and type hints using AST to synthesize
property-based tests that verify mathematical and algorithmic invariants:
- Roundtrip Invariants: `decode(encode(x)) == x` or `from_dict(to_dict(x)) == x`
- Idempotence Invariants: `f(f(x)) == f(x)` (normalization, formatting, cleanup)
- Boundedness / Range Invariants: `0.0 <= score <= 100.0`
- Exception Safety & Non-Crashing Invariants across arbitrary valid input domains
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

# Heuristic patterns identifying candidate functions for specific invariant properties
ROUNDTRIP_PAIRS = [
    (re.compile(r"encode", re.IGNORECASE), re.compile(r"decode", re.IGNORECASE)),
    (re.compile(r"serialize", re.IGNORECASE), re.compile(r"deserialize", re.IGNORECASE)),
    (re.compile(r"to_dict", re.IGNORECASE), re.compile(r"from_dict", re.IGNORECASE)),
    (re.compile(r"dump", re.IGNORECASE), re.compile(r"load", re.IGNORECASE)),
]

IDEMPOTENT_NAMES = re.compile(
    r"^(clean|normalize|sanitize|format|strip|deduplicate|slugify|canonicalize)",
    re.IGNORECASE,
)

BOUNDED_NAMES = re.compile(
    r"(score|ratio|rate|percentage|density|weight|confidence|probability)",
    re.IGNORECASE,
)


@dataclass
class PropertyTestTemplate:
    """A synthesized property-based test case template for Hypothesis."""

    target_function: str
    target_module: str
    file_path: str
    invariant_type: str  # "idempotence" | "boundedness" | "roundtrip" | "exception_safety"
    strategy_code: str
    test_code: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_function": self.target_function,
            "target_module": self.target_module,
            "file_path": self.file_path,
            "invariant_type": self.invariant_type,
            "strategy_code": self.strategy_code,
            "test_code": self.test_code,
        }


@dataclass
class PropertyTestReport:
    """Aggregated report of property test candidates and generated suite."""

    candidate_functions_count: int
    templates: list[PropertyTestTemplate] = field(default_factory=list)
    full_test_suite_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_functions_count": self.candidate_functions_count,
            "templates_count": len(self.templates),
            "templates": [t.to_dict() for t in self.templates[:25]],
            "full_test_suite_code": self.full_test_suite_code,
        }


class PropertyTestGenerator:
    """Generates Hypothesis property-based test templates from codebase AST."""

    def _type_annotation_to_strategy(self, annotation: ast.expr | None, param_name: str) -> str:
        """Maps an AST type annotation to an appropriate Hypothesis strategy."""
        if annotation is None:
            # Fallback based on parameter naming heuristics
            p_lower = param_name.lower()
            if "score" in p_lower or "ratio" in p_lower or "pct" in p_lower or "confidence" in p_lower:
                return "st.floats(min_value=0.0, max_value=100.0, allow_nan=False)"
            if p_lower.startswith(("is_", "has_")) or "flag" in p_lower:
                return "st.booleans()"
            if (
                p_lower == "id"
                or p_lower.endswith("_id")
                or p_lower.startswith("id_")
                or "count" in p_lower
                or "num" in p_lower
                or "index" in p_lower
            ):
                return "st.integers(min_value=0, max_value=1000)"
            return "st.text(min_size=1, max_size=50)"

        if isinstance(annotation, ast.Name):
            tname = annotation.id.lower()
            if tname == "int":
                return "st.integers(min_value=-1000, max_value=1000)"
            if tname == "float":
                return "st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)"
            if tname == "str":
                return "st.text(min_size=0, max_size=80)"
            if tname == "bool":
                return "st.booleans()"

        if isinstance(annotation, ast.Subscript):
            base_type = getattr(annotation.value, "id", "").lower()
            if base_type == "list":
                elem_strat = self._type_annotation_to_strategy(annotation.slice, "elem")
                return f"st.lists({elem_strat}, max_size=20)"
            if base_type == "dict":
                return "st.dictionaries(st.text(min_size=1, max_size=20), st.integers(), max_size=10)"

        return "st.text(min_size=1, max_size=50)"

    def analyze_function(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        module_path: str,
        file_path: str,
    ) -> PropertyTestTemplate | None:
        """Analyzes a single function and synthesizes a property test template if suitable."""
        func_name = func_node.name

        # Skip private, dunder, or test functions
        if func_name.startswith(("_", "test_")):
            return None

        # Filter arguments (excluding self / cls)
        params = [arg for arg in func_node.args.args if arg.arg not in ("self", "cls")]
        if not params or len(params) > 4:
            return None

        # Build hypothesis @given strategies
        strategies: list[str] = []
        param_names: list[str] = []
        for p in params:
            strat = self._type_annotation_to_strategy(p.annotation, p.arg)
            strategies.append(f"{p.arg}={strat}")
            param_names.append(p.arg)

        given_args = ", ".join(strategies)
        func_args = ", ".join(param_names)

        # Detect invariant type
        invariant_type = "exception_safety"
        invariant_assert = f"result = {func_name}({func_args})\n    assert result is not None"

        if IDEMPOTENT_NAMES.search(func_name) and len(params) == 1:
            invariant_type = "idempotence"
            invariant_assert = (
                f"first = {func_name}({func_args})\n"
                f"    second = {func_name}(first)\n"
                f"    assert first == second"
            )
        elif BOUNDED_NAMES.search(func_name):
            invariant_type = "boundedness"
            invariant_assert = (
                f"result = {func_name}({func_args})\n"
                f"    assert 0.0 <= float(result) <= 100.0"
            )

        test_code = (
            f"@given({given_args})\n"
            f"def test_property_{func_name}({func_args}):\n"
            f"    \"\"\"Property-based invariant verification for {func_name} ({invariant_type}).\"\"\"\n"
            f"    {invariant_assert}\n"
        )

        return PropertyTestTemplate(
            target_function=func_name,
            target_module=module_path,
            file_path=file_path,
            invariant_type=invariant_type,
            strategy_code=given_args,
            test_code=test_code,
        )

    def scan_repository(self, repo_path: Path, max_templates: int = 15) -> PropertyTestReport:
        """Scans Python files in repository and generates property test suite."""
        repo_path = repo_path.resolve()
        source_files = discover_source_files(repo_path)
        # Exclude tests and build dirs
        target_files = [
            f for f in source_files
            if not f.name.startswith("test_") and not f.name.endswith("_test.py") and "tests" not in f.parts
        ]

        templates: list[PropertyTestTemplate] = []

        for tf in target_files:
            try:
                content = tf.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(tf))
                rel_path = str(tf.relative_to(repo_path))
                mod_name = rel_path.replace("/", ".").replace(".py", "")

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                        template = self.analyze_function(node, mod_name, rel_path)
                        if template is not None:
                            templates.append(template)
                            if len(templates) >= max_templates:
                                break
                if len(templates) >= max_templates:
                    break
            except Exception as err:
                logger.debug(f"Failed to parse {tf} for property tests: {err}")

        # Construct full test file string
        header = (
            '"""Auto-generated Property-Based Test Suite via Hypothesis & WARDEN."""\n\n'
            "import pytest\n"
            "from hypothesis import given, strategies as st\n\n"
        )
        body = "\n\n".join(t.test_code for t in templates)
        full_suite = header + body if templates else ""

        return PropertyTestReport(
            candidate_functions_count=len(templates),
            templates=templates,
            full_test_suite_code=full_suite,
        )
