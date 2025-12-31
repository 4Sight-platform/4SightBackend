"""
Pydantic schemas for SEO Maturity Grader API.

Defines request and response models with strict validation.
All schemas are designed for deterministic, presentation-ready output.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from .enums import Stage, BrandCategory, QUESTION_IDS


class QuestionnaireAnswers(BaseModel):
    """
    Questionnaire answers model.
    All 10 questions (T1-T4, C1-C4, M1-M2) must have integer values 1-5.
    """
    T1: int = Field(..., ge=1, le=5, description="Technical SEO Q1 score")
    T2: int = Field(..., ge=1, le=5, description="Technical SEO Q2 score")
    T3: int = Field(..., ge=1, le=5, description="Technical SEO Q3 score")
    T4: int = Field(..., ge=1, le=5, description="Technical SEO Q4 score")
    C1: int = Field(..., ge=1, le=5, description="Content & Keywords Q1 score")
    C2: int = Field(..., ge=1, le=5, description="Content & Keywords Q2 score")
    C3: int = Field(..., ge=1, le=5, description="Content & Keywords Q3 score")
    C4: int = Field(..., ge=1, le=5, description="Content & Keywords Q4 score")
    M1: int = Field(..., ge=1, le=5, description="Measurement & Analytics Q1 score")
    M2: int = Field(..., ge=1, le=5, description="Measurement & Analytics Q2 score")


class GraderRequest(BaseModel):
    """
    Request schema for POST /seo/grader/submit.
    
    All inputs are validated to ensure deterministic processing.
    """
    website_url: str = Field(
        ...,
        min_length=10,
        max_length=2048,
        description="Website URL to analyze (HTTPS recommended, HTTP allowed with warning)"
    )
    brand_category: str = Field(
        ...,
        description="Brand/business category for context"
    )
    target_keywords: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Up to 5 target keywords for SERP reality check"
    )
    questionnaire_answers: QuestionnaireAnswers = Field(
        ...,
        description="Answers to 10 questionnaire questions"
    )
    client_request_id: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional client-provided request ID for tracing"
    )
    
    @field_validator('target_keywords')
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        """Validate and normalize keywords."""
        if len(v) > 5:
            raise ValueError("Maximum 5 keywords allowed")
        
        # Trim each keyword to 80 chars max and remove duplicates
        normalized = []
        seen = set()
        for kw in v:
            trimmed = kw.strip()[:80]
            if trimmed and trimmed.lower() not in seen:
                normalized.append(trimmed)
                seen.add(trimmed.lower())
        
        return normalized
    
    @field_validator('brand_category')
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate brand category."""
        # Allow any string but normalize common variations
        return v.strip()


class DeclaredScores(BaseModel):
    """Scores from questionnaire (declared capabilities)."""
    technical: int = Field(..., ge=0, le=20, description="Technical SEO score (0-20)")
    content_keywords: int = Field(..., ge=0, le=20, description="Content & Keywords score (0-20)")
    measurement: int = Field(..., ge=0, le=10, description="Measurement & Analytics score (0-10)")


class ObservedScores(BaseModel):
    """Scores from observed website metrics."""
    core_web_vitals: int = Field(..., ge=0, le=20, description="Core Web Vitals score (0-20)")
    onpage: int = Field(..., ge=0, le=15, description="On-page SEO score (0-15)")
    authority_proxies: int = Field(..., ge=0, le=10, description="Authority proxies score (0-10)")
    serp_reality: int = Field(..., ge=0, le=5, description="SERP reality check score (0-5)")


class DimensionScores(BaseModel):
    """Combined dimension scores for both declared and observed."""
    declared: DeclaredScores
    observed: ObservedScores


class RawSignalsSummary(BaseModel):
    """
    Raw signals summary for transparency.
    Shows the actual measured values before scoring transformation.
    """
    lcp_ms: Optional[int] = Field(None, description="Largest Contentful Paint in milliseconds")
    cls: Optional[float] = Field(None, description="Cumulative Layout Shift score")
    inp_ms: Optional[int] = Field(None, description="Interaction to Next Paint in milliseconds")
    cwv_notes: Optional[str] = Field(None, description="Explanation for missing or approximate CWV data")
    title_present: Optional[bool] = Field(None, description="Whether page has a title tag (None if bot-blocked)")
    meta_unique: Optional[bool] = Field(None, description="Whether meta description appears unique (None if bot-blocked)")
    h1_present: bool = Field(default=True, description="Whether page has H1 tag")
    onpage_notes: Optional[str] = Field(None, description="Notes about on-page analysis (e.g. bot blocked)")
    domain_age_years: Optional[int] = Field(None, description="Domain age in years")
    referring_domains_estimate: Optional[int] = Field(None, description="Estimated referring domains count")
    serp_hits_top10: int = Field(0, description="Number of keywords ranking in top 10")
    serp_hits_top30: int = Field(0, description="Number of keywords ranking in top 30")


class GraderResponse(BaseModel):
    """
    Response schema for POST /seo/grader/submit.
    
    This is a presentation-ready response - the frontend should render
    this structure directly without implementing any scoring logic.
    """
    total_score: int = Field(..., ge=0, le=100, description="Total SEO maturity score (0-100)")
    stage: str = Field(..., description="Maturity stage label")
    questionnaire_score: int = Field(..., ge=0, le=50, description="Sum of declared dimension scores")
    observed_score: int = Field(..., ge=0, le=50, description="Sum of observed dimension scores")
    dimension_scores: DimensionScores = Field(..., description="Breakdown by dimension")
    declared_vs_observed_gap: str = Field(
        ...,
        description="Deterministic gap description between declared and observed scores"
    )
    top_risks: List[str] = Field(
        ...,
        max_length=3,
        description="Top 3 weakest signals as actionable risk statements"
    )
    raw_signals_summary: RawSignalsSummary = Field(
        ...,
        description="Raw measured values for transparency"
    )
    notes: str = Field(
        ...,
        description="Notes about data sources and any approximations used"
    )
    generated_at: str = Field(
        ...,
        description="ISO 8601 timestamp of when the report was generated"
    )
    
    @staticmethod
    def generate_timestamp() -> str:
        """Generate deterministic timestamp in ISO 8601 format."""
        return datetime.now().astimezone().isoformat()


class ServiceStatus(BaseModel):
    """Status of individual external services."""
    pagespeed: str = Field(..., description="PageSpeed API status: configured|fallback")
    serp: str = Field(..., description="SERP API status: configured|gcs|fallback")
    whois: str = Field(..., description="WHOIS API status: configured|fallback")
    authority: str = Field(..., description="Authority API status: moz|ahrefs|majestic|fallback")


class HealthResponse(BaseModel):
    """Response schema for GET /seo/grader/health."""
    status: str = Field(default="healthy", description="Overall health status")
    version: str = Field(..., description="API version")
    services: ServiceStatus = Field(..., description="External service configuration status")


class ErrorResponse(BaseModel):
    """Standardized error response."""
    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Client request ID if provided")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "VALIDATION_ERROR",
                "message": "Invalid input: website_url must be a valid URL",
                "details": {"field": "website_url"},
                "request_id": "abc-123"
            }
        }
