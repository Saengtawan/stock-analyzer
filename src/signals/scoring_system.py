"""
Advanced Scoring System for Stock Analysis
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from loguru import logger


class AdvancedScoringSystem:
    """Advanced scoring system with multiple methodologies"""

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize scoring system

        Args:
            config: Configuration dictionary with scoring parameters
        """
        self.config = config or {}
        self.weights = self._initialize_weights()
        self.thresholds = self._initialize_thresholds()

    def calculate_comprehensive_score(self,
                                    fundamental_data: Dict[str, Any],
                                    technical_data: Dict[str, Any],
                                    market_data: Dict[str, Any] = None,
                                    time_horizon: str = 'medium') -> Dict[str, Any]:
        """
        Calculate comprehensive investment score

        Args:
            fundamental_data: Fundamental analysis results
            technical_data: Technical analysis results
            market_data: Market/macro data (optional)
            time_horizon: Investment time horizon

        Returns:
            Comprehensive scoring results
        """
        try:
            # Calculate individual category scores
            valuation_score = self._score_valuation(fundamental_data)
            quality_score = self._score_quality(fundamental_data)
            growth_score = self._score_growth(fundamental_data)
            momentum_score = self._score_momentum(technical_data)
            technical_score = self._score_technical_setup(technical_data)

            # Market context score (if available)
            market_score = self._score_market_context(market_data) if market_data else 5.0

            # Time horizon adjustments
            adjusted_weights = self._adjust_weights_for_horizon(time_horizon)

            # Calculate weighted score
            total_score = (
                valuation_score * adjusted_weights['valuation'] +
                quality_score * adjusted_weights['quality'] +
                growth_score * adjusted_weights['growth'] +
                momentum_score * adjusted_weights['momentum'] +
                technical_score * adjusted_weights['technical'] +
                market_score * adjusted_weights['market']
            )

            # Risk adjustments
            risk_adjustment = self._calculate_risk_adjustment(fundamental_data, technical_data)
            adjusted_score = total_score * risk_adjustment

            # Generate detailed breakdown
            score_breakdown = {
                'total_score': min(adjusted_score, 10.0),
                'raw_total_score': total_score,
                'risk_adjustment': risk_adjustment,
                'time_horizon': time_horizon,
                'category_scores': {
                    'valuation': valuation_score,
                    'quality': quality_score,
                    'growth': growth_score,
                    'momentum': momentum_score,
                    'technical': technical_score,
                    'market_context': market_score
                },
                'weighted_contributions': {
                    'valuation': valuation_score * adjusted_weights['valuation'],
                    'quality': quality_score * adjusted_weights['quality'],
                    'growth': growth_score * adjusted_weights['growth'],
                    'momentum': momentum_score * adjusted_weights['momentum'],
                    'technical': technical_score * adjusted_weights['technical'],
                    'market_context': market_score * adjusted_weights['market']
                },
                'weights_used': adjusted_weights,
                'rating': self._score_to_rating(adjusted_score),
                'percentile_rank': self._calculate_percentile_rank(adjusted_score)
            }

            return score_breakdown

        except Exception as e:
            logger.error(f"Comprehensive scoring failed: {e}")
            return {'total_score': 5.0, 'error': str(e)}

    def _score_valuation(self, fundamental_data: Dict[str, Any]) -> float:
        """Score valuation attractiveness (0-10)"""
        score = 0
        max_score = 10

        # P/E Ratio (25% of valuation score)
        pe_ratio = fundamental_data.get('financial_ratios', {}).get('pe_ratio')
        if pe_ratio:
            if pe_ratio < 10:
                score += 2.5
            elif pe_ratio < 15:
                score += 2.0
            elif pe_ratio < 20:
                score += 1.5
            elif pe_ratio < 25:
                score += 1.0
            elif pe_ratio > 40:
                score += 0.0
            else:
                score += 0.5

        # PEG Ratio (25% of valuation score)
        peg_ratio = fundamental_data.get('financial_ratios', {}).get('peg_ratio')
        if peg_ratio:
            if peg_ratio < 0.8:
                score += 2.5
            elif peg_ratio < 1.0:
                score += 2.0
            elif peg_ratio < 1.5:
                score += 1.5
            elif peg_ratio < 2.0:
                score += 1.0
            else:
                score += 0.0

        # P/B Ratio (25% of valuation score)
        pb_ratio = fundamental_data.get('financial_ratios', {}).get('pb_ratio')
        if pb_ratio:
            if pb_ratio < 1.0:
                score += 2.5
            elif pb_ratio < 2.0:
                score += 2.0
            elif pb_ratio < 3.0:
                score += 1.5
            elif pb_ratio < 4.0:
                score += 1.0
            else:
                score += 0.0

        # DCF Valuation (25% of valuation score)
        dcf_results = fundamental_data.get('dcf_valuation', {})
        intrinsic_value = dcf_results.get('intrinsic_value_per_share')
        current_price = fundamental_data.get('current_price')

        if intrinsic_value and current_price and current_price > 0:
            discount_premium = (intrinsic_value - current_price) / current_price
            if discount_premium > 0.3:  # 30%+ undervalued
                score += 2.5
            elif discount_premium > 0.2:  # 20%+ undervalued
                score += 2.0
            elif discount_premium > 0.1:  # 10%+ undervalued
                score += 1.5
            elif discount_premium > 0:  # Undervalued
                score += 1.0
            elif discount_premium > -0.1:  # Fair value
                score += 0.5
            else:  # Overvalued
                score += 0.0

        return min(score, max_score)

    def _score_quality(self, fundamental_data: Dict[str, Any]) -> float:
        """Score business quality (0-10)"""
        score = 0
        max_score = 10

        ratios = fundamental_data.get('financial_ratios', {})

        # Profitability Quality (40% of quality score)
        roe = ratios.get('roe', 0)
        if roe > 0.25:
            score += 2.0
        elif roe > 0.20:
            score += 1.6
        elif roe > 0.15:
            score += 1.2
        elif roe > 0.10:
            score += 0.8
        elif roe > 0.05:
            score += 0.4

        roa = ratios.get('roa', 0)
        if roa > 0.10:
            score += 2.0
        elif roa > 0.08:
            score += 1.6
        elif roa > 0.05:
            score += 1.2
        elif roa > 0.03:
            score += 0.8
        elif roa > 0.01:
            score += 0.4

        # Financial Stability (40% of quality score)
        debt_to_equity = ratios.get('debt_to_equity', float('inf'))
        if debt_to_equity < 0.2:
            score += 2.0
        elif debt_to_equity < 0.5:
            score += 1.6
        elif debt_to_equity < 1.0:
            score += 1.2
        elif debt_to_equity < 2.0:
            score += 0.8
        else:
            score += 0.0

        current_ratio = ratios.get('current_ratio', 0)
        if current_ratio > 2.5:
            score += 2.0
        elif current_ratio > 2.0:
            score += 1.6
        elif current_ratio > 1.5:
            score += 1.2
        elif current_ratio > 1.0:
            score += 0.8
        else:
            score += 0.0

        # Operational Efficiency (20% of quality score)
        profit_margin = ratios.get('profit_margin', 0)
        if profit_margin > 0.20:
            score += 2.0
        elif profit_margin > 0.15:
            score += 1.6
        elif profit_margin > 0.10:
            score += 1.2
        elif profit_margin > 0.05:
            score += 0.8
        elif profit_margin > 0:
            score += 0.4

        return min(score, max_score)

    def _score_growth(self, fundamental_data: Dict[str, Any]) -> float:
        """Score growth prospects (0-10)"""
        score = 0
        max_score = 10

        ratios = fundamental_data.get('financial_ratios', {})

        # Revenue Growth (50% of growth score)
        revenue_growth = ratios.get('revenue_growth', 0)
        if revenue_growth > 0.25:
            score += 5.0
        elif revenue_growth > 0.20:
            score += 4.0
        elif revenue_growth > 0.15:
            score += 3.0
        elif revenue_growth > 0.10:
            score += 2.0
        elif revenue_growth > 0.05:
            score += 1.0
        elif revenue_growth > 0:
            score += 0.5

        # Earnings Growth (50% of growth score)
        earnings_growth = ratios.get('earnings_growth', 0)
        if earnings_growth > 0.30:
            score += 5.0
        elif earnings_growth > 0.25:
            score += 4.0
        elif earnings_growth > 0.20:
            score += 3.0
        elif earnings_growth > 0.15:
            score += 2.0
        elif earnings_growth > 0.10:
            score += 1.0
        elif earnings_growth > 0:
            score += 0.5

        return min(score, max_score)

    def _score_momentum(self, technical_data: Dict[str, Any]) -> float:
        """Score price momentum (0-10)"""
        score = 0
        max_score = 10

        indicators = technical_data.get('indicators', {})

        # RSI Momentum (25% of momentum score)
        rsi = indicators.get('rsi')
        if rsi:
            if 40 <= rsi <= 60:
                score += 2.5  # Neutral zone
            elif 30 <= rsi < 40 or 60 < rsi <= 70:
                score += 2.0  # Moderate zone
            elif rsi < 30:
                score += 1.0  # Oversold (contrarian signal)
            elif rsi > 70:
                score += 1.0  # Overbought (contrarian signal)

        # MACD Momentum (25% of momentum score)
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_histogram = indicators.get('macd_histogram')

        if all(x is not None for x in [macd_line, macd_signal, macd_histogram]):
            if macd_line > macd_signal and macd_histogram > 0:
                score += 2.5  # Strong bullish
            elif macd_line > macd_signal:
                score += 2.0  # Bullish
            elif macd_line < macd_signal and macd_histogram < 0:
                score += 0.0  # Strong bearish
            elif macd_line < macd_signal:
                score += 0.5  # Bearish
            else:
                score += 1.25  # Neutral

        # Price vs Moving Averages (25% of momentum score)
        current_price = indicators.get('current_price', 0)
        sma_20 = indicators.get('sma_20')
        sma_50 = indicators.get('sma_50')

        if current_price and sma_20 and sma_50:
            if current_price > sma_20 > sma_50:
                score += 2.5  # Strong uptrend
            elif current_price > sma_20:
                score += 2.0  # Moderate uptrend
            elif current_price < sma_20 < sma_50:
                score += 0.0  # Strong downtrend
            elif current_price < sma_20:
                score += 0.5  # Moderate downtrend
            else:
                score += 1.25  # Mixed signals

        # Volume Confirmation (25% of momentum score)
        volume_signal = technical_data.get('signals', {}).get('volume_signal', {})
        volume_signal_type = volume_signal.get('signal', 'NEUTRAL')
        volume_strength = volume_signal.get('strength', 'Weak')

        if volume_signal_type == 'BULLISH':
            if volume_strength == 'Strong':
                score += 2.5
            elif volume_strength == 'Moderate':
                score += 2.0
            else:
                score += 1.5
        elif volume_signal_type == 'BEARISH':
            if volume_strength == 'Strong':
                score += 0.0
            elif volume_strength == 'Moderate':
                score += 0.5
            else:
                score += 1.0
        else:
            score += 1.25

        return min(score, max_score)

    def _score_technical_setup(self, technical_data: Dict[str, Any]) -> float:
        """Score technical setup and chart patterns (0-10)"""
        score = 0
        max_score = 10

        indicators = technical_data.get('indicators', {})
        signals = technical_data.get('signals', {})

        # Support/Resistance Setup (40% of technical score)
        sr_signal = signals.get('sr_signal', {})
        sr_signal_type = sr_signal.get('signal', 'NEUTRAL')
        sr_strength = sr_signal.get('strength', 'Weak')

        if sr_signal_type == 'BUY':
            if sr_strength == 'Strong':
                score += 4.0
            elif sr_strength == 'Moderate':
                score += 3.0
            else:
                score += 2.0
        elif sr_signal_type == 'SELL':
            if sr_strength == 'Strong':
                score += 0.0
            elif sr_strength == 'Moderate':
                score += 1.0
            else:
                score += 2.0
        else:
            score += 2.0

        # Bollinger Bands Setup (30% of technical score)
        bb_signal = signals.get('bb_signal', {})
        bb_signal_type = bb_signal.get('signal', 'NEUTRAL')
        bb_strength = bb_signal.get('strength', 'Weak')

        if bb_signal_type == 'BUY':
            if bb_strength == 'Strong':
                score += 3.0
            elif bb_strength == 'Moderate':
                score += 2.5
            else:
                score += 2.0
        elif bb_signal_type == 'SELL':
            if bb_strength == 'Strong':
                score += 0.0
            elif bb_strength == 'Moderate':
                score += 1.0
            else:
                score += 1.5
        else:
            score += 1.5

        # ATR and Volatility (20% of technical score)
        atr = indicators.get('atr')
        current_price = indicators.get('current_price')

        if atr and current_price:
            volatility_pct = (atr / current_price) * 100
            if 1.0 <= volatility_pct <= 3.0:
                score += 2.0  # Optimal volatility
            elif 0.5 <= volatility_pct < 1.0 or 3.0 < volatility_pct <= 5.0:
                score += 1.5  # Acceptable volatility
            else:
                score += 1.0  # Too low or too high volatility

        # Trend Confirmation (10% of technical score)
        trend_info = technical_data.get('trend_analysis', {})
        trend_direction = trend_info.get('trend_direction', 'Sideways')

        if trend_direction in ['Strong Uptrend', 'Uptrend']:
            score += 1.0
        elif trend_direction in ['Strong Downtrend', 'Downtrend']:
            score += 0.0
        else:
            score += 0.5

        return min(score, max_score)

    def _score_market_context(self, market_data: Dict[str, Any]) -> float:
        """Score market context and macro factors (0-10)"""
        if not market_data:
            return 5.0  # Neutral if no market data

        score = 5.0  # Start neutral
        # This would include market regime, VIX levels, sector performance, etc.
        # Simplified implementation for now

        market_trend = market_data.get('market_trend', 'Neutral')
        if market_trend == 'Bull Market':
            score = 7.0
        elif market_trend == 'Bear Market':
            score = 3.0

        return score

    def _calculate_risk_adjustment(self,
                                 fundamental_data: Dict[str, Any],
                                 technical_data: Dict[str, Any]) -> float:
        """Calculate risk adjustment factor (0.5 - 1.2)"""
        adjustment = 1.0

        # Financial risk adjustment
        fund_risk = fundamental_data.get('risk_assessment', {})
        debt_to_equity = fundamental_data.get('financial_ratios', {}).get('debt_to_equity', 0)

        if debt_to_equity > 3.0:
            adjustment *= 0.8
        elif debt_to_equity > 2.0:
            adjustment *= 0.9

        # Technical risk adjustment
        tech_risk = technical_data.get('risk_assessment', {})
        volatility_risk = tech_risk.get('volatility_risk', 'Moderate')

        if volatility_risk == 'Very High':
            adjustment *= 0.7
        elif volatility_risk == 'High':
            adjustment *= 0.85

        # Confluence bonus
        # If both analyses agree strongly, give a small bonus
        fund_score = fundamental_data.get('fundamental_score', {}).get('total_score', 5.0)
        tech_score = technical_data.get('technical_score', {}).get('total_score', 5.0)

        if abs(fund_score - tech_score) < 1.0 and min(fund_score, tech_score) > 7.0:
            adjustment *= 1.1

        return max(0.5, min(adjustment, 1.2))

    def _adjust_weights_for_horizon(self, time_horizon: str) -> Dict[str, float]:
        """Adjust scoring weights based on investment time horizon"""
        base_weights = self.weights.copy()

        if time_horizon == 'short':  # 1-14 days
            return {
                'valuation': 0.1,
                'quality': 0.1,
                'growth': 0.1,
                'momentum': 0.35,
                'technical': 0.3,
                'market': 0.05
            }
        elif time_horizon == 'medium':  # 1-6 months
            return {
                'valuation': 0.2,
                'quality': 0.2,
                'growth': 0.2,
                'momentum': 0.2,
                'technical': 0.15,
                'market': 0.05
            }
        else:  # long term 6+ months
            return {
                'valuation': 0.3,
                'quality': 0.3,
                'growth': 0.25,
                'momentum': 0.05,
                'technical': 0.05,
                'market': 0.05
            }

    def _initialize_weights(self) -> Dict[str, float]:
        """Initialize default scoring weights"""
        return {
            'valuation': 0.25,
            'quality': 0.25,
            'growth': 0.20,
            'momentum': 0.15,
            'technical': 0.10,
            'market': 0.05
        }

    def _initialize_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Initialize scoring thresholds"""
        return {
            'excellent': {'min': 8.5, 'max': 10.0},
            'good': {'min': 7.0, 'max': 8.5},
            'fair': {'min': 5.0, 'max': 7.0},
            'poor': {'min': 3.0, 'max': 5.0},
            'very_poor': {'min': 0.0, 'max': 3.0}
        }

    def _score_to_rating(self, score: float) -> str:
        """Convert numerical score to rating"""
        if score >= 8.5:
            return "Excellent"
        elif score >= 7.0:
            return "Good"
        elif score >= 5.0:
            return "Fair"
        elif score >= 3.0:
            return "Poor"
        else:
            return "Very Poor"

    def _calculate_percentile_rank(self, score: float) -> float:
        """Calculate percentile rank (simplified)"""
        # This would normally compare against a universe of stocks
        # For now, use a simple mapping
        return min(score * 10, 100)

    def generate_score_explanation(self, score_breakdown: Dict[str, Any]) -> Dict[str, Any]:
        """Generate detailed explanation of the score"""
        total_score = score_breakdown.get('total_score', 0)
        category_scores = score_breakdown.get('category_scores', {})

        explanations = []

        # Overall assessment
        rating = score_breakdown.get('rating', 'Fair')
        explanations.append(f"Overall rating: {rating} ({total_score:.1f}/10)")

        # Category explanations
        for category, score in category_scores.items():
            if score >= 8.0:
                strength = "Strong"
            elif score >= 6.0:
                strength = "Good"
            elif score >= 4.0:
                strength = "Moderate"
            else:
                strength = "Weak"

            explanations.append(f"{category.title()}: {strength} ({score:.1f}/10)")

        # Key drivers
        top_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        best_category = top_categories[0][0] if top_categories else None
        worst_category = top_categories[-1][0] if top_categories else None

        key_drivers = []
        if best_category:
            key_drivers.append(f"Strongest factor: {best_category}")
        if worst_category and worst_category != best_category:
            key_drivers.append(f"Weakest factor: {worst_category}")

        return {
            'explanations': explanations,
            'key_drivers': key_drivers,
            'interpretation': self._interpret_score(total_score),
            'improvement_areas': self._identify_improvement_areas(category_scores)
        }

    def _interpret_score(self, score: float) -> str:
        """Interpret the overall score"""
        if score >= 8.5:
            return "Exceptional investment opportunity with strong fundamentals and technical setup"
        elif score >= 7.0:
            return "Solid investment candidate with good potential"
        elif score >= 5.0:
            return "Moderate investment potential with mixed signals"
        elif score >= 3.0:
            return "Below average investment with significant concerns"
        else:
            return "Poor investment candidate with major red flags"

    def _identify_improvement_areas(self, category_scores: Dict[str, float]) -> List[str]:
        """Identify areas needing improvement"""
        improvement_areas = []

        for category, score in category_scores.items():
            if score < 4.0:
                improvement_areas.append(f"Address {category} concerns")

        return improvement_areas