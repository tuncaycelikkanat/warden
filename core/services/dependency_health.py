import re
import httpx
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from core.services.package import PackageCheckerService

logger = logging.getLogger(__name__)

@dataclass
class Vulnerability:
    cve_id: str
    summary: str
    details: str

    @classmethod
    def from_osv(cls, data: dict) -> 'Vulnerability':
        return cls(
            cve_id=data.get("id", "Unknown"),
            summary=data.get("summary", "No summary provided"),
            details=data.get("details", "")
        )

@dataclass
class PackageAuditEntry:
    name: str
    version: Optional[str]
    integrity_verdict: Dict[str, Any]
    known_vulnerabilities: List[Vulnerability]
    status: str  # "ok", "failed_check"

@dataclass
class DependencyHealthResult:
    entries: List[PackageAuditEntry]

class DependencyHealthService:
    def __init__(self):
        self._integrity_checker = PackageCheckerService()
        self._http = httpx.AsyncClient(timeout=10.0)

    async def close(self):
        await self._http.aclose()

    def _parse_manifest(self, repo_path: Path) -> List[Dict[str, str]]:
        """Parses requirements.txt and returns list of dicts with name and version."""
        req_file = repo_path / "requirements.txt"
        packages = []
        if req_file.exists():
            content = req_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Match package==version or just package
                match = re.match(r"^([a-zA-Z0-9_\-]+)(?:==|>=|<=|~=)([\w\.]+)$", line)
                if match:
                    packages.append({"name": match.group(1), "version": match.group(2), "ecosystem": "PyPI"})
                else:
                    # Just the package name
                    match = re.match(r"^([a-zA-Z0-9_\-]+)", line)
                    if match:
                        packages.append({"name": match.group(1), "version": None, "ecosystem": "PyPI"})
        return packages

    async def _query_osv(self, name: str, version: Optional[str], ecosystem: str) -> List[Vulnerability]:
        """Queries OSV.dev for known vulnerabilities."""
        if not version:
            return [] # OSV requires version for accurate querying, though it supports commit hashes too.
            
        payload = {
            "package": {"name": name, "ecosystem": ecosystem},
            "version": version
        }
        
        try:
            response = await self._http.post("https://api.osv.dev/v1/query", json=payload)
            response.raise_for_status()
            data = response.json()
            return [Vulnerability.from_osv(v) for v in data.get("vulns", [])]
        except httpx.RequestError as e:
            logger.warning(f"OSV query failed for {name}: {e}")
            return [] # Return empty on network error (Step 8.8: Error tolerance)
        except Exception as e:
            logger.warning(f"Unexpected error querying OSV for {name}: {e}")
            return []

    async def check_manifest(self, repo_path: Path) -> DependencyHealthResult:
        packages = self._parse_manifest(repo_path)
        
        async def process_package(pkg):
            name = pkg["name"]
            version = pkg["version"]
            ecosystem = pkg["ecosystem"]
            
            # 1. Check integrity (from Milestone 2)
            try:
                integrity = await self._integrity_checker.calculate_risk_score(name)
                status = "ok"
            except Exception as e:
                logger.error(f"Integrity check failed for {name}: {e}")
                integrity = {"risk_level": "UNKNOWN", "details": [str(e)]}
                status = "failed_check"
                
            # 2. Check known vulnerabilities (OSV)
            vulns = await self._query_osv(name, version, ecosystem)
            
            return PackageAuditEntry(
                name=name,
                version=version,
                integrity_verdict=integrity,
                known_vulnerabilities=vulns,
                status=status
            )
            
        entries = await asyncio.gather(*(process_package(pkg) for pkg in packages))
        return DependencyHealthResult(entries=list(entries))
