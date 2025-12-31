"""
Authority metrics adapter.

Provides domain authority metrics from Moz, Ahrefs, or Majestic APIs.
Falls back to heuristic estimation when no API is configured.
"""

import asyncio
import base64
import hashlib
import hmac
import httpx
import logging
import time
from dataclasses import dataclass
from typing import Optional
from config import settings
from utils.cache import cache_result
from utils.rate_limiter import with_rate_limit

logger = logging.getLogger(__name__)


@dataclass
class AuthorityMetrics:
    """
    Domain authority metrics container.
    
    Attributes:
        domain: Domain name
        domain_authority: DA score (0-100), normalized to 0-1 for subscore
        referring_domains: Estimated referring domains count
        source: Data source (moz/ahrefs/majestic/fallback)
        error: Error message if lookup failed
    """
    domain: str
    domain_authority: Optional[float] = None  # 0-100 scale
    referring_domains: Optional[int] = None
    source: str = "fallback"
    error: Optional[str] = None


class AuthorityAdapter:
    """
    Adapter for domain authority metrics.
    
    Priority order:
    1. Moz (MOZ_ACCESS_ID + MOZ_SECRET_KEY)
    2. Ahrefs (AHREFS_API_KEY)
    3. Majestic (MAJESTIC_API_KEY)
    4. Fallback heuristics
    
    Environment Variables:
        MOZ_ACCESS_ID: Moz API access ID
        MOZ_SECRET_KEY: Moz API secret key
        AHREFS_API_KEY: Ahrefs API key
        MAJESTIC_API_KEY: Majestic API key
    """
    
    MOZ_URL = "https://lsapi.seomoz.com/v2/url_metrics"
    TIMEOUT = settings.request_timeout_seconds
    
    def __init__(self):
        self.moz_access_id = settings.moz_access_id
        self.moz_secret_key = settings.moz_secret_key
        self.ahrefs_key = settings.ahrefs_api_key
        self.majestic_key = settings.majestic_api_key
        
        # Determine which backend to use
        if self.moz_access_id and self.moz_secret_key:
            self.backend = "moz"
        elif self.ahrefs_key:
            self.backend = "ahrefs"
        elif self.majestic_key:
            self.backend = "majestic"
        else:
            self.backend = "fallback"
    
    @cache_result("authority", key_prefix="auth_")
    async def get_authority(
        self,
        domain: str,
        domain_age_years: Optional[int] = None,
        has_brand_presence: bool = False
    ) -> AuthorityMetrics:
        """
        Get domain authority metrics.
        
        Args:
            domain: Domain name to lookup
            domain_age_years: Domain age for fallback calculation
            has_brand_presence: Whether brand appears in search (for fallback)
            
        Returns:
            AuthorityMetrics with DA and related data
        """
        domain = domain.lower().strip()
        
        if self.backend == "moz":
            return await self._fetch_from_moz(domain)
        elif self.backend == "ahrefs":
            return await self._fetch_from_ahrefs(domain)
        elif self.backend == "majestic":
            return await self._fetch_from_majestic(domain)
        else:
            return self._fallback_estimation(domain, domain_age_years, has_brand_presence)
    
    @with_rate_limit("moz")
    async def _fetch_from_moz(self, domain: str) -> AuthorityMetrics:
        """Fetch domain authority from Moz API."""
        try:
            # Moz API uses signature-based auth
            expires = int(time.time()) + 300  # 5 minutes
            string_to_sign = f"{self.moz_access_id}\n{expires}"
            
            signature = base64.b64encode(
                hmac.new(
                    self.moz_secret_key.encode(),
                    string_to_sign.encode(),
                    hashlib.sha1
                ).digest()
            ).decode()
            
            headers = {
                "Content-Type": "application/json",
            }
            
            payload = {
                "targets": [domain],
            }
            
            params = {
                "AccessID": self.moz_access_id,
                "Expires": expires,
                "Signature": signature,
            }
            
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.post(
                    self.MOZ_URL,
                    json=payload,
                    params=params,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("results"):
                    result = data["results"][0]
                    return AuthorityMetrics(
                        domain=domain,
                        domain_authority=result.get("domain_authority", 0),
                        referring_domains=result.get("root_domains_to_root_domain", 0),
                        source="moz",
                    )
                else:
                    return AuthorityMetrics(domain=domain, error="No results from Moz")
                
        except httpx.TimeoutException:
            logger.error(f"Moz API timeout for {domain}")
            return AuthorityMetrics(domain=domain, source="moz", error="Timeout")
        except Exception as e:
            logger.error(f"Moz API error for {domain}: {e}")
            return AuthorityMetrics(domain=domain, source="moz", error=str(e))
    
    async def _fetch_from_ahrefs(self, domain: str) -> AuthorityMetrics:
        """
        Fetch domain rating from Ahrefs API.
        
        Note: Ahrefs API endpoint varies by subscription.
        This is a placeholder structure.
        """
        # Ahrefs API implementation would go here
        # For now, return as if not configured
        logger.warning("Ahrefs API not fully implemented, using fallback")
        return self._fallback_estimation(domain, None, False)
    
    async def _fetch_from_majestic(self, domain: str) -> AuthorityMetrics:
        """
        Fetch trust/citation flow from Majestic API.
        
        Note: Majestic API endpoint varies by subscription.
        This is a placeholder structure.
        """
        # Majestic API implementation would go here
        # For now, return as if not configured
        logger.warning("Majestic API not fully implemented, using fallback")
        return self._fallback_estimation(domain, None, False)
    
    def _fallback_estimation(
        self,
        domain: str,
        domain_age_years: Optional[int],
        has_brand_presence: bool
    ) -> AuthorityMetrics:
        """
        Estimate authority using fallback heuristics.
        
        Deterministic rules:
        - Domain age >= 5 years: +0.4 (40 DA points equivalent)
        - Presence of >5 referring domains (estimated): +0.4
        - Brand search presence: +0.2
        
        Cap at 100 (or 1.0 normalized).
        
        Note: This is conservative and documented as approximate.
        """
        logger.info(f"Using authority fallback estimation for {domain}")
        
        estimated_da = 0.0
        
        # Domain age contribution
        if domain_age_years is not None:
            if domain_age_years >= 5:
                estimated_da += 40  # +0.4 when normalized
            elif domain_age_years >= 3:
                estimated_da += 30
            elif domain_age_years >= 1:
                estimated_da += 20
            else:
                estimated_da += 10
        
        # We can't easily estimate referring domains without API
        # Use a conservative estimate based on domain age
        estimated_refs = None
        if domain_age_years is not None and domain_age_years >= 2:
            # Assume established domains have some links
            estimated_refs = domain_age_years * 5  # Rough estimate
            if estimated_refs > 5:
                estimated_da += 40  # +0.4 when normalized
        
        # Brand presence contribution
        if has_brand_presence:
            estimated_da += 20  # +0.2 when normalized
        
        # Cap at 100
        estimated_da = min(estimated_da, 100)
        
        return AuthorityMetrics(
            domain=domain,
            domain_authority=estimated_da,
            referring_domains=estimated_refs,
            source="fallback",
        )


def compute_authority_subscore(
    metrics: AuthorityMetrics,
    domain_age_years: Optional[int] = None,
    has_brand_presence: bool = False
) -> float:
    """
    Compute deterministic authority subscore (0-1).
    
    If DA is available from API:
        subscore = DA / 100 (normalized)
    
    If using fallback:
        - Domain age >= 5 years: +0.4
        - >5 referring domains: +0.4
        - Brand search presence: +0.2
        - Cap at 1.0
    
    Args:
        metrics: Authority metrics from adapter
        domain_age_years: Domain age for fallback
        has_brand_presence: Brand search presence for fallback
        
    Returns:
        Subscore between 0.0 and 1.0
    """
    if metrics.error and metrics.domain_authority is None:
        # If lookup failed completely, use minimal fallback
        subscore = 0.0
        
        if domain_age_years is not None and domain_age_years >= 5:
            subscore += 0.4
        elif domain_age_years is not None and domain_age_years >= 1:
            subscore += 0.2
        
        if has_brand_presence:
            subscore += 0.2
        
        return min(subscore, 1.0)
    
    if metrics.domain_authority is not None:
        # Normalize DA to 0-1
        return min(metrics.domain_authority / 100.0, 1.0)
    
    # Fallback calculation
    subscore = 0.0
    
    if domain_age_years is not None and domain_age_years >= 5:
        subscore += 0.4
    
    if metrics.referring_domains is not None and metrics.referring_domains > 5:
        subscore += 0.4
    
    if has_brand_presence:
        subscore += 0.2
    
    return min(subscore, 1.0)
