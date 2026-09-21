"""Service to detect a repository's own license from LICENSE files and project manifests."""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LICENSE_CATEGORY_MAP: dict[str, str] = {
    # Permissive
    "MIT": "permissive",
    "Apache-2.0": "permissive",
    "BSD-3-Clause": "permissive",
    "BSD-2-Clause": "permissive",
    "ISC": "permissive",
    "Python-2.0": "permissive",
    "Unlicense": "permissive",
    "CC0-1.0": "permissive",
    # Weak Copyleft
    "LGPL-2.1-only": "weak_copyleft",
    "LGPL-2.1-or-later": "weak_copyleft",
    "LGPL-3.0-only": "weak_copyleft",
    "LGPL-3.0-or-later": "weak_copyleft",
    "MPL-2.0": "weak_copyleft",
    "EPL-2.0": "weak_copyleft",
    # Strong Copyleft
    "GPL-2.0-only": "strong_copyleft",
    "GPL-2.0-or-later": "strong_copyleft",
    "GPL-3.0-only": "strong_copyleft",
    "GPL-3.0-or-later": "strong_copyleft",
    "AGPL-3.0-only": "strong_copyleft",
    "AGPL-3.0-or-later": "strong_copyleft",
}


@dataclass
class RepoLicenseInfo:
    """Represents detected licensing information for the current repository."""

    spdx_id: str | None
    source: str | None
    confidence: str  # "high", "medium", "none"
    category: str  # "permissive", "weak_copyleft", "strong_copyleft", "all_rights_reserved_by_default"


class RepoLicenseDetector:
    """Detects repository license from LICENSE files and pyproject.toml."""

    def _match_text_to_spdx(self, text: str) -> str | None:
        """Matches common license body text snippets to standard SPDX IDs."""
        upper = text.upper()

        if "AFFERO GENERAL PUBLIC LICENSE" in upper:
            return "AGPL-3.0-only"

        if "LESSER GENERAL PUBLIC LICENSE" in upper:
            if "VERSION 3" in upper or "3.0" in upper:
                return "LGPL-3.0-only"
            return "LGPL-2.1-only"

        if "GNU GENERAL PUBLIC LICENSE" in upper:
            if "VERSION 3" in upper or "GPLV3" in upper or "VERSION 3, 29 JUNE 2007" in upper:
                return "GPL-3.0-only"
            if "VERSION 2" in upper or "GPLV2" in upper:
                return "GPL-2.0-only"
            return "GPL-3.0-only"

        if "APACHE LICENSE" in upper and ("VERSION 2.0" in upper or "2.0" in upper):
            return "Apache-2.0"

        if "PERMISSION IS HEREBY GRANTED, FREE OF CHARGE" in upper or "MIT LICENSE" in upper:
            return "MIT"

        if "MOZILLA PUBLIC LICENSE" in upper and "2.0" in upper:
            return "MPL-2.0"

        if "REDISTRIBUTION AND USE IN SOURCE AND BINARY FORMS" in upper:
            if "NEITHER THE NAME OF" in upper or "CLAUSE" in upper:
                return "BSD-3-Clause"
            return "BSD-2-Clause"

        if "PERMISSION TO USE, COPY, MODIFY, AND/OR DISTRIBUTE THIS SOFTWARE" in upper:
            return "ISC"

        if "FREE AND UNENCUMBERED SOFTWARE RELEASED INTO THE PUBLIC DOMAIN" in upper:
            return "Unlicense"

        return None

    def _extract_from_pyproject(self, pyproject_path: Path) -> str | None:
        """Extracts license definition or classifier from pyproject.toml."""
        try:
            data: dict[str, Any] = tomllib.loads(pyproject_path.read_text(encoding="utf-8", errors="ignore"))
        except Exception as e:
            logger.warning(f"Failed to parse pyproject.toml: {e}")
            return None

        # 1. Check project.license
        project = data.get("project", {})
        lic_field = project.get("license")
        if isinstance(lic_field, str) and lic_field.strip():
            matched = self._match_text_to_spdx(lic_field)
            if matched:
                return matched
            return lic_field.strip()
        elif isinstance(lic_field, dict):
            text = lic_field.get("text", "")
            if text:
                matched = self._match_text_to_spdx(text)
                if matched:
                    return matched
                return text

        # 2. Check project.classifiers
        classifiers = project.get("classifiers", [])
        for c in classifiers:
            if isinstance(c, str) and "License ::" in c:
                if "MIT" in c:
                    return "MIT"
                if "Apache" in c:
                    return "Apache-2.0"
                if "GPLv3" in c or "General Public License v3" in c:
                    return "GPL-3.0-only"
                if "GPLv2" in c or "General Public License v2" in c:
                    return "GPL-2.0-only"
                if "BSD" in c:
                    return "BSD-3-Clause"
                if "Mozilla Public License" in c:
                    return "MPL-2.0"

        return None

    def detect(self, repo_path: Path) -> RepoLicenseInfo:
        """
        Detects repo license from files or project metadata.
        Falls back to 'all_rights_reserved_by_default' when no license file exists.
        """
        candidate_files = [
            "LICENSE",
            "LICENSE.txt",
            "LICENSE.md",
            "LICENSE.rst",
            "COPYING",
            "COPYING.LESSER",
        ]

        for fname in candidate_files:
            file_path = repo_path / fname
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    spdx = self._match_text_to_spdx(content)
                    if spdx:
                        category = LICENSE_CATEGORY_MAP.get(spdx, "permissive")
                        return RepoLicenseInfo(
                            spdx_id=spdx,
                            source=fname,
                            confidence="high",
                            category=category,
                        )
                except Exception as e:
                    logger.warning(f"Failed to read {fname}: {e}")

        # Check pyproject.toml
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            spdx = self._extract_from_pyproject(pyproject)
            if spdx:
                category = LICENSE_CATEGORY_MAP.get(spdx, "permissive")
                return RepoLicenseInfo(
                    spdx_id=spdx,
                    source="pyproject.toml",
                    confidence="medium",
                    category=category,
                )

        # Default legal state when no license is granted: All Rights Reserved
        return RepoLicenseInfo(
            spdx_id=None,
            source=None,
            confidence="none",
            category="all_rights_reserved_by_default",
        )
