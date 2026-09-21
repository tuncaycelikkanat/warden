"""Docker containerization and readiness analyzer."""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from core.services.shared.scan_exclusions import get_scan_exclusions

logger = logging.getLogger(__name__)

WEB_FRAMEWORK_PATTERNS = {
    "fastapi",
    "flask",
    "django",
    "aiohttp",
    "starlette",
    "tornado",
    "uvicorn",
    "gunicorn",
    "sanic",
    "litestar",
    "falcon",
}


@dataclass
class DockerResult:
    """Represents Docker configuration readiness evaluation results."""

    score: float
    has_dockerfile: bool
    has_healthcheck: bool
    has_env_example: bool
    has_docker_compose: bool
    has_non_root_user: bool = False
    has_multistage: bool = False
    dockerfile_path: str | None = None
    applicable: bool = True
    measured: bool = True
    reason: str | None = None


class DockerReadinessService:
    """Service to evaluate Dockerfile, compose, environment template readiness and container security."""

    def _is_excluded(self, path: Path, repo_path: Path) -> bool:
        """Checks if a path resides inside central scan exclusion directories."""
        exclusions = set(get_scan_exclusions(repo_path, extra=["tests", "fixtures", "test_data", "examples"]))
        try:
            rel = path.relative_to(repo_path)
            parts = rel.parts
        except ValueError:
            parts = path.parts

        for p in parts:
            if p in exclusions or (p.startswith(".") and p not in {".docker", ".env.example", ".env.sample", ".env.template"}):
                return True
        return False

    def _find_dockerfile(self, repo_path: Path) -> Path | None:
        """Finds candidate Dockerfile in root or standard deployment/monorepo subdirectories."""
        primary_candidates = [
            repo_path / "Dockerfile",
            repo_path / "Dockerfile.prod",
            repo_path / "Dockerfile.production",
            repo_path / "docker" / "Dockerfile",
            repo_path / "deploy" / "Dockerfile",
            repo_path / ".docker" / "Dockerfile",
        ]
        for cand in primary_candidates:
            if cand.is_file() and not self._is_excluded(cand, repo_path):
                return cand

        # Check single-level subdirectories (e.g. backend/Dockerfile, services/api/Dockerfile)
        try:
            for sub_df in sorted(repo_path.glob("*/Dockerfile")):
                if sub_df.is_file() and not self._is_excluded(sub_df, repo_path):
                    return sub_df
        except OSError as e:
            logger.warning(f"Error globbing for sub-dockerfiles: {e}")

        return None

    def _find_docker_compose(self, repo_path: Path) -> bool:
        """Checks if docker-compose configuration exists."""
        candidates = [
            repo_path / "docker-compose.yml",
            repo_path / "docker-compose.yaml",
            repo_path / "compose.yml",
            repo_path / "compose.yaml",
            repo_path / "docker" / "docker-compose.yml",
            repo_path / "docker" / "docker-compose.yaml",
        ]
        return any(c.is_file() and not self._is_excluded(c, repo_path) for c in candidates)

    def _check_env_example(self, repo_path: Path) -> bool:
        """Checks if a non-empty environment template file exists."""
        env_files = [
            repo_path / ".env.example",
            repo_path / ".env.sample",
            repo_path / ".env.template",
        ]
        for f in env_files:
            if f.is_file() and not self._is_excluded(f, repo_path):
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore").strip()
                    if content:
                        return True
                except OSError as e:
                    logger.warning(f"Failed to read env example {f}: {e}")
        return False

    def _parse_dockerfile(
        self, dockerfile: Path
    ) -> tuple[bool, bool, bool]:
        """
        Parses Dockerfile for:
        1. Valid HEALTHCHECK (ignores comments and NONE).
        2. Non-root USER directive.
        3. Multi-stage build (multiple FROM with AS).
        """
        has_healthcheck = False
        has_non_root_user = False
        from_stages: list[str | None] = []

        try:
            content = dockerfile.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            logger.warning(f"Failed to read Dockerfile {dockerfile}: {e}")
            return False, False, False

        for line in content.splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue

            # Strip trailing comments if any
            if " #" in clean:
                clean = clean.split(" #", 1)[0].strip()

            # 1. HEALTHCHECK inspection
            hc_match = re.search(r"^HEALTHCHECK\s+(.+)$", clean, re.IGNORECASE)
            if hc_match:
                hc_body = hc_match.group(1).strip()
                if not hc_body.upper().startswith("NONE"):
                    has_healthcheck = True

            # 2. USER inspection (non-root)
            user_match = re.search(r"^USER\s+(\S+)", clean, re.IGNORECASE)
            if user_match:
                user_val = user_match.group(1).strip().strip("\"'").lower()
                if ":" in user_val:
                    user_val = user_val.split(":", 1)[0]
                if user_val not in {"root", "0"}:
                    has_non_root_user = True

            # 3. Multi-stage FROM inspection
            from_match = re.search(
                r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", clean, re.IGNORECASE
            )
            if from_match:
                alias = from_match.group(2)
                from_stages.append(alias)

        has_multistage = len(from_stages) >= 2 and any(stage is not None for stage in from_stages[:-1])

        return has_healthcheck, has_non_root_user, has_multistage

    def _is_containerization_applicable(
        self, repo_path: Path, has_docker_files: bool
    ) -> tuple[bool, str | None]:
        """
        Determines if containerization is applicable for this repository.
        If Docker artifacts exist, it is always applicable.
        If no Docker artifacts exist and the project is a pure library/CLI
        without web framework dependencies, containerization is marked not applicable.
        """
        if has_docker_files:
            return True, None

        # Check if project contains web frameworks in dependency manifests
        manifest_files = [
            repo_path / "requirements.txt",
            repo_path / "pyproject.toml",
            repo_path / "setup.py",
            repo_path / "Pipfile",
        ]

        found_web_framework = False
        has_library_manifest = False

        for mf in manifest_files:
            if mf.is_file() and not self._is_excluded(mf, repo_path):
                has_library_manifest = True
                try:
                    content = mf.read_text(encoding="utf-8", errors="ignore").lower()
                    for fw in WEB_FRAMEWORK_PATTERNS:
                        if re.search(rf"\b{re.escape(fw)}\b", content):
                            found_web_framework = True
                            break
                except OSError:
                    pass

            if found_web_framework:
                break

        if found_web_framework:
            return True, None

        if has_library_manifest:
            return False, "pure_library_containerization_not_applicable"

        return True, None

    async def analyze(self, repo_path: Path) -> DockerResult:
        """Analyzes container readiness, health checks, security user, and compose setup."""

        def _sync_analyze() -> DockerResult:
            dockerfile = self._find_dockerfile(repo_path)
            has_dockerfile = dockerfile is not None
            has_docker_compose = self._find_docker_compose(repo_path)
            has_env_example = self._check_env_example(repo_path)

            has_healthcheck = False
            has_non_root_user = False
            has_multistage = False
            rel_df_path: str | None = None

            if dockerfile:
                try:
                    rel_df_path = str(dockerfile.relative_to(repo_path))
                except ValueError:
                    rel_df_path = str(dockerfile)

                has_healthcheck, has_non_root_user, has_multistage = self._parse_dockerfile(dockerfile)

            has_any_docker = has_dockerfile or has_docker_compose
            applicable, reason = self._is_containerization_applicable(repo_path, has_any_docker)

            if not applicable:
                return DockerResult(
                    score=100.0,
                    has_dockerfile=False,
                    has_healthcheck=False,
                    has_env_example=has_env_example,
                    has_docker_compose=False,
                    has_non_root_user=False,
                    has_multistage=False,
                    dockerfile_path=None,
                    applicable=False,
                    measured=False,
                    reason=reason,
                )

            if not has_dockerfile:
                return DockerResult(
                    score=0.0,
                    has_dockerfile=False,
                    has_healthcheck=False,
                    has_env_example=has_env_example,
                    has_docker_compose=has_docker_compose,
                    has_non_root_user=False,
                    has_multistage=False,
                    dockerfile_path=None,
                    applicable=True,
                    measured=True,
                    reason="dockerfile_missing",
                )

            score = 30.0
            if has_healthcheck:
                score += 25.0
            if has_non_root_user:
                score += 15.0
            if has_multistage:
                score += 10.0
            if has_env_example:
                score += 10.0
            if has_docker_compose:
                score += 10.0

            return DockerResult(
                score=min(100.0, round(score, 1)),
                has_dockerfile=True,
                has_healthcheck=has_healthcheck,
                has_env_example=has_env_example,
                has_docker_compose=has_docker_compose,
                has_non_root_user=has_non_root_user,
                has_multistage=has_multistage,
                dockerfile_path=rel_df_path,
                applicable=True,
                measured=True,
                reason=None,
            )

        return await asyncio.to_thread(_sync_analyze)
