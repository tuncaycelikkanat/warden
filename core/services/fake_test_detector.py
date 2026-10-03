"""Advanced Fake & Placebo Test Detector for WARDEN.

Identifies meaningless, tautological, and deceptive unit test patterns:
- Tautological Assertions:
  - Self-equality: `assert x == x`, `assert obj is obj`
  - Non-negative length invariants: `assert len(data) >= 0`
  - Trivial boolean constants: `assert True`, `assert 1`, `assert "valid"`
- Uninvoked Mock Assertions (Python's silent mock bug):
  - Statements accessing mock assertion attributes without invocation:
    `mock.assert_called_once` (missing parentheses `()`), which evaluates silently as truthy
    without executing any verification!
- Assertion-free empty tests and placebo tests designed solely to game code coverage.
- Optional LLM-assisted verification for ambiguous assertion patterns.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MOCK_ASSERTION_ATTRS = {
    "assert_called",
    "assert_called_once",
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
    "assert_not_called",
}


@dataclass
class FakeTestDetail:
    """Detailed diagnosis of a detected fake, tautological, or placebo test."""

    file_path: str
    function_name: str
    line_number: int
    fake_type: str  # "NO_ASSERTION" | "TAUTOLOGY" | "UNINVOKED_MOCK_ASSERTION" | "TRIVIAL_CONSTANT" | "SEMANTIC_PLACEBO"
    snippet: str
    explanation: str
    severity: str  # "CRITICAL" | "HIGH" | "MEDIUM"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "function_name": self.function_name,
            "line_number": self.line_number,
            "fake_type": self.fake_type,
            "snippet": self.snippet,
            "explanation": self.explanation,
            "severity": self.severity,
        }


class FakeTestDetector:
    """Detects deceptive, tautological, and uninvoked mock tests across test suites."""

    def __init__(self, llm_provider: Any = None) -> None:
        self.llm_provider = llm_provider

    def _is_tautology_compare(self, comp: ast.Compare) -> tuple[bool, str]:
        """Checks if a compare node is an obvious tautology."""
        left_dump = ast.dump(comp.left)

        # 1. Self comparison (e.g. assert x == x or assert x is x)
        for op, right in zip(comp.ops, comp.comparators):
            right_dump = ast.dump(right)
            if isinstance(op, (ast.Eq, ast.Is)) and left_dump == right_dump:
                return True, "Değişkenin kendisiyle karşılaştırılması (assert x == x)"

        # 2. assert len(...) >= 0 (len is always >= 0)
        if isinstance(comp.left, ast.Call) and isinstance(comp.left.func, ast.Name) and comp.left.func.id == "len":
            for op, right in zip(comp.ops, comp.comparators):
                if isinstance(op, ast.GtE) and isinstance(right, ast.Constant) and right.value == 0:
                    return True, "len(...) >= 0 her zaman doğrudur (Tautology)"

        return False, ""

    def _is_trivial_constant(self, test_expr: ast.expr) -> bool:
        """Checks if an assertion test expression is a constant literal."""
        if isinstance(test_expr, ast.Constant):
            return bool(test_expr.value) is True
        if isinstance(test_expr, (ast.Tuple, ast.List)):
            if len(test_expr.elts) > 0 and all(isinstance(e, ast.Constant) for e in test_expr.elts):
                return True
        return False

    def _find_uninvoked_mock_assertions(self, func_node: ast.AST) -> list[tuple[int, str]]:
        """Detects mock.assert_called_once written as an attribute access without () call."""
        uninvoked: list[tuple[int, str]] = []
        for stmt in ast.walk(func_node):
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Attribute):
                attr_name = stmt.value.attr
                if attr_name in MOCK_ASSERTION_ATTRS:
                    lineno = getattr(stmt, "lineno", 1)
                    uninvoked.append((lineno, attr_name))
        return uninvoked

    def analyze_function(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        lines: list[str],
        asserting_helpers: set[str] | None = None,
    ) -> list[FakeTestDetail]:
        """Analyzes a single test function for fake, tautological, or placebo patterns."""
        helpers = asserting_helpers or set()
        findings: list[FakeTestDetail] = []
        func_name = func_node.name

        def _get_snippet(lineno: int) -> str:
            if 0 < lineno <= len(lines):
                return lines[lineno - 1].strip()[:120]
            return func_name

        # 1. Check for uninvoked mock assertions (silent bug)
        uninvoked_mocks = self._find_uninvoked_mock_assertions(func_node)
        for lineno, attr_name in uninvoked_mocks:
            findings.append(
                FakeTestDetail(
                    file_path=file_path,
                    function_name=func_name,
                    line_number=lineno,
                    fake_type="UNINVOKED_MOCK_ASSERTION",
                    snippet=_get_snippet(lineno),
                    explanation=f"'{attr_name}' parantez '()' çağrısı olmadan yazılmış. Test hiçbir şeyi doğrulamıyor!",
                    severity="CRITICAL",
                )
            )

        # 2. Walk assertions for tautologies and trivial constants
        direct_asserts_count = 0
        valid_asserts_count = 0

        for node in ast.walk(func_node):
            if isinstance(node, ast.Assert):
                direct_asserts_count += 1
                lineno = getattr(node, "lineno", func_node.lineno)

                if self._is_trivial_constant(node.test):
                    findings.append(
                        FakeTestDetail(
                            file_path=file_path,
                            function_name=func_name,
                            line_number=lineno,
                            fake_type="TRIVIAL_CONSTANT",
                            snippet=_get_snippet(lineno),
                            explanation="Sabit değişmez değer doğrulaması (assert True / assert 1). Anlamsız test.",
                            severity="HIGH",
                        )
                    )
                elif isinstance(node.test, ast.Compare):
                    is_taut, reason = self._is_tautology_compare(node.test)
                    if is_taut:
                        findings.append(
                            FakeTestDetail(
                                file_path=file_path,
                                function_name=func_name,
                                line_number=lineno,
                                fake_type="TAUTOLOGY",
                                snippet=_get_snippet(lineno),
                                explanation=reason,
                                severity="HIGH",
                            )
                        )
                    else:
                        valid_asserts_count += 1
                else:
                    valid_asserts_count += 1

            elif isinstance(node, ast.Call):
                # Check for unittest assert* or pytest.fail
                func_expr = node.func
                attr_name = getattr(func_expr, "attr", "")
                id_name = getattr(func_expr, "id", "")
                if attr_name.startswith("assert") or id_name.startswith("assert") or attr_name in ("fail", "warns"):
                    direct_asserts_count += 1
                    valid_asserts_count += 1

            elif isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        call_func = item.context_expr.func
                        c_attr = getattr(call_func, "attr", "")
                        c_id = getattr(call_func, "id", "")
                        if c_attr in ("raises", "warns") or c_id in ("raises", "warns"):
                            direct_asserts_count += 1
                            valid_asserts_count += 1

        # 3. Check for delegating helper function call
        called_helpers = False
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name in helpers and name != func_name:
                    called_helpers = True
                    break

        # 4. If zero direct assertions, no other findings, and no asserting helper: flag as NO_ASSERTION
        if direct_asserts_count == 0 and not called_helpers and not findings:
            findings.append(
                FakeTestDetail(
                    file_path=file_path,
                    function_name=func_name,
                    line_number=func_node.lineno,
                    fake_type="NO_ASSERTION",
                    snippet=_get_snippet(func_node.lineno),
                    explanation="Fonksiyon gövdesinde hiçbir assertion veya doğrulama bulunmuyor.",
                    severity="CRITICAL",
                )
            )

        return findings

    async def verify_with_llm(self, test_code: str) -> dict[str, Any]:
        """Optionally queries LLM to classify if a suspicious test function validates real business logic."""
        if not self.llm_provider:
            return {"is_fake": False, "reason": "No LLM provider configured"}

        prompt = (
            "Analyze the following unit test function. Determine if it is a genuine test verifying "
            "actual behavior, or a fake/placebo test written solely to artificially inflate code coverage.\n\n"
            f"```python\n{test_code}\n```\n\n"
            "Respond in JSON: {\"is_fake\": boolean, \"confidence\": float, \"reason\": string}"
        )
        try:
            res = await self.llm_provider.generate(prompt)
            if isinstance(res, dict) and "is_fake" in res:
                return res
        except Exception as err:
            logger.warning(f"Error in LLM fake test verification: {err}")

        return {"is_fake": False, "reason": "LLM verification failed"}
