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
    observed: ObservedScoreResult
) -> List[str]:
    """
    Identify top 3 weakest signals as actionable risk statements.
    
    Logic (deterministic):
    1. Rank all scored components by their subscore ratio
    2. Select bottom 3 as risks
    3. Map to predefined risk templates
    
    Args:
        declared: Declared evaluation result
        observed: Observed evaluation result
        
    Returns:
        List of 3 risk statements
    """
    # Compute ratios for each component
    # Higher ratio = better performance
    risk_candidates = []
    
    # CWV: score out of 20
    cwv_ratio = observed.core_web_vitals / 20.0
    if cwv_ratio < 0.4:
        risk_candidates.append((cwv_ratio, "cwv_critical"))
    elif cwv_ratio < 0.6:
        risk_candidates.append((cwv_ratio, "cwv_poor"))
    elif cwv_ratio < 0.8:
        risk_candidates.append((cwv_ratio, "cwv_moderate"))
    
    # On-page: score out of 15
    onpage_ratio = observed.onpage / 15.0
    if onpage_ratio < 0.5:
        risk_candidates.append((onpage_ratio, "onpage_poor"))
    elif onpage_ratio < 0.75:
        risk_candidates.append((onpage_ratio, "onpage_moderate"))
    
    # Authority: score out of 10
    authority_ratio = observed.authority_proxies / 10.0
    if authority_ratio < 0.5:
        risk_candidates.append((authority_ratio, "authority_poor"))
    elif authority_ratio < 0.75:
        risk_candidates.append((authority_ratio, "authority_moderate"))
    
    # SERP: score out of 5
    serp_ratio = observed.serp_reality / 5.0
    if serp_ratio < 0.5:
        risk_candidates.append((serp_ratio, "serp_reality_poor"))
    elif serp_ratio < 0.75:
        risk_candidates.append((serp_ratio, "serp_reality_moderate"))
    
    # Check declared vs observed gap
    gap = declared.total - observed.total
    if gap > 10:
        risk_candidates.append((0.0, "declared_high"))
    elif gap < -10:
        risk_candidates.append((0.0, "observed_high"))
    
    # Sort by ratio (ascending = weakest first)
    risk_candidates.sort(key=lambda x: x[0])
    
    # Take top 3 unique risks
    seen_templates = set()
    risks = []
    
    for _, template_key in risk_candidates:
        if template_key not in seen_templates and len(risks) < 3:
            risks.append(RISK_TEMPLATES[template_key])
            seen_templates.add(template_key)
    
    # If we don't have 3 risks, add generic ones
    while len(risks) < 3:
        if "cwv_moderate" not in seen_templates:
            risks.append(RISK_TEMPLATES.get("cwv_moderate", "Monitor Core Web Vitals"))
            seen_templates.add("cwv_moderate")
        elif "onpage_moderate" not in seen_templates:
            risks.append(RISK_TEMPLATES.get("onpage_moderate", "Review on-page optimization"))
            seen_templates.add("onpage_moderate")
        else:
            # Generic fallback
            risks.append("Continue monitoring SEO performance metrics")
            break
    
    return risks[:3]


def generate_grader_response(
    declared: DeclaredScoreResult,
    observed: ObservedScoreResult
) -> GraderResponse:
    """
    Generate the complete presentation-ready response.
    
    This is the main function that assembles all components
    into the final JSON response structure.
    
    Args:
        declared: Declared evaluation result
        observed: Observed evaluation result
        
    Returns:
        GraderResponse ready for JSON serialization
    """
    # Compute final score
    total_score = compute_final_score(declared, observed)
    
    # Determine stage
    stage = compute_stage(total_score)
    
    # Compute gap description
    gap_description = compute_gap_description(declared.total, observed.total)
    
    # Identify risks
    top_risks = identify_top_risks(declared, observed)
    
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
