# ADR-001: Dual-Layer Mechanical and LLM Scoring Model

## Status
Accepted

## Context
Traditional static analysis tools (SonarQube, ESLint, Bandit) excel at deterministic, rule-based syntax checks, complexity metrics, and known CVE lookups. However, they are blind to architectural coherence, domain intent, and vibe-coding anti-patterns (such as superficial AI-generated scaffolding or brittle design choices).

Conversely, pure LLM-based code reviewers suffer from hallucination, non-determinism, slow evaluation speeds, token cost, and lack of reproducible gating in CI/CD pipelines.

## Decision
WARDEN adopts a strict **Dual-Layer Architecture**:

1. **Layer 1 (Mechanical Baseline - 60% Weight):**
   - 16 pluggable, deterministic static analyzers executed concurrently (`AnalyzerRegistry`).
   - Pure Python AST inspection, Shannon entropy calculation, regex heuristics, and external tool adapters (Semgrep, Gitleaks, Radon, pip-licenses).
   - Zero LLM dependency; fully operable in air-gapped and offline environments.
   - Guaranteed determinism and idempotency: repeated runs on the exact same commit yield identical numerical scores.

2. **Layer 2 (Cognitive/Architectural Rubrics - 40% Weight):**
   - Evaluated by multi-model LLM panels (Gemini, Claude, OpenAI, Ollama).
   - Scored against structured rubrics: Architectural Cohesion, Error Handling Strategy, Cognitive Load, Domain Modeling, and Supply-Chain Posture.
   - Guarded by prompt sanitization and strict JSON schema decoding.
   - Optional: If Layer 2 is omitted (e.g. running `--layer1-only` or without API keys), the 40% weight is automatically redistributed to Layer 1 with zero degradation in gate evaluation.

## Consequences

### Positive
- **Determinism:** CI/CD builds pass or fail on concrete, reproducible metrics.
- **Cost & Speed:** Fast feedback loops (< 5 seconds for Layer 1 on medium repositories).
- **Graceful Degradation:** Pipelines never block on LLM rate limits or external API outages.
- **Depth:** Captures both shallow code smells and deep architectural debt.

### Negative
- Requires maintaining two evaluation engines (static AST walkers and LLM prompt templates).
- Score normalization across heterogeneous analyzers requires calibrated weights (`ScorecardAggregatorService`).
