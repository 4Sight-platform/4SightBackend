"""
Enumerations and constants for SEO Maturity Grader.

This module defines all the fixed values used in the deterministic scoring model.
"""

from enum import Enum
from typing import List


class Stage(str, Enum):
    """
    SEO Maturity Stage labels based on total score.
    
    Mapping (deterministic):
    - 0-30: Chaotic
    - 31-50: Reactive
    - 51-70: Structured
    - 71-85: Optimised
    - 86-100: Strategic
    """
    CHAOTIC = "Chaotic"
    REACTIVE = "Reactive"
    STRUCTURED = "Structured"
    OPTIMISED = "Optimised"
    STRATEGIC = "Strategic"


class BrandCategory(str, Enum):
    """Allowed brand categories for context."""
    SAAS = "SaaS"
    ECOMMERCE = "E-commerce"
    AGENCY = "Agency"
    PUBLISHER = "Publisher"
    LOCAL_BUSINESS = "Local Business"
    ENTERPRISE = "Enterprise"
    STARTUP = "Startup"
    OTHER = "Other"


class GapSeverity(str, Enum):
    """Severity levels for declared vs observed gap."""
    MINIMAL = "Minimal"
    MODERATE = "Moderate"
    HIGH = "High"


# Question IDs - must be provided in questionnaire_answers
TECHNICAL_QUESTIONS: List[str] = ["T1", "T2", "T3", "T4"]
CONTENT_QUESTIONS: List[str] = ["C1", "C2", "C3", "C4"]
MEASUREMENT_QUESTIONS: List[str] = ["M1", "M2"]
QUESTION_IDS: List[str] = TECHNICAL_QUESTIONS + CONTENT_QUESTIONS + MEASUREMENT_QUESTIONS

# Dimension weights for questionnaire (total = 50)
DECLARED_WEIGHTS = {
    "technical": 20,
    "content_keywords": 20,
    "measurement": 10,
}

# Bucket weights for observed metrics (total = 50)
OBSERVED_WEIGHTS = {
    "core_web_vitals": 20,
    "onpage": 15,
    "authority_proxies": 10,
    "serp_reality": 5,
}

# Core Web Vitals thresholds (deterministic)
# Based on Google's "Good" thresholds
CWV_THRESHOLDS = {
    "lcp_good_ms": 2500,      # LCP <= 2.5s is "Good"
    "lcp_poor_ms": 4000,      # LCP > 4s is "Poor"
    "cls_good": 0.1,          # CLS <= 0.1 is "Good"
    "cls_poor": 0.25,         # CLS > 0.25 is "Poor"
    "inp_good_ms": 200,       # INP <= 200ms is "Good"
    "inp_poor_ms": 500,       # INP > 500ms is "Poor"
}

# Stage thresholds (deterministic mapping)
STAGE_THRESHOLDS = [
    (0, 30, Stage.CHAOTIC),
    (31, 50, Stage.REACTIVE),
    (51, 70, Stage.STRUCTURED),
    (71, 85, Stage.OPTIMISED),
    (86, 100, Stage.STRATEGIC),
]

# Gap threshold definitions
GAP_THRESHOLDS = {
    "minimal_max": 3,    # abs(diff) <= 3 → Minimal
    "moderate_max": 10,  # 4 <= abs(diff) <= 10 → Moderate
    # abs(diff) > 10 → High
}

# Questionnaire question text (for reference and frontend display)
QUESTIONNAIRE_QUESTIONS = {
    "T1": "How would you rate your website's page load speed and Core Web Vitals optimization?",
    "T2": "How effectively is your site crawlable and indexable by search engines?",
    "T3": "How well-implemented is your technical SEO infrastructure (sitemaps, robots.txt, structured data)?",
    "T4": "How secure and mobile-friendly is your website (HTTPS, responsive design)?",
    "C1": "How comprehensive is your keyword research and targeting strategy?",
    "C2": "How well-optimized is your on-page content (titles, meta descriptions, headers)?",
    "C3": "How consistent is your content creation and publishing schedule?",
    "C4": "How effectively do you align content with user search intent?",
    "M1": "How well do you track and measure SEO performance metrics?",
    "M2": "How effectively do you use data to inform SEO strategy decisions?",
}

# Answer scale descriptions
ANSWER_SCALE = {
    1: "Not at all / Never",
    2: "Rarely / Minimal effort",
    3: "Sometimes / Moderate effort",
    4: "Often / Good effort",
    5: "Always / Excellent",
}

# Risk message templates (deterministic)
RISK_TEMPLATES = {
    "cwv_critical": "CRITICAL PERFORMANCE COLLAPSE: Extreme latency detected. Site is actively hemorrhaging users and crawler efficiency.",
    "cwv_poor": "TECHNICAL DECAY: Major performance bottlenecks. Core Web Vitals are in a state of failure.",
    "cwv_moderate": "UNSTABLE PERFORMANCE: Inconsistent user experience. Structural speed issues are developing.",
    "onpage_poor": "STRUCTURAL CATASTROPHE: Fundamental SEO signals (Title, Meta, H1) are missing or catastrophically misconfigured.",
    "onpage_moderate": "SIGNAL MISALIGNMENT: Search engines are likely failing to interpret page relevance correctly.",
    "authority_poor": "TOTAL AUTHORITY VOID: Zero trust signals detected. Domain is invisible to the broader organic ecosystem.",
    "authority_moderate": "AUTHORITY DEFICIT: Domain trust signals are significantly lagging behind market reality.",
    "serp_reality_poor": "ORGANIC OBSOLESCENCE: Critical target keywords have zero visibility in top SERP tiers.",
    "serp_reality_moderate": "FRAGMENTED VISIBILITY: Target keywords are failing to achieve or maintain consistent positioning.",
    "declared_high": "CAPABILITY HALLUCINATION: Self-assessed SEO maturity is radically disconnected from observable technical reality.",
    "observed_high": "UNDERUTILIZED ENGINE: Technical execution is strong but is being wasted by an unaligned strategy.",
}
