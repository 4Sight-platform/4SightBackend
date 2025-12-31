"""
URL validation and SSRF prevention utilities.

This module provides deterministic URL validation to ensure:
1. Only http/https schemes are allowed
2. Private IPs and localhost are rejected to prevent SSRF
3. URLs are normalized consistently for caching
"""

import ipaddress
import re
from urllib.parse import urlparse, urlunparse
from typing import Tuple, Optional


# RFC1918 private IP ranges + loopback + link-local
PRIVATE_IP_PATTERNS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

# Patterns that indicate localhost or internal hostnames
LOCALHOST_PATTERNS = [
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
]


def is_private_ip(ip_str: str) -> bool:
    """
    Check if an IP address is in a private/reserved range.
    
    Args:
        ip_str: IP address as string
        
    Returns:
        True if the IP is private/reserved, False otherwise
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in PRIVATE_IP_PATTERNS:
            if ip in network:
                return True
        return False
    except ValueError:
        # Not a valid IP address, likely a hostname
        return False


def is_localhost(hostname: str) -> bool:
    """
    Check if hostname refers to localhost.
    
    Args:
        hostname: Hostname to check
        
    Returns:
        True if hostname is localhost variant
    """
    hostname_lower = hostname.lower().strip()
    
    # Direct localhost patterns
    if hostname_lower in LOCALHOST_PATTERNS:
        return True
    
    # Check for localhost subdomains
    if hostname_lower.endswith(".localhost"):
        return True
    
    return False


def is_ssrf_safe(hostname: str) -> Tuple[bool, Optional[str]]:
    """
    Check if hostname is safe from SSRF attacks.
    
    This performs deterministic checks against known private ranges
    and localhost patterns. DNS resolution is NOT performed here
    to maintain determinism.
    
    Args:
        hostname: Hostname or IP address to validate
        
    Returns:
        Tuple of (is_safe, error_message)
        If is_safe is True, error_message is None
    """
    if not hostname:
        return False, "Empty hostname"
    
    hostname = hostname.strip().lower()
    
    # Check for localhost patterns
    if is_localhost(hostname):
        return False, "Localhost URLs are not allowed"
    
    # Check if it's a direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if is_private_ip(hostname):
            return False, f"Private IP addresses are not allowed: {hostname}"
        # It's a valid non-private IP
        return True, None
    except ValueError:
        # Not an IP address, it's a hostname
        pass
    
    # Check for numeric hostnames that might resolve to private IPs
    # e.g., 192.168.1.1.nip.io, 127.0.0.1.xip.io
    ip_like_pattern = re.compile(
        r'^(\d{1,3}\.){3}\d{1,3}(?:\.[a-z]+)?$|'  # IPv4-like
        r'^0x[0-9a-f]+$|'                          # Hex encoding
        r'^\d+$'                                    # Decimal encoding
    )
    if ip_like_pattern.match(hostname):
        return False, "Suspicious hostname pattern detected"
    
    # Hostname appears valid
    return True, None


def validate_url(url: str) -> Tuple[bool, str, Optional[str]]:
    """
    Validate a URL for SEO analysis.
    
    Performs the following checks:
    1. Parses URL structure
    2. Validates scheme (http/https only)
    3. Ensures hostname is present
    4. Checks for SSRF safety
    
    Args:
        url: URL string to validate
        
    Returns:
        Tuple of (is_valid, normalized_url_or_original, error_message)
        If valid, returns (True, normalized_url, None)
        If invalid, returns (False, original_url, error_message)
    """
    if not url:
        return False, url, "URL is required"
    
    url = url.strip()
    
    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, url, f"Invalid URL format: {str(e)}"
    
    # Check scheme
    if parsed.scheme not in ("http", "https"):
        if not parsed.scheme:
            # Try adding https://
            url = f"https://{url}"
            try:
                parsed = urlparse(url)
            except Exception:
                return False, url, "Could not parse URL even with https:// prefix"
        else:
            return False, url, f"Invalid scheme: {parsed.scheme}. Only http and https are allowed"
    
    # Check for hostname
    if not parsed.hostname:
        return False, url, "URL must have a valid hostname"
    
    # SSRF check
    is_safe, ssrf_error = is_ssrf_safe(parsed.hostname)
    if not is_safe:
        return False, url, ssrf_error
    
    # Normalize URL
    normalized = normalize_url(parsed)
    
    # Generate warning for HTTP
    warning = None
    if parsed.scheme == "http":
        warning = "HTTP URL detected. HTTPS is recommended for security."
    
    return True, normalized, warning


def normalize_url(parsed) -> str:
    """
    Normalize a parsed URL for consistent caching.
    
    Normalization rules:
    1. Lowercase scheme and hostname
    2. Remove default ports (80 for http, 443 for https)
    3. Remove trailing slash from path (except for root)
    4. Sort query parameters (not implemented yet for simplicity)
    
    Args:
        parsed: ParseResult from urlparse
        
    Returns:
        Normalized URL string
    """
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    
    # Handle port
    port = parsed.port
    if port:
        # Remove default ports
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            port = None
    
    netloc = hostname
    if port:
        netloc = f"{hostname}:{port}"
    
    # Normalize path
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    
    # Rebuild URL
    normalized = urlunparse((
        scheme,
        netloc,
        path,
        "",  # params
        parsed.query,
        ""   # fragment (removed for caching)
    ))
    
    return normalized


def extract_domain(url: str) -> Optional[str]:
    """
    Extract the domain from a URL.
    
    Args:
        url: URL string
        
    Returns:
        Domain string or None if extraction fails
    """
    try:
        parsed = urlparse(url)
        return parsed.hostname.lower() if parsed.hostname else None
    except Exception:
        return None
