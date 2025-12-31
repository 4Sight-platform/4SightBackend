"""
Unit tests for scoring logic.

Tests the deterministic scoring functions with exact expected outputs.
"""

import pytest
from evaluators.declared_evaluator import DeclaredEvaluator, DeclaredScoreResult
from evaluators.scoring import compute_final_score, identify_top_risks, compute_gap_description
from models.schemas import QuestionnaireAnswers
from utils.rounding import (
    round_half_up,
    compute_dimension_score,
    compute_observed_bucket_score,
    compute_stage,
    compute_gap_description,
)


class TestRoundHalfUp:
    """Tests for round_half_up function."""
    
    def test_round_half_up_rounds_up_on_half(self):
        """0.5 should round up to 1."""
        assert round_half_up(0.5) == 1
        assert round_half_up(2.5) == 3
        assert round_half_up(3.5) == 4
    
    def test_round_half_up_normal_rounding(self):
        """Normal rounding behavior."""
        assert round_half_up(2.4) == 2
        assert round_half_up(2.6) == 3
        assert round_half_up(0.0) == 0
        assert round_half_up(100.0) == 100
    
    def test_round_half_up_negative(self):
        """Negative numbers round away from zero (standard HALF_UP)."""
        assert round_half_up(-2.5) == -3  # Rounds away from zero
        assert round_half_up(-2.4) == -2


class TestDimensionScore:
    """Tests for compute_dimension_score function."""
    
    def test_technical_seo_dimension(self):
        """Test Technical SEO scoring (T1-T4, weight=20)."""
        # Perfect score: all 5s
        # sum=20, max=20, percent=1.0, score=20
        assert compute_dimension_score([5, 5, 5, 5], 20) == 20
        
        # Minimum score: all 1s
        # sum=4, max=20, percent=0.2, score=4
        assert compute_dimension_score([1, 1, 1, 1], 20) == 4
        
        # Mixed: [4, 3, 5, 3]
        # sum=15, max=20, percent=0.75, score=15
        assert compute_dimension_score([4, 3, 5, 3], 20) == 15
    
    def test_content_dimension(self):
        """Test Content & Keywords scoring (C1-C4, weight=20)."""
        # [4, 3, 2, 3] = sum=12, percent=0.6, score=12
        assert compute_dimension_score([4, 3, 2, 3], 20) == 12
    
    def test_measurement_dimension(self):
        """Test Measurement & Analytics scoring (M1-M2, weight=10)."""
        # [2, 3] = sum=5, percent=0.5, score=5
        assert compute_dimension_score([2, 3], 10) == 5
        
        # [5, 5] = sum=10, percent=1.0, score=10
        assert compute_dimension_score([5, 5], 10) == 10
    
    def test_empty_answers(self):
        """Empty answers should return 0."""
        assert compute_dimension_score([], 20) == 0


class TestObservedBucketScore:
    """Tests for compute_observed_bucket_score function."""
    
    def test_cwv_bucket_scoring(self):
        """Test Core Web Vitals bucket (weight=20)."""
        # All three pass: subscore=1.0, score=20
        assert compute_observed_bucket_score(1.0, 20) == 20
        
        # Two of three pass: subscore=0.75, score=15
        assert compute_observed_bucket_score(0.75, 20) == 15
        
        # One of three pass: subscore=0.5, score=10
        assert compute_observed_bucket_score(0.5, 20) == 10
        
        # None pass: subscore=0.25, score=5
        assert compute_observed_bucket_score(0.25, 20) == 5
        
        # Page unreachable: subscore=0.0, score=0
        assert compute_observed_bucket_score(0.0, 20) == 0
    
    def test_onpage_bucket_scoring(self):
        """Test On-page SEO bucket (weight=15)."""
        # Average subscore=0.66 (title good, meta moderate, h1 good)
        assert compute_observed_bucket_score(0.66, 15) == 10
    
    def test_authority_bucket_scoring(self):
        """Test Authority Proxies bucket (weight=10)."""
        assert compute_observed_bucket_score(0.6, 10) == 6
    
    def test_serp_bucket_scoring(self):
        """Test SERP Reality bucket (weight=5)."""
        # 2 of 5 keywords in top 10
        # subscore = 2/5 = 0.4, score = 2
        assert compute_observed_bucket_score(0.4, 5) == 2
    
    def test_subscore_clamping(self):
        """Subscore should be clamped to [0, 1]."""
        # Negative clamped to 0
        assert compute_observed_bucket_score(-0.5, 20) == 0
        
        # Greater than 1 clamped to 1
        assert compute_observed_bucket_score(1.5, 20) == 20


class TestStageMapping:
    """Tests for compute_stage function."""
    
    def test_chaotic_stage(self):
        """Scores 0-30 map to Chaotic."""
        assert compute_stage(0) == "Chaotic"
        assert compute_stage(15) == "Chaotic"
        assert compute_stage(30) == "Chaotic"
    
    def test_reactive_stage(self):
        """Scores 31-50 map to Reactive."""
        assert compute_stage(31) == "Reactive"
        assert compute_stage(40) == "Reactive"
        assert compute_stage(50) == "Reactive"
    
    def test_structured_stage(self):
        """Scores 51-70 map to Structured."""
        assert compute_stage(51) == "Structured"
        assert compute_stage(60) == "Structured"
        assert compute_stage(70) == "Structured"
    
    def test_optimised_stage(self):
        """Scores 71-85 map to Optimised."""
        assert compute_stage(71) == "Optimised"
        assert compute_stage(78) == "Optimised"
        assert compute_stage(85) == "Optimised"
    
    def test_strategic_stage(self):
        """Scores 86-100 map to Strategic."""
        assert compute_stage(86) == "Strategic"
        assert compute_stage(93) == "Strategic"
        assert compute_stage(100) == "Strategic"


class TestGapDescription:
    """Tests for compute_gap_description function."""
    
    def test_minimal_gap(self):
        """Gap <= 3 is Minimal."""
        result = compute_gap_description(32, 30)  # diff=2
        assert "Minimal" in result
        assert "well-aligned" in result
        
        result = compute_gap_description(30, 32)  # diff=-2
        assert "Minimal" in result
    
    def test_moderate_gap_declared_exceeds(self):
        """Gap 4-10 with declared > observed."""
        result = compute_gap_description(35, 28)  # diff=7
        assert "Moderate" in result
        assert "somewhat exceeds" in result
    
    def test_moderate_gap_observed_exceeds(self):
        """Gap 4-10 with observed > declared."""
        result = compute_gap_description(28, 35)  # diff=-7
        assert "Moderate" in result
        assert "observable execution somewhat stronger" in result
    
    def test_high_gap_declared_exceeds(self):
        """Gap > 10 with declared > observed."""
        result = compute_gap_description(40, 25)  # diff=15
        assert "High" in result
        assert "significantly exceeds" in result
    
    def test_high_gap_observed_exceeds(self):
        """Gap > 10 with observed > declared."""
        result = compute_gap_description(25, 40)  # diff=-15
        assert "High" in result
        assert "significantly stronger" in result


class TestDeclaredEvaluator:
    """Tests for DeclaredEvaluator class."""
    
    def test_example_scoring_case(self):
        """
        Test the example from the spec:
        T1=4, T2=3, T3=5, T4=3 → technical=15
        C1=4, C2=3, C3=2, C4=3 → content=12
        M1=2, M2=3 → measurement=5
        Total=32
        """
        answers = QuestionnaireAnswers(
            T1=4, T2=3, T3=5, T4=3,
            C1=4, C2=3, C3=2, C4=3,
            M1=2, M2=3
        )
        
        evaluator = DeclaredEvaluator()
        result = evaluator.evaluate(answers)
        
        assert result.technical == 15
        assert result.content_keywords == 12
        assert result.measurement == 5
        assert result.total == 32
    
    def test_perfect_score(self):
        """All 5s should give maximum score of 50."""
        answers = QuestionnaireAnswers(
            T1=5, T2=5, T3=5, T4=5,
            C1=5, C2=5, C3=5, C4=5,
            M1=5, M2=5
        )
        
        evaluator = DeclaredEvaluator()
        result = evaluator.evaluate(answers)
        
        assert result.technical == 20
        assert result.content_keywords == 20
        assert result.measurement == 10
        assert result.total == 50
    
    def test_minimum_score(self):
        """All 1s should give minimum score."""
        answers = QuestionnaireAnswers(
            T1=1, T2=1, T3=1, T4=1,
            C1=1, C2=1, C3=1, C4=1,
            M1=1, M2=1
        )
        
        evaluator = DeclaredEvaluator()
        result = evaluator.evaluate(answers)
        
        # T: sum=4, percent=0.2, score=4
        assert result.technical == 4
        # C: sum=4, percent=0.2, score=4
        assert result.content_keywords == 4
        # M: sum=2, percent=0.2, score=2
        assert result.measurement == 2
        assert result.total == 10


class TestFinalScoring:
    """Tests for compute_final_score function."""
    
    def test_combined_score(self):
        """Test combining declared and observed scores."""
        from evaluators.declared_evaluator import DeclaredScoreResult
        from evaluators.observed_evaluator import ObservedScoreResult
        from adapters.pagespeed_adapter import CoreWebVitals
        from adapters.serp_adapter import SERPSummary
        from adapters.whois_adapter import DomainInfo
        from adapters.authority_adapter import AuthorityMetrics
        from evaluators.observed_evaluator import OnPageMetrics
        
        declared = DeclaredScoreResult(
            technical=15,
            content_keywords=12,
            measurement=5,
            total=32,
        )
        
        observed = ObservedScoreResult(
            core_web_vitals=14,
            onpage=10,
            authority_proxies=6,
            serp_reality=3,
            total=33,
            raw_cwv=CoreWebVitals(lcp_ms=3000, cls=0.12, inp_ms=240),
            raw_onpage=OnPageMetrics(title_present=True, meta_unique=False),
            raw_domain_info=DomainInfo(domain="example.com", age_years=2),
            raw_serp=SERPSummary(results=[], hits_top10=0, hits_top30=1),
            raw_authority=AuthorityMetrics(domain="example.com", domain_authority=30),
            notes="Test notes",
        )
        
        total = compute_final_score(declared, observed)
        assert total == 65  # 32 + 33


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
