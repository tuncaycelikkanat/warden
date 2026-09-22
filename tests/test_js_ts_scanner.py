"""Tests for JsTsScannerService."""

import json
from pathlib import Path

import pytest

from core.services.js_ts_scanner import JsTsScannerService


@pytest.fixture
def scanner() -> JsTsScannerService:
    return JsTsScannerService()


class TestJsTsScannerService:
    def test_non_applicable_repo(self, scanner: JsTsScannerService, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('hello')")
        result = scanner.scan(tmp_path)
        assert not result.applicable

    def test_package_json_unpinned_dependencies(self, scanner: JsTsScannerService, tmp_path: Path) -> None:
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(json.dumps({
            "dependencies": {
                "react": "^18.2.0",
                "lodash": "4.17.21",
                "axios": "~1.6.0"
            }
        }))
        result = scanner.scan(tmp_path)
        assert result.applicable
        assert result.total_dependencies == 3
        assert "react" in result.unpinned_dependencies
        assert "axios" in result.unpinned_dependencies
        assert "lodash" not in result.unpinned_dependencies
        assert result.score < 100.0

    def test_tsconfig_strict_mode(self, scanner: JsTsScannerService, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        tsconfig = tmp_path / "tsconfig.json"
        tsconfig.write_text(json.dumps({
            "compilerOptions": {
                "strict": True,
                "target": "ES2022"
            }
        }))
        (tmp_path / "index.ts").write_text("const msg: string = 'test';")

        result = scanner.scan(tmp_path, files=[tmp_path / "index.ts"])
        assert result.applicable
        assert result.is_typescript
        assert result.strict_mode_enabled

    def test_inner_html_vulnerability_detected(self, scanner: JsTsScannerService, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        vuln_file = tmp_path / "app.js"
        vuln_file.write_text("""
function render(userInput) {
    document.getElementById('content').innerHTML = userInput;
}
""")
        result = scanner.scan(tmp_path, files=[vuln_file])
        assert result.inner_html_count == 1
        assert any("dangerously-set-inner-html" in f.rule for f in result.findings)
        assert result.score < 100.0

    def test_any_type_and_console_log_counting(self, scanner: JsTsScannerService, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}")
        ts_file = tmp_path / "service.ts"
        ts_file.write_text("""
function parse(data: any): any {
    console.log("Parsing data:", data);
    return (data as any).id;
}
""")
        result = scanner.scan(tmp_path, files=[ts_file])
        assert result.is_typescript
        assert result.any_type_count >= 2
        assert result.console_log_count == 1
        d = result.to_dict()
        assert d["applicable"] is True
