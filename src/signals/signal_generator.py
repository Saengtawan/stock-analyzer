"""
Signal Generator - Combines fundamental and technical analysis
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger

from analysis.fundamental.fundamental_analyzer import FundamentalAnalyzer
from analysis.technical.technical_analyzer import TechnicalAnalyzer


class SignalGenerator:
    """Generate trading signals by combining fundamental and technical analysis"""

    def __init__(self,
                 fundamental_analyzer: FundamentalAnalyzer,
                 technical_analyzer: TechnicalAnalyzer,
                 time_horizon: str = "medium",
                 config: Dict[str, Any] = None):
        """
        Initialize signal generator

        Args:
            fundamental_analyzer: Fundamental analysis engine
            technical_analyzer: Technical analysis engine
            time_horizon: Investment time horizon ('short', 'medium', 'long')
            config: Configuration dictionary
        """
        self.fundamental = fundamental_analyzer
        self.technical = technical_analyzer
        self.time_horizon = time_horizon
        self.config = config or {}

        # Weight configuration based on time horizon
        self.weights = self._get_weights(time_horizon)

    def generate_signals(self) -> Dict[str, Any]:
        """
        Generate comprehensive trading signals

        Returns:
            Dictionary containing all signals and recommendations
        """
        logger.info("Generating comprehensive trading signals")

        try:
            # Get fundamental analysis
            fundamental_results = self.fundamental.analyze()

            # Get technical analysis
            technical_results = self.technical.analyze()

            # Calculate confluence signals
            confluence_signals = self._calculate_confluence_signals(
                fundamental_results, technical_results
            )

            # Calculate final score
            final_score = self._calculate_final_score(
                fundamental_results.get('fundamental_score', {}),
                technical_results.get('technical_score', {}),
                confluence_signals
            )

            # Generate recommendation
            recommendation = self._generate_recommendation(final_score, confluence_signals)

            # Calculate entry/exit points
            entry_exit = self._calculate_entry_exit_points(
                technical_results, fundamental_results
            )

            # Risk assessment
            risk_assessment = self._assess_combined_risk(
                fundamental_results, technical_results
            )

            # Generate insights
            insights = self._generate_insights(
                fundamental_results, technical_results, confluence_signals
            )

            return {
                'symbol': self.fundamental.symbol,
                'analysis_date': datetime.now().isoformat(),
                'time_horizon': self.time_horizon,

                # Individual analysis results
                'fundamental_analysis': fundamental_results,
                'technical_analysis': technical_results,

                # Combined results
                'confluence_signals': confluence_signals,
                'final_score': final_score,
                'recommendation': recommendation,
                'entry_exit_points': entry_exit,
                'risk_assessment': risk_assessment,

                # Insights and summary
                'key_insights': insights,
                'signal_strength': self._calculate_signal_strength(confluence_signals),
                'confidence_level': self._calculate_confidence_level(final_score, confluence_signals)
            }

        except Exception as e:
            logger.error(f"Signal generation failed: {e}")
            return {
                'symbol': getattr(self.fundamental, 'symbol', 'Unknown'),
                'error': str(e),
                'recommendation': 'HOLD',
                'final_score': {'total_score': 5.0}
            }

    def _get_weights(self, time_horizon: str) -> Dict[str, float]:
        """Get analysis weights based on time horizon"""
        weight_configs = {
            'short': {  # 1-14 days
                'fundamental_weight': 0.2,
                'technical_weight': 0.8
            },
            'medium': {  # 1-6 months
                'fundamental_weight': 0.5,
                'technical_weight': 0.5
            },
            'long': {  # 6+ months
                'fundamental_weight': 0.7,
                'technical_weight': 0.3
            }
        }

        return weight_configs.get(time_horizon, weight_configs['medium'])

    def _calculate_confluence_signals(self,
                                    fundamental_results: Dict[str, Any],
                                    technical_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate confluence between fundamental and technical signals"""
        confluence = {}

        # Extract scores
        fund_score = fundamental_results.get('fundamental_score', {}).get('total_score', 5.0)
        tech_score = technical_results.get('technical_score', {}).get('total_score', 5.0)

        # Extract recommendations
        fund_rec = fundamental_results.get('recommendation', 'Hold')
        tech_rec = technical_results.get('recommendation', 'Hold')

        # Signal alignment
        confluence['score_alignment'] = self._assess_score_alignment(fund_score, tech_score)
        confluence['recommendation_alignment'] = self._assess_recommendation_alignment(fund_rec, tech_rec)

        # Confluence strength
        confluence['confluence_strength'] = self._calculate_confluence_strength(
            fund_score, tech_score, fund_rec, tech_rec
        )

        # Conflicting signals
        confluence['conflicts'] = self._identify_conflicts(fundamental_results, technical_results)

        # Supporting factors
        confluence['supporting_factors'] = self._identify_supporting_factors(
            fundamental_results, technical_results
        )

        return confluence

    def _assess_score_alignment(self, fund_score: float, tech_score: float) -> Dict[str, Any]:
        """Assess alignment between fundamental and technical scores"""
        score_diff = abs(fund_score - tech_score)

        if score_diff <= 1.0:
            alignment = "Strong"
        elif score_diff <= 2.0:
            alignment = "Moderate"
        else:
            alignment = "Weak"

        return {
            'alignment': alignment,
            'fundamental_score': fund_score,
            'technical_score': tech_score,
            'score_difference': score_diff
        }

    def _assess_recommendation_alignment(self, fund_rec: str, tech_rec: str) -> Dict[str, Any]:
        """Assess alignment between recommendations"""
        # Convert recommendations to numerical values for comparison
        rec_values = {
            'Strong Sell': 1,
            'Sell': 2,
            'Hold': 3,
            'Buy': 4,
            'Strong Buy': 5
        }

        fund_val = rec_values.get(fund_rec, 3)
        tech_val = rec_values.get(tech_rec, 3)

        diff = abs(fund_val - tech_val)

        if diff == 0:
            alignment = "Perfect"
        elif diff == 1:
            alignment = "Strong"
        elif diff == 2:
            alignment = "Moderate"
        else:
            alignment = "Conflicting"

        return {
            'alignment': alignment,
            'fundamental_recommendation': fund_rec,
            'technical_recommendation': tech_rec,
            'recommendation_difference': diff
        }

    def _calculate_confluence_strength(self,
                                     fund_score: float,
                                     tech_score: float,
                                     fund_rec: str,
                                     tech_rec: str) -> str:
        """Calculate overall confluence strength"""
        # Score confluence
        score_diff = abs(fund_score - tech_score)
        score_confluence = 1.0 - (score_diff / 10.0)  # Normalize to 0-1

        # Recommendation confluence
        rec_values = {'Strong Sell': 1, 'Sell': 2, 'Hold': 3, 'Buy': 4, 'Strong Buy': 5}
        fund_val = rec_values.get(fund_rec, 3)
        tech_val = rec_values.get(tech_rec, 3)
        rec_diff = abs(fund_val - tech_val)
        rec_confluence = 1.0 - (rec_diff / 4.0)  # Normalize to 0-1

        # Overall confluence
        overall_confluence = (score_confluence + rec_confluence) / 2

        if overall_confluence >= 0.8:
            return "Very Strong"
        elif overall_confluence >= 0.6:
            return "Strong"
        elif overall_confluence >= 0.4:
            return "Moderate"
        else:
            return "Weak"

    def _identify_conflicts(self,
                           fundamental_results: Dict[str, Any],
                           technical_results: Dict[str, Any]) -> List[str]:
        """Identify conflicts between fundamental and technical analysis"""
        conflicts = []

        fund_rec = fundamental_results.get('recommendation', 'Hold')
        tech_rec = technical_results.get('recommendation', 'Hold')

        # Major recommendation conflicts
        if fund_rec in ['Strong Buy', 'Buy'] and tech_rec in ['Strong Sell', 'Sell']:
            conflicts.append("Fundamental analysis suggests buying while technical suggests selling")
        elif fund_rec in ['Strong Sell', 'Sell'] and tech_rec in ['Strong Buy', 'Buy']:
            conflicts.append("Technical analysis suggests buying while fundamental suggests selling")

        # DCF vs Technical price levels
        dcf_value = fundamental_results.get('dcf_valuation', {}).get('intrinsic_value_per_share')
        current_price = fundamental_results.get('current_price', 0)
        tech_resistance = technical_results.get('support_resistance', {}).get('resistance_1')

        if dcf_value and tech_resistance and current_price:
            if dcf_value > current_price * 1.2 and current_price >= tech_resistance * 0.98:
                conflicts.append("DCF suggests undervaluation but price is at technical resistance")

        return conflicts

    def _identify_supporting_factors(self,
                                   fundamental_results: Dict[str, Any],
                                   technical_results: Dict[str, Any]) -> List[str]:
        """Identify factors that support the combined signal"""
        supporting_factors = []

        # Both analyses agree on direction
        fund_rec = fundamental_results.get('recommendation', 'Hold')
        tech_rec = technical_results.get('recommendation', 'Hold')

        if fund_rec == tech_rec and fund_rec != 'Hold':
            supporting_factors.append(f"Both fundamental and technical analysis recommend {fund_rec}")

        # High individual scores
        fund_score = fundamental_results.get('fundamental_score', {}).get('total_score', 0)
        tech_score = technical_results.get('technical_score', {}).get('total_score', 0)

        if fund_score >= 8.0:
            supporting_factors.append("Strong fundamental analysis score")
        if tech_score >= 8.0:
            supporting_factors.append("Strong technical analysis score")

        # Specific supporting factors
        key_signals = technical_results.get('key_signals', [])
        for signal in key_signals:
            if 'Strong' in signal:
                supporting_factors.append(f"Technical: {signal}")

        fund_strengths = fundamental_results.get('key_strengths', [])
        for strength in fund_strengths[:2]:  # Top 2 strengths
            supporting_factors.append(f"Fundamental: {strength}")

        return supporting_factors

    def _calculate_overvaluation_penalty(self, fundamental_score: Dict[str, Any]) -> float:
        """Calculate penalty for overvalued stocks in long-term horizon"""
        penalty = 0

        # Extract valuation score (should be low for overvalued stocks)
        component_scores = fundamental_score.get('component_scores', {})
        valuation_score = component_scores.get('valuation', 1.0)  # 0-2 scale

        # If valuation score is very low (< 0.5), apply heavy penalty
        if valuation_score < 0.5:
            penalty += 3.0  # Heavy penalty for severely overvalued
        elif valuation_score < 1.0:
            penalty += 2.0  # Moderate penalty for overvalued
        elif valuation_score < 1.5:
            penalty += 1.0  # Light penalty for slightly overvalued

        # Additional penalty for poor overall fundamental score
        fund_total = fundamental_score.get('total_score', 5.0)
        if fund_total < 3.0:
            penalty += 1.5  # Additional penalty for poor fundamentals
        elif fund_total < 4.0:
            penalty += 1.0

        return penalty

    def _calculate_final_score(self,
                              fundamental_score: Dict[str, Any],
                              technical_score: Dict[str, Any],
                              confluence_signals: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate final combined score"""
        fund_score = fundamental_score.get('total_score', 5.0)
        tech_score = technical_score.get('total_score', 5.0)

        # Apply time horizon weights
        weighted_score = (
            fund_score * self.weights['fundamental_weight'] +
            tech_score * self.weights['technical_weight']
        )

        # Special penalty for overvalued stocks in long-term horizon
        if self.time_horizon == 'long':
            overvaluation_penalty = self._calculate_overvaluation_penalty(fundamental_score)
            weighted_score = max(weighted_score - overvaluation_penalty, 0)

        # Confluence adjustment
        confluence_strength = confluence_signals.get('confluence_strength', 'Moderate')
        if confluence_strength == 'Very Strong':
            confluence_multiplier = 1.1
        elif confluence_strength == 'Strong':
            confluence_multiplier = 1.05
        elif confluence_strength == 'Moderate':
            confluence_multiplier = 1.0
        else:
            confluence_multiplier = 0.95

        final_score = min(weighted_score * confluence_multiplier, 10.0)

        return {
            'total_score': final_score,
            'fundamental_contribution': fund_score * self.weights['fundamental_weight'],
            'technical_contribution': tech_score * self.weights['technical_weight'],
            'confluence_adjustment': confluence_multiplier,
            'max_score': 10.0,
            'rating': self._get_score_rating(final_score)
        }

    def _generate_recommendation(self,
                               final_score: Dict[str, Any],
                               confluence_signals: Dict[str, Any]) -> Dict[str, Any]:
        """Generate final recommendation"""
        score = final_score['total_score']

        # Base recommendation from score
        if score >= 8.5:
            base_rec = "Strong Buy"
        elif score >= 7.0:
            base_rec = "Buy"
        elif score >= 5.5:
            base_rec = "Hold"
        elif score >= 4.0:
            base_rec = "Sell"
        else:
            base_rec = "Strong Sell"

        # Special adjustment for long-term overvalued stocks
        if self.time_horizon == 'long' and hasattr(self, 'fundamental') and self.fundamental:
            fund_results = getattr(self.fundamental, 'last_results', {})
            fund_score = fund_results.get('fundamental_score', {})
            component_scores = fund_score.get('component_scores', {})
            valuation_score = component_scores.get('valuation', 1.0)

            # If severely overvalued in long-term, downgrade recommendation
            if valuation_score < 0.5 and base_rec in ["Strong Buy", "Buy"]:
                base_rec = "Hold"
            elif valuation_score < 1.0 and base_rec == "Strong Buy":
                base_rec = "Buy"

        # Adjust for confluence
        confluence_strength = confluence_signals.get('confluence_strength', 'Moderate')
        conflicts = confluence_signals.get('conflicts', [])

        if conflicts and len(conflicts) > 1:
            # Multiple conflicts - downgrade recommendation
            if base_rec == "Strong Buy":
                adjusted_rec = "Buy"
            elif base_rec == "Strong Sell":
                adjusted_rec = "Sell"
            else:
                adjusted_rec = "Hold"
        elif confluence_strength in ['Very Strong', 'Strong']:
            # Strong confluence - keep recommendation
            adjusted_rec = base_rec
        else:
            # Moderate/weak confluence - consider hold
            if base_rec in ["Strong Buy", "Strong Sell"]:
                adjusted_rec = base_rec.replace("Strong ", "")
            else:
                adjusted_rec = base_rec

        return {
            'recommendation': adjusted_rec,
            'base_recommendation': base_rec,
            'confidence': self._calculate_confidence_level(final_score, confluence_signals),
            'reasoning': self._generate_recommendation_reasoning(
                final_score, confluence_signals, adjusted_rec
            )
        }

    def _calculate_entry_exit_points(self,
                                   technical_results: Dict[str, Any],
                                   fundamental_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate optimal entry and exit points"""
        tech_entry_exit = technical_results.get('entry_exit_points', {})
        dcf_value = fundamental_results.get('dcf_valuation', {}).get('intrinsic_value_per_share')
        current_price = fundamental_results.get('current_price', 0)

        # Entry points
        tech_long_entry = tech_entry_exit.get('long_entry', current_price * 0.98)

        # Combine with fundamental value
        if dcf_value and dcf_value > current_price:
            # Stock is undervalued, can enter at higher price
            optimal_entry = min(dcf_value * 0.95, tech_long_entry * 1.02)
        else:
            # Use technical entry
            optimal_entry = tech_long_entry

        # Exit points
        tech_tp1 = tech_entry_exit.get('long_take_profit_1', current_price * 1.05)
        tech_tp2 = tech_entry_exit.get('long_take_profit_2', current_price * 1.10)

        # Fundamental target
        fund_target = dcf_value if dcf_value else current_price * 1.15

        return {
            'optimal_entry': optimal_entry,
            'stop_loss': tech_entry_exit.get('long_stop_loss', optimal_entry * 0.95),
            'take_profit_1': tech_tp1,
            'take_profit_2': max(tech_tp2, fund_target * 0.9),
            'fundamental_target': fund_target,
            'risk_reward_ratio': self._calculate_risk_reward_ratio(
                optimal_entry,
                tech_entry_exit.get('long_stop_loss', optimal_entry * 0.95),
                tech_tp1
            )
        }

    def _assess_combined_risk(self,
                            fundamental_results: Dict[str, Any],
                            technical_results: Dict[str, Any]) -> Dict[str, Any]:
        """Assess combined risk from both analyses"""
        fund_risk = fundamental_results.get('risk_assessment', {})
        tech_risk = technical_results.get('risk_assessment', {})

        # Overall risk level
        risk_factors = []

        # Financial risks
        if fund_risk.get('leverage_risk') == 'High':
            risk_factors.append('High financial leverage')
        if fund_risk.get('liquidity_risk') == 'High':
            risk_factors.append('Liquidity concerns')

        # Technical risks
        if tech_risk.get('volatility_risk') == 'Very High':
            risk_factors.append('Very high price volatility')
        if tech_risk.get('support_resistance_risk') == 'High':
            risk_factors.append('Price near key technical levels')

        # Combined risk level
        high_risk_count = sum(1 for factor in risk_factors)

        if high_risk_count >= 3:
            overall_risk = "Very High"
        elif high_risk_count >= 2:
            overall_risk = "High"
        elif high_risk_count >= 1:
            overall_risk = "Moderate"
        else:
            overall_risk = "Low"

        return {
            'overall_risk': overall_risk,
            'risk_factors': risk_factors,
            'fundamental_risks': fund_risk,
            'technical_risks': tech_risk,
            'risk_mitigation': self._suggest_risk_mitigation(risk_factors)
        }

    def _generate_insights(self,
                          fundamental_results: Dict[str, Any],
                          technical_results: Dict[str, Any],
                          confluence_signals: Dict[str, Any]) -> List[str]:
        """Generate actionable insights"""
        insights = []

        # Confluence insights
        confluence_strength = confluence_signals.get('confluence_strength')
        if confluence_strength == 'Very Strong':
            insights.append("Fundamental and technical analysis are in strong agreement")
        elif confluence_strength == 'Weak':
            insights.append("Mixed signals between fundamental and technical analysis - proceed with caution")

        # Add best insights from individual analyses
        fund_insights = fundamental_results.get('insights', [])
        tech_insights = technical_results.get('key_signals', [])

        # Add top fundamental insights
        insights.extend(fund_insights[:2])

        # Add top technical insights
        insights.extend(tech_insights[:2])

        # Time horizon specific insights
        if self.time_horizon == 'short':
            insights.append(f"Short-term focus: Technical signals weighted at {self.weights['technical_weight']*100:.0f}%")
        elif self.time_horizon == 'long':
            insights.append(f"Long-term focus: Fundamental analysis weighted at {self.weights['fundamental_weight']*100:.0f}%")

        return insights

    def _calculate_signal_strength(self, confluence_signals: Dict[str, Any]) -> str:
        """Calculate overall signal strength"""
        confluence_strength = confluence_signals.get('confluence_strength', 'Moderate')
        conflicts = confluence_signals.get('conflicts', [])

        if confluence_strength in ['Very Strong', 'Strong'] and len(conflicts) == 0:
            return "Very Strong"
        elif confluence_strength == 'Strong' and len(conflicts) <= 1:
            return "Strong"
        elif confluence_strength == 'Moderate':
            return "Moderate"
        else:
            return "Weak"

    def _calculate_confidence_level(self,
                                  final_score: Dict[str, Any],
                                  confluence_signals: Dict[str, Any]) -> str:
        """Calculate confidence level in the recommendation"""
        score = final_score['total_score']
        confluence_strength = confluence_signals.get('confluence_strength', 'Moderate')
        conflicts = confluence_signals.get('conflicts', [])

        # Base confidence from score
        if score >= 8.5 or score <= 1.5:
            base_confidence = "High"
        elif score >= 7.0 or score <= 3.0:
            base_confidence = "Moderate"
        else:
            base_confidence = "Low"

        # Special adjustment for long-term overvalued stocks
        if self.time_horizon == 'long' and hasattr(self, 'fundamental') and self.fundamental:
            fund_results = getattr(self.fundamental, 'last_results', {})
            fund_score = fund_results.get('fundamental_score', {})
            component_scores = fund_score.get('component_scores', {})
            valuation_score = component_scores.get('valuation', 1.0)

            # Reduce confidence for overvalued stocks in long-term
            if valuation_score < 0.5:  # Severely overvalued
                if base_confidence == "High":
                    base_confidence = "Low"
                elif base_confidence == "Moderate":
                    base_confidence = "Low"
            elif valuation_score < 1.0:  # Overvalued
                if base_confidence == "High":
                    base_confidence = "Moderate"

        # Adjust for confluence
        if confluence_strength in ['Very Strong', 'Strong'] and len(conflicts) == 0:
            if base_confidence == "Moderate":
                return "High"
            elif base_confidence == "Low":
                return "Moderate"
            else:
                return base_confidence
        elif len(conflicts) > 1:
            if base_confidence == "High":
                return "Moderate"
            elif base_confidence == "Moderate":
                return "Low"
            else:
                return base_confidence
        else:
            return base_confidence

    def _calculate_risk_reward_ratio(self, entry: float, stop_loss: float, take_profit: float) -> float:
        """Calculate risk-reward ratio"""
        if entry <= 0 or stop_loss <= 0 or take_profit <= 0:
            return 0

        risk = entry - stop_loss
        reward = take_profit - entry

        if risk <= 0:
            return 0

        return reward / risk

    def _get_score_rating(self, score: float) -> str:
        """Convert score to rating"""
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

    def _generate_recommendation_reasoning(self,
                                         final_score: Dict[str, Any],
                                         confluence_signals: Dict[str, Any],
                                         recommendation: str) -> str:
        """Generate reasoning for the recommendation"""
        score = final_score['total_score']
        confluence_strength = confluence_signals.get('confluence_strength', 'Moderate')

        reasoning = f"Recommendation based on combined score of {score:.1f}/10 "
        reasoning += f"with {confluence_strength.lower()} confluence between fundamental and technical analysis. "

        if self.time_horizon == 'short':
            reasoning += "Short-term technical factors heavily weighted. "
        elif self.time_horizon == 'long':
            reasoning += "Long-term fundamental factors heavily weighted. "

        conflicts = confluence_signals.get('conflicts', [])
        if conflicts:
            reasoning += f"Note: {len(conflicts)} conflict(s) identified between analyses. "

        return reasoning

    def _suggest_risk_mitigation(self, risk_factors: List[str]) -> List[str]:
        """Suggest risk mitigation strategies"""
        suggestions = []

        if 'High financial leverage' in risk_factors:
            suggestions.append("Monitor debt levels and interest coverage ratios closely")

        if 'Very high price volatility' in risk_factors:
            suggestions.append("Consider smaller position sizes and wider stop losses")

        if 'Price near key technical levels' in risk_factors:
            suggestions.append("Wait for clear breakout/breakdown before entering")

        if 'Liquidity concerns' in risk_factors:
            suggestions.append("Monitor trading volume and avoid large position sizes")

        return suggestions