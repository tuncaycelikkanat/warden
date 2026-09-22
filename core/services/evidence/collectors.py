"""Specialized evidence collectors for Layer 2 dynamic categories."""

import re
from pathlib import Path
from typing import Any

from core.services.evidence.base import extract_snippet, safe_read_file
from core.services.rubric import CodeSnippet


def collect_llm_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for LLM integration, prompt defense, and resilience."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    llm_providers: set[str] = set()
    has_sanitization = False
    has_resilience = False
    has_cost_latency = False

    provider_pattern = re.compile(
        r"\b(google\.genai|genai\.Client|openai|Anthropic|langchain|llama_index|litellm|transformers)\b",
        re.IGNORECASE,
    )
    sanitizer_pattern = re.compile(
        r"\b(PromptSanitizer|sanitize.*prompt|injection.*defense|guardrails|nemo_guardrails|promptfoo)\b",
        re.IGNORECASE,
    )
    resilience_pattern = re.compile(
        r"\b(models_to_try|fallback|retry|tenacity|Backoff)\b",
        re.IGNORECASE,
    )
    tracking_pattern = re.compile(
        r"\b(total_tokens|prompt_tokens|usage_metadata|latency_sec|audit_log)\b",
        re.IGNORECASE,
    )

    for f in files:
        rel = str(f.relative_to(path))
        content = safe_read_file(f)
        if not content:
            continue

        matches = provider_pattern.findall(content)
        if matches:
            matched_files.append(rel)
            for m in matches:
                llm_providers.add(m)

        if sanitizer_pattern.search(content):
            has_sanitization = True
            matched_files.append(rel)
            if not any(s.context == "LLM Prompt Sanitization / Guardrail" for s in snippets):
                snip = extract_snippet(
                    rel, content, sanitizer_pattern, "LLM Prompt Sanitization / Guardrail"
                )
                if snip:
                    snippets.append(snip)

        if resilience_pattern.search(content) and (
            matches or any(k in rel.lower() for k in ["llm", "rubric", "ai", "model"])
        ):
            has_resilience = True
            matched_files.append(rel)

        if tracking_pattern.search(content) and (
            matches or any(k in rel.lower() for k in ["llm", "rubric", "ai", "model"])
        ):
            has_cost_latency = True
            matched_files.append(rel)

        if len(snippets) == 0 and matches:
            snip = extract_snippet(rel, content, provider_pattern, "LLM Client invocation")
            if snip:
                snippets.append(snip)

    if llm_providers:
        findings.append(
            f"LLM Providers: Detected SDK integrations ({', '.join(sorted(llm_providers))}) in {len(matched_files)} files"
        )
    if has_sanitization:
        findings.append("LLM Security: Prompt sanitization, input filtering, or guardrail mechanisms detected")
    elif llm_providers:
        findings.append("LLM Security: No dedicated prompt sanitization or injection guardrails observed")

    if has_resilience:
        findings.append("LLM Resilience: Multi-model fallback, retry loops, or backoff error handling detected")
    if has_cost_latency:
        findings.append("LLM Observability: Token usage metrics, latency tracking, or structured LLM audit logging detected")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_concurrency_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for concurrency safety, async loops, and locks."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    concurrency_primitives: set[str] = set()
    sync_mechanisms: set[str] = set()

    gather_pattern = re.compile(
        r"\b(asyncio\.gather|asyncio\.create_task|TaskGroup|ThreadPoolExecutor|ProcessPoolExecutor)\b"
    )
    sync_pattern = re.compile(
        r"\b(asyncio\.Lock|threading\.Lock|RLock|Semaphore|Queue|asyncio\.Queue)\b"
    )

    for f in files:
        rel = str(f.relative_to(path))
        content = safe_read_file(f)
        if not content:
            continue

        prims = gather_pattern.findall(content)
        syncs = sync_pattern.findall(content)

        if prims or syncs or "async def " in content:
            matched_files.append(rel)
            for p in prims:
                concurrency_primitives.add(p)
            for s in syncs:
                sync_mechanisms.add(s)

            if len(snippets) == 0 and prims:
                snip = extract_snippet(rel, content, gather_pattern, "Concurrency coordination primitive")
                if snip:
                    snippets.append(snip)
            elif len(snippets) < 2 and syncs:
                snip = extract_snippet(rel, content, sync_pattern, "Concurrency synchronization lock/queue")
                if snip:
                    snippets.append(snip)

    if concurrency_primitives:
        findings.append(
            f"Concurrency Primitives: Detected async/parallel execution ({', '.join(sorted(concurrency_primitives))}) across {len(matched_files)} files"
        )
    elif matched_files:
        findings.append(f"Asynchronous Execution: Asynchronous coroutines (async def) present across {len(matched_files)} files")

    if sync_mechanisms:
        findings.append(f"Synchronization Safety: Thread/task synchronization primitives detected ({', '.join(sorted(sync_mechanisms))})")
    elif concurrency_primitives:
        findings.append("Synchronization Safety: Zero explicit locks or synchronization primitives detected (verify shared state isolation)")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_api_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for API design, routes, schema validation, and error handling."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    frameworks: set[str] = set()
    has_schemas = False
    has_typed_exceptions = False
    has_auth_or_ratelimit = False

    route_pattern = re.compile(
        r"(@\w+\.(get|post|put|delete|patch|options|head)|urlpatterns\s*=|@api_view|app\.(get|post|put|delete)\()",
        re.IGNORECASE,
    )
    schema_pattern = re.compile(r"(class\s+\w+\(.*(?:BaseModel|Schema).*\):|@dataclass)", re.IGNORECASE)
    exc_pattern = re.compile(r"(raise\s+HTTPException|status_code\s*=|status\.HTTP_)", re.IGNORECASE)
    sec_pattern = re.compile(r"\b(Depends|HTTPBearer|OAuth2|rate_limit|Limiter|slowapi)\b", re.IGNORECASE)

    for f in files:
        rel = str(f.relative_to(path))
        if not any(
            k in rel.lower()
            for k in ["api", "router", "endpoint", "controller", "view", "server", "main", "app", "schema", "route"]
        ):
            continue

        content = safe_read_file(f)
        if not content:
            continue

        file_has_api = False
        if "fastapi" in content.lower() or "apirouter" in content.lower():
            frameworks.add("FastAPI")
            file_has_api = True
        elif "flask" in content.lower() or "blueprint" in content.lower():
            frameworks.add("Flask")
            file_has_api = True
        elif "django" in content.lower() or "rest_framework" in content.lower():
            frameworks.add("Django REST")
            file_has_api = True
        elif "express" in content.lower():
            frameworks.add("Express")
            file_has_api = True

        if route_pattern.search(content):
            file_has_api = True

        if schema_pattern.search(content):
            has_schemas = True
            file_has_api = True

        if exc_pattern.search(content):
            has_typed_exceptions = True
            file_has_api = True

        if sec_pattern.search(content):
            has_auth_or_ratelimit = True
            file_has_api = True

        if file_has_api:
            matched_files.append(rel)
            if len(snippets) == 0 and route_pattern.search(content):
                snip = extract_snippet(rel, content, route_pattern, "API route endpoint declaration")
                if snip:
                    snippets.append(snip)

    if frameworks:
        findings.append(
            f"API Framework: {', '.join(sorted(frameworks))} routing detected across {len(matched_files)} files"
        )
    elif matched_files:
        findings.append(f"API Routing: Endpoints and handlers detected across {len(matched_files)} files")

    if has_schemas:
        findings.append("API Validation: Structured schema validation (Pydantic BaseModel / Dataclass / Serializers) detected")
    if has_typed_exceptions:
        findings.append("API Error Handling: Explicit HTTP status codes and typed HTTPException responses detected")
    if has_auth_or_ratelimit:
        findings.append("API Security: Authentication dependencies, security guards, or rate limiting detected")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_devops_evidence(
    path: Path,
    files: list[Path],
    layer1_data: dict[str, Any] | None = None,
    l1_summary: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for DevOps, containerization, CI/CD, and IaC deployment."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    # 1. Docker / Containerization
    docker_candidates = [
        "Dockerfile", "Dockerfile.prod", "Dockerfile.dev",
        "docker-compose.yml", "docker-compose.yaml", "compose.yaml"
    ]
    for c in docker_candidates:
        if (path / c).exists():
            matched_files.append(c)

    dockerfile_path = path / "Dockerfile"
    if dockerfile_path.exists():
        df_content = safe_read_file(dockerfile_path)
        has_multistage = len(re.findall(r"^FROM\s+", df_content, re.MULTILINE | re.IGNORECASE)) > 1
        has_user = bool(re.search(r"^USER\s+(?!root\b)\S+", df_content, re.MULTILINE | re.IGNORECASE))
        has_health = bool(re.search(r"^HEALTHCHECK\s+(?!NONE\b)", df_content, re.MULTILINE | re.IGNORECASE))
        findings.append(
            f"Containerization: Dockerfile present (multi-stage={has_multistage}, non-root-user={has_user}, healthcheck={has_health})"
        )
        snip = extract_snippet(
            "Dockerfile", df_content,
            re.compile(r"^(USER|HEALTHCHECK|FROM\s+.*\s+AS)\b", re.MULTILINE | re.IGNORECASE),
            "Dockerfile security/stage directive"
        )
        if not snip:
            snip = extract_snippet(
                "Dockerfile", df_content,
                re.compile(r"^FROM\s+", re.MULTILINE | re.IGNORECASE),
                "Dockerfile base image"
            )
        if snip:
            snippets.append(snip)

    # 2. CI/CD Pipelines
    ci_patterns = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".circleci", "azure-pipelines.yml"]
    ci_found: list[str] = []
    for pat in ci_patterns:
        target = path / pat
        if target.is_dir():
            for ci_file in target.glob("*.y*ml"):
                rel = str(ci_file.relative_to(path))
                ci_found.append(rel)
                matched_files.append(rel)
        elif target.is_file():
            rel = str(target.relative_to(path))
            ci_found.append(rel)
            matched_files.append(rel)

    if ci_found:
        findings.append(f"CI/CD: Found {len(ci_found)} workflow pipeline(s): {', '.join(ci_found[:3])}")
        first_ci = path / ci_found[0]
        ci_content = safe_read_file(first_ci)
        snip = extract_snippet(
            ci_found[0], ci_content,
            re.compile(r"^\s*(jobs|steps|stages):", re.MULTILINE),
            "CI pipeline workflow definition"
        )
        if snip:
            snippets.append(snip)

    # 3. Infrastructure as Code (IaC) & Cloud
    iac_files: list[str] = []
    for f in files:
        rel = str(f.relative_to(path))
        if f.suffix in [".tf", ".hcl"] or (
            any(k in rel.lower() for k in ["k8s", "kubernetes", "helm"]) and f.suffix in [".yaml", ".yml"]
        ):
            iac_files.append(rel)
            matched_files.append(rel)

    if iac_files:
        findings.append(f"IaC: Infrastructure-as-Code detected ({len(iac_files)} file(s)): {', '.join(iac_files[:3])}")
        iac_sample = path / iac_files[0]
        iac_content = safe_read_file(iac_sample)
        snip = extract_snippet(
            iac_files[0], iac_content,
            re.compile(r'^\s*(resource|module|variable|apiVersion)\b', re.MULTILINE),
            "IaC resource configuration"
        )
        if snip:
            snippets.append(snip)

    # 4. Secrets & Configuration
    env_files = [e for e in [".env.example", ".env.template", ".env.dist"] if (path / e).exists()]
    if env_files:
        matched_files.extend(env_files)
        findings.append(f"Configuration: Environment variable template present ({', '.join(env_files)})")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_architecture_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for layered architecture, modularity, and interfaces."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    recognized_layers = ["domain", "models", "services", "repositories", "controllers", "api", "infra", "infrastructure", "adapters"]
    detected_layers: set[str] = set()

    interface_pattern = re.compile(r"(class\s+\w+\(.*(?:ABC|Protocol).*\):|@abstractmethod)", re.IGNORECASE)

    for f in files:
        rel = str(f.relative_to(path))
        parts = [p.lower() for p in Path(rel).parts]
        for layer in recognized_layers:
            if layer in parts:
                detected_layers.add(layer)
                matched_files.append(rel)

        content = safe_read_file(f)
        if interface_pattern.search(content):
            matched_files.append(rel)
            if len(snippets) == 0:
                snip = extract_snippet(rel, content, interface_pattern, "Architectural boundary / Interface contract")
                if snip:
                    snippets.append(snip)

    if detected_layers:
        findings.append(f"Layered Architecture: Clear separation into domain layers ({', '.join(sorted(detected_layers))})")
    if snippets:
        findings.append("Modularity & Inversion: Abstract base classes / typing Protocols defined for boundary decoupling")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_frontend_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for Frontend UX, state management, components, and a11y."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    component_extensions = {".tsx", ".jsx", ".vue", ".svelte"}
    ui_files = [str(f.relative_to(path)) for f in files if f.suffix in component_extensions or f.name == "package.json"]
    matched_files.extend(ui_files)

    state_tools: set[str] = set()
    a11y_matches = 0
    state_pattern = re.compile(r"\b(useDispatch|createSlice|create\(|defineStore|useContext|useState|useReducer)\b")
    a11y_pattern = re.compile(r"(aria-[a-z]+|role=|<main>|<nav>|<header>|<footer>|alt=)", re.IGNORECASE)

    for f in files:
        if f.suffix not in component_extensions and f.suffix not in {".html", ".js", ".ts"}:
            continue
        rel = str(f.relative_to(path))
        content = safe_read_file(f)
        if not content:
            continue

        states = state_pattern.findall(content)
        for s in states:
            state_tools.add(s)

        a11y_count = len(a11y_pattern.findall(content))
        a11y_matches += a11y_count

        if len(snippets) == 0 and (states or a11y_count > 0):
            target_pat = state_pattern if states else a11y_pattern
            snip = extract_snippet(rel, content, target_pat, "Frontend state / UI component")
            if snip:
                snippets.append(snip)

    if ui_files:
        findings.append(f"UI Components: Detected {len(ui_files)} component/frontend files")
    if state_tools:
        findings.append(f"State Management: Predictable state hooks / store patterns detected ({', '.join(sorted(state_tools)[:4])})")
    if a11y_matches > 0:
        findings.append(f"Accessibility (a11y): {a11y_matches} semantic HTML elements or aria attributes detected")

    return list(dict.fromkeys(matched_files)), findings, snippets


def collect_quantitative_evidence(
    path: Path, files: list[Path]
) -> tuple[list[str], list[str], list[CodeSnippet]]:
    """Collects dynamic evidence for quantitative modeling, validation, backtesting, and risk metrics."""
    matched_files: list[str] = []
    findings: list[str] = []
    snippets: list[CodeSnippet] = []

    metrics_found: set[str] = set()
    validation_found: set[str] = set()

    metric_pattern = re.compile(r"\b(sharpe|sortino|max_drawdown|drawdown|calmar|cagr|win_rate)\b", re.IGNORECASE)
    val_pattern = re.compile(r"\b(train_test_split|TimeSeriesSplit|cross_val_score|walk_forward|out_of_sample|KFold)\b", re.IGNORECASE)
    bt_pattern = re.compile(r"\b(backtest|backtrader|zipline|vectorbt|ccxt|simulate)\b", re.IGNORECASE)

    for f in files:
        rel = str(f.relative_to(path))
        content = safe_read_file(f)
        if not content:
            continue

        m_metrics = metric_pattern.findall(content)
        m_val = val_pattern.findall(content)
        m_bt = bt_pattern.findall(content)

        if m_metrics or m_val or m_bt:
            matched_files.append(rel)
            for m in m_metrics:
                metrics_found.add(m.lower())
            for v in m_val:
                validation_found.add(v)

            if len(snippets) == 0:
                pat = metric_pattern if m_metrics else (val_pattern if m_val else bt_pattern)
                snip = extract_snippet(rel, content, pat, "Quantitative metric / validation logic")
                if snip:
                    snippets.append(snip)

    if bt_pattern and matched_files:
        findings.append(f"Quantitative Modeling: Algorithmic simulation / calculation files detected ({len(matched_files)} files)")
    if metrics_found:
        findings.append(f"Risk & Performance Metrics: Quantitative performance metrics computed ({', '.join(sorted(metrics_found))})")
    if validation_found:
        findings.append(f"Statistical Validation: Overfitting prevention & validation splits detected ({', '.join(sorted(validation_found))})")

    return list(dict.fromkeys(matched_files)), findings, snippets
