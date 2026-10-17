# ADR-002: Pluggable Analyzer Architecture via Protocol and EntryPoints

## Status
Accepted

## Context
Initially, Layer 1 analyzers were orchestrated by a monolithic sequential/hardcoded runner in `core/services/orchestrator.py` (`_run_l1_scanners`). Adding a new scanner required modifying the orchestrator, coupling individual scanner dependencies to the core engine, and preventing third-party or proprietary scanners from integrating without forking the codebase.

Furthermore, an unhandled exception in any single analyzer could crash the entire audit run, violating the principle of fault isolation.

## Decision
WARDEN adopts a **Pluggable Protocol & Registry Architecture**:

1. **Protocol Definition (`core.analyzers.protocol`):**
   - Analyzers implement the `AnalyzerPlugin` runtime-checkable Protocol:
     - `key: str` (unique identifier)
     - `display_name: str`
     - `async run(ctx: AnalysisContext) -> AnalyzerOutput`
   - `AnalysisContext` provides immutable references to `repo_path`, `full_history`, `incremental`, and cancellation tokens.
   - `AnalyzerOutput` encapsulates `data`, `summary`, `measured: bool`, and optional `error: str`.

2. **Registry & Concurrent Execution (`core.analyzers.registry`):**
   - `AnalyzerRegistry` manages analyzer instances.
   - `run_all(ctx)` executes all registered analyzers concurrently via `asyncio.gather(*tasks)`.
   - Each execution is wrapped in `_safe_run` exception boundaries: if an analyzer fails or crashes, its error is contained, logged, and marked as `measured=False`, while all other analyzers continue unaffected.

3. **Open Plugin Discovery via EntryPoints:**
   - WARDEN standardizes on Python's `entry_points` mechanism under the group `"warden.analyzers"`.
   - All 16 built-in analyzers are registered under this entry-point group in `pyproject.toml`.
   - Any third-party Python package can register an analyzer by declaring:
     ```toml
     [project.entry-points."warden.analyzers"]
     custom_scanner = "my_package.scanners:CustomScanner"
     ```
   - `AnalyzerRegistry.load_entrypoints()` automatically discovers and registers installed plugins at runtime without modifying WARDEN core.

## Consequences

### Positive
- **Extensibility:** 3rd parties can integrate custom static analysis rules or internal enterprise scanners seamlessly.
- **Fault Isolation:** Crashes in one scanner never abort the audit or corrupt scorecard generation.
- **Testability:** Each analyzer is isolated and can be unit-tested with mock contexts without bootstrapping the full CLI.
- **Decoupling:** `AuditOrchestrator` is reduced to coordinating the registry rather than hardcoding analyzer details.

### Negative
- Asynchronous concurrency requires analyzers that execute external CLI tools (e.g. Semgrep, Gitleaks) to manage process pools and avoid thread exhaustion.
