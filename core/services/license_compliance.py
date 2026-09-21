"""Service to analyze third-party dependency licenses and identify copyleft or unknown licenses."""

import asyncio
import json
import logging
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.services.repo_license_detector import (
    LICENSE_CATEGORY_MAP,
    RepoLicenseDetector,
    RepoLicenseInfo,
)

logger = logging.getLogger(__name__)


@dataclass
class LicenseResult:
    """Represents the license compliance scan results for third-party dependencies."""

    score: float | None
    copyleft_count: int
    unknown_count: int
    dependencies: list[dict[str, Any]]
    repo_license: str | None = None
    repo_category: str | None = None
    measured: bool = True
    method: str = "pip-licenses"  # "pip-licenses", "static_fallback", "empty_repo", "unmeasured"
    note: str = ""


# Fallback development and test tools that are not distributed application dependencies
FALLBACK_DEV_TOOL_PACKAGES = {
    "semgrep",
    "pip-licenses",
    "pytest",
    "ruff",
    "mypy",
    "interrogate",
    "radon",
    "coverage",
    "levenshtein",
    "black",
    "flake8",
    "isort",
    "tox",
    "pre-commit",
    "sphinx",
    "build",
    "twine",
}

# Known package licenses for static fallback or packages with missing wheel metadata
KNOWN_PACKAGE_LICENSES: dict[str, str] = {
    "peewee": "MIT",
    "face": "BSD-3-Clause",
    "requests": "Apache-2.0",
    "urllib3": "MIT",
    "certifi": "MPL-2.0",
    "charset-normalizer": "MIT",
    "idna": "BSD-3-Clause",
    "fastapi": "MIT",
    "pydantic": "MIT",
    "pydantic-core": "MIT",
    "httpx": "BSD-3-Clause",
    "httpcore": "BSD-3-Clause",
    "uvicorn": "BSD-3-Clause",
    "sqlmodel": "MIT",
    "sqlalchemy": "MIT",
    "python-dotenv": "BSD-3-Clause",
    "click": "BSD-3-Clause",
    "flask": "BSD-3-Clause",
    "jinja2": "BSD-3-Clause",
    "starlette": "BSD-3-Clause",
    "anyio": "MIT",
    "sniffio": "MIT",
    "google-genai": "Apache-2.0",
    "mcp": "MIT",
}

_NORMALIZATION_MAP: dict[str, str] | None = None


def _get_normalization_map() -> dict[str, str]:
    """Loads normalization dictionary from core/data/license_normalization_map.json."""
    global _NORMALIZATION_MAP
    if _NORMALIZATION_MAP is not None:
        return _NORMALIZATION_MAP

    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "license_normalization_map.json",
        Path("core/data/license_normalization_map.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                _NORMALIZATION_MAP = json.loads(p.read_text(encoding="utf-8"))
                return _NORMALIZATION_MAP
            except Exception as e:
                logger.warning(f"Failed to load license normalization map: {e}")

    _NORMALIZATION_MAP = {}
    return _NORMALIZATION_MAP


def normalize_license(raw_text: str | None) -> str | None:
    """
    Normalizes free-text license descriptions into standard SPDX identifiers.
    Returns None if the license text cannot be recognized.
    """
    if not raw_text or not raw_text.strip():
        return None

    clean = raw_text.strip()
    norm_map = _get_normalization_map()

    # 1. Exact match in normalization map
    key = clean.lower()
    if key in norm_map:
        return norm_map[key]

    # 2. Direct SPDX ID match
    if clean in LICENSE_CATEGORY_MAP:
        return clean

    # 3. Simple heuristic matching
    upper = clean.upper()
    if "AGPL" in upper:
        return "AGPL-3.0-only"
    if "LGPL" in upper:
        return "LGPL-3.0-only" if ("3" in upper) else "LGPL-2.1-only"
    if "GPL" in upper:
        if "3" in upper or "V3" in upper:
            return "GPL-3.0-only"
        if "2" in upper or "V2" in upper:
            return "GPL-2.0-only"
        return "GPL-3.0-only"
    if "APACHE" in upper:
        return "Apache-2.0"
    if "MIT" in upper:
        return "MIT"
    if "BSD" in upper:
        return "BSD-3-Clause"
    if "MOZILLA" in upper or "MPL" in upper:
        return "MPL-2.0"
    if "ISC" in upper:
        return "ISC"

    return None


def resolve_multi_license(raw_text: str | None) -> str | None:
    """
    Resolves multi-license expressions (OR / AND).
    For 'OR': picks the most permissive option available.
    For 'AND': picks the most restrictive option (must comply with both).
    """
    if not raw_text or not raw_text.strip():
        return None

    priority_permissive = {"permissive": 0, "weak_copyleft": 1, "strong_copyleft": 2, "unknown": 3}
    priority_restrictive = {"strong_copyleft": 0, "weak_copyleft": 1, "permissive": 2, "unknown": 3}

    if " OR " in raw_text:
        parts = [p.strip() for p in raw_text.split(" OR ")]
        normalized_options = [normalize_license(p) for p in parts]
        valid_options = [opt for opt in normalized_options if opt]
        if not valid_options:
            return None
        return min(
            valid_options,
            key=lambda o: priority_permissive.get(LICENSE_CATEGORY_MAP.get(o, "unknown"), 3),
        )

    if " AND " in raw_text:
        parts = [p.strip() for p in raw_text.split(" AND ")]
        normalized_options = [normalize_license(p) for p in parts]
        valid_options = [opt for opt in normalized_options if opt]
        if not valid_options:
            return None
        return min(
            valid_options,
            key=lambda o: priority_restrictive.get(LICENSE_CATEGORY_MAP.get(o, "unknown"), 3),
        )

    return normalize_license(raw_text)


def _load_dev_dependency_names(repo_path: Path) -> set[str]:
    """
    Extracts developer and test dependencies from project manifests.
    Falls back to common dev tool names if no manifest separation exists.
    """
    names: set[str] = set()

    # 1. pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
            # PEP 621 optional-dependencies
            opt_deps = data.get("project", {}).get("optional-dependencies", {})
            for group in ("dev", "test", "lint", "docs", "testing"):
                if group in opt_deps and isinstance(opt_deps[group], list):
                    for d in opt_deps[group]:
                        pkg_match = re.match(r"^([a-zA-Z0-9_\-\.]+)", str(d))
                        if pkg_match:
                            names.add(pkg_match.group(1).lower())

            # Poetry dependency groups
            poetry_groups = data.get("tool", {}).get("poetry", {}).get("group", {})
            for group in ("dev", "test", "lint", "docs", "testing"):
                if group in poetry_groups:
                    deps = poetry_groups[group].get("dependencies", {})
                    for dep_name in deps:
                        names.add(dep_name.lower())
        except Exception as e:
            logger.warning(f"Failed to extract dev dependencies from pyproject.toml: {e}")

    # 2. dev-requirements.txt or requirements-dev.txt
    for dev_file in ("dev-requirements.txt", "requirements-dev.txt", "test-requirements.txt"):
        dev_req = repo_path / dev_file
        if dev_req.exists():
            try:
                for line in dev_req.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith(("#", "-")):
                        pkg_match = re.match(r"^([a-zA-Z0-9_\-\.]+)", line)
                        if pkg_match:
                            names.add(pkg_match.group(1).lower())
            except Exception as e:
                logger.warning(f"Failed to extract dev dependencies from {dev_file}: {e}")

    # Merge with core fallback dev tools
    return names | {pkg.lower() for pkg in FALLBACK_DEV_TOOL_PACKAGES}


class LicenseComplianceService:
    """Service to audit third-party dependency licenses with repository compatibility."""

    def __init__(self) -> None:
        self._detector = RepoLicenseDetector()

    def _run_pip_licenses(self, repo_path: Path) -> list[dict[str, Any]]:
        """Executes pip-licenses to extract installed JSON dependency licensing metadata."""
        try:
            subprocess.run(
                ["uv", "pip", "install", "pip-licenses"],
                cwd=str(repo_path),
                capture_output=True,
                check=False,
                timeout=15,
            )
            res = subprocess.run(
                ["uv", "run", "pip-licenses", "--format=json"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if not res.stdout.strip():
                return []
            return json.loads(res.stdout)
        except Exception as e:
            logger.warning(f"pip-licenses execution failed in {repo_path}: {e}")
            return []

    def _static_fallback(self, repo_path: Path) -> list[dict[str, Any]]:
        """Extracts packages from manifest and matches against known license registry."""
        packages: list[str] = []

        # Read requirements.txt
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-", "./", "../", "/")):
                    match = re.match(r"^([a-zA-Z0-9_\-\.]+)", line)
                    if match:
                        packages.append(match.group(1).lower())

        # Read pyproject.toml if no requirements found
        if not packages:
            pyproject = repo_path / "pyproject.toml"
            if pyproject.exists():
                try:
                    data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
                    deps = data.get("project", {}).get("dependencies", [])
                    for d in deps:
                        match = re.match(r"^([a-zA-Z0-9_\-\.]+)", str(d))
                        if match:
                            packages.append(match.group(1).lower())
                except Exception:
                    pass

        results: list[dict[str, Any]] = []
        for pkg in packages:
            lic = KNOWN_PACKAGE_LICENSES.get(pkg, "UNKNOWN")
            results.append({"Name": pkg, "License": lic, "source": "static_fallback"})

        return results

    def _evaluate_compatibility(
        self, repo_license: RepoLicenseInfo, dep_category: str
    ) -> tuple[str, float]:
        """
        Evaluates risk level and scorecard penalty based on compatibility matrix.
        Returns (risk_level, penalty).
        """
        if repo_license.category == "all_rights_reserved_by_default":
            # Most restrictive repo state: proprietary/no-license
            if dep_category == "strong_copyleft":
                return "high", 20.0
            if dep_category == "weak_copyleft":
                return "medium", 8.0
            if dep_category == "unknown":
                return "medium", 5.0
            return "none", 0.0

        if repo_license.category == "strong_copyleft":
            # GPL/AGPL repository: fully compatible with GPL/AGPL dependencies
            if dep_category == "unknown":
                return "low", 5.0
            return "none", 0.0

        # Permissive or weak copyleft project
        if dep_category == "strong_copyleft":
            return "high", 20.0
        if dep_category == "weak_copyleft":
            return "low", 3.0
        if dep_category == "unknown":
            return "low", 5.0

        return "none", 0.0

    async def analyze(self, repo_path: Path) -> LicenseResult:
        """Analyzes dependency licenses and repo license compatibility."""
        repo_info = self._detector.detect(repo_path)
        dev_packages = _load_dev_dependency_names(repo_path)

        # 1. Try pip-licenses
        deps = await asyncio.to_thread(self._run_pip_licenses, repo_path)
        method = "pip-licenses"

        # 2. If pip-licenses returned nothing, attempt static fallback
        if not deps:
            deps = self._static_fallback(repo_path)
            method = "static_fallback"

        # 3. Check if repository genuinely has zero dependencies
        req_exists = (repo_path / "requirements.txt").exists()
        pyproject_exists = (repo_path / "pyproject.toml").exists()

        if not deps:
            if req_exists or pyproject_exists:
                # Manifest exists but dependencies could not be resolved -> Unmeasured
                return LicenseResult(
                    score=None,
                    copyleft_count=0,
                    unknown_count=0,
                    dependencies=[],
                    repo_license=repo_info.spdx_id,
                    repo_category=repo_info.category,
                    measured=False,
                    method="unmeasured",
                    note="Bağımlılık lisansları çözümlenemedi (sanal ortam veya paket bulunamadı).",
                )
            else:
                # Genuinely zero-dependency repository
                return LicenseResult(
                    score=100.0,
                    copyleft_count=0,
                    unknown_count=0,
                    dependencies=[],
                    repo_license=repo_info.spdx_id,
                    repo_category=repo_info.category,
                    measured=True,
                    method="empty_repo",
                    note="Projeye ait bağımlılık manifesti bulunmuyor.",
                )

        # Determine root project name to avoid auditing the project itself as a dependency
        root_pkg_name = repo_path.resolve().name.lower().replace("-", "_")
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                pdata = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
                pname = pdata.get("project", {}).get("name")
                if pname:
                    root_pkg_name = str(pname).lower().replace("-", "_")
            except Exception:
                pass

        copyleft_count = 0
        unknown_count = 0
        total_penalty = 0.0
        dep_list: list[dict[str, Any]] = []

        for dep in deps:
            raw_name = dep.get("Name", "Unknown")
            name_lower = raw_name.lower()

            # Skip the package itself if installed in editable mode
            if name_lower.replace("-", "_") == root_pkg_name:
                continue
            raw_license = dep.get("License", "Unknown")

            # Fallback for known packages if UNKNOWN
            if name_lower in KNOWN_PACKAGE_LICENSES and (
                "UNKNOWN" in raw_license.upper() or not raw_license.strip()
            ):
                raw_license = KNOWN_PACKAGE_LICENSES[name_lower]

            is_dev = name_lower in dev_packages
            resolved_spdx = resolve_multi_license(raw_license)
            dep_category = (
                LICENSE_CATEGORY_MAP.get(resolved_spdx, "permissive")
                if resolved_spdx
                else "unknown"
            )

            is_copyleft = dep_category in ("strong_copyleft", "weak_copyleft")
            is_unknown = dep_category == "unknown"

            risk_level = "none"
            penalty = 0.0

            if is_dev:
                # Dev / test dependencies are not distributed with application binaries
                status_note = f"Geliştirme/test bağımlılığı ({resolved_spdx or raw_license}); cezalandırılmadı."
            else:
                risk_level, penalty = self._evaluate_compatibility(repo_info, dep_category)
                if is_copyleft and penalty > 0:
                    copyleft_count += 1
                elif is_unknown and penalty > 0:
                    unknown_count += 1
                total_penalty += penalty
                status_note = f"Lisans: {resolved_spdx or raw_license} ({dep_category}), Risk: {risk_level}"

            dep_list.append(
                {
                    "name": raw_name,
                    "raw_license": raw_license,
                    "spdx_id": resolved_spdx,
                    "category": dep_category,
                    "is_dev": is_dev,
                    "is_copyleft": is_copyleft and not is_dev,
                    "is_unknown": is_unknown and not is_dev,
                    "risk_level": risk_level,
                    "penalty": penalty,
                    "note": status_note,
                }
            )

        final_score = max(0.0, min(100.0, 100.0 - total_penalty))

        return LicenseResult(
            score=final_score,
            copyleft_count=copyleft_count,
            unknown_count=unknown_count,
            dependencies=dep_list,
            repo_license=repo_info.spdx_id,
            repo_category=repo_info.category,
            measured=True,
            method=method,
            note=f"Proje Lisansı: {repo_info.spdx_id or 'Belirtilmemiş (Tüm Hakları Saklıdır)'}",
        )
