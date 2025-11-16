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
        # 🆕 v6.0: Volatility-aware recommendation thresholds
        self.recommendation_thresholds = {
            'HIGH': {      # High volatility stocks (ATR% >= 5%)
                'STRONG_BUY': 8.0,
                'BUY': 5.5,     # More lenient - easier to qualify for BUY
                'HOLD': 4.5,
                'SELL': 3.0,
                'AVOID': 2.0
            },
            'MEDIUM': {    # Medium volatility stocks (ATR% >= 3%)
                'STRONG_BUY': 8.0,
                'BUY': 6.0,     # Moderate threshold
                'HOLD': 4.5,
                'SELL': 3.0,
                'AVOID': 2.0
            },
            'LOW': {       # Low volatility stocks (ATR% < 3%)
                'STRONG_BUY': 8.0,
                'BUY': 6.5,     # Stricter - higher bar for BUY
                'HOLD': 4.5,
                'SELL': 3.0,
                'AVOID': 2.0
            }
        }

        # Default thresholds (backward compatibility)
        self.default_thresholds = self.recommendation_thresholds['LOW']

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
                                       volatility_class: str = 'MEDIUM',
                                       analysis_results: Optional[Dict[str, Any]] = None,
                                       immediate_entry_info: Optional[Dict[str, Any]] = None,
                                       entry_levels: Optional[Dict[str, Any]] = None,
                                       tp_levels: Optional[Dict[str, Any]] = None,
                                       sl_details: Optional[Dict[str, Any]] = None,
                                       swing_points: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        logger.info(f"Generating unified recommendation for time_horizon: {time_horizon}")
        weights = self._get_component_weights(time_horizon)
        logger.info(f"Weights applied for {time_horizon}: {weights}")

        # 2. Score each component (0-10 scale)
        technical_component = technical_score
        fundamental_component = fundamental_score
        price_action_component = self._score_price_action(price_change_analysis)
        insider_component = self._score_insider_activity(insider_data)
        risk_reward_component = self._score_risk_reward(risk_reward_ratio)

        # 🆕 2a. Data Quality Check - Detect missing data vs bad data
        data_quality_check = self._check_data_quality(
            fundamental_score=fundamental_score,
            technical_score=technical_score,
            insider_component=insider_component,  # 🆕 Pass insider to check consistency
            analysis_results=analysis_results
        )

        # Adjust weights if data is missing (not bad, just missing)
        if data_quality_check['fundamental_missing']:
            logger.warning(f"⚠️ Fundamental data missing: {data_quality_check['fundamental_reason']}")
            # Redistribute fundamental weight to other components instead of penalty
            weights = self._redistribute_weights(weights, 'fundamental', data_quality_check)

            # 🆕 Validate weights sum to 1.0 after redistribution
            total_weight = sum(weights.values())
            if abs(total_weight - 1.0) > 0.01:  # Allow small floating point error
                logger.error(f"❌ Weight redistribution error: weights sum to {total_weight:.3f} (expected 1.0)")
            else:
                logger.info(f"✅ Weight redistribution successful (total: {total_weight:.3f})")

        missing_data_warnings = data_quality_check['warnings']

        # 🆕 2b. Adjust technical score based on Dip Quality (if available)
        if analysis_results:
            technical_component = self._adjust_score_with_dip_quality(
                technical_component, analysis_results
            )

        # NEW: Momentum component
        if analysis_results:
            momentum_component = self._score_momentum(analysis_results)
        else:
            momentum_component = 5.0  # Neutral if not available

        # NEW: Market State component (v3.0) - ใช้ Entry Readiness Score
        if analysis_results:
            market_state_component = self._score_market_state(analysis_results)
        else:
            market_state_component = 5.0  # Neutral if not available

        # NEW v3.1: Divergence component (RSI-Price, MACD-Price divergence)
        if analysis_results:
            divergence_component = self._score_divergence(analysis_results)
        else:
            divergence_component = 5.0  # Neutral if not available

        # 🆕 v4.0: Short Interest component (squeeze potential)
        if analysis_results:
            short_interest_component = self._score_short_interest(analysis_results)
        else:
            short_interest_component = 5.0  # Neutral if not available

        # 🆕 v5.0: Analyst Recommendations component
        if analysis_results:
            analyst_component = self._score_analyst_recommendations(analysis_results)
        else:
            analyst_component = 5.0  # Neutral if not available

        # 🆕 v5.0: Risk Assessment component (Yahoo Finance risk scores)
        if analysis_results:
            risk_assessment_component = self._score_risk_assessment(analysis_results)
        else:
            risk_assessment_component = 5.0  # Neutral if not available

        # 🆕 Log all component scores for debugging
        logger.info("=" * 60)
        logger.info("📊 COMPONENT SCORES (0-10 scale):")
        logger.info(f"  Technical:      {technical_component:.1f}/10 (weight: {weights['technical']:.2f})")
        logger.info(f"  Fundamental:    {fundamental_component:.1f}/10 (weight: {weights['fundamental']:.2f})")
        logger.info(f"  Price Action:   {price_action_component:.1f}/10 (weight: {weights['price_action']:.2f})")
        logger.info(f"  Insider:        {insider_component:.1f}/10 (weight: {weights['insider']:.2f})")
        logger.info(f"  Risk/Reward:    {risk_reward_component:.1f}/10 (weight: {weights['risk_reward']:.2f})")
        logger.info(f"  Momentum:       {momentum_component:.1f}/10 (weight: {weights['momentum']:.2f})")
        logger.info(f"  Market State:   {market_state_component:.1f}/10 (weight: {weights['market_state']:.2f})")
        logger.info(f"  Divergence:     {divergence_component:.1f}/10 (weight: {weights['divergence']:.2f})")
        logger.info(f"  Short Interest: {short_interest_component:.1f}/10 (weight: {weights.get('short_interest', 0.0):.2f})")
        logger.info(f"  Analyst Recs:   {analyst_component:.1f}/10 (weight: {weights.get('analyst', 0.0):.2f})") # 🆕 v5.0
        logger.info(f"  Risk Score:     {risk_assessment_component:.1f}/10 (weight: {weights.get('risk_score', 0.0):.2f})") # 🆕 v5.0
        logger.info("=" * 60)

        # 3. Calculate weighted score (🆕 v5.0: added analyst & risk_score)
        weighted_score = (
            technical_component * weights['technical'] +
            fundamental_component * weights['fundamental'] +
            price_action_component * weights['price_action'] +
            insider_component * weights['insider'] +
            risk_reward_component * weights['risk_reward'] +
            momentum_component * weights['momentum'] +
            market_state_component * weights['market_state'] +  # NEW v3.0
            divergence_component * weights['divergence'] +  # NEW v3.1
            short_interest_component * weights.get('short_interest', 0.0) +  # 🆕 v4.0
            analyst_component * weights.get('analyst', 0.0) +  # 🆕 v5.0
            risk_assessment_component * weights.get('risk_score', 0.0)  # 🆕 v5.0
        )

        logger.info(f"⚖️  WEIGHTED SCORE: {weighted_score:.2f}/10")
        logger.info(f"📋 Initial Recommendation ({volatility_class} volatility): {self._score_to_recommendation(weighted_score, volatility_class)}")

        # 4. Apply critical filters (veto conditions) - 🆕 ENHANCED with analysis_results
        veto_result = self._apply_veto_conditions(
            risk_reward_ratio,
            price_change_analysis,
            insider_data,
            weighted_score,
            volatility_class,  # 🆕 v6.0: Pass volatility class for threshold selection
            analysis_results=analysis_results  # 🆕 Pass full analysis for regime/volatility/etc checks
        )

        if veto_result['veto']:
            # Override recommendation due to critical issue
            final_score = veto_result['adjusted_score']
            final_recommendation = veto_result['forced_recommendation']
            confidence = 'LOW'
            veto_reasons = veto_result['reasons']
            logger.warning(f"🚨 VETO APPLIED: {weighted_score:.2f} → {final_score:.2f}, Forced: {final_recommendation}")
            for reason in veto_reasons:
                logger.warning(f"  • {reason}")
        else:
            final_score = weighted_score
            final_recommendation = self._score_to_recommendation(weighted_score, volatility_class)
            confidence = self._calculate_confidence(
                weighted_score,
                [technical_component, fundamental_component, price_action_component,
                 insider_component, risk_reward_component, momentum_component, market_state_component,
                 divergence_component, short_interest_component,
                 analyst_component, risk_assessment_component],  # 🆕 v5.0 added analyst & risk
                volatility_class  # 🆕 v6.0: Pass volatility class for threshold selection
            )
            veto_reasons = []
            logger.info(f"✅ No veto applied - proceeding with recommendation: {final_recommendation}")

        # 🆕 Get position size multiplier from veto result
        position_size_multiplier = veto_result.get('position_size_multiplier', 1.0)

        logger.info("=" * 60)
        logger.info(f"🎯 FINAL RECOMMENDATION: {final_recommendation} (Score: {final_score:.1f}/10, Confidence: {confidence})")
        logger.info("=" * 60)

        # 5. Calculate Signal Integrity Index (SII) - 🆕 v4.0: added short_interest
        sii_result = self._calculate_signal_integrity_index(
            [technical_component, fundamental_component, price_action_component,
             insider_component, risk_reward_component, momentum_component, market_state_component,
             divergence_component, short_interest_component,
             analyst_component, risk_assessment_component],  # 🆕 v5.0
            weights,
            final_recommendation
        )

        # 5b. Generate detailed reasoning
        reasoning = self._generate_detailed_reasoning(
            final_recommendation,
            {
                'technical': technical_component,
                'fundamental': fundamental_component,
                'price_action': price_action_component,
                'insider': insider_component,
                'risk_reward': risk_reward_component,
                'momentum': momentum_component,
                'market_state': market_state_component,
                'divergence': divergence_component,
                'short_interest': short_interest_component,  # 🆕 v4.0
                'analyst': analyst_component,  # 🆕 v5.0
                'risk_score': risk_assessment_component  # 🆕 v5.0
            },
            weights,
            price_change_analysis,
            insider_data,
            risk_reward_ratio,
            veto_reasons,
            missing_data_warnings=missing_data_warnings  # 🆕 Pass data quality warnings
        )

        # 6. Use the ALREADY CALCULATED risk_reward_ratio (from Market State entry price)
        # DO NOT recalculate using current_price - that causes inconsistency!
        logger.info(f"✅ Using pre-calculated R/R ratio: {risk_reward_ratio:.2f}:1 (from Market State entry price)")

        # 7. Generate position sizing recommendation - 🆕 ENHANCED with multiplier
        position_sizing = self._calculate_position_sizing(
            final_score,
            risk_reward_ratio,
            confidence,
            position_size_multiplier=position_size_multiplier  # 🆕 Apply regime/volatility adjustments
        )

        # 8. Calculate risk/reward in dollars and percentages
        # These are for display only - they show CURRENT vs targets (not entry vs targets)
        risk_dollars = abs(current_price - stop_loss)
        reward_dollars = abs(target_price - current_price)
        risk_percent = (risk_dollars / current_price) * 100
        reward_percent = (reward_dollars / current_price) * 100

        return {
            'recommendation': final_recommendation,
            'score': round(final_score, 1),
            'confidence': confidence,
            'confidence_percentage': self._confidence_to_percentage(confidence),

            # Add price targets for Enhanced Features
            'current_price': current_price,
            'target_price': target_price,
            'stop_loss': stop_loss,

            # 🆕 v5.0 + v5.1: Intelligent Entry/TP/SL Features
            'immediate_entry_info': immediate_entry_info or {},
            'entry_levels': entry_levels or {},
            'tp_levels': tp_levels or {},
            'sl_details': sl_details or {},
            'swing_points': swing_points or {},

            'component_scores': {
                'technical': round(technical_component, 1),
                'fundamental': round(fundamental_component, 1),
                'price_action': round(price_action_component, 1),
                'insider': round(insider_component, 1),
                'risk_reward': round(risk_reward_component, 1),
                'momentum': round(momentum_component, 1),
                'market_state': round(market_state_component, 1),  # NEW v3.0
                'divergence': round(divergence_component, 1),  # NEW v3.1
                'short_interest': round(short_interest_component, 1),  # 🆕 v4.0
                'analyst': round(analyst_component, 1),  # 🆕 v5.0
                'risk_score': round(risk_assessment_component, 1)  # 🆕 v5.0
            },

            'weights_applied': weights,

            'signal_integrity_index': sii_result,  # NEW: SII for signal consistency

            'risk_reward_analysis': {
                'ratio': risk_reward_ratio,  # ✅ FIXED: Use the pre-calculated R/R from Market State
                'risk_dollars': round(risk_dollars, 2),
                'reward_dollars': round(reward_dollars, 2),
                'risk_percent': round(risk_percent, 2),
                'reward_percent': round(reward_percent, 2),
                'is_favorable': risk_reward_ratio >= 1.5
            },

            'position_sizing': position_sizing,

            'reasoning': reasoning,

            # NEW v3.1: Enhanced Final Verdict
            'final_verdict': self._generate_final_verdict(
                final_recommendation,
                final_score,
                confidence,
                reasoning,
                risk_reward_ratio,
                veto_reasons
            ),

            'veto_applied': bool(veto_reasons),
            'veto_reasons': veto_reasons,

            # 🆕 v4.1: Price Prediction & Bull Trap Warning
            'price_prediction': self._generate_price_prediction(
                current_price,
                target_price,
                stop_loss,
                analysis_results
            ),

            'analysis_timestamp': pd.Timestamp.now().isoformat()
        }

    def _get_component_weights(self, time_horizon: str) -> Dict[str, float]:
        """
        Get component weights based on time horizon

        OPTIMIZED WEIGHTS (v3.1 - with Market State + Divergence):
        - Short (1-14 days): Focus on Technical + Market State + Momentum + Divergence
        - Medium (1-6 months): Balanced approach with more Fundamental
        - Long (6+ months): Focus on Fundamentals + Insider conviction
        """
        weights = {
            'short': {
                'technical': 0.18,      # ↓ Chart patterns, S/R
                'market_state': 0.16,   # ↓ Entry timing, market regime
                'risk_reward': 0.16,    # ↓ R/R ratio critical
                'momentum': 0.11,       # ↓ RSI, MACD, EMA
                'divergence': 0.10,     # ⭐ v3.1: RSI/MACD-Price divergence
                'fundamental': 0.09,    # = Basic screening
                'short_interest': 0.08, # 🆕 v4.0: Squeeze potential
                'price_action': 0.04,   # ↓ Volume, candles
                'analyst': 0.03,        # 🆕 v5.0: Less relevant for short-term
                'risk_score': 0.04,     # 🆕 v5.0: Important to avoid high-risk stocks
                'insider': 0.01         # ↓ Minimal
            },
            'medium': {
                'fundamental': 0.24,    # ↓ Earnings, growth, valuation
                'technical': 0.15,      # ↓ Trend direction
                'market_state': 0.12,   # ↓ Entry timing
                'insider': 0.10,        # = Insider trades
                'momentum': 0.09,       # ↓ Trend strength
                'risk_reward': 0.09,    # = Position sizing
                'analyst': 0.06,        # 🆕 v5.0: Moderate weight
                'risk_score': 0.05,     # 🆕 v5.0: Risk penalty
                'divergence': 0.05,     # ⭐ v3.1: Moderate weight
                'short_interest': 0.03, # 🆕 v4.0: Moderate relevance
                'price_action': 0.02    # = Confirmation
            },
            'long': {
                'fundamental': 0.52,    # ↑ DOMINANT: Growth, valuation, moat
                'insider': 0.19,        # ↑ Long-term conviction signal
                'analyst': 0.08,        # 🆕 v5.0: Important for long-term
                'risk_reward': 0.07,    # ↓ Less critical
                'risk_score': 0.06,     # 🆕 v5.0: Long-term risk matters
                'technical': 0.05,      # ↓ Entry timing only
                'market_state': 0.02,   # ↓ Minimal for long-term
                'short_interest': 0.02, # 🆕 v4.0: Can indicate squeeze but not primary factor
                'momentum': 0.01,       # ↓ Almost irrelevant
                'divergence': 0.01,     # ↓ Irrelevant for long-term
                'price_action': 0.00    # ↓ Completely irrelevant
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

    def _score_market_state(self, analysis_results: Dict[str, Any]) -> float:
        """
        Score Market State Analysis (0-10) - NEW in v3.0

        Uses Entry Readiness Score และ Market State confidence:
        - Entry Readiness 0-100 → convert to 0-10 scale
        - Market State confidence → modifier
        - Action Signal (BUY_NOW/READY/WAIT) → additional weight

        ตัวอย่าง:
        - Entry Readiness 80%, Confidence 75% → Score ~8.5/10
        - Entry Readiness 50%, Confidence 65% → Score ~5.5/10
        """
        try:
            technical_analysis = analysis_results.get('technical_analysis', {})
            market_state_analysis = technical_analysis.get('market_state_analysis', {})

            if not market_state_analysis:
                return 5.0  # Neutral if no market state data

            strategy = market_state_analysis.get('strategy', {})
            confidence_data = market_state_analysis.get('confidence', {})

            # 1. Base score from Entry Readiness (0-100 → 0-10)
            entry_readiness = strategy.get('entry_readiness', 50.0)
            base_score = entry_readiness / 10.0  # Convert 0-100 to 0-10

            # 2. Confidence modifier
            confidence_pct = confidence_data.get('confidence', 50)
            confidence_modifier = (confidence_pct - 50) / 50  # -1 to +1

            # 3. Action Signal modifier
            action_signal = strategy.get('action_signal', 'WAIT')
            if action_signal == 'BUY_NOW':
                action_modifier = 1.5  # Strong positive
            elif action_signal == 'READY':
                action_modifier = 0.5  # Moderate positive
            elif action_signal == 'WAIT':
                action_modifier = -0.5  # Slight negative
            else:
                action_modifier = 0.0

            # 4. Volume confirmation bonus
            volume_confirmation = confidence_data.get('volume_confirmation', False)
            volume_bonus = 0.5 if volume_confirmation else 0.0

            # 5. Calculate final score
            final_score = base_score + (confidence_modifier * 2.0) + action_modifier + volume_bonus

            logger.debug(f"Market State Score: entry_readiness={entry_readiness:.1f} → base={base_score:.1f}, "
                        f"conf_mod={confidence_modifier:.2f}, action_mod={action_modifier:.1f}, "
                        f"vol_bonus={volume_bonus:.1f} → final={final_score:.1f}")

            return max(0, min(10, final_score))

        except Exception as e:
            logger.warning(f"Market state scoring failed: {e}")
            return 5.0  # Neutral on error

    def _score_divergence(self, analysis_results: Dict[str, Any]) -> float:
        """
        Score Divergence Analysis (0-10) - NEW in v3.1

        Detects RSI-Price and MACD-Price divergences:
        - Bullish Divergence: Price ลง แต่ indicator ขึ้น → สัญญาณกลับตัวขึ้น (Strong BUY)
        - Bearish Divergence: Price ขึ้น แต่ indicator ลง → สัญญาณกลับตัวลง (Strong SELL)
        - No Divergence: Price และ indicator เป็นทิศทางเดียวกัน → สัญญาณยืนยัน

        Returns:
            Score 0-10 (10 = Strong Bullish Div, 5 = No Div, 0 = Strong Bearish Div)
        """
        try:
            technical_analysis = analysis_results.get('technical_analysis', {})
            indicators = technical_analysis.get('indicators', {})

            score = 5.0  # Neutral base

            # Get price data for trend calculation
            current_price = indicators.get('current_price', 0)
            sma_50 = indicators.get('sma_50', current_price)

            # Calculate price trend (simple: compare current vs SMA50)
            if current_price and sma_50:
                price_trend_pct = ((current_price - sma_50) / sma_50) * 100
            else:
                price_trend_pct = 0

            # 1. RSI DIVERGENCE
            rsi = indicators.get('rsi')
            if rsi is not None:
                # RSI Bullish Divergence: Price down (< SMA50) but RSI oversold/rising
                if price_trend_pct < -5 and rsi < 35:
                    # Strong bullish divergence signal
                    score += 3.0
                    logger.debug(f"Divergence: Bullish RSI divergence detected (Price down {price_trend_pct:.1f}%, RSI {rsi:.0f})")
                elif price_trend_pct < -2 and rsi < 45:
                    # Moderate bullish divergence
                    score += 1.5

                # RSI Bearish Divergence: Price up (> SMA50) but RSI overbought/falling
                elif price_trend_pct > 5 and rsi > 65:
                    # Strong bearish divergence signal
                    score -= 3.0
                    logger.debug(f"Divergence: Bearish RSI divergence detected (Price up {price_trend_pct:.1f}%, RSI {rsi:.0f})")
                elif price_trend_pct > 2 and rsi > 55:
                    # Moderate bearish divergence
                    score -= 1.5

            # 2. MACD DIVERGENCE
            macd_line = indicators.get('macd_line')
            macd_signal = indicators.get('macd_signal')
            macd_histogram = indicators.get('macd_histogram')

            if all(x is not None for x in [macd_line, macd_signal, macd_histogram]):
                # MACD Bullish Divergence: Price down but MACD turning up
                if price_trend_pct < -3 and macd_line > macd_signal and macd_histogram > 0:
                    score += 2.0
                    logger.debug(f"Divergence: Bullish MACD divergence (Price down, MACD bullish crossover)")
                # MACD Bearish Divergence: Price up but MACD turning down
                elif price_trend_pct > 3 and macd_line < macd_signal and macd_histogram < 0:
                    score -= 2.0
                    logger.debug(f"Divergence: Bearish MACD divergence (Price up, MACD bearish crossover)")

            # 3. Volume Divergence (OBV) - if available
            obv = indicators.get('obv')
            obv_sma = indicators.get('obv_sma_20')  # Assume we have OBV SMA

            if obv and obv_sma:
                obv_trend_pct = ((obv - obv_sma) / abs(obv_sma)) * 100 if obv_sma != 0 else 0

                # Bullish Volume Divergence: Price down but OBV up (buying pressure)
                if price_trend_pct < -3 and obv_trend_pct > 5:
                    score += 1.0
                    logger.debug(f"Divergence: Bullish OBV divergence (Price down, OBV up)")
                # Bearish Volume Divergence: Price up but OBV down (no buying support)
                elif price_trend_pct > 3 and obv_trend_pct < -5:
                    score -= 1.0
                    logger.debug(f"Divergence: Bearish OBV divergence (Price up, OBV down)")

            logger.debug(f"Divergence Score: {score:.1f}/10 (price_trend={price_trend_pct:.1f}%, rsi={rsi}, macd_hist={macd_histogram})")

            return max(0, min(10, score))

        except Exception as e:
            logger.warning(f"Divergence scoring failed: {e}")
            return 5.0  # Neutral on error

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

    def _adjust_score_with_dip_quality(self, technical_score: float,
                                      analysis_results: Dict[str, Any]) -> float:
        """
        🆕 Adjust technical score based on Dip Quality and Falling Knife analysis

        Dip Quality:
        - EXCELLENT: +1.0 points (great buy opportunity)
        - GOOD: +0.5 points
        - FAIR: +0.2 points
        - POOR: -1.0 points (dangerous)

        Already considers falling_knife_penalty in dip_analysis
        """
        try:
            technical_analysis = analysis_results.get('technical_analysis', {})
            market_state = technical_analysis.get('market_state_analysis', {})
            dip_analysis = market_state.get('dip_opportunity', {})

            is_dip = dip_analysis.get('is_dip', False)
            dip_quality = dip_analysis.get('dip_quality', 'NONE')
            opportunity_score = dip_analysis.get('opportunity_score', 0)

            adjustment = 0.0

            if is_dip:
                if dip_quality == 'EXCELLENT':
                    adjustment = 1.0
                    logger.info(f"✅ DIP QUALITY BONUS: +1.0 (EXCELLENT dip opportunity)")
                elif dip_quality == 'GOOD':
                    adjustment = 0.5
                    logger.info(f"✅ DIP QUALITY BONUS: +0.5 (GOOD dip opportunity)")
                elif dip_quality == 'FAIR':
                    adjustment = 0.2
                    logger.info(f"⚠️ DIP QUALITY BONUS: +0.2 (FAIR dip, be cautious)")
                elif dip_quality == 'POOR':
                    adjustment = -1.0
                    logger.warning(f"❌ DIP QUALITY PENALTY: -1.0 (POOR dip quality - likely falling knife)")
            else:
                # Not a dip, no adjustment
                logger.debug("No dip detected - no quality adjustment")

            # Apply adjustment and ensure bounds
            adjusted_score = max(0, min(10, technical_score + adjustment))

            if adjustment != 0:
                logger.info(f"Technical score adjusted: {technical_score:.1f} → {adjusted_score:.1f} (dip quality: {dip_quality})")

            return adjusted_score

        except Exception as e:
            logger.warning(f"Dip quality adjustment failed: {e}")
            return technical_score  # Return original on error

    def _score_short_interest(self, analysis_results: Dict[str, Any]) -> float:
        """
        🆕 v4.0: Score Short Interest and Squeeze Potential (0-10)

        Short Interest Scoring:
        - High short interest (>20%) + high squeeze potential → 8-10 (opportunity)
        - Moderate short interest (10-20%) → 5-7 (neutral to positive)
        - Low short interest (<10%) → 4-6 (neutral)
        - Very low (<5%) → 3-5 (slightly negative - no squeeze catalyst)

        Squeeze Potential:
        - HIGH: +3 points (GameStop/AMC scenario)
        - MEDIUM: +1.5 points
        - LOW: +0.5 points

        Returns:
            Score 0-10 (10 = high squeeze opportunity)
        """
        try:
            # Try to get from enhanced features first
            enhanced_features = analysis_results.get('enhanced_features', {})
            short_interest_data = enhanced_features.get('short_interest', {})

            # If not in enhanced features, try from symbol info
            if not short_interest_data or 'short_interest' not in short_interest_data:
                # Try alternative location
                symbol_info = analysis_results.get('symbol_info', {})
                short_pct = symbol_info.get('short_percent_of_float', 0)
                days_to_cover = symbol_info.get('short_ratio', 0)

                if short_pct == 0:
                    # No short interest data available
                    logger.debug("No short interest data available - using neutral score")
                    return 5.0

                # Manual calculation if we have basic data
                short_interest_data = {
                    'short_interest': {
                        'short_pct_float': short_pct,
                        'days_to_cover': days_to_cover
                    }
                }

            # Extract short interest metrics
            si_metrics = short_interest_data.get('short_interest', {})
            short_pct = si_metrics.get('short_pct_float', si_metrics.get('percentage', 0))
            days_to_cover = si_metrics.get('days_to_cover', 0)
            squeeze_potential = short_interest_data.get('squeeze_potential', 'LOW')

            logger.debug(f"Short Interest: {short_pct:.1f}%, Days to Cover: {days_to_cover:.1f}, Squeeze: {squeeze_potential}")

            # Base score from short interest percentage
            score = 5.0  # Neutral base

            if short_pct >= 30:
                score = 8.0  # Very high short interest
            elif short_pct >= 20:
                score = 7.0  # High short interest
            elif short_pct >= 15:
                score = 6.5  # Moderately high
            elif short_pct >= 10:
                score = 6.0  # Moderate
            elif short_pct >= 5:
                score = 5.0  # Neutral
            else:
                score = 4.0  # Low short interest (no catalyst)

            # Adjust based on squeeze potential
            if squeeze_potential == 'HIGH' or squeeze_potential == 'EXTREME':
                score += 2.5
                logger.info(f"🚀 HIGH SQUEEZE POTENTIAL: Short Interest bonus +2.5 points")
            elif squeeze_potential == 'MEDIUM' or squeeze_potential == 'MODERATE':
                score += 1.5
                logger.info(f"⚡ MEDIUM SQUEEZE POTENTIAL: Short Interest bonus +1.5 points")
            elif squeeze_potential == 'LOW':
                score += 0.5

            # Days to cover bonus (if >= 5 days, harder for shorts to exit)
            if days_to_cover >= 7:
                score += 1.0
                logger.debug(f"Days to Cover bonus: +1.0 ({days_to_cover:.1f} days)")
            elif days_to_cover >= 5:
                score += 0.5
                logger.debug(f"Days to Cover bonus: +0.5 ({days_to_cover:.1f} days)")

            # Cap at 10
            score = min(10.0, score)

            logger.info(f"Short Interest Score: {score:.1f}/10 (SI: {short_pct:.1f}%, Squeeze: {squeeze_potential})")

            return score

        except Exception as e:
            logger.warning(f"Short interest scoring failed: {e}")
            return 5.0  # Neutral on error

    def _score_analyst_recommendations(self, analysis_results: Dict[str, Any]) -> float:
        """
        🆕 v5.0: Score based on analyst recommendations (0-10)

        Scoring logic:
        - Strong Buy (many analysts, buy) → 8-10
        - Buy → 6-8
        - Hold → 4-6
        - Sell/Underperform → 0-3

        Modifiers:
        - Number of analysts (confidence boost)
        - Price target vs current price (upside potential)
        """
        try:
            # Get financial data with analyst recommendations
            financial_data = analysis_results.get('fundamental_analysis', {})

            # Extract analyst data
            recommendation_key = financial_data.get('recommendation_key', 'hold')
            num_analysts = financial_data.get('number_of_analyst_opinions', 0)
            target_mean = financial_data.get('target_mean_price', 0)
            current_price = financial_data.get('current_price', 0)

            # Base score from recommendation
            recommendation_scores = {
                'strong_buy': 9.0,
                'strongbuy': 9.0,
                'buy': 7.5,
                'hold': 5.0,
                'sell': 2.5,
                'strong_sell': 1.0,
                'strongsell': 1.0,
                'underperform': 2.0,
                'outperform': 7.0
            }

            rec_key = str(recommendation_key).lower() if recommendation_key else 'hold'
            score = recommendation_scores.get(rec_key, 5.0)

            logger.debug(f"Analyst base score from '{rec_key}': {score:.1f}/10")

            # Bonus for number of analysts (confidence)
            if num_analysts >= 40:
                score += 1.0
                logger.debug(f"Analyst count bonus: +1.0 ({num_analysts} analysts)")
            elif num_analysts >= 20:
                score += 0.5
                logger.debug(f"Analyst count bonus: +0.5 ({num_analysts} analysts)")
            elif num_analysts >= 10:
                score += 0.3
                logger.debug(f"Analyst count bonus: +0.3 ({num_analysts} analysts)")
            elif num_analysts < 5 and num_analysts > 0:
                score -= 0.5
                logger.debug(f"Low analyst coverage penalty: -0.5 ({num_analysts} analysts)")

            # Price target upside/downside adjustment
            if target_mean and current_price and current_price > 0:
                upside_pct = ((target_mean - current_price) / current_price) * 100

                if upside_pct > 30:
                    score += 1.0
                    logger.debug(f"High upside bonus: +1.0 ({upside_pct:.1f}% upside)")
                elif upside_pct > 15:
                    score += 0.5
                    logger.debug(f"Moderate upside bonus: +0.5 ({upside_pct:.1f}% upside)")
                elif upside_pct < -15:
                    score -= 1.0
                    logger.debug(f"Downside penalty: -1.0 ({upside_pct:.1f}% downside)")
                elif upside_pct < -5:
                    score -= 0.5
                    logger.debug(f"Slight downside penalty: -0.5 ({upside_pct:.1f}% downside)")

            # Cap at 0-10
            score = max(0, min(10, score))

            logger.info(f"Analyst Score: {score:.1f}/10 (Rec: {rec_key}, Analysts: {num_analysts})")

            return score

        except Exception as e:
            logger.warning(f"Analyst recommendation scoring failed: {e}")
            return 5.0  # Neutral on error

    def _score_risk_assessment(self, analysis_results: Dict[str, Any]) -> float:
        """
        🆕 v5.0: Score based on Yahoo Finance risk assessment (0-10)

        Risk scoring (inverse - lower risk = higher score):
        - Risk 1-2 (Very Low) → 9-10
        - Risk 3-4 (Low) → 7-8
        - Risk 5-6 (Medium) → 5-6
        - Risk 7-8 (High) → 3-4
        - Risk 9-10 (Very High) → 0-2

        Uses: overall_risk primarily, with modifiers from specific risks
        """
        try:
            # Get financial data with risk scores
            financial_data = analysis_results.get('fundamental_analysis', {})

            # Extract risk scores (1-10 scale from Yahoo)
            overall_risk = financial_data.get('overall_risk', 5)
            audit_risk = financial_data.get('audit_risk')
            board_risk = financial_data.get('board_risk')
            comp_risk = financial_data.get('compensation_risk')

            # No risk data available
            if overall_risk is None or overall_risk == 0:
                logger.debug("No risk assessment data available - using neutral score")
                return 5.0

            # Inverse scoring: low risk = high score
            # overall_risk is 1-10, we want to convert to score 0-10
            base_score = 10 - (overall_risk - 1)  # Risk 1→10, Risk 10→1

            logger.debug(f"Risk base score from overall_risk={overall_risk}: {base_score:.1f}/10")

            # Penalty for specific high risks
            if comp_risk and comp_risk >= 9:
                base_score -= 0.5
                logger.debug(f"High compensation risk penalty: -0.5 (comp_risk={comp_risk})")

            if board_risk and board_risk >= 8:
                base_score -= 0.3
                logger.debug(f"High board risk penalty: -0.3 (board_risk={board_risk})")

            if audit_risk and audit_risk >= 8:
                base_score -= 0.3
                logger.debug(f"High audit risk penalty: -0.3 (audit_risk={audit_risk})")

            # Bonus for very low risk
            if overall_risk <= 2:
                base_score += 0.5
                logger.debug(f"Very low risk bonus: +0.5 (overall_risk={overall_risk})")

            # Cap at 0-10
            score = max(0, min(10, base_score))

            logger.info(f"Risk Assessment Score: {score:.1f}/10 (Overall Risk: {overall_risk}/10 → Lower is better)")

            return score

        except Exception as e:
            logger.warning(f"Risk assessment scoring failed: {e}")
            return 5.0  # Neutral on error

    def _check_data_quality(self,
                           fundamental_score: float,
                           technical_score: float,
                           insider_component: float = 5.0,
                           analysis_results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        🆕 Check data quality to distinguish missing data from bad data

        Returns:
            Dictionary with:
            - fundamental_missing: bool
            - fundamental_reason: str (why it's missing)
            - warnings: list of warning messages
            - is_etf: bool
            - data_completeness: float (0-1)
            - has_insider_data: bool
        """
        warnings = []
        fundamental_missing = False
        fundamental_reason = ""
        is_etf = False
        data_completeness = 1.0
        has_insider_data = insider_component != 5.0  # If not neutral, we have insider data

        # Check if fundamental = 0 due to missing data
        if fundamental_score == 0:
            # Try to determine why
            if analysis_results:
                fundamental_analysis = analysis_results.get('fundamental_analysis', {})

                # Check if ETF
                is_etf = fundamental_analysis.get('is_etf', False)

                # Check data quality
                data_quality = fundamental_analysis.get('data_quality', {})
                data_completeness = data_quality.get('completeness', 0.0) if data_quality else 0.0

                if is_etf:
                    fundamental_missing = True
                    fundamental_reason = "ETF/Special instrument - No fundamental data expected"
                    warnings.append("⚠️ ETF detected - Using technical analysis only (normal behavior)")
                elif data_completeness < 0.3:
                    fundamental_missing = True

                    # 🆕 IMPROVED: Check if we have insider data
                    if has_insider_data:
                        fundamental_reason = f"Financial data incomplete ({data_completeness:.0%}) but Insider data available"
                        warnings.append(f"⚠️ Missing earnings/valuation data ({data_completeness:.0%} complete)")
                        warnings.append(f"✅ Insider data available (score: {insider_component:.1f}/10) - Using for analysis")
                    else:
                        fundamental_reason = f"Data incomplete ({data_completeness:.0%}) - API error or new ticker"
                        warnings.append(f"⚠️ Missing fundamental data ({data_completeness:.0%} complete) - Relying on technical analysis")
                else:
                    # Data exists but score is genuinely 0 (very poor fundamentals)
                    fundamental_missing = False
                    fundamental_reason = "Poor fundamentals (genuine low score)"
                    # Don't add warning - this is legitimate bad score
            else:
                # No analysis_results - assume missing data
                fundamental_missing = True
                fundamental_reason = "No analysis results available"
                warnings.append("⚠️ Limited data available - Confidence may be lower")
                data_completeness = 0.5

        return {
            'fundamental_missing': fundamental_missing,
            'fundamental_reason': fundamental_reason,
            'warnings': warnings,
            'is_etf': is_etf,
            'data_completeness': data_completeness,
            'has_insider_data': has_insider_data
        }

    def _redistribute_weights(self,
                             weights: Dict[str, float],
                             missing_component: str,
                             data_quality_check: Dict[str, Any]) -> Dict[str, float]:
        """
        🆕 Redistribute weights when data is missing (not bad, just missing)

        Instead of penalizing with fundamental=0, redistribute its weight to other components
        """
        adjusted_weights = weights.copy()

        if missing_component == 'fundamental':
            fundamental_weight = weights.get('fundamental', 0.0)

            if fundamental_weight > 0:
                logger.info(f"Redistributing fundamental weight ({fundamental_weight:.2f}) to other components")

                # Remove fundamental weight
                adjusted_weights['fundamental'] = 0.0

                # Distribute to technical and market_state (most reliable alternatives)
                boost = fundamental_weight / 2.0
                adjusted_weights['technical'] = adjusted_weights.get('technical', 0.0) + boost
                adjusted_weights['market_state'] = adjusted_weights.get('market_state', 0.0) + boost

                logger.info(f"New weights: technical={adjusted_weights['technical']:.2f}, market_state={adjusted_weights['market_state']:.2f}")

        return adjusted_weights

    def _apply_veto_conditions(self,
                               risk_reward_ratio: float,
                               price_change_analysis: Dict[str, Any],
                               insider_data: Dict[str, Any],
                               current_score: float,
                               volatility_class: str = 'LOW',
                               analysis_results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply veto conditions that can override the recommendation

        ENHANCED VETO conditions (v4.0):
        1. R:R ratio < 1.5 for BUY → Force HOLD (insufficient reward)
        2. R:R ratio < 1.0 → Force HOLD (risk too high)
        3. Price drop > 5% + strong selling → Force SELL
        4. Heavy insider selling → Downgrade to HOLD
        5. 🆕 Market Regime = CRISIS → Force HOLD + reduce position
        6. 🆕 Volatility Spike > 50% → Force HOLD + reduce position
        7. 🆕 Overextension EXTREME → Wait for pullback
        8. 🆕 Falling Knife HIGH → Avoid catching falling knife
        9. 🆕 R:R deterioration > 30% → Consider exit
        """
        veto = False
        reasons = []
        adjusted_score = current_score
        forced_recommendation = None
        position_size_multiplier = 1.0  # Default: no adjustment

        # Veto 1: R:R ratio < 1.5 for BUY signals - 🆕 v6.0: Volatility-aware threshold
        # Get volatility-aware BUY threshold
        buy_threshold = self.recommendation_thresholds.get(volatility_class, self.default_thresholds)['BUY']

        if risk_reward_ratio < 1.5 and current_score >= buy_threshold:  # Would be BUY or STRONG BUY
            veto = True
            adjusted_score = 4.5  # Force to HOLD
            forced_recommendation = 'HOLD'
            reasons.append(f"R:R ratio {risk_reward_ratio:.2f} < 1.5 - Insufficient reward for BUY signal ({volatility_class} volatility, threshold={buy_threshold})")

        # Veto 2: Poor risk/reward ratio - 🆕 v6.0: Volatility-aware thresholds
        elif risk_reward_ratio < 1.0:
            veto = True
            # Define volatility-aware R/R thresholds
            rr_thresholds = {
                'HIGH': 0.5,      # More lenient for high volatility stocks
                'MEDIUM': 0.65,   # Moderate threshold
                'LOW': 0.8        # Strict for low volatility stocks
            }
            threshold = rr_thresholds.get(volatility_class, 0.8)  # Default to LOW volatility

            # R/R < threshold = AVOID (don't enter at all)
            # R/R threshold-1.0 = HOLD (risky but not terrible)
            if risk_reward_ratio < threshold:
                adjusted_score = min(current_score, 3.5)
                forced_recommendation = 'AVOID'
                reasons.append(f"R:R ratio {risk_reward_ratio:.2f} < {threshold} ({volatility_class} volatility) - Risk significantly exceeds reward - AVOID entry")
            else:
                adjusted_score = min(current_score, 4.5)
                forced_recommendation = 'HOLD'
                reasons.append(f"R:R ratio {risk_reward_ratio:.2f} < 1.0 ({volatility_class} volatility) - Risk exceeds reward slightly - HOLD or wait for better entry")

        # Veto 3: Strong price decline with heavy selling
        if price_change_analysis:
            change_pct = price_change_analysis.get('change_percent', 0)
            selling_pressure = price_change_analysis.get('selling_pressure_pct', 50)

            if change_pct < -5 and selling_pressure > 70:
                veto = True
                adjusted_score = min(adjusted_score, 3.0)  # Force to SELL territory
                forced_recommendation = 'SELL'
                reasons.append(f"Strong price decline ({change_pct:.1f}%) with heavy selling pressure ({selling_pressure:.0f}%)")

        # Veto 4: Heavy insider selling
        if insider_data:
            net_sentiment = insider_data.get('net_activity', {}).get('sentiment', 'neutral')
            if net_sentiment in ['very_bearish', 'bearish']:
                veto = True
                adjusted_score = min(adjusted_score, 4.5)
                forced_recommendation = 'HOLD'
                reasons.append(f"Insider sentiment is {net_sentiment} - insiders are selling")

        # 🆕 Veto 5: Market Regime = CRISIS or BEAR_TRENDING
        if analysis_results:
            technical_analysis = analysis_results.get('technical_analysis', {})
            market_regime_data = technical_analysis.get('market_regime', {})
            current_regime = market_regime_data.get('current', {})
            regime_type = current_regime.get('regime_type', 'unknown')

            logger.debug(f"Veto check - Market regime: {regime_type}")

            # CRISIS regime: ตลาดวิกฤติ → หยุดเข้าใหม่ทั้งหมด
            if regime_type in ['CRISIS', 'crisis']:
                if current_score >= buy_threshold:  # Would be BUY (volatility-aware)
                    veto = True
                    adjusted_score = 4.5
                    forced_recommendation = 'HOLD'
                    reasons.append("🚨 Market in CRISIS regime - avoid new positions")
                position_size_multiplier = min(position_size_multiplier, 0.3)  # ลด 70%

            # BEAR_TRENDING: ตลาดขาลง → ระมัดระวังสูง
            elif regime_type in ['BEAR_TRENDING', 'bear_trending', 'BEAR_VOLATILE', 'bear_volatile']:
                if current_score >= 8.0:  # Would be STRONG BUY
                    adjusted_score = max(adjusted_score - 1.5, buy_threshold)  # Downgrade to BUY (volatility-aware)
                    reasons.append(f"⚠️ Market in {regime_type} - reduced conviction")
                position_size_multiplier = min(position_size_multiplier, 0.6)  # ลด 40%

        # 🆕 Veto 6: Volatility Spike
        if analysis_results:
            technical_analysis = analysis_results.get('technical_analysis', {})
            risk_metrics = technical_analysis.get('risk_metrics', {})

            current_atr = risk_metrics.get('atr_current')
            historical_atr = risk_metrics.get('atr_average')

            if current_atr and historical_atr and historical_atr > 0:
                atr_change_pct = ((current_atr - historical_atr) / historical_atr) * 100

                logger.debug(f"Veto check - ATR change: {atr_change_pct:.1f}%")

                # Volatility spike > 50%
                if atr_change_pct > 50:
                    if current_score >= buy_threshold:  # Would be BUY (volatility-aware)
                        veto = True
                        adjusted_score = 4.5
                        forced_recommendation = 'HOLD'
                        reasons.append(f"🔥 Volatility spike detected (+{atr_change_pct:.0f}%) - too risky to enter")
                    position_size_multiplier = min(position_size_multiplier, 0.5)  # ลด 50%

                # Moderate volatility increase 30-50%
                elif atr_change_pct > 30:
                    reasons.append(f"⚠️ Elevated volatility (+{atr_change_pct:.0f}%) - reduce position size")
                    position_size_multiplier = min(position_size_multiplier, 0.75)  # ลด 25%

        # 🆕 Veto 7: Overextension (ราคาวิ่งไปไกลเกินไป)
        if analysis_results:
            technical_analysis = analysis_results.get('technical_analysis', {})
            market_state = technical_analysis.get('market_state_analysis', {})
            overextension = market_state.get('overextension', {})

            is_overextended = overextension.get('is_overextended', False)
            severity = overextension.get('severity', 'NONE')
            distance_pct = overextension.get('distance_pct', 0)

            logger.debug(f"Veto check - Overextension: {is_overextended}, severity: {severity}, distance: {distance_pct:.1f}%")

            if is_overextended and severity == 'EXTREME':
                if current_score >= buy_threshold:  # Would be BUY (volatility-aware)
                    veto = True
                    adjusted_score = 4.5
                    forced_recommendation = 'HOLD'
                    reasons.append(f"📈 Price EXTREMELY overextended ({distance_pct:.1f}% above mean) - wait for pullback")

            elif is_overextended and severity == 'HIGH':
                if current_score >= 7.5:  # Would be STRONG BUY
                    adjusted_score = max(adjusted_score - 1.0, buy_threshold)  # Downgrade to BUY (volatility-aware)
                    reasons.append(f"⚠️ Price overextended ({distance_pct:.1f}%) - reduced target")

        # 🆕 Veto 8: Falling Knife (หุ้นตกต่อเนื่อง)
        if analysis_results:
            technical_analysis = analysis_results.get('technical_analysis', {})
            market_state = technical_analysis.get('market_state_analysis', {})
            falling_knife = market_state.get('falling_knife', {})

            is_falling_knife = falling_knife.get('is_falling_knife', False)
            risk_level = falling_knife.get('risk_level', 'NONE')
            fall_days = falling_knife.get('fall_days', 0)

            logger.debug(f"Veto check - Falling knife: {is_falling_knife}, risk: {risk_level}, days: {fall_days}")

            if is_falling_knife and risk_level in ['HIGH', 'EXTREME']:
                if current_score >= 5.0:  # Would be anything above SELL
                    veto = True
                    adjusted_score = min(adjusted_score, 3.5)
                    forced_recommendation = 'SELL' if current_score < 6.5 else 'HOLD'
                    reasons.append(f"🔪 Falling knife detected ({fall_days} consecutive down days) - don't catch it!")

            elif is_falling_knife and risk_level == 'MODERATE':
                if current_score >= 7.5:  # Would be STRONG BUY
                    adjusted_score = max(adjusted_score - 1.5, 4.5)
                    reasons.append(f"⚠️ Moderate falling knife ({fall_days} down days) - wait for stabilization")

        # 🆕 Veto 9: R:R Deterioration (สำหรับคนที่ถือหุ้นอยู่แล้ว)
        if analysis_results:
            # ตรวจสอบจาก risk_alerts ถ้ามี
            pass  # Will implement after integrating risk_alerts

        return {
            'veto': veto,
            'adjusted_score': adjusted_score,
            'forced_recommendation': forced_recommendation,
            'reasons': reasons,
            'position_size_multiplier': position_size_multiplier  # 🆕 ส่งค่า multiplier กลับไปด้วย
        }

    def _score_to_recommendation(self, score: float, volatility_class: str = 'LOW') -> str:
        """Convert score to recommendation (🆕 v6.0: Volatility-aware thresholds)"""
        # Get thresholds for the specific volatility class
        thresholds = self.recommendation_thresholds.get(volatility_class, self.default_thresholds)

        if score >= thresholds['STRONG_BUY']:
            return 'STRONG BUY'
        elif score >= thresholds['BUY']:
            return 'BUY'
        elif score >= thresholds['HOLD']:
            return 'HOLD'
        elif score >= thresholds['SELL']:
            return 'SELL'
        elif score >= thresholds['AVOID']:
            return 'AVOID'  # 🆕 Don't enter - risk too high
        else:
            return 'STRONG SELL'

    def _calculate_confidence(self, final_score: float, component_scores: List[float], volatility_class: str = 'LOW') -> str:
        """
        IMPROVED: Calculate confidence level based on:
        1. Agreement between components (std deviation)
        2. Distance from threshold boundaries
        3. Score consistency (how aligned are all components)
        4. Overall score strength

        FIXED v3.4: Adjusted thresholds to be achievable
        🆕 v6.0: Volatility-aware thresholds
        """
        # 1. Calculate agreement (standard deviation)
        std_dev = np.std(component_scores)

        # 2. Distance from nearest threshold
        thresholds_dict = self.recommendation_thresholds.get(volatility_class, self.default_thresholds)
        thresholds = sorted(thresholds_dict.values())
        min_distance = min(abs(final_score - t) for t in thresholds)

        # 3. Score consistency - normalize scores and check correlation
        # Components pointing in same direction = high consistency
        mean_score = np.mean(component_scores)
        consistency = sum(1 for s in component_scores if abs(s - mean_score) < 2.0) / len(component_scores)

        # 4. Overall score strength - extreme scores have more conviction
        score_strength = abs(final_score - 5.0) / 5.0  # 0 = neutral, 1 = very strong/weak

        # Calculate confidence score (0-1)
        conf_score = 0

        # Factor 1: Low std_dev = more agreement (40% max)
        if std_dev < 0.8:
            conf_score += 0.4  # Perfect agreement
        elif std_dev < 1.2:
            conf_score += 0.3  # Very good agreement
        elif std_dev < 1.8:
            conf_score += 0.2  # Good agreement
        elif std_dev < 2.5:
            conf_score += 0.1  # Fair agreement
        # else: 0 (poor agreement)

        # Factor 2: Far from threshold = more certain (30% max)
        # FIXED: More realistic distance thresholds
        if min_distance > 1.2:
            conf_score += 0.3  # Very far from threshold
        elif min_distance > 0.7:
            conf_score += 0.2  # Far from threshold
        elif min_distance > 0.4:
            conf_score += 0.1  # Moderate distance
        # else: 0 (too close to threshold)

        # Factor 3: High consistency (20% max)
        conf_score += consistency * 0.2

        # Factor 4: Strong scores = more conviction (10% max)
        conf_score += score_strength * 0.1

        # Convert to category (FIXED thresholds)
        if conf_score >= 0.70:  # Was 0.75 (unreachable)
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

    def _calculate_signal_integrity_index(self,
                                          component_scores: List[float],
                                          weights: Dict[str, float],
                                          final_recommendation: str) -> Dict[str, Any]:
        """
        Calculate Signal Integrity Index (SII) - measures signal consistency

        SII Formula:
        SII = (Component_Agreement × 0.5) + (Directional_Consistency × 0.3) + (Weight_Alignment × 0.2)

        Thresholds:
        - SII > 0.7 → BUY/SELL (High confidence, strong signal)
        - SII 0.4-0.7 → HOLD (Mixed signals, moderate confidence)
        - SII < 0.4 → AVOID (Conflicting signals, low confidence)

        Args:
            component_scores: List of component scores (0-10)
            weights: Component weights
            final_recommendation: Final recommendation (BUY/HOLD/SELL)

        Returns:
            Dictionary with SII score, interpretation, and details
        """
        # 1. COMPONENT AGREEMENT (50%)
        # Measures how much components agree with each other
        mean_score = np.mean(component_scores)
        std_dev = np.std(component_scores)

        # Lower std dev = higher agreement
        # Normalize: std_dev of 0 = 1.0, std_dev of 5 = 0.0
        component_agreement = max(0, 1.0 - (std_dev / 5.0))

        # 2. DIRECTIONAL CONSISTENCY (30%)
        # Measures if components point in same direction as final recommendation
        if final_recommendation in ['STRONG BUY', 'BUY']:
            # For BUY: count how many components > 6
            bullish_count = sum(1 for score in component_scores if score >= 6.0)
            directional_consistency = bullish_count / len(component_scores)
        elif final_recommendation in ['STRONG SELL', 'SELL']:
            # For SELL: count how many components < 4
            bearish_count = sum(1 for score in component_scores if score <= 4.0)
            directional_consistency = bearish_count / len(component_scores)
        else:  # HOLD
            # For HOLD: count how many components in neutral zone (4-6)
            neutral_count = sum(1 for score in component_scores if 4.0 <= score <= 6.0)
            directional_consistency = neutral_count / len(component_scores)

        # 3. WEIGHT ALIGNMENT (20%)
        # Check if highest-weighted components agree with recommendation
        component_names = list(weights.keys())
        sorted_by_weight = sorted(zip(component_names, component_scores, weights.values()),
                                 key=lambda x: x[2], reverse=True)

        # Check top 3 weighted components
        top_3 = sorted_by_weight[:3]
        aligned_count = 0

        for name, score, weight in top_3:
            if final_recommendation in ['STRONG BUY', 'BUY']:
                if score >= 6.0:
                    aligned_count += 1
            elif final_recommendation in ['STRONG SELL', 'SELL']:
                if score <= 4.0:
                    aligned_count += 1
            else:  # HOLD
                if 4.0 <= score <= 6.0:
                    aligned_count += 1

        weight_alignment = aligned_count / 3

        # Calculate final SII
        sii_score = (
            component_agreement * 0.5 +
            directional_consistency * 0.3 +
            weight_alignment * 0.2
        )

        # Determine SII interpretation
        if sii_score > 0.7:
            sii_interpretation = 'STRONG SIGNAL'
            sii_action = 'BUY/SELL'
            sii_quality = 'High confidence - All signals align'
            sii_color = '🟢'
        elif sii_score >= 0.4:
            sii_interpretation = 'MODERATE SIGNAL'
            sii_action = 'HOLD'
            sii_quality = 'Mixed signals - Wait for clarity'
            sii_color = '🟡'
        else:
            sii_interpretation = 'WEAK SIGNAL'
            sii_action = 'AVOID'
            sii_quality = 'Conflicting signals - High risk'
            sii_color = '🔴'

        logger.info(f"Signal Integrity Index (SII) = {sii_score:.2f}")
        logger.info(f"  Component Agreement (50%): {component_agreement:.2f}")
        logger.info(f"  Directional Consistency (30%): {directional_consistency:.2f}")
        logger.info(f"  Weight Alignment (20%): {weight_alignment:.2f}")
        logger.info(f"  → {sii_interpretation} ({sii_action})")

        return {
            'sii_score': round(sii_score, 2),
            'sii_percentage': round(sii_score * 100, 1),
            'interpretation': sii_interpretation,
            'recommended_action': sii_action,
            'quality': sii_quality,
            'color': sii_color,
            'components': {
                'component_agreement': round(component_agreement, 2),
                'directional_consistency': round(directional_consistency, 2),
                'weight_alignment': round(weight_alignment, 2)
            },
            'details': {
                'mean_score': round(mean_score, 2),
                'std_deviation': round(std_dev, 2),
                'component_count': len(component_scores),
                'aligned_components': int(directional_consistency * len(component_scores))
            }
        }

    # REMOVED: _calculate_realistic_rr() method
    # We now use the pre-calculated risk_reward_ratio from Market State entry price
    # to ensure consistency across all displays

    def _calculate_position_sizing(self, score: float, rr_ratio: float, confidence: str,
                                   position_size_multiplier: float = 1.0) -> Dict[str, Any]:
        """
        ENHANCED v4.0: Dynamic position sizing formula with regime/volatility adjustments
        position_size% = min((score / 10) * (R:R / 2) * multiplier, 10)

        Additional adjustments:
        - Confidence multiplier
        - 🆕 Market regime multiplier (CRISIS: 0.3x, BEAR: 0.6x)
        - 🆕 Volatility spike multiplier (spike +50%: 0.5x)
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

        # 🆕 Apply regime/volatility multiplier
        # This comes from veto_conditions and captures:
        # - Market regime (CRISIS: 0.3, BEAR: 0.6, BULL: 1.0)
        # - Volatility spike (High vol: 0.5-0.75)
        # - Multiple factors stack multiplicatively (e.g., CRISIS + high vol = 0.3 * 0.5 = 0.15)

        # Calculate final size
        final_size = base_size * conf_multiplier * position_size_multiplier * 100  # Convert to percentage

        # Apply caps
        final_size = max(0.5, min(final_size, 10.0))  # Min 0.5%, Max 10%

        # Conservative and aggressive variants
        conservative = max(0.5, final_size * 0.5)
        aggressive = min(final_size * 1.5, 15.0)

        # 🆕 Add warning if position size was reduced significantly
        size_warning = None
        if position_size_multiplier < 0.5:
            size_warning = f"⚠️ Position size reduced to {position_size_multiplier*100:.0f}% of normal due to market conditions"
        elif position_size_multiplier < 0.8:
            size_warning = f"⚠️ Position size reduced to {position_size_multiplier*100:.0f}% of normal"

        return {
            'recommended_percentage': round(final_size, 2),
            'conservative_percentage': round(conservative, 2),
            'aggressive_percentage': round(aggressive, 2),
            'rationale': f"Dynamic: (score={score:.1f}/10) * (R:R={rr_ratio:.2f}/2) * confidence={conf_multiplier:.1f} * regime/vol={position_size_multiplier:.2f}",
            'formula_used': 'position% = min((score/10) * (R:R/2) * confidence * multiplier, 10%)',
            'position_size_multiplier': position_size_multiplier,  # 🆕 Show the multiplier
            'size_warning': size_warning  # 🆕 Warning if significantly reduced
        }

    def _generate_detailed_reasoning(self,
                                    recommendation: str,
                                    component_scores: Dict[str, float],
                                    weights: Dict[str, float],
                                    price_change_analysis: Dict[str, Any],
                                    insider_data: Dict[str, Any],
                                    rr_ratio: float,
                                    veto_reasons: List[str],
                                    missing_data_warnings: List[str] = None) -> Dict[str, Any]:
        """Generate detailed reasoning for the recommendation (🆕 with data quality warnings)"""

        reasons_for = []
        reasons_against = []

        # 🆕 Add data quality warnings first (if any)
        if missing_data_warnings:
            for warning in missing_data_warnings:
                reasons_against.append(warning)

        # Technical
        if component_scores['technical'] >= 7:
            reasons_for.append(f"Strong technical signals (score: {component_scores['technical']:.1f}/10)")
        elif component_scores['technical'] <= 3:
            reasons_against.append(f"Weak technical setup (score: {component_scores['technical']:.1f}/10)")

        # Fundamental - 🆕 IMPROVED: Only show as "Poor" if not missing
        if component_scores['fundamental'] >= 7:
            reasons_for.append(f"Solid fundamentals (score: {component_scores['fundamental']:.1f}/10)")
        elif component_scores['fundamental'] <= 3 and weights.get('fundamental', 0) > 0:
            # Only add to reasons_against if fundamental weight > 0 (i.e., data exists and is genuinely poor)
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

        # Risk/Reward - Skip if veto already covers it (avoid duplicates)
        has_rr_veto = any('R:R ratio' in reason or 'risk/reward' in reason.lower() for reason in veto_reasons)
        if not has_rr_veto:
            if rr_ratio >= 2.0:
                reasons_for.append(f"Favorable risk/reward ratio ({rr_ratio:.2f}:1)")
            elif rr_ratio < 1.0:
                reasons_against.append(f"Unfavorable risk/reward ratio ({rr_ratio:.2f}:1)")

        # 🆕 Short Interest (v4.0)
        short_interest_score = component_scores.get('short_interest', 5.0)
        if short_interest_score >= 8.0:
            reasons_for.append(f"High short squeeze potential (score: {short_interest_score:.1f}/10)")
        elif short_interest_score >= 7.0:
            reasons_for.append(f"Moderate short squeeze potential (score: {short_interest_score:.1f}/10)")

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

    def _generate_final_verdict(self,
                                recommendation: str,
                                score: float,
                                confidence: str,
                                reasoning: Dict[str, Any],
                                rr_ratio: float,
                                veto_reasons: List[str]) -> Dict[str, Any]:
        """
        Generate clear and actionable Final Verdict - NEW v3.1

        Returns a structured verdict with:
        1. Verdict Level (STRONG / MODERATE / WEAK)
        2. Clear Action Summary (one-line instruction)
        3. Risk Warnings (if any critical concerns)
        4. Confidence Assessment (why confident or not)
        """

        # 1. Determine Verdict Level (strength of recommendation)
        conviction = reasoning.get('conviction_level', 'Moderate')
        reasons_for = reasoning.get('reasons_for', [])
        reasons_against = reasoning.get('reasons_against', [])

        # Calculate verdict strength
        if recommendation in ['STRONG BUY', 'STRONG SELL']:
            base_strength = 'STRONG'
        elif recommendation in ['BUY', 'SELL']:
            base_strength = 'MODERATE'
        else:  # HOLD
            base_strength = 'WEAK'

        # Adjust based on confidence and conviction
        if confidence == 'HIGH' and conviction in ['High', 'Very High']:
            verdict_level = 'STRONG'
        elif confidence == 'LOW' or len(reasons_against) > len(reasons_for):
            verdict_level = 'WEAK'
        else:
            verdict_level = base_strength

        # 2. Generate Clear Action Summary
        if recommendation in ['STRONG BUY', 'BUY']:
            if verdict_level == 'STRONG':
                action_summary = f"✅ STRONG BUY: เข้าซื้อได้เลย - สัญญาณชัดเจน (Score {score:.1f}/10, R:R {rr_ratio:.2f}:1)"
            elif verdict_level == 'MODERATE':
                action_summary = f"✅ BUY: เข้าซื้อได้ แต่ควรระวัง - สัญญาณปานกลาง (Score {score:.1f}/10)"
            else:
                action_summary = f"⚠️ WEAK BUY: พิจารณาเข้าซื้อ - สัญญาณอ่อน ควรรอยืนยันเพิ่ม (Score {score:.1f}/10)"

        elif recommendation in ['STRONG SELL', 'SELL']:
            if verdict_level == 'STRONG':
                action_summary = f"❌ STRONG SELL: ขายออกหรือเข้า Short - สัญญาณชัดเจน (Score {score:.1f}/10)"
            elif verdict_level == 'MODERATE':
                action_summary = f"❌ SELL: พิจารณาขายออก - สัญญาณปานกลาง (Score {score:.1f}/10)"
            else:
                action_summary = f"⚠️ WEAK SELL: พิจารณาขาย - สัญญาณอ่อน ควรรอยืนยันเพิ่ม (Score {score:.1f}/10)"

        else:  # HOLD
            if len(reasons_against) > 0:
                action_summary = f"⏸️ HOLD: รอดูต่อ - สัญญาณไม่ชัดเจน มีข้อกังวล (Score {score:.1f}/10)"
            else:
                action_summary = f"⏸️ HOLD: รอสัญญาณที่ดีกว่า - ยังไม่มี edge ชัดเจน (Score {score:.1f}/10)"

        # 3. Generate Risk Warnings
        risk_warnings = []

        # Critical risks from veto reasons
        if veto_reasons:
            risk_warnings.append({
                'level': 'CRITICAL',
                'icon': '🔴',
                'message': 'มีข้อจำกัดสำคัญ',
                'details': veto_reasons
            })

        # High-risk concerns from reasons_against
        critical_concerns = [r for r in reasons_against if any(word in r.lower() for word in ['poor', 'weak', 'unfavorable', 'negative'])]
        if critical_concerns:
            risk_warnings.append({
                'level': 'HIGH',
                'icon': '🟠',
                'message': 'มีปัจจัยเสี่ยงสูง',
                'details': critical_concerns[:2]
            })

        # Low R:R warning
        if rr_ratio < 1.5 and recommendation not in ['HOLD', 'SELL', 'STRONG SELL']:
            risk_warnings.append({
                'level': 'MODERATE',
                'icon': '🟡',
                'message': f'R:R ratio ต่ำกว่าที่แนะนำ ({rr_ratio:.2f}:1)',
                'details': [f'ควร R:R >= 1.5:1 สำหรับการซื้อ (ปัจจุบัน {rr_ratio:.2f}:1)']
            })

        # Low confidence warning
        if confidence == 'LOW':
            risk_warnings.append({
                'level': 'MODERATE',
                'icon': '🟡',
                'message': f'Confidence ต่ำ ({confidence})',
                'details': ['สัญญาณไม่ชัดเจน - indicators ขัดแย้งกัน']
            })

        # 4. Confidence Assessment (why confident or not)
        if confidence == 'HIGH':
            confidence_assessment = {
                'status': 'HIGH_CONFIDENCE',
                'icon': '🟢',
                'message': 'มีความเชื่อมั่นสูง',
                'reasons': reasons_for[:3]
            }
        elif confidence == 'MEDIUM':
            confidence_assessment = {
                'status': 'MODERATE_CONFIDENCE',
                'icon': '🟡',
                'message': 'ความเชื่อมั่นปานกลาง',
                'reasons': ['มี indicators ที่สนับสนุน แต่ยังมีบางส่วนขัดแย้ง'] + reasons_for[:2]
            }
        else:  # LOW
            confidence_assessment = {
                'status': 'LOW_CONFIDENCE',
                'icon': '🔴',
                'message': 'ความเชื่อมั่นต่ำ',
                'reasons': ['Indicators ขัดแย้งกัน', 'สัญญาณไม่ชัดเจน'] + (reasons_against[:2] if reasons_against else ['ควรรอสัญญาณที่ชัดเจนกว่า'])
            }

        # 5. Bottom Line (final one-sentence summary)
        if verdict_level == 'STRONG' and len(risk_warnings) == 0:
            bottom_line = f"🎯 สรุป: {recommendation} ด้วยความเชื่อมั่น{confidence} - เข้าได้เลย"
        elif verdict_level == 'MODERATE' or (verdict_level == 'STRONG' and len(risk_warnings) > 0):
            bottom_line = f"⚖️ สรุป: {recommendation} แต่มีข้อควรระวัง - พิจารณาก่อนตัดสินใจ"
        else:
            bottom_line = f"⏳ สรุป: {recommendation} แต่สัญญาณอ่อน - ควรรอยืนยันเพิ่มเติม"

        return {
            'verdict_level': verdict_level,  # STRONG / MODERATE / WEAK
            'action_summary': action_summary,  # One-line clear instruction
            'risk_warnings': risk_warnings,  # List of warnings (if any)
            'confidence_assessment': confidence_assessment,  # Why confident or not
            'bottom_line': bottom_line,  # Final one-sentence summary

            # Supporting data
            'recommendation': recommendation,
            'score': round(score, 1),
            'confidence': confidence,
            'conviction': conviction,
            'rr_ratio': round(rr_ratio, 2),

            # Counts
            'reasons_for_count': len(reasons_for),
            'reasons_against_count': len(reasons_against),
            'risk_warning_count': len(risk_warnings)
        }

    def _generate_price_prediction(
        self,
        current_price: float,
        target_price: float,
        stop_loss: float,
        analysis_results: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        🆕 v4.1: Generate Price Prediction & Bull Trap Warning

        Returns:
            {
                'intraday_forecast': {...},
                'multi_day_forecast': {...},
                'bull_trap_alert': {...},
                'trading_alert': {...}
            }
        """
        try:
            # Import here to avoid circular dependency
            from .price_prediction import IntradayPricePredictor, generate_trading_alert

            if not analysis_results:
                return {
                    'available': False,
                    'message': 'No analysis data available for prediction'
                }

            # Extract required data
            technical_analysis = analysis_results.get('technical_analysis', {})
            indicators = technical_analysis.get('indicators', {})
            market_state = technical_analysis.get('market_state_analysis', {})

            # Get support/resistance
            support_resistance = indicators.get('support_resistance', {})
            support = support_resistance.get('support_1', stop_loss)
            resistance = support_resistance.get('resistance_1', target_price)

            # Get ATR and volatility
            atr = indicators.get('atr', 0)
            if atr == 0:
                # Fallback: estimate from price range
                atr = (resistance - support) / 2

            # Get trend
            trend_info = technical_analysis.get('trend_analysis', {})
            trend = trend_info.get('trend', 'sideways')

            # Get volume ratio
            current_volume = indicators.get('current_volume', 0)
            volume_sma = indicators.get('volume_sma', 1)
            volume_ratio = current_volume / volume_sma if volume_sma > 0 else 1.0

            # Get volatility
            volatility = indicators.get('volatility', 2.0)

            # Get falling knife data
            falling_knife_data = market_state.get('falling_knife', {})

            # Get momentum indicators
            momentum_indicators = {
                'rsi': indicators.get('rsi'),
                'macd_line': indicators.get('macd_line'),
                'macd_signal': indicators.get('macd_signal'),
                'macd_histogram': indicators.get('macd_histogram')
            }

            # Get price change
            price_change_analysis = analysis_results.get('price_change_analysis', {})
            price_change_pct = price_change_analysis.get('change_percent', 0)

            # Get trend strength (ensure it's a float)
            trend_strength_raw = trend_info.get('trend_strength', 50)

            # Map string values to numeric
            strength_mapping = {
                'Very Strong': 90,
                'Strong': 75,
                'Moderate': 50,
                'Weak': 25,
                'Very Weak': 10
            }

            try:
                # Check if it's a string that needs mapping
                if isinstance(trend_strength_raw, str):
                    trend_strength = strength_mapping.get(trend_strength_raw, 50.0)
                else:
                    trend_strength = float(trend_strength_raw) if trend_strength_raw is not None else 50.0
            except (ValueError, TypeError):
                logger.warning(f"Invalid trend_strength value: {trend_strength_raw}, using default 50.0")
                trend_strength = 50.0

            # Initialize predictor
            predictor = IntradayPricePredictor()

            # 1. Predict intraday range
            intraday_forecast = predictor.predict_intraday_range(
                current_price=current_price,
                support=support,
                resistance=resistance,
                atr=atr,
                volatility=volatility,
                trend=trend,
                volume_ratio=volume_ratio
            )

            # 2. Detect bull trap
            bull_trap_alert = predictor.detect_bull_trap(
                current_price=current_price,
                trend=trend,
                falling_knife_data=falling_knife_data,
                momentum_indicators=momentum_indicators,
                price_change_pct=price_change_pct,
                volume_ratio=volume_ratio
            )

            # 3. Predict multi-day trend
            multi_day_forecast = predictor.predict_multi_day_trend(
                current_price=current_price,
                trend_strength=trend_strength,
                momentum_indicators=momentum_indicators,
                falling_knife_data=falling_knife_data,
                days_ahead=3
            )

            # 4. Generate trading alert
            trading_alert = generate_trading_alert(
                intraday_prediction=intraday_forecast,
                bull_trap_detection=bull_trap_alert,
                multi_day_trend=multi_day_forecast
            )

            # Log warnings
            if bull_trap_alert.get('is_bull_trap'):
                logger.warning(f"🚨 BULL TRAP DETECTED: {bull_trap_alert.get('trap_probability')}%")
                logger.warning(f"   {bull_trap_alert.get('warning_message')}")

            return {
                'available': True,
                'intraday_forecast': intraday_forecast,
                'bull_trap_alert': bull_trap_alert,
                'multi_day_forecast': multi_day_forecast,
                'trading_alert': trading_alert
            }

        except Exception as e:
            logger.error(f"Price prediction generation failed: {e}")
            return {
                'available': False,
                'error': str(e)
            }


def generate_action_plan(unified_rec: Dict[str, Any],
                         current_price: float,
                         entry: float,
                         stop: float,
                         targets: List[float],
                         symbol: str = '') -> Dict[str, Any]:
    """
    Generate clear actionable trading plan from unified recommendation

    Args:
        unified_rec: Unified recommendation dict
        current_price: Current stock price
        entry: Entry price
        stop: Stop loss price
        targets: List of target prices [target_1, target_2]
        symbol: Stock symbol (optional)

    Returns:
        Actionable trading plan with clear instructions
    """
    recommendation = unified_rec.get('recommendation', 'HOLD')
    score = unified_rec.get('score', 5.0)
    confidence = unified_rec.get('confidence', 'MEDIUM')
    confidence_pct = unified_rec.get('confidence_percentage', 50)
    rr_analysis = unified_rec.get('risk_reward_analysis', {})
    position_sizing = unified_rec.get('position_sizing', {})
    reasoning = unified_rec.get('reasoning', {})

    # Calculate entry zone (±1% around entry)
    entry_low = entry * 0.99
    entry_high = entry * 1.01

    # Calculate stop loss details
    stop_loss_pct = rr_analysis.get('risk_percent', 0)
    stop_loss_dollars = abs(entry - stop)

    # Calculate target details
    target_1 = targets[0] if len(targets) > 0 else entry * 1.03
    target_2 = targets[1] if len(targets) > 1 else entry * 1.06

    target_1_pct = ((target_1 - entry) / entry) * 100
    target_2_pct = ((target_2 - entry) / entry) * 100
    target_1_dollars = target_1 - entry
    target_2_dollars = target_2 - entry

    # Risk/Reward ratio
    rr_ratio = rr_analysis.get('ratio', 1.0)
    is_favorable = rr_analysis.get('is_favorable', False)

    # Position sizing
    recommended_size = position_sizing.get('recommended_percentage', 2.0)
    conservative_size = position_sizing.get('conservative_percentage', 1.0)
    aggressive_size = position_sizing.get('aggressive_percentage', 3.0)

    # Key reasons
    reasons_for = reasoning.get('reasons_for', [])
    reasons_against = reasoning.get('reasons_against', [])
    key_factors = reasoning.get('key_factors', [])

    # Generate action instruction based on recommendation
    if recommendation in ['STRONG BUY', 'BUY']:
        action_instruction = f"BUY {symbol}" if symbol else "BUY"
        action_detail = "เปิดสถานะซื้อ (Long Position)"
        stop_direction = "ต่ำกว่า"
        target_direction = "สูงกว่า"
        risk_color = "🔴"
        reward_color = "🟢"
    elif recommendation in ['STRONG SELL', 'SELL']:
        action_instruction = f"SELL {symbol}" if symbol else "SELL"
        action_detail = "เปิดสถานะขาย (Short Position) หรือออกจากฐานะ"
        stop_direction = "สูงกว่า"
        target_direction = "ต่ำกว่า"
        risk_color = "🟢"
        reward_color = "🔴"
    else:  # HOLD
        action_instruction = "HOLD / WAIT"
        action_detail = "รอสัญญาณที่ชัดเจนกว่า - ยังไม่มี edge"
        stop_direction = "ต่ำกว่า"
        target_direction = "สูงกว่า"
        risk_color = "🔴"
        reward_color = "🟢"

    # Format the action plan
    action_plan = {
        # Primary instruction
        'action': recommendation,
        'action_instruction': action_instruction,
        'action_detail': action_detail,
        'symbol': symbol,

        # Entry zone
        'entry_zone': f"${entry_low:.2f} - ${entry_high:.2f}",
        'entry_price': f"${entry:.2f}",
        'current_price': f"${current_price:.2f}",
        'entry_vs_current': f"{((entry - current_price) / current_price) * 100:+.2f}%",

        # Stop loss
        'stop_loss': f"${stop:.2f} ({stop_direction} entry {abs(stop_loss_pct):.1f}%)",
        'stop_loss_price': f"${stop:.2f}",
        'stop_loss_percent': f"{abs(stop_loss_pct):.1f}%",
        'stop_loss_dollars': f"{risk_color} -${stop_loss_dollars:.2f}",

        # Targets
        'target_1': f"${target_1:.2f} ({target_direction} entry +{abs(target_1_pct):.1f}%)",
        'target_1_price': f"${target_1:.2f}",
        'target_1_percent': f"+{abs(target_1_pct):.1f}%",
        'target_1_dollars': f"{reward_color} +${target_1_dollars:.2f}",

        'target_2': f"${target_2:.2f} ({target_direction} entry +{abs(target_2_pct):.1f}%)",
        'target_2_price': f"${target_2:.2f}",
        'target_2_percent': f"+{abs(target_2_pct):.1f}%",
        'target_2_dollars': f"{reward_color} +${target_2_dollars:.2f}",

        # Risk/Reward
        'risk_reward_ratio': f"{rr_ratio:.2f}:1",
        'rr_ratio_value': rr_ratio,
        'rr_is_favorable': is_favorable,
        'rr_quality': 'Good' if rr_ratio >= 2.0 else 'Fair' if rr_ratio >= 1.5 else 'Poor',

        # Position sizing
        'position_size': f"{recommended_size:.1f}% of portfolio",
        'position_size_value': recommended_size,
        'position_size_conservative': f"{conservative_size:.1f}%",
        'position_size_aggressive': f"{aggressive_size:.1f}%",

        # Confidence
        'confidence': confidence,
        'confidence_percentage': f"{confidence_pct}%",
        'confidence_value': confidence_pct,
        'score': f"{score:.1f}/10",
        'score_value': score,

        # Rationale
        'summary': reasoning.get('summary', ''),
        'reasons_for': reasons_for[:3],  # Top 3 reasons
        'reasons_against': reasons_against[:3],  # Top 3 concerns
        'key_factors': key_factors,

        # Exit strategy
        'exit_strategy': {
            'partial_exit_1': f"ขายออก 50% ที่ Target 1 (${target_1:.2f})",
            'partial_exit_2': f"ขายออก 50% ที่ Target 2 (${target_2:.2f})",
            'stop_loss': f"ตัดขาดทุนที่ ${stop:.2f} (ไม่มีข้อยกเว้น)",
            'trailing_stop': f"ใช้ Trailing Stop หลังราคาผ่าน Target 1"
        },

        # Timing
        'time_horizon': unified_rec.get('time_horizon', 'short'),
        'timeframe': 'Days to weeks' if unified_rec.get('time_horizon', 'short') == 'short' else 'Weeks to months' if unified_rec.get('time_horizon') == 'medium' else 'Months to years',

        # Checklist
        'pre_trade_checklist': [
            f"✓ R:R ratio = {rr_ratio:.2f}:1 {'(Good)' if is_favorable else '(Review)'}",
            f"✓ Position size = {recommended_size:.1f}% of portfolio",
            f"✓ Stop loss set at ${stop:.2f}",
            f"✓ Confidence level = {confidence} ({confidence_pct}%)",
            f"✓ Account for commissions and slippage"
        ]
    }

    return action_plan


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

    # ===== FIXED: Use Market State entry price for R:R calculation =====
    # Extract Market State entry price from technical analysis
    market_state_analysis = technical_analysis.get('market_state_analysis', {})
    strategy_recommendation = market_state_analysis.get('strategy', {})
    trading_plan = strategy_recommendation.get('trading_plan', {})

    # 🆕 v5.0 + v5.1: Extract ALL intelligent features from trading_plan
    # Immediate Entry Logic (v5.1)
    immediate_entry_info = {
        'immediate_entry': trading_plan.get('immediate_entry', False),
        'confidence': trading_plan.get('immediate_entry_confidence', 0),
        'reasons': trading_plan.get('immediate_entry_reasons', []),
        'action': trading_plan.get('entry_action', 'WAIT_FOR_PULLBACK')
    }

    # Multiple Entry Levels (v5.0 - Fibonacci Retracement)
    entry_levels = {
        'aggressive': trading_plan.get('entry_aggressive'),
        'moderate': trading_plan.get('entry_moderate'),
        'conservative': trading_plan.get('entry_conservative'),
        'recommended': trading_plan.get('entry_price'),
        'method': trading_plan.get('entry_method', 'N/A'),
        'entry_reason': trading_plan.get('entry_reason', '')
    }

    # Multiple TP Levels (v5.0 - Fibonacci Extension)
    tp_levels = {
        'tp1': trading_plan.get('tp1'),
        'tp2': trading_plan.get('tp2'),
        'tp3': trading_plan.get('tp3'),
        'recommended': trading_plan.get('take_profit'),
        'method': trading_plan.get('tp_method', 'N/A')
    }

    # Stop Loss Details (v5.0 - Structure-based)
    sl_details = {
        'value': trading_plan.get('stop_loss'),
        'method': trading_plan.get('sl_method', 'N/A'),
        'swing_low': trading_plan.get('swing_low'),
        'risk_pct': trading_plan.get('risk_pct', 0)
    }

    # Swing Points (v5.0)
    swing_points = {
        'swing_high': trading_plan.get('swing_high'),
        'swing_low': trading_plan.get('swing_low')
    }

    # Volatility Classification (v6.0)
    volatility_class = trading_plan.get('volatility_class', 'MEDIUM')
    atr_pct = trading_plan.get('atr_pct', 0)

    logger.info(f"🆕 Extracted v5.0 + v5.1 features:")
    logger.info(f"  Volatility Class: {volatility_class} (ATR: {atr_pct:.2f}%)")
    logger.info(f"  Immediate Entry: {immediate_entry_info['immediate_entry']} (confidence: {immediate_entry_info['confidence']}%)")
    logger.info(f"  Entry Method: {entry_levels['method']}")
    logger.info(f"  TP Method: {tp_levels['method']}")
    logger.info(f"  SL Method: {sl_details['method']}")

    # Get entry range from Market State
    entry_range = trading_plan.get('entry_range', [current_price * 0.995, current_price * 1.005])
    entry_price = sum(entry_range) / 2 if entry_range and len(entry_range) == 2 else current_price

    # Use Market State targets if available (more accurate than generic targets)
    market_state_tp = trading_plan.get('take_profit')
    market_state_sl = trading_plan.get('stop_loss')

    if market_state_tp and market_state_sl:
        # Use Market State values (preferred - most accurate)
        logger.info(f"✅ Using Market State trading plan: Entry=${entry_price:.2f}, TP=${market_state_tp:.2f}, SL=${market_state_sl:.2f}")
        target_price = float(market_state_tp)
        stop_loss = float(market_state_sl)
    else:
        # Fallback to generic values
        logger.warning(f"⚠️ Market State trading plan not available, using generic values")
        entry_price = float(current_price)

    # Calculate R:R ratio using ENTRY PRICE (not current price!)
    try:
        risk = abs(float(entry_price) - float(stop_loss))
        reward = abs(float(target_price) - float(entry_price))
        rr_ratio = float(reward / risk) if risk > 0 else 0.0
        logger.info(f"📊 R/R Calculation: Risk=${risk:.2f} ({((risk/entry_price)*100):.1f}%), Reward=${reward:.2f} ({((reward/entry_price)*100):.1f}%), R/R={rr_ratio:.2f}:1")
    except (TypeError, ValueError) as e:
        # Debug logging
        logger.error(f"Type conversion error in R:R calculation:")
        logger.error(f"  entry_price: {entry_price} (type: {type(entry_price)})")
        logger.error(f"  target_price: {target_price} (type: {type(target_price)})")
        logger.error(f"  stop_loss: {stop_loss} (type: {type(stop_loss)})")
        logger.error(f"  Error: {e}")
        raise

    # ===== GET TIME HORIZON FROM analysis_results (CRITICAL FIX!) =====
    # Extract time_horizon from performance_expectations which contains the correct value from analyze_stock()
    performance_expectations = analysis_results.get('performance_expectations', {})
    time_horizon = performance_expectations.get('time_horizon', analysis_results.get('time_horizon', 'short'))
    logger.info(f"✅ Extracted time_horizon from performance_expectations: {time_horizon}")

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
        volatility_class=volatility_class,  # v6.0: Volatility-aware thresholds
        analysis_results=analysis_results,  # NEW: Pass full analysis for momentum scoring
        # 🆕 v5.0 + v5.1: Pass intelligent features
        immediate_entry_info=immediate_entry_info,
        entry_levels=entry_levels,
        tp_levels=tp_levels,
        sl_details=sl_details,
        swing_points=swing_points
    )


def generate_multi_timeframe_analysis(analysis_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate recommendations for all 3 timeframes (SHORT/MEDIUM/LONG) - NEW v3.0

    Returns multi-timeframe analysis with warnings if timeframes don't align.
    Used for "แบบที่ 3" - show selected timeframe + warnings for others.

    Args:
        analysis_results: Full analysis results

    Returns:
        {
            'short': {...},    # Recommendation for short-term
            'medium': {...},   # Recommendation for medium-term
            'long': {...},     # Recommendation for long-term
            'selected': 'short',  # Which one user selected
            'alignment': {
                'all_aligned': False,
                'warnings': [...],
                'summary': '...'
            }
        }
    """
    engine = UnifiedRecommendationEngine()

    # Extract common data (same for all timeframes)
    technical_analysis = analysis_results.get('technical_analysis', {})
    fundamental_analysis = analysis_results.get('fundamental_analysis', {})

    technical_score = technical_analysis.get('technical_score', 5.0)
    if isinstance(technical_score, dict):
        technical_score = technical_score.get('total_score', 5.0)

    fundamental_score = fundamental_analysis.get('overall_score', 5.0)
    price_change_analysis = analysis_results.get('price_change_analysis', {})
    insider_data = analysis_results.get('insider_institutional', {})

    # Get prices
    current_price = float(analysis_results.get('current_price', 100.0))
    suggested_targets = analysis_results.get('suggested_targets', [])
    suggested_stop_loss = analysis_results.get('suggested_stop_loss')

    target_price = float(suggested_targets[0]) if suggested_targets else current_price * 1.05
    stop_loss = float(suggested_stop_loss) if suggested_stop_loss else current_price * 0.95

    # Calculate R/R ratio (same for all)
    market_state_analysis = technical_analysis.get('market_state_analysis', {})
    trading_plan = market_state_analysis.get('strategy', {}).get('trading_plan', {})
    entry_range = trading_plan.get('entry_range', [current_price * 0.995, current_price * 1.005])
    entry_price = sum(entry_range) / 2 if entry_range and len(entry_range) == 2 else current_price

    risk = abs(entry_price - stop_loss)
    reward = abs(target_price - entry_price)
    rr_ratio = reward / risk if risk > 0 else 0.0

    # Get selected timeframe
    performance_expectations = analysis_results.get('performance_expectations', {})
    selected_timeframe = performance_expectations.get('time_horizon', 'short')

    # Generate recommendations for ALL 3 timeframes
    recommendations = {}

    logger.info(f"🔍 Generating Multi-Timeframe Analysis...")
    logger.info(f"  Base Scores: Tech={technical_score:.1f}, Fund={fundamental_score:.1f}, R/R={rr_ratio:.2f}")

    for horizon in ['short', 'medium', 'long']:
        rec = engine.generate_unified_recommendation(
            technical_score=technical_score,
            fundamental_score=fundamental_score,
            price_change_analysis=price_change_analysis,
            insider_data=insider_data,
            risk_reward_ratio=rr_ratio,
            current_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            time_horizon=horizon,
            analysis_results=analysis_results
        )

        # DEBUG: Log each timeframe result
        logger.info(f"  {horizon.upper()}: {rec['recommendation']} {rec['score']:.1f}/10 ({rec['confidence']})")

        recommendations[horizon] = rec

    # Analyze alignment and generate warnings
    alignment_analysis = _analyze_timeframe_alignment(
        recommendations,
        selected_timeframe
    )

    return {
        'short': recommendations['short'],
        'medium': recommendations['medium'],
        'long': recommendations['long'],
        'selected': selected_timeframe,
        'alignment': alignment_analysis
    }


def _analyze_timeframe_alignment(recommendations: Dict[str, Dict], selected: str) -> Dict[str, Any]:
    """
    Analyze if timeframes are aligned or conflicting

    Returns warnings for timeframes that differ from selected one.
    """
    selected_rec = recommendations[selected]
    selected_action = selected_rec['recommendation']
    selected_score = selected_rec['score']

    warnings = []
    all_aligned = True

    # Check other timeframes
    for horizon in ['short', 'medium', 'long']:
        if horizon == selected:
            continue

        other_rec = recommendations[horizon]
        other_action = other_rec['recommendation']
        other_score = other_rec['score']

        # Check if different recommendation
        if other_action != selected_action:
            all_aligned = False

            # Generate warning message
            horizon_thai = {
                'short': 'ระยะสั้น (1-14 วัน)',
                'medium': 'ระยะกลาง (1-3 เดือน)',
                'long': 'ระยะยาว (6-12 เดือน)'
            }

            # Determine severity
            action_diff = abs(_action_to_score(other_action) - _action_to_score(selected_action))

            if action_diff >= 2:  # BUY vs SELL
                severity = 'critical'
                icon = '🔴'
                message = f"{horizon_thai[horizon]}: {other_action} ({other_score:.1f}/10)"
                reason = _get_alignment_reason(horizon, other_action, other_rec)
                warnings.append({
                    'timeframe': horizon,
                    'severity': severity,
                    'icon': icon,
                    'message': message,
                    'reason': reason
                })
            elif action_diff == 1:  # BUY vs HOLD or HOLD vs SELL
                severity = 'warning'
                icon = '🟡'
                message = f"{horizon_thai[horizon]}: {other_action} ({other_score:.1f}/10)"
                reason = _get_alignment_reason(horizon, other_action, other_rec)
                warnings.append({
                    'timeframe': horizon,
                    'severity': severity,
                    'icon': icon,
                    'message': message,
                    'reason': reason
                })

    # Generate summary
    if all_aligned:
        summary = f"✅ สัญญาณสอดคล้องกันทุก timeframe - {selected_action} signal ชัดเจน"
    elif len(warnings) == 1:
        summary = f"⚠️ หุ้นนี้เหมาะกับ {_get_thai_timeframe(selected)} เป็นหลัก"
    else:
        summary = f"⚠️ คำเตือน: สัญญาณแตกต่างกันในแต่ละ timeframe"

    return {
        'all_aligned': all_aligned,
        'warnings': warnings,
        'summary': summary,
        'warning_count': len(warnings)
    }


def _action_to_score(action: str) -> int:
    """Convert action to numeric score for comparison"""
    mapping = {
        'STRONG BUY': 2,
        'BUY': 1,
        'HOLD': 0,
        'SELL': -1,
        'STRONG SELL': -2
    }
    return mapping.get(action, 0)


def _get_thai_timeframe(horizon: str) -> str:
    """Get Thai name for timeframe"""
    mapping = {
        'short': 'ระยะสั้น',
        'medium': 'ระยะกลาง',
        'long': 'ระยะยาว'
    }
    return mapping.get(horizon, horizon)


def _get_alignment_reason(horizon: str, action: str, recommendation: Dict) -> str:
    """Get reason why this timeframe has different recommendation"""
    component_scores = recommendation.get('component_scores', {})

    if horizon == 'medium':
        # Medium-term focuses on fundamentals
        fund_score = component_scores.get('fundamental', 5.0)
        if action in ['SELL', 'STRONG SELL']:
            return f"Fundamentals อ่อนแรง ({fund_score:.1f}/10) - ไม่เหมาะถือกลางถึงยาว"
        elif action == 'HOLD':
            return f"Fundamentals ปานกลาง ({fund_score:.1f}/10) - รอดูต่อก่อน"
        else:
            return f"Fundamentals ดี ({fund_score:.1f}/10)"

    elif horizon == 'long':
        # Long-term focuses on fundamentals + insider
        fund_score = component_scores.get('fundamental', 5.0)
        insider_score = component_scores.get('insider', 5.0)

        if action in ['SELL', 'STRONG SELL']:
            return f"Fundamentals อ่อน ({fund_score:.1f}/10) และ Insider ไม่สนับสนุน - ไม่แนะนำถือยาว"
        elif action == 'HOLD':
            return f"Fundamentals ปานกลาง ({fund_score:.1f}/10) - ยังไม่เหมาะลงทุนยาว"
        else:
            return f"Fundamentals แข็งแรง ({fund_score:.1f}/10)"

    else:  # short
        # Short-term focuses on technicals + momentum
        tech_score = component_scores.get('technical', 5.0)
        mom_score = component_scores.get('momentum', 5.0)

        if action in ['SELL', 'STRONG SELL']:
            return f"Technicals อ่อน ({tech_score:.1f}/10) + Momentum ลง ({mom_score:.1f}/10)"
        elif action == 'HOLD':
            return f"Technicals ปานกลาง ({tech_score:.1f}/10) - รอ momentum"
        else:
            return f"Technicals + Momentum แข็งแรง"
