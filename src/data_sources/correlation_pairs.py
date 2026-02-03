#!/usr/bin/env python3
"""
Correlation & Pairs Analysis
Identify stocks that move together and leader/follower relationships
"""

import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Rate limiting for yf.download
_last_download_time = 0
_download_delay = 1.0  # 1 second between batch downloads


class CorrelationTracker:
    """Track stock correlations and pairs trading opportunities"""

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=24)

        # Define sector/industry groups
        self.groups = {
            'semiconductors': ['NVDA', 'AMD', 'AVGO', 'MU', 'QCOM', 'LRCX', 'AMAT', 'KLAC', 'MRVL'],
            'mega_tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META'],
            'ev_stocks': ['TSLA', 'RIVN', 'LCID', 'NIO', 'XPEV'],
            'cloud': ['SNOW', 'CRWD', 'DDOG', 'NET', 'ZS', 'PLTR'],
            'oil': ['XOM', 'CVX', 'COP', 'OXY'],
            'banks': ['JPM', 'BAC', 'GS', 'MS', 'C'],
            'crypto_related': ['COIN', 'MSTR']
        }

    def get_correlation_data(self, symbol: str) -> Optional[Dict]:
        """
        Get correlation data for a symbol

        Returns:
            Dict with correlation data or None if unavailable
            {
                'sector_peers': List[str],  # Stocks in same sector
                'correlated_stocks': List[Tuple[str, float]],  # (symbol, correlation)
                'sector_leader': str,  # Which stock leads the sector
                'is_leader': bool,  # Is this stock a leader?
                'leader_momentum': float,  # Leader's recent momentum %
                'correlation_score': float,  # 0-100 (higher = following strong leader)
                'pair_trade_opportunity': bool  # Correlation breakdown
            }
        """

        # Check cache
        cache_key = f"{symbol}_corr"
        if cache_key in self.cache:
            cached_data, cache_time = self.cache[cache_key]
            if datetime.now() - cache_time < self.cache_duration:
                logger.debug(f"{symbol}: Using cached correlation data")
                return cached_data

        try:
            # Find which group this symbol belongs to
            peer_group = None
            for group_name, symbols in self.groups.items():
                if symbol in symbols:
                    peer_group = symbols
                    break

            if not peer_group:
                # No predefined group - return basic data
                return {
                    'sector_peers': [],
                    'correlated_stocks': [],
                    'sector_leader': None,
                    'is_leader': False,
                    'leader_momentum': 0.0,
                    'correlation_score': 0.0,
                    'pair_trade_opportunity': False
                }

            # Download price data for peer group
            price_data = self._get_peer_prices(peer_group)

            if price_data is None or price_data.empty:
                return None

            # Calculate correlations
            correlations = self._calculate_correlations(symbol, price_data)

            # Find sector leader
            leader, leader_momentum = self._find_sector_leader(price_data)

            is_leader = (leader == symbol)

            # Calculate correlation score
            corr_score = self._calculate_correlation_score(
                symbol,
                leader,
                leader_momentum,
                correlations
            )

            result = {
                'sector_peers': [s for s in peer_group if s != symbol],
                'correlated_stocks': correlations[:5],  # Top 5
                'sector_leader': leader,
                'is_leader': is_leader,
                'leader_momentum': leader_momentum,
                'correlation_score': corr_score,
                'pair_trade_opportunity': False  # Would need more sophisticated analysis
            }

            # Cache result
            self.cache[cache_key] = (result, datetime.now())

            return result

        except Exception as e:
            logger.error(f"{symbol}: Error calculating correlations: {e}")
            return None

    def _get_peer_prices(self, symbols: List[str], period: str = '3mo') -> Optional[pd.DataFrame]:
        """Download price data for a group of symbols with rate limiting"""
        global _last_download_time

        try:
            # Rate limiting
            now = time.time()
            elapsed = now - _last_download_time
            if elapsed < _download_delay:
                time.sleep(_download_delay - elapsed)
            _last_download_time = time.time()

            data = yf.download(symbols, period=period, progress=False)['Close']

            if isinstance(data, pd.Series):
                # Only one symbol
                data = data.to_frame()

            return data

        except Exception as e:
            logger.error(f"Error downloading peer prices: {e}")
            return None

    def _calculate_correlations(self, symbol: str, price_data: pd.DataFrame) -> List[Tuple[str, float]]:
        """Calculate correlations with peers"""
        try:
            # Calculate returns
            returns = price_data.pct_change().dropna()

            if symbol not in returns.columns:
                return []

            # Calculate correlation with each peer
            correlations = []
            for col in returns.columns:
                if col != symbol:
                    corr = returns[symbol].corr(returns[col])
                    if not np.isnan(corr):
                        correlations.append((col, corr))

            # Sort by correlation (highest first)
            correlations.sort(key=lambda x: x[1], reverse=True)

            return correlations

        except Exception as e:
            logger.error(f"Error calculating correlations: {e}")
            return []

    def _find_sector_leader(self, price_data: pd.DataFrame) -> Tuple[str, float]:
        """
        Find which stock is leading the sector
        Leader = stock with highest momentum in last 7 days
        """
        try:
            if len(price_data) < 7:
                return None, 0.0

            # Calculate 7-day momentum for each stock
            momentum = {}
            for col in price_data.columns:
                current = price_data[col].iloc[-1]
                week_ago = price_data[col].iloc[-7]
                mom = ((current - week_ago) / week_ago) * 100
                momentum[col] = mom

            # Find leader
            leader = max(momentum.items(), key=lambda x: x[1])

            return leader[0], leader[1]

        except Exception as e:
            logger.error(f"Error finding sector leader: {e}")
            return None, 0.0

    def _calculate_correlation_score(self, symbol: str, leader: str, leader_momentum: float, correlations: List) -> float:
        """
        Calculate correlation score 0-100

        High score when:
        1. Leader has strong positive momentum
        2. Stock is highly correlated with leader
        3. Stock is not the leader (follower opportunity)
        """

        score = 0.0

        # Leader momentum contribution (max 50 points)
        if leader_momentum > 10:
            score += 50
        elif leader_momentum > 7:
            score += 40
        elif leader_momentum > 5:
            score += 30
        elif leader_momentum > 3:
            score += 20
        elif leader_momentum > 0:
            score += 10

        # Correlation with leader (max 50 points)
        if correlations:
            # Find correlation with leader
            leader_corr = None
            for stock, corr in correlations:
                if stock == leader:
                    leader_corr = corr
                    break

            if leader_corr:
                if leader_corr > 0.9:
                    score += 50
                elif leader_corr > 0.8:
                    score += 40
                elif leader_corr > 0.7:
                    score += 30
                elif leader_corr > 0.6:
                    score += 20

        # Penalty if this stock IS the leader (we want followers)
        if symbol == leader:
            score *= 0.5

        return min(100, score)

    def get_batch_correlation_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get correlation data for multiple symbols"""
        results = {}

        for symbol in symbols:
            data = self.get_correlation_data(symbol)
            if data:
                results[symbol] = data

        return results


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    tracker = CorrelationTracker()

    test_symbols = ['AMD', 'NVDA', 'TSLA', 'RIVN']

    print("\n" + "="*80)
    print("🔗 CORRELATION & PAIRS TEST")
    print("="*80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        data = tracker.get_correlation_data(symbol)
        if data:
            print(f"  Sector peers: {', '.join(data['sector_peers'][:3])}")
            print(f"  Sector leader: {data['sector_leader']} ({data['leader_momentum']:+.1f}%)")
            print(f"  Is leader: {data['is_leader']}")
            if data['correlated_stocks']:
                top_corr = data['correlated_stocks'][0]
                print(f"  Top correlation: {top_corr[0]} ({top_corr[1]:.2f})")
            print(f"  Correlation score: {data['correlation_score']:.1f}/100")
        else:
            print("  No data available")
