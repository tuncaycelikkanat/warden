import ast
import logging
from dataclasses import dataclass
from pathlib import Path

from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

@dataclass
class ResilienceFinding:
    type: str  # "bare_except" or "missing_timeout"
    file: str
    line: int
    message: str

@dataclass
class ResilienceResult:
    findings: list[ResilienceFinding]

class ResilienceAnalyzerService:
    async def analyze(self, repo_path: Path) -> ResilienceResult:
        """Analyzes resilience patterns like bare excepts and missing timeouts using AST."""
        import asyncio
        
        def scan_files():
            findings = []
            files = discover_source_files(repo_path)
            for f in files:
                if f.suffix != ".py":
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                    tree = ast.parse(content, filename=str(f))
                    findings.extend(self._find_bare_except(tree, f))
                    findings.extend(self._find_missing_timeout(tree, f))
                except SyntaxError:
                    continue
                except Exception as e:
                    logger.warning(f"Error parsing AST for {f}: {e}")
            return findings

        findings = await asyncio.to_thread(scan_files)
        return ResilienceResult(findings=findings)

    def _find_bare_except(self, tree: ast.AST, file_path: Path) -> list[ResilienceFinding]:
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    # check if it just has 'pass'
                    is_pass = False
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        is_pass = True
                    msg = "Bare except with 'pass'" if is_pass else "Bare except without specific Exception type"
                    findings.append(ResilienceFinding(
                        type="bare_except",
                        file=str(file_path),
                        line=node.lineno,
                        message=msg
                    ))
        return findings

    def _find_missing_timeout(self, tree: ast.AST, file_path: Path) -> list[ResilienceFinding]:
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # check if it's requests.get/post/put/delete or httpx.*
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in ("requests", "httpx"):
                        if node.func.attr in ("get", "post", "put", "delete", "request"):
                            # check if 'timeout' is in keywords
                            has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
                            if not has_timeout:
                                findings.append(ResilienceFinding(
                                    type="missing_timeout",
                                    file=str(file_path),
                                    line=node.lineno,
                                    message=f"Missing timeout in {node.func.value.id}.{node.func.attr} call"
                                ))
        return findings
