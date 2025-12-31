"""
Declared (Questionnaire) Evaluator.

Computes the questionnaire component score (0-50 points) from user answers.
Uses deterministic scoring with round_half_up for all calculations.
"""

from dataclasses import dataclass
from typing import Dict, List
from models.enums import (
    TECHNICAL_QUESTIONS,
    CONTENT_QUESTIONS,
    MEASUREMENT_QUESTIONS,
    DECLARED_WEIGHTS,
)
from models.schemas import QuestionnaireAnswers
from utils.rounding import compute_dimension_score


@dataclass
class DeclaredScoreResult:
    """
    Result of declared (questionnaire) evaluation.
    
    Attributes:
        technical: Technical SEO dimension score (0-20)
        content_keywords: Content & Keywords dimension score (0-20)
        measurement: Measurement & Analytics dimension score (0-10)
        total: Total questionnaire score (0-50)
    """
    technical: int
    content_keywords: int
    measurement: int
    total: int


class DeclaredEvaluator:
    """
    Evaluates questionnaire answers to produce declared capability scores.
    
    Scoring Model (deterministic):
    - Technical SEO (T1-T4): 20 points
    - Content & Keywords (C1-C4): 20 points
    - Measurement & Analytics (M1-M2): 10 points
    
    Formula per dimension:
        S_dim = sum of answers for dimension questions
        DimensionRawPercent = S_dim / (5 × N_questions_in_dim)
        DimensionScore = round_half_up(DimensionRawPercent × DimensionWeight)
    
    Total = sum(DimensionScore) → integer 0-50
    """
    
    def __init__(self):
        self.technical_weight = DECLARED_WEIGHTS["technical"]  # 20
        self.content_weight = DECLARED_WEIGHTS["content_keywords"]  # 20
        self.measurement_weight = DECLARED_WEIGHTS["measurement"]  # 10
    
    def evaluate(self, answers: QuestionnaireAnswers) -> DeclaredScoreResult:
        """
        Evaluate questionnaire answers.
        
        Args:
            answers: QuestionnaireAnswers with T1-T4, C1-C4, M1-M2
            
        Returns:
            DeclaredScoreResult with dimension scores and total
        """
        # Extract answer values for each dimension
        technical_answers = self._get_dimension_answers(answers, TECHNICAL_QUESTIONS)
        content_answers = self._get_dimension_answers(answers, CONTENT_QUESTIONS)
        measurement_answers = self._get_dimension_answers(answers, MEASUREMENT_QUESTIONS)
        
        # Compute dimension scores using deterministic rounding
        technical_score = compute_dimension_score(
            technical_answers, 
            self.technical_weight
        )
        content_score = compute_dimension_score(
            content_answers,
            self.content_weight
        )
        measurement_score = compute_dimension_score(
            measurement_answers,
            self.measurement_weight
        )
        
        # Total is sum of dimensions
        total = technical_score + content_score + measurement_score
        
        return DeclaredScoreResult(
            technical=technical_score,
            content_keywords=content_score,
            measurement=measurement_score,
            total=total,
        )
    
    def _get_dimension_answers(
        self,
        answers: QuestionnaireAnswers,
        question_ids: List[str]
    ) -> List[int]:
        """
        Extract answer values for a set of questions.
        
        Args:
            answers: QuestionnaireAnswers object
            question_ids: List of question IDs (e.g., ["T1", "T2", "T3", "T4"])
            
        Returns:
            List of answer values
        """
        return [getattr(answers, qid) for qid in question_ids]


# Example scoring walkthrough (for documentation):
#
# Given answers: T1=4, T2=3, T3=5, T4=3, C1=4, C2=3, C3=2, C4=3, M1=2, M2=3
#
# Technical (T1-T4):
#   sum = 4 + 3 + 5 + 3 = 15
#   max = 5 × 4 = 20
#   raw_percent = 15/20 = 0.75
#   score = round_half_up(0.75 × 20) = round_half_up(15.0) = 15
#
# Content (C1-C4):
#   sum = 4 + 3 + 2 + 3 = 12
#   max = 5 × 4 = 20
#   raw_percent = 12/20 = 0.60
#   score = round_half_up(0.60 × 20) = round_half_up(12.0) = 12
#
# Measurement (M1-M2):
#   sum = 2 + 3 = 5
#   max = 5 × 2 = 10
#   raw_percent = 5/10 = 0.50
#   score = round_half_up(0.50 × 10) = round_half_up(5.0) = 5
#
# Total: 15 + 12 + 5 = 32
