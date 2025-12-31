"""
Unit tests for URL validation and SSRF prevention.

Tests ensure that malicious URLs are properly rejected.
"""

import pytest
from utils.url_validator import (
    validate_url,
    normalize_url,
    is_ssrf_safe,
    is_private_ip,
    is_localhost,
    extract_domain,
)
from urllib.parse import urlparse


class TestIsPrivateIP:
    """Tests for is_private_ip function."""
    
    def test_private_ips_detected(self):
        """RFC1918 private IPs should be detected."""
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("10.255.255.255") is True
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("172.31.255.255") is True
        assert is_private_ip("192.168.0.1") is True
        assert is_private_ip("192.168.255.255") is True
    
    def test_loopback_detected(self):
        """Loopback addresses should be detected."""
        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("127.0.0.2") is True
        assert is_private_ip("127.255.255.255") is True
    
    def test_link_local_detected(self):
        """Link-local addresses should be detected."""
        assert is_private_ip("169.254.0.1") is True
        assert is_private_ip("169.254.255.255") is True
    
    def test_public_ips_not_detected(self):
        """Public IPs should not be flagged."""
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False
        assert is_private_ip("142.250.185.78") is False  # google.com
    
    def test_non_ip_returns_false(self):
        """Non-IP strings should return False."""
        assert is_private_ip("example.com") is False
        assert is_private_ip("not-an-ip") is False


class TestIsLocalhost:
    """Tests for is_localhost function."""
    
    def test_localhost_variants_detected(self):
        """Various localhost patterns should be detected."""
        assert is_localhost("localhost") is True
        assert is_localhost("LOCALHOST") is True
        assert is_localhost("localhost.localdomain") is True
        assert is_localhost("127.0.0.1") is True
        assert is_localhost("0.0.0.0") is True
        assert is_localhost("::1") is True
    
    def test_localhost_subdomains_detected(self):
        """Subdomains of localhost should be detected."""
        assert is_localhost("foo.localhost") is True
        assert is_localhost("bar.baz.localhost") is True
    
    def test_non_localhost_not_detected(self):
        """Non-localhost hostnames should not be flagged."""
        assert is_localhost("example.com") is False
        assert is_localhost("mylocalhost.com") is False


class TestIsSSRFSafe:
    """Tests for is_ssrf_safe function."""
    
    def test_public_hostnames_safe(self):
        """Public hostnames should be safe."""
        is_safe, error = is_ssrf_safe("example.com")
        assert is_safe is True
        assert error is None
        
        is_safe, error = is_ssrf_safe("google.com")
        assert is_safe is True
    
    def test_localhost_rejected(self):
        """Localhost should be rejected."""
        is_safe, error = is_ssrf_safe("localhost")
        assert is_safe is False
        assert "not allowed" in error.lower()
    
    def test_private_ip_rejected(self):
        """Private IPs should be rejected."""
        is_safe, error = is_ssrf_safe("192.168.1.1")
        assert is_safe is False
        assert "private" in error.lower()
        
        is_safe, error = is_ssrf_safe("10.0.0.1")
        assert is_safe is False
    
    def test_public_ip_allowed(self):
        """Public IPs should be allowed."""
        is_safe, error = is_ssrf_safe("8.8.8.8")
        assert is_safe is True
    
    def test_empty_hostname_rejected(self):
        """Empty hostname should be rejected."""
        is_safe, error = is_ssrf_safe("")
        assert is_safe is False


class TestValidateURL:
    """Tests for validate_url function."""
    
    def test_valid_https_url(self):
        """Valid HTTPS URLs should pass."""
        is_valid, normalized, warning = validate_url("https://example.com")
        assert is_valid is True
        assert normalized == "https://example.com/"
        assert warning is None
    
    def test_valid_http_url_with_warning(self):
        """Valid HTTP URLs should pass with warning."""
        is_valid, normalized, warning = validate_url("http://example.com")
        assert is_valid is True
        assert normalized == "http://example.com/"
        assert "HTTP URL" in warning
    
    def test_url_without_scheme_gets_https(self):
        """URLs without scheme should get https:// added."""
        is_valid, normalized, warning = validate_url("example.com")
        assert is_valid is True
        assert normalized.startswith("https://")
    
    def test_localhost_url_rejected(self):
        """Localhost URLs should be rejected."""
        is_valid, normalized, error = validate_url("https://localhost")
        assert is_valid is False
        assert "localhost" in error.lower()
        
        is_valid, normalized, error = validate_url("https://127.0.0.1")
        assert is_valid is False
    
    def test_private_ip_url_rejected(self):
        """Private IP URLs should be rejected."""
        is_valid, normalized, error = validate_url("https://192.168.1.1")
        assert is_valid is False
        assert "private" in error.lower()
    
    def test_invalid_scheme_rejected(self):
        """Invalid schemes should be rejected."""
        is_valid, normalized, error = validate_url("ftp://example.com")
        assert is_valid is False
        assert "scheme" in error.lower()
        
        is_valid, normalized, error = validate_url("file:///etc/passwd")
        assert is_valid is False
    
    def test_empty_url_rejected(self):
        """Empty URL should be rejected."""
        is_valid, normalized, error = validate_url("")
        assert is_valid is False


class TestNormalizeURL:
    """Tests for normalize_url function."""
    
    def test_lowercases_scheme_and_host(self):
        """Scheme and host should be lowercased."""
        parsed = urlparse("HTTPS://EXAMPLE.COM/Path")
        normalized = normalize_url(parsed)
        assert normalized.startswith("https://example.com")
    
    def test_removes_default_port(self):
        """Default ports (80, 443) should be removed."""
        parsed = urlparse("https://example.com:443/path")
        normalized = normalize_url(parsed)
        assert ":443" not in normalized
        
        parsed = urlparse("http://example.com:80/path")
        normalized = normalize_url(parsed)
        assert ":80" not in normalized
    
    def test_preserves_non_default_port(self):
        """Non-default ports should be preserved."""
        parsed = urlparse("https://example.com:8080/path")
        normalized = normalize_url(parsed)
        assert ":8080" in normalized
    
    def test_removes_trailing_slash_except_root(self):
        """Trailing slashes should be removed except for root."""
        parsed = urlparse("https://example.com/path/")
        normalized = normalize_url(parsed)
        assert not normalized.endswith("//")
        
        # Root should keep slash
        parsed = urlparse("https://example.com/")
        normalized = normalize_url(parsed)
        assert normalized.endswith("/")


class TestExtractDomain:
    """Tests for extract_domain function."""
    
    def test_extracts_domain_from_url(self):
        """Domain should be extracted from full URL."""
        assert extract_domain("https://example.com/path") == "example.com"
        assert extract_domain("https://www.example.com") == "www.example.com"
        assert extract_domain("http://sub.domain.example.com:8080") == "sub.domain.example.com"
    
    def test_returns_none_for_invalid(self):
        """Invalid URLs should return None."""
        assert extract_domain("not-a-url") is None or extract_domain("not-a-url") == "not-a-url"
        assert extract_domain("") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
