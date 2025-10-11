"""
AI Confidence Score Calculation
Provides transparent and reliable confidence scoring for AI-generated analysis
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class ConfidenceLevel(Enum):
    """Confidence level categories"""
    VERY_HIGH = "very_high"  # 90-100%
    HIGH = "high"             # 75-89%
    MEDIUM = "medium"         # 50-74%
    LOW = "low"               # 25-49%
    VERY_LOW = "very_low"     # 0-24%


@dataclass
class ConfidenceBreakdown:
    """Detailed breakdown of confidence score"""
    overall: float  # 0-1
    data_quality: float  # 0-1
    model_uncertainty: float  # 0-1
    market_volatility_factor: float  # 0-1
    data_completeness: float  # 0-1
    historical_accuracy: float  # 0-1 (optional)

    def to_dict(self) -> Dict[str, Any]:
        level = self._get_confidence_level()
        return {
            'overall_score': round(self.overall, 2),
            'overall_percentage': f"{round(self.overall * 100)}%",
            'confidence_level': level.value,
            'breakdown': {
                'data_quality': {
                    'score': round(self.data_quality, 2),
                    'weight': 0.35,
                    'description': 'Quality and reliability of source data'
                },
                'model_uncertainty': {
                    'score': round(self.model_uncertainty, 2),
                    'weight': 0.25,
                    'description': 'AI model prediction certainty'
                },
                'market_volatility': {
                    'score': round(self.market_volatility_factor, 2),
                    'weight': 0.20,
                    'description': 'Impact of market volatility on reliability'
                },
                'data_completeness': {
                    'score': round(self.data_completeness, 2),
                    'weight': 0.15,
                    'description': 'Completeness of available data'
                },
                'historical_accuracy': {
                    'score': round(self.historical_accuracy, 2) if self.historical_accuracy else None,
                    'weight': 0.05,
                    'description': 'Past performance of similar predictions'
                }
            },
            'interpretation': self._get_interpretation()
        }

    def _get_confidence_level(self) -> ConfidenceLevel:
        """Determine confidence level from score"""
        if self.overall >= 0.90:
            return ConfidenceLevel.VERY_HIGH
        elif self.overall >= 0.75:
            return ConfidenceLevel.HIGH
        elif self.overall >= 0.50:
            return ConfidenceLevel.MEDIUM
        elif self.overall >= 0.25:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def _get_interpretation(self) -> str:
        """Get human-readable interpretation"""
        level = self._get_confidence_level()

        interpretations = {
            ConfidenceLevel.VERY_HIGH: "Very high confidence - Analysis based on high-quality, complete data with low uncertainty",
            ConfidenceLevel.HIGH: "High confidence - Generally reliable analysis with good data quality",
            ConfidenceLevel.MEDIUM: "Medium confidence - Reasonable analysis but some data gaps or uncertainty present",
            ConfidenceLevel.LOW: "Low confidence - Significant data limitations or high uncertainty",
            ConfidenceLevel.VERY_LOW: "Very low confidence - Substantial data gaps or very high uncertainty"
        }

        return interpretations.get(level, "Unknown confidence level")


class AIConfidenceCalculator:
    """Calculates AI confidence scores with transparency"""

    # Default weights for confidence factors
    DEFAULT_WEIGHTS = {
        'data_quality': 0.35,
        'model_uncertainty': 0.25,
        'market_volatility': 0.20,
        'data_completeness': 0.15,
        'historical_accuracy': 0.05
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize confidence calculator

        Args:
            weights: Custom weights for factors (must sum to 1.0)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS

        # Validate weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

    def calculate_confidence(
        self,
        data_quality_score: float,
        model_predictions: Dict[str, Any],
        market_data: Dict[str, Any],
        data_completeness: float,
        historical_accuracy: Optional[float] = None
    ) -> ConfidenceBreakdown:
        """
        Calculate comprehensive confidence score

        Args:
            data_quality_score: Overall data quality (0-1)
            model_predictions: Model predictions with uncertainty
            market_data: Market conditions and volatility
            data_completeness: How complete is the data (0-1)
            historical_accuracy: Historical accuracy of similar predictions (0-1)

        Returns:
            ConfidenceBreakdown with detailed scores
        """
        # 1. Data Quality Component (already calculated)
        data_quality = data_quality_score

        # 2. Model Uncertainty Component
        model_uncertainty = self._calculate_model_uncertainty(model_predictions)

        # 3. Market Volatility Factor
        market_volatility_factor = self._calculate_market_volatility_factor(market_data)

        # 4. Data Completeness (already provided)
        completeness = data_completeness

        # 5. Historical Accuracy (optional)
        hist_accuracy = historical_accuracy if historical_accuracy is not None else 0.75

        # Calculate weighted overall score
        overall = (
            data_quality * self.weights['data_quality'] +
            model_uncertainty * self.weights['model_uncertainty'] +
            market_volatility_factor * self.weights['market_volatility'] +
            completeness * self.weights['data_completeness'] +
            hist_accuracy * self.weights['historical_accuracy']
        )

        return ConfidenceBreakdown(
            overall=overall,
            data_quality=data_quality,
            model_uncertainty=model_uncertainty,
            market_volatility_factor=market_volatility_factor,
            data_completeness=completeness,
            historical_accuracy=hist_accuracy
        )

    def _calculate_model_uncertainty(self, model_predictions: Dict[str, Any]) -> float:
        """
        Calculate model uncertainty score

        Args:
            model_predictions: Model output with uncertainty metrics

        Returns:
            Score from 0 (very uncertain) to 1 (very certain)
        """
        # If model provides explicit confidence
        if 'confidence' in model_predictions:
            return float(model_predictions['confidence'])

        # If model provides probability distribution
        if 'probabilities' in model_predictions:
            probs = model_predictions['probabilities']
            max_prob = max(probs.values()) if isinstance(probs, dict) else max(probs)
            return float(max_prob)

        # If prediction has variance/std
        if 'variance' in model_predictions:
            variance = float(model_predictions['variance'])
            # Convert variance to confidence (lower variance = higher confidence)
            return max(0.0, 1.0 - min(variance, 1.0))

        # Default: medium confidence
        return 0.70

    def _calculate_market_volatility_factor(self, market_data: Dict[str, Any]) -> float:
        """
        Calculate impact of market volatility on confidence

        Args:
            market_data: Market conditions including volatility

        Returns:
            Score from 0 (very volatile/uncertain) to 1 (stable/certain)
        """
        # Extract volatility measure
        volatility = market_data.get('volatility', 0.30)  # Default 30%

        # Also consider market regime
        regime = market_data.get('market_regime', 'normal')

        # Base score from volatility (inverse relationship)
        # Low volatility (<20%) = high confidence
        # High volatility (>50%) = low confidence
        if volatility < 0.20:
            vol_score = 0.90
        elif volatility < 0.30:
            vol_score = 0.75
        elif volatility < 0.40:
            vol_score = 0.60
        elif volatility < 0.50:
            vol_score = 0.45
        else:
            vol_score = 0.30

        # Adjust for market regime
        regime_adjustments = {
            'bull': 0.05,  # Slightly more confident in bull markets
            'bear': -0.10,  # Less confident in bear markets
            'sideways': 0.0,
            'volatile': -0.15,  # Much less confident in volatile markets
            'normal': 0.0
        }

        adjustment = regime_adjustments.get(regime, 0.0)
        final_score = max(0.0, min(1.0, vol_score + adjustment))

        return final_score

    def calculate_recommendation_confidence(
        self,
        fundamental_score: float,
        technical_score: float,
        data_quality: float,
        score_agreement: float
    ) -> ConfidenceBreakdown:
        """
        Calculate confidence for investment recommendation

        Args:
            fundamental_score: Fundamental analysis score (0-10)
            technical_score: Technical analysis score (0-10)
            data_quality: Overall data quality (0-1)
            score_agreement: How much scores agree (0-1)

        Returns:
            ConfidenceBreakdown
        """
        # Normalize scores to 0-1
        fund_normalized = fundamental_score / 10.0
        tech_normalized = technical_score / 10.0

        # Model uncertainty based on score agreement
        # High agreement = low uncertainty
        model_uncertainty = score_agreement

        # Market volatility - estimate from scores
        # Extreme scores suggest volatile conditions
        avg_score = (fund_normalized + tech_normalized) / 2
        if avg_score < 0.3 or avg_score > 0.8:
            market_factor = 0.60  # Extreme scores = less certain
        else:
            market_factor = 0.80  # Moderate scores = more certain

        # Data completeness based on data quality
        completeness = data_quality

        return self.calculate_confidence(
            data_quality_score=data_quality,
            model_predictions={'confidence': model_uncertainty},
            market_data={'volatility': 0.30},
            data_completeness=completeness,
            historical_accuracy=0.75
        )

    @staticmethod
    def create_from_analysis(analysis_result: Dict[str, Any]) -> ConfidenceBreakdown:
        """
        Create confidence breakdown from analysis result

        Args:
            analysis_result: Complete analysis result

        Returns:
            ConfidenceBreakdown
        """
        calculator = AIConfidenceCalculator()

        # Extract necessary data
        data_quality = analysis_result.get('data_quality', {}).get('overall_score', 0.70)

        fundamental = analysis_result.get('fundamental_analysis', {})
        technical = analysis_result.get('technical_analysis', {})

        fund_score = fundamental.get('overall_score', 5.0)
        tech_score = technical.get('technical_score', {}).get('total_score', 5.0)

        # Calculate score agreement
        fund_norm = fund_score / 10.0
        tech_norm = tech_score / 10.0
        score_diff = abs(fund_norm - tech_norm)
        score_agreement = 1.0 - score_diff

        return calculator.calculate_recommendation_confidence(
            fundamental_score=fund_score,
            technical_score=tech_score,
            data_quality=data_quality,
            score_agreement=score_agreement
        )
