"""Smart Git Hook service providing pre-commit and pre-push quality gates for WARDEN."""

import ast
import logging
import os
import stat
from pathlib import Path

from core.services.entropy_analyzer import EntropyAnalyzerService
from core.services.git_diff_analyzer import GitDiffAnalyzer

logger = logging.getLogger(__name__)

PRE_COMMIT_TEMPLATE = """#!/bin/sh
# WARDEN Smart Git Hook: pre-commit
# Automatically installed by WARDEN. Checks staged files for secrets and syntax errors.
if command -v warden >/dev/null 2>&1; then
    warden hook run --hook-type pre-commit
elif [ -f ".venv/bin/warden" ]; then
    .venv/bin/warden hook run --hook-type pre-commit
elif command -v uv >/dev/null 2>&1; then
    uv run python -m core.main hook run --hook-type pre-commit
else
    python3 -m core.main hook run --hook-type pre-commit
fi
"""

PRE_PUSH_TEMPLATE = """#!/bin/sh
# WARDEN Smart Git Hook: pre-push
# Automatically installed by WARDEN. Runs incremental quality audit and enforces quality gate.
MIN_SCORE={min_score}
if command -v warden >/dev/null 2>&1; then
    warden hook run --hook-type pre-push --min-score $MIN_SCORE
elif [ -f ".venv/bin/warden" ]; then
    .venv/bin/warden hook run --hook-type pre-push --min-score $MIN_SCORE
elif command -v uv >/dev/null 2>&1; then
    uv run python -m core.main hook run --hook-type pre-push --min-score $MIN_SCORE
else
    python3 -m core.main hook run --hook-type pre-push --min-score $MIN_SCORE
fi
"""


class GitHookService:
    """Manages installation, uninstallation, and execution of smart Git hooks."""

    def __init__(self) -> None:
        self.diff_analyzer = GitDiffAnalyzer()
        self.entropy_analyzer = EntropyAnalyzerService()

    def get_hooks_dir(self, repo_path: Path) -> Path | None:
        """Returns the .git/hooks directory path if repository exists, else None."""
        repo_path = repo_path.resolve()
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            return None
        if git_dir.is_file():
            # Support git worktrees or submodules where .git is a pointer file
            try:
                content = git_dir.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir:"):
                    real_git_dir = (repo_path / content.replace("gitdir:", "").strip()).resolve()
                    return real_git_dir / "hooks"
            except Exception as e:
                logger.warning(f"Could not read gitdir pointer: {e}")
                return None
        return git_dir / "hooks"

    def install(self, repo_path: Path, hook_type: str = "all", min_score: int = 80) -> bool:
        """Installs pre-commit and/or pre-push git hooks into .git/hooks/."""
        hooks_dir = self.get_hooks_dir(repo_path)
        if not hooks_dir:
            logger.error(f"Not a valid git repository: {repo_path}")
            return False

        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_type = hook_type.lower()
        success = True

        if hook_type in ("pre-commit", "all"):
            pre_commit_path = hooks_dir / "pre-commit"
            try:
                pre_commit_path.write_text(PRE_COMMIT_TEMPLATE, encoding="utf-8")
                # chmod +x (0o755)
                cur_mode = os.stat(pre_commit_path).st_mode
                os.chmod(pre_commit_path, cur_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception as e:
                logger.error(f"Failed to write pre-commit hook: {e}")
                success = False

        if hook_type in ("pre-push", "all"):
            pre_push_path = hooks_dir / "pre-push"
            try:
                content = PRE_PUSH_TEMPLATE.format(min_score=min_score)
                pre_push_path.write_text(content, encoding="utf-8")
                cur_mode = os.stat(pre_push_path).st_mode
                os.chmod(pre_push_path, cur_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except Exception as e:
                logger.error(f"Failed to write pre-push hook: {e}")
                success = False

        return success

    def uninstall(self, repo_path: Path, hook_type: str = "all") -> bool:
        """Removes installed WARDEN hooks from .git/hooks/."""
        hooks_dir = self.get_hooks_dir(repo_path)
        if not hooks_dir or not hooks_dir.exists():
            return False

        hook_type = hook_type.lower()
        targets = []
        if hook_type in ("pre-commit", "all"):
            targets.append(hooks_dir / "pre-commit")
        if hook_type in ("pre-push", "all"):
            targets.append(hooks_dir / "pre-push")

        success = True
        for target in targets:
            if target.exists():
                try:
                    target.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete hook {target}: {e}")
                    success = False

        return success

    def run_pre_commit(self, repo_path: Path) -> tuple[bool, str]:
        """Scans staged files for high-entropy secrets, syntax errors, and sensitive credentials.

        Executes in <1 second to maintain fast commit loop.
        """
        staged_files = self.diff_analyzer.get_staged_files(repo_path)
        if not staged_files:
            return True, "[✓] Sahnelenmiş (staged) dosya bulunamadı, pre-commit kontrolü temiz."

        issues: list[str] = []

        for f in staged_files:
            if not f.is_file():
                continue

            rel_path = f.relative_to(repo_path) if f.is_relative_to(repo_path) else f

            # 1. Check Python syntax errors
            if f.suffix.lower() == ".py":
                try:
                    code = f.read_text(encoding="utf-8", errors="ignore")
                    ast.parse(code, filename=str(f))
                except SyntaxError as syn_err:
                    issues.append(f"❌ [SyntaxError] {rel_path}:{syn_err.lineno} -> {syn_err.msg}")
                    continue
                except Exception as e:
                    logger.debug(f"AST parse error on {f}: {e}")

            # 2. Check high-entropy secrets
            findings = self.entropy_analyzer.scan_file(f)
            for finding in findings:
                if finding.confidence == "HIGH" or finding.entropy_score >= 4.2:
                    issues.append(
                        f"🚨 [Secret Leak] {rel_path}:{finding.line} -> Potansiyel sır: "
                        f"{finding.variable_name} ({finding.masked_value}) - Entropi: {finding.entropy_score:.2f}"
                    )

            # 3. Check for exposed .env files
            if f.name.lower() in (".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"):
                issues.append(f"🚨 [Sensitive File] {rel_path} gibi hassas ortam/anahtar dosyaları commit edilmemelidir!")

        if issues:
            report_lines = [
                "[!] WARDEN pre-commit kalite kapısı ihlali tespit edildi!",
                f"    {len(issues)} kritik sorun nedeniyle commit engellendi:",
            ]
            for issue in issues:
                report_lines.append(f"    - {issue}")
            report_lines.append("\nLütfen yukarıdaki sorunları çözün veya gerekiyorsa '--no-verify' ile atlayın.")
            return False, "\n".join(report_lines)

        return True, f"[✓] WARDEN pre-commit: {len(staged_files)} staged dosya incelendi, tüm kontroller temiz!"

    async def run_pre_push(self, repo_path: Path, min_score: int = 80) -> tuple[bool, str]:
        """Runs incremental quality audit on unpushed changes and validates quality gate."""
        from core.services.orchestrator import AuditOrchestrator

        repo_path = repo_path.resolve()
        orchestrator = AuditOrchestrator()

        try:
            result = await orchestrator.run_full_audit(str(repo_path), incremental=True)
            scorecard = result.get("scorecard", {})
            total_score = scorecard.get("total_score", 0)
            grade = scorecard.get("grade", "F")

            if total_score < min_score:
                msg = (
                    f"[!] WARDEN pre-push kalite kapısı BAŞARISIZ!\n"
                    f"    Mevcut Skor: {total_score}/100 (Harf Notu: {grade})\n"
                    f"    Gereken Asgari Skor: {min_score}/100\n"
                    f"    Lütfen kod kalitesini artırın veya kalite eşiğini düzenleyin."
                )
                return False, msg

            msg = (
                f"[✓] WARDEN pre-push kalite kapısı GEÇTİ!\n"
                f"    Skor: {total_score}/100 (Harf Notu: {grade}) >= Eşik: {min_score}"
            )
            return True, msg
        except Exception as e:
            logger.warning(f"pre-push audit encountered error: {e}")
            return False, f"[!] pre-push denetimi sırasında hata oluştu: {e}"
