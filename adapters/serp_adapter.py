"""
SERP (Search Engine Results Page) adapter.

Provides SERP visibility checking for target keywords.
Supports multiple backends: SerpApi (preferred), Google Custom Search, and fallback.
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from config import settings
from utils.cache import cache_result
from utils.rate_limiter import with_rate_limit
from utils.url_validator import extract_domain

logger = logging.getLogger(__name__)


@dataclass
class SERPResult:
    """
    SERP lookup result for a single keyword.
    
    Attributes:
        keyword: The keyword searched
        rank: Position in results (1-indexed), None if not found
        is_top10: True if rank <= 10
        is_top30: True if rank <= 30
        error: Error message if lookup failed
    """
    keyword: str
    rank: Optional[int] = None
    is_top10: bool = False
    is_top30: bool = False
    error: Optional[str] = None


@dataclass
class SERPSummary:
    """
    Aggregated SERP results for all keywords.
    
    Attributes:
        results: List of individual keyword results
        hits_top10: Count of keywords ranking in top 10
        hits_top30: Count of keywords ranking in top 30
        is_approximate: True if using fallback method
    """
    results: List[SERPResult]
    hits_top10: int = 0
    hits_top30: int = 0
    is_approximate: bool = False


class SERPAdapter:
    """
    Adapter for SERP visibility checking.
    
    Priority order:
    1. SerpApi (SERPAPI_KEY) - most reliable
    2. Google Custom Search (GCS_API_KEY + GCS_CX) - limited quota
    3. Fallback - always returns 0 with is_approximate=True
    
    Environment Variables:
        SERPAPI_KEY: SerpApi API key
        GCS_API_KEY: Google Custom Search API key
        GCS_CX: Google Custom Search Engine ID
    """
    
    SERPAPI_URL = "https://serpapi.com/search.json"
    GCS_URL = "https://www.googleapis.com/customsearch/v1"
    TIMEOUT = settings.request_timeout_seconds
    MAX_RESULTS_TO_CHECK = 30  # Check first 30 results
    
    def __init__(self):
        self.serpapi_key = settings.serpapi_key
        self.gcs_api_key = settings.gcs_api_key
        self.gcs_cx = settings.gcs_cx
        
        # Determine which backend to use
        if self.serpapi_key:
            self.backend = "serpapi"
        elif self.gcs_api_key and self.gcs_cx:
            self.backend = "gcs"
        else:
            self.backend = "fallback"
    
    @cache_result("serp", key_prefix="serp_")
    async def check_keywords(
        self,
        domain: str,
        keywords: List[str]
    ) -> SERPSummary:
        """
        Check SERP visibility for a domain across keywords.
        
        Args:
            domain: Domain to check for (e.g., "example.com")
            keywords: List of keywords to check
            
        Returns:
            SERPSummary with results per keyword
        """
        if not keywords:
            return SERPSummary(results=[], hits_top10=0, hits_top30=0)
        
        if self.backend == "serpapi":
            results = await self._check_via_serpapi(domain, keywords)
        elif self.backend == "gcs":
            results = await self._check_via_gcs(domain, keywords)
        else:
            results = self._fallback_results(keywords)
        
        # Aggregate results
        hits_top10 = sum(1 for r in results if r.is_top10)
        hits_top30 = sum(1 for r in results if r.is_top30)
        
        return SERPSummary(
            results=results,
            hits_top10=hits_top10,
            hits_top30=hits_top30,
            is_approximate=(self.backend == "fallback"),
        )
    
    async def _check_via_serpapi(
        self,
        domain: str,
        keywords: List[str]
    ) -> List[SERPResult]:
        """Check keywords using SerpApi."""
        results = []
        
        for keyword in keywords:
            result = await self._serpapi_single_keyword(domain, keyword)
            results.append(result)
        
        return results
    
    @with_rate_limit("serpapi")
    async def _serpapi_single_keyword(
        self,
        domain: str,
        keyword: str
    ) -> SERPResult:
        """Query SerpApi for a single keyword."""
        params = {
            "q": keyword,
            "api_key": self.serpapi_key,
            "engine": "google",
            "num": self.MAX_RESULTS_TO_CHECK,
            "gl": "us",
            "hl": "en",
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.get(self.SERPAPI_URL, params=params)
                response.raise_for_status()
                data = response.json()
                
                return self._parse_serpapi_response(domain, keyword, data)
                
        except httpx.TimeoutException:
            logger.error(f"SerpApi timeout for keyword: {keyword}")
            return SERPResult(keyword=keyword, error="Timeout")
        except Exception as e:
            logger.error(f"SerpApi error for keyword {keyword}: {e}")
            return SERPResult(keyword=keyword, error=str(e))
    
    def _parse_serpapi_response(
        self,
        domain: str,
        keyword: str,
        data: dict
    ) -> SERPResult:
        """Parse SerpApi response to find domain rank."""
        organic_results = data.get("organic_results", [])
        
        for i, result in enumerate(organic_results, start=1):
            link = result.get("link", "")
            result_domain = extract_domain(link)
            
            if result_domain and domain in result_domain:
                return SERPResult(
                    keyword=keyword,
                    rank=i,
                    is_top10=(i <= 10),
                    is_top30=(i <= 30),
                )
        
        # Not found in results
        return SERPResult(keyword=keyword, rank=None, is_top10=False, is_top30=False)
    
    async def _check_via_gcs(
        self,
        domain: str,
        keywords: List[str]
    ) -> List[SERPResult]:
        """Check keywords using Google Custom Search."""
        results = []
        
        for keyword in keywords:
            result = await self._gcs_single_keyword(domain, keyword)
            results.append(result)
        
        return results
    
    @with_rate_limit("gcs")
    async def _gcs_single_keyword(
        self,
        domain: str,
        keyword: str
    ) -> SERPResult:
        """Query Google Custom Search for a single keyword."""
        # GCS only returns 10 results per query, need multiple queries for top 30
        all_ranks = []
        
        for start in [1, 11, 21]:  # Pages for results 1-10, 11-20, 21-30
            params = {
                "q": keyword,
                "key": self.gcs_api_key,
                "cx": self.gcs_cx,
                "start": start,
                "num": 10,
            }
            
            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    response = await client.get(self.GCS_URL, params=params)
                    
                    if response.status_code == 429:
                        logger.warning("GCS rate limited")
                        break
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    items = data.get("items", [])
                    for i, item in enumerate(items, start=start):
                        link = item.get("link", "")
                        result_domain = extract_domain(link)
                        
                        if result_domain and domain in result_domain:
                            return SERPResult(
                                keyword=keyword,
                                rank=i,
                                is_top10=(i <= 10),
                                is_top30=(i <= 30),
                            )
                            
            except Exception as e:
                logger.error(f"GCS error for keyword {keyword}: {e}")
                return SERPResult(keyword=keyword, error=str(e))
        
        # Not found
        return SERPResult(keyword=keyword, rank=None, is_top10=False, is_top30=False)
    
    def _fallback_results(self, keywords: List[str]) -> List[SERPResult]:
        """
        Fallback when no SERP API is configured.
        
        Returns all keywords as not found with is_approximate=True.
        This is conservative - assumes no visibility when we can't check.
        """
        logger.warning("Using SERP fallback - no API configured")
        return [
            SERPResult(
                keyword=keyword,
                rank=None,
                is_top10=False,
                is_top30=False,
                error="No SERP API configured",
            )
            for keyword in keywords
        ]


def compute_serp_subscore(summary: SERPSummary, num_keywords: int) -> float:
    """
    Compute deterministic subscore (0-1) from SERP results.
    
    Rules:
    - For each keyword in top 10: +1.0 point
    - For each keyword in top 30 (but not top 10): +0.5 point
    - subscore = sum / num_keywords, clipped to [0, 1]
    - If no keywords provided, subscore = 0.0
    
    Args:
        summary: SERP results summary
        num_keywords: Number of keywords that were checked
        
    Returns:
        Subscore between 0.0 and 1.0
    """
    if num_keywords == 0:
        return 0.0
    
    total_points = 0.0
    
    for result in summary.results:
        if result.is_top10:
            total_points += 1.0
        elif result.is_top30:
            total_points += 0.5
    
    # Normalize by number of keywords
    subscore = total_points / num_keywords
    
    # Clip to [0, 1]
    return max(0.0, min(1.0, subscore))
