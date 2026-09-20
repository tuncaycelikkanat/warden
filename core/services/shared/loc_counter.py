"""Centralized lines-of-code (LOC) counter for Layer 1 density metrics."""

from pathlib import Path

from core.services.shared.scan_exclusions import get_scan_exclusions


def count_source_lines(repo_path: Path, exclusions: list[str] | None = None) -> int:
    """Counts non-empty lines of Python source code in the repository.

    Excludes standard virtualenvs, caches, build artifacts, and vendor directories.
    """
    excluded_set = set(get_scan_exclusions(repo_path, extra=exclusions))
    total_loc = 0

    try:
        for p in repo_path.rglob("*.py"):
            try:
                rel = p.relative_to(repo_path)
            except ValueError:
                rel = p

            if any(part in excluded_set or part.startswith(".") for part in rel.parts[:-1]):
                continue

            try:
                with p.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip():
                            total_loc += 1
            except Exception:
                continue
    except Exception:
        return 0

    return total_loc
