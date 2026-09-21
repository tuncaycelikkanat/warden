"""Dependency health and supply-chain vulnerability analyzer via OSV.dev and package risk checks."""

import asyncio
import logging
import re
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from core.services.package import PackageCheckerService

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    """Represents a security vulnerability identified via OSV.dev database."""

    cve_id: str
    summary: str
    details: str

    @classmethod
    def from_osv(cls, data: dict[str, Any]) -> "Vulnerability":
        """Constructs a Vulnerability instance from raw OSV API JSON."""
        return cls(
            cve_id=data.get("id", "Unknown"),
            summary=data.get("summary", "No summary provided"),
            details=data.get("details", ""),
        )


@dataclass
class PackageAuditEntry:
    """Audit status and vulnerability findings for a single dependency."""

    name: str
    version: str | None
    integrity_verdict: dict[str, Any]
    known_vulnerabilities: list[Vulnerability]
    status: str  # "ok", "failed_check", "version_unpinned"
    note: str = ""


@dataclass
class ManifestParseResult:
    """Result of parsing package manifests, tracking packages and skipped lines."""

    packages: list[dict[str, Any]]
    skipped_lines: list[dict[str, str]] = field(default_factory=list)

    def __iter__(self) -> Any:
        """Allows iterating over packages directly."""
        return iter(self.packages)

    def __len__(self) -> int:
        return len(self.packages)

    def __getitem__(self, index: int) -> dict[str, Any]:
        return self.packages[index]


@dataclass
class DependencyHealthResult:
    """Represents aggregated dependency health and vulnerability findings."""

    entries: list[PackageAuditEntry]
    skipped_lines: list[dict[str, str]] = field(default_factory=list)
    unpinned_packages: list[str] = field(default_factory=list)


class OsvCache:
    """In-memory cache for OSV.dev vulnerability queries (24h TTL)."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl = ttl_seconds
        self._cache: dict[tuple[str, str, str], tuple[float, list[dict[str, Any]]]] = {}

    def get(self, ecosystem: str, name: str, version: str) -> list[Vulnerability] | None:
        """Returns cached vulnerabilities if not expired, or None."""
        key = (ecosystem.lower(), name.lower(), version)
        cached = self._cache.get(key)
        if cached:
            ts, raw_vulns = cached
            if time.time() - ts < self.ttl:
                return [Vulnerability.from_osv(v) for v in raw_vulns]
            del self._cache[key]
        return None

    def set(self, ecosystem: str, name: str, version: str, vulns_raw: list[dict[str, Any]]) -> None:
        """Stores query results with current timestamp."""
        key = (ecosystem.lower(), name.lower(), version)
        self._cache[key] = (time.time(), vulns_raw)

    def clear(self) -> None:
        """Flushes cache."""
        self._cache.clear()


class DependencyHealthService:
    """Service to audit package dependencies for CVEs and supply-chain risks."""

    def __init__(self) -> None:
        """Initializes HTTP client, package checker, and OSV query cache."""
        self._integrity_checker = PackageCheckerService()
        self._http = httpx.AsyncClient(timeout=10.0)
        self._osv_cache = OsvCache(ttl_seconds=86400)

    async def close(self) -> None:
        """Closes underlying HTTP client session."""
        await self._http.aclose()

    def _parse_requirements_content(self, content: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Parses requirements.txt text into packages and skipped lines."""
        packages: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Strip inline comment if any
            if " #" in line:
                line = line.split(" #", 1)[0].strip()

            # Handle pip options / local paths
            if line.startswith(("-", "./", "../", "/")):
                skipped.append({"line": raw_line.strip(), "reason": "pip_option_or_local_path"})
                continue

            # Handle VCS URLs
            if any(line.startswith(proto) for proto in ("git+", "hg+", "svn+", "bzr+", "http://", "https://")):
                egg_match = re.search(r"#egg=([a-zA-Z0-9_\-\.]+)", line)
                if egg_match:
                    packages.append({"name": egg_match.group(1), "version": None, "ecosystem": "PyPI", "pinned": False})
                else:
                    skipped.append({"line": raw_line.strip(), "reason": "vcs_url_without_egg"})
                continue

            # Match package name, optional [extras], and optional version constraint
            # Examples:
            #   requests==2.31.0
            #   celery[redis]==5.3.0
            #   urllib3>=1.26.0,<2.0.0
            #   black
            match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[([a-zA-Z0-9_\-,\s]+)\])?\s*(.*)$", line)
            if not match:
                skipped.append({"line": raw_line.strip(), "reason": "unrecognized_syntax"})
                continue

            name = match.group(1)
            specifiers = match.group(3).strip()

            if not specifiers:
                # Completely unpinned
                packages.append({"name": name, "version": None, "ecosystem": "PyPI", "pinned": False})
            else:
                # Exact pinned: ==X.Y.Z
                pinned_match = re.match(r"^==\s*([a-zA-Z0-9_\.\-]+)$", specifiers)
                if pinned_match:
                    version = pinned_match.group(1)
                    packages.append({"name": name, "version": version, "ecosystem": "PyPI", "pinned": True})
                else:
                    # Inequality or range constraint (e.g. >=, <=, ~=, multiple)
                    packages.append(
                        {
                            "name": name,
                            "version": None,
                            "constraint": specifiers,
                            "ecosystem": "PyPI",
                            "pinned": False,
                        }
                    )

        return packages, skipped

    def _parse_manifest(self, repo_path: Path) -> ManifestParseResult:
        """Parses requirements.txt or pyproject.toml and returns packages and skipped lines."""
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            content = req_file.read_text(encoding="utf-8", errors="ignore")
            pkgs, skipped = self._parse_requirements_content(content)
            return ManifestParseResult(packages=pkgs, skipped_lines=skipped)

        # Fallback to pyproject.toml if requirements.txt doesn't exist
        pyproject_file = repo_path / "pyproject.toml"
        if pyproject_file.exists():
            try:
                data = tomllib.loads(pyproject_file.read_text(encoding="utf-8", errors="ignore"))
                deps = data.get("project", {}).get("dependencies", [])
                if isinstance(deps, list) and deps:
                    pkgs, skipped = self._parse_requirements_content("\n".join(str(d) for d in deps))
                    return ManifestParseResult(packages=pkgs, skipped_lines=skipped)
            except Exception as e:
                logger.warning(f"Failed to parse pyproject.toml in {repo_path}: {e}")

        return ManifestParseResult(packages=[], skipped_lines=[])

    async def _query_osv(self, name: str, version: str | None, ecosystem: str) -> list[Vulnerability]:
        """Queries OSV.dev for known vulnerabilities with caching."""
        if not version:
            return []

        # Check in-memory cache
        cached = self._osv_cache.get(ecosystem, name, version)
        if cached is not None:
            return cached

        payload = {
            "package": {"name": name, "ecosystem": ecosystem},
            "version": version,
        }

        try:
            response = await self._http.post("https://api.osv.dev/v1/query", json=payload)
            response.raise_for_status()
            data = response.json()
            vulns_raw = data.get("vulns", [])
            self._osv_cache.set(ecosystem, name, version, vulns_raw)
            return [Vulnerability.from_osv(v) for v in vulns_raw]
        except httpx.RequestError as e:
            logger.warning(f"OSV query failed for {name}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Unexpected error querying OSV for {name}: {e}")
            return []

    async def check_manifest(self, repo_path: Path) -> DependencyHealthResult:
        """Audits all packages in manifest for known CVEs and supply-chain anomalies."""
        parse_result = self._parse_manifest(repo_path)
        packages = parse_result.packages
        skipped = parse_result.skipped_lines

        async def process_package(pkg: dict[str, Any]) -> PackageAuditEntry:
            name = pkg["name"]
            version = pkg.get("version")
            ecosystem = pkg.get("ecosystem", "PyPI")
            is_pinned = pkg.get("pinned", version is not None)

            # 1. Check integrity (PackageCheckerService)
            note = ""
            try:
                integrity = await self._integrity_checker.calculate_risk_score(name)
                risk_level = integrity.get("risk_level", "low")
                if risk_level == "high":
                    status = "failed_check"
                    note = "; ".join(integrity.get("details", []))
                elif not is_pinned or not version:
                    status = "version_unpinned"
                    constraint_note = f" ({pkg.get('constraint')})" if pkg.get("constraint") else ""
                    note = f"Sürüm sabitlenmemiş{constraint_note}; bilinen CVE taraması yapılamadı."
                else:
                    status = "ok"
                    if risk_level == "review":
                        note = "; ".join(integrity.get("details", []))
            except Exception as e:
                logger.error(f"Integrity check failed for {name}: {e}")
                integrity = {"risk_level": "UNKNOWN", "details": [str(e)]}
                status = "failed_check"
                note = f"Paket doğrulama hatası: {e}"

            # 2. Check known vulnerabilities (OSV)
            vulns: list[Vulnerability] = []
            if version:
                vulns = await self._query_osv(name, version, ecosystem)

            return PackageAuditEntry(
                name=name,
                version=version,
                integrity_verdict=integrity,
                known_vulnerabilities=vulns,
                status=status,
                note=note,
            )

        entries = await asyncio.gather(*(process_package(pkg) for pkg in packages))
        unpinned_list = [e.name for e in entries if e.status == "version_unpinned"]

        return DependencyHealthResult(
            entries=list(entries),
            skipped_lines=skipped,
            unpinned_packages=unpinned_list,
        )
