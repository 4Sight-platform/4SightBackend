"""
Configuration management for SEO Maturity Grader.

All environment variables are loaded here with their default values.
Required vs optional status is documented for each.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Environment Variable Reference (FREE APIs ONLY):
    - PAGESPEED_API_KEY: Google PageSpeed Insights API key (FREE - 25K queries/day)
    
    All other features use built-in fallback heuristics (no API required).
    """
    
    # Application settings
    app_name: str = "SEO Maturity Grader"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # PageSpeed Insights API (FREE - 25,000 queries/day)
    # Get key at: https://console.cloud.google.com/apis/credentials
    # Enable "PageSpeed Insights API" in Google Cloud Console
    pagespeed_api_key: Optional[str] = None
    
    # PAID APIs DISABLED - Using fallback heuristics instead
    # These are kept as None and not used
    serpapi_key: Optional[str] = None
    gcs_api_key: Optional[str] = None
    gcs_cx: Optional[str] = None
    whoisxml_api_key: Optional[str] = None
    moz_access_id: Optional[str] = None
    moz_secret_key: Optional[str] = None
    ahrefs_api_key: Optional[str] = None
    majestic_api_key: Optional[str] = None
    
    # Cache settings
    cache_ttl_seconds: int = 21600  # 6 hours default
    cache_max_size: int = 1000
    
    # Rate limiting settings
    rate_limit_per_second: float = 1.0
    max_retries: int = 3
    request_timeout_seconds: int = 45  # PageSpeed API can take 20-60s
    max_concurrent_requests: int = 5
    
    # CORS settings
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_service_status() -> dict:
    """
    Returns the configuration status of external services.
    Used by the health endpoint.
    
    NOTE: Only PageSpeed Insights API is supported (FREE).
    All other services use built-in fallback heuristics.
    """
    return {
        "pagespeed": "configured" if settings.pagespeed_api_key else "fallback",
        # Paid APIs disabled - always use fallback heuristics
        "serp": "fallback (free mode)",
        "whois": "fallback (free mode)", 
        "authority": "fallback (free mode)",
    }
