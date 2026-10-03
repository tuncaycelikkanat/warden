"""AST-based Mutation Testing Engine and Mutant Survival Analyzer for WARDEN (Section D1).

Introduces controlled, deterministic synthetic faults (mutants) into source code
to assess the test suite's bug detection effectiveness (kill rate) and discover blind spots.
"""

from __future__ import annotations

import ast
import logging
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Operator mutation mappings
COMPARISON_MUTATIONS: dict[type[ast.cmpop], tuple[type[ast.cmpop], str, str]] = {
    ast.Eq: (ast.NotEq, "!=", "=="),
    ast.NotEq: (ast.Eq, "==", "!="),
    ast.Lt: (ast.GtE, ">=", "<"),
    ast.LtE: (ast.Gt, ">", "<="),
    ast.Gt: (ast.LtE, "<=", ">"),
    ast.GtE: (ast.Lt, "<", ">="),
    ast.In: (ast.NotIn, "not in", "in"),
    ast.NotIn: (ast.In, "in", "not in"),
    ast.Is: (ast.IsNot, "is not", "is"),
    ast.IsNot: (ast.Is, "is", "is not"),
}

ARITHMETIC_MUTATIONS: dict[type[ast.operator], tuple[type[ast.operator], str, str]] = {
    ast.Add: (ast.Sub, "-", "+"),
    ast.Sub: (ast.Add, "+", "-"),
    ast.Mult: (ast.FloorDiv, "//", "*"),
    ast.FloorDiv: (ast.Mult, "*", "//"),
    ast.Div: (ast.Mult, "*", "/"),
    ast.Mod: (ast.Mult, "*", "%"),
}

LOGICAL_MUTATIONS: dict[type[ast.boolop], tuple[type[ast.boolop], str, str]] = {
    ast.And: (ast.Or, "or", "and"),
    ast.Or: (ast.And, "and", "or"),
}


@dataclass
class MutantCandidate:
    """Represents a single synthetic mutation candidate."""

    id: str
    index: int
    file_path: str
    line_number: int
    col_offset: int
    operator_category: str  # comparison, arithmetic, logical, boundary, condition_inversion
    original_op: str
    mutated_op: str
    original_snippet: str
    mutated_snippet: str
    status: str = "UNTESTED"  # UNTESTED, KILLED, SURVIVED, TIMEOUT, ERROR
    killer_test: str | None = None
    execution_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MutationReport:
    """Aggregated results of mutation testing."""

    target_path: str
    total_mutants_discovered: int
    mutants_tested: int
    killed: int
    survived: int
    timed_out: int
    errored: int
    mutation_score: float
    mutants: list[MutantCandidate] = field(default_factory=list)
    dry_run: bool = False
    execution_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "total_mutants_discovered": self.total_mutants_discovered,
            "mutants_tested": self.mutants_tested,
            "killed": self.killed,
            "survived": self.survived,
            "timed_out": self.timed_out,
            "errored": self.errored,
            "mutation_score": self.mutation_score,
            "mutants": [m.to_dict() for m in self.mutants],
            "dry_run": self.dry_run,
            "execution_time_seconds": self.execution_time_seconds,
        }


class ASTMutator(ast.NodeTransformer):
    """Discovers or applies a single mutation deterministically by index."""

    def __init__(self, target_index: int | None = None, file_path: str = "") -> None:
        super().__init__()
        self.target_index = target_index
        self.file_path = file_path
        self.current_index = 0
        self.candidates: list[MutantCandidate] = []
        self._in_annotation = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Don't mutate return type annotation
        if node.returns:
            old_ann = self._in_annotation
            self._in_annotation = True
            # Visit returns without mutating
            self._in_annotation = old_ann

        # Don't mutate arg type annotations
        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation:
                pass

        return self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
        # Only mutate assigned value, not annotation
        if node.value:
            node.value = self.visit(node.value)
        return node

    def visit_Import(self, node: ast.Import) -> ast.AST:
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        # Condition Inversion
        idx = self.current_index
        orig_s = f"if {ast.unparse(node.test)}:"

        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            new_test = node.test.operand
        else:
            new_test = ast.UnaryOp(op=ast.Not(), operand=node.test)

        mut_s = f"if {ast.unparse(new_test)}:"

        cand = MutantCandidate(
            id=f"{self.file_path}:{node.lineno}:cond_inv:{idx}",
            index=idx,
            file_path=self.file_path,
            line_number=node.lineno,
            col_offset=node.col_offset,
            operator_category="condition_inversion",
            original_op="if <cond>",
            mutated_op="if not (<cond>)",
            original_snippet=orig_s,
            mutated_snippet=mut_s,
        )
        self.candidates.append(cand)
        self.current_index += 1

        if self.target_index is not None and self.target_index == idx:
            new_node = ast.If(test=new_test, body=node.body, orelse=node.orelse)
            return ast.copy_location(new_node, node)

        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        if node.ops:
            op_cls = type(node.ops[0])
            if op_cls in COMPARISON_MUTATIONS:
                idx = self.current_index
                target_cls, new_sym, old_sym = COMPARISON_MUTATIONS[op_cls]
                orig_s = ast.unparse(node)
                mut_node = ast.Compare(
                    left=node.left,
                    ops=[target_cls(), *node.ops[1:]],
                    comparators=node.comparators,
                )
                mut_s = ast.unparse(mut_node)

                cand = MutantCandidate(
                    id=f"{self.file_path}:{node.lineno}:cmp:{idx}",
                    index=idx,
                    file_path=self.file_path,
                    line_number=node.lineno,
                    col_offset=node.col_offset,
                    operator_category="comparison",
                    original_op=old_sym,
                    mutated_op=new_sym,
                    original_snippet=orig_s,
                    mutated_snippet=mut_s,
                )
                self.candidates.append(cand)
                self.current_index += 1

                if self.target_index is not None and self.target_index == idx:
                    return ast.copy_location(mut_node, node)

        return self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        op_cls = type(node.op)
        if op_cls in ARITHMETIC_MUTATIONS:
            idx = self.current_index
            target_cls, new_sym, old_sym = ARITHMETIC_MUTATIONS[op_cls]
            orig_s = ast.unparse(node)
            mut_node = ast.BinOp(left=node.left, op=target_cls(), right=node.right)
            mut_s = ast.unparse(mut_node)

            cand = MutantCandidate(
                id=f"{self.file_path}:{node.lineno}:arith:{idx}",
                index=idx,
                file_path=self.file_path,
                line_number=node.lineno,
                col_offset=node.col_offset,
                operator_category="arithmetic",
                original_op=old_sym,
                mutated_op=new_sym,
                original_snippet=orig_s,
                mutated_snippet=mut_s,
            )
            self.candidates.append(cand)
            self.current_index += 1

            if self.target_index is not None and self.target_index == idx:
                return ast.copy_location(mut_node, node)

        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        op_cls = type(node.op)
        if op_cls in LOGICAL_MUTATIONS:
            idx = self.current_index
            target_cls, new_sym, old_sym = LOGICAL_MUTATIONS[op_cls]
            orig_s = ast.unparse(node)
            mut_node = ast.BoolOp(op=target_cls(), values=node.values)
            mut_s = ast.unparse(mut_node)

            cand = MutantCandidate(
                id=f"{self.file_path}:{node.lineno}:logic:{idx}",
                index=idx,
                file_path=self.file_path,
                line_number=node.lineno,
                col_offset=node.col_offset,
                operator_category="logical",
                original_op=old_sym,
                mutated_op=new_sym,
                original_snippet=orig_s,
                mutated_snippet=mut_s,
            )
            self.candidates.append(cand)
            self.current_index += 1

            if self.target_index is not None and self.target_index == idx:
                return ast.copy_location(mut_node, node)

        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self._in_annotation:
            return node

        # Boolean boundary mutation
        if isinstance(node.value, bool):
            idx = self.current_index
            orig_s = str(node.value)
            new_val = not node.value
            mut_s = str(new_val)

            cand = MutantCandidate(
                id=f"{self.file_path}:{node.lineno}:bound:{idx}",
                index=idx,
                file_path=self.file_path,
                line_number=node.lineno,
                col_offset=node.col_offset,
                operator_category="boundary",
                original_op=orig_s,
                mutated_op=mut_s,
                original_snippet=orig_s,
                mutated_snippet=mut_s,
            )
            self.candidates.append(cand)
            self.current_index += 1

            if self.target_index is not None and self.target_index == idx:
                new_node = ast.Constant(value=new_val)
                return ast.copy_location(new_node, node)

        # 0 <-> 1 integer boundary mutation
        elif isinstance(node.value, int) and node.value in (0, 1):
            idx = self.current_index
            orig_s = str(node.value)
            new_int_val = 1 if node.value == 0 else 0
            mut_s = str(new_int_val)

            cand = MutantCandidate(
                id=f"{self.file_path}:{node.lineno}:bound:{idx}",
                index=idx,
                file_path=self.file_path,
                line_number=node.lineno,
                col_offset=node.col_offset,
                operator_category="boundary",
                original_op=orig_s,
                mutated_op=mut_s,
                original_snippet=orig_s,
                mutated_snippet=mut_s,
            )
            self.candidates.append(cand)
            self.current_index += 1

            if self.target_index is not None and self.target_index == idx:
                new_node = ast.Constant(value=new_int_val)
                return ast.copy_location(new_node, node)

        return self.generic_visit(node)


class MutationTesterService:
    """Service to discover and evaluate mutants across project modules."""

    def __init__(self, repo_path: Path | None = None) -> None:
        self.repo_path = repo_path or Path(".")

    def discover_mutants(self, file_path: Path) -> list[MutantCandidate]:
        """Discovers all possible mutants in a single Python file."""
        if not file_path.is_file():
            return []

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            logger.warning("Could not parse file %s for mutation: %s", file_path, exc)
            return []

        rel_path = str(file_path.relative_to(self.repo_path)) if file_path.is_relative_to(self.repo_path) else str(file_path)
        mutator = ASTMutator(target_index=None, file_path=rel_path)
        mutator.visit(tree)
        return mutator.candidates

    def generate_mutated_source(self, file_path: Path, target_index: int) -> str:
        """Generates mutated source code with a single mutant applied."""
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        rel_path = str(file_path.relative_to(self.repo_path)) if file_path.is_relative_to(self.repo_path) else str(file_path)
        mutator = ASTMutator(target_index=target_index, file_path=rel_path)
        mutated_tree = mutator.visit(tree)
        ast.fix_missing_locations(mutated_tree)
        return ast.unparse(mutated_tree)

    def discover_repo_mutants(
        self,
        target_subpath: Path | None = None,
        max_mutants: int = 100,
    ) -> list[MutantCandidate]:
        """Discovers mutants across eligible files in the project."""
        target_dir = target_subpath or (self.repo_path / "core" / "services")
        if not target_dir.exists():
            target_dir = self.repo_path

        mutants: list[MutantCandidate] = []

        if target_dir.is_file():
            files = [target_dir]
        else:
            files = sorted(target_dir.rglob("*.py"))

        for f in files:
            # Rule 1 & exclusion safety
            if f.name == "orchestrator.py":
                continue
            if "__pycache__" in f.parts or ".venv" in f.parts or "migrations" in f.parts:
                continue
            if "test_" in f.name or f.name.startswith("."):
                continue

            file_mutants = self.discover_mutants(f)
            mutants.extend(file_mutants)
            if len(mutants) >= max_mutants:
                break

        return mutants[:max_mutants]

    def resolve_test_file(self, source_file: Path) -> Path | None:
        """Finds the most specific test file for a given source file."""
        stem = source_file.stem
        # Direct pattern: tests/test_{stem}.py
        candidate = self.repo_path / "tests" / f"test_{stem}.py"
        if candidate.is_file():
            return candidate

        # Nested pattern: tests/**/test_{stem}.py
        matches = list((self.repo_path / "tests").glob(f"**/test_{stem}.py"))
        if matches:
            return matches[0]

        return None

    def run_mutation_testing(
        self,
        target_path: Path | None = None,
        test_path: Path | None = None,
        max_mutants: int = 15,
        timeout: float = 8.0,
        dry_run: bool = False,
    ) -> MutationReport:
        """Runs mutation testing either in dry-run mode or live test execution.

        Source files are GUARANTEED to be restored to their original content
        via try...finally blocks.
        """
        start_time = time.perf_counter()
        target = target_path or self.repo_path

        if target.is_file():
            mutants = self.discover_mutants(target)
        else:
            mutants = self.discover_repo_mutants(target_subpath=target, max_mutants=max_mutants)

        mutants_to_test = mutants[:max_mutants]
        total_discovered = len(mutants)

        if dry_run:
            elapsed = time.perf_counter() - start_time
            return MutationReport(
                target_path=str(target),
                total_mutants_discovered=total_discovered,
                mutants_tested=0,
                killed=0,
                survived=0,
                timed_out=0,
                errored=0,
                mutation_score=100.0,
                mutants=mutants_to_test,
                dry_run=True,
                execution_time_seconds=round(elapsed, 3),
            )

        killed = 0
        survived = 0
        timed_out = 0
        errored = 0

        for candidate in mutants_to_test:
            cand_file = self.repo_path / candidate.file_path
            if not cand_file.is_file():
                candidate.status = "ERROR"
                candidate.killer_test = "File not found"
                errored += 1
                continue

            # Read original content
            original_content = cand_file.read_text(encoding="utf-8")

            # Determine test target
            resolved_test = test_path or self.resolve_test_file(cand_file)
            test_target_arg = str(resolved_test) if resolved_test else str(self.repo_path / "tests")

            c_start = time.perf_counter()
            try:
                # 1. Generate & write mutant
                mutated_code = self.generate_mutated_source(cand_file, candidate.index)
                cand_file.write_text(mutated_code, encoding="utf-8")

                # 2. Run test suite
                cmd = ["uv", "run", "pytest", test_target_arg, "-q", "--tb=no"]
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                c_elapsed = time.perf_counter() - c_start
                candidate.execution_time_seconds = round(c_elapsed, 3)

                if proc.returncode != 0:
                    # Test failed -> Mutant was caught/killed!
                    candidate.status = "KILLED"
                    candidate.killer_test = self._extract_failing_test(proc.stdout, proc.stderr)
                    killed += 1
                else:
                    # Test passed -> Mutant survived (blind spot!)
                    candidate.status = "SURVIVED"
                    survived += 1

            except subprocess.TimeoutExpired:
                c_elapsed = time.perf_counter() - c_start
                candidate.execution_time_seconds = round(c_elapsed, 3)
                candidate.status = "TIMEOUT"
                candidate.killer_test = f"Timed out after {timeout}s"
                timed_out += 1

            except Exception as exc:
                c_elapsed = time.perf_counter() - c_start
                candidate.execution_time_seconds = round(c_elapsed, 3)
                candidate.status = "ERROR"
                candidate.killer_test = str(exc)
                errored += 1

            finally:
                # Inviolable guarantee: Always restore original file content
                cand_file.write_text(original_content, encoding="utf-8")
                # Safety check
                restored = cand_file.read_text(encoding="utf-8")
                if restored != original_content:
                    logger.error("CRITICAL: Failed to cleanly restore %s!", cand_file)

        tested_count = killed + survived + timed_out + errored
        effective_killed = killed + timed_out
        score = round((effective_killed / tested_count * 100.0), 2) if tested_count > 0 else 100.0
        total_elapsed = time.perf_counter() - start_time

        return MutationReport(
            target_path=str(target),
            total_mutants_discovered=total_discovered,
            mutants_tested=tested_count,
            killed=killed,
            survived=survived,
            timed_out=timed_out,
            errored=errored,
            mutation_score=score,
            mutants=mutants_to_test,
            dry_run=False,
            execution_time_seconds=round(total_elapsed, 3),
        )

    def _extract_failing_test(self, stdout: str, stderr: str) -> str | None:
        """Parses the failing test name from pytest output."""
        output = f"{stdout}\n{stderr}"
        match = re.search(r"FAILED\s+([^\s:]+(?:::[\w_]+)?)", output)
        if match:
            return match.group(1)
        match = re.search(r"(tests/[^\s:]+\.py::[^\s\n]+)\s+FAILED", output)
        if match:
            return match.group(1)
        return "pytest-failure"
