"""Git commit message quality and hygiene analyzer."""

import asyncio
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_COMMIT_SAMPLE_SIZE = 10

BOT_AUTHOR_PATTERNS = re.compile(
    r"\[bot\]|dependabot|renovate|github-actions|semantic-release|gitlab-bot|git-bot",
    re.IGNORECASE,
)

CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|build|ci|revert)(\([a-zA-Z0-9_\-\./]+\))?!?:\s*(.+)$",
    re.IGNORECASE,
)

GENERIC_FILLER_PATTERN = re.compile(
    r"\b(various|changes|updates|stuff|things|misc)\b.*\b(various|changes|updates|stuff|things|misc)\b",
    re.IGNORECASE,
)

MEANINGFUL_SINGLE_WORDS = {
    "refactor",
    "bugfix",
    "release",
    "hotfix",
    "revert",
    "cleanup",
    "initial",
    "init",
    "format",
    "docs",
    "documentation",
}

BAD_EXACT_MATCHES = {
    "wip",
    "fix",
    "asdf",
    "test",
    "update",
    "changes",
    "stuff",
    "misc",
    "temp",
    "foo",
    "bar",
    "güncelleme",
    "düzeltme",
    "deneme",
    "testler",
    "degisiklikler",
    "değişiklikler",
}


@dataclass
class CommitHygieneResult:
    """Represents git commit message hygiene analysis metrics."""

    score: float
    total_commits: int
    bad_commits: int
    bad_ratio: float
    avg_length: float
    measured: bool = True
    reason: str | None = None


class CommitHygieneService:
    """Service to evaluate git commit conventions and message quality."""

    def _is_bot_commit(self, author_name: str, author_email: str) -> bool:
        """Determines if a commit was authored by an automated bot based on metadata."""
        return bool(
            BOT_AUTHOR_PATTERNS.search(author_name) or BOT_AUTHOR_PATTERNS.search(author_email)
        )

    def _is_bad_commit(self, subject: str) -> bool:
        """Evaluates whether a commit message subject line fails hygiene standards."""
        cleaned = subject.strip()
        if not cleaned:
            return True

        # Verbose filler detection (gaming resistance)
        if GENERIC_FILLER_PATTERN.search(cleaned):
            return True

        # Conventional Commits format validation
        conv_match = CONVENTIONAL_COMMIT_PATTERN.match(cleaned)
        if conv_match:
            desc = conv_match.group(3).strip().lower()
            return desc in BAD_EXACT_MATCHES or len(desc) < 3 or bool(re.match(r"^(.)\1+$", desc))

        # Meaningful single-word exemptions (reverse risk prevention)
        words = cleaned.split()
        if len(words) == 1:
            return words[0].lower() not in MEANINGFUL_SINGLE_WORDS

        # Character length threshold
        if len(cleaned) < 5:
            return True

        # Exact match bad patterns
        if cleaned.lower() in BAD_EXACT_MATCHES:
            return True

        # Repeated characters spam (e.g., 'aaaaa', 'asdfasdf')
        return bool(re.match(r"^(.)\1{4,}$", cleaned)) or "asdfasdf" in cleaned.lower()

    async def analyze(self, repo_path: Path) -> CommitHygieneResult:
        """Analyzes commit history for message quality and conventional commits using git CLI."""

        def _sync_analyze() -> CommitHygieneResult:
            git_bin = shutil.which("git")
            if not git_bin:
                return CommitHygieneResult(
                    score=100.0,
                    total_commits=0,
                    bad_commits=0,
                    bad_ratio=0.0,
                    avg_length=0.0,
                    measured=False,
                    reason="git_not_found",
                )

            try:
                res = subprocess.run(
                    [git_bin, "log", "--no-merges", "-n", "100", "--pretty=format:%H|%an|%ae|%s"],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return CommitHygieneResult(
                    score=100.0,
                    total_commits=0,
                    bad_commits=0,
                    bad_ratio=0.0,
                    avg_length=0.0,
                    measured=False,
                    reason="git_log_timeout",
                )
            except Exception as e:
                logger.warning(f"Error running git log: {e}")
                return CommitHygieneResult(
                    score=100.0,
                    total_commits=0,
                    bad_commits=0,
                    bad_ratio=0.0,
                    avg_length=0.0,
                    measured=False,
                    reason="git_execution_error",
                )

            if res.returncode != 0:
                return CommitHygieneResult(
                    score=100.0,
                    total_commits=0,
                    bad_commits=0,
                    bad_ratio=0.0,
                    avg_length=0.0,
                    measured=False,
                    reason="not_a_git_repository",
                )

            human_subjects: list[str] = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) < 4:
                    continue
                _h, author_name, author_email, subject = parts
                if self._is_bot_commit(author_name, author_email):
                    continue
                human_subjects.append(subject.strip())

            if len(human_subjects) < MIN_COMMIT_SAMPLE_SIZE:
                avg_len = (
                    float(sum(len(s) for s in human_subjects) / len(human_subjects))
                    if human_subjects
                    else 0.0
                )
                return CommitHygieneResult(
                    score=100.0,
                    total_commits=len(human_subjects),
                    bad_commits=0,
                    bad_ratio=0.0,
                    avg_length=round(avg_len, 1),
                    measured=False,
                    reason="insufficient_commit_sample",
                )

            total_commits = len(human_subjects)
            bad_commits = sum(1 for s in human_subjects if self._is_bad_commit(s))
            total_length = sum(len(s) for s in human_subjects)
            avg_length = total_length / total_commits
            bad_ratio = bad_commits / total_commits

            score = 100.0 - ((bad_ratio / 0.05) * 8.0)
            final_score = max(20.0, min(100.0, round(score, 1)))

            return CommitHygieneResult(
                score=final_score,
                total_commits=total_commits,
                bad_commits=bad_commits,
                bad_ratio=round(bad_ratio, 4),
                avg_length=round(avg_length, 1),
                measured=True,
                reason=None,
            )

        return await asyncio.to_thread(_sync_analyze)
