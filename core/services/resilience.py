"""Resilience and fault-tolerance analyzer using AST parsing."""

import ast
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.services.shared.scan_exclusions import is_duplication_excluded, is_lockfile_or_vendor
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

ABSURD_TIMEOUT_THRESHOLD = 60.0
HTTP_CLIENT_CONSTRUCTORS = {"Session", "Client", "AsyncClient"}
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "request"}


@dataclass
class ResilienceDefect:
    """Represents a resilience defect such as a bare except, missing timeout, or resource leak."""

    rule: str  # "bare_except", "silent_exception_swallow", "missing_timeout", "resource_leak"
    file: str
    line: int
    detail: str
    severity: str = "HIGH"

    @property
    def type(self) -> str:
        """Backward compatibility with existing callers expecting .type."""
        return self.rule

    @property
    def message(self) -> str:
        """Backward compatibility with existing callers expecting .message."""
        return self.detail


# Backward compatibility alias
ResilienceFinding = ResilienceDefect


@dataclass
class SkippedFile:
    """Represents a file that failed parsing due to syntax or encoding errors."""

    file: str
    reason: str


@dataclass
class ResilienceResult:
    """Encapsulates all identified resilience defect findings and parse health."""

    measured: bool
    defects: list[ResilienceDefect] = field(default_factory=list)
    file_count: int = 0
    skipped_files: list[SkippedFile] = field(default_factory=list)
    reason: str | None = None

    @property
    def findings(self) -> list[ResilienceDefect]:
        """Backward compatibility with existing callers expecting .findings."""
        return self.defects


class ResilienceAnalyzerService:
    """Service to detect resilience anti-patterns via robust AST analysis."""

    async def analyze(self, repo_path: Path) -> ResilienceResult:
        """Analyzes resilience patterns with error resilience and central exclusions."""
        return await asyncio.to_thread(self._scan_repository, repo_path)

    def _scan_repository(self, repo_path: Path) -> ResilienceResult:
        all_files = discover_source_files(repo_path)
        py_files: list[Path] = []

        for f in all_files:
            if f.suffix != ".py":
                continue
            rel_str = str(f.relative_to(repo_path)) if f.is_relative_to(repo_path) else str(f)
            if is_lockfile_or_vendor(rel_str, repo_path) or is_duplication_excluded(rel_str, repo_path):
                continue
            py_files.append(f)

        if not py_files:
            return ResilienceResult(measured=False, reason="no_python_files", file_count=0)

        defects: list[ResilienceDefect] = []
        skipped_files: list[SkippedFile] = []

        for f in py_files:
            rel_path = str(f.relative_to(repo_path)) if f.is_relative_to(repo_path) else str(f)
            try:
                content = f.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(f))
                defects.extend(self._scan_rules(tree, rel_path))
            except (SyntaxError, RecursionError, UnicodeDecodeError, MemoryError, OSError) as e:
                skipped_files.append(SkippedFile(file=rel_path, reason=f"{type(e).__name__}: {e}"))
                logger.warning("Error parsing AST for %s: %s", rel_path, e)

        if skipped_files and len(skipped_files) == len(py_files):
            return ResilienceResult(
                measured=False,
                reason="all_files_failed_to_parse",
                file_count=len(py_files),
                skipped_files=skipped_files,
            )

        return ResilienceResult(
            measured=True,
            defects=defects,
            file_count=len(py_files),
            skipped_files=skipped_files,
        )

    def _eval_literal(self, node: ast.AST) -> Any:
        """Evaluates simple literal AST nodes (int, float, None, str). Returns Ellipsis for dynamic."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            if isinstance(node.operand.value, (int, float)):
                return -node.operand.value
        return ...

    def _is_http_call(self, node: ast.Call, session_vars: set[str]) -> tuple[bool, str]:
        """Checks whether an AST Call is a network request via requests, httpx, or a known session var."""
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                caller_name = node.func.value.id
                if caller_name in ("requests", "httpx") and attr_name in HTTP_METHODS:
                    return True, f"{caller_name}.{attr_name}"
                if caller_name in session_vars and attr_name in HTTP_METHODS:
                    return True, f"{caller_name}.{attr_name}"
        return False, ""

    def _find_session_vars(self, tree: ast.AST) -> set[str]:
        """Discovers local variable names assigned to requests.Session or httpx.Client."""
        session_vars: set[str] = set()

        for node in ast.walk(tree):
            # 1. Assign: s = requests.Session() / client = httpx.Client()
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id in ("requests", "httpx") and func.attr in HTTP_CLIENT_CONSTRUCTORS:
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                session_vars.add(target.id)

            # 2. With: with requests.Session() as s:
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        func = item.context_expr.func
                        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                            if func.value.id in ("requests", "httpx") and func.attr in HTTP_CLIENT_CONSTRUCTORS:
                                if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                                    session_vars.add(item.optional_vars.id)

        return session_vars

    def _check_body_noop(self, body: list[ast.stmt]) -> bool:
        """Determines if an AST block body is effectively a no-op (pass, ..., or docstring only)."""
        if len(body) == 1:
            stmt = body[0]
            if isinstance(stmt, ast.Pass):
                return True
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Ellipsis (...) or standalone string
                if stmt.value.value is Ellipsis or isinstance(stmt.value.value, str):
                    return True
        return False

    def _scan_rules(self, tree: ast.AST, file_path: str) -> list[ResilienceDefect]:
        """Runs all resilience defect rules against a parsed AST tree."""
        defects: list[ResilienceDefect] = []
        session_vars = self._find_session_vars(tree)

        # Mark all calls inside 'with' statements so we don't flag them as resource leaks
        with_calls: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        with_calls.add(id(item.context_expr))

        # 1. Check Except Handlers (bare_except & silent_exception_swallow)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                is_noop = self._check_body_noop(node.body)

                if node.type is None:
                    msg = "Bare except with 'pass'" if is_noop else "Bare except without specific Exception type"
                    defects.append(
                        ResilienceDefect(
                            rule="bare_except",
                            file=file_path,
                            line=node.lineno,
                            detail=msg,
                        )
                    )
                else:
                    # Broad exception check: except Exception: pass or except BaseException: pass
                    is_broad = False
                    exc_name = ""
                    if isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
                        is_broad = True
                        exc_name = node.type.id

                    if is_broad and is_noop:
                        defects.append(
                            ResilienceDefect(
                                rule="silent_exception_swallow",
                                file=file_path,
                                line=node.lineno,
                                detail=f"Silent exception swallow with '{exc_name}: pass'",
                            )
                        )

        # 2. Check HTTP Calls for Missing or Absurd Timeout
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_http, call_name = self._is_http_call(node, session_vars)
                if is_http:
                    timeout_kw = next((kw for kw in node.keywords if kw.arg == "timeout"), None)
                    if timeout_kw is None:
                        defects.append(
                            ResilienceDefect(
                                rule="missing_timeout",
                                file=file_path,
                                line=node.lineno,
                                detail=f"Missing timeout in {call_name} call (parametre_yok)",
                            )
                        )
                    else:
                        val = self._eval_literal(timeout_kw.value)
                        if val is None:
                            defects.append(
                                ResilienceDefect(
                                    rule="missing_timeout",
                                    file=file_path,
                                    line=node.lineno,
                                    detail=f"Missing timeout in {call_name} call (timeout=None)",
                                )
                            )
                        elif isinstance(val, (int, float)) and val > ABSURD_TIMEOUT_THRESHOLD:
                            defects.append(
                                ResilienceDefect(
                                    rule="missing_timeout",
                                    file=file_path,
                                    line=node.lineno,
                                    detail=f"Absurd timeout in {call_name} call (timeout={val}s)",
                                )
                            )

        # 3. Check Resource Leak on open() without with or explicit close()
        defects.extend(self._scan_resource_leaks(tree, file_path, with_calls))

        return defects

    def _scan_resource_leaks(self, tree: ast.AST, file_path: str, with_calls: set[int]) -> list[ResilienceDefect]:
        """Flags open() calls not guarded by context managers or explicit .close() calls."""
        defects: list[ResilienceDefect] = []

        # We inspect function scopes (or module scope) to pair variable assignments with .close()
        for scope_node in ast.walk(tree):
            if isinstance(scope_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                # Collect all .close() calls in this scope
                closed_vars: set[str] = set()
                for child in ast.walk(scope_node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                        if child.func.attr == "close" and isinstance(child.func.value, ast.Name):
                            closed_vars.add(child.func.value.id)

                # Look for open() calls in this scope's immediate or nested statements
                for child in ast.walk(scope_node):
                    if isinstance(child, ast.Call) and id(child) not in with_calls:
                        if isinstance(child.func, ast.Name) and child.func.id == "open":
                            # Check if assigned to variable: var = open(...)
                            # We can find parent assignment if present
                            # To do so cleanly, check if any closed_var was assigned this call
                            is_closed = False
                            for assign in ast.walk(scope_node):
                                if isinstance(assign, ast.Assign) and assign.value is child:
                                    for target in assign.targets:
                                        if isinstance(target, ast.Name) and target.id in closed_vars:
                                            is_closed = True
                                            break

                            if not is_closed:
                                defects.append(
                                    ResilienceDefect(
                                        rule="resource_leak",
                                        file=file_path,
                                        line=child.lineno,
                                        detail="File opened without context manager or explicit close()",
                                    )
                                )

        # Deduplicate defects that might have been walked from module and inner function
        seen: set[tuple[str, int, str]] = set()
        unique_defects: list[ResilienceDefect] = []
        for d in defects:
            key = (d.file, d.line, d.detail)
            if key not in seen:
                seen.add(key)
                unique_defects.append(d)

        return unique_defects

    # Backward compatibility methods
    def _find_bare_except(self, tree: ast.AST, file_path: Path) -> list[ResilienceDefect]:
        """Legacy helper for existing tests."""
        defects = self._scan_rules(tree, str(file_path))
        return [d for d in defects if d.rule in ("bare_except", "silent_exception_swallow")]

    def _find_missing_timeout(self, tree: ast.AST, file_path: Path) -> list[ResilienceDefect]:
        """Legacy helper for existing tests."""
        defects = self._scan_rules(tree, str(file_path))
        return [d for d in defects if d.rule == "missing_timeout"]
