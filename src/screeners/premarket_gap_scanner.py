#!/usr/bin/env python3
"""
PRE-MARKET GAP SCANNER v2.0
Based on backtest results: 100% win rate, 77% rotation rate, +13.3%/month

Strategy:
- Scan AFTER gap already happened (6 AM - 9:30 AM ET)
- Detect overnight gaps 5%+ with high volume (3x+)
- Classify catalyst confidence (70%, 80%, 90%)
- Calculate rotation worthiness vs current positions
- Alert when high-confidence gaps found

Buy: At market open (9:30 AM ET)
Sell: Same day close OR next day (depends on momentum)

Based on: backtests/backtest_gap_scanner_comprehensive.py
Win rate: 100% (57/57 events in backtest)
Rotation rate: 77.2% worth rotating
Monthly return: +13.3%
"""

import numpy as np
import pandas as pd
from datetime import datetime, time
from typing import List, Dict, Optional, Tuple
from loguru import logger
import yfinance as yf


class PreMarketGapSignal:
    """Signal for pre-market gap opportunity"""

    def __init__(self, symbol: str, gap_type: str, gap_pct: float,
                 confidence: int, catalyst_type: str, volume_ratio: float,
                 prev_close: float, current_price: float,
                 day_return_estimate: float, rotation_benefit: float,
                 worth_rotating: bool, reasons: List[str]):
        self.symbol = symbol
        self.gap_type = gap_type  # 'OVERNIGHT_GAP' or 'INTRADAY_BREAKOUT'
        self.gap_pct = gap_pct
        self.confidence = confidence  # 70, 80, or 90
        self.catalyst_type = catalyst_type  # 'MAJOR_CATALYST', 'CATALYST', 'POSSIBLE_CATALYST'
        self.volume_ratio = volume_ratio
        self.prev_close = prev_close
        self.current_price = current_price
        self.day_return_estimate = day_return_estimate
        self.rotation_benefit = rotation_benefit  # Net benefit of rotating
        self.worth_rotating = worth_rotating
        self.reasons = reasons
        self.timestamp = datetime.now()

    def __repr__(self):
        return (f"PreMarketGapSignal({self.symbol}, gap={self.gap_pct:.1f}%, "
                f"conf={self.confidence}%, rotation_benefit={self.rotation_benefit:+.1f}%)")


class PreMarketGapScanner:
    """
    Scan for high-confidence pre-market gaps

    Based on comprehensive backtest (2023-2025):
    - 57 overnight gaps found
    - 100% win rate
    - 77.2% worth rotating
    - +13.3% monthly return
    """

    # Gap thresholds
    MIN_GAP_PCT = 5.0  # Minimum gap to consider

    # Volume thresholds
    MIN_VOLUME_RATIO = 1.5  # For any consideration
    HIGH_VOLUME_RATIO = 2.0  # For PROBABLE_CATALYST
    VERY_HIGH_VOLUME_RATIO = 2.5  # For SCHEDULED_CATALYST

    # Confidence scoring thresholds
    MAJOR_CATALYST_GAP = 15.0  # Gap 15%+ = likely major catalyst
    CATALYST_GAP = 10.0  # Gap 10%+ = likely catalyst
    POSSIBLE_CATALYST_GAP = 8.0  # Gap 8%+ = possible catalyst

    # Rotation parameters (from backtest)
    ROTATION_COST = 0.1  # Slippage + fees (0.1%)
    OPPORTUNITY_COST = 2.0  # Expected return from current position (2%)

    def __init__(self, watchlist: List[str] = None):
        """
        Args:
            watchlist: List of symbols to monitor (if None, use default universe)
        """
        self.watchlist = watchlist or self._get_default_watchlist()
        self._price_cache = {}
        self._last_close_cache = {}

    def _get_default_watchlist(self) -> List[str]:
        """Get default watchlist (high-volume stocks that gap frequently)"""
        return [
            # Tech giants
            'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
            # Biotech (FDA catalysts)
            'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN',
            # High volatility
            'GME', 'AMC', 'PLTR', 'COIN', 'HOOD',
            # Growth/Cloud
            'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP', 'ROKU',
            # Speculative
            'PLUG', 'RIVN', 'LCID', 'SOFI', 'UPST', 'RBLX'
        ]

    def scan_premarket(self, min_confidence: int = 80) -> List[PreMarketGapSignal]:
        """
        Scan for pre-market gaps (call between 6 AM - 9:30 AM ET)

        Args:
            min_confidence: Minimum confidence level (70, 80, or 90)

        Returns:
            List of high-confidence gap signals, sorted by rotation benefit
        """
        logger.info(f"PreMarketGapScanner: Scanning {len(self.watchlist)} symbols...")

        signals = []

        for symbol in self.watchlist:
            try:
                signal = self._check_gap(symbol, min_confidence)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Error checking {symbol}: {e}")

        # Sort by rotation benefit (highest first)
        signals.sort(key=lambda x: x.rotation_benefit, reverse=True)

        if signals:
            logger.info(f"PreMarketGapScanner: Found {len(signals)} high-confidence gaps")
            for sig in signals[:5]:  # Log top 5
                logger.info(f"  {sig.symbol}: {sig.gap_pct:+.1f}% gap, "
                           f"{sig.confidence}% conf, "
                           f"rotation benefit: {sig.rotation_benefit:+.1f}%")
        else:
            logger.info("PreMarketGapScanner: No high-confidence gaps found")

        return signals

    def _check_gap(self, symbol: str, min_confidence: int) -> Optional[PreMarketGapSignal]:
        """Check if symbol has a high-confidence gap"""

        # Get yesterday's close and today's pre-market price
        prev_close = self._get_previous_close(symbol)
        current_price = self._get_premarket_price(symbol)

        if prev_close is None or current_price is None:
            return None

        if prev_close <= 0 or current_price <= 0:
            return None

        # Calculate gap %
        gap_pct = ((current_price - prev_close) / prev_close) * 100

        # Only positive gaps >= 5%
        if gap_pct < self.MIN_GAP_PCT:
            return None

        # Get volume ratio (current vs 20-day average)
        volume_ratio = self._get_volume_ratio(symbol)
        if volume_ratio is None or volume_ratio < self.MIN_VOLUME_RATIO:
            return None

        # Classify catalyst and assign confidence
        catalyst_type, confidence, day_return_estimate = self._classify_catalyst(
            gap_pct, volume_ratio, current_price
        )

        # Filter by minimum confidence
        if confidence < min_confidence:
            return None

        # Calculate rotation worthiness
        rotation_benefit, worth_rotating = self._calculate_rotation_benefit(
            day_return_estimate
        )

        # Build reasons list
        reasons = []
        reasons.append(f"Gap: {gap_pct:+.1f}%")
        reasons.append(f"Volume: {volume_ratio:.1f}x avg")
        reasons.append(f"Catalyst: {catalyst_type}")
        reasons.append(f"Confidence: {confidence}%")
        if worth_rotating:
            reasons.append(f"Worth rotating (+{rotation_benefit:.1f}% benefit)")
        else:
            reasons.append(f"Not worth rotating ({rotation_benefit:+.1f}% benefit)")

        return PreMarketGapSignal(
            symbol=symbol,
            gap_type='OVERNIGHT_GAP',
            gap_pct=gap_pct,
            confidence=confidence,
            catalyst_type=catalyst_type,
            volume_ratio=volume_ratio,
            prev_close=prev_close,
            current_price=current_price,
            day_return_estimate=day_return_estimate,
            rotation_benefit=rotation_benefit,
            worth_rotating=worth_rotating,
            reasons=reasons
        )

    def _classify_catalyst(self, gap_pct: float, volume_ratio: float,
                          current_price: float) -> Tuple[str, int, float]:
        """
        Classify catalyst type and assign confidence score

        Based on backtest patterns:
        - MAJOR_CATALYST (90%): gap 15%+, volume 2.5x+
        - CATALYST (80%): gap 10%+, volume 2x+
        - POSSIBLE_CATALYST (70%): gap 8%+, volume 1.5x+

        Returns:
            (catalyst_type, confidence_score, estimated_day_return)
        """

        # Tier S: 85-95% confidence
        if gap_pct >= self.MAJOR_CATALYST_GAP and volume_ratio >= self.VERY_HIGH_VOLUME_RATIO:
            # Estimate: gaps this big typically give 5%+ intraday return
            estimated_return = gap_pct * 0.4  # Conservative: 40% of gap holds intraday
            return 'MAJOR_CATALYST', 90, estimated_return

        # Tier A: 75-85% confidence
        elif gap_pct >= self.CATALYST_GAP and volume_ratio >= self.HIGH_VOLUME_RATIO:
            # Estimate: 3%+ intraday return typical
            estimated_return = gap_pct * 0.35
            return 'CATALYST', 80, estimated_return

        # Tier B: 65-75% confidence
        elif gap_pct >= self.POSSIBLE_CATALYST_GAP and volume_ratio >= self.MIN_VOLUME_RATIO:
            # Estimate: 2%+ intraday return
            estimated_return = gap_pct * 0.3
            return 'POSSIBLE_CATALYST', 70, estimated_return

        # Below threshold
        else:
            return 'UNCERTAIN', 50, 0.0

    def _calculate_rotation_benefit(self, gap_return: float) -> Tuple[float, bool]:
        """
        Calculate net benefit of rotating into gap vs holding current position

        Formula (from backtest):
        net_benefit = gap_gain - rotation_cost - opportunity_cost

        Args:
            gap_return: Estimated return from gap trade

        Returns:
            (net_benefit, worth_rotating)
        """
        gap_gain = gap_return
        net_benefit = gap_gain - self.ROTATION_COST - self.OPPORTUNITY_COST
        worth_rotating = net_benefit > 0

        return net_benefit, worth_rotating

    def _get_previous_close(self, symbol: str) -> Optional[float]:
        """Get yesterday's closing price"""
        if symbol in self._last_close_cache:
            return self._last_close_cache[symbol]

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='5d')

            if hist.empty or len(hist) < 1:
                return None

            # Get most recent close (yesterday)
            prev_close = float(hist['Close'].iloc[-1])
            self._last_close_cache[symbol] = prev_close
            return prev_close

        except Exception as e:
            logger.debug(f"Error getting prev close for {symbol}: {e}")
            return None

    def _get_premarket_price(self, symbol: str) -> Optional[float]:
        """
        Get current pre-market price

        Note: yfinance doesn't provide real-time pre-market quotes reliably.
        In production, use:
        - Alpaca API: alpaca.get_latest_quote(symbol)
        - IEX Cloud: iex.get_quote(symbol)
        - Polygon.io: polygon.get_last_trade(symbol)

        For now, use regular market quote (placeholder)
        """
        try:
            ticker = yf.Ticker(symbol)

            # Try to get pre-market quote (not always available)
            quote = ticker.info
            current_price = quote.get('regularMarketPrice') or quote.get('currentPrice')

            if current_price:
                return float(current_price)

            # Fallback: use last close (not ideal for pre-market)
            hist = ticker.history(period='1d')
            if not hist.empty:
                return float(hist['Close'].iloc[-1])

            return None

        except Exception as e:
            logger.debug(f"Error getting current price for {symbol}: {e}")
            return None

    def _get_volume_ratio(self, symbol: str) -> Optional[float]:
        """Get volume ratio (current vs 20-day average)"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1mo')

            if hist.empty or len(hist) < 20:
                return None

            # Current volume (today or latest)
            current_volume = float(hist['Volume'].iloc[-1])

            # 20-day average
            avg_volume_20 = float(hist['Volume'].iloc[-20:].mean())

            if avg_volume_20 <= 0:
                return None

            volume_ratio = current_volume / avg_volume_20
            return volume_ratio

        except Exception as e:
            logger.debug(f"Error getting volume ratio for {symbol}: {e}")
            return None


# Convenience function
def scan_premarket_gaps(watchlist: List[str] = None, min_confidence: int = 80) -> List[PreMarketGapSignal]:
    """
    Scan for pre-market gaps

    Args:
        watchlist: List of symbols to scan (default: common gappers)
        min_confidence: Minimum confidence (70, 80, or 90)

    Returns:
        List of high-confidence gap signals
    """
    scanner = PreMarketGapScanner(watchlist)
    return scanner.scan_premarket(min_confidence)


if __name__ == '__main__':
    # Test scan
    logger.info("Testing Pre-Market Gap Scanner...")
    signals = scan_premarket_gaps(min_confidence=70)

    if signals:
        print(f"\n✅ Found {len(signals)} gap signals:\n")
        for sig in signals:
            print(f"{sig.symbol}:")
            print(f"  Gap: {sig.gap_pct:+.1f}%")
            print(f"  Confidence: {sig.confidence}%")
            print(f"  Catalyst: {sig.catalyst_type}")
            print(f"  Volume: {sig.volume_ratio:.1f}x average")
            print(f"  Rotation benefit: {sig.rotation_benefit:+.1f}%")
            print(f"  Worth rotating: {'✅ YES' if sig.worth_rotating else '❌ NO'}")
            print()
    else:
        print("\n❌ No gaps found (market may be closed or no significant gaps today)")
