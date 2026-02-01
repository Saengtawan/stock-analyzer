#!/usr/bin/env python3
"""
Short Interest Data Source
Track short interest and short squeeze potential
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class ShortInterestTracker:
    """Track short interest and squeeze potential"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)

    def get_short_interest(self, symbol: str) -> Optional[Dict]:
        """
        Get short interest data

        Returns:
            Dict with short interest data or None if unavailable
            {
                'short_percent_float': float,  # % of float that is shorted
                'short_percent_shares': float,  # % of shares outstanding
                'short_ratio': float,  # Days to cover (short interest / avg volume)
                'shares_short': int,
                'shares_outstanding': int,
                'avg_volume': int,
                'squeeze_score': float,  # 0-100 (higher = more squeeze potential)
                'squeeze_risk': str,  # 'high', 'medium', 'low', 'none'
                'is_heavily_shorted': bool  # >20% of float
            }
        """

        # Check cache
        cache_key = f"{symbol}_short"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached short interest data")
                return cached_data

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Get short interest data
            short_pct_float = info.get('shortPercentOfFloat', 0) * 100  # Convert to %
            short_pct_shares = info.get('sharesPercentSharesOut', 0) * 100
            short_ratio = info.get('shortRatio', 0)  # Days to cover
            shares_short = info.get('sharesShort', 0)
            shares_outstanding = info.get('sharesOutstanding', 0)
            avg_volume = info.get('averageVolume', 0)

            # Calculate squeeze score
            squeeze_score, squeeze_risk = self._calculate_squeeze_potential(
                short_pct_float,
                short_ratio,
                avg_volume
            )

            is_heavily_shorted = short_pct_float > 10.0  # Lowered from 20.0 to 10.0

            result = {
                'short_percent_float': short_pct_float,
                'short_percent_shares': short_pct_shares,
                'short_ratio': short_ratio,
                'shares_short': shares_short,
                'shares_outstanding': shares_outstanding,
                'avg_volume': avg_volume,
                'squeeze_score': squeeze_score,
                'squeeze_risk': squeeze_risk,
                'is_heavily_shorted': is_heavily_shorted
            }

            # Cache result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"{symbol}: Error fetching short interest: {e}")
            return None

    def _calculate_squeeze_potential(self, short_pct: float, days_to_cover: float, volume: int) -> tuple:
        """
        Calculate short squeeze potential

        High squeeze potential when:
        1. High short % of float (>20%)
        2. High days to cover (>5)
        3. Decent volume (liquidity for squeeze)

        Returns: (score, risk_level)
        """

        score = 0.0

        # Short % contribution (max 50 points) - Lowered thresholds
        if short_pct >= 40:
            score += 50
        elif short_pct >= 30:
            score += 45
        elif short_pct >= 20:
            score += 40
        elif short_pct >= 15:
            score += 35
        elif short_pct >= 10:
            score += 30
        elif short_pct >= 7:
            score += 20
        elif short_pct >= 5:
            score += 10

        # Days to cover contribution (max 30 points)
        if days_to_cover >= 10:
            score += 30
        elif days_to_cover >= 7:
            score += 25
        elif days_to_cover >= 5:
            score += 20
        elif days_to_cover >= 3:
            score += 10

        # Volume contribution (max 20 points)
        if volume >= 10_000_000:
            score += 20
        elif volume >= 5_000_000:
            score += 15
        elif volume >= 1_000_000:
            score += 10
        elif volume >= 500_000:
            score += 5

        # Determine risk level
        if score >= 70:
            risk = 'high'
        elif score >= 50:
            risk = 'medium'
        elif score >= 30:
            risk = 'low'
        else:
            risk = 'none'

        return score, risk

    def get_batch_short_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get short interest for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_short_interest(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = ShortInterestTracker()

    test_symbols = ['GME', 'AMC', 'TSLA', 'AAPL']  # GME/AMC had famous squeezes

    print("\n" + "="*80)
    print("📉 SHORT INTEREST TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_short_interest(symbol)
        if data:
            print(f"  Short % of float: {data['short_percent_float']:.2f}%")
            print(f"  Days to cover: {data['short_ratio']:.2f}")
            print(f"  Squeeze score: {data['squeeze_score']:.1f}/100")
            print(f"  Squeeze risk: {data['squeeze_risk']}")
            print(f"  Heavily shorted: {data['is_heavily_shorted']}")
        else:
            print("  No data available")
