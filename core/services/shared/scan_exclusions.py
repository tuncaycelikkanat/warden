"""Centralized scan exclusion lists and helpers for Layer 1 scanners."""

from pathlib import Path

STANDARD_EXCLUSIONS: list[str] = [
    ".git",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "build",
    "dist",
    ".tox",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
]


import re


def get_scan_exclusions(repo_path: Path | None = None, extra: list[str] | None = None) -> list[str]:
    """Returns the unified list of directory and file exclusions.

    All Layer 1 scanners (ruff, radon, jscpd, ast analyzers) should use this single source of truth.
    """
    exclusions = list(STANDARD_EXCLUSIONS)
    if extra:
        exclusions.extend(extra)
    return exclusions


def get_scan_exclusion_pattern(repo_path: Path | None = None, extra: list[str] | None = None) -> str:
    """Returns a regex pattern of exclusions suitable for Mypy's --exclude argument."""
    exclusions = get_scan_exclusions(repo_path, extra=extra)
    escaped = [re.escape(item) for item in exclusions]
    return f"({'|'.join(escaped)})"

