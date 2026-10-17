# ADR-004: Quality Gate Contract and Exit Code Specification

## Status
Accepted

## Context
When code review and auditing tools are deployed into CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins), process exit codes represent a public contract. Tools that output exit code `1` indiscriminately for all failure types (configuration errors, crashes, quality regressions, or security vulnerabilities) force CI pipelines into clumsy workarounds (such as string grepping logs) to determine why a step failed.

Furthermore, machine-parseable output (JSON) must be cleanly separated from diagnostic logs to enable downstream automation (`jq`, webhook dispatchers, PR bot commenters).

## Decision
WARDEN adopts a **Deterministic Quality Gate Contract**:

1. **Standardized Process Exit Codes (`core.services.quality_gate.ExitCode`):**
   - **`0 (PASSED)`**: All quality checks passed; audit score meets or exceeds the required threshold, and no blocking security findings were detected.
   - **`1 (BELOW_THRESHOLD)`**: Audit score fell below the configured minimum threshold (`--min-score <N>`).
   - **`2 (SECURITY_VIOLATION)`**: One or more critical security violations were detected under `--fail-on-critical` (e.g., exposed hardcoded secrets, SAST ERROR-level rules, or vulnerable dependencies with known CVEs). Security violations take precedence over score thresholds.
   - **`3 (EXECUTION_ERROR)`**: Audit could not complete due to execution or environment failures (e.g. invalid repository path, missing binary, corrupted database, or internal error).

2. **Stream Separation for Machine Parsing:**
   - Under `--format json`, standard output (`stdout`) is guaranteed to be a single, pure JSON document.
   - All human-facing banners, progress indicators, and informational messages are automatically redirected to standard error (`stderr`).
   - CI scripts can safely pipe `warden audit --format json | jq .exit_code` without encountering interleaved log text.

## Consequences

### Positive
- CI/CD pipelines can branch intelligently based on exit codes:
  - Exit code `2` can trigger a security incident and block deployment immediately.
  - Exit code `1` can notify developers of code quality degradation or add a PR review warning.
  - Exit code `3` alerts DevOps engineers to pipeline infrastructure issues.
- Clean JSON stdout guarantees zero JSON-parsing syntax errors in automation scripts.

### Negative
- Users consuming WARDEN programmatically must check exit codes according to the specified enum values rather than assuming a binary 0/1 outcome.
