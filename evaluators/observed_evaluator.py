"""
Observed (Website) Evaluator.

Computes the observed component score (0-50 points) from website analysis.
Uses external adapters for data collection and deterministic scoring.
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup

from adapters.pagespeed_adapter import PageSpeedAdapter, CoreWebVitals, compute_cwv_subscore
from adapters.serp_adapter import SERPAdapter, SERPSummary, compute_serp_subscore
from adapters.whois_adapter import WhoisAdapter, DomainInfo, compute_domain_age_score
from adapters.authority_adapter import AuthorityAdapter, AuthorityMetrics, compute_authority_subscore
from models.enums import OBSERVED_WEIGHTS
from utils.rounding import compute_observed_bucket_score
from utils.url_validator import extract_domain
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class OnPageMetrics:
    """
    On-page SEO metrics container.
    
    Attributes:
        title_present: Whether page has a title tag
        title_length: Title length in characters
        title_quality_score: Title quality score (0-1)
        meta_present: Whether meta description exists
        meta_unique: Whether meta description appears unique (not generic)
        meta_quality_score: Meta quality score (0-1)
        h1_present: Whether H1 tag exists
        h1_relevance_score: H1 relevance score (0-1)
        canonical_present: Whether canonical tag exists
        bot_blocked: Whether the site blocked our request (403, etc.)
        error: Error message if analysis failed
    """
    title_present: bool = False
    title_length: int = 0
    title_quality_score: float = 0.0
    meta_present: bool = False
    meta_unique: bool = False
    meta_quality_score: float = 0.0
    h1_present: bool = False
    h1_relevance_score: float = 0.67  # Default moderate
    canonical_present: bool = False
    bot_blocked: bool = False  # True if site returned 403/blocked
    error: Optional[str] = None


@dataclass
class ObservedScoreResult:
    """
    Result of observed (website) evaluation.
    
    Attributes:
        core_web_vitals: CWV bucket score (0-20)
        onpage: On-page SEO bucket score (0-15)
        authority_proxies: Authority bucket score (0-10)
        serp_reality: SERP reality bucket score (0-5)
        total: Total observed score (0-50)
        raw_cwv: Raw Core Web Vitals metrics
        raw_onpage: Raw on-page metrics
        raw_domain_info: Raw domain info
        raw_serp: Raw SERP summary
        notes: Notes about data sources used
    """
    core_web_vitals: int
    onpage: int
    authority_proxies: int
    serp_reality: int
    total: int
    raw_cwv: CoreWebVitals
    raw_onpage: OnPageMetrics
    raw_domain_info: DomainInfo
    raw_serp: SERPSummary
    raw_authority: AuthorityMetrics
    notes: str


class ObservedEvaluator:
    """
    Evaluates website observable metrics to produce observed capability scores.
    
    Scoring Buckets (deterministic):
    - Core Web Vitals & Site Health: 20 points
    - On-page SEO Execution: 15 points
    - Authority Proxies: 10 points
    - SERP Reality Check: 5 points
    
    Each bucket uses deterministic subscore rules (0-1) then:
        BucketScore = round_half_up(subscore × BucketWeight)
    
    Total = sum(BucketScore) → integer 0-50
    """
    
    def __init__(self):
        self.pagespeed = PageSpeedAdapter()
        self.serp = SERPAdapter()
        self.whois = WhoisAdapter()
        self.authority = AuthorityAdapter()
        
        # Weights from enums
        self.cwv_weight = OBSERVED_WEIGHTS["core_web_vitals"]  # 20
        self.onpage_weight = OBSERVED_WEIGHTS["onpage"]  # 15
        self.authority_weight = OBSERVED_WEIGHTS["authority_proxies"]  # 10
        self.serp_weight = OBSERVED_WEIGHTS["serp_reality"]  # 5
    
    async def evaluate(
        self,
        url: str,
        keywords: List[str],
        brand_name: Optional[str] = None
    ) -> ObservedScoreResult:
        """
        Evaluate website observable metrics.
        
        Args:
            url: Website URL to analyze
            keywords: Target keywords for SERP check
            brand_name: Brand name for brand search presence check
            
        Returns:
            ObservedScoreResult with bucket scores and raw data
        """
        domain = extract_domain(url) or ""
        notes_parts = []
        
        # Run all evaluations concurrently (with rate limiting)
        cwv_task = self.pagespeed.get_metrics(url)
        onpage_task = self._analyze_onpage(url)
        domain_task = self.whois.get_domain_info(domain)
        serp_task = self.serp.check_keywords(domain, keywords) if keywords else None
        
        # Gather results
        if serp_task:
            cwv, onpage, domain_info, serp_summary = await asyncio.gather(
                cwv_task, onpage_task, domain_task, serp_task
            )
        else:
            cwv, onpage, domain_info = await asyncio.gather(
                cwv_task, onpage_task, domain_task
            )
            serp_summary = SERPSummary(results=[], hits_top10=0, hits_top30=0)
        
        # Check brand presence for authority fallback
        has_brand_presence = False
        if brand_name and self.authority.backend == "fallback":
            has_brand_presence = await self._check_brand_presence(brand_name, domain)
        
        # Get authority metrics
        authority = await self.authority.get_authority(
            domain,
            domain_age_years=domain_info.age_years,
            has_brand_presence=has_brand_presence
        )
        
        # Compute subscores (deterministic 0-1)
        cwv_subscore = compute_cwv_subscore(cwv)
        onpage_subscore = self._compute_onpage_subscore(onpage)
        authority_subscore = compute_authority_subscore(
            authority,
            domain_age_years=domain_info.age_years,
            has_brand_presence=has_brand_presence
        )
        serp_subscore = compute_serp_subscore(serp_summary, len(keywords))
        
        # Compute bucket scores (deterministic rounding)
        cwv_score = compute_observed_bucket_score(cwv_subscore, self.cwv_weight)
        onpage_score = compute_observed_bucket_score(onpage_subscore, self.onpage_weight)
        authority_score = compute_observed_bucket_score(authority_subscore, self.authority_weight)
        serp_score = compute_observed_bucket_score(serp_subscore, self.serp_weight)
        
        # Total
        total = cwv_score + onpage_score + authority_score + serp_score
        
        # Build notes
        if self.pagespeed.is_configured:
            notes_parts.append("Core Web Vitals from PageSpeed Insights API")
        else:
            notes_parts.append("Core Web Vitals estimated from timing heuristics (approximate)")
        
        if self.authority.backend != "fallback":
            notes_parts.append(f"Authority metrics from {self.authority.backend.upper()}")
        else:
            notes_parts.append("Authority estimated from domain age and heuristics (approximate)")
        
        if self.serp.backend != "fallback":
            notes_parts.append(f"SERP data from {self.serp.backend.upper()}")
        else:
            notes_parts.append("SERP visibility could not be verified (no API configured)")
        
        return ObservedScoreResult(
            core_web_vitals=cwv_score,
            onpage=onpage_score,
            authority_proxies=authority_score,
            serp_reality=serp_score,
            total=total,
            raw_cwv=cwv,
            raw_onpage=onpage,
            raw_domain_info=domain_info,
            raw_serp=serp_summary,
            raw_authority=authority,
            notes="; ".join(notes_parts) + ".",
        )
    
    async def _analyze_onpage(self, url: str) -> OnPageMetrics:
        """
        Analyze on-page SEO elements.
        
        Checks:
        - Title tag presence and quality
        - Meta description presence and uniqueness
        - H1 tag presence
        - Canonical tag presence
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
                headers=headers
            ) as client:
                response = await client.get(url)
                
                # Handle bot blocking (403 Forbidden)
                if response.status_code == 403:
                    return OnPageMetrics(
                        bot_blocked=True,
                        # Give fair default scores since we can't verify
                        title_quality_score=0.5,
                        meta_quality_score=0.5,
                        h1_relevance_score=0.5,
                        error="Site restricts automated access"
                    )
                
                if response.status_code != 200:
                    return OnPageMetrics(error=f"HTTP {response.status_code}")
                
                html = response.text
                return self._parse_onpage_html(html)
                
        except httpx.TimeoutException:
            return OnPageMetrics(error="Timeout fetching page")
        except Exception as e:
            logger.error(f"On-page analysis error: {e}")
            return OnPageMetrics(error=str(e))
    
    def _parse_onpage_html(self, html: str) -> OnPageMetrics:
        """Parse HTML to extract on-page SEO metrics."""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Title analysis
            title_tag = soup.find('title')
            title_text = title_tag.get_text(strip=True) if title_tag else ""
            title_present = len(title_text) > 0
            title_length = len(title_text)
            
            # Title quality scoring (deterministic):
            # - Good length (30-60 chars): 1.0
            # - Acceptable (20-70 chars): 0.66
            # - Present but poor length: 0.33
            # - Missing: 0.0
            if not title_present:
                title_quality = 0.0
            elif 30 <= title_length <= 60:
                title_quality = 1.0
            elif 20 <= title_length <= 70:
                title_quality = 0.66
            else:
                title_quality = 0.33
            
            # Meta description analysis
            meta_tag = soup.find('meta', attrs={'name': 'description'})
            meta_present = meta_tag is not None and meta_tag.get('content')
            meta_content = meta_tag.get('content', '').strip() if meta_present else ""
            
            # Check if meta is unique (not generic placeholder)
            # Only flag extremely generic placeholder text
            generic_patterns = [
                "lorem ipsum", "placeholder", "add your description here",
                "enter description", "default description", "todo:"
            ]
            meta_unique = meta_present and len(meta_content) > 50 and not any(
                pattern in meta_content.lower() 
                for pattern in generic_patterns
            )
            
            # Meta quality scoring (deterministic):
            # - Unique and good length (100-160 chars): 1.0
            # - Present and acceptable length: 0.66
            # - Present but poor: 0.33
            # - Missing: 0.0
            meta_length = len(meta_content)
            if not meta_present:
                meta_quality = 0.0
            elif meta_unique and 100 <= meta_length <= 160:
                meta_quality = 1.0
            elif meta_present and 50 <= meta_length <= 200:
                meta_quality = 0.66
            else:
                meta_quality = 0.33
            
            # H1 analysis
            h1_tag = soup.find('h1')
            h1_present = h1_tag is not None and bool(h1_tag.get_text(strip=True))
            
            # H1 relevance (simplified - just check existence)
            # In production, could compare with title/meta
            h1_relevance = 1.0 if h1_present else 0.0
            
            # Canonical tag
            canonical = soup.find('link', attrs={'rel': 'canonical'})
            canonical_present = canonical is not None and canonical.get('href')
            
            return OnPageMetrics(
                title_present=title_present,
                title_length=title_length,
                title_quality_score=title_quality,
                meta_present=meta_present,
                meta_unique=meta_unique,
                meta_quality_score=meta_quality,
                h1_present=h1_present,
                h1_relevance_score=h1_relevance,
                canonical_present=canonical_present,
            )
            
        except Exception as e:
            logger.error(f"HTML parsing error: {e}")
            return OnPageMetrics(error=str(e))
    
    def _compute_onpage_subscore(self, metrics: OnPageMetrics) -> float:
        """
        Compute on-page SEO subscore (0-1).
        
        Deterministic formula:
            subscore = average(title_quality, meta_quality, h1_relevance)
        
        Each component is scored 0/0.33/0.66/1.0 based on quality.
        """
        if metrics.error:
            return 0.0
        
        # Average of three components
        total = (
            metrics.title_quality_score +
            metrics.meta_quality_score +
            metrics.h1_relevance_score
        )
        
        return total / 3.0
    
    async def _check_brand_presence(self, brand_name: str, domain: str) -> bool:
        """
        Check if brand appears in search results.
        
        This is used for authority fallback scoring.
        For now, returns False as we don't have a reliable way
        to check without using SERP API.
        """
        # In a full implementation, this would search for the brand name
        # and check if the domain appears in top 10 results.
        # For now, we conservatively return False.
        return False
