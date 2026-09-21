"""CI/CD configuration presence and validity analyzer."""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.services.shared.scan_exclusions import get_scan_exclusions

logger = logging.getLogger(__name__)

AUTOMATIC_TRIGGERS = {
    "push",
    "pull_request",
    "merge_request",
    "schedule",
    "release",
    "merge_request_event",
    "default",
    "branches",
    "pr",
    "trigger",
}

CI_FILE_PATTERNS = [
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    "Jenkinsfile",
    ".travis.yml",
    "bitbucket-pipelines.yml",
    "azure-pipelines.yml",
    ".drone.yml",
    ".woodpecker.yml",
]


@dataclass
class CiCdFileResult:
    """Represents analysis of an individual CI/CD configuration file."""

    file: str
    valid_yaml: bool
    has_job_content: bool
    has_automatic_trigger: bool
    trigger_keys: set[str] = field(default_factory=set)
    reason: str | None = None


@dataclass
class CiCdResult:
    """Represents CI/CD configuration analysis results."""

    score: float
    has_file: bool
    has_valid_content: bool
    has_automatic_trigger: bool = False
    files: list[CiCdFileResult] = field(default_factory=list)
    measured: bool = True
    reason: str | None = None


class CiCdPresenceService:
    """Service to detect and evaluate CI/CD workflow configurations with structural YAML validation."""

    async def analyze(self, repo_path: Path) -> CiCdResult:
        """Analyzes the repository for valid CI/CD workflow configurations."""
        return await asyncio.to_thread(self._check_cicd, repo_path)

    def _is_excluded(self, file_path: Path, repo_path: Path) -> bool:
        """Checks if a CI file is located inside an excluded folder such as examples or vendor."""
        try:
            rel = file_path.relative_to(repo_path)
        except ValueError:
            rel = file_path

        exclusions = set(get_scan_exclusions(repo_path, extra=["examples", "example", "vendor", "test_data", "fixtures"]))
        return any(part in exclusions or part.startswith(".") for part in rel.parts[:-1] if part != ".github" and part != ".circleci")

    def _discover_ci_files(self, repo_path: Path) -> list[Path]:
        """Discovers CI/CD configuration files while respecting central exclusions."""
        ci_files: list[Path] = []

        # 1. GitHub workflows
        gh_dir = repo_path / ".github" / "workflows"
        if gh_dir.is_dir():
            for ext in ("*.yml", "*.yaml"):
                for p in gh_dir.glob(ext):
                    if p.is_file() and not self._is_excluded(p, repo_path):
                        ci_files.append(p)

        # 2. CircleCI
        circle_cfg = repo_path / ".circleci" / "config.yml"
        if circle_cfg.is_file() and not self._is_excluded(circle_cfg, repo_path):
            ci_files.append(circle_cfg)

        # 3. Root-level standard CI files
        root_patterns = [
            ".gitlab-ci.yml",
            "Jenkinsfile",
            ".travis.yml",
            "bitbucket-pipelines.yml",
            "azure-pipelines.yml",
            ".drone.yml",
            ".woodpecker.yml",
        ]
        for name in root_patterns:
            p = repo_path / name
            if p.is_file() and not self._is_excluded(p, repo_path):
                ci_files.append(p)

        return sorted(ci_files)

    def _extract_github_triggers(self, parsed: dict[Any, Any]) -> set[str]:
        """Extracts trigger keys from GitHub Actions workflow handling PyYAML boolean parsing quirks."""
        # In YAML 1.1, unquoted 'on' is parsed as boolean True
        on_val = parsed.get("on") if "on" in parsed else parsed.get(True)
        triggers: set[str] = set()

        if isinstance(on_val, str):
            triggers.add(on_val.strip().lower())
        elif isinstance(on_val, list):
            for item in on_val:
                if isinstance(item, str):
                    triggers.add(item.strip().lower())
                elif item is True:
                    triggers.add("on")
        elif isinstance(on_val, dict):
            for k in on_val:
                triggers.add(str(k).strip().lower())

        return triggers

    def _is_jenkinsfile(self, content: str) -> bool:
        """Determines if a Jenkinsfile contains structural pipeline content."""
        lower = content.lower()
        return any(k in lower for k in ("pipeline", "stages", "node", "stage("))

    def _analyze_ci_file(self, file_path: Path, repo_path: Path) -> CiCdFileResult:
        """Parses and validates a single CI/CD file."""
        rel_str = str(file_path.relative_to(repo_path)) if file_path.is_relative_to(repo_path) else str(file_path)

        try:
            raw_content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            return CiCdFileResult(
                file=rel_str,
                valid_yaml=False,
                has_job_content=False,
                has_automatic_trigger=False,
                reason=f"read_error: {e}",
            )

        # Jenkinsfile handling (Groovy syntax)
        if file_path.name == "Jenkinsfile":
            has_jobs = self._is_jenkinsfile(raw_content)
            return CiCdFileResult(
                file=rel_str,
                valid_yaml=True,
                has_job_content=has_jobs,
                has_automatic_trigger=has_jobs,
                trigger_keys={"push"} if has_jobs else set(),
            )

        # YAML parsing
        try:
            parsed = yaml.safe_load(raw_content)
        except (yaml.YAMLError, ValueError, TypeError) as e:
            return CiCdFileResult(
                file=rel_str,
                valid_yaml=False,
                has_job_content=False,
                has_automatic_trigger=False,
                reason=f"yaml_parse_error: {e}",
            )

        if not isinstance(parsed, dict):
            return CiCdFileResult(
                file=rel_str,
                valid_yaml=False,
                has_job_content=False,
                has_automatic_trigger=False,
                reason="not_a_mapping",
            )

        # Determine job content and triggers based on CI platform
        trigger_keys: set[str] = set()
        has_job_content = False

        if ".github" in rel_str:
            jobs = parsed.get("jobs")
            has_job_content = isinstance(jobs, dict) and len(jobs) > 0
            trigger_keys = self._extract_github_triggers(parsed)
        elif "gitlab" in rel_str:
            has_job_content = "stages" in parsed or any(
                isinstance(v, dict) and ("script" in v or "stage" in v) for v in parsed.values()
            )
            trigger_keys = {"push"}
        elif "circleci" in rel_str:
            has_job_content = isinstance(parsed.get("jobs"), dict) or "workflows" in parsed
            trigger_keys = {"push"}
        elif "bitbucket" in rel_str:
            has_job_content = "pipelines" in parsed and isinstance(parsed["pipelines"], dict)
            trigger_keys = {"push"}
        elif "azure" in rel_str:
            has_job_content = any(k in parsed for k in ("jobs", "stages", "steps"))
            trigger = parsed.get("trigger")
            if trigger != "none":
                trigger_keys = {"push"}
        else:
            # Drone, Woodpecker, Travis or Generic
            has_job_content = any(k in parsed for k in ("jobs", "stages", "steps", "pipeline", "kind"))
            trigger_keys = {"push"}

        has_auto = bool(trigger_keys & AUTOMATIC_TRIGGERS)

        return CiCdFileResult(
            file=rel_str,
            valid_yaml=True,
            has_job_content=has_job_content,
            has_automatic_trigger=has_auto,
            trigger_keys=trigger_keys,
            reason=None,
        )

    def _check_cicd(self, repo_path: Path) -> CiCdResult:
        """Main check logic for CI/CD presence and tiered scoring."""
        ci_files = self._discover_ci_files(repo_path)
        if not ci_files:
            return CiCdResult(
                score=0.0,
                has_file=False,
                has_valid_content=False,
                has_automatic_trigger=False,
                files=[],
                measured=True,
                reason="no_cicd_files_found",
            )

        file_results = [self._analyze_ci_file(f, repo_path) for f in ci_files]
        valid_job_files = [r for r in file_results if r.valid_yaml and r.has_job_content]

        if not valid_job_files:
            # Files exist, but content is invalid YAML or has no jobs/stages
            return CiCdResult(
                score=25.0,
                has_file=True,
                has_valid_content=False,
                has_automatic_trigger=False,
                files=file_results,
                measured=True,
                reason="cicd_files_lack_valid_jobs",
            )

        has_auto = any(r.has_automatic_trigger for r in valid_job_files)
        # Tiered scoring: 100 for automatic triggers, 60 for manual dispatch only (dead pipeline)
        score = 100.0 if has_auto else 60.0

        return CiCdResult(
            score=score,
            has_file=True,
            has_valid_content=True,
            has_automatic_trigger=has_auto,
            files=file_results,
            measured=True,
            reason=None,
        )
