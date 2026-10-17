<div align="center">

```text
 ██╗    ██╗ █████╗ ██████╗ ██████╗ ███████╗███╗   ██╗
 ██║    ██║██╔══██╗██╔══██╗██╔══██╗██╔════╝████╗  ██║
 ██║ █╗ ██║███████║██████╔╝██║  ██║█████╗  ██╔██╗ ██║
 ██║███╗██║██╔══██║██╔══██╗██║  ██║██╔══╝  ██║╚██╗██║
 ╚███╔███╔╝██║  ██║██║  ██║██████╔╝███████╗██║ ╚████║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝
```

### 🛡️ Autonomous Code Audit, Architectural Governance & Vibe-Coding Quality Engine
### 🛡️ Otonom Kod Denetimi, Mimari Kalite ve Vibe-Coding Yönetişim Motoru

[![CI](https://github.com/tuncaycelikkanat/warden/actions/workflows/ci.yml/badge.svg)](https://github.com/tuncaycelikkanat/warden/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PyPI](https://img.shields.io/pypi/v/warden-audit?style=flat-square&logo=pypi)](https://pypi.org/project/warden-audit/)
[![MCP](https://img.shields.io/badge/MCP-Protocol%20Ready-purple?style=flat-square)](mcp_server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

---

### 🌐 Select Language / Dil Seçimi
**[ 🇬🇧 English Documentation ](#-english)** &nbsp;&nbsp;•&nbsp;&nbsp; **[ 🇹🇷 Türkçe Dokümantasyon ](#-türkçe)**

---

</div>

<a id="-english"></a>
# 🇬🇧 English

## 📑 Table of Contents
- [💡 Why WARDEN?](#-why-warden)
- [🏛️ Dual-Layer Architecture](#-dual-layer-architecture)
- [📊 Live Terminal Scorecard](#-live-terminal-scorecard)
- [🚀 Quick Start](#-quick-start)
- [💻 Comprehensive CLI Reference](#-comprehensive-cli-reference)
  - [1. Core Lifecycle Commands](#1-core-lifecycle-commands)
  - [2. Testing & Verification Suite](#2-testing--verification-suite)
  - [3. Security & Supply-Chain Suite](#3-security--supply-chain-suite)
  - [4. Architectural Intelligence & AI Analytics](#4-architectural-intelligence--ai-analytics)
- [🌐 Modern Web Dashboard & REST API](#-modern-web-dashboard--rest-api)
- [🤖 Model Context Protocol (MCP) Server & Agent Guardrails](#-model-context-protocol-mcp-server--agent-guardrails)
- [⚙️ Central Configuration (`warden.config.yaml`)](#-central-configuration-wardenconfigyaml)
- [🔐 Environment Variables (`.env`)](#-environment-variables-env)
- [🐙 CI/CD Quality Gates & Exit Codes](#-cicd-quality-gates--exit-codes)
- [🐳 Production Deployment (Docker & Terraform)](#-production-deployment-docker--terraform)
- [🔬 Testing, Mutation & Reliability](#-testing-mutation--reliability)
- [📚 Documentation Index](#-documentation-index)
- [📄 License & Authors](#-license--authors)

---

## 💡 Why WARDEN?

In the era of AI code assistants (**Cursor**, **GitHub Copilot**, **ChatGPT**, **Claude**), developers write code faster than ever. This accelerated paradigm—popularized as **"Vibe Coding"**—often trades deep architectural rigor, defensive programming, and security discipline for immediate generation speed. While productivity skyrockets, insidious software liabilities slip into production:

- ❌ **Swallowed Exceptions (Silent Failures):** Blanket `except Exception: pass` blocks injected by LLMs simply to keep code running without crashing, masking fatal runtime regressions.
- ❌ **Didactic AI Slop & Prompt Leaks:** Obvious explanatory comments explaining basic arithmetic, markdown artifacts (```python, ```json), and leftover LLM templates polluting source files.
- ❌ **Missing Call Timeouts:** Network (`requests.get`, `httpx.post`) or DB calls without explicit `timeout` arguments, leaving worker threads vulnerable to hung connections and cascading server deadlocks.
- ❌ **Unpinned & Poisoned Dependencies:** Version-less requirements and dependency confusion / typosquatting packages (`reqeusts`, `colorma`) leading to severe supply-chain vulnerabilities.
- ❌ **Secret & Credential Leaks:** Hardcoded API keys, JWT secrets, and bearer tokens inadvertently committed to Git history or embedded in test fixtures.
- ❌ **Hallucination Drift (Churn × Complexity Hotspots):** Fragile files repeatedly re-prompted to fix bugs, driving churn and cyclomatic complexity to catastrophic levels.

**WARDEN** is an autonomous quality assurance, security, and architectural governance engine designed specifically to conquer these challenges. It bridges the gap between **deterministic mechanical static analysis** and **LLM-powered semantic contextual reasoning**.

---

## 🏛️ Dual-Layer Architecture

WARDEN goes beyond rigid linters by combining mechanical precision with LLM-level semantic understanding:

```mermaid
flowchart TD
    subgraph Ingestion["Ingestion & Interfaces"]
        CLI["CLI: warden audit / bench"]
        API["FastAPI Web Dashboard & REST API"]
        MCP["MCP Server: AI Agent Shield"]
        GH["GitHub Actions & PR Review Bot"]
    end

    subgraph CoreEngine["Core Orchestration & Extensibility"]
        Dispatcher["CLI Dispatcher & API Factory"]
        Registry["Pluggable Analyzer Registry<br/>(entry_points: 'warden.analyzers')"]
        Gate["Quality Gate Engine<br/>(ExitCode 0 / 1 / 2 / 3)"]
    end

    subgraph Layer1["Layer 1: Deterministic Static Analysis (60%)"]
        Sec["Security & Entropy<br/>(Semgrep, Gitleaks, Shannon Entropy)"]
        Res["Resilience AST<br/>(Timeouts, Bare Excepts, Resource Leaks)"]
        Health["Code Health & Types<br/>(Coverage, Mypy, Ruff, Radon CC)"]
        Vibe["Vibe Governance<br/>(AI-Slop Classifier, Churn Hotspots)"]
    end

    subgraph Layer2["Layer 2: Semantic LLM Rubrics (40% - Optional)"]
        Collectors["7 Dynamic Evidence Collectors<br/>(API, Arch, Concurrency, DevOps)"]
        LLM["Multi-Model LLM Panels<br/>(Gemini, Claude, OpenAI, Ollama)"]
    end

    subgraph Output["Consolidated Output"]
        Scorecard["Hierarchical Scorecard Aggregator"]
        Reports["Reports: Terminal, JSON, SARIF, Markdown, PDF"]
    end

    CLI --> Dispatcher
    API --> Dispatcher
    MCP --> Dispatcher
    GH --> Dispatcher

    Dispatcher --> Registry
    Registry --> Layer1
    Registry --> Layer2

    Layer1 --> Scorecard
    Layer2 --> Scorecard
    Scorecard --> Gate
    Scorecard --> Output
```

### 1. Layer 1: 16 Deterministic Mechanical Analyzers (60% Weight)
Organized into 5 foundational dimensions:
1. **🛡️ Security & Supply Chain (25%):** Semgrep SAST (OWASP Top 10, SQLi, XSS), Gitleaks secret detection, Google OSV vulnerability database checks, open-source license compliance.
2. **🧪 Code Health & Testing (25%):** Sandboxed line/branch test coverage (`coverage.py`), AST assertion density (detects empty/tautological tests), Mypy static type safety, Interrogate documentation coverage.
3. **📐 Structural Health & Complexity (20%):** Radon McCabe Cyclomatic Complexity, JSCPD cross-language token-level code duplication (DRY), Halstead Maintainability Index.
4. **⚡ Resilience & Performance (15%):** AST defect scanner for missing HTTP/DB timeouts, bare except handlers, Dockerfile multi-stage / non-root linting.
5. **🤖 Developer Hygiene & Vibe-Coding (15%):** Heuristic NLP & regex for AI comments, prompt injection remnants, Git commit conventions, and Churn × Complexity hotspot tracking.

### 2. Layer 2: LLM Dynamic Semantic Rubrics (40% Weight)
Layer 2 does not rely on vague prompt summaries. It feeds **7 concrete evidence collectors** into LLMs (Gemini, Claude, OpenAI, Ollama):
- **API Collector:** FastAPI/Flask routes, schema validation, HTTP status codes, authentication decorators.
- **Architecture Collector:** Layer boundaries, domain decoupling, abstraction leakage, cyclic dependencies.
- **Concurrency Collector:** Thread pools, async/await event loop safety, mutex locks, race condition defenses.
- **DevOps Collector:** Multi-stage Docker, CI workflows, Terraform IaC, environment hygiene.
- **Frontend Collector:** Component lifecycle, state management, accessibility (ARIA), hydration safety.
- **LLM Collector:** Prompt sanitization, structured output enforcement, fallback resilience.
- **Quantitative Collector:** Aggregates Layer 1 metrics for context-aware interpretation.

> [!TIP]
> **Graceful Degradation:** If no LLM API key (`GEMINI_API_KEY`) is configured, WARDEN does not fail. Layer 2's 40% weight is automatically redistributed to Layer 1 (60% → 100%), completing the audit 100% deterministically with zero external dependencies.

---

## 📊 Live Terminal Scorecard

Running `warden audit --path . --min-score 75` generates an executive scorecard:

```text
================================================================================
🛡️  WARDEN — Autonomous Code Audit & Quality Governance Scorecard
================================================================================
📂 Target: /home/tuncay/PycharmProjects/warden  |  ⏱️ Duration: 14.2s
🔍 16 Layer-1 Analyzers and Dynamic Evidence Collectors Completed

┌───────────────────────────────────────┬──────────┬─────────────┬──────────────┐
│ Audit Dimension                       │ Weight   │ Score (/100)│ Status       │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ 🛡️ Security & Supply Chain            │   25%    │     97.9    │ 🟢 Pristine  │
│ 🧪 Code Health & Test Coverage        │   25%    │     99.9    │ 🟢 Pristine  │
│ 📐 Structural Health & Complexity     │   20%    │     86.9    │ 🟢 Passed    │
│ ⚡ Resilience & Performance            │   15%    │    100.0    │ 🟢 Pristine  │
│ 🤖 Developer Hygiene & Vibe-Coding    │   15%    │     96.6    │ 🟢 Pristine  │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ Layer 1 (Deterministic Static Score)  │  100%    │     97.0    │ 🟢 Pristine  │
│ Layer 2 (LLM Semantic Rubric Score)   │   N/A    │  Degraded   │ ⚪ Zero-Dep  │
└───────────────────────────────────────┴──────────┴─────────────┴──────────────┘

🏆 OVERALL WARDEN SCORE: 97/100 (Grade: A+ — Outstanding Excellence)
• Quality Gate: ✅ PASSED (Threshold: 75.0, Critical Violations: 0)
• Output Report: warden_reports/warden_report_*.md (.pdf / .sarif)
================================================================================
```

---

## 🎯 Empirical Benchmark & Detection Proof

Unlike tools that rely on anecdotal claims, WARDEN's static defect and vibe-coding detectors are quantitatively validated against a curated, ground-truth benchmark dataset ([`benchmarks/dataset.py`](benchmarks/dataset.py)) covering real-world positive and negative cases.

Run the benchmark suite locally anytime with:
```bash
warden bench
# or machine-readable JSON
warden benchmark --json
```

### Quantitative Detector Performance (v0.1.0 Benchmark Suite)

| Detector / Category | Samples | True Positives | False Positives | True Negatives | False Negatives | Precision | Recall | F1-Score | Accuracy |
|:--------------------|:-------:|:--------------:|:---------------:|:--------------:|:---------------:|:---------:|:------:|:--------:|:--------:|
| `ai_slop`           | 7       | 4              | 0               | 3              | 0               | **100.0%**| **100.0%**| **1.000**| **100.0%**|
| `bare_except`       | 5       | 2              | 0               | 3              | 0               | **100.0%**| **100.0%**| **1.000**| **100.0%**|
| `missing_timeout`   | 7       | 4              | 0               | 3              | 0               | **100.0%**| **100.0%**| **1.000**| **100.0%**|
| `secret_entropy`    | 7       | 3              | 0               | 4              | 0               | **100.0%**| **100.0%**| **1.000**| **100.0%**|
| `silent_swallow`    | 6       | 3              | 0               | 3              | 0               | **100.0%**| **100.0%**| **1.000**| **100.0%**|
| **OVERALL (Macro)** | **32**  | **16**         | **0**           | **16**         | **0**           | **100.0%**| **100.0%**| **1.000**| **100.0%**|

> [!NOTE]
> **Score Determinism Guarantee:** WARDEN guarantees **0 variance** across repeated Layer 1 audits on the same git tree. Every run is bit-for-bit idempotent, verified by automated property-based Hypothesis tests ([`tests/test_determinism.py`](tests/test_determinism.py)).

---

## 🚦 CI/CD Quality Gate & Exit Code Specification

When integrated into GitHub Actions, GitLab CI, or pre-commit hooks, WARDEN provides a deterministic exit code contract:

| Exit Code | Constant | Meaning | CI Action |
|:---------:|:---------|:--------|:----------|
| `0` | `PASSED` | Audit passed all thresholds; no blocking security issues. | ✅ Build passes |
| `1` | `BELOW_THRESHOLD` | Overall score is below `--min-score <N>`. | ⚠️ Quality gate regression |
| `2` | `SECURITY_VIOLATION` | Secret leaks, SAST errors, or vulnerable dependencies under `--fail-on-critical`. | 🚨 Critical security failure |
| `3` | `EXECUTION_ERROR` | Fatal runtime error (bad path, missing tool, invalid configuration). | ❌ Infrastructure / Config error |

Piping into downstream CI tools is 100% reliable with `--format json`: all human logs stream to `stderr`, leaving `stdout` as pure, machine-parseable JSON:
```bash
warden audit --format json --min-score 85 | jq .scorecard.total_score
```

---

## 🚀 Quick Start

### ⚡ Instant Install via PyPI
```bash
pip install warden-audit

# or using uv
uv tool install warden-audit
```

### 1. Automated Installation from Source (Linux / macOS)
The fastest way to install WARDEN and its system scanners:
```bash
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden
chmod +x install.sh
./install.sh
```

### 2. Manual Installation with `uv`
```bash
# 1. Clone repository
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden

# 2. Create and activate virtual environment
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
uv pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
```

### 3. Add Your LLM API Key (Optional for Layer 2)
```bash
echo 'GEMINI_API_KEY="AIzaSyYourGeminiApiKeyHere"' >> .env
```

### 4. Run Your First Audit
```bash
# Full audit on current directory
uv run python core/main.py audit --path .

# Fast incremental audit on changed files only (< 3 seconds)
uv run python core/main.py audit --path . --incremental

# Enforce a strict quality gate in CI
uv run python core/main.py audit --path . --min-score 80 --fail-on-critical
```

---

## 💻 Comprehensive CLI Reference

WARDEN provides 20+ specialized CLI commands grouped into 4 functional domains:

### 1. Core Lifecycle Commands

| Command | Arguments & Flags | Description |
| :--- | :--- | :--- |
| `audit` | `[target] [--path <p>] [--min-score <s>] [--incremental] [--since-commit <c>] [--full-history]` | Runs full dual-layer audit, evaluates quality gates, generates reports. |
| `serve` | `[--host 0.0.0.0] [--port 8000] [--reload]` | Boots FastAPI REST API, Swagger UI (`/docs`), and web dashboard. |
| `watch` | `[target] [--min-score <s>] [--debounce 0.8]` | Continuous real-time audit watcher; triggers instant delta scorecard on file save. |
| `badge` | `[--score <s>] [--grade <g>] [--label <l>] [-o <file>]` | Generates shields.io-compatible vector SVG badge for README score display. |
| `milestone`| `<audit_id> [--label <text>] [--clear]` | Tags an audit report in the DB as a reference baseline for future regressions. |
| `metrics` | `[--json]` | Exports Prometheus OpenMetrics exposition or JSON operational metrics. |
| `hook` | `install\|uninstall\|run [--hook-type pre-commit\|pre-push\|all] [--min-score 80]` | Manages local Git hooks to block subpar commits/pushes before they reach origin. |

```bash
# Continuous real-time live audit on code edits
warden watch . --min-score 80

# Generate SVG vector badge for README
warden badge --score 95 --grade A+ -o warden-score.svg

# Tag audit #42 as milestone release v1.0.0
warden milestone 42 --label "v1.0.0-release"

# Install pre-commit & pre-push hooks
warden hook install --hook-type all --min-score 80
```

---

### 2. Testing & Verification Suite

| Command | Arguments & Flags | Description |
| :--- | :--- | :--- |
| `generate-property-tests` | `[target] [--output <file>] [--max-tests 15]` | Analyzes AST type hints and synthesizes Hypothesis property-based test invariant templates. |
| `mutate` | `[target] [--test-path <p>] [--max-mutants 15] [--timeout 8.0] [--dry-run] [--output <f>]` | Executes AST mutation testing to measure mutant kill rate and catch test suite blind spots. |
| `bdd` | `[target] [--feature-dir <d>] [--output <f>] [--enrich-llm] [--provider gemini]` | Extracts Given-When-Then BDD Gherkin scenarios from test code with optional LLM user-story enrichment. |

```bash
# Synthesize property tests for core services
warden generate-property-tests core/services/ --output tests/test_properties_gen.py

# Run mutation testing with dry-run mapping
warden mutate core/services/evidence/ --dry-run
```

---

### 3. Security & Supply-Chain Suite

| Command | Arguments & Flags | Description |
| :--- | :--- | :--- |
| `generate-sbom` | `[target] [--output <file>]` | Generates a CycloneDX v1.5 JSON Software Bill of Materials (SBOM) for compliance. |
| `scan-entropy` | `[target] [--max-findings 25]` | Scans source code using Shannon entropy to pinpoint zero-day leaked credentials. |
| `check-attack-surface` | `[target] [--top 10]` | Constructs NetworkX dependency graph and computes PageRank criticality & blast radius. |
| `check-typosquatting` | `<package_name>` | Evaluates candidate packages for typosquatting attacks against top PyPI libraries. |

```bash
# Export CycloneDX SBOM
warden generate-sbom . --output sbom.json

# Scan code for high-entropy secrets
warden scan-entropy . --max-findings 10

# Test a suspicious package
warden check-typosquatting reqeusts-security-patch
```

---

### 4. Architectural Intelligence & AI Analytics

| Command | Arguments & Flags | Description |
| :--- | :--- | :--- |
| `check-cycles` | `[target]` | Detects circular imports and cyclic dependency graphs using NetworkX AST DAG analysis. |
| `check-ck` | `[target] [--top 15] [--smells-only] [--output <f>]` | Computes Chidamber & Kemerer (CK) Object-Oriented metrics (WMC, DIT, CBO, RFC, LCOM4) and smells. |
| `export-sarif` | `[target] [--output warden.sarif] [--audit-id <id>]` | Exports findings to OASIS SARIF v2.1.0 for GitHub Code Scanning tab integration. |
| `export-pdf` | `[target] [--output report.pdf] [--audit-id <id>]` | Generates a boardroom-ready Executive PDF report with colorful badges and charts. |
| `query` | `"<nl_query>" [--json] [--provider gemini]` | Natural language Text-to-SQL dashboard query engine with chart recommendations. |
| `classify` | `[target] [--weights] [--override key=val]` | Classifies project archetype (FastAPI, CLI, Library) and tunes dynamic quality weights. |
| `forecast` | `[target] [--horizon 5] [--dimension total\|all]` | Projects future code quality and tech debt trends using Holt's exponential smoothing. |
| `anomaly` | `[target] [--audit-id <id>] [--method hybrid\|mahalanobis]` | Multivariate anomaly detection to catch sudden score drifts and quality regression roots. |
| `pr-review` | `[target] [--pr 1] [--owner org] [--repo repo] [--post]` | GitHub PR Review Bot: runs diff audit, writes upsert summary comment, and posts inline notes. |

```bash
# Inspect circular imports
warden check-cycles .

# Inspect object-oriented architectural smells (God Class, Brain Class)
warden check-ck core/ --smells-only

# Ask natural language questions about historical audits
warden query "Which repositories have a score below 80 in the last 30 days?"
```

---

## 🌐 Modern Web Dashboard & REST API

WARDEN includes a built-in dark-themed Single-Page Application (SPA) dashboard and a production-grade FastAPI REST API.

```bash
uv run python core/main.py serve --host 0.0.0.0 --port 8000 --reload
```

- 📊 **Web Dashboard:** [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/)
- 📖 **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 📈 **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- 💓 **Health Check Endpoint:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Key Dashboard Capabilities:
- 🎯 **Executive KPI Cards:** Instant visibility into overall score, letter grade, critical vulnerabilities, and test coverage.
- 🕸️ **5D Architectural Radar:** Live balance chart across Security, Testing, Structural, Resilience, and DevOps.
- 📈 **Time-Series Evolution Curves:** Historical quality trajectory across Git commits with regression alert triggers.
- ⚖️ **A/B Audit Comparator:** Side-by-side delta view contrasting any two audits or branches.
- 📢 **Slack & Discord Webhooks:** Automated alerts triggering on quality regressions (>= 5 point drops) or critical CVE detections.

---

## 🤖 Model Context Protocol (MCP) Server & Agent Guardrails

WARDEN natively implements Anthropic's **Model Context Protocol (MCP)** via `mcp_server/server.py`. AI agents in **Cursor**, **Claude Desktop**, or **Antigravity** can tap into WARDEN tools directly:

```json
{
  "mcpServers": {
    "warden": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/warden"
    }
  }
}
```

### Provided MCP Tools:
- `security_scan(file_path)`: Scans any file with WARDEN's AST & Semgrep security rules.
- `check_package(package_name)`: Verifies candidate PyPI packages for typosquatting and malicious indicators.
- `evaluate_agent_action(command)`: **Agent Guardrail:** Analyzes shell commands before execution to block catastrophic commands (`rm -rf /`, piping unvetted URLs into bash, tampering with `.env`).
- `check_cycles(directory)`: Verifies import acyclicity on the fly.
- `scan_entropy(file_path)`: Detects credential leakage before staging files.

---

## ⚙️ Central Configuration (`warden.config.yaml`)

Customize thresholds and rule weights at the root of your project:

```yaml
# ==============================================================================
# 🛡️ WARDEN — Central Governance Configuration
# ==============================================================================

general:
  project_name: "My Enterprise Project"
  threshold_score: 75.0               # Minimum quality gate pass score (0 - 100)
  fail_on_critical_vulns: true        # Immediately fail gate on CRITICAL CVE or leak
  ignore_paths:
    - "tests/fixtures"
    - "alembic/versions"
    - "frontend/dist"

category_weights:
  security_supply_chain: 0.25         # Security & Supply Chain (25%)
  code_health_test: 0.25              # Code Health & Test Coverage (25%)
  structural_health: 0.20             # Structural Health & Complexity (20%)
  resilience_performance: 0.15        # Resilience & Defensive Timeouts (15%)
  dev_hygiene_devops: 0.15            # Developer Hygiene & Vibe-Coding (15%)

thresholds:
  max_complexity: 12                  # Cyclomatic complexity ceiling
  max_duplication_percent: 3.0        # Max allowable code duplication (%)
  min_coverage: 80.0                  # Minimum target line test coverage (%)
  max_vibe_ratio: 0.15                # Max allowable AI-slop / didactic comment ratio
  max_hotspot_churn_ratio: 0.05       # Hotspot churn threshold for complex files

llm:
  provider: "gemini"                  # gemini | openai | anthropic | ollama
  models:
    - "gemini-2.5-pro"
    - "gemini-2.5-flash"
    - "gemini-2.0-flash"
  timeout_seconds: 45
  temperature: 0.1
  retry_count: 3
```

---

## 🔐 Environment Variables (`.env`)

| Variable | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `GEMINI_API_KEY` | String | - | API key for Google Gemini models (Layer 2 analysis). |
| `OPENAI_API_KEY` | String | - | API key when using OpenAI provider. |
| `ANTHROPIC_API_KEY`| String | - | API key for Claude models. |
| `DATABASE_URL` | String | `sqlite:///./warden.db` | SQLModel URI (`postgresql://user:pass@host:5432/warden`). |
| `REDIS_URL` | String | `redis://localhost:6379/0`| Distributed cache URL (falls back to memory). |
| `WARDEN_AUTH_ENABLED`| Bool | `false` | Enables JWT Bearer authorization on API endpoints. |
| `JWT_SECRET_KEY` | String | `dev-secret` | HS256 secret key for signing tokens. |
| `SLACK_WEBHOOK_URL`| String | - | Slack incoming webhook for audit notifications. |
| `DISCORD_WEBHOOK_URL`| String | - | Discord webhook for regression and audit alerts. |
| `WARDEN_SANDBOX` | Bool | `true` | Enables resource-limited sandbox during test coverage runs. |

---

## 🐙 CI/CD Quality Gates & Exit Codes

WARDEN integrates seamlessly into your CI/CD pipelines to block low-quality Pull Requests:

### Exit Codes
| Exit Code | Meaning | Pipeline Result |
| :---: | :--- | :--- |
| **`0`** | **Passed:** Quality threshold met, zero critical vulnerabilities. | ✅ Passed |
| **`1`** | **Below Threshold:** Overall score fell below `--min-score`. | ❌ Blocked |
| **`2`** | **Security Violation:** Critical CVE or secret leak found (`--fail-on-critical`). | ❌ Security Fail |
| **`3`** | **Execution Error:** Configuration or dependency runtime failure. | ⚠️ Error |

### GitHub Actions Workflow (`.github/workflows/warden-pr.yml`)
```yaml
name: WARDEN Quality Gate

on:
  pull_request:
    branches: [ main, master ]

jobs:
  warden:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for Git churn & diff analysis
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Dependencies
        run: |
          pip install uv && uv pip install --system -r requirements.txt
      - name: Audit & Enforce Quality Gate
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python core/main.py audit \
            --path . \
            --incremental \
            --since-commit origin/${{ github.base_ref }} \
            --min-score 75 \
            --fail-on-critical
```

---

## 🐳 Production Deployment (Docker & Terraform)

### Docker Compose
Run WARDEN API, Dashboard, PostgreSQL, and Redis with a single command:
```bash
docker-compose up -d --build
```
- Multi-stage build minimizing attack surface.
- Runs securely under an unprivileged `warden` non-root system user.
- Built-in container health check.

### AWS ECS Fargate & Terraform
```bash
cd terraform
terraform init
terraform apply -var="subnet_ids=[\"subnet-a\", \"subnet-b\"]"
```

---

## 🔬 Testing, Mutation & Reliability

WARDEN holds its own codebase to the highest software engineering standards:
- **870+ Unit, Integration & Property Tests** (100% passing rate across Python 3.11, 3.12, 3.13)
- **Zero Regressions & 100% Determinism** (Hypothesis-backed invariant testing)
- **Air-gapped, zero-network, deterministic test execution (< 90 seconds)**
- Quantitative detector validation with **100% Precision & Recall** on ground-truth benchmark suite

```bash
# Run test suite
uv run pytest tests/ -q

# Run detector benchmark suite
warden bench
```

---

## 📚 Documentation Index

- 🚀 [Getting Started Guide](docs/getting-started.md)
- 🏛️ [Architecture & 25+ Metric Scoring Model](docs/architecture-and-scoring.md)
- 🤖 [Vibe-Coding & AI-Slop Governance](docs/vibe-coding-governance.md)
- 🚦 [CI/CD Quality Gates & Automation](docs/ci-cd-quality-gates.md)
- ⚙️ [Configuration Reference Guide](docs/configuration-reference.md)
- 🌐 [REST API & Webhooks Integration](docs/api-and-webhooks.md)
- 🛡️ [Security Threat Model & STRIDE Analysis](docs/security/threat_model.md)

### 📜 Architecture Decision Records (ADRs)
- 📄 [ADR-001: Dual-Layer Mechanical & LLM Scoring Model](docs/adr/ADR-001-dual-layer-scoring.md)
- 📄 [ADR-002: Pluggable Analyzer Architecture via Protocol & EntryPoints](docs/adr/ADR-002-pluggable-analyzers.md)
- 📄 [ADR-003: Subprocess Sandboxing & Resource Limitation Strategy](docs/adr/ADR-003-subprocess-sandboxing.md)
- 📄 [ADR-004: Quality Gate Contract & Exit Code Specification](docs/adr/ADR-004-quality-gate-contract.md)

---

## 📄 License & Authors

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.  
Crafted with passion by **Tuncay Çelikkanat** and open-source contributors.

---

[ ⬆️ Back to Top / Başa Dön ](#-autonomous-code-audit-architectural-governance--vibe-coding-quality-engine)

---
---

<a id="-türkçe"></a>
# 🇹🇷 Türkçe

## 📑 İçindekiler
- [💡 Neden WARDEN?](#-neden-warden)
- [🏛️ İki Katmanlı Mimari](#-iki-katmanlı-mimari)
- [📊 Canlı Terminal Karnesi](#-canlı-terminal-karnesi)
- [🚀 Hızlı Başlangıç](#-hızlı-başlangıç)
- [💻 Kapsamlı CLI Kullanım Kılavuzu](#-kapsamlı-cli-kullanım-kılavuzu)
  - [1. Çekirdek Yaşam Döngüsü Komutları](#1-çekirdek-yaşam-döngüsü-komutları)
  - [2. Test ve Doğrulama Paketi](#2-test-ve-doğrulama-paketi)
  - [3. Güvenlik ve Tedarik Zinciri Paketi](#3-güvenlik-ve-tedarik-zinciri-paketi)
  - [4. Mimari Zeka ve Yapay Zeka Analitiği](#4-mimari-zeka-ve-yapay-zeka-analitiği)
- [🌐 Modern Web Kontrol Paneli ve REST API](#-modern-web-kontrol-paneli-ve-rest-api)
- [🤖 Model Context Protocol (MCP) Sunucusu ve Ajan Kalkanı](#-model-context-protocol-mcp-sunucusu-ve-ajan-kalkanı)
- [⚙️ Merkezi Yapılandırma (`warden.config.yaml`)](#-merkezi-yapılandırma-wardenconfigyaml)
- [🔐 Ortam Değişkenleri (`.env`)](#-ortam-değişkenleri-env)
- [🐙 CI/CD Kalite Kapıları ve Çıkış Kodları](#-cicd-kalite-kapıları-ve-çıkış-kodları)
- [🐳 Production Dağıtımı (Docker & Terraform)](#-production-dağıtımı-docker--terraform)
- [🔬 Test Gücü, Mutasyon ve Güvenilirlik](#-test-gücü-mutasyon-ve-güvenilirlik)
- [📚 Dokümantasyon Rehberleri](#-dokümantasyon-rehberleri)
- [📄 Lisans ve Emeği Geçenler](#-lisans-ve-emeği-geçenler)

---

## 💡 Neden WARDEN?

Yapay zeka kodlama asistanlarının (**Cursor**, **GitHub Copilot**, **ChatGPT**, **Claude**) yazılım dünyasını hızlandırdığı bu yeni çağda, geliştiriciler mimari detaylardan uzaklaşarak **"Vibe Coding"** tarzına yönelmektedir. Bu hız muazzam bir üretkenlik getirse de, arkasında görünmez ve sinsi yazılım riskleri bırakır:

- ❌ **Yutulan Hatalar (Swallowed Exceptions):** Kodun çalışıyor gibi görünmesi için eklenen ve sessizce hataları yutan `except Exception: pass` blokları.
- ❌ **Didaktik AI Yorum Kirliliği (AI Slop):** Bariz işlemleri anlatan gereksiz eğitici yorumlar ve dosyalarda unutulan chat/markdown artıkları (```python, ```json).
- ❌ **Zaman Aşımı (Timeout) Eksikliği:** Ağ (`requests.get`, `httpx.post`) veya veritabanı kilitlendiğinde tüm sunucuyu asılı bırakan parametresiz çağrılar.
- ❌ **Pini Çözülmüş / Zehirli Bağımlılıklar:** Belirsiz sürüm numaraları veya typosquatting tuzaklarına düşen sahte paketler (`reqeusts`, `colorma`).
- ❌ **Gizli Anahtar Sızıntıları:** Git geçmişine veya test dosyalarına dikkatsizce gömülen gerçek API anahtarları, token'lar ve parolalar.
- ❌ **Halüsinasyon Kayması (Churn × Karmaşıklık Hotspot'ları):** Sürekli yapay zekaya baştan yazdırılan ve döngüsel karmaşıklığı tavan yapmış patlamaya hazır dosyalar.

**WARDEN**, bu yeni nesil yazılım risklerini ortadan kaldırmak için geliştirilmiş; **deterministik mekanik ölçümler ile LLM tabanlı semantik muhakemeyi birleştiren iki katmanlı otonom bir kalite güvence (QA), güvenlik ve mimari denetim motorudur.**

---

## 🏛️ İki Katmanlı Mimari

WARDEN, yalnızca statik analiz kurallarıyla sınırlı kalmaz; yapay zekanın ürettiği mimari kararları da somut kanıtlarla doğrular:

```mermaid
flowchart TD
    subgraph Arayuzler["Giriş & Arayüzler"]
        CLI["CLI: warden audit / bench"]
        API["FastAPI Web Kontrol Paneli & REST API"]
        MCP["MCP Sunucusu: Ajan Kalkanı"]
        GH["GitHub Actions & PR İnceleme Botu"]
    end

    subgraph Cekirdek["Çekirdek Orkestrasyon & Eklenebilirlik"]
        Dispatcher["CLI Dispatcher & API Fabrikası"]
        Registry["Eklenebilir Analizör Kayıtçısı<br/>(entry_points: 'warden.analyzers')"]
        Gate["Kalite Kapısı Motoru<br/>(ExitCode 0 / 1 / 2 / 3)"]
    end

    subgraph Katman1["Katman 1: Deterministik Statik Analiz (%60)"]
        Sec["Güvenlik & Entropi<br/>(Semgrep, Gitleaks, Shannon Entropisi)"]
        Res["Dayanıklılık AST<br/>(Zaman Aşımları, Bare Except'ler)"]
        Health["Kod Sağlığı & Tipler<br/>(Kapsam, Mypy, Ruff, Radon CC)"]
        Vibe["Vibe Hijyeni<br/>(AI-Slop Sınıflandırıcısı, Churn Risk)"]
    end

    subgraph Katman2["Katman 2: Semantik LLM Rubrikleri (%40 - Opsiyonel)"]
        Collectors["7 Dinamik Kanıt Toplayıcı Modül<br/>(API, Mimari, Eşzamanlılık, DevOps)"]
        LLM["Çoklu LLM Paneli<br/>(Gemini, Claude, OpenAI, Ollama)"]
    end

    subgraph Cikti["Konsolide Çıktı"]
        Scorecard["Hiyerarşik Karne Hesaplayıcı"]
        Raporlar["Raporlar: Terminal, JSON, SARIF, Markdown, PDF"]
    end

    CLI --> Dispatcher
    API --> Dispatcher
    MCP --> Dispatcher
    GH --> Dispatcher

    Dispatcher --> Registry
    Registry --> Katman1
    Registry --> Katman2

    Katman1 --> Scorecard
    Katman2 --> Scorecard
    Scorecard --> Gate
    Scorecard --> Cikti
```

### 1. Katman 1: 16 Deterministik Mekanik Analizör (%60 Ağırlık)
5 temel grupta toplanır:
1. **🛡️ Güvenlik ve Tedarik Zinciri (%25):** Semgrep SAST (OWASP Top 10, SQLi, XSS), Gitleaks gizli anahtar tespiti, Google OSV güvenlik açığı veri tabanı taraması, lisans uyumluluğu.
2. **🧪 Kod Sağlığı ve Test (%25):** İzole edilmiş test kapsamı (`coverage.py`), AST assertion yoğunluğu (sahte/boş testleri eler), Mypy statik tip denetimi, Interrogate docstring oranı.
3. **📐 Yapısal Sağlık ve Karmaşıklık (%20):** Radon McCabe Döngüsel Karmaşıklığı (CC), JSCPD kod tekrarı (DRY), Halstead Bakım İndeksi.
4. **⚡ Dayanıklılık ve Performans (%15):** Zaman aşımı (timeout) olmayan HTTP/DB istekleri, bare except blokları (`except:`), Dockerfile multi-stage / non-root kontrolleri.
5. **🤖 Geliştirici Hijyeni ve Vibe-Coding (%15):** Heuristic NLP & Regex ile AI yorumları, prompt sızıntıları, Git Conventional Commit hijyeni ve Churn × Karmaşıklık risk haritası.

### 2. Katman 2: LLM Destekli Dinamik Semantik Rubrik (%40 Ağırlık)
Katman 2, yapay zekayı yüzeysel yönlendirmelerle değil; **7 bağımsız kanıt toplayıcı modül** aracılığıyla toplanan somut kod parçacıklarıyla besler:
- **API Toplayıcısı:** FastAPI/Flask rota mimarisi, şema doğrulama, HTTP durum kodları, auth dekoratörleri.
- **Mimari Toplayıcısı:** Katmanlı mimari sınırları, soyutlama sızıntıları, döngüsel bağımlılıklar.
- **Eşzamanlılık Toplayıcısı:** Thread havuzları, async/await güvenliği, lock mekanizmaları, race condition savunmaları.
- **DevOps Toplayıcısı:** CI/CD iş akışları, Docker yapıları, Terraform IaC, ortam değişkeni hijyeni.
- **Frontend Toplayıcısı:** Durum yönetimi, bileşen yaşam döngüsü, ARIA erişilebilirliği.
- **LLM Toplayıcısı:** Prompt sanitizasyonu, structured output denetimi, hata yedekleme mekanizmaları.
- **Sayısal Toplayıcı:** Katman 1'in ürettiği metrikleri LLM'in bağlamsal yorumlaması için harmanlar.

> [!TIP]
> **Zarafetle Derece Düşürme (Graceful Degradation):** Eğer `GEMINI_API_KEY` tanımlanmamışsa, sistem hata verip durmaz. Katman 2'nin %40'lık ağırlığı doğrudan Katman 1'e devredilir (%60 → %100) ve denetim sıfır harici bağımlılıkla tamamlanır.

---

## 📊 Canlı Terminal Karnesi

`warden audit --path . --min-score 75` komutu koşturulduğunda WARDEN'in ürettiği konsol karnesi:

```text
================================================================================
🛡️  WARDEN — Otonom Kod Denetimi ve Kalite Güvence Karnesi
================================================================================
📂 Hedef: /home/tuncay/PycharmProjects/warden  |  ⏱️ Süre: 14.2s
🔍 16 Katman-1 Analizörü ve Dinamik Kanıt Toplayıcılar Tamamlandı

┌───────────────────────────────────────┬──────────┬─────────────┬──────────────┐
│ Denetim Grubu                         │ Ağırlık  │ Puan (/100) │ Durum        │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ 🛡️ Güvenlik & Tedarik Zinciri          │   %25    │     97.9    │ 🟢 Mükemmel  │
│ 🧪 Kod Sağlığı & Test Kapsamı         │   %25    │     99.9    │ 🟢 Mükemmel  │
│ 📐 Yapısal Sağlık & Karmaşıklık       │   %20    │     86.9    │ 🟢 Başarılı  │
│ ⚡ Dayanıklılık & Performans          │   %15    │    100.0    │ 🟢 Mükemmel  │
│ 🤖 Geliştirici Hijyeni & Vibe-Coding  │   %15    │     96.6    │ 🟢 Mükemmel  │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ Katman 1 (Deterministik Statik Skor)  │  %100    │     97.0    │ 🟢 Mükemmel  │
│ Katman 2 (LLM Semantik Rubrik)        │   Yok    │  Degraded   │ ⚪ Sıfır-Bağ │
└───────────────────────────────────────┴──────────┴─────────────┴──────────────┘

🏆 GENEL WARDEN SKORU: 97/100 (A+ — Olağanüstü Başarı)
• Kalite Kapısı: ✅ GEÇTİ (Baraj Eşiği: 75.0, Kritik Zafiyet: 0)
• Markdown Rapor: warden_reports/warden_report_*.md (ve .pdf / .sarif)
================================================================================
```

---

## 🎯 Ampirik Benchmark ve Tespit Doğruluğu

Soyut iddialar yerine WARDEN'ın statik hata ve vibe-coding detektörleri, gerçek dünya pozitif ve negatif örneklerini içeren etiketli bir benchmark veriseti ([`benchmarks/dataset.py`](benchmarks/dataset.py)) üzerinde niceliksel olarak doğrulanmaktadır.

Benchmark paketini istediğiniz an çalıştırabilirsiniz:
```bash
warden bench
# veya CI için JSON formatında
warden benchmark --json
```

### Niceliksel Detektör Başarımı (v0.1.0 Benchmark Paketi)

| Detektör / Kategori | Örnek | Doğru Pozitif | Yanlış Pozitif | Doğru Negatif | Yanlış Negatif | Kesinlik (P) | Duyarlılık (R) | F1-Skoru | Doğruluk |
|:--------------------|:-----:|:-------------:|:--------------:|:-------------:|:--------------:|:------------:|:--------------:|:--------:|:--------:|
| `ai_slop`           | 7     | 4             | 0              | 3             | 0              | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|
| `bare_except`       | 5     | 2             | 0              | 3             | 0              | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|
| `missing_timeout`   | 7     | 4             | 0              | 3             | 0              | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|
| `secret_entropy`    | 7     | 3             | 0              | 4             | 0              | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|
| `silent_swallow`    | 6     | 3             | 0              | 3             | 0              | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|
| **GENEL (Makro)**   | **32**| **16**        | **0**          | **16**        | **0**          | **%100.0**   | **%100.0**     | **1.000**| **%100.0**|

> [!NOTE]
> **Skor Determinizm Güvencesi:** WARDEN, aynı git commit ağacında tekrarlanan Katman 1 denetimlerinde **0 sapma** garantisi verir. Her denetim bit-seviyesinde idempotenttir ve Hypothesis tabanlı property testleriyle ([`tests/test_determinism.py`](tests/test_determinism.py)) doğrulanır.

---

## 🚦 CI/CD Kalite Kapısı ve Çıkış Kodları Sözleşmesi

GitHub Actions, GitLab CI veya pre-commit hook entegrasyonlarında WARDEN öngörülebilir bir çıkış kodu sözleşmesi sunar:

| Çıkış Kodu | Sabit | Anlamı | CI Karşılığı |
|:----------:|:------|:-------|:-------------|
| `0` | `PASSED` | Denetim tüm eşikleri geçti; engelleyici güvenlik sorunu yok. | ✅ Derleme onaylandı |
| `1` | `BELOW_THRESHOLD` | Genel skor minimum eşiğin (`--min-score <N>`) altında kaldı. | ⚠️ Kalite kapısı uyarısı |
| `2` | `SECURITY_VIOLATION` | `--fail-on-critical` altında secret sızıntısı veya kritik SAST hatası bulundu. | 🚨 Güvenlik engeli |
| `3` | `EXECUTION_ERROR` | Geçersiz yol veya eksik araç gibi çalışma zamanı hatası oluştu. | ❌ Altyapı hatası |

`--format json` flag'i ile insan logları `stderr`'e yönlendirilir, `stdout` saf JSON olarak kalır:
```bash
warden audit --format json --min-score 85 | jq .scorecard.total_score
```

---

## 🚀 Hızlı Başlangıç

### ⚡ PyPI Üzerinden Anında Kurulum
```bash
pip install warden-audit

# veya uv ile
uv tool install warden-audit
```

### 1. Kaynak Koddan Otomatik Kurulum (Linux & macOS)
```bash
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden
chmod +x install.sh
./install.sh
```

### 2. Manuel Kurulum (`uv` ile)
```bash
# 1. Depoyu klonlayın
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden

# 2. Sanal ortamı açıp aktif edin
uv venv
source .venv/bin/activate  # Windows için: .venv\Scripts\activate

# 3. Bağımlılıkları yükleyin
uv pip install -r requirements.txt

# 4. Ortam dosyasını oluşturun
cp .env.example .env
```

### 3. API Anahtarınızı Ekleyin (Katman 2 için opsiyonel)
```bash
echo 'GEMINI_API_KEY="AIzaSyYourGeminiApiKeyHere"' >> .env
```

### 4. İlk Denetiminizi Koşturun
```bash
# Geçerli repoyu denetle
uv run python core/main.py audit --path .

# Yalnızca değişen dosyaları 3 saniyede denetle (Artımlı denetim)
uv run python core/main.py audit --path . --incremental

# CI/CD için minimum skor barajı koy
uv run python core/main.py audit --path . --min-score 80 --fail-on-critical
```

---

## 💻 Kapsamlı CLI Kullanım Kılavuzu

WARDEN, 4 ana alana ayrılmış 20'den fazla gelişmiş CLI komutuna sahiptir:

### 1. Çekirdek Yaşam Döngüsü Komutları

| Komut | Parametreler & Flag'ler | Açıklama |
| :--- | :--- | :--- |
| `audit` | `[target] [--path <p>] [--min-score <s>] [--incremental] [--since-commit <c>] [--full-history]` | Tam denetim koşturur, kalite kapısını doğrular ve rapor üretir. |
| `serve` | `[--host 0.0.0.0] [--port 8000] [--reload]` | FastAPI REST API, Swagger UI (`/docs`) ve dashboard sunucusunu başlatır. |
| `watch` | `[target] [--min-score <s>] [--debounce 0.8]` | Dosya kayıtlarını gerçek zamanlı izler; her kayıtta anlık skor deltası ve karne basar. |
| `badge` | `[--score <s>] [--grade <g>] [--label <l>] [-o <dosya>]` | README için shields.io uyumlu vektörel SVG skor rozeti üretir. |
| `milestone`| `<audit_id> [--label <text>] [--clear]` | Bir raporu veritabanında referans taban çizgisi (baseline) olarak etiketler. |
| `metrics` | `[--json]` | Prometheus OpenMetrics formatında veya JSON operasyonel metrik basar. |
| `hook` | `install\|uninstall\|run [--hook-type pre-commit\|pre-push\|all] [--min-score 80]` | Git kancalarını yönetir, hatalı commit veya push'ları yerel ortamda engeller. |

```bash
# Kod yazarken anlık canlı denetim ve regresyon izleyici
warden watch . --min-score 80

# README için dinamik vektörel SVG rozeti oluştur
warden badge --score 95 --grade A+ -o warden-score.svg

# #42 numaralı denetimi v1.0.0 kilometre taşı olarak işaretle
warden milestone 42 --label "v1.0.0-release"

# Pre-commit ve pre-push Git hook kancalarını kur
warden hook install --hook-type all --min-score 80
```

---

### 2. Test ve Doğrulama Paketi

| Komut | Parametreler & Flag'ler | Açıklama |
| :--- | :--- | :--- |
| `generate-property-tests` | `[target] [--output <dosya>] [--max-tests 15]` | Python AST'sini inceleyerek Hypothesis tabanlı property test şablonları üretir. |
| `mutate` | `[target] [--test-path <p>] [--max-mutants 15] [--timeout 8.0] [--dry-run] [--output <f>]` | AST Mutasyon Testi koşturarak test paketinin mutant öldürme skorunu hesaplar. |
| `bdd` | `[target] [--feature-dir <d>] [--output <f>] [--enrich-llm] [--provider gemini]` | Testlerden Given-When-Then BDD Gherkin senaryoları ve katalog üretir. |

```bash
# Servisler için property test taslağı sentezle
warden generate-property-tests core/services/ --output tests/test_properties_gen.py

# Mutasyon testini dry-run modunda haritalandır
warden mutate core/services/evidence/ --dry-run
```

---

### 3. Güvenlik ve Tedarik Zinciri Paketi

| Komut | Parametreler & Flag'ler | Açıklama |
| :--- | :--- | :--- |
| `generate-sbom` | `[target] [--output <dosya>]` | Tedarik zinciri güvenliği için CycloneDX v1.5 JSON SBOM manifestosu üretir. |
| `scan-entropy` | `[target] [--max-findings 25]` | Shannon entropi algoritması ile kodda unutulan gizli API anahtarlarını tespit eder. |
| `check-attack-surface` | `[target] [--top 10]` | NetworkX ile bağımlılık grafını kurup PageRank kritikliği ve tahribat yarıçapını (blast radius) hesaplar. |
| `check-typosquatting` | `<package_name>` | Aday paket adını PyPI popüler kütüphanelerine karşı typosquatting saldırılarına karşı test eder. |

```bash
# CycloneDX SBOM çıktısı al
warden generate-sbom . --output sbom.json

# Yüksek entropili sırları tara
warden scan-entropy . --max-findings 10

# Şüpheli bir paketi incele
warden check-typosquatting reqeusts-security-patch
```

---

### 4. Mimari Zeka ve Yapay Zeka Analitiği

| Komut | Parametreler & Flag'ler | Açıklama |
| :--- | :--- | :--- |
| `check-cycles` | `[target]` | NetworkX AST DAG analiziyle döngüsel import (circular import) hatalarını yakalar. |
| `check-ck` | `[target] [--top 15] [--smells-only] [--output <f>]` | Chidamber & Kemerer (CK) nesne yönelimli mimari metriklerini (WMC, DIT, CBO, RFC, LCOM4) hesaplar. |
| `export-sarif` | `[target] [--output warden.sarif] [--audit-id <id>]` | GitHub Code Scanning için OASIS SARIF v2.1.0 standardında rapor üretir. |
| `export-pdf` | `[target] [--output rapor.pdf] [--audit-id <id>]` | Renkli rozetler ve tablolar içeren Kurumsal Executive Summary PDF raporu basar. |
| `query` | `"<doğal_dil_sorusu>" [--json] [--provider gemini]` | Doğal dil ile veritabanını sorgulayan Text-to-SQL analitik motoru. |
| `classify` | `[target] [--weights] [--override key=val]` | Proje arketipini analiz eder ve dinamik kalite ağırlıklarını yapılandırır. |
| `forecast` | `[target] [--horizon 5] [--dimension total\|all]` | Holt's Exponential Smoothing ile gelecek kod kalitesi ve teknik borç trendini tahminler. |
| `anomaly` | `[target] [--audit-id <id>] [--method hybrid\|mahalanobis]` | Mahalanobis mesafesi ve Autoencoder ile kalite skorlarındaki anomalileri ve kök nedenleri saptar. |
| `pr-review` | `[target] [--pr 1] [--owner org] [--repo repo] [--post]` | GitHub PR İnceleme Botu: PR diff'ini denetler, özet yorum ve satır içi inline notlar bırakır. |

```bash
# Döngüsel bağımlılıkları denetle
warden check-cycles .

# God Class ve Brain Class gibi mimari kokuları tara
warden check-ck core/ --smells-only

# Doğal dilde soru sorarak geçmiş denetimleri incele
warden query "Son 30 günde skoru 80'in altında kalan repolar hangileri?"
```

---

## 🌐 Modern Web Kontrol Paneli ve REST API

WARDEN, karanlık temalı modern bir Single-Page Application (SPA) arayüzü ve FastAPI RESTful API ile birlikte gelir:

```bash
uv run python core/main.py serve --host 0.0.0.0 --port 8000 --reload
```

- 📊 **Web Dashboard:** [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/)
- 📖 **Etkileşimli Swagger Belgeleri:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 📈 **Prometheus Metrikleri:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- 💓 **Sağlık Kontrolü:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Dashboard Yetenekleri:
- 🎯 **KPI Kartları:** Anlık skor, harf notu, bulunan kritik açıklar ve test kapsamı.
- 🕸️ **5 Boyutlu Radar Analizi:** Güvenlik, Test, Yapısal Sağlık, DevOps ve Dayanıklılık dengesi.
- 📈 **Zaman Serisi Skor Eğrisi:** Commit bazında kalite trendi ve regresyon alarmları.
- ⚖️ **A/B Karşılaştırma:** İki denetim veya dal arasındaki delta puanlarını yan yana inceleme.
- 📢 **Slack & Discord Webhook'ları:** Skor 5 puandan fazla düştüğünde veya kritik açık bulunduğunda anında bildirim.

---

## 🤖 Model Context Protocol (MCP) Sunucusu ve Ajan Kalkanı

WARDEN, Anthropic tarafından duyurulan **Model Context Protocol (MCP)** standardını destekler (`mcp_server/server.py`). **Cursor**, **Claude Desktop** veya **Antigravity** gibi yapay zeka araçları WARDEN yeteneklerini doğrudan araç olarak çağırabilir:

```json
{
  "mcpServers": {
    "warden": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/warden"
    }
  }
}
```

### Desteklenen MCP Araçları:
- `security_scan(file_path)`: İlgili dosyayı WARDEN Semgrep kurallarıyla tarar.
- `check_package(package_name)`: PyPI paketlerini typosquatting ve güvenlik risklerine karşı analiz eder.
- `evaluate_agent_action(command)`: **Ajan Kalkanı:** AI ajanının terminalde çalıştırmak istediği tehlikeli kabuk komutlarını (`rm -rf /`, curl bash çalıştırma, `.env` silme) engeller.
- `check_cycles(directory)`: Modüller arası dairesel bağımlılıkları denetler.
- `scan_entropy(file_path)`: Dosyadaki şüpheli token ve anahtarları commit öncesi yakalar.

---

## ⚙️ Merkezi Yapılandırma (`warden.config.yaml`)

Projenizin kurallarını kök dizindeki `warden.config.yaml` dosyasından özelleştirebilirsiniz:

```yaml
# ==============================================================================
# 🛡️ WARDEN — Merkezi Yönetişim Yapılandırması
# ==============================================================================

general:
  project_name: "Kurumsal Proje"
  threshold_score: 75.0               # Kalite kapısı geçme barajı (0 - 100)
  fail_on_critical_vulns: true        # Kritik CVE veya sızıntıda skordan bağımsız doğrudan fail et
  ignore_paths:
    - "tests/fixtures"
    - "alembic/versions"
    - "frontend/dist"

category_weights:
  security_supply_chain: 0.25         # Güvenlik ve Tedarik Zinciri (%25)
  code_health_test: 0.25              # Kod Sağlığı ve Test Kapsamı (%25)
  structural_health: 0.20             # Yapısal Sağlık & Karmaşıklık (%20)
  resilience_performance: 0.15        # Dayanıklılık & Timeout Disiplini (%15)
  dev_hygiene_devops: 0.15            # Geliştirici Hijyeni & Vibe-Coding (%15)

thresholds:
  max_complexity: 12                  # Kabul edilebilir döngüsel karmaşıklık üst sınırı
  max_duplication_percent: 3.0        # İzin verilen maksimum kod tekrarı (%)
  min_coverage: 80.0                  # Hedeflenen minimum test satır kapsamı (%)
  max_vibe_ratio: 0.15                # Kabul edilebilir maksimum didaktik yorum oranı
  max_hotspot_churn_ratio: 0.05       # Karmaşık dosyalarda riskli commit sıklığı eşiği

llm:
  provider: "gemini"                  # gemini | openai | anthropic | ollama
  models:
    - "gemini-2.5-pro"
    - "gemini-2.5-flash"
    - "gemini-2.0-flash"
  timeout_seconds: 45
  temperature: 0.1
  retry_count: 3
```

---

## 🔐 Ortam Değişkenleri (`.env`)

| Değişken Adı | Tip | Varsayılan | Açıklama |
| :--- | :---: | :---: | :--- |
| `GEMINI_API_KEY` | String | - | Google Gemini modelleri için API anahtarı (Katman 2). |
| `OPENAI_API_KEY` | String | - | OpenAI sağlayıcısı kullanılacaksa API anahtarı. |
| `ANTHROPIC_API_KEY`| String | - | Claude modelleri için API anahtarı. |
| `DATABASE_URL` | String | `sqlite:///./warden.db` | SQLModel veritabanı URI (`postgresql://user:pass@host/db`). |
| `REDIS_URL` | String | `redis://localhost:6379/0`| Dağıtık önbellek URI (Yoksa bellek içi önbellek kullanılır). |
| `WARDEN_AUTH_ENABLED`| Bool | `false` | API uç noktalarında JWT kimlik doğrulamasını aktif eder. |
| `JWT_SECRET_KEY` | String | `dev-secret` | JWT token imzalamak için HS256 gizli anahtarı. |
| `SLACK_WEBHOOK_URL`| String | - | Denetim sonuçlarının gönderileceği Slack Incoming Webhook. |
| `DISCORD_WEBHOOK_URL`| String | - | Denetim sonuçlarının gönderileceği Discord Webhook. |
| `WARDEN_SANDBOX` | Bool | `true` | Test koşumlarında OS kaynak limitlerini ve izolasyonu aktif eder. |

---

## 🐙 CI/CD Kalite Kapıları ve Çıkış Kodları

### Çıkış Kodları (Exit Codes)
| Çıkış Kodu | Anlamı | CI Pipeline Davranışı |
| :---: | :--- | :--- |
| **`0`** | **Başarılı:** Kalite kapısı barajı aşıldı, kritik açık yok. | ✅ Geçti (Passed) |
| **`1`** | **Baraj Altı:** Toplam skor `--min-score` eşiğinin altında kaldı. | ❌ Engellendi (Blocked) |
| **`2`** | **Kritik Güvenlik Açığı:** Puan yeterli olsa bile kritik CVE veya sızıntı bulundu (`--fail-on-critical`). | ❌ Güvenlik Hatası (Security Fail) |
| **`3`** | **Yürütme Hatası:** Geçersiz hedef dizin veya sistem hatası. | ⚠️ Sistem Hatası (Error) |

### GitHub Actions İş Akışı (`.github/workflows/warden-pr.yml`)
```yaml
name: WARDEN Quality Gate

on:
  pull_request:
    branches: [ main, master ]

jobs:
  warden:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Git geçmişi ve diff analizi için zorunlu
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Bağımlılıkları Yükle
        run: |
          pip install uv && uv pip install --system -r requirements.txt
      - name: Denetim ve Kalite Kapısı
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python core/main.py audit \
            --path . \
            --incremental \
            --since-commit origin/${{ github.base_ref }} \
            --min-score 75 \
            --fail-on-critical
```

---

## 🐳 Production Dağıtımı (Docker & Terraform)

### Docker Compose
```bash
docker-compose up -d --build
```
- Multi-stage build ile hafif ve güvenli imaj.
- Yetkisiz (non-root) `warden` sistem kullanıcısı ile çalışır.
- Otomatik PostgreSQL & Redis bağlantı havuzu ve liveness probe.

### AWS ECS Fargate & Terraform
```bash
cd terraform
terraform init
terraform apply -var="subnet_ids=[\"subnet-a\", \"subnet-b\"]"
```

---

## 🔬 Test Gücü, Mutasyon ve Güvenilirlik

WARDEN kod tabanı en katı test disipliniyle korunmaktadır:
- **870+ Birim, Entegrasyon & Property Testi** (Python 3.11, 3.12, 3.13 üzerinde %100 Başarılı)
- **Sıfır Regresyon ve %100 Determinizm** (Hypothesis tabanlı invaryant doğrulaması)
- Ağ çağrılarından ve flaky gecikmelerden arındırılmış, deterministik test yürütme (< 90 saniye).
- Ground-truth benchmark verisetinde **%100 Kesinlik (Precision) ve %100 Duyarlılık (Recall)** başarımı.

```bash
# Testleri koşturmak için:
uv run pytest tests/ -q

# Detektör benchmark paketini çalıştırmak için:
warden bench
```

---

## 📚 Dokümantasyon Rehberleri

- 🚀 [Hızlı Başlangıç Kılavuzu](docs/getting-started.md)
- 🏛️ [Mimari ve 25+ Metrik Skorlama Modeli](docs/architecture-and-scoring.md)
- 🤖 [Vibe-Coding ve AI-Slop Yönetişimi](docs/vibe-coding-governance.md)
- 🚦 [CI/CD Kalite Kapıları ve Otomasyon](docs/ci-cd-quality-gates.md)
- ⚙️ [Merkezi Yapılandırma Referansı](docs/configuration-reference.md)
- 🌐 [REST API ve Webhook Entegrasyonları](docs/api-and-webhooks.md)
- 🛡️ [Güvenlik Tehdit Modeli ve STRIDE Analizi](docs/security/threat_model.md)

### 📜 Mimari Karar Kayıtları (ADR'lar)
- 📄 [ADR-001: İki Katmanlı Mekanik ve LLM Skorlama Modeli](docs/adr/ADR-001-dual-layer-scoring.md)
- 📄 [ADR-002: Protokol ve EntryPoints ile Eklenebilir Analizör Mimarisi](docs/adr/ADR-002-pluggable-analyzers.md)
- 📄 [ADR-003: Alt İşlem Kum Havuzu ve Kaynak Sınırlandırma Stratejisi](docs/adr/ADR-003-subprocess-sandboxing.md)
- 📄 [ADR-004: Kalite Kapısı Sözleşmesi ve Süreç Çıkış Kodları](docs/adr/ADR-004-quality-gate-contract.md)

---

## 📄 Lisans ve Emeği Geçenler

Bu proje **MIT Lisansı** altında lisanslanmıştır. Detaylı bilgi için [LICENSE](LICENSE) dosyasına göz atabilirsiniz.  
**Tuncay Çelikkanat** ve açık kaynak topluluğu tarafından tutkuyla geliştirilmiştir.

---

[ ⬆️ Başa Dön / Back to Top ](#-autonomous-code-audit-architectural-governance--vibe-coding-quality-engine)
