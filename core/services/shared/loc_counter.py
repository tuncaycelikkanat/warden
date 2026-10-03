import logging
from pathlib import Path

from core.services.shared.scan_exclusions import get_scan_exclusions

logger = logging.getLogger(__name__)


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
            except Exception as err:
                logger.debug(f"Failed to read file {p}: {err}")
                continue
    except Exception as err:
        logger.debug(f"Failed scanning repository for LOC: {err}")
        return 0

    return total_loc
