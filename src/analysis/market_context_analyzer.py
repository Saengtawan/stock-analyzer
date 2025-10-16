"""
Market Context Analyzer
Analyzes broader market conditions (Index trend, VIX, Sector performance)
to provide context for individual stock recommendations
"""
from typing import Dict, Any, Optional
from loguru import logger
import numpy as np


class MarketContextAnalyzer:
    """
    Analyze market-wide context to adjust stock recommendations

    Factors analyzed:
    1. Major indices trend (S&P 500, NASDAQ direction)
    2. VIX level (market fear/volatility)
    3. Sector rotation (which sectors are outperforming)
    4. Market breadth (advance/decline ratio)
    """

    def __init__(self):
        self.vix_thresholds = {
            'low': 15,
            'normal': 20,
            'elevated': 30,
            'high': 40
        }

    def analyze_market_context(self,
                               market_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze overall market context

        Args:
            market_data: Optional market data (indices, VIX, etc.)

        Returns:
            Market context analysis with adjustment factors
        """
        # If no market data provided, return neutral context
        if not market_data:
            return self._get_neutral_context()

        # 1. Analyze index trends
        index_analysis = self._analyze_indices(market_data)

        # 2. Analyze VIX (volatility/fear)
        vix_analysis = self._analyze_vix(market_data)

        # 3. Analyze sector rotation
        sector_analysis = self._analyze_sectors(market_data)

        # 4. Analyze market breadth
        breadth_analysis = self._analyze_breadth(market_data)

        # 5. Calculate overall market bias
        market_bias = self._calculate_market_bias(
            index_analysis, vix_analysis, sector_analysis, breadth_analysis
        )

        # 6. Generate adjustment recommendations
        adjustments = self._generate_adjustments(market_bias, vix_analysis)

        return {
            'market_bias': market_bias,
            'index_analysis': index_analysis,
            'vix_analysis': vix_analysis,
            'sector_analysis': sector_analysis,
            'breadth_analysis': breadth_analysis,
            'adjustments': adjustments,
            'context_score': self._calculate_context_score(market_bias, vix_analysis)
        }

    def _get_neutral_context(self) -> Dict[str, Any]:
        """Return neutral market context when no data available"""
        return {
            'market_bias': 'NEUTRAL',
            'index_analysis': {
                'sp500_trend': 'NEUTRAL',
                'nasdaq_trend': 'NEUTRAL',
                'overall_trend': 'NEUTRAL'
            },
            'vix_analysis': {
                'level': 'NORMAL',
                'value': 20.0,
                'interpretation': 'Normal volatility'
            },
            'sector_analysis': {
                'rotation_active': False,
                'leading_sectors': [],
                'lagging_sectors': []
            },
            'breadth_analysis': {
                'advance_decline_ratio': 1.0,
                'breadth_interpretation': 'NEUTRAL'
            },
            'adjustments': {
                'score_adjustment': 0.0,
                'confidence_adjustment': 0.0,
                'position_size_multiplier': 1.0,
                'recommendations': ['Market context data not available - use standard analysis']
            },
            'context_score': 5.0
        }

    def _analyze_indices(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze major market indices trends

        Looks at S&P 500 and NASDAQ trends:
        - Price vs moving averages
        - Momentum
        - Recent performance
        """
        indices = market_data.get('indices', {})

        sp500_data = indices.get('sp500', {})
        nasdaq_data = indices.get('nasdaq', {})

        # Analyze S&P 500
        sp500_trend = self._determine_index_trend(sp500_data)

        # Analyze NASDAQ
        nasdaq_trend = self._determine_index_trend(nasdaq_data)

        # Overall market trend
        if sp500_trend == 'BULLISH' and nasdaq_trend == 'BULLISH':
            overall = 'STRONGLY_BULLISH'
        elif sp500_trend == 'BEARISH' and nasdaq_trend == 'BEARISH':
            overall = 'STRONGLY_BEARISH'
        elif sp500_trend == 'BULLISH' or nasdaq_trend == 'BULLISH':
            overall = 'BULLISH'
        elif sp500_trend == 'BEARISH' or nasdaq_trend == 'BEARISH':
            overall = 'BEARISH'
        else:
            overall = 'NEUTRAL'

        return {
            'sp500_trend': sp500_trend,
            'nasdaq_trend': nasdaq_trend,
            'overall_trend': overall,
            'sp500_data': sp500_data,
            'nasdaq_data': nasdaq_data
        }

    def _determine_index_trend(self, index_data: Dict[str, Any]) -> str:
        """Determine trend for a single index"""
        if not index_data:
            return 'NEUTRAL'

        current_price = index_data.get('current')
        sma_50 = index_data.get('sma_50')
        sma_200 = index_data.get('sma_200')
        change_1m = index_data.get('change_1m', 0)

        # Price above both MAs and positive monthly return = BULLISH
        if sma_50 and sma_200 and current_price:
            if current_price > sma_50 > sma_200 and change_1m > 0:
                return 'BULLISH'
            elif current_price < sma_50 < sma_200 and change_1m < 0:
                return 'BEARISH'

        # Fallback to simple momentum
        if change_1m > 3:
            return 'BULLISH'
        elif change_1m < -3:
            return 'BEARISH'

        return 'NEUTRAL'

    def _analyze_vix(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze VIX (CBOE Volatility Index)

        VIX levels:
        - < 15: Low volatility (complacent market)
        - 15-20: Normal
        - 20-30: Elevated (cautious)
        - > 30: High fear (panic mode)
        """
        vix_value = market_data.get('vix', {}).get('current', 20.0)

        if vix_value < self.vix_thresholds['low']:
            level = 'LOW'
            interpretation = 'Low volatility - market complacency'
            risk_adjustment = 0.0  # Neutral
        elif vix_value < self.vix_thresholds['normal']:
            level = 'NORMAL'
            interpretation = 'Normal volatility environment'
            risk_adjustment = 0.0
        elif vix_value < self.vix_thresholds['elevated']:
            level = 'ELEVATED'
            interpretation = 'Elevated volatility - exercise caution'
            risk_adjustment = 0.2  # Increase risk awareness
        elif vix_value < self.vix_thresholds['high']:
            level = 'HIGH'
            interpretation = 'High volatility - significant market stress'
            risk_adjustment = 0.4
        else:
            level = 'EXTREME'
            interpretation = 'Extreme volatility - panic mode'
            risk_adjustment = 0.6

        return {
            'level': level,
            'value': vix_value,
            'interpretation': interpretation,
            'risk_adjustment': risk_adjustment
        }

    def _analyze_sectors(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze sector performance and rotation

        Identifies which sectors are leading/lagging
        """
        sectors = market_data.get('sectors', {})

        if not sectors:
            return {
                'rotation_active': False,
                'leading_sectors': [],
                'lagging_sectors': []
            }

        # Sort sectors by performance
        sector_performance = []
        for sector, data in sectors.items():
            perf = data.get('change_1m', 0)
            sector_performance.append((sector, perf))

        sector_performance.sort(key=lambda x: x[1], reverse=True)

        # Top 3 = leading, Bottom 3 = lagging
        leading = [s[0] for s in sector_performance[:3]]
        lagging = [s[0] for s in sector_performance[-3:]]

        # Check if rotation is active (high dispersion)
        if len(sector_performance) > 0:
            performances = [p[1] for p in sector_performance]
            std_dev = np.std(performances)
            rotation_active = std_dev > 5.0  # > 5% std dev = active rotation
        else:
            rotation_active = False

        return {
            'rotation_active': rotation_active,
            'leading_sectors': leading,
            'lagging_sectors': lagging,
            'all_sectors': dict(sector_performance)
        }

    def _analyze_breadth(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market breadth

        Advance/Decline ratio tells us how broad the market move is
        """
        breadth = market_data.get('breadth', {})

        advancing = breadth.get('advancing', 1500)
        declining = breadth.get('declining', 1500)

        ad_ratio = advancing / max(declining, 1)

        if ad_ratio > 1.5:
            interpretation = 'STRONG_BREADTH'
            description = 'Broad market participation - healthy rally'
        elif ad_ratio > 1.1:
            interpretation = 'POSITIVE_BREADTH'
            description = 'More stocks advancing - supportive'
        elif ad_ratio > 0.9:
            interpretation = 'NEUTRAL_BREADTH'
            description = 'Mixed market action'
        elif ad_ratio > 0.7:
            interpretation = 'NEGATIVE_BREADTH'
            description = 'More stocks declining - warning sign'
        else:
            interpretation = 'POOR_BREADTH'
            description = 'Broad market weakness'

        return {
            'advance_decline_ratio': round(ad_ratio, 2),
            'breadth_interpretation': interpretation,
            'description': description,
            'advancing': advancing,
            'declining': declining
        }

    def _calculate_market_bias(self,
                               index_analysis: Dict[str, Any],
                               vix_analysis: Dict[str, Any],
                               sector_analysis: Dict[str, Any],
                               breadth_analysis: Dict[str, Any]) -> str:
        """
        Calculate overall market bias

        Returns: BULLISH, BEARISH, or NEUTRAL
        """
        bias_score = 0

        # Index trend (most important)
        overall_trend = index_analysis.get('overall_trend')
        if overall_trend == 'STRONGLY_BULLISH':
            bias_score += 3
        elif overall_trend == 'BULLISH':
            bias_score += 2
        elif overall_trend == 'STRONGLY_BEARISH':
            bias_score -= 3
        elif overall_trend == 'BEARISH':
            bias_score -= 2

        # VIX (fear gauge)
        vix_level = vix_analysis.get('level')
        if vix_level in ['EXTREME', 'HIGH']:
            bias_score -= 2  # High fear = bearish
        elif vix_level == 'LOW':
            bias_score += 1  # Low fear = bullish

        # Breadth
        breadth_interp = breadth_analysis.get('breadth_interpretation')
        if breadth_interp == 'STRONG_BREADTH':
            bias_score += 1
        elif breadth_interp == 'POOR_BREADTH':
            bias_score -= 1

        # Convert score to bias
        if bias_score >= 3:
            return 'STRONGLY_BULLISH'
        elif bias_score >= 1:
            return 'BULLISH'
        elif bias_score <= -3:
            return 'STRONGLY_BEARISH'
        elif bias_score <= -1:
            return 'BEARISH'
        else:
            return 'NEUTRAL'

    def _generate_adjustments(self,
                             market_bias: str,
                             vix_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate recommendation adjustments based on market context
        """
        score_adjustment = 0.0
        confidence_adjustment = 0.0
        position_size_multiplier = 1.0
        recommendations = []

        # Adjust based on market bias
        if market_bias == 'STRONGLY_BULLISH':
            score_adjustment = 0.5  # Boost bullish signals
            confidence_adjustment = 0.1
            position_size_multiplier = 1.2
            recommendations.append('Strong market tailwind - favorable for longs')
        elif market_bias == 'BULLISH':
            score_adjustment = 0.3
            confidence_adjustment = 0.05
            position_size_multiplier = 1.1
            recommendations.append('Market supports bullish positions')
        elif market_bias == 'STRONGLY_BEARISH':
            score_adjustment = -0.5  # Penalize bullish signals
            confidence_adjustment = -0.1
            position_size_multiplier = 0.7
            recommendations.append('Strong market headwind - reduce exposure')
        elif market_bias == 'BEARISH':
            score_adjustment = -0.3
            confidence_adjustment = -0.05
            position_size_multiplier = 0.8
            recommendations.append('Market weakness - exercise caution')

        # Adjust based on VIX
        vix_level = vix_analysis.get('level')
        risk_adjustment = vix_analysis.get('risk_adjustment', 0)

        if vix_level in ['HIGH', 'EXTREME']:
            position_size_multiplier *= 0.7  # Reduce size in high volatility
            confidence_adjustment -= 0.1
            recommendations.append(f'High VIX ({vix_analysis.get("value"):.1f}) - reduce position sizes')
        elif vix_level == 'LOW':
            position_size_multiplier *= 1.1  # Can be more aggressive
            recommendations.append('Low volatility environment - opportunity for larger positions')

        return {
            'score_adjustment': round(score_adjustment, 2),
            'confidence_adjustment': round(confidence_adjustment, 2),
            'position_size_multiplier': round(position_size_multiplier, 2),
            'recommendations': recommendations
        }

    def _calculate_context_score(self, market_bias: str, vix_analysis: Dict[str, Any]) -> float:
        """
        Calculate overall market context score (0-10)

        Higher score = better market environment
        """
        score = 5.0  # Neutral base

        # Adjust for market bias
        bias_scores = {
            'STRONGLY_BULLISH': 4.0,
            'BULLISH': 2.0,
            'NEUTRAL': 0.0,
            'BEARISH': -2.0,
            'STRONGLY_BEARISH': -4.0
        }
        score += bias_scores.get(market_bias, 0.0)

        # Adjust for VIX
        vix_level = vix_analysis.get('level')
        if vix_level == 'LOW':
            score += 1.0
        elif vix_level in ['HIGH', 'EXTREME']:
            score -= 2.0

        return max(0.0, min(10.0, score))

    def apply_market_context_to_recommendation(self,
                                              base_score: float,
                                              base_confidence: str,
                                              base_position_size: float,
                                              market_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply market context adjustments to a stock recommendation

        Args:
            base_score: Base recommendation score (0-10)
            base_confidence: Base confidence (LOW/MEDIUM/HIGH)
            base_position_size: Base position size percentage
            market_context: Market context analysis

        Returns:
            Adjusted recommendation
        """
        adjustments = market_context.get('adjustments', {})

        # Adjust score
        score_adjustment = adjustments.get('score_adjustment', 0.0)
        adjusted_score = max(0.0, min(10.0, base_score + score_adjustment))

        # Adjust confidence
        confidence_map = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
        base_conf_value = confidence_map.get(base_confidence, 1)
        conf_adjustment = adjustments.get('confidence_adjustment', 0.0)

        adjusted_conf_value = base_conf_value + (1 if conf_adjustment >= 0.1 else -1 if conf_adjustment <= -0.1 else 0)
        adjusted_conf_value = max(0, min(2, adjusted_conf_value))

        reverse_map = {0: 'LOW', 1: 'MEDIUM', 2: 'HIGH'}
        adjusted_confidence = reverse_map[adjusted_conf_value]

        # Adjust position size
        position_multiplier = adjustments.get('position_size_multiplier', 1.0)
        adjusted_position_size = base_position_size * position_multiplier

        return {
            'adjusted_score': round(adjusted_score, 1),
            'adjusted_confidence': adjusted_confidence,
            'adjusted_position_size': round(adjusted_position_size, 2),
            'score_change': round(adjusted_score - base_score, 2),
            'position_size_change': round(adjusted_position_size - base_position_size, 2),
            'market_context_applied': True,
            'market_bias': market_context.get('market_bias'),
            'context_recommendations': adjustments.get('recommendations', [])
        }

    def calculate_relative_strength(self,
                                    stock_return: float,
                                    sector_return: Optional[float] = None,
                                    market_return: Optional[float] = None,
                                    stock_symbol: str = '') -> Dict[str, Any]:
        """
        Calculate relative strength of stock vs sector and market

        Args:
            stock_return: Stock's return over period (e.g., 1-month %)
            sector_return: Sector's return over same period
            market_return: Market (S&P 500) return over same period
            stock_symbol: Stock symbol for logging

        Returns:
            Relative strength analysis with scores and interpretation
        """
        logger.info(f"Calculating relative strength for {stock_symbol}")

        results = {
            'stock_return': round(stock_return, 2) if stock_return is not None else None,
            'sector_return': round(sector_return, 2) if sector_return is not None else None,
            'market_return': round(market_return, 2) if market_return is not None else None,
        }

        # Calculate relative strength vs sector
        if sector_return is not None and stock_return is not None:
            rs_vs_sector = stock_return - sector_return
            results['rs_vs_sector'] = round(rs_vs_sector, 2)

            # Interpret
            if rs_vs_sector > 5:
                results['sector_interpretation'] = 'STRONG_OUTPERFORMER'
                results['sector_description'] = f"Outperforming sector by {rs_vs_sector:.1f}% - very strong relative strength"
                results['sector_score'] = 9.0
            elif rs_vs_sector > 2:
                results['sector_interpretation'] = 'OUTPERFORMER'
                results['sector_description'] = f"Outperforming sector by {rs_vs_sector:.1f}% - strong relative strength"
                results['sector_score'] = 7.5
            elif rs_vs_sector > 0:
                results['sector_interpretation'] = 'SLIGHT_OUTPERFORMER'
                results['sector_description'] = f"Outperforming sector by {rs_vs_sector:.1f}% - positive momentum"
                results['sector_score'] = 6.0
            elif rs_vs_sector > -2:
                results['sector_interpretation'] = 'SLIGHT_UNDERPERFORMER'
                results['sector_description'] = f"Underperforming sector by {abs(rs_vs_sector):.1f}% - watch closely"
                results['sector_score'] = 4.5
            elif rs_vs_sector > -5:
                results['sector_interpretation'] = 'UNDERPERFORMER'
                results['sector_description'] = f"Underperforming sector by {abs(rs_vs_sector):.1f}% - weak relative strength"
                results['sector_score'] = 3.0
            else:
                results['sector_interpretation'] = 'STRONG_UNDERPERFORMER'
                results['sector_description'] = f"Underperforming sector by {abs(rs_vs_sector):.1f}% - very weak"
                results['sector_score'] = 1.5
        else:
            results['rs_vs_sector'] = None
            results['sector_interpretation'] = 'NO_DATA'
            results['sector_description'] = 'Sector data not available'
            results['sector_score'] = 5.0

        # Calculate relative strength vs market
        if market_return is not None and stock_return is not None:
            rs_vs_market = stock_return - market_return
            results['rs_vs_market'] = round(rs_vs_market, 2)

            # Interpret
            if rs_vs_market > 5:
                results['market_interpretation'] = 'STRONG_OUTPERFORMER'
                results['market_description'] = f"Outperforming market by {rs_vs_market:.1f}% - market leader"
                results['market_score'] = 9.0
            elif rs_vs_market > 2:
                results['market_interpretation'] = 'OUTPERFORMER'
                results['market_description'] = f"Outperforming market by {rs_vs_market:.1f}% - strong performance"
                results['market_score'] = 7.5
            elif rs_vs_market > 0:
                results['market_interpretation'] = 'SLIGHT_OUTPERFORMER'
                results['market_description'] = f"Outperforming market by {rs_vs_market:.1f}% - above average"
                results['market_score'] = 6.0
            elif rs_vs_market > -2:
                results['market_interpretation'] = 'SLIGHT_UNDERPERFORMER'
                results['market_description'] = f"Underperforming market by {abs(rs_vs_market):.1f}% - below average"
                results['market_score'] = 4.5
            elif rs_vs_market > -5:
                results['market_interpretation'] = 'UNDERPERFORMER'
                results['market_description'] = f"Underperforming market by {abs(rs_vs_market):.1f}% - weak performance"
                results['market_score'] = 3.0
            else:
                results['market_interpretation'] = 'STRONG_UNDERPERFORMER'
                results['market_description'] = f"Underperforming market by {abs(rs_vs_market):.1f}% - very weak"
                results['market_score'] = 1.5
        else:
            results['rs_vs_market'] = None
            results['market_interpretation'] = 'NO_DATA'
            results['market_description'] = 'Market data not available'
            results['market_score'] = 5.0

        # Calculate combined RS score
        sector_score = results.get('sector_score', 5.0)
        market_score = results.get('market_score', 5.0)
        combined_rs_score = (sector_score + market_score) / 2
        results['combined_rs_score'] = round(combined_rs_score, 1)

        # Overall interpretation
        if combined_rs_score >= 7.5:
            results['overall_interpretation'] = 'STRONG_RELATIVE_STRENGTH'
            results['overall_description'] = "Strong relative strength - stock is a leader"
            results['recommendation'] = "Favor this stock - showing leadership"
        elif combined_rs_score >= 6.0:
            results['overall_interpretation'] = 'POSITIVE_RELATIVE_STRENGTH'
            results['overall_description'] = "Positive relative strength - stock performing well"
            results['recommendation'] = "Good candidate - outperforming peers"
        elif combined_rs_score >= 4.5:
            results['overall_interpretation'] = 'NEUTRAL_RELATIVE_STRENGTH'
            results['overall_description'] = "Neutral relative strength - in line with benchmarks"
            results['recommendation'] = "Average performance - no edge from RS"
        elif combined_rs_score >= 3.0:
            results['overall_interpretation'] = 'WEAK_RELATIVE_STRENGTH'
            results['overall_description'] = "Weak relative strength - lagging benchmarks"
            results['recommendation'] = "Caution - underperforming peers"
        else:
            results['overall_interpretation'] = 'VERY_WEAK_RELATIVE_STRENGTH'
            results['overall_description'] = "Very weak relative strength - significant underperformance"
            results['recommendation'] = "Avoid - showing significant weakness"

        # Generate key insights
        insights = []
        if results.get('rs_vs_sector') is not None:
            if results['rs_vs_sector'] > 3:
                insights.append(f"📈 Sector leader: +{results['rs_vs_sector']:.1f}% vs sector")
            elif results['rs_vs_sector'] < -3:
                insights.append(f"📉 Sector laggard: {results['rs_vs_sector']:.1f}% vs sector")

        if results.get('rs_vs_market') is not None:
            if results['rs_vs_market'] > 3:
                insights.append(f"🚀 Market leader: +{results['rs_vs_market']:.1f}% vs S&P 500")
            elif results['rs_vs_market'] < -3:
                insights.append(f"⚠️ Market laggard: {results['rs_vs_market']:.1f}% vs S&P 500")

        # Trading signal based on RS
        if combined_rs_score >= 7.0:
            insights.append("✅ Strong buy signal from relative strength")
        elif combined_rs_score <= 3.5:
            insights.append("❌ Avoid - weak relative strength")

        results['key_insights'] = insights

        logger.info(f"RS for {stock_symbol}: Combined score = {combined_rs_score:.1f}/10")
        return results
