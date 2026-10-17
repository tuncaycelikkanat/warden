# ADR-003: Subprocess Sandboxing and Resource Limitation Strategy

## Status
Accepted

## Context
WARDEN audits third-party and untrusted repositories. Certain Layer 1 analyzers invoke external binaries (such as `semgrep`, `gitleaks`, `git`, and `interrogate`) or parse complex Python ASTs that could trigger denial-of-service (ReDoS, recursive AST overflows, memory exhaustion, or hanging subprocesses).

Unbounded subprocess execution presents risks:
- Subprocesses hanging indefinitely on interactive prompts or network calls.
- Runaway memory consumption on maliciously crafted repository inputs.
- Arbitrary code execution if target files or filenames are passed insecurely to shell invocations.

## Decision
WARDEN adopts strict **Subprocess Sandboxing and Resource Limitation**:

1. **No Shell Invocations (`shell=False`):**
   - All subprocess calls across WARDEN use explicit argument vectors (argv lists). `shell=True` is prohibited to prevent command injection.

2. **Hard Timeout Envelopes:**
   - Every external subprocess is bound to an explicit `timeout` parameter (default 30-60 seconds depending on repository size).
   - If a process exceeds its timeout, `subprocess.TimeoutExpired` is caught, the child process group is SIGKILLed, and the defect/analyzer records a graceful timeout failure (`AnalyzerTimeoutError`).

3. **Isolated Working Directories and Read-Only Traversal:**
   - Analyzers operate strictly in read-only mode against the target repository path.
   - Temporary files (e.g., intermediate JSON reports from Gitleaks or Semgrep) are generated in secure, ephemeral directories managed via `tempfile.TemporaryDirectory` with restrictive permissions (`0700`) and guaranteed cleanup.

4. **AST Parse Defensiveness:**
   - Python code analysis (`ast.parse`) is safeguarded against recursion depth exploits, non-UTF-8 character encodings, and syntax bombs by wrapping AST visits with explicit catches for `(SyntaxError, RecursionError, UnicodeDecodeError, MemoryError, OSError)`.

## Consequences

### Positive
- Prevents malicious codebases from compromising CI runners or developer machines.
- Guaranteed termination: audits never hang indefinitely in automated pipelines.
- Predictable resource bounds on CPU and memory usage.

### Negative
- Extremely large monorepos may hit timeouts if default limits are not adjusted via `--timeout` configurations.
