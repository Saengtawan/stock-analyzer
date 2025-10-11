"""
Transparent Score Calculation System
Provides clear, auditable scoring with configurable weights
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ScoreComponent:
    """Individual score component"""
    name: str
    score: float  # 0-10
    weight: float  # 0-1
    max_score: float = 10.0

    @property
    def weighted_score(self) -> float:
        """Calculate weighted contribution"""
        return (self.score / self.max_score) * self.weight * 10.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'score': round(self.score, 2),
            'weight': round(self.weight, 2),
            'weighted_score': round(self.weighted_score, 2),
            'percentage': f"{round((self.score / self.max_score) * 100)}%"
        }


class TransparentScoreCalculator:
    """Calculate overall scores with full transparency"""

    # Default weights for analysis components
    DEFAULT_WEIGHTS = {
        'fundamental': 0.40,
        'technical': 0.40,
        'risk': 0.20
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize score calculator

        Args:
            weights: Custom weights (must sum to 1.0)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

        # Validate
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

    def calculate_overall_score(
        self,
        fundamental_score: float,
        technical_score: float,
        risk_score: float
    ) -> Dict[str, Any]:
        """
        Calculate overall score with transparency

        Args:
            fundamental_score: Fundamental analysis score (0-10)
            technical_score: Technical analysis score (0-10)
            risk_score: Risk score (0-10, higher = less risky)

        Returns:
            Dictionary with detailed breakdown
        """
        components = [
            ScoreComponent('fundamental', fundamental_score, self.weights['fundamental']),
            ScoreComponent('technical', technical_score, self.weights['technical']),
            ScoreComponent('risk', risk_score, self.weights['risk'])
        ]

        # Calculate overall score
        overall = sum(c.weighted_score for c in components)

        return {
            'overall_score': round(overall, 1),
            'components': [c.to_dict() for c in components],
            'weights': self.weights,
            'formula': 'weighted_average',
            'calculation': f"({fundamental_score}*{self.weights['fundamental']}) + "
                          f"({technical_score}*{self.weights['technical']}) + "
                          f"({risk_score}*{self.weights['risk']})",
            'interpretation': self._get_interpretation(overall)
        }

    @staticmethod
    def _get_interpretation(score: float) -> str:
        """Get score interpretation"""
        if score >= 8.0:
            return "Excellent - Strong buy opportunity"
        elif score >= 6.5:
            return "Good - Consider buying"
        elif score >= 5.0:
            return "Fair - Hold or cautious buy"
        elif score >= 3.5:
            return "Weak - Consider selling"
        else:
            return "Poor - Avoid or sell"
