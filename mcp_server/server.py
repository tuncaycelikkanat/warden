"""Model Context Protocol (MCP) server exposing WARDEN audit, scanning, and remediation tools."""

import ast
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from core.services.circular_dependency_detector import CircularDependencyDetector
from core.services.entropy_analyzer import EntropyAnalyzerService
from core.services.monitor import AgentActionMonitor
from core.services.package import PackageCheckerService
from core.services.scanner import SecurityScannerService

logger = logging.getLogger(__name__)

app = Server("warden_mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Lists all available WARDEN MCP tools."""
    return [
        Tool(
            name="security_scan",
            description="Scans a file for security vulnerabilities using WARDEN Semgrep rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to scan",
                    }
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="check_package",
            description="Checks a PyPI package for security risks, typosquatting, and malware indicators.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the PyPI package to check",
                    }
                },
                "required": ["package_name"],
            },
        ),
        Tool(
            name="evaluate_agent_action",
            description="Evaluates a shell command for dangerous patterns before execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to evaluate",
                    }
                },
                "required": ["command"],
            },
        ),
        Tool(
            name="run_full_audit",
            description="Runs a full project audit (10+ tools) and returns the 0-100 scorecard, grade, and Markdown report path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to audit",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="warden_risk_score",
            description="Calculates real-time risk score (0-100), risk level (LOW/MEDIUM/HIGH/CRITICAL), and findings for a file or code snippet using AST, Shannon entropy, and security heuristics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Optional absolute path to the file to evaluate",
                    },
                    "code_snippet": {
                        "type": "string",
                        "description": "Optional Python source code snippet to evaluate directly",
                    },
                },
            },
        ),
        Tool(
            name="warden_fix_suggestion",
            description="Generates actionable remediation code, diff patch, and security explanation for detected vulnerabilities, secrets, or anti-patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "Category of issue (e.g. 'secret', 'sql_injection', 'eval', 'complexity', 'vibe_slop')",
                    },
                    "code_snippet": {
                        "type": "string",
                        "description": "The problematic code snippet requiring remediation",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional path of the target file",
                    },
                },
                "required": ["issue_type", "code_snippet"],
            },
        ),
        Tool(
            name="warden_check_cycles",
            description="Analyzes Python import dependency relationships to detect circular imports, cycle break candidates, and Mermaid graph visualization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository or project directory",
                    }
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="warden_check_entropy",
            description="Scans project files using Shannon entropy analysis to detect potential API keys, cryptographic tokens, and credentials.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to scan",
                    },
                    "max_findings": {
                        "type": "integer",
                        "description": "Maximum number of suspicious findings to return (default: 25)",
                    },
                },
                "required": ["repo_path"],
            },
        ),
        Tool(
            name="warden_audit",
            description="Executes a full or incremental WARDEN quality and security audit, reporting scores, grade, and quality gate pass/fail status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to audit",
                    },
                    "incremental": {
                        "type": "boolean",
                        "description": "If true, scans only modified or newly added files (faster)",
                    },
                    "min_score": {
                        "type": "integer",
                        "description": "Quality gate threshold (e.g. 80). If audit score is below this, returns quality gate failed",
                    },
                },
                "required": ["repo_path"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatches tool execution for requested WARDEN MCP tool."""
    if name == "security_scan":
        file_path = arguments.get("file_path")
        if not file_path:
            return [TextContent(type="text", text="Error: file_path is required")]

        try:
            scanner = SecurityScannerService()
            findings = scanner.scan_file(file_path)
            risk_level = scanner.calculate_risk_level(findings)

            result_str = f"Risk Level: {risk_level.upper()}\n"
            if findings:
                result_str += f"Found {len(findings)} issues:\n"
                for idx, f in enumerate(findings):
                    result_str += f"{idx+1}. {f.get('check_id')} at line {f.get('start', {}).get('line')}\n"
                    result_str += f"   {f.get('extra', {}).get('message')}\n"
            else:
                result_str += "No vulnerabilities found."

            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error scanning file: {e!s}")]

    elif name == "check_package":
        package_name = arguments.get("package_name")
        if not package_name:
            return [TextContent(type="text", text="Error: package_name is required")]

        try:
            checker = PackageCheckerService()
            result = await checker.calculate_risk_score(package_name)

            risk_level = result.get("risk_level", "unknown").upper()
            details = "\n- ".join(result.get("details", []))

            result_str = f"Package: {package_name}\nRisk Level: {risk_level}\nDetails:\n- {details}"
            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error checking package: {e!s}")]

    elif name == "evaluate_agent_action":
        command = arguments.get("command")
        if not command:
            return [TextContent(type="text", text="Error: command is required")]

        try:
            monitor = AgentActionMonitor()
            result = monitor.evaluate_action(command)

            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating action: {e!s}")]

    elif name in ("run_full_audit", "warden_audit"):
        repo_path = arguments.get("repo_path")
        if not repo_path:
            return [TextContent(type="text", text="Error: repo_path is required")]

        incremental = arguments.get("incremental", False)
        min_score = arguments.get("min_score")

        try:
            from core.infra.database import create_db_and_tables
            from core.services.orchestrator import AuditOrchestrator
            from core.services.report import AuditReportService

            create_db_and_tables()

            orch = AuditOrchestrator()
            res = await orch.run_full_audit(repo_path, incremental=incremental)

            reporter = AuditReportService()
            db_id = reporter.save_to_db(repo_path, res)
            md_path = reporter.generate_markdown(repo_path, res)

            scorecard = res.get("scorecard", {})
            total_score = scorecard.get("total_score", 0)
            grade = scorecard.get("grade", "F")
            l1 = scorecard.get("layer1_score", 0)
            l2 = scorecard.get("layer2_score", 0)

            gate_status = "N/A"
            gate_passed = True
            if min_score is not None:
                gate_passed = total_score >= min_score
                gate_status = "PASSED ✅" if gate_passed else f"FAILED ❌ (Score {total_score} < min {min_score})"

            result_str = (
                f"🛡️ WARDEN Audit Report\n"
                f"Repository: {repo_path}\n"
                f"Total Score: {total_score}/100 (Grade: {grade})\n"
                f"Layer 1 Score: {l1}/100 | Layer 2 Score: {l2}/100\n"
                f"Quality Gate: {gate_status}\n"
                f"Report saved to DB (ID: {db_id}) and {md_path}"
            )
            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error running audit: {e!s}")]

    elif name == "warden_risk_score":
        file_path = arguments.get("file_path")
        code_snippet = arguments.get("code_snippet")

        if not file_path and not code_snippet:
            return [TextContent(type="text", text="Error: Either file_path or code_snippet must be provided")]

        try:
            code = code_snippet or ""
            target_path = Path(file_path).resolve() if file_path else None
            if target_path and target_path.is_file() and not code:
                code = target_path.read_text(encoding="utf-8", errors="ignore")

            entropy_analyzer = EntropyAnalyzerService()
            entropy_findings = entropy_analyzer.scan_code(code, file_path=str(target_path or "snippet.py"))

            security_findings = []
            if target_path and target_path.is_file():
                try:
                    scanner = SecurityScannerService()
                    security_findings = scanner.scan_file(str(target_path))
                except Exception:
                    pass

            # AST syntax and complexity analysis
            syntax_valid = True
            complexity_issues = []
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        branches = sum(
                            1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler))
                        )
                        if branches > 10:
                            complexity_issues.append(f"Function '{node.name}' has high cyclomatic complexity ({branches})")
            except SyntaxError as syn_err:
                syntax_valid = False
                complexity_issues.append(f"Syntax error at line {syn_err.lineno}: {syn_err.msg}")

            # Compute risk score (0 to 100)
            risk_score = 0.0
            if not syntax_valid:
                risk_score += 50.0
            if entropy_findings:
                risk_score += min(40.0, len(entropy_findings) * 20.0)
            if security_findings:
                risk_score += min(40.0, len(security_findings) * 15.0)
            if complexity_issues and syntax_valid:
                risk_score += min(20.0, len(complexity_issues) * 10.0)

            risk_score = min(100.0, risk_score)
            if risk_score >= 70.0:
                level = "CRITICAL"
            elif risk_score >= 45.0:
                level = "HIGH"
            elif risk_score >= 20.0:
                level = "MEDIUM"
            else:
                level = "LOW"

            details = {
                "risk_score": risk_score,
                "risk_level": level,
                "syntax_valid": syntax_valid,
                "secret_findings_count": len(entropy_findings),
                "security_findings_count": len(security_findings),
                "complexity_findings_count": len(complexity_issues),
                "findings": [
                    {
                        "type": "secret_leak",
                        "line": f.line,
                        "variable": f.variable_name,
                        "masked_value": f.masked_value,
                        "entropy": f.entropy_score,
                    }
                    for f in entropy_findings
                ]
                + [{"type": "complexity_or_syntax", "issue": issue} for issue in complexity_issues],
            }

            return [TextContent(type="text", text=json.dumps(details, indent=2, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating risk score: {e!s}")]

    elif name == "warden_fix_suggestion":
        issue_type = (arguments.get("issue_type") or "").lower()
        code_snippet = arguments.get("code_snippet") or ""
        file_path = arguments.get("file_path") or "module.py"

        if not issue_type or not code_snippet:
            return [TextContent(type="text", text="Error: issue_type and code_snippet are required")]

        remediation = ""
        explanation = ""

        if any(k in issue_type for k in ("secret", "token", "key", "credential", "entropy")):
            explanation = (
                "Hassas API anahtarı veya kimlik bilgisi kaynak koda gömülmüş (hardcoded). "
                "Ortam değişkeninden (`os.getenv`) okunmalı ve `.env` dosyası `.gitignore`'a eklenmelidir."
            )
            remediation = (
                "import os\n\n"
                "# Doğru yaklaşım: Değeri ortam değişkeninden güvenle okuyun\n"
                'API_KEY = os.getenv("APP_SECRET_KEY")\n'
                "if not API_KEY:\n"
                '    raise RuntimeError("APP_SECRET_KEY ortam değişkeni tanımlanmamış!")'
            )
        elif "sql" in issue_type:
            explanation = (
                "Dinamik string birleştirme (f-string veya format) SQL Injection açığına yol açar. "
                "Parametreli sorgular (`cursor.execute(..., params)`) kullanılmalıdır."
            )
            remediation = (
                "# Güvenli parametreli sorgu kullanımı:\n"
                'cursor.execute("SELECT * FROM users WHERE username = %s AND status = %s", (username, "active"))'
            )
        elif "eval" in issue_type or "exec" in issue_type:
            explanation = (
                "`eval()` veya `exec()` arbitrary code execution açığı oluşturur. "
                "Literal değerlendirmeler için `ast.literal_eval` kullanılmalıdır."
            )
            remediation = (
                "import ast\n\n"
                "# Güvenli literal parse:\n"
                "safe_data = ast.literal_eval(user_input_str)"
            )
        elif "complexity" in issue_type or "cyclomatic" in issue_type:
            explanation = (
                "Yüksek siklomatik karmaşıklık kodun bakımını zorlaştırır ve test edilebilirliğini düşürür. "
                "Erken dönüşler (guard clauses) ve alt fonksiyonlara ayırma önerilir."
            )
            remediation = (
                "# Guard clauses ile düzleştirilmiş akış:\n"
                "def process_data(item):\n"
                "    if not item or not item.is_valid:\n"
                "        return None\n"
                "    return transform_item(item)"
            )
        else:
            explanation = (
                f"'{issue_type}' türü sorun için WARDEN güvenli refactoring kalıbı önerilmektedir."
            )
            remediation = (
                "# Refactored ve temiz kod sürümü:\n"
                + "\n".join(f"# {line}" for line in code_snippet.splitlines()[:5])
                + "\n# Lütfen kod tabanı standartlarına uygun temiz blok ile değiştirin."
            )

        result_payload = {
            "target_file": file_path,
            "issue_type": issue_type,
            "explanation": explanation,
            "suggested_fix": remediation,
        }

        return [TextContent(type="text", text=json.dumps(result_payload, indent=2, ensure_ascii=False))]

    elif name == "warden_check_cycles":
        repo_path = arguments.get("repo_path")
        if not repo_path:
            return [TextContent(type="text", text="Error: repo_path is required")]

        try:
            detector = CircularDependencyDetector()
            report = detector.analyze(Path(repo_path))

            result_str = (
                f"🔄 Circular Dependency Analysis for: {repo_path}\n"
                f"Total Modules Analyzed: {report.total_modules_analyzed}\n"
                f"Import Relationships (Edges): {report.total_import_edges}\n"
                f"Cycles Detected: {report.cycles_count}\n"
            )

            if report.has_cycles:
                result_str += "\nDetected Cycles:\n"
                for idx, c in enumerate(report.cycles, 1):
                    result_str += f"{idx}. {' -> '.join(c.cycle_path)} (Length: {c.length})\n"
                    if c.break_suggestion:
                        result_str += f"   Suggestion: {c.break_suggestion}\n"
            else:
                result_str += "\n✅ Clean! No circular import cycles detected (Acyclic DAG)."

            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error checking cycles: {e!s}")]

    elif name == "warden_check_entropy":
        repo_path = arguments.get("repo_path")
        if not repo_path:
            return [TextContent(type="text", text="Error: repo_path is required")]

        max_findings = arguments.get("max_findings", 25)

        try:
            analyzer = EntropyAnalyzerService()
            findings = analyzer.scan_repository(Path(repo_path), max_findings=max_findings)

            if not findings:
                return [TextContent(type="text", text=f"✅ Clean! No high-entropy secrets found in {repo_path}.")]

            result_str = f"⚠️ Found {len(findings)} high-entropy secret candidates in {repo_path}:\n"
            for idx, f in enumerate(findings, 1):
                result_str += (
                    f"{idx}. [{f.confidence}] {f.file}:{f.line} -> Variable: '{f.variable_name}' "
                    f"({f.masked_value}) [Entropy: {f.entropy_score:.2f}, Charset: {f.charset_type}]\n"
                )

            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error checking entropy: {e!s}")]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Runs the MCP server over standard input/output streams."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
