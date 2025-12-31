"""
WHOIS / Domain Age adapter.

Provides domain age information for authority proxy calculation.
Supports WHOISXMLAPI and python-whois as fallback.
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from config import settings
from utils.cache import cache_result
from utils.rate_limiter import with_rate_limit

logger = logging.getLogger(__name__)


@dataclass
class DomainInfo:
    """
    Domain information container.
    
    Attributes:
        domain: Domain name
        creation_date: Domain creation date
        age_years: Age in years (floored)
        registrar: Registrar name if available
        error: Error message if lookup failed
        is_approximate: True if using fallback method
    """
    domain: str
    creation_date: Optional[datetime] = None
    age_years: Optional[int] = None
    registrar: Optional[str] = None
    error: Optional[str] = None
    is_approximate: bool = False


class WhoisAdapter:
    """
    Adapter for WHOIS / domain age lookups.
    
    Priority order:
    1. WHOISXMLAPI (WHOISXML_API_KEY) - most reliable
    2. python-whois library - free but less reliable
    
    Environment Variables:
        WHOISXML_API_KEY: WHOISXMLAPI API key
    """
    
    WHOISXML_URL = "https://www.whoisxmlapi.com/whoisserver/WhoisService"
    TIMEOUT = settings.request_timeout_seconds
    
    def __init__(self):
        self.api_key = settings.whoisxml_api_key
        self.is_configured = bool(self.api_key)
    
    @cache_result("whois", key_prefix="whois_")
    async def get_domain_info(self, domain: str) -> DomainInfo:
        """
        Get domain information including age.
        
        Args:
            domain: Domain name to lookup (without protocol)
            
        Returns:
            DomainInfo with age and details
        """
        # Clean domain
        domain = self._clean_domain(domain)
        
        if self.is_configured:
            return await self._fetch_from_api(domain)
        else:
            return await self._fallback_whois(domain)
    
    def _clean_domain(self, domain: str) -> str:
        """Clean domain string for lookup."""
        domain = domain.lower().strip()
        
        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]
        
        return domain
    
    @with_rate_limit("whoisxml")
    async def _fetch_from_api(self, domain: str) -> DomainInfo:
        """Fetch domain info from WHOISXMLAPI."""
        params = {
            "apiKey": self.api_key,
            "domainName": domain,
            "outputFormat": "JSON",
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.get(self.WHOISXML_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
                return self._parse_whoisxml_response(domain, data)
                
        except httpx.TimeoutException:
            logger.error(f"WHOISXML timeout for {domain}")
            return DomainInfo(domain=domain, error="Timeout")
        except Exception as e:
            logger.error(f"WHOISXML error for {domain}: {e}")
            return DomainInfo(domain=domain, error=str(e))
    
    def _parse_whoisxml_response(self, domain: str, data: dict) -> DomainInfo:
        """Parse WHOISXMLAPI response."""
        try:
            whois_record = data.get("WhoisRecord", {})
            
            # Try to get creation date
            creation_date_str = whois_record.get("createdDate")
            if not creation_date_str:
                # Alternative field names
                creation_date_str = whois_record.get("registryData", {}).get("createdDate")
            
            creation_date = None
            age_years = None
            
            if creation_date_str:
                # Parse date string - WHOISXML uses ISO format
                try:
                    # Handle various date formats
                    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
                        try:
                            creation_date = datetime.strptime(creation_date_str[:19], fmt[:19])
                            break
                        except ValueError:
                            continue
                    
                    if creation_date:
                        age_days = (datetime.now() - creation_date).days
                        age_years = age_days // 365
                except Exception as e:
                    logger.warning(f"Could not parse creation date: {creation_date_str}")
            
            registrar = whois_record.get("registrarName")
            
            return DomainInfo(
                domain=domain,
                creation_date=creation_date,
                age_years=age_years,
                registrar=registrar,
            )
            
        except Exception as e:
            logger.error(f"Error parsing WHOISXML response: {e}")
            return DomainInfo(domain=domain, error=f"Parse error: {str(e)}")
    
    async def _fallback_whois(self, domain: str) -> DomainInfo:
        """
        Fallback using python-whois library.
        
        This runs in a thread pool to avoid blocking.
        """
        try:
            # Import here to avoid dependency issues if not installed
            import whois
            
            # Run in thread pool since whois is blocking
            loop = asyncio.get_event_loop()
            w = await loop.run_in_executor(None, whois.whois, domain)
            
            creation_date = None
            age_years = None
            
            # Handle creation_date which can be a list or single value
            raw_creation = w.creation_date
            if raw_creation:
                if isinstance(raw_creation, list):
                    creation_date = raw_creation[0]
                else:
                    creation_date = raw_creation
                
                if isinstance(creation_date, datetime):
                    age_days = (datetime.now() - creation_date).days
                    age_years = age_days // 365
            
            registrar = w.registrar if hasattr(w, 'registrar') else None
            
            return DomainInfo(
                domain=domain,
                creation_date=creation_date,
                age_years=age_years,
                registrar=registrar,
                is_approximate=True,  # Fallback method
            )
            
        except Exception as e:
            logger.error(f"python-whois fallback error for {domain}: {e}")
            return DomainInfo(
                domain=domain,
                error=f"WHOIS lookup failed: {str(e)}",
                is_approximate=True,
            )


def compute_domain_age_score(age_years: Optional[int]) -> float:
    """
    Compute domain age contribution to authority proxy.
    
    Rules (deterministic):
    - Domain age >= 5 years: +0.4
    - Domain age 3-4 years: +0.3
    - Domain age 1-2 years: +0.2
    - Domain age < 1 year: +0.1
    - Unknown age: +0.0
    
    Args:
        age_years: Domain age in years
        
    Returns:
        Score contribution between 0.0 and 0.4
    """
    if age_years is None:
        return 0.0
    
    if age_years >= 5:
        return 0.4
    elif age_years >= 3:
        return 0.3
    elif age_years >= 1:
        return 0.2
    else:
        return 0.1
