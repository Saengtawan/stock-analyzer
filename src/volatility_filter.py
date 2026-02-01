#!/usr/bin/env python3
"""
Volatility Filter Module
Filters out low-volatility stocks that can't realistically hit 10-15% targets
Based on backtest analysis showing certain stocks never hit 15% targets
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from typing import Dict, List, Optional


class VolatilityFilter:
    """
    Volatility-based stock filter

    Purpose: Exclude stocks with insufficient volatility to hit profit targets
    Based on backtest showing some stocks (MSFT, AAPL, NFLX, etc.) never hit 15%
    """

    # Based on backtest analysis - stocks with 0% win rate
    LOW_VOLATILITY_BLACKLIST = [
        'MSFT',   # 0% win rate, max +4.7%
        'AAPL',   # 0% win rate, max +10.3%
        'NFLX',   # 0% win rate, max +3.3%
        'ADBE',   # 0% win rate, max +5.6%
        'UBER',   # 0% win rate, max +5.6%
        'NOW',    # 0% win rate, max +5.8%
        'META',   # 7% win rate, avg +6.2%
        'CRM',    # 7% win rate, avg +8.1%
        'HUBS',   # 11% win rate, avg +9.0%
        'TEAM',   # 11% win rate, avg +8.5%
    ]

    # High-performing stocks (for reference/priority)
    HIGH_VOLATILITY_WHITELIST = [
        'MU',     # 100% win rate, avg +41.5%
        'INTC',   # 87% win rate, avg +36.8%
        'LRCX',   # 80% win rate, avg +28.1%
        'GOOGL',  # 80% win rate, avg +20.2%
        'AVGO',   # 60% win rate, avg +17.2%
        'SHOP',   # 53% win rate, avg +15.5%
        'AMD',    # 53% win rate, avg +28.8%
    ]

    def __init__(self, lookback_days: int = 90):
        """
        Initialize volatility filter

        Args:
            lookback_days: Days to look back for volatility calculation
        """
        self.lookback_days = lookback_days
        self._volatility_cache = {}

    def is_blacklisted(self, symbol: str) -> bool:
        """Check if stock is on blacklist"""
        return symbol.upper() in self.LOW_VOLATILITY_BLACKLIST

    def is_whitelisted(self, symbol: str) -> bool:
        """Check if stock is on whitelist"""
        return symbol.upper() in self.HIGH_VOLATILITY_WHITELIST

    def calculate_volatility_metrics(self, symbol: str) -> Optional[Dict]:
        """
        Calculate comprehensive volatility metrics

        Returns:
            Dict with volatility metrics or None if failed
        """
        # Check cache first
        if symbol in self._volatility_cache:
            cache_time, metrics = self._volatility_cache[symbol]
            if datetime.now() - cache_time < timedelta(hours=1):
                return metrics

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f'{self.lookback_days}d')

            if hist.empty or len(hist) < 30:
                return None

            # Calculate various volatility metrics

            # 1. Average True Range (ATR) as % of price
            high_low = hist['High'] - hist['Low']
            high_close = np.abs(hist['High'] - hist['Close'].shift())
            low_close = np.abs(hist['Low'] - hist['Close'].shift())

            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = true_range.rolling(window=14).mean().iloc[-1]
            atr_pct = (atr / hist['Close'].iloc[-1]) * 100

            # 2. Historical volatility (std dev of returns)
            returns = hist['Close'].pct_change()
            volatility = returns.std() * np.sqrt(252) * 100  # Annualized

            # 3. Max 30-day move (realistic target potential)
            max_30d_gain = 0
            for i in range(len(hist) - 30):
                period_max = hist['High'].iloc[i:i+30].max()
                period_start = hist['Close'].iloc[i]
                gain = ((period_max - period_start) / period_start) * 100
                max_30d_gain = max(max_30d_gain, gain)

            # 4. Average 30-day high-low range
            avg_30d_range = []
            for i in range(len(hist) - 30):
                period_high = hist['High'].iloc[i:i+30].max()
                period_low = hist['Low'].iloc[i:i+30].min()
                range_pct = ((period_high - period_low) / period_low) * 100
                avg_30d_range.append(range_pct)

            avg_range = np.mean(avg_30d_range) if avg_30d_range else 0

            metrics = {
                'atr_pct': atr_pct,
                'annual_volatility': volatility,
                'max_30d_gain': max_30d_gain,
                'avg_30d_range': avg_range,
                'is_blacklisted': self.is_blacklisted(symbol),
                'is_whitelisted': self.is_whitelisted(symbol)
            }

            # Cache results
            self._volatility_cache[symbol] = (datetime.now(), metrics)

            return metrics

        except Exception as e:
            logger.debug(f"Failed to calculate volatility for {symbol}: {e}")
            return None

    def passes_volatility_filter(self,
                                  symbol: str,
                                  target_gain: float = 12.0,
                                  strict: bool = False) -> tuple[bool, str]:
        """
        Check if stock passes volatility filter

        Args:
            symbol: Stock symbol
            target_gain: Target gain percentage (default 12%)
            strict: If True, require higher volatility thresholds

        Returns:
            (passes, reason) tuple
        """
        # Immediate blacklist check
        if self.is_blacklisted(symbol):
            return False, f"BLACKLISTED (0% win rate in backtests)"

        # Whitelist gets priority
        if self.is_whitelisted(symbol):
            return True, "WHITELISTED (proven high win rate)"

        # Calculate metrics
        metrics = self.calculate_volatility_metrics(symbol)

        if not metrics:
            return False, "Insufficient data for volatility analysis"

        # Define thresholds based on target
        # For 12% target, stock should have shown capability of 12%+ moves
        min_max_30d_gain = target_gain * 1.2  # 20% buffer
        min_avg_range = target_gain * 1.5     # Should have avg range of 18%+
        min_atr_pct = 2.0 if not strict else 3.0  # At least 2-3% daily range

        # Check thresholds
        if metrics['max_30d_gain'] < min_max_30d_gain:
            return False, f"Max 30d gain {metrics['max_30d_gain']:.1f}% < {min_max_30d_gain:.1f}% (too stable)"

        if metrics['avg_30d_range'] < min_avg_range:
            return False, f"Avg 30d range {metrics['avg_30d_range']:.1f}% < {min_avg_range:.1f}% (low volatility)"

        if metrics['atr_pct'] < min_atr_pct:
            return False, f"ATR {metrics['atr_pct']:.2f}% < {min_atr_pct}% (insufficient daily movement)"

        return True, f"PASS (Max 30d: {metrics['max_30d_gain']:.1f}%, ATR: {metrics['atr_pct']:.2f}%)"

    def filter_universe(self,
                       symbols: List[str],
                       target_gain: float = 12.0,
                       strict: bool = False) -> tuple[List[str], Dict[str, str]]:
        """
        Filter a list of symbols based on volatility

        Args:
            symbols: List of stock symbols
            target_gain: Target gain percentage
            strict: Use strict filtering

        Returns:
            (filtered_symbols, rejection_reasons) tuple
        """
        filtered = []
        reasons = {}

        logger.info(f"🔍 Volatility Filter: Screening {len(symbols)} stocks")
        logger.info(f"   Target: {target_gain}%")
        logger.info(f"   Blacklist: {len(self.LOW_VOLATILITY_BLACKLIST)} stocks")

        for symbol in symbols:
            passes, reason = self.passes_volatility_filter(symbol, target_gain, strict)

            if passes:
                filtered.append(symbol)
                if self.is_whitelisted(symbol):
                    logger.info(f"   ✅ {symbol}: {reason}")
            else:
                reasons[symbol] = reason
                if self.is_blacklisted(symbol):
                    logger.warning(f"   ❌ {symbol}: {reason}")

        logger.info(f"✅ Volatility Filter: {len(filtered)}/{len(symbols)} passed ({len(filtered)/len(symbols)*100:.1f}%)")
        logger.info(f"   Whitelisted: {len([s for s in filtered if self.is_whitelisted(s)])}")
        logger.info(f"   Rejected: {len(reasons)} ({', '.join(list(reasons.keys())[:5])}{'...' if len(reasons) > 5 else ''})")

        return filtered, reasons

    def get_filter_stats(self) -> Dict:
        """Get statistics about the filter"""
        return {
            'blacklist_count': len(self.LOW_VOLATILITY_BLACKLIST),
            'whitelist_count': len(self.HIGH_VOLATILITY_WHITELIST),
            'blacklist': self.LOW_VOLATILITY_BLACKLIST,
            'whitelist': self.HIGH_VOLATILITY_WHITELIST,
            'cache_size': len(self._volatility_cache)
        }


if __name__ == "__main__":
    # Test the filter
    print("Testing Volatility Filter\n")

    vf = VolatilityFilter()

    test_symbols = ['MU', 'MSFT', 'AAPL', 'GOOGL', 'INTC', 'NFLX', 'AMD']

    print("Individual Tests:")
    for symbol in test_symbols:
        passes, reason = vf.passes_volatility_filter(symbol, target_gain=12.0)
        status = "✅ PASS" if passes else "❌ FAIL"
        print(f"{status} {symbol}: {reason}")

    print("\n" + "="*60)
    print("\nBatch Filter Test:")
    filtered, reasons = vf.filter_universe(test_symbols, target_gain=12.0)

    print(f"\nPassed: {filtered}")
    print(f"Failed: {list(reasons.keys())}")
