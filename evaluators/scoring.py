"""
Final scoring and response generation.

Combines declared and observed scores into the final grader response.
All logic is deterministic with documented rules.
"""

from datetime import datetime
from typing import List, Optional, Tuple

from evaluators.declared_evaluator import DeclaredScoreResult
from evaluators.observed_evaluator import ObservedScoreResult
from models.schemas import (
    GraderResponse,
    DimensionScores,
    DeclaredScores,
    ObservedScores,
    RawSignalsSummary,
)
from models.enums import RISK_TEMPLATES
from utils.rounding import compute_stage, compute_gap_description


def compute_final_score(
    declared: DeclaredScoreResult,
    observed: ObservedScoreResult
) -> int:
    """
    Compute the final total score.
    
    Formula:
        TotalScore = QuestionnaireScore + ObservedScore
    
    Both components are already integers 0-50.
    Result is clamped to 0-100.
    
    Args:
        declared: Declared evaluation result
        observed: Observed evaluation result
        
    Returns:
        Total score as integer (0-100)
    """
    total = declared.total + observed.total
    return max(0, min(100, total))


def identify_top_risks(
    declared: DeclaredScoreResult,
    observed: ObservedScoreResult,
    website_url: str = ""
) -> List[str]:
    """
    Identify top 3 weakest signals as actionable risk statements.
    
    Logic (deterministic):
    1. Rank all scored components by their subscore ratio
    2. Select bottom 3 as risks
    3. Generate dynamic, site-specific messages with actual metrics
    
    Args:
        declared: Declared evaluation result
        observed: Observed evaluation result
        website_url: The website URL for context
        
    Returns:
        List of 3 risk statements with site-specific data
    """
    # Extract domain name for personalized messages
    domain = ""
    if website_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(website_url)
            domain = parsed.netloc.replace("www.", "")
        except:
            domain = website_url
    
    # Get actual metric values for dynamic messages
    raw_cwv = observed.raw_cwv
    raw_serp = observed.raw_serp
    raw_domain = observed.raw_domain_info
    
    # Compute ratios for each component
    risk_candidates = []
    
    # CWV: score out of 20
    cwv_ratio = observed.core_web_vitals / 20.0
    cwv_score = observed.core_web_vitals
    lcp_value = f"{raw_cwv.lcp_ms}ms" if raw_cwv.lcp_ms else "unmeasurable"
    
    if cwv_ratio < 0.4:
        msg = f"CRITICAL PERFORMANCE COLLAPSE: {domain} shows extreme latency (LCP: {lcp_value}). Scoring {cwv_score}/20 on Core Web Vitals - actively hemorrhaging users."
        risk_candidates.append((cwv_ratio, msg))
    elif cwv_ratio < 0.6:
        msg = f"TECHNICAL DECAY: {domain} has major performance issues (LCP: {lcp_value}). Core Web Vitals at {cwv_score}/20 indicates structural speed problems."
        risk_candidates.append((cwv_ratio, msg))
    elif cwv_ratio < 0.8:
        msg = f"UNSTABLE PERFORMANCE: {domain} scoring {cwv_score}/20 on Core Web Vitals. Speed inconsistencies affecting user experience."
        risk_candidates.append((cwv_ratio, msg))
    
    # On-page: score out of 15
    onpage_ratio = observed.onpage / 15.0
    onpage_score = observed.onpage
    
    if onpage_ratio < 0.5:
        msg = f"STRUCTURAL CATASTROPHE: {domain} critical SEO signals scoring only {onpage_score}/15. Title, Meta, or H1 tags are missing or misconfigured."
        risk_candidates.append((onpage_ratio, msg))
    elif onpage_ratio < 0.75:
        msg = f"SIGNAL MISALIGNMENT: {domain} on-page SEO at {onpage_score}/15. Search engines may struggle to interpret page relevance."
        risk_candidates.append((onpage_ratio, msg))
    
    # Authority: score out of 10
    authority_ratio = observed.authority_proxies / 10.0
    authority_score = observed.authority_proxies
    domain_age = f"{raw_domain.age_years} years" if raw_domain.age_years else "unknown age"
    
    if authority_ratio < 0.5:
        msg = f"AUTHORITY VOID: {domain} ({domain_age}) shows minimal trust signals. Authority score {authority_score}/10 - invisible to organic ecosystem."
        risk_candidates.append((authority_ratio, msg))
    elif authority_ratio < 0.75:
        msg = f"AUTHORITY DEFICIT: {domain} trust signals at {authority_score}/10 significantly lag behind competitors in this space."
        risk_candidates.append((authority_ratio, msg))
    
    # SERP: score out of 5
    serp_ratio = observed.serp_reality / 5.0
    serp_score = observed.serp_reality
    top10_hits = raw_serp.hits_top10 if raw_serp.hits_top10 is not None else 0
    top30_hits = raw_serp.hits_top30 if raw_serp.hits_top30 is not None else 0
    
    if serp_ratio < 0.5:
        msg = f"ORGANIC OBSOLESCENCE: {domain} has only {top10_hits} top-10 positions ({top30_hits} in top-30). SERP reality score: {serp_score}/5 - critical visibility gap."
        risk_candidates.append((serp_ratio, msg))
    elif serp_ratio < 0.75:
        msg = f"FRAGMENTED VISIBILITY: {domain} achieving {top10_hits} top-10 rankings but scoring {serp_score}/5 on SERP reality. Inconsistent positioning detected."
        risk_candidates.append((serp_ratio, msg))
    
    # Check declared vs observed gap
    gap = declared.total - observed.total
    if gap > 10:
        msg = f"CAPABILITY HALLUCINATION: {domain} self-assessed at {declared.total}/50 but observed reality is {observed.total}/50 - a {gap}-point disconnect from technical truth."
        risk_candidates.append((0.0, msg))
    elif gap < -10:
        msg = f"UNDERUTILIZED ENGINE: {domain} technical execution ({observed.total}/50) exceeds strategic alignment ({declared.total}/50). {abs(gap)} points of untapped potential."
        risk_candidates.append((0.0, msg))
    
    # Sort by ratio (ascending = weakest first)
    risk_candidates.sort(key=lambda x: x[0])
    
    # Take top 3 unique risks
    risks = []
    for _, msg in risk_candidates:
        if len(risks) < 3:
            risks.append(msg)
    
    # If we don't have 3 risks, add context-aware fallbacks
    while len(risks) < 3:
        if cwv_ratio >= 0.8 and len([r for r in risks if "Web Vitals" in r]) == 0:
            risks.append(f"MONITORING ADVISED: {domain} Core Web Vitals are acceptable but should be continuously monitored for regression.")
        elif onpage_ratio >= 0.75 and len([r for r in risks if "on-page" in r.lower()]) == 0:
            risks.append(f"OPTIMIZATION OPPORTUNITY: {domain} on-page elements are functional but could be enhanced for better search visibility.")
        else:
            risks.append(f"CONTINUOUS IMPROVEMENT: {domain} should maintain regular SEO audits to stay competitive in search rankings.")
            break
    
    return risks[:3]


def generate_grader_response(
    declared: DeclaredScoreResult,
    observed: ObservedScoreResult,
    website_url: str = ""
) -> GraderResponse:
    """
    Generate the complete presentation-ready response.
    
    This is the main function that assembles all components
    into the final JSON response structure.
    
    Args:
        declared: Declared evaluation result
        observed: Observed evaluation result
        website_url: The analyzed website URL for context
        
    Returns:
        GraderResponse ready for JSON serialization
    """
    # Compute final score
    total_score = compute_final_score(declared, observed)
    
    # Determine stage
    stage = compute_stage(total_score)
    
    # Compute gap description
    gap_description = compute_gap_description(declared.total, observed.total)
    
    # Identify risks with site-specific context
    top_risks = identify_top_risks(declared, observed, website_url)
    
    # Build dimension scores
    dimension_scores = DimensionScores(
        declared=DeclaredScores(
            technical=declared.technical,
            content_keywords=declared.content_keywords,
            measurement=declared.measurement,
        ),
        observed=ObservedScores(
            core_web_vitals=observed.core_web_vitals,
            onpage=observed.onpage,
            authority_proxies=observed.authority_proxies,
            serp_reality=observed.serp_reality,
        ),
    )
    
    # Build raw signals summary
    raw_cwv = observed.raw_cwv
    raw_onpage = observed.raw_onpage
    raw_domain = observed.raw_domain_info
    raw_serp = observed.raw_serp
    
    # Determine onpage notes based on bot blocking
    onpage_notes = None
    if raw_onpage.bot_blocked:
        onpage_notes = "Site restricts automated access - on-page data estimated"
    elif raw_onpage.error:
        onpage_notes = raw_onpage.error
    
    raw_signals = RawSignalsSummary(
        lcp_ms=raw_cwv.lcp_ms,
        cls=raw_cwv.cls,
        inp_ms=raw_cwv.inp_ms,
        cwv_notes=raw_cwv.error,  # Pass the error/notes explaining why data might be missing
        # For bot-blocked sites, return None instead of False (means "unknown" not "missing")
        title_present=raw_onpage.title_present if not raw_onpage.bot_blocked else None,
        meta_unique=raw_onpage.meta_unique if not raw_onpage.bot_blocked else None,
        h1_present=raw_onpage.h1_present,
        onpage_notes=onpage_notes,
        domain_age_years=raw_domain.age_years,
        referring_domains_estimate=observed.raw_authority.referring_domains,
        serp_hits_top10=raw_serp.hits_top10,
        serp_hits_top30=raw_serp.hits_top30,
    )
    
    # Generate timestamp
    generated_at = datetime.now().astimezone().isoformat()
    
    # Add brutal warning if chaotic
    final_notes = observed.notes
    if total_score <= 30:
        error_codes = ["ERR_STRUCTURAL_DECAY", "ERR_AUTHORITY_VOID", "ERR_CRAWL_TRAP"]
        import random
        selected_err = random.choice(error_codes)
        final_notes = f"CRITICAL SYSTEM FAILURE [{selected_err}]: {final_notes} Structural SEO deficiencies detected. Immediate remediation required to prevent total organic obsolescence and permanent market irrelevance."

    return GraderResponse(
        total_score=total_score,
        stage=stage,
        questionnaire_score=declared.total,
        observed_score=observed.total,
        dimension_scores=dimension_scores,
        declared_vs_observed_gap=gap_description,
        top_risks=top_risks,
        raw_signals_summary=raw_signals,
        notes=final_notes,
        generated_at=generated_at,
    )
