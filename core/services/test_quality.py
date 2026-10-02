"""Test suite quality and assertion density analyzer using AST."""

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.fake_test_detector import FakeTestDetail, FakeTestDetector
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)


@dataclass
class FakeTestLocation:
    """Represents the location of an assertion-free test."""

    file_path: str
    function_name: str
    line_number: int


@dataclass
class TestQualityResult:
    """Represents test quality metrics including assertion counts and empty test ratios."""

    __test__ = False
    score: float
    total_tests: int
    fake_tests: int
    fake_test_ratio: float
    avg_assertion_density: float = 0.0
    fake_test_locations: list[FakeTestLocation] = field(default_factory=list)
    fake_test_details: list[FakeTestDetail] = field(default_factory=list)
    tautology_count: int = 0
    uninvoked_mock_count: int = 0
    measured: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "total_tests": self.total_tests,
            "fake_tests": self.fake_tests,
            "fake_test_ratio": self.fake_test_ratio,
            "avg_assertion_density": self.avg_assertion_density,
            "tautology_count": self.tautology_count,
            "uninvoked_mock_count": self.uninvoked_mock_count,
            "fake_test_locations": [
                {
                    "file_path": loc.file_path,
                    "function_name": loc.function_name,
                    "line_number": loc.line_number,
                }
                for loc in self.fake_test_locations
            ],
            "fake_test_details": [d.to_dict() for d in self.fake_test_details[:50]],
            "measured": self.measured,
        }


class TestQualityService:
    """Service to evaluate test quality, detect assertion-free tests, and analyze assertion density."""

    __test__ = False

    def __init__(self, fake_detector: FakeTestDetector | None = None) -> None:
        self.fake_detector = fake_detector or FakeTestDetector()

    def _is_trivial_assertion(self, assert_node: ast.Assert) -> bool:
        """Detects trivial assertion statements like assert True, assert 1, assert 'ok'."""
        test_expr = assert_node.test
        if isinstance(test_expr, ast.Constant):
            return bool(test_expr.value) is True
        if isinstance(test_expr, (ast.Tuple, ast.List)):
            if len(test_expr.elts) > 0 and all(isinstance(e, ast.Constant) for e in test_expr.elts):
                return True
        return False

    def _is_assert_call(self, call_node: ast.Call) -> bool:
        """Detects assertion calls like self.assertEqual, mock.assert_called, pytest.fail, etc."""
        func = call_node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            obj_name = getattr(func.value, "id", "")
            if attr.startswith("assert"):
                return True
            if attr in ("fail", "warns") and (obj_name in ("pytest", "self") or not obj_name):
                return True
        elif isinstance(func, ast.Name):
            if func.id.startswith("assert") or func.id in ("fail", "warns"):
                return True
        return False

    def _is_context_manager_assertion(self, context_expr: ast.expr) -> bool:
        """Detects context manager assertions like with pytest.raises(...), with pytest.warns(...)."""
        if isinstance(context_expr, ast.Call):
            call = context_expr
            if isinstance(call.func, ast.Attribute):
                attr_name = call.func.attr
                obj_name = getattr(call.func.value, "id", "")
                if attr_name in ("raises", "warns") and obj_name == "pytest":
                    return True
            elif isinstance(call.func, ast.Name):
                if call.func.id in ("raises", "warns"):
                    return True
        return False

    def _count_direct_assertions(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """Counts direct assertions in a function body."""
        count = 0
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assert):
                if not self._is_trivial_assertion(node):
                    count += 1
            elif isinstance(node, ast.Call):
                if self._is_assert_call(node):
                    count += 1
            elif isinstance(node, ast.With):
                for item in node.items:
                    if self._is_context_manager_assertion(item.context_expr):
                        count += 1
        return count

    def _build_asserting_function_index(self, tree: ast.AST) -> set[str]:
        """Indexes all functions in the module that contain at least one direct assertion."""
        asserting_index: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if self._count_direct_assertions(node) > 0:
                    asserting_index.add(node.name)
        return asserting_index

    def _extract_call_name(self, func_expr: ast.expr) -> str:
        """Extracts the simple identifier or attribute name from a call expression."""
        if isinstance(func_expr, ast.Name):
            return func_expr.id
        if isinstance(func_expr, ast.Attribute):
            return func_expr.attr
        return ""

    def _calls_asserting_helper(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        asserting_index: set[str],
    ) -> bool:
        """Checks if a function delegates validation to a local helper containing assertions."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                called_name = self._extract_call_name(node.func)
                if called_name and called_name != func_node.name and called_name in asserting_index:
                    return True
        return False

    async def analyze(self, repo_path: Path) -> TestQualityResult:
        """Analyzes test files using AST to evaluate assertion presence and test quality."""
        import asyncio

        def analyze_files() -> tuple[int, int, int, list[FakeTestLocation], list[FakeTestDetail], int, int]:
            files = discover_source_files(repo_path)
            test_files = [f for f in files if f.name.startswith("test_") or f.name.endswith("_test.py")]

            total_tests = 0
            fake_tests = 0
            total_direct_assertions = 0
            fake_locations: list[FakeTestLocation] = []
            fake_details: list[FakeTestDetail] = []
            tautology_count = 0
            uninvoked_mock_count = 0

            for tf in test_files:
                try:
                    content = tf.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    tree = ast.parse(content, filename=str(tf))
                    asserting_index = self._build_asserting_function_index(tree)

                    try:
                        rel_path = str(tf.relative_to(repo_path))
                    except ValueError:
                        rel_path = tf.name

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if node.name.startswith("test_"):
                                total_tests += 1
                                direct_assertions = self._count_direct_assertions(node)
                                total_direct_assertions += direct_assertions

                                # Advanced fake test analysis
                                findings = self.fake_detector.analyze_function(
                                    node, rel_path, lines, asserting_index
                                )
                                if findings:
                                    fake_details.extend(findings)
                                    for fd in findings:
                                        if fd.fake_type == "TAUTOLOGY":
                                            tautology_count += 1
                                        elif fd.fake_type == "UNINVOKED_MOCK_ASSERTION":
                                            uninvoked_mock_count += 1

                                # Check assertion-free status
                                if direct_assertions > 0:
                                    continue

                                # Check two-pass indirect helper
                                if self._calls_asserting_helper(node, asserting_index):
                                    continue

                                # Assertion-free fake test detected
                                fake_tests += 1
                                fake_locations.append(
                                    FakeTestLocation(
                                        file_path=rel_path,
                                        function_name=node.name,
                                        line_number=node.lineno,
                                    )
                                )
                except Exception as e:
                    logger.warning(f"Failed to parse test file {tf}: {e}")

            return (
                total_tests,
                fake_tests,
                total_direct_assertions,
                fake_locations,
                fake_details,
                tautology_count,
                uninvoked_mock_count,
            )

        (
            total_tests,
            fake_tests,
            total_direct_assertions,
            fake_locations,
            fake_details,
            tautology_count,
            uninvoked_mock_count,
        ) = await asyncio.to_thread(analyze_files)

        if total_tests == 0:
            return TestQualityResult(
                score=0.0,
                total_tests=0,
                fake_tests=0,
                fake_test_ratio=0.0,
                avg_assertion_density=0.0,
                fake_test_locations=[],
                fake_test_details=[],
                tautology_count=0,
                uninvoked_mock_count=0,
                measured=True,
            )

        ratio = fake_tests / total_tests
        raw_score = 100.0 - ((ratio / 0.05) * 10.0)
        clamped_score = max(0.0, min(100.0, raw_score))
        avg_density = round(total_direct_assertions / total_tests, 2)

        return TestQualityResult(
            score=round(clamped_score, 1),
            total_tests=total_tests,
            fake_tests=fake_tests,
            fake_test_ratio=round(ratio, 4),
            avg_assertion_density=avg_density,
            fake_test_locations=fake_locations,
            fake_test_details=fake_details,
            tautology_count=tautology_count,
            uninvoked_mock_count=uninvoked_mock_count,
            measured=True,
        )
