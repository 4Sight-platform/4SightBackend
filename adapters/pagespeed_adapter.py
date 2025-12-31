"""
PageSpeed Insights API adapter.

Provides Core Web Vitals metrics (LCP, CLS, INP) from Google PageSpeed Insights API.
Falls back to basic timing heuristics if API key is not configured.
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from config import settings
from utils.cache import cache_result
from utils.rate_limiter import with_rate_limit

logger = logging.getLogger(__name__)


@dataclass
class CoreWebVitals:
    """
    Core Web Vitals metrics container.
    
    Attributes:
        lcp_ms: Largest Contentful Paint in milliseconds
        cls: Cumulative Layout Shift score
        inp_ms: Interaction to Next Paint in milliseconds
        is_approximate: True if metrics are from fallback heuristics
        error: Error message if fetch failed
    """
    lcp_ms: Optional[int] = None
    cls: Optional[float] = None
    inp_ms: Optional[int] = None
    is_approximate: bool = False
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if we have valid metrics."""
        return self.lcp_ms is not None and self.error is None


class PageSpeedAdapter:
    """
    Adapter for Google PageSpeed Insights API.
    
    Uses the PSI API to fetch real Core Web Vitals data from Chrome UX Report.
    Falls back to basic timing heuristics if API key is not available.
    
    Environment Variables:
        PAGESPEED_API_KEY: Google PageSpeed Insights API key
    """
    
    BASE_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    
    def __init__(self):
        self.api_key = settings.pagespeed_api_key
        self.is_configured = bool(self.api_key)
        self.timeout = settings.request_timeout_seconds  # Read at runtime
    
    @cache_result("pagespeed", key_prefix="psi_")
    async def get_metrics(self, url: str) -> CoreWebVitals:
        """
        Get Core Web Vitals metrics for a URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            CoreWebVitals with metrics or error
        """
        if self.is_configured:
            return await self._fetch_from_api(url)
        else:
            return await self._fallback_heuristics(url)
    
    @with_rate_limit("pagespeed")
    async def _fetch_from_api(self, url: str) -> CoreWebVitals:
        """
        Fetch metrics from PageSpeed Insights API.
        
        Uses both field data (CrUX) and lab data (Lighthouse) for best coverage.
        Prefers field data when available as it represents real user experience.
        """
        params = {
            "url": url,
            "key": self.api_key,
            "strategy": "mobile",  # Mobile-first
            "category": "performance",
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.BASE_URL, params=params)
                
                if response.status_code == 429:
                    logger.warning("PageSpeed API rate limited, falling back to heuristics")
                    return await self._fallback_heuristics(url)
                
                response.raise_for_status()
                data = response.json()
                
                return self._parse_response(data)
                
        except httpx.TimeoutException:
            logger.error(f"PageSpeed API timeout for {url}")
            return CoreWebVitals(error="API request timed out")
        except httpx.HTTPStatusError as e:
            logger.error(f"PageSpeed API error {e.response.status_code}: {e}")
            return CoreWebVitals(error=f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"PageSpeed API unexpected error: {e}")
            return CoreWebVitals(error=f"Unexpected error: {str(e)}")
    
    def _parse_response(self, data: dict) -> CoreWebVitals:
        """
        Parse PageSpeed API response to extract Core Web Vitals.
        
        Priority:
        1. Field data (CrUX) - real user metrics
        2. Lab data (Lighthouse) - simulated metrics
        """
        try:
            # Try to get field data first (Chrome UX Report)
            loading_experience = data.get("loadingExperience", {})
            metrics = loading_experience.get("metrics", {})
            
            lcp_ms = None
            cls = None
            inp_ms = None
            is_approximate = False
            error_reason = None
            
            # LCP from field data
            if "LARGEST_CONTENTFUL_PAINT_MS" in metrics:
                lcp_data = metrics["LARGEST_CONTENTFUL_PAINT_MS"]
                lcp_ms = lcp_data.get("percentile", lcp_data.get("numericValue"))
            
            # CLS from field data
            if "CUMULATIVE_LAYOUT_SHIFT_SCORE" in metrics:
                cls_data = metrics["CUMULATIVE_LAYOUT_SHIFT_SCORE"]
                cls = cls_data.get("percentile", cls_data.get("numericValue"))
                if cls:
                    cls = cls / 100  # Normalize to decimal
            
            # INP from field data (newer metric)
            if "INTERACTION_TO_NEXT_PAINT" in metrics:
                inp_data = metrics["INTERACTION_TO_NEXT_PAINT"]
                inp_ms = inp_data.get("percentile", inp_data.get("numericValue"))
            
            # Fall back to Lighthouse data if field data missing
            lighthouse = data.get("lighthouseResult", {})
            audits = lighthouse.get("audits", {})
            
            if lcp_ms is None and "largest-contentful-paint" in audits:
                lcp_audit = audits["largest-contentful-paint"]
                if lcp_audit.get("numericValue"):
                    lcp_ms = int(lcp_audit["numericValue"])
                    is_approximate = True
            
            if cls is None and "cumulative-layout-shift" in audits:
                cls_audit = audits["cumulative-layout-shift"]
                if cls_audit.get("numericValue") is not None:
                    cls = cls_audit["numericValue"]
                    is_approximate = True
            
            # INP fallback: use TBT as proxy (not exact, but indicative)
            if inp_ms is None and "total-blocking-time" in audits:
                tbt_audit = audits["total-blocking-time"]
                if tbt_audit.get("numericValue"):
                    # TBT is not INP, but provides interactivity signal
                    # Rough approximation: TBT * 2 as INP estimate
                    inp_ms = int(tbt_audit["numericValue"] * 2)
                    is_approximate = True
            
            # Set error reason if any metrics are missing
            missing = []
            if lcp_ms is None:
                missing.append("LCP")
            if cls is None:
                missing.append("CLS")
            if inp_ms is None:
                missing.append("INP")
            
            if missing:
                error_reason = f"No Chrome user data available for {', '.join(missing)}. Site may have insufficient traffic for CrUX data."
            elif is_approximate:
                error_reason = "Using Lighthouse lab data (simulated, not real user metrics)"
            
            return CoreWebVitals(
                lcp_ms=lcp_ms,
                cls=cls,
                inp_ms=inp_ms,
                is_approximate=is_approximate,
                error=error_reason,
            )
            
        except Exception as e:
            logger.error(f"Error parsing PageSpeed response: {e}")
            return CoreWebVitals(error=f"Failed to parse API response: {str(e)}")
    
    async def _fallback_heuristics(self, url: str) -> CoreWebVitals:
        """
        Fallback: estimate metrics from basic HTTP timing.
        
        This is a rough approximation when API is not available.
        Performs a simple fetch and estimates metrics from timing.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                start_time = asyncio.get_event_loop().time()
                response = await client.get(url)
                end_time = asyncio.get_event_loop().time()
                
                # Total response time as LCP proxy (rough estimate)
                total_ms = int((end_time - start_time) * 1000)
                
                # Approximate LCP based on response time
                # Real LCP includes rendering; add 50% estimate
                lcp_estimate = int(total_ms * 1.5)
                
                # CLS approximation: assume moderate if HTML is large
                content_length = len(response.content)
                # Larger pages tend to have more layout shifts
                if content_length > 500000:
                    cls_estimate = 0.15
                elif content_length > 200000:
                    cls_estimate = 0.08
                else:
                    cls_estimate = 0.05
                
                # INP approximation based on response time
                # Slower sites tend to have worse interactivity
                inp_estimate = min(total_ms, 500)
                
                return CoreWebVitals(
                    lcp_ms=lcp_estimate,
                    cls=cls_estimate,
                    inp_ms=inp_estimate,
                    is_approximate=True,
                    error="Estimated from response timing (PageSpeed API not available)",
                )
                
        except httpx.TimeoutException:
            logger.error(f"Fallback fetch timeout for {url}")
            return CoreWebVitals(
                lcp_ms=None,
                cls=None,
                inp_ms=None,
                is_approximate=True,
                error="Site unreachable or timeout",
            )
        except Exception as e:
            logger.error(f"Fallback heuristics error: {e}")
            return CoreWebVitals(
                lcp_ms=None,
                cls=None, 
                inp_ms=None,
                is_approximate=True,
                error=f"Could not analyze site: {str(e)}",
            )


def compute_cwv_subscore(metrics: CoreWebVitals) -> float:
    """
    Compute deterministic subscore (0-1) from Core Web Vitals.
    
    Rules (deterministic):
    - All three pass "Good" thresholds → 1.0
    - Two of three pass → 0.75
    - One of three passes → 0.5
    - None pass but site loads → 0.25
    - Page unreachable or HTTPS invalid → 0.0
    
    Thresholds (Google's "Good"):
    - LCP <= 2500ms
    - CLS <= 0.1
    - INP <= 200ms
    """
    # Check if we have valid metrics (now we always should)
    # Even with error note, if we have lcp_ms we can compute score
    if metrics.lcp_ms is None:
        return 0.0
    
    passing = 0
    
    # LCP check
    if metrics.lcp_ms is not None and metrics.lcp_ms <= 2500:
        passing += 1
    
    # CLS check
    if metrics.cls is not None and metrics.cls <= 0.1:
        passing += 1
    
    # INP check
    if metrics.inp_ms is not None and metrics.inp_ms <= 200:
        passing += 1
    
    # Map passing count to subscore
    if passing == 3:
        return 1.0
    elif passing == 2:
        return 0.75
    elif passing == 1:
        return 0.5
    else:
        return 0.25  # Site loaded but none passed
