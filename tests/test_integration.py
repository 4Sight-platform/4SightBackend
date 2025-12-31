"""
Integration tests with mocked external APIs.

Tests the complete grader flow with mocked responses.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import Response

from fastapi.testclient import TestClient
from main import app

from adapters.pagespeed_adapter import CoreWebVitals
from adapters.serp_adapter import SERPSummary, SERPResult
from adapters.whois_adapter import DomainInfo
from adapters.authority_adapter import AuthorityMetrics
from evaluators.observed_evaluator import OnPageMetrics


# Test client
client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health endpoint."""
    
    def test_health_returns_ok(self):
        """Health endpoint should return healthy status."""
        response = client.get("/seo/grader/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"
        assert "services" in data


class TestGraderEndpointValidation:
    """Tests for grader endpoint input validation."""
    
    def test_missing_url_returns_422(self):
        """Missing required fields should return 422."""
        response = client.post("/seo/grader/submit", json={})
        assert response.status_code == 422
    
    def test_invalid_url_returns_400(self):
        """Invalid URL should return 400."""
        response = client.post("/seo/grader/submit", json={
            "website_url": "ftp://invalid.com",
            "brand_category": "SaaS",
            "target_keywords": [],
            "questionnaire_answers": {
                "T1": 3, "T2": 3, "T3": 3, "T4": 3,
                "C1": 3, "C2": 3, "C3": 3, "C4": 3,
                "M1": 3, "M2": 3,
            }
        })
        assert response.status_code == 400
    
    def test_localhost_url_rejected(self):
        """Localhost URLs should be rejected for SSRF prevention."""
        response = client.post("/seo/grader/submit", json={
            "website_url": "https://localhost",
            "brand_category": "SaaS",
            "target_keywords": [],
            "questionnaire_answers": {
                "T1": 3, "T2": 3, "T3": 3, "T4": 3,
                "C1": 3, "C2": 3, "C3": 3, "C4": 3,
                "M1": 3, "M2": 3,
            }
        })
        assert response.status_code == 400
        assert "localhost" in response.json()["message"].lower()
    
    def test_private_ip_rejected(self):
        """Private IPs should be rejected for SSRF prevention."""
        response = client.post("/seo/grader/submit", json={
            "website_url": "https://192.168.1.1",
            "brand_category": "SaaS",
            "target_keywords": [],
            "questionnaire_answers": {
                "T1": 3, "T2": 3, "T3": 3, "T4": 3,
                "C1": 3, "C2": 3, "C3": 3, "C4": 3,
                "M1": 3, "M2": 3,
            }
        })
        assert response.status_code == 400
    
    def test_invalid_questionnaire_answer_range(self):
        """Questionnaire answers outside 1-5 should fail validation."""
        response = client.post("/seo/grader/submit", json={
            "website_url": "https://example.com",
            "brand_category": "SaaS",
            "target_keywords": [],
            "questionnaire_answers": {
                "T1": 6,  # Invalid: > 5
                "T2": 3, "T3": 3, "T4": 3,
                "C1": 3, "C2": 3, "C3": 3, "C4": 3,
                "M1": 3, "M2": 3,
            }
        })
        assert response.status_code == 422
    
    def test_too_many_keywords_rejected(self):
        """More than 5 keywords should fail validation."""
        response = client.post("/seo/grader/submit", json={
            "website_url": "https://example.com",
            "brand_category": "SaaS",
            "target_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5", "kw6"],
            "questionnaire_answers": {
                "T1": 3, "T2": 3, "T3": 3, "T4": 3,
                "C1": 3, "C2": 3, "C3": 3, "C4": 3,
                "M1": 3, "M2": 3,
            }
        })
        assert response.status_code == 422


class TestGraderEndpointWithMocks:
    """Integration tests with mocked external API responses."""
    
    @pytest.mark.asyncio
    async def test_complete_grader_flow_mocked(self):
        """Test complete grader flow with mocked observed evaluator."""
        from evaluators.observed_evaluator import ObservedEvaluator, ObservedScoreResult
        
        # Create mock observed result
        mock_observed_result = ObservedScoreResult(
            core_web_vitals=14,
            onpage=10,
            authority_proxies=6,
            serp_reality=3,
            total=33,
            raw_cwv=CoreWebVitals(lcp_ms=3200, cls=0.12, inp_ms=240),
            raw_onpage=OnPageMetrics(
                title_present=True,
                title_length=55,
                title_quality_score=1.0,
                meta_present=True,
                meta_unique=False,
                meta_quality_score=0.66,
                h1_present=True,
                h1_relevance_score=1.0,
            ),
            raw_domain_info=DomainInfo(domain="example.com", age_years=2),
            raw_serp=SERPSummary(
                results=[
                    SERPResult(keyword="seo automation", rank=25, is_top10=False, is_top30=True),
                ],
                hits_top10=0,
                hits_top30=1,
            ),
            raw_authority=AuthorityMetrics(
                domain="example.com",
                domain_authority=30,
                source="fallback",
            ),
            notes="Test notes: Using mocked data.",
        )
        
        # Patch the observed evaluator
        with patch.object(
            ObservedEvaluator,
            'evaluate',
            new_callable=AsyncMock,
            return_value=mock_observed_result
        ):
            response = client.post("/seo/grader/submit", json={
                "website_url": "https://example.com",
                "brand_category": "SaaS",
                "target_keywords": ["seo automation", "rank tracking"],
                "questionnaire_answers": {
                    "T1": 4, "T2": 3, "T3": 5, "T4": 3,
                    "C1": 4, "C2": 3, "C3": 2, "C4": 3,
                    "M1": 2, "M2": 3,
                },
                "client_request_id": "test-123"
            })
        
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        assert "total_score" in data
        assert "stage" in data
        assert "questionnaire_score" in data
        assert "observed_score" in data
        assert "dimension_scores" in data
        assert "declared_vs_observed_gap" in data
        assert "top_risks" in data
        assert "raw_signals_summary" in data
        assert "notes" in data
        assert "generated_at" in data
        
        # Verify questionnaire scoring (deterministic)
        assert data["questionnaire_score"] == 32  # 15 + 12 + 5
        
        # Verify observed score from mock
        assert data["observed_score"] == 33
        
        # Verify total
        assert data["total_score"] == 65  # 32 + 33
        
        # Verify stage
        assert data["stage"] == "Structured"  # 51-70 range
        
        # Verify dimension breakdown
        assert data["dimension_scores"]["declared"]["technical"] == 15
        assert data["dimension_scores"]["declared"]["content_keywords"] == 12
        assert data["dimension_scores"]["declared"]["measurement"] == 5
        
        # Verify raw signals
        raw = data["raw_signals_summary"]
        assert raw["lcp_ms"] == 3200
        assert raw["cls"] == 0.12
        assert raw["title_present"] is True
        
        # Verify top risks has exactly 3 items
        assert len(data["top_risks"]) == 3
    
    def test_response_is_presentation_ready(self):
        """Verify response contains no raw metric blobs, only presentation data."""
        from evaluators.observed_evaluator import ObservedEvaluator, ObservedScoreResult
        
        mock_observed_result = ObservedScoreResult(
            core_web_vitals=20,
            onpage=15,
            authority_proxies=10,
            serp_reality=5,
            total=50,
            raw_cwv=CoreWebVitals(lcp_ms=2000, cls=0.05, inp_ms=150),
            raw_onpage=OnPageMetrics(title_present=True, meta_unique=True),
            raw_domain_info=DomainInfo(domain="example.com", age_years=5),
            raw_serp=SERPSummary(results=[], hits_top10=2, hits_top30=2),
            raw_authority=AuthorityMetrics(domain="example.com", domain_authority=70),
            notes="All services configured.",
        )
        
        with patch.object(
            ObservedEvaluator,
            'evaluate',
            new_callable=AsyncMock,
            return_value=mock_observed_result
        ):
            response = client.post("/seo/grader/submit", json={
                "website_url": "https://example.com",
                "brand_category": "Enterprise",
                "target_keywords": ["enterprise seo"],
                "questionnaire_answers": {
                    "T1": 5, "T2": 5, "T3": 5, "T4": 5,
                    "C1": 5, "C2": 5, "C3": 5, "C4": 5,
                    "M1": 5, "M2": 5,
                }
            })
        
        assert response.status_code == 200
        data = response.json()
        
        # All scores should be integers
        assert isinstance(data["total_score"], int)
        assert isinstance(data["questionnaire_score"], int)
        assert isinstance(data["observed_score"], int)
        
        # Stage should be a readable string
        assert data["stage"] in ["Chaotic", "Reactive", "Structured", "Optimised", "Strategic"]
        
        # Gap should be a descriptive string
        assert isinstance(data["declared_vs_observed_gap"], str)
        assert len(data["declared_vs_observed_gap"]) > 10  # Not empty
        
        # Risks should be list of strings
        assert all(isinstance(r, str) for r in data["top_risks"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
