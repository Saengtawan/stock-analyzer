#!/usr/bin/env python3
"""
Macro Indicators Data Source
Track Fed policy, interest rates, sector performance for rotation signals
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class MacroIndicatorsTracker:
    """Track macro indicators and sector rotation"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)

        # Sector ETFs for tracking sector performance
        self.sector_etfs = {
            'Technology': 'XLK',
            'Financials': 'XLF',
            'Healthcare': 'XLV',
            'Energy': 'XLE',
            'Consumer Discretionary': 'XLY',
            'Consumer Staples': 'XLP',
            'Industrials': 'XLI',
            'Materials': 'XLB',
            'Real Estate': 'XLRE',
            'Utilities': 'XLU',
            'Communications': 'XLC'
        }

    def get_macro_data(self, symbol: str) -> Optional[Dict]:
        """
        Get macro environment data relevant to this stock

        Returns:
            Dict with macro data or None if unavailable
            {
                'sector': str,
                'sector_momentum_7d': float,  # Sector ETF 7-day momentum
                'sector_momentum_30d': float,
                'sector_rank': int,  # Rank among all sectors (1 = best)
                'market_regime': str,  # 'bull', 'bear', 'sideways'
                'spy_momentum_7d': float,
                'spy_momentum_30d': float,
                'sector_outperforming': bool,  # Sector beating SPY
                'macro_score': float,  # 0-100
                'sector_rotation_signal': str  # 'into', 'out_of', 'neutral'
            }
        """

        # Check cache
        cache_key = f"{symbol}_macro"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached macro data")
                return cached_data

        try:
            # Get stock info to find sector
            ticker = yf.Ticker(symbol)
            info = ticker.info
            sector = info.get('sector', 'Unknown')

            # Get SPY (market) performance
            spy_data = self._get_momentum('SPY')

            if not spy_data:
                return None

            market_regime = self._determine_market_regime(spy_data)

            # Get sector performance
            sector_etf = self._get_sector_etf(sector)
            if sector_etf:
                sector_data = self._get_momentum(sector_etf)
                sector_mom_7d = sector_data['momentum_7d']
                sector_mom_30d = sector_data['momentum_30d']
            else:
                sector_mom_7d = 0.0
                sector_mom_30d = 0.0

            # Calculate all sector ranks
            sector_rank = self._get_sector_rank(sector)

            # Determine if sector is outperforming
            sector_outperforming = sector_mom_7d > spy_data['momentum_7d']

            # Calculate macro score
            macro_score = self._calculate_macro_score(
                sector_mom_7d,
                sector_mom_30d,
                sector_rank,
                market_regime,
                sector_outperforming
            )

            # Sector rotation signal
            rotation_signal = self._get_rotation_signal(
                sector_mom_7d,
                sector_mom_30d,
                spy_data['momentum_7d'],
                spy_data['momentum_30d']
            )

            result = {
                'sector': sector,
                'sector_momentum_7d': sector_mom_7d,
                'sector_momentum_30d': sector_mom_30d,
                'sector_rank': sector_rank,
                'market_regime': market_regime,
                'spy_momentum_7d': spy_data['momentum_7d'],
                'spy_momentum_30d': spy_data['momentum_30d'],
                'sector_outperforming': sector_outperforming,
                'macro_score': macro_score,
                'sector_rotation_signal': rotation_signal
            }

            # Cache result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"{symbol}: Error fetching macro data: {e}")
            return None

    def _get_momentum(self, symbol: str) -> Optional[Dict]:
        """Calculate momentum for a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='3mo')

            if len(hist) < 30:
                return None

            current = hist['Close'].iloc[-1]
            week_ago = hist['Close'].iloc[-7]
            month_ago = hist['Close'].iloc[-30]

            mom_7d = ((current - week_ago) / week_ago) * 100
            mom_30d = ((current - month_ago) / month_ago) * 100

            return {
                'momentum_7d': mom_7d,
                'momentum_30d': mom_30d,
                'current_price': current
            }

        except Exception as e:
            logger.error(f"Error getting momentum for {symbol}: {e}")
            return None

    def _determine_market_regime(self, spy_data: Dict) -> str:
        """Determine market regime from SPY momentum"""
        mom_7d = spy_data['momentum_7d']
        mom_30d = spy_data['momentum_30d']

        # Bull: both short and long term positive
        if mom_7d > 2 and mom_30d > 3:
            return 'bull'

        # Bear: both negative
        elif mom_7d < -2 and mom_30d < -3:
            return 'bear'

        # Sideways: mixed or flat
        else:
            return 'sideways'

    def _get_sector_etf(self, sector: str) -> Optional[str]:
        """Get ETF symbol for a sector"""
        return self.sector_etfs.get(sector, None)

    def _get_sector_rank(self, sector: str) -> int:
        """
        Get sector's rank among all sectors
        1 = best performing, 11 = worst
        """
        try:
            # Get performance for all sectors
            sector_performance = []

            for sector_name, etf in self.sector_etfs.items():
                data = self._get_momentum(etf)
                if data:
                    sector_performance.append({
                        'sector': sector_name,
                        'momentum': data['momentum_7d']
                    })

            # Sort by momentum
            sector_performance.sort(key=lambda x: x['momentum'], reverse=True)

            # Find rank
            for i, item in enumerate(sector_performance, 1):
                if item['sector'] == sector:
                    return i

            return 6  # Middle rank if not found

        except Exception as e:
            logger.error(f"Error calculating sector rank: {e}")
            return 6

    def _calculate_macro_score(self, sector_mom_7d: float, sector_mom_30d: float,
                               sector_rank: int, market_regime: str,
                               sector_outperforming: bool) -> float:
        """
        Calculate macro score 0-100

        High score when:
        1. Bull market
        2. Sector outperforming
        3. Sector in top 3
        4. Strong sector momentum
        """

        score = 0.0

        # Market regime (max 30 points)
        if market_regime == 'bull':
            score += 30
        elif market_regime == 'sideways':
            score += 15

        # Sector rank (max 30 points)
        if sector_rank == 1:
            score += 30
        elif sector_rank == 2:
            score += 25
        elif sector_rank == 3:
            score += 20
        elif sector_rank <= 5:
            score += 10

        # Sector outperforming (max 20 points)
        if sector_outperforming:
            score += 20

        # Sector momentum (max 20 points)
        if sector_mom_7d > 5:
            score += 20
        elif sector_mom_7d > 3:
            score += 15
        elif sector_mom_7d > 1:
            score += 10
        elif sector_mom_7d > 0:
            score += 5

        return min(100, score)

    def _get_rotation_signal(self, sector_7d: float, sector_30d: float,
                            spy_7d: float, spy_30d: float) -> str:
        """
        Determine if money is rotating into or out of this sector

        into: Sector accelerating vs market
        out_of: Sector weakening vs market
        neutral: No clear signal
        """

        # Relative strength
        rel_strength_7d = sector_7d - spy_7d
        rel_strength_30d = sector_30d - spy_30d

        # Rotating into sector
        if rel_strength_7d > 2 and rel_strength_7d > rel_strength_30d:
            return 'into'

        # Rotating out of sector
        elif rel_strength_7d < -2 and rel_strength_7d < rel_strength_30d:
            return 'out_of'

        # No clear signal
        else:
            return 'neutral'

    def get_batch_macro_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get macro data for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_macro_data(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = MacroIndicatorsTracker()

    test_symbols = ['AAPL', 'JPM', 'XOM', 'NVDA']

    print("\n" + "="*80)
    print("📈 MACRO INDICATORS TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_macro_data(symbol)
        if data:
            print(f"  Sector: {data['sector']}")
            print(f"  Sector momentum: {data['sector_momentum_7d']:+.1f}% (rank #{data['sector_rank']})")
            print(f"  Market regime: {data['market_regime']}")
            print(f"  Sector outperforming: {data['sector_outperforming']}")
            print(f"  Rotation signal: {data['sector_rotation_signal']}")
            print(f"  Macro score: {data['macro_score']:.1f}/100")
        else:
            print("  No data available")
