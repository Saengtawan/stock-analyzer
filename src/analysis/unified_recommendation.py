"""
Unified Recommendation System
แก้ไขปัญหา conflicting recommendations โดยรวมทุกส่วนเข้าด้วยกัน
"""
from typing import Dict, Any, List, Optional
from loguru import logger
import numpy as np


class UnifiedRecommendationEngine:
    """
    Unified recommendation engine that combines all analysis components
    into a single, consistent recommendation
    """

    def __init__(self):
        self.recommendation_thresholds = {
            'STRONG_BUY': 8.0,
            'BUY': 6.5,
            'HOLD': 4.5,
            'SELL': 3.0
        }

    def generate_unified_recommendation(self,
                                       technical_score: float,
                                       fundamental_score: float,
                                       price_change_analysis: Dict[str, Any],
                                       insider_data: Dict[str, Any],
                                       risk_reward_ratio: float,
                                       current_price: float,
                                       target_price: float,
                                       stop_loss: float,
                                       time_horizon: str = 'short',
                                       analysis_results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a single unified recommendation from all analysis components

        Args:
            technical_score: Technical analysis score (0-10)
            fundamental_score: Fundamental analysis score (0-10)
            price_change_analysis: Price change analysis results
            insider_data: Insider trading data
            risk_reward_ratio: Calculated R:R ratio
            current_price: Current stock price
            target_price: Target price
            stop_loss: Stop loss price
            time_horizon: Investment horizon

        Returns:
            Unified recommendation with confidence and detailed reasoning
        """

        # Debug: Check parameter types
        logger.debug(f"generate_unified_recommendation params:")
        logger.debug(f"  current_price: {type(current_price)} = {current_price}")
        logger.debug(f"  target_price: {type(target_price)} = {target_price}")
        logger.debug(f"  stop_loss: {type(stop_loss)} = {stop_loss}")

        # 1. Calculate component weights based on time horizon
        weights = self._get_component_weights(time_horizon)

        # 2. Score each component (0-10 scale)
        technical_component = technical_score
        fundamental_component = fundamental_score
        price_action_component = self._score_price_action(price_change_analysis)
        insider_component = self._score_insider_activity(insider_data)
        risk_reward_component = self._score_risk_reward(risk_reward_ratio)

        # NEW: Momentum component
        if analysis_results:
            momentum_component = self._score_momentum(analysis_results)
        else:
            momentum_component = 5.0  # Neutral if not available

        # 3. Calculate weighted score
        weighted_score = (
            technical_component * weights['technical'] +
            fundamental_component * weights['fundamental'] +
            price_action_component * weights['price_action'] +
            insider_component * weights['insider'] +
            risk_reward_component * weights['risk_reward'] +
            momentum_component * weights['momentum']
        )

        # 4. Apply critical filters (veto conditions)
        veto_result = self._apply_veto_conditions(
            risk_reward_ratio,
            price_change_analysis,
            insider_data,
            weighted_score
        )

        if veto_result['veto']:
            # Override recommendation due to critical issue
            final_score = veto_result['adjusted_score']
            final_recommendation = veto_result['forced_recommendation']
            confidence = 'LOW'
            veto_reasons = veto_result['reasons']
        else:
            final_score = weighted_score
            final_recommendation = self._score_to_recommendation(weighted_score)
            confidence = self._calculate_confidence(
                weighted_score,
                [technical_component, fundamental_component, price_action_component,
                 insider_component, risk_reward_component]
            )
            veto_reasons = []

        # 5. Generate detailed reasoning
        reasoning = self._generate_detailed_reasoning(
            final_recommendation,
            {
                'technical': technical_component,
                'fundamental': fundamental_component,
                'price_action': price_action_component,
                'insider': insider_component,
                'risk_reward': risk_reward_component
            },
            weights,
            price_change_analysis,
            insider_data,
            risk_reward_ratio,
            veto_reasons
        )

        # 6. Calculate realistic R:R ratio
        realistic_rr = self._calculate_realistic_rr(current_price, target_price, stop_loss)

        # 7. Generate position sizing recommendation
        position_sizing = self._calculate_position_sizing(
            final_score,
            risk_reward_ratio,
            confidence
        )

        return {
            'recommendation': final_recommendation,
            'score': round(final_score, 1),
            'confidence': confidence,
            'confidence_percentage': self._confidence_to_percentage(confidence),

            'component_scores': {
                'technical': round(technical_component, 1),
                'fundamental': round(fundamental_component, 1),
                'price_action': round(price_action_component, 1),
                'insider': round(insider_component, 1),
                'risk_reward': round(risk_reward_component, 1),
                'momentum': round(momentum_component, 1)  # NEW
            },

            'weights_applied': weights,

            'risk_reward_analysis': {
                'ratio': realistic_rr,
                'risk_dollars': round(current_price - stop_loss, 2),
                'reward_dollars': round(target_price - current_price, 2),
                'risk_percent': round(((current_price - stop_loss) / current_price) * 100, 2),
                'reward_percent': round(((target_price - current_price) / current_price) * 100, 2),
                'is_favorable': realistic_rr >= 1.5
            },

            'position_sizing': position_sizing,

            'reasoning': reasoning,

            'veto_applied': bool(veto_reasons),
            'veto_reasons': veto_reasons,

            'analysis_timestamp': pd.Timestamp.now().isoformat()
        }

    def _get_component_weights(self, time_horizon: str) -> Dict[str, float]:
        """Get component weights based on time horizon"""
        weights = {
            'short': {
                'technical': 0.30,
                'fundamental': 0.05,
                'price_action': 0.30,
                'insider': 0.05,
                'risk_reward': 0.20,  # Increased importance for short-term
                'momentum': 0.10  # NEW: Momentum weight
            },
            'medium': {
                'technical': 0.25,
                'fundamental': 0.25,
                'price_action': 0.20,
                'insider': 0.05,
                'risk_reward': 0.18,
                'momentum': 0.07  # NEW: Momentum weight
            },
            'long': {
                'technical': 0.15,
                'fundamental': 0.45,
                'price_action': 0.10,
                'insider': 0.10,
                'risk_reward': 0.15,
                'momentum': 0.05  # NEW: Momentum weight
            }
        }

        return weights.get(time_horizon, weights['short'])

    def _score_price_action(self, price_change_analysis: Dict[str, Any]) -> float:
        """
        Score price action (0-10)

        Factors:
        - Price change direction and magnitude
        - Candle strength
        - Trend strength
        - Volume confirmation
        """
        if not price_change_analysis or 'error' in price_change_analysis:
            return 5.0

        score = 5.0  # Neutral base

        # Price change impact
        change_pct = price_change_analysis.get('change_percent', 0)
        if change_pct > 3:
            score += 2.0  # Strong up
        elif change_pct > 1:
            score += 1.0  # Moderate up
        elif change_pct < -3:
            score -= 2.0  # Strong down
        elif change_pct < -1:
            score -= 1.0  # Moderate down

        # Trend strength - handle if it's a dict or a number
        trend_strength_raw = price_change_analysis.get('trend_strength', 50)
        if isinstance(trend_strength_raw, dict):
            # If it's a dict, try to extract a numeric value
            trend_strength = float(trend_strength_raw.get('value', trend_strength_raw.get('score', 50)))
        else:
            trend_strength = float(trend_strength_raw if trend_strength_raw is not None else 50)

        trend_strength = trend_strength / 100 * 3  # 0-3 points
        score += trend_strength

        # Adjust for selling pressure
        selling_pressure = price_change_analysis.get('selling_pressure_pct', 50)
        if selling_pressure > 70:
            score -= 1.5
        elif selling_pressure > 60:
            score -= 0.5

        return max(0, min(10, score))

    def _score_insider_activity(self, insider_data: Dict[str, Any]) -> float:
        """
        Score insider activity (0-10)

        Uses REAL SEC EDGAR data:
        - Form 4 filing activity (insider transactions)
        - Activity trends (increasing/decreasing)
        - Activity spikes
        - Smart money signals (institutional 13F filings)
        """
        if not insider_data:
            return 5.0  # Neutral

        # Check if we have real SEC data
        has_real_data = insider_data.get('has_real_data', False)

        if not has_real_data:
            return 5.0  # Neutral if no real data

        # Use pre-calculated scores from SEC analyzer
        insider_score = insider_data.get('insider_score', 5.0)  # From SEC Form 4 analysis
        institutional_score = insider_data.get('institutional_score', 5.0)  # From SEC Form 13F analysis

        # Weighted average (60% insider, 40% institutional)
        combined_score = (insider_score * 0.6) + (institutional_score * 0.4)

        # Apply additional modifiers based on specific signals
        insider_trading = insider_data.get('insider_trading', {})
        institutional_ownership = insider_data.get('institutional_ownership', {})

        # Trend analysis modifier
        trend_analysis = insider_trading.get('trend_analysis', {})
        trend_direction = trend_analysis.get('trend_direction', 'neutral')
        activity_spike = trend_analysis.get('activity_spike', False)

        if trend_direction == 'increasing':
            combined_score += 0.5
        elif trend_direction == 'decreasing':
            combined_score -= 0.5

        if activity_spike:
            combined_score += 0.3  # Bonus for activity spike

        # Smart money signal modifier
        flow_analysis = institutional_ownership.get('flow_analysis', {})
        smart_signal = flow_analysis.get('smart_money_signal', 'neutral')

        if smart_signal == 'bullish':
            combined_score += 0.5
        elif smart_signal == 'bearish':
            combined_score -= 0.5

        return max(0, min(10, combined_score))

    def _score_momentum(self, analysis_results: Dict[str, Any]) -> float:
        """
        Score momentum indicators (0-10)

        Combines RSI, MACD, and EMA crossover signals
        """
        score = 5.0  # Neutral base

        technical_analysis = analysis_results.get('technical_analysis', {})
        indicators = technical_analysis.get('indicators', {})

        # 1. RSI scoring (0-3 points)
        rsi = indicators.get('rsi')
        if rsi is not None:
            if rsi <= 30:
                score += 3.0  # Oversold - strong buy signal
            elif rsi <= 40:
                score += 1.5  # Approaching oversold
            elif rsi >= 70:
                score -= 3.0  # Overbought - strong sell signal
            elif rsi >= 60:
                score -= 1.5  # Approaching overbought

        # 2. MACD scoring (0-3 points)
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_histogram = indicators.get('macd_histogram')

        if all(x is not None for x in [macd_line, macd_signal, macd_histogram]):
            if macd_line > macd_signal and macd_histogram > 0:
                if macd_line > 0:
                    score += 3.0  # Bullish crossover above zero
                else:
                    score += 2.0  # Bullish crossover below zero
            elif macd_line < macd_signal and macd_histogram < 0:
                if macd_line < 0:
                    score -= 3.0  # Bearish crossover below zero
                else:
                    score -= 2.0  # Bearish crossover above zero

        # 3. EMA crossover (0-4 points)
        current_price = indicators.get('current_price')
        ema_9 = indicators.get('ema_9')
        ema_21 = indicators.get('ema_21')
        ema_50 = indicators.get('ema_50')

        if all(x is not None for x in [current_price, ema_9, ema_21, ema_50]):
            if current_price > ema_9 > ema_21 > ema_50:
                score += 4.0  # Perfect bullish alignment
            elif current_price > ema_9 > ema_21:
                score += 2.0  # Strong bullish
            elif current_price < ema_9 < ema_21 < ema_50:
                score -= 4.0  # Perfect bearish alignment
            elif current_price < ema_9 < ema_21:
                score -= 2.0  # Strong bearish

        return max(0, min(10, score))

    def _score_risk_reward(self, rr_ratio: float) -> float:
        """
        Score risk/reward ratio (0-10)

        UPDATED THRESHOLDS:
        Excellent: R:R >= 3.0 → 10 points
        Good: R:R >= 2.0 → 8 points
        Fair: R:R >= 1.5 → 6 points (minimum acceptable)
        Marginal: R:R >= 1.0 → 3 points (risky)
        Poor: R:R < 1.0 → 0-1 points (avoid)
        """
        if rr_ratio >= 3.0:
            return 10.0
        elif rr_ratio >= 2.5:
            return 9.0
        elif rr_ratio >= 2.0:
            return 8.0
        elif rr_ratio >= 1.5:
            return 6.0  # Minimum acceptable
        elif rr_ratio >= 1.2:
            return 4.0  # Marginal
        elif rr_ratio >= 1.0:
            return 3.0  # Very risky
        elif rr_ratio >= 0.75:
            return 1.5
        elif rr_ratio >= 0.5:
            return 1.0
        else:
            return 0.5

    def _apply_veto_conditions(self,
                               risk_reward_ratio: float,
                               price_change_analysis: Dict[str, Any],
                               insider_data: Dict[str, Any],
                               current_score: float) -> Dict[str, Any]:
        """
        Apply veto conditions that can override the recommendation

        UPDATED VETO conditions:
        1. R:R ratio < 1.5 for BUY → Force HOLD (insufficient reward)
        2. R:R ratio < 1.0 → Force HOLD (risk too high)
        3. Price drop > 5% + strong selling → Force SELL
        4. Heavy insider selling → Downgrade to HOLD
        """
        veto = False
        reasons = []
        adjusted_score = current_score
        forced_recommendation = None

        # Veto 1: R:R ratio < 1.5 for BUY signals (NEW)
        if risk_reward_ratio < 1.5 and current_score >= 6.5:  # Would be BUY or STRONG BUY
            veto = True
            adjusted_score = 4.5  # Force to HOLD
            forced_recommendation = 'HOLD'
            reasons.append(f"R:R ratio {risk_reward_ratio:.2f} < 1.5 - Insufficient reward for BUY signal")

        # Veto 2: Poor risk/reward ratio
        elif risk_reward_ratio < 1.0:
            veto = True
            adjusted_score = min(current_score, 4.5)  # Force to HOLD or lower
            forced_recommendation = 'HOLD' if current_score > 4.5 else self._score_to_recommendation(adjusted_score)
            reasons.append(f"R:R ratio {risk_reward_ratio:.2f} < 1.0 - Risk exceeds reward")

        # Veto 2: Strong price decline with heavy selling
        if price_change_analysis:
            change_pct = price_change_analysis.get('change_percent', 0)
            selling_pressure = price_change_analysis.get('selling_pressure_pct', 50)

            if change_pct < -5 and selling_pressure > 70:
                veto = True
                adjusted_score = min(adjusted_score, 3.0)  # Force to SELL territory
                forced_recommendation = 'SELL'
                reasons.append(f"Strong price decline ({change_pct:.1f}%) with heavy selling pressure ({selling_pressure:.0f}%)")

        # Veto 3: Heavy insider selling
        if insider_data:
            net_sentiment = insider_data.get('net_activity', {}).get('sentiment', 'neutral')
            if net_sentiment in ['very_bearish', 'bearish']:
                veto = True
                adjusted_score = min(adjusted_score, 4.5)
                forced_recommendation = 'HOLD'
                reasons.append(f"Insider sentiment is {net_sentiment} - insiders are selling")

        return {
            'veto': veto,
            'adjusted_score': adjusted_score,
            'forced_recommendation': forced_recommendation,
            'reasons': reasons
        }

    def _score_to_recommendation(self, score: float) -> str:
        """Convert score to recommendation"""
        if score >= self.recommendation_thresholds['STRONG_BUY']:
            return 'STRONG BUY'
        elif score >= self.recommendation_thresholds['BUY']:
            return 'BUY'
        elif score >= self.recommendation_thresholds['HOLD']:
            return 'HOLD'
        elif score >= self.recommendation_thresholds['SELL']:
            return 'SELL'
        else:
            return 'STRONG SELL'

    def _calculate_confidence(self, final_score: float, component_scores: List[float]) -> str:
        """
        IMPROVED: Calculate confidence level based on:
        1. Agreement between components (std deviation)
        2. Distance from threshold boundaries
        3. Score consistency (how aligned are all components)
        4. Overall score strength
        """
        # 1. Calculate agreement (standard deviation)
        std_dev = np.std(component_scores)

        # 2. Distance from nearest threshold
        thresholds = sorted(self.recommendation_thresholds.values())
        min_distance = min(abs(final_score - t) for t in thresholds)

        # 3. Score consistency - normalize scores and check correlation
        # Components pointing in same direction = high consistency
        mean_score = np.mean(component_scores)
        consistency = sum(1 for s in component_scores if abs(s - mean_score) < 2.0) / len(component_scores)

        # 4. Overall score strength - extreme scores have more conviction
        score_strength = abs(final_score - 5.0) / 5.0  # 0 = neutral, 1 = very strong/weak

        # Calculate confidence score (0-1)
        conf_score = 0

        # Factor 1: Low std_dev = more agreement
        if std_dev < 1.0:
            conf_score += 0.4
        elif std_dev < 2.0:
            conf_score += 0.25
        elif std_dev < 3.0:
            conf_score += 0.1

        # Factor 2: Far from threshold = more certain
        if min_distance > 1.5:
            conf_score += 0.3
        elif min_distance > 0.8:
            conf_score += 0.15

        # Factor 3: High consistency
        conf_score += consistency * 0.2

        # Factor 4: Strong scores = more conviction
        conf_score += score_strength * 0.1

        # Convert to category
        if conf_score >= 0.75:
            return 'HIGH'
        elif conf_score >= 0.45:
            return 'MEDIUM'
        else:
            return 'LOW'

    def _confidence_to_percentage(self, confidence: str) -> int:
        """Convert confidence string to percentage"""
        mapping = {
            'HIGH': 85,
            'MEDIUM': 65,
            'LOW': 45
        }
        return mapping.get(confidence, 50)

    def _calculate_realistic_rr(self, current_price: float, target_price: float, stop_loss: float) -> float:
        """Calculate realistic R:R ratio"""
        logger.debug(f"_calculate_realistic_rr: cp={type(current_price)}, tp={type(target_price)}, sl={type(stop_loss)}")

        risk = abs(current_price - stop_loss)
        reward = abs(target_price - current_price)

        logger.debug(f"_calculate_realistic_rr: risk={type(risk)}={risk}, reward={type(reward)}={reward}")

        if risk == 0:
            return 0.0

        return round(reward / risk, 2)

    def _calculate_position_sizing(self, score: float, rr_ratio: float, confidence: str) -> Dict[str, Any]:
        """
        IMPROVED: Dynamic position sizing formula
        position_size% = min((score / 10) * (R:R / 2), 5)

        Additional adjustments:
        - Confidence multiplier
        - Volatility adjustment (via R:R proxy)
        - Hard caps for safety
        """
        # NEW FORMULA: Based on score and R:R
        # Base calculation: (score/10) * (R:R/2)
        # Example: score=8, R:R=2.0 → (0.8) * (1.0) = 0.8 = 8%
        base_size = (score / 10) * (rr_ratio / 2)

        # Adjust for confidence
        conf_multiplier = {
            'HIGH': 1.3,     # 30% boost for high confidence
            'MEDIUM': 1.0,   # No change
            'LOW': 0.6       # 40% reduction for low confidence
        }.get(confidence, 1.0)

        # Calculate final size
        final_size = base_size * conf_multiplier * 100  # Convert to percentage

        # Apply caps
        final_size = max(0.5, min(final_size, 10.0))  # Min 0.5%, Max 10%

        # Conservative and aggressive variants
        conservative = max(0.5, final_size * 0.5)
        aggressive = min(final_size * 1.5, 15.0)

        return {
            'recommended_percentage': round(final_size, 2),
            'conservative_percentage': round(conservative, 2),
            'aggressive_percentage': round(aggressive, 2),
            'rationale': f"Dynamic: (score={score:.1f}/10) * (R:R={rr_ratio:.2f}/2) * confidence={conf_multiplier:.1f}",
            'formula_used': 'position% = min((score/10) * (R:R/2) * confidence, 10%)'
        }

    def _generate_detailed_reasoning(self,
                                    recommendation: str,
                                    component_scores: Dict[str, float],
                                    weights: Dict[str, float],
                                    price_change_analysis: Dict[str, Any],
                                    insider_data: Dict[str, Any],
                                    rr_ratio: float,
                                    veto_reasons: List[str]) -> Dict[str, Any]:
        """Generate detailed reasoning for the recommendation"""

        reasons_for = []
        reasons_against = []

        # Technical
        if component_scores['technical'] >= 7:
            reasons_for.append(f"Strong technical signals (score: {component_scores['technical']:.1f}/10)")
        elif component_scores['technical'] <= 3:
            reasons_against.append(f"Weak technical setup (score: {component_scores['technical']:.1f}/10)")

        # Fundamental
        if component_scores['fundamental'] >= 7:
            reasons_for.append(f"Solid fundamentals (score: {component_scores['fundamental']:.1f}/10)")
        elif component_scores['fundamental'] <= 3:
            reasons_against.append(f"Poor fundamentals (score: {component_scores['fundamental']:.1f}/10)")

        # Price Action
        if price_change_analysis:
            change_pct = price_change_analysis.get('change_percent', 0)
            if change_pct > 2:
                reasons_for.append(f"Positive price momentum (+{change_pct:.1f}%)")
            elif change_pct < -2:
                reasons_against.append(f"Negative price momentum ({change_pct:.1f}%)")

        # Insider
        if insider_data:
            net_sentiment = insider_data.get('net_activity', {}).get('sentiment', 'neutral')
            if net_sentiment in ['bullish', 'very_bullish']:
                reasons_for.append(f"Insiders are buying ({net_sentiment})")
            elif net_sentiment in ['bearish', 'very_bearish']:
                reasons_against.append(f"Insiders are selling ({net_sentiment})")

        # Risk/Reward
        if rr_ratio >= 2.0:
            reasons_for.append(f"Favorable risk/reward ratio ({rr_ratio:.2f}:1)")
        elif rr_ratio < 1.0:
            reasons_against.append(f"Unfavorable risk/reward ratio ({rr_ratio:.2f}:1)")

        # Veto reasons are always "against"
        reasons_against.extend(veto_reasons)

        return {
            'summary': self._generate_summary(recommendation, reasons_for, reasons_against),
            'reasons_for': reasons_for,
            'reasons_against': reasons_against,
            'key_factors': self._identify_key_factors(component_scores, weights),
            'conviction_level': self._determine_conviction(reasons_for, reasons_against)
        }

    def _generate_summary(self, recommendation: str, reasons_for: List[str], reasons_against: List[str]) -> str:
        """Generate a summary sentence"""
        if recommendation in ['STRONG BUY', 'BUY']:
            if len(reasons_against) == 0:
                return f"Strong {recommendation} signal with no significant concerns."
            else:
                return f"{recommendation} recommendation despite some concerns: {', '.join(reasons_against[:2])}"
        elif recommendation == 'HOLD':
            return f"HOLD recommended due to mixed signals or insufficient conviction."
        else:  # SELL or STRONG SELL
            return f"{recommendation} due to: {', '.join(reasons_against[:2])}"

    def _identify_key_factors(self, component_scores: Dict[str, float], weights: Dict[str, float]) -> List[str]:
        """Identify the key factors driving the recommendation"""
        # Calculate weighted contribution
        contributions = {
            name: score * weights[name]
            for name, score in component_scores.items()
        }

        # Sort by contribution
        sorted_factors = sorted(contributions.items(), key=lambda x: abs(x[1] - 5.0), reverse=True)

        # Return top 3
        key_factors = []
        for name, _ in sorted_factors[:3]:
            score = component_scores[name]
            impact = "positive" if score >= 5 else "negative"
            key_factors.append(f"{name.title()}: {score:.1f}/10 ({impact} impact)")

        return key_factors

    def _determine_conviction(self, reasons_for: List[str], reasons_against: List[str]) -> str:
        """Determine conviction level"""
        for_count = len(reasons_for)
        against_count = len(reasons_against)

        if for_count >= 4 and against_count == 0:
            return "Very High"
        elif for_count >= 3 and against_count <= 1:
            return "High"
        elif for_count >= 2:
            return "Moderate"
        else:
            return "Low"


# Helper function to make it easy to use
import pandas as pd

def create_unified_recommendation(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper function to create unified recommendation from analysis results

    Usage:
        unified = create_unified_recommendation(analysis_results)
        print(f"Recommendation: {unified['recommendation']}")
        print(f"Confidence: {unified['confidence']}")
    """
    # Debug: Check what keys are in analysis_results
    logger.debug(f"analysis_results keys: {list(analysis_results.keys())[:20]}")

    engine = UnifiedRecommendationEngine()

    # Extract required data with safe extraction
    technical_analysis = analysis_results.get('technical_analysis', {})
    fundamental_analysis = analysis_results.get('fundamental_analysis', {})

    # Handle technical_score - could be nested or direct
    if isinstance(technical_analysis.get('technical_score'), dict):
        technical_score = technical_analysis.get('technical_score', {}).get('total_score', 5.0)
    else:
        technical_score = technical_analysis.get('technical_score', 5.0)

    # Handle fundamental_score
    fundamental_score = fundamental_analysis.get('overall_score', 5.0)

    price_change_analysis = analysis_results.get('price_change_analysis', {})
    insider_data = analysis_results.get('insider_institutional', {})

    # Extract price targets with safe conversion to float
    # target/stop loss are at root level, not in signal_analysis

    # Debug: print what we're getting
    _current_price_raw = analysis_results.get('current_price')
    _suggested_targets_raw = analysis_results.get('suggested_targets')
    _suggested_stop_loss_raw = analysis_results.get('suggested_stop_loss')

    logger.debug(f"Raw extraction - current_price: {type(_current_price_raw)} = {_current_price_raw}")
    logger.debug(f"Raw extraction - suggested_targets: {type(_suggested_targets_raw)} = {_suggested_targets_raw}")
    logger.debug(f"Raw extraction - suggested_stop_loss: {type(_suggested_stop_loss_raw)} = {_suggested_stop_loss_raw}")

    current_price = float(_current_price_raw) if _current_price_raw is not None else 100.0

    # Get suggested_targets (list) and suggested_stop_loss
    suggested_targets = _suggested_targets_raw if isinstance(_suggested_targets_raw, list) else []
    suggested_stop_loss = _suggested_stop_loss_raw

    # Safe extraction of target_price (use first target or default)
    if suggested_targets and len(suggested_targets) > 0:
        target_price = float(suggested_targets[0])  # Use first target
    else:
        target_price = float(current_price * 1.05)

    # Safe extraction of stop_loss
    if suggested_stop_loss is not None:
        stop_loss = float(suggested_stop_loss)
    else:
        stop_loss = float(current_price * 0.95)

    logger.debug(f"After conversion - current_price: {type(current_price)} = {current_price}")
    logger.debug(f"After conversion - target_price: {type(target_price)} = {target_price}")
    logger.debug(f"After conversion - stop_loss: {type(stop_loss)} = {stop_loss}")

    # Calculate R:R ratio (fixed calculation) - ensure all are floats
    try:
        risk = abs(float(current_price) - float(stop_loss))
        reward = abs(float(target_price) - float(current_price))
        rr_ratio = float(reward / risk) if risk > 0 else 0.0
    except (TypeError, ValueError) as e:
        # Debug logging
        logger.error(f"Type conversion error in R:R calculation:")
        logger.error(f"  current_price: {current_price} (type: {type(current_price)})")
        logger.error(f"  target_price: {target_price} (type: {type(target_price)})")
        logger.error(f"  stop_loss: {stop_loss} (type: {type(stop_loss)})")
        logger.error(f"  Error: {e}")
        raise

    time_horizon = analysis_results.get('time_horizon', 'short')

    return engine.generate_unified_recommendation(
        technical_score=technical_score,
        fundamental_score=fundamental_score,
        price_change_analysis=price_change_analysis,
        insider_data=insider_data,
        risk_reward_ratio=rr_ratio,
        current_price=current_price,
        target_price=target_price,
        stop_loss=stop_loss,
        time_horizon=time_horizon,
        analysis_results=analysis_results  # NEW: Pass full analysis for momentum scoring
    )
