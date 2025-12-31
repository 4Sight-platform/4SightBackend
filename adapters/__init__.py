"""Adapters package for external API integrations."""

from .pagespeed_adapter import PageSpeedAdapter
from .serp_adapter import SERPAdapter
from .whois_adapter import WhoisAdapter
from .authority_adapter import AuthorityAdapter

__all__ = [
    "PageSpeedAdapter",
    "SERPAdapter", 
    "WhoisAdapter",
    "AuthorityAdapter",
]
