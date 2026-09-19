import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CommitHygieneResult:
    score: float
    total_commits: int
    bad_commits: int
    bad_ratio: float
    avg_length: float

class CommitHygieneService:
    async def analyze(self, repo_path: Path) -> CommitHygieneResult:
        import asyncio
        
        def run_gitpython():
            try:
                subprocess.run(["uv", "pip", "install", "gitpython"], cwd=str(repo_path), capture_output=True, check=False)
                import git
            except Exception as e:
                logger.warning(f"Failed to install/import gitpython: {e}")
                return []
                
            try:
                repo = git.Repo(repo_path)
                # Ensure we only get up to 100 commits
                # if repo is empty, this might raise an exception
                commits = list(repo.iter_commits(max_count=100))
                
                messages = [c.message.strip() for c in commits]
                return messages
            except git.InvalidGitRepositoryError:
                logger.warning(f"Not a git repository: {repo_path}")
                return []
            except Exception as e:
                logger.warning(f"Failed to read git repository: {e}")
                return []

        messages = await asyncio.to_thread(run_gitpython)
        
        if not messages:
            return CommitHygieneResult(score=100.0, total_commits=0, bad_commits=0, bad_ratio=0.0, avg_length=0.0)
            
        total_commits = len(messages)
        bad_commits = 0
        total_length = 0
        
        bad_patterns = {"wip", "fix", "asdf", "test", "update", "changes"}
        
        for msg in messages:
            # First line is usually the subject
            subject = msg.split('\n')[0].strip()
            total_length += len(subject)
            
            lower_msg = subject.lower()
            words = lower_msg.split()
            
            is_bad = False
            if len(subject) < 5:
                is_bad = True
            elif len(words) <= 1:
                is_bad = True
            elif any(bp == lower_msg for bp in bad_patterns):
                is_bad = True
                
            if is_bad:
                bad_commits += 1
                
        avg_length = total_length / total_commits
        bad_ratio = bad_commits / total_commits
        
        # her %5 için -8 -> ratio / 0.05 * 8
        score = 100.0 - ((bad_ratio / 0.05) * 8.0)
        
        return CommitHygieneResult(
            score=max(20.0, min(100.0, score)),
            total_commits=total_commits,
            bad_commits=bad_commits,
            bad_ratio=bad_ratio,
            avg_length=avg_length
        )
