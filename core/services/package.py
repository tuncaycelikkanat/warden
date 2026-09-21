"""Service to verify Python package authenticity, downloads, and typosquatting risks."""

import json
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings in pure Python."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] + [0] * len(s2)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row
    return prev_row[-1]


_top_packages_cache: set[str] | None = None


def _get_top_packages() -> set[str]:
    """Loads and caches top 1000 PyPI package names."""
    global _top_packages_cache
    if _top_packages_cache is not None:
        return _top_packages_cache

    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "top_pypi_packages.json",
        Path("core/data/top_pypi_packages.json"),
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    _top_packages_cache = set(json.load(f))
                    return _top_packages_cache
            except Exception as e:
                logger.warning(f"Failed to load top packages from {p}: {e}")
    _top_packages_cache = set()
    return _top_packages_cache


class PackageCheckerService:
    """Service to inspect PyPI packages for existence, metrics, and typosquatting risks."""

    def __init__(self) -> None:
        """Initializes caches for metadata and download stats."""
        self._metadata_cache: dict[str, dict[str, Any] | None] = {}
        self._stats_cache: dict[str, int] = {}
        self._http_headers = {"User-Agent": "Warden/1.0 (Package Integrity Scanner)"}

    async def get_pypi_metadata(self, package_name: str) -> dict[str, Any] | None:
        """
        Fetches metadata for a given package from PyPI.
        Returns the parsed JSON dictionary, or None if the package does not exist.
        """
        pkg_key = package_name.lower()
        if pkg_key in self._metadata_cache:
            return self._metadata_cache[pkg_key]

        url = f"https://pypi.org/pypi/{package_name}/json"

        async with httpx.AsyncClient(timeout=10.0, headers=self._http_headers) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    self._metadata_cache[pkg_key] = data
                    return data
                elif response.status_code == 404:
                    self._metadata_cache[pkg_key] = None
                    return None
                else:
                    logger.warning(f"PyPI returned {response.status_code} for {package_name}")
                    return None
            except httpx.RequestError as e:
                logger.warning(f"Failed to fetch {package_name} from PyPI due to network: {e}")
                return {"_network_error": True, "error": str(e)}

    async def get_pypi_stats(self, package_name: str) -> int:
        """
        Fetches download stats from pypistats.org. Returns downloads in the last month.
        Returns 0 if it fails or is rate-limited.
        """
        pkg_key = package_name.lower()
        if pkg_key in self._stats_cache:
            return self._stats_cache[pkg_key]

        url = f"https://pypistats.org/api/packages/{package_name}/recent"
        async with httpx.AsyncClient(timeout=5.0, headers=self._http_headers) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    downloads = data.get("data", {}).get("last_month", 0)
                    self._stats_cache[pkg_key] = downloads
                    return downloads
                return 0
            except Exception as e:
                logger.warning(f"Failed to fetch pypistats for {package_name}: {e}")
                return 0

    def check_typosquatting(self, package_name: str) -> str | None:
        """
        Checks if the package name is suspiciously similar to a top 1000 PyPI package.
        Returns the name of the popular package it's mimicking, or None.
        """
        top_packages = _get_top_packages()
        if not top_packages:
            return None

        pkg_lower = package_name.lower()
        top_lower_map = {p.lower(): p for p in top_packages}

        if pkg_lower in top_lower_map:
            return None

        for popular_lower, popular_orig in top_lower_map.items():
            threshold = 1 if len(popular_lower) <= 4 else 2
            distance = _levenshtein_distance(pkg_lower, popular_lower)
            if 0 < distance <= threshold:
                return popular_orig

        return None

    def _evaluate_risk_level(
        self, typo_mimic: str | None, total_releases: int, stats: int
    ) -> tuple[str, list[str]]:
        """Evaluates categorical risk level and rationale based on multi-signal package metrics."""
        reasons = []
        if typo_mimic:
            # Multi-signal verification:
            # If the package has mature release history or significant downloads,
            # it is likely an established package (or legitimate coincidence) rather than typosquatting.
            if total_releases >= 10 or stats >= 10000:
                return "review", [
                    f"Benzer popüler paket ('{typo_mimic}') mevcut ancak paket köklü ({total_releases} sürüm, {stats} indirme); inceleme önerilir."
                ]
            return "high", [
                f"Typosquatting alert: suspiciously similar to popular package '{typo_mimic}' with low activity ({stats} downloads, {total_releases} releases)"
            ]

        if total_releases == 0:
            return "high", ["No releases found on PyPI"]

        if total_releases > 50 or stats > 10000:
            return "low", ["Popular and mature package"]

        risk_level = "low"
        if total_releases < 3:
            risk_level = "medium"
            reasons.append(f"Very few releases ({total_releases})")

        if 0 < stats < 1000:
            risk_level = "medium"
            reasons.append(f"Low download count ({stats} in last month)")

        if not reasons:
            reasons.append("Acceptable package health metrics")

        return risk_level, reasons

    async def calculate_risk_score(self, package_name: str) -> dict[str, Any]:
        """
        Calculates a risk score for a package based on PyPI metadata and stats.
        Returns a dict with 'risk_level' (low, medium, review, high) and 'details'.
        """
        top_packages = _get_top_packages()
        pkg_lower = package_name.lower()
        is_top = any(pkg_lower == p.lower() for p in top_packages)

        typo_mimic = self.check_typosquatting(package_name)
        metadata = await self.get_pypi_metadata(package_name)

        if metadata and metadata.get("_network_error"):
            # Network connectivity issue during audit (e.g. sandbox or offline)
            risk = "low" if is_top else "medium"
            return {
                "package": package_name,
                "risk_level": risk,
                "details": ["Ağ bağlantısı sağlanamadığı için PyPI doğrulaması atlandı."],
                "stats": {"downloads_last_month": 0, "total_releases": 0},
            }

        if not metadata:
            if is_top:
                return {
                    "package": package_name,
                    "risk_level": "low",
                    "details": ["Popular and mature package (top PyPI catalog)"],
                    "stats": {"downloads_last_month": 0, "total_releases": 0},
                }

            details = ["Package not found on PyPI"]
            if typo_mimic:
                details.append(f"Typosquatting alert: suspiciously similar to popular package '{typo_mimic}'")
            return {"package": package_name, "risk_level": "high", "details": details}

        stats = await self.get_pypi_stats(package_name)
        releases = metadata.get("releases", {})
        total_releases = len(releases)

        risk_level, reasons = self._evaluate_risk_level(typo_mimic, total_releases, stats)

        return {
            "package": package_name,
            "risk_level": risk_level,
            "details": reasons,
            "stats": {
                "downloads_last_month": stats,
                "total_releases": total_releases,
            },
        }
