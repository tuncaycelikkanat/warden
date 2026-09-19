import httpx
import logging
import json
import os
import Levenshtein
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class PackageCheckerService:
    async def get_pypi_metadata(self, package_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetches metadata for a given package from PyPI.
        Returns the parsed JSON dictionary, or None if the package does not exist.
        """
        url = f"https://pypi.org/pypi/{package_name}/json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.warning(f"PyPI returned {response.status_code} for {package_name}")
                    return None
            except httpx.RequestError as e:
                logger.error(f"Failed to fetch {package_name} from PyPI: {e}")
                return None

    async def get_pypi_stats(self, package_name: str) -> int:
        """
        Fetches download stats from pypistats.org. Returns downloads in the last month.
        Returns 0 if it fails or is rate-limited.
        """
        url = f"https://pypistats.org/api/packages/{package_name}/recent"
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", {}).get("last_month", 0)
                return 0
            except Exception as e:
                logger.warning(f"Failed to fetch pypistats for {package_name}: {e}")
                return 0

    def check_typosquatting(self, package_name: str) -> Optional[str]:
        """
        Checks if the package name is suspiciously similar to a top 1000 PyPI package.
        Returns the name of the popular package it's mimicking, or None.
        """
        data_file = "core/data/top_pypi_packages.json"
        if not os.path.exists(data_file):
            return None
            
        with open(data_file, "r") as f:
            top_packages = json.load(f)
            
        if package_name in top_packages:
            return None
            
        for popular_pkg in top_packages:
            distance = Levenshtein.distance(package_name.lower(), popular_pkg.lower())
            threshold = 1 if len(popular_pkg) <= 4 else 2
            
            if distance <= threshold and distance > 0:
                return popular_pkg
                
        return None

    async def calculate_risk_score(self, package_name: str) -> Dict[str, Any]:
        """
        Calculates a risk score for a package based on PyPI metadata and stats.
        Returns a dict with 'risk_level' (low, medium, high) and 'details'.
        """
        typo_mimic = self.check_typosquatting(package_name)
        
        metadata = await self.get_pypi_metadata(package_name)
        if not metadata:
            details = ["Package not found on PyPI"]
            if typo_mimic:
                details.append(f"Typosquatting alert: suspiciously similar to popular package '{typo_mimic}'")
            return {"package": package_name, "risk_level": "high", "details": details}
            
        stats = await self.get_pypi_stats(package_name)
        
        info = metadata.get("info", {})
        releases = metadata.get("releases", {})
        
        total_releases = len(releases)
        
        risk_level = "low"
        reasons = []
        
        if typo_mimic:
            risk_level = "high"
            reasons.append(f"Typosquatting alert: suspiciously similar to popular package '{typo_mimic}'")
            
        if total_releases < 3:
            risk_level = "medium" if risk_level != "high" else "high"
            reasons.append(f"Very few releases ({total_releases})")
            
        if 0 < stats < 1000:
            if risk_level == "low":
                risk_level = "medium"
            reasons.append(f"Low download count ({stats} in last month)")
            
        if total_releases > 50 or stats > 10000:
            risk_level = "low"
            reasons = ["Popular and mature package"]
            
        if total_releases == 0:
            risk_level = "high"
            reasons.append("No releases found")
            
        return {
            "package": package_name,
            "risk_level": risk_level,
            "details": reasons,
            "stats": {
                "downloads_last_month": stats,
                "total_releases": total_releases
            }
        }
