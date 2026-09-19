import asyncio
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from core.services.scanner import SecurityScannerService
from core.services.package import PackageCheckerService
from core.services.monitor import AgentActionMonitor

app = Server("warden_mcp")

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="security_scan",
            description="Scans a file for security vulnerabilities using WARDEN Semgrep rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to scan"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="check_package",
            description="Checks a PyPI package for security risks, typosquatting, and malware indicators.",
            inputSchema={
                "type": "object",
                "properties": {
                    "package_name": {
                        "type": "string",
                        "description": "Name of the PyPI package to check"
                    }
                },
                "required": ["package_name"]
            }
        ),
        Tool(
            name="evaluate_agent_action",
            description="Evaluates a shell command for dangerous patterns before execution.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to evaluate"
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            name="run_full_audit",
            description="Runs a full project audit (10+ tools) and returns the 0-100 scorecard, grade, and Markdown report path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the repository to audit"
                    }
                },
                "required": ["repo_path"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
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
            return [TextContent(type="text", text=f"Error scanning file: {str(e)}")]
            
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
            return [TextContent(type="text", text=f"Error checking package: {str(e)}")]
            
    elif name == "evaluate_agent_action":
        command = arguments.get("command")
        if not command:
            return [TextContent(type="text", text="Error: command is required")]
            
        try:
            monitor = AgentActionMonitor()
            result = monitor.evaluate_action(command)
            
            import json
            return [TextContent(type="text", text=json.dumps(result))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating action: {str(e)}")]
            
    elif name == "run_full_audit":
        repo_path = arguments.get("repo_path")
        if not repo_path:
            return [TextContent(type="text", text="Error: repo_path is required")]
            
        try:
            from core.infra.database import create_db_and_tables
            from core.services.orchestrator import AuditOrchestrator
            from core.services.report import AuditReportService
            
            # Ensure DB is created
            create_db_and_tables()
            
            orch = AuditOrchestrator()
            res = await orch.run_full_audit(repo_path)
            
            reporter = AuditReportService()
            db_id = reporter.save_to_db(repo_path, res)
            md_path = reporter.generate_markdown(repo_path, res)
            
            scorecard = res.get("scorecard", {})
            result_str = (
                f"Audit Complete!\n"
                f"Total Score: {scorecard.get('total_score')}/100 (Grade: {scorecard.get('grade')})\n"
                f"Layer 1 Score: {scorecard.get('layer1_score')} | Layer 2 Score: {scorecard.get('layer2_score')}\n"
                f"Report saved to DB (ID: {db_id}) and {md_path}"
            )
            return [TextContent(type="text", text=result_str)]
        except Exception as e:
            return [TextContent(type="text", text=f"Error running full audit: {str(e)}")]
            
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the MCP server over standard input/output
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
