#!/usr/bin/env python3
"""
Analyst Ratings Data Source
Track analyst upgrades/downgrades and price target changes
"""

import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, List

from .rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class AnalystRatingsTracker:
    """Track analyst ratings and recommendations"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)

    def get_analyst_data(self, symbol: str) -> Optional[Dict]:
        """
        Get analyst ratings and recommendations

        Returns:
            Dict with analyst data or None if unavailable
            {
                'target_price': float,  # Average analyst target price
                'current_price': float,
                'upside_potential': float,  # % upside to target
                'num_analysts': int,
                'recommendation': str,  # 'buy', 'hold', 'sell'
                'recommendation_score': float,  # 1.0 (strong buy) to 5.0 (strong sell)
                'recent_upgrades': int,  # Last 30 days
                'recent_downgrades': int,
                'upgrade_score': float,  # -100 to +100
                'has_recent_upgrade': bool  # Upgraded in last 30 days (lowered threshold)
            }
        """

        # Check cache
        cache_key = f"{symbol}_analyst"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached analyst data")
                return cached_data

        try:
            limiter = get_rate_limiter()
            ticker = limiter.get_ticker(symbol)
            info = limiter.get_info(symbol)

            if not info:
                logger.debug(f"{symbol}: No info available")
                return None

            # Get analyst recommendations
            rec_key = info.get('recommendationKey', 'none')
            rec_mean = info.get('recommendationMean', 3.0)
            num_analysts = info.get('numberOfAnalystOpinions', 0)

            # Get target price
            target_price = info.get('targetMeanPrice', None)
            current_price = info.get('currentPrice', info.get('regularMarketPrice', None))

            if not current_price or not target_price:
                logger.debug(f"{symbol}: Missing price data")
                return None

            upside_potential = ((target_price - current_price) / current_price) * 100

            # Get upgrade/downgrade history
            try:
                upgrades_downgrades = ticker.upgrades_downgrades
                recent_changes = self._analyze_recent_changes(upgrades_downgrades) if upgrades_downgrades is not None else None
            except:
                recent_changes = None

            # Calculate scores
            upgrade_score = self._calculate_upgrade_score(
                rec_mean,
                recent_changes if recent_changes else {'upgrades': 0, 'downgrades': 0}
            )

            has_recent_upgrade = recent_changes and recent_changes.get('has_recent_upgrade', False) if recent_changes else False

            result = {
                'target_price': target_price,
                'current_price': current_price,
                'upside_potential': upside_potential,
                'num_analysts': num_analysts,
                'recommendation': rec_key,
                'recommendation_score': rec_mean,
                'recent_upgrades': recent_changes.get('upgrades', 0) if recent_changes else 0,
                'recent_downgrades': recent_changes.get('downgrades', 0) if recent_changes else 0,
                'upgrade_score': upgrade_score,
                'has_recent_upgrade': has_recent_upgrade
            }

            # Cache result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"{symbol}: Error fetching analyst data: {e}")
            return None

    def _analyze_recent_changes(self, df: pd.DataFrame) -> Dict:
        """Analyze recent upgrades/downgrades"""
        if df is None or df.empty:
            return {'upgrades': 0, 'downgrades': 0, 'has_recent_upgrade': False}

        try:
            # Filter last 30 days
            cutoff = datetime.now() - timedelta(days=30)
            cutoff_30d = datetime.now() - timedelta(days=30)

            # df index is datetime
            recent_df = df[df.index >= cutoff]

            if recent_df.empty:
                return {'upgrades': 0, 'downgrades': 0, 'has_recent_upgrade': False}

            # Count upgrades vs downgrades
            upgrades = 0
            downgrades = 0
            has_recent_upgrade = False

            for idx, row in recent_df.iterrows():
                action = str(row.get('ToGrade', '')).lower()
                from_grade = str(row.get('FromGrade', '')).lower()

                # Simple heuristic
                if 'up' in action or 'buy' in action or 'outperform' in action:
                    upgrades += 1
                    if idx >= cutoff_30d:
                        has_recent_upgrade = True
                elif 'down' in action or 'sell' in action or 'underperform' in action:
                    downgrades += 1

            return {
                'upgrades': upgrades,
                'downgrades': downgrades,
                'has_recent_upgrade': has_recent_upgrade
            }

        except Exception as e:
            logger.error(f"Error analyzing upgrades/downgrades: {e}")
            return {'upgrades': 0, 'downgrades': 0, 'has_recent_upgrade': False}

    def _calculate_upgrade_score(self, rec_mean: float, changes: Dict) -> float:
        """
        Calculate upgrade score from -100 (bearish) to +100 (bullish)

        rec_mean: 1.0 (strong buy) to 5.0 (strong sell)
        changes: {'upgrades': N, 'downgrades': M}
        """

        # Base score from recommendation mean
        # 1.0 = +100, 2.0 = +50, 3.0 = 0, 4.0 = -50, 5.0 = -100
        base_score = (3.0 - rec_mean) / 2.0 * 100

        # Adjust for recent changes
        upgrade_delta = (changes['upgrades'] - changes['downgrades']) * 10
        upgrade_delta = max(-50, min(50, upgrade_delta))  # Cap at +/- 50

        total_score = base_score + upgrade_delta
        total_score = max(-100, min(100, total_score))  # Ensure -100 to +100

        return total_score

    def get_batch_analyst_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get analyst data for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_analyst_data(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = AnalystRatingsTracker()

    test_symbols = ['AAPL', 'TSLA', 'NVDA', 'MU']

    print("\n" + "="*80)
    print("📊 ANALYST RATINGS TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_analyst_data(symbol)
        if data:
            print(f"  Recommendation: {data['recommendation']} ({data['recommendation_score']:.2f})")
            print(f"  Target upside: {data['upside_potential']:+.1f}%")
            print(f"  Analysts: {data['num_analysts']}")
            print(f"  Recent upgrades/downgrades: {data['recent_upgrades']}/{data['recent_downgrades']}")
            print(f"  Upgrade score: {data['upgrade_score']:+.1f}")
            print(f"  Recent upgrade (30d): {data['has_recent_upgrade']}")
        else:
            print("  No data available")
