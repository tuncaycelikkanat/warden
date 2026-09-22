"""Base helpers and classes for dynamic category evidence collection."""

import logging
import re
from pathlib import Path

from core.services.rubric import CodeSnippet

logger = logging.getLogger(__name__)


def safe_read_file(file_path: Path, max_chars: int = 150000) -> str:
    """Safely reads file content as string."""
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def extract_snippet(
    file_rel: str,
    content: str,
    match_pattern: re.Pattern[str],
    context: str,
    max_lines: int = 15,
) -> CodeSnippet | None:
    """Extracts a focused code snippet around the first pattern match."""
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if match_pattern.search(line):
            start = max(0, idx - 2)
            end = min(len(lines), start + max_lines)
            snippet_code = "\n".join(lines[start:end])
            return CodeSnippet(
                file=file_rel,
                line_start=start + 1,
                line_end=end,
                code=snippet_code,
                context=context,
            )
    return None
