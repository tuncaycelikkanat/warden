import asyncio
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from core.services.scanner import SecurityScannerService
from core.services.package import PackageCheckerService

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
            
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the MCP server over standard input/output
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
