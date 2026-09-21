"""Comprehensive tests for dynamic CategoryEvidence generation in AuditOrchestrator."""

from pathlib import Path

from core.services.orchestrator import AuditOrchestrator
from core.services.rubric import CategoryEvidence, CodeSnippet


def test_devops_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic DevOps evidence extraction for Docker, CI, and IaC."""
    orch = AuditOrchestrator()

    df = tmp_path / "Dockerfile"
    df.write_text("FROM python:3.12-alpine AS builder\nFROM python:3.12-slim\nUSER nonroot\nHEALTHCHECK --interval=30s CMD curl -f http://localhost:8080/health\n")

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3.8'\nservices:\n  web:\n    build: .\n")

    ci_dir = tmp_path / ".github" / "workflows"
    ci_dir.mkdir(parents=True)
    ci_file = ci_dir / "pipeline.yml"
    ci_file.write_text("name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest\n")

    tf = tmp_path / "main.tf"
    tf.write_text('resource "aws_s3_bucket" "audit_storage" {\n  bucket = "warden-bucket"\n}\n')

    env_ex = tmp_path / ".env.example"
    env_ex.write_text("DATABASE_URL=postgres://localhost:5432/db\n")

    files = [df, compose, ci_file, tf, env_ex]

    files_found, findings, snippets = orch._ev_devops(tmp_path, files)

    assert "Dockerfile" in files_found
    assert ".env.example" in files_found
    assert any("pipeline.yml" in f for f in files_found)
    assert any("main.tf" in f for f in files_found)

    findings_text = " ".join(findings)
    assert "multi-stage=True" in findings_text
    assert "non-root-user=True" in findings_text
    assert "healthcheck=True" in findings_text
    assert "CI/CD: Found 1 workflow pipeline(s)" in findings_text
    assert "Infrastructure-as-Code detected" in findings_text
    assert "Environment variable template present" in findings_text

    # Verify no hardcoded WARDEN praise
    assert "5-model fallback pool" not in findings_text

    assert len(snippets) >= 2
    assert isinstance(snippets[0], CodeSnippet)
    assert any(s.file == "Dockerfile" for s in snippets)
    assert any("pipeline.yml" in s.file for s in snippets)


def test_api_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic API design evidence detection."""
    orch = AuditOrchestrator()

    api_file = tmp_path / "api_routes.py"
    api_file.write_text(
        "from fastapi import APIRouter, HTTPException, Depends\n"
        "from pydantic import BaseModel\n"
        "router = APIRouter()\n"
        "class ItemPayload(BaseModel):\n"
        "    name: str\n"
        "@router.post('/items', status_code=201)\n"
        "def create_item(item: ItemPayload):\n"
        "    if not item.name:\n"
        "        raise HTTPException(status_code=400, detail='Missing name')\n"
        "    return item\n"
    )

    files = [api_file]
    files_found, findings, snippets = orch._ev_api(tmp_path, files)

    assert "api_routes.py" in files_found
    findings_text = " ".join(findings)
    assert "FastAPI" in findings_text
    assert "Pydantic BaseModel" in findings_text
    assert "HTTPException" in findings_text
    assert "Authentication dependencies" in findings_text

    assert len(snippets) > 0
    assert snippets[0].context == "API route endpoint declaration"
    assert "create_item" in snippets[0].code


def test_llm_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic LLM integration and prompt defense evidence detection."""
    orch = AuditOrchestrator()

    llm_file = tmp_path / "llm_client.py"
    llm_file.write_text(
        "import openai\n"
        "from tenacity import retry, stop_after_attempt\n"
        "class CustomPromptSanitizer:\n"
        "    def sanitize_prompt(self, text: str) -> str:\n"
        "        return text.replace('{', '').replace('}', '')\n"
        "@retry(stop=stop_after_attempt(3))\n"
        "def call_model(prompt: str):\n"
        "    client = openai.OpenAI()\n"
        "    resp = client.chat.completions.create(model='gpt-4', messages=[{'role': 'user', 'content': prompt}])\n"
        "    tokens = resp.usage.total_tokens\n"
        "    return resp\n"
    )

    files = [llm_file]
    files_found, findings, snippets = orch._ev_llm(tmp_path, files)

    assert "llm_client.py" in files_found
    findings_text = " ".join(findings)
    assert "openai" in findings_text
    assert "Prompt sanitization" in findings_text
    assert "retry loops" in findings_text
    assert "Token usage metrics" in findings_text

    # Anti-praise guarantee: Must NOT contain WARDEN's Google GenAI praise
    assert "google.genai client with 5-model fallback pool" not in findings_text

    assert len(snippets) > 0
    assert any("PromptSanitizer" in s.code for s in snippets)


def test_concurrency_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic concurrency and lock synchronization evidence detection."""
    orch = AuditOrchestrator()

    conc_file = tmp_path / "parallel_worker.py"
    conc_file.write_text(
        "import asyncio\n"
        "lock = asyncio.Lock()\n"
        "async def process_batch(items):\n"
        "    async with lock:\n"
        "        tasks = [asyncio.create_task(asyncio.sleep(0.01)) for _ in items]\n"
        "        return await asyncio.gather(*tasks)\n"
    )

    files = [conc_file]
    files_found, findings, snippets = orch._ev_concurrency(tmp_path, files)

    assert "parallel_worker.py" in files_found
    findings_text = " ".join(findings)
    assert "asyncio.gather" in findings_text
    assert "asyncio.Lock" in findings_text

    assert len(snippets) > 0


def test_architecture_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic layered architecture and interface contract detection."""
    orch = AuditOrchestrator()

    domain_dir = tmp_path / "domain"
    domain_dir.mkdir()
    service_dir = tmp_path / "services"
    service_dir.mkdir()

    iface_file = domain_dir / "interfaces.py"
    iface_file.write_text(
        "from abc import ABC, abstractmethod\n"
        "class AuditRepositoryProtocol(ABC):\n"
        "    @abstractmethod\n"
        "    def save_record(self, data: dict) -> None:\n"
        "        pass\n"
    )

    svc_file = service_dir / "engine.py"
    svc_file.write_text("class AuditService:\n    pass\n")

    files = [iface_file, svc_file]
    files_found, findings, snippets = orch._ev_architecture(tmp_path, files)

    assert any("domain" in f for f in files_found)
    assert any("services" in f for f in files_found)

    findings_text = " ".join(findings)
    assert "domain" in findings_text
    assert "services" in findings_text
    assert "Abstract base classes" in findings_text

    assert len(snippets) > 0
    assert "AuditRepositoryProtocol" in snippets[0].code


def test_frontend_ux_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic Frontend UX, component, and accessibility detection."""
    orch = AuditOrchestrator()

    comp_file = tmp_path / "Dashboard.tsx"
    comp_file.write_text(
        "import React, { useState } from 'react';\n"
        "export const Dashboard = () => {\n"
        "    const [active, setActive] = useState(false);\n"
        "    return (\n"
        "        <main role='main' aria-label='Analytics Panel'>\n"
        "            <button aria-expanded={active} onClick={() => setActive(!active)}>Toggle</button>\n"
        "        </main>\n"
        "    );\n"
        "};\n"
    )

    files = [comp_file]
    files_found, findings, snippets = orch._ev_frontend_ux(tmp_path, files)

    assert "Dashboard.tsx" in files_found
    findings_text = " ".join(findings)
    assert "UI Components: Detected 1" in findings_text
    assert "useState" in findings_text
    assert "Accessibility (a11y)" in findings_text

    assert len(snippets) > 0
    assert "aria-label" in snippets[0].code


def test_quantitative_logic_evidence_dynamic(tmp_path: Path):
    """Verifies dynamic quantitative modeling and validation detection."""
    orch = AuditOrchestrator()

    quant_file = tmp_path / "quant_strategy.py"
    quant_file.write_text(
        "import numpy as np\n"
        "from sklearn.model_selection import TimeSeriesSplit\n"
        "def compute_metrics(returns):\n"
        "    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)\n"
        "    max_drawdown = np.max(np.maximum.accumulate(returns) - returns)\n"
        "    return {'sharpe': sharpe, 'max_drawdown': max_drawdown}\n"
    )

    files = [quant_file]
    files_found, findings, snippets = orch._ev_quantitative_logic(tmp_path, files)

    assert "quant_strategy.py" in files_found
    findings_text = " ".join(findings)
    assert "sharpe" in findings_text
    assert "max_drawdown" in findings_text
    assert "TimeSeriesSplit" in findings_text

    assert len(snippets) > 0
    assert "sharpe" in snippets[0].code


def test_empty_repo_no_evidence_found(tmp_path: Path):
    """Verifies that an empty repo gracefully returns no_evidence_found status without fake praise."""
    orch = AuditOrchestrator()
    readme = tmp_path / "notes.txt"
    readme.write_text("Just some notes without any code or frameworks.")
    files = [readme]

    categories = [
        "devops_deployment",
        "api_design",
        "llm_integration",
        "concurrency_safety",
        "architectural_discipline",
        "frontend_ux",
        "quantitative_logic",
    ]

    for cat in categories:
        ev = orch._build_category_evidence(
            tmp_path, files, cat, coverage=None, base_files=[], base_findings=[]
        )
        assert isinstance(ev, CategoryEvidence)
        assert ev.evidence_collection_status == "no_evidence_found"
        assert len(ev.code_snippets) == 0
        assert len(ev.collection_errors) == 0
        assert any("No concrete evidence" in f for f in ev.findings)


def test_unknown_category_partial_error(tmp_path: Path):
    """Verifies that an unregistered category produces a partial_error status."""
    orch = AuditOrchestrator()
    ev = orch._build_category_evidence(
        tmp_path, [], "unknown_arbitrary_category", coverage=None, base_files=[], base_findings=[]
    )
    assert ev.evidence_collection_status == "partial_error"
    assert any("No collector registered" in err for err in ev.collection_errors)


def test_snippet_bounds_and_structure(tmp_path: Path):
    """Verifies CodeSnippet dataclass fields, bounds, and string structure."""
    file = tmp_path / "test.py"
    lines = ["line 1", "line 2", "def target_function():", "    return 42", "line 5"]
    file.write_text("\n".join(lines))

    orch = AuditOrchestrator()
    content = file.read_text()
    import re
    snip = orch._extract_snippet("test.py", content, re.compile(r"def target_function"), "Function signature")

    assert snip is not None
    assert snip.file == "test.py"
    assert snip.line_start == 1
    assert snip.line_end == 5
    assert "def target_function():" in snip.code
    assert snip.context == "Function signature"
