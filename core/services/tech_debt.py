"""Service for measuring code churn, hot spots, and technical debt markers."""

import asyncio
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.services.shared.scan_exclusions import is_duplication_excluded, is_lockfile_or_vendor
from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)

TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", re.IGNORECASE)


@dataclass
class TodoMarker:
    """Represents an identified TODO/FIXME comment marker in code."""

    file: str
    line: int
    marker: str
    text: str


@dataclass
class FileChurnEntry:
    """Represents churn statistics and age for a single tracked file."""

    file: str
    commit_count: int
    lines_changed: int
    first_commit_date: datetime | None = None
    last_commit_date: datetime | None = None
    age_days: int = 0


@dataclass
class TechDebtResult:
    """Metrics and evidence of repository technical debt and churn."""

    measured: bool
    churn_entries: list[FileChurnEntry] = field(default_factory=list)
    todo_markers: list[TodoMarker] = field(default_factory=list)
    total_commits_in_window: int = 0
    reason: str | None = None
    note: str | None = None


class TechDebtService:
    """Measures technical debt using git churn hotspots and code comment markers."""

    WINDOW = "--since=6.months.ago"

    def _has_sufficient_history(self, repo_path: Path, git_bin: str) -> bool:
        """Verifies repository has a valid, non-shallow git history with commits."""
        # 1. Check if git repo
        rev_cmd = [git_bin, "rev-parse", "--is-shallow-repository"]
        res = subprocess.run(rev_cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=10, check=False)
        if res.returncode != 0:
            return False

        # 2. Check shallow flag
        if res.stdout.strip().lower() == "true":
            return False

        # 3. Check shallow file explicitly
        if (repo_path / ".git" / "shallow").is_file():
            return False

        # 4. Check if repo has at least one commit
        head_cmd = [git_bin, "rev-parse", "--verify", "HEAD"]
        head_res = subprocess.run(head_cmd, cwd=str(repo_path), capture_output=True, text=True, timeout=10, check=False)
        return head_res.returncode == 0

    def _parse_iso_date(self, date_str: str) -> datetime | None:
        """Parses ISO 8601 git author date."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.strip())
        except (ValueError, TypeError):
            return None

    def _parse_churn(self, raw_output: str, git_bin: str, repo_path: Path) -> tuple[list[FileChurnEntry], int]:
        """Parses git log numstat output into file churn metrics and age."""
        now = datetime.now(UTC)
        file_stats: dict[str, dict[str, Any]] = {}
        total_commits = 0

        current_commit_date: datetime | None = None
        seen_files_in_commit: set[str] = set()

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("__COMMIT__"):
                total_commits += 1
                seen_files_in_commit.clear()
                parts = line.split("|")
                if len(parts) >= 2:
                    current_commit_date = self._parse_iso_date(parts[1])
                continue

            parts = line.split("\t")
            if len(parts) < 3:
                continue

            added_str, deleted_str, file_name = parts[0], parts[1], parts[2]
            # Skip non-numeric changes (e.g. binary files)
            added = int(added_str) if added_str.isdigit() else 0
            deleted = int(deleted_str) if deleted_str.isdigit() else 0

            # Exclude vendor, lockfiles, and generated files
            if is_lockfile_or_vendor(file_name, repo_path) or is_duplication_excluded(file_name, repo_path):
                continue

            if file_name not in file_stats:
                file_stats[file_name] = {
                    "commit_count": 0,
                    "lines_changed": 0,
                    "first_date": current_commit_date,
                    "last_date": current_commit_date,
                }

            file_stats[file_name]["lines_changed"] += (added + deleted)
            if file_name not in seen_files_in_commit:
                file_stats[file_name]["commit_count"] += 1
                seen_files_in_commit.add(file_name)

            if current_commit_date:
                # Update first date if earlier
                first = file_stats[file_name]["first_date"]
                if not first or current_commit_date < first:
                    file_stats[file_name]["first_date"] = current_commit_date
                last = file_stats[file_name]["last_date"]
                if not last or current_commit_date > last:
                    file_stats[file_name]["last_date"] = current_commit_date

        entries: list[FileChurnEntry] = []
        for file_name, stats in file_stats.items():
            first_date = stats["first_date"]

            # Query git log to get the true initial creation commit date
            try:
                creation_run = subprocess.run(
                    [git_bin, "log", "--follow", "--diff-filter=A", "--format=%aI", "-1", "--", file_name],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if creation_run.returncode == 0 and creation_run.stdout.strip():
                    orig_date = self._parse_iso_date(creation_run.stdout.strip())
                    if orig_date:
                        first_date = orig_date
            except Exception:
                pass

            age_days = 0
            if first_date:
                # Ensure timezone aware comparison
                if first_date.tzinfo is None:
                    first_date = first_date.replace(tzinfo=UTC)
                age_days = max(0, (now - first_date).days)

            entries.append(
                FileChurnEntry(
                    file=file_name,
                    commit_count=stats["commit_count"],
                    lines_changed=stats["lines_changed"],
                    first_commit_date=first_date,
                    last_commit_date=stats["last_date"],
                    age_days=age_days,
                )
            )

        # Sort by commit count descending
        entries.sort(key=lambda e: e.commit_count, reverse=True)
        return entries, total_commits

    def _scan_todo_markers(self, repo_path: Path) -> list[TodoMarker]:
        """Scans source files for TODO, FIXME, HACK, XXX comments."""
        markers: list[TodoMarker] = []
        source_files = discover_source_files(repo_path)

        for file_path in source_files:
            rel_path = str(file_path.relative_to(repo_path)) if file_path.is_relative_to(repo_path) else str(file_path)
            if is_lockfile_or_vendor(rel_path, repo_path) or is_duplication_excluded(rel_path, repo_path):
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, start=1):
                        # Word-boundary check only within comments to avoid false positives like hackathon or docstrings
                        if "#" in line:
                            comment_part = line[line.index("#"):]
                            match = TODO_PATTERN.search(comment_part)
                            if match:
                                marker_type = match.group(1).upper()
                                marker_text = match.group(2).strip()
                                markers.append(
                                    TodoMarker(
                                        file=rel_path,
                                        line=lineno,
                                        marker=marker_type,
                                        text=marker_text[:120],
                                    )
                                )
            except OSError:
                pass

        return markers

    def _run_git_churn(self, repo_path: Path, git_bin: str) -> str:
        """Executes git log numstat subprocess."""
        cmd = [
            git_bin,
            "log",
            self.WINDOW,
            "--numstat",
            "--pretty=format:__COMMIT__%H|%aI",
        ]
        res = subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git log failed (exit {res.returncode}): {res.stderr}")
        return res.stdout

    async def analyze(self, repo_path: Path) -> TechDebtResult:
        """Analyzes technical debt via git churn hotspots and TODO markers."""
        git_bin = shutil.which("git")
        if not git_bin:
            return TechDebtResult(measured=False, reason="git_not_found")

        if not self._has_sufficient_history(repo_path, git_bin):
            return TechDebtResult(measured=False, reason="git_history_unavailable_or_shallow")

        try:
            raw_output = await asyncio.to_thread(self._run_git_churn, repo_path, git_bin)
        except subprocess.TimeoutExpired:
            logger.warning("git log timed out after 60s")
            return TechDebtResult(measured=False, reason="git_log_timeout")
        except Exception as e:
            logger.warning(f"git log execution failed: {e}")
            return TechDebtResult(measured=False, reason=f"git_error: {e}")

        churn_entries, total_commits = self._parse_churn(raw_output, git_bin, repo_path)
        todo_markers = await asyncio.to_thread(self._scan_todo_markers, repo_path)

        note = "no_commits_in_window" if total_commits == 0 else None

        return TechDebtResult(
            measured=True,
            churn_entries=churn_entries,
            todo_markers=todo_markers,
            total_commits_in_window=total_commits,
            note=note,
        )
