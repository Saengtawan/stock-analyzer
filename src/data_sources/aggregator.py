#!/usr/bin/env python3
"""
Alternative Data Aggregator
Combines all alternative data sources into unified signals
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

from .insider_trading import InsiderTradingTracker
from .analyst_ratings import AnalystRatingsTracker
from .short_interest import ShortInterestTracker
from .social_sentiment import SocialSentimentTracker
from .correlation_pairs import CorrelationTracker
from .macro_indicators import MacroIndicatorsTracker

logger = logging.getLogger(__name__)


class AlternativeDataAggregator:
    """
    Aggregates all alternative data sources into a unified score

    This is the main class to use - it handles all the complexity of
    fetching and combining data from multiple sources.
    """

    def __init__(self):
        self.insider = InsiderTradingTracker()
        self.analyst = AnalystRatingsTracker()
        self.short_interest = ShortInterestTracker()
        self.social = SocialSentimentTracker()
        self.correlation = CorrelationTracker()
        self.macro = MacroIndicatorsTracker()

    def get_comprehensive_data(self, symbol: str) -> Optional[Dict]:
        """
        Get comprehensive alternative data for a symbol

        Returns:
            Dict with all data sources combined + overall scores
            {
                'symbol': str,
                'timestamp': datetime,

                # Individual data sources
                'insider': Dict,
                'analyst': Dict,
                'short_interest': Dict,
                'social': Dict,
                'correlation': Dict,
                'macro': Dict,

                # Combined scores
                'overall_score': float,  # 0-100 (higher = better opportunity)
                'confidence': float,  # 0-100 (how many data sources agree)
                'signal_strength': str,  # 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'

                # Key signals
                'has_insider_buying': bool,
                'has_analyst_upgrade': bool,
                'has_squeeze_potential': bool,
                'has_social_buzz': bool,
                'has_sector_momentum': bool,
                'follows_strong_leader': bool,

                # Summary
                'positive_signals': int,  # Number of bullish signals
                'negative_signals': int,  # Number of bearish signals
                'recommendation': str  # Final recommendation
            }
        """

        logger.info(f"Fetching comprehensive data for {symbol}...")

        try:
            # Fetch all data sources
            insider_data = self.insider.get_insider_activity(symbol)
            analyst_data = self.analyst.get_analyst_data(symbol)
            short_data = self.short_interest.get_short_interest(symbol)
            social_data = self.social.get_reddit_sentiment(symbol)
            corr_data = self.correlation.get_correlation_data(symbol)
            macro_data = self.macro.get_macro_data(symbol)

            # Count how many data sources returned valid data
            valid_sources = sum([
                insider_data is not None,
                analyst_data is not None,
                short_data is not None,
                social_data is not None,
                corr_data is not None,
                macro_data is not None
            ])

            if valid_sources == 0:
                logger.warning(f"{symbol}: No data sources available")
                return None

            # Calculate individual scores
            scores = self._calculate_individual_scores(
                insider_data,
                analyst_data,
                short_data,
                social_data,
                corr_data,
                macro_data
            )

            # Calculate overall score (weighted average)
            overall_score = self._calculate_overall_score(scores)

            # Calculate confidence (how many sources agree)
            confidence = self._calculate_confidence(scores, valid_sources)

            # Determine signal strength
            signal_strength = self._determine_signal_strength(overall_score, confidence)

            # Extract key signals
            key_signals = self._extract_key_signals(
                insider_data,
                analyst_data,
                short_data,
                social_data,
                corr_data,
                macro_data
            )

            # Count positive/negative signals
            positive_signals = sum([
                key_signals['has_insider_buying'],
                key_signals['has_analyst_upgrade'],
                key_signals['has_squeeze_potential'],
                key_signals['has_social_buzz'],
                key_signals['has_sector_momentum'],
                key_signals['follows_strong_leader']
            ])

            negative_signals = 0  # Would need bearish signals

            # Generate recommendation
            recommendation = self._generate_recommendation(
                overall_score,
                confidence,
                positive_signals
            )

            result = {
                'symbol': symbol,
                'timestamp': datetime.now(),

                # Individual data sources
                'insider': insider_data,
                'analyst': analyst_data,
                'short_interest': short_data,
                'social': social_data,
                'correlation': corr_data,
                'macro': macro_data,

                # Combined scores
                'overall_score': overall_score,
                'confidence': confidence,
                'signal_strength': signal_strength,

                # Key signals
                **key_signals,

                # Summary
                'positive_signals': positive_signals,
                'negative_signals': negative_signals,
                'recommendation': recommendation,

                # Individual component scores (for debugging)
                'component_scores': scores
            }

            return result

        except Exception as e:
            logger.error(f"{symbol}: Error in get_comprehensive_data: {e}")
            return None

    def _calculate_individual_scores(self, insider, analyst, short, social, corr, macro) -> Dict:
        """Extract individual scores from each data source"""
        return {
            'insider': insider.get('insider_score', 0) if insider else 0,
            'analyst': analyst.get('upgrade_score', 0) if analyst else 0,
            'short': short.get('squeeze_score', 0) if short else 0,
            'social': social.get('social_score', 0) if social else 0,
            'correlation': corr.get('correlation_score', 0) if corr else 0,
            'macro': macro.get('macro_score', 0) if macro else 0
        }

    def _calculate_overall_score(self, scores: Dict) -> float:
        """
        Calculate weighted overall score

        Weights based on predictive power:
        - Insider: 25% (highest power)
        - Analyst: 20%
        - Short: 20%
        - Social: 15%
        - Correlation: 10%
        - Macro: 10%
        """

        weights = {
            'insider': 0.25,
            'analyst': 0.20,
            'short': 0.20,
            'social': 0.15,
            'correlation': 0.10,
            'macro': 0.10
        }

        total_score = 0.0
        total_weight = 0.0

        for key, weight in weights.items():
            if scores[key] > 0:  # Only include non-zero scores
                total_score += scores[key] * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalize (scores are already 0-100)
        return total_score / total_weight

    def _calculate_confidence(self, scores: Dict, valid_sources: int) -> float:
        """
        Calculate confidence based on:
        1. Number of data sources available
        2. Agreement between sources
        """

        # Base confidence from number of sources (0-50 points)
        source_confidence = (valid_sources / 6) * 50

        # Agreement confidence (0-50 points)
        # Check if scores are consistent (all bullish or all bearish)
        positive_scores = sum(1 for s in scores.values() if s > 50)
        negative_scores = sum(1 for s in scores.values() if s < 50)
        total_scores = sum(1 for s in scores.values() if s > 0)

        if total_scores == 0:
            agreement_confidence = 0
        else:
            agreement_ratio = max(positive_scores, negative_scores) / total_scores
            agreement_confidence = agreement_ratio * 50

        return min(100, source_confidence + agreement_confidence)

    def _determine_signal_strength(self, overall_score: float, confidence: float) -> str:
        """Determine signal strength from score and confidence"""

        # Strong signals require both high score AND high confidence
        if overall_score >= 80 and confidence >= 70:
            return 'strong_buy'
        elif overall_score >= 65 and confidence >= 60:
            return 'buy'
        elif overall_score <= 35 and confidence >= 60:
            return 'sell'
        elif overall_score <= 20 and confidence >= 70:
            return 'strong_sell'
        else:
            return 'neutral'

    def _extract_key_signals(self, insider, analyst, short, social, corr, macro) -> Dict:
        """Extract boolean key signals"""
        return {
            'has_insider_buying': insider.get('has_recent_buying', False) if insider else False,
            'has_analyst_upgrade': analyst.get('has_recent_upgrade', False) if analyst else False,
            'has_squeeze_potential': short.get('is_heavily_shorted', False) if short else False,
            'has_social_buzz': social.get('trending', False) if social else False,
            'has_sector_momentum': (macro.get('sector_rotation_signal') == 'into') if macro else False,
            'follows_strong_leader': (corr.get('correlation_score', 0) > 60) if corr else False
        }

    def _generate_recommendation(self, overall_score: float, confidence: float, positive_signals: int) -> str:
        """Generate final recommendation"""

        if overall_score >= 70 and confidence >= 60 and positive_signals >= 3:
            return "STRONG BUY - Multiple positive signals"
        elif overall_score >= 60 and positive_signals >= 2:
            return "BUY - Good setup"
        elif overall_score >= 50:
            return "HOLD - Neutral signals"
        elif overall_score >= 40:
            return "WATCH - Mixed signals"
        else:
            return "PASS - Weak signals"

    def get_batch_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get comprehensive data for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_comprehensive_data(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    aggregator = AlternativeDataAggregator()

    test_symbols = ['AAPL', 'TSLA', 'NVDA']

    print("\n" + "="*80)
    print("🎯 ALTERNATIVE DATA AGGREGATOR TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{'='*80}")
        print(f"📊 {symbol}")
        print('='*80)

        data = aggregator.get_comprehensive_data(symbol)

        if data:
            print(f"\n🎯 Overall Score: {data['overall_score']:.1f}/100")
            print(f"📊 Confidence: {data['confidence']:.1f}/100")
            print(f"💪 Signal Strength: {data['signal_strength']}")
            print(f"\n✅ Positive Signals: {data['positive_signals']}/6")
            print(f"   - Insider buying: {data['has_insider_buying']}")
            print(f"   - Analyst upgrade: {data['has_analyst_upgrade']}")
            print(f"   - Squeeze potential: {data['has_squeeze_potential']}")
            print(f"   - Social buzz: {data['has_social_buzz']}")
            print(f"   - Sector momentum: {data['has_sector_momentum']}")
            print(f"   - Follows leader: {data['follows_strong_leader']}")
            print(f"\n💡 Recommendation: {data['recommendation']}")

            print(f"\n📈 Component Scores:")
            for key, score in data['component_scores'].items():
                print(f"   {key.capitalize()}: {score:.1f}/100")
        else:
            print("  ❌ No data available")
