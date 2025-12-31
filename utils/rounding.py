"""
Deterministic rounding utilities.

This module provides the round_half_up function and dimension score
computation to ensure consistent, reproducible scoring across all runs.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List


def round_half_up(value: float, decimals: int = 0) -> int:
    """
    Round a number using "round half up" strategy.
    
    This ensures deterministic rounding where 0.5 always rounds up,
    avoiding Python's default banker's rounding.
    
    Args:
        value: Number to round
        decimals: Number of decimal places (0 for integer)
        
    Returns:
        Rounded integer
        
    Examples:
        >>> round_half_up(2.5)
        3
        >>> round_half_up(3.5)
        4
        >>> round_half_up(2.4)
        2
    """
    if decimals == 0:
        # Convert to Decimal for precise rounding
        d = Decimal(str(value))
        rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(rounded)
    else:
        quantize_str = "0." + "0" * decimals
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)
        return float(rounded)


def compute_dimension_score(
    answers: List[int],
    weight: int,
    max_per_answer: int = 5
) -> int:
    """
    Compute a weighted dimension score from questionnaire answers.
    
    Formula:
        raw_sum = sum(answers)
        max_possible = max_per_answer × len(answers)
        raw_percent = raw_sum / max_possible
        score = round_half_up(raw_percent × weight)
    
    Args:
        answers: List of answer values (each 1-5)
        weight: Maximum points for this dimension
        max_per_answer: Maximum value per answer (default 5)
        
    Returns:
        Dimension score as integer
        
    Examples:
        >>> compute_dimension_score([4, 3, 5, 3], 20)  # Technical SEO
        15
        >>> compute_dimension_score([2, 3], 10)  # Measurement
        5
    """
    if not answers:
        return 0
    
    raw_sum = sum(answers)
    max_possible = max_per_answer * len(answers)
    
    if max_possible == 0:
        return 0
    
    raw_percent = raw_sum / max_possible
    score = round_half_up(raw_percent * weight)
    
    # Ensure score doesn't exceed weight (safety cap)
    return min(score, weight)


def compute_observed_bucket_score(subscore: float, weight: int) -> int:
    """
    Compute a weighted bucket score from an observed subscore.
    
    Formula:
        score = round_half_up(subscore × weight)
    
    Args:
        subscore: Normalized subscore between 0.0 and 1.0
        weight: Maximum points for this bucket
        
    Returns:
        Bucket score as integer
        
    Examples:
        >>> compute_observed_bucket_score(0.75, 20)  # CWV passing 2 of 3
        15
        >>> compute_observed_bucket_score(0.5, 15)   # On-page average
        8
    """
    # Clamp subscore to [0, 1]
    clamped = max(0.0, min(1.0, subscore))
    score = round_half_up(clamped * weight)
    
    # Ensure score doesn't exceed weight (safety cap)
    return min(score, weight)


def compute_stage(total_score: int) -> str:
    """
    Map total score to maturity stage label.
    
    Deterministic mapping:
        0-30: Chaotic
        31-50: Reactive
        51-70: Structured
        71-85: Optimised
        86-100: Strategic
    
    Args:
        total_score: Total score (0-100)
        
    Returns:
        Stage label string
    """
    if total_score <= 30:
        return "Chaotic"
    elif total_score <= 50:
        return "Reactive"
    elif total_score <= 70:
        return "Structured"
    elif total_score <= 85:
        return "Optimised"
    else:
        return "Strategic"


def compute_gap_description(
    questionnaire_score: int,
    observed_score: int
) -> str:
    """
    Generate deterministic gap description between declared and observed scores.
    
    Logic:
        diff = questionnaire_score - observed_score
        if abs(diff) <= 3 → "Minimal"
        if 4 <= abs(diff) <= 10 → "Moderate"
        if abs(diff) > 10 → "High"
        
        Add explanatory phrase based on sign:
        - If positive: "declared capability exceeds observable execution"
        - If negative: "observable execution stronger than declared capability"
        - If zero/minimal: "declared and observed capabilities are well-aligned"
    
    Args:
        questionnaire_score: Score from questionnaire (0-50)
        observed_score: Score from observed metrics (0-50)
        
    Returns:
        Gap description string
    """
    diff = questionnaire_score - observed_score
    abs_diff = abs(diff)
    
    # Determine severity
    if abs_diff <= 3:
        severity = "Minimal"
        explanation = "declared and observed capabilities are well-aligned"
    elif abs_diff <= 10:
        severity = "Moderate"
        if diff > 0:
            explanation = "declared capability somewhat exceeds observable execution"
        else:
            explanation = "observable execution somewhat stronger than declared capability"
    else:
        severity = "High"
        if diff > 0:
            explanation = "declared capability significantly exceeds observable execution"
        else:
            explanation = "observable execution significantly stronger than declared capability"
    
    return f"{severity} — {explanation}"
