"""Git diff analysis service for incremental audits in WARDEN."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class GitDiffAnalyzer:
    """Detects modified, added, or untracked source files in a git repository."""

    def get_changed_files(
        self,
        repo_path: Path,
        since_commit: str | None = None,
        include_untracked: bool = True,
    ) -> list[Path]:
        """Returns list of absolute Path objects for files modified since a commit or working copy.

        Args:
            repo_path: Path to the root of the git repository.
            since_commit: Optional git ref (e.g. 'HEAD~1', 'main', 'origin/master').
                          If None, inspects uncommitted working copy changes against HEAD.
            include_untracked: If True, also includes untracked new files.

        Returns:
            list[Path]: Files that have changed and actually exist on disk.
        """
        repo_path = repo_path.resolve()
        changed: set[Path] = set()

        if since_commit:
            cmd = ["git", "diff", "--name-only", "--diff-filter=d", since_commit, "HEAD"]
        else:
            # Staged and unstaged changes against HEAD
            cmd = ["git", "diff", "--name-only", "--diff-filter=d", "HEAD"]

        try:
            res = subprocess.run(
                cmd,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    f = (repo_path / line.strip()).resolve()
                    if f.is_file():
                        changed.add(f)
            else:
                logger.warning(f"git diff failed (code {res.returncode}): {res.stderr}")
        except Exception as e:
            logger.warning(f"Failed to execute git diff: {e}")

        if include_untracked:
            try:
                untracked_res = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                if untracked_res.returncode == 0:
                    for line in untracked_res.stdout.splitlines():
                        f = (repo_path / line.strip()).resolve()
                        if f.is_file():
                            changed.add(f)
            except Exception as e:
                logger.warning(f"Failed to list untracked files: {e}")

        return sorted(changed)
