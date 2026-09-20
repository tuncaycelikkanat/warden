"""Test suite quality and assertion density analyzer using AST."""

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)


@dataclass
class TestQualityResult:
    """Represents test quality metrics including assertion counts and empty test ratios."""
    __test__ = False
    score: float
    total_tests: int
    fake_tests: int
    fake_test_ratio: float


class TestQualityService:
    """Service to evaluate test quality and identify assertion-free tests."""
    __test__ = False

    async def analyze(self, repo_path: Path) -> TestQualityResult:
        """Analyzes test files using AST to verify assertion presence."""
        import asyncio
        
        def count_assertions_in_func(func_node: ast.FunctionDef) -> int:
            assertions = 0
            for node in ast.walk(func_node):
                if isinstance(node, ast.Assert):
                    assertions += 1
                elif isinstance(node, ast.Call):
                    # Check for assertEqual, assertRaises, self.assert*, pytest.raises
                    if isinstance(node.func, ast.Attribute):
                        attr_name = node.func.attr
                        if attr_name.startswith('assert') or attr_name == 'raises' and getattr(node.func.value, 'id', '') == 'pytest':
                            assertions += 1
                    elif isinstance(node.func, ast.Name):
                        if node.func.id.startswith('assert'):
                            assertions += 1
                            
                elif isinstance(node, ast.With):
                    # Check for `with pytest.raises(...)`
                    for item in node.items:
                        if isinstance(item.context_expr, ast.Call):
                            call = item.context_expr
                            if isinstance(call.func, ast.Attribute) and call.func.attr == 'raises' and getattr(call.func.value, 'id', '') == 'pytest' or isinstance(call.func, ast.Name) and call.func.id == 'raises':
                                assertions += 1
                                
            return assertions
            
        def analyze_files():
            files = discover_source_files(repo_path)
            test_files = [f for f in files if f.name.startswith("test_") or f.name.endswith("_test.py")]
            
            total_tests = 0
            fake_tests = 0
            
            for tf in test_files:
                try:
                    content = tf.read_text(encoding="utf-8")
                    tree = ast.parse(content, filename=str(tf))
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.FunctionDef):
                            if node.name.startswith("test_"):
                                total_tests += 1
                                if count_assertions_in_func(node) == 0:
                                    fake_tests += 1
                except Exception as e:
                    logger.warning(f"Failed to parse test file {tf}: {e}")
                    
            return total_tests, fake_tests

        total_tests, fake_tests = await asyncio.to_thread(analyze_files)
        
        if total_tests == 0:
            return TestQualityResult(score=0.0, total_tests=0, fake_tests=0, fake_test_ratio=0.0)
            
        ratio = fake_tests / total_tests
        
        score = 100.0 - ((ratio / 0.05) * 10.0)
        
        return TestQualityResult(
            score=max(0.0, min(100.0, score)),
            total_tests=total_tests,
            fake_tests=fake_tests,
            fake_test_ratio=ratio
        )
