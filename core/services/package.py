import httpx
import logging
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
