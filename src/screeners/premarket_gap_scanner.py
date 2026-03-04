#!/usr/bin/env python3
"""
PRE-MARKET GAP SCANNER v6.82

Redesigned to use batch yfinance with prepost=True for real pre-market bars.

Strategy:
- Scan between 6:00 AM - 9:35 AM ET (after gaps have formed)
- Detect overnight gaps ≥8% with pre-market volume ≥0.3x avg daily regular volume
- Full universe: ~1000 stocks from UniverseRepository
- Confidence tiers: MAJOR_CATALYST(90%), CATALYST(80%), POSSIBLE_CATALYST(70%)

Fixes from v1.0:
- _get_premarket_price() returned regularMarketPrice (not real pre-market) → gap always ~0%
- _get_previous_close() returned today's close when market was open
- Hardcoded 35-stock watchlist
- MIN_VOLUME_RATIO=1.5x was vs daily volume (wrong basis for 5.5h pre-market window)
- Per-symbol yf.Ticker() calls (slow) → now batch yf.download() (fast)
"""

import pandas as pd
from datetime import datetime, date, time
from typing import List, Optional, Tuple
from loguru import logger
import yfinance as yf
import pytz


BATCH_SIZE = 100  # symbols per yf.download call
ET_TZ = pytz.timezone('America/New_York')


class PreMarketGapSignal:
    """Signal for pre-market gap opportunity"""

    def __init__(self, symbol: str, gap_type: str, gap_pct: float,
                 confidence: int, catalyst_type: str, volume_ratio: float,
                 prev_close: float, current_price: float,
                 day_return_estimate: float, rotation_benefit: float,
                 worth_rotating: bool, reasons: List[str]):
        self.symbol = symbol
        self.gap_type = gap_type          # 'OVERNIGHT_GAP'
        self.gap_pct = gap_pct
        self.confidence = confidence      # 70, 80, or 90
        self.catalyst_type = catalyst_type
        self.volume_ratio = volume_ratio
        self.prev_close = prev_close
        self.current_price = current_price
        self.day_return_estimate = day_return_estimate
        self.rotation_benefit = rotation_benefit
        self.worth_rotating = worth_rotating
        self.reasons = reasons
        self.timestamp = datetime.now()

    def __repr__(self):
        return (f"PreMarketGapSignal({self.symbol}, gap={self.gap_pct:.1f}%, "
                f"conf={self.confidence}%, rotation_benefit={self.rotation_benefit:+.1f}%)")


class PreMarketGapScanner:
    """
    v6.82: Batch pre-market gap scanner using real hourly bars with prepost=True.

    Downloads 1h bars (period='5d', prepost=True) in batches of 100 symbols.
    For each symbol:
      - prev_close: last Close in regular hours (9:30-15:30 ET) before today
      - premarket_price: last Close in pre-market bars (before 9:30 ET) today
      - premarket_volume: total Volume of today's pre-market bars
      - volume_ratio: premarket_volume / avg daily regular-hours volume (past days)
    """

    # Gap thresholds
    MIN_GAP_PCT = 8.0             # Minimum gap to consider (raised from 5% — more selective)
    POSSIBLE_CATALYST_GAP = 8.0
    CATALYST_GAP = 10.0
    MAJOR_CATALYST_GAP = 15.0

    # Volume thresholds (pre-market vol vs avg DAILY regular-hours vol)
    # Pre-market runs 4:00-9:30 ET (5.5h) vs regular 9:30-16:00 (6.5h)
    # 0.3x = stock doing 30% of avg daily vol in pre-market → meaningful interest
    MIN_VOLUME_RATIO = 0.3
    HIGH_VOLUME_RATIO = 0.6
    VERY_HIGH_VOLUME_RATIO = 1.0

    # Rotation parameters
    ROTATION_COST = 0.1           # Slippage + fees
    OPPORTUNITY_COST = 2.0        # Expected return from existing position

    def __init__(self):
        self._universe: List[str] = []
        self._load_universe()

    def _load_universe(self):
        """Load full universe from UniverseRepository (~1000 stocks)."""
        try:
            try:
                from database.repositories.universe_repository import UniverseRepository
            except ImportError:
                from src.database.repositories.universe_repository import UniverseRepository
            universe_dict = UniverseRepository().get_all()
            self._universe = list(universe_dict.keys()) if universe_dict else []
            logger.info(f"PreMarketGapScanner: Loaded {len(self._universe)} symbols from universe")
        except Exception as e:
            logger.warning(f"PreMarketGapScanner: Could not load universe ({e}), using fallback")
            self._universe = [
                'NVDA', 'AMD', 'TSLA', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NFLX',
                'MRNA', 'BNTX', 'NVAX', 'VRTX', 'REGN', 'COIN', 'HOOD',
                'SNOW', 'CRWD', 'NET', 'DDOG', 'ZS', 'SHOP',
            ]

    def scan_premarket(self, min_confidence: int = 80) -> List[PreMarketGapSignal]:
        """
        Scan all universe symbols for pre-market gaps.

        Args:
            min_confidence: Minimum confidence level (70, 80, or 90)

        Returns:
            List of gap signals sorted by rotation_benefit descending
        """
        if not self._universe:
            logger.warning("PreMarketGapScanner: No universe symbols loaded")
            return []

        today = datetime.now(ET_TZ).date()
        logger.info(f"PreMarketGapScanner: Scanning {len(self._universe)} symbols "
                    f"for gaps ≥{self.MIN_GAP_PCT}% (min_confidence={min_confidence}%)...")

        signals: List[PreMarketGapSignal] = []
        total_with_data = 0

        for batch_start in range(0, len(self._universe), BATCH_SIZE):
            batch = self._universe[batch_start:batch_start + BATCH_SIZE]
            try:
                batch_signals, n_ok = self._scan_batch(batch, today, min_confidence)
                signals.extend(batch_signals)
                total_with_data += n_ok
            except Exception as e:
                logger.debug(f"Batch {batch_start}-{batch_start + len(batch)} error: {e}")

        signals.sort(key=lambda x: x.rotation_benefit, reverse=True)

        if signals:
            logger.info(f"PreMarketGapScanner: Found {len(signals)} gap signals "
                        f"({total_with_data}/{len(self._universe)} had data)")
            for sig in signals[:5]:
                logger.info(f"  {sig.symbol}: {sig.gap_pct:+.1f}% gap, "
                            f"{sig.catalyst_type}, vol={sig.volume_ratio:.2f}x, "
                            f"benefit={sig.rotation_benefit:+.1f}%")
        else:
            logger.info(f"PreMarketGapScanner: No gaps ≥{self.MIN_GAP_PCT}% found "
                        f"({total_with_data}/{len(self._universe)} had data)")

        return signals

    def _scan_batch(self, symbols: List[str], today: date,
                    min_confidence: int) -> Tuple[List[PreMarketGapSignal], int]:
        """
        Batch download 1h bars with prepost=True, analyze each symbol.
        Returns (signals, n_symbols_with_data).
        """
        try:
            data = yf.download(
                symbols,
                period='5d',
                interval='1h',
                prepost=True,
                group_by='ticker',
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            logger.debug(f"yf.download batch failed ({len(symbols)} symbols): {e}")
            return [], 0

        if data is None or data.empty:
            return [], 0

        signals = []
        n_ok = 0

        for symbol in symbols:
            try:
                # Extract per-symbol DataFrame
                if len(symbols) == 1:
                    # Single symbol: flat DataFrame (no MultiIndex)
                    sym_df = data.copy()
                elif isinstance(data.columns, pd.MultiIndex):
                    if symbol not in data.columns.get_level_values(0):
                        continue
                    sym_df = data[symbol].copy()
                else:
                    continue

                if sym_df is None or sym_df.empty:
                    continue

                # Drop all-NaN rows
                sym_df = sym_df.dropna(how='all')
                if sym_df.empty:
                    continue

                # Ensure tz-aware index in ET
                if sym_df.index.tz is None:
                    sym_df.index = sym_df.index.tz_localize('UTC')
                sym_df.index = sym_df.index.tz_convert(ET_TZ)

                n_ok += 1
                sig = self._analyze_symbol(symbol, sym_df, today, min_confidence)
                if sig:
                    signals.append(sig)

            except Exception as e:
                logger.debug(f"  {symbol}: analysis error: {e}")

        return signals, n_ok

    def _analyze_symbol(self, symbol: str, sym_df: pd.DataFrame,
                        today: date, min_confidence: int) -> Optional[PreMarketGapSignal]:
        """
        Detect pre-market gap for a single symbol from its 1h bar DataFrame.

        prev_close: last Close in regular hours (9:30-15:30 ET) BEFORE today
        premarket_price: last Close in pre-market bars (before 9:30 ET) TODAY
        premarket_volume: total Volume of today's pre-market bars
        volume_ratio: premarket_volume / avg daily regular-hours volume (past days)
        """
        try:
            today_idx = sym_df.index.date == today
            prev_idx = sym_df.index.date < today

            # Regular-hours bars before today (9:30 AM - 3:30 PM ET)
            regular_prev = sym_df[
                prev_idx &
                (sym_df.index.time >= time(9, 30)) &
                (sym_df.index.time <= time(15, 30))
            ]
            if regular_prev.empty:
                return None

            prev_close = float(regular_prev['Close'].iloc[-1])
            if prev_close <= 0 or pd.isna(prev_close):
                return None

            # Pre-market bars: today before 9:30 AM ET
            premarket = sym_df[
                today_idx &
                (sym_df.index.time < time(9, 30))
            ]
            if premarket.empty:
                return None  # No pre-market data yet

            premarket_price = float(premarket['Close'].iloc[-1])
            if premarket_price <= 0 or pd.isna(premarket_price):
                return None

            premarket_volume = float(premarket['Volume'].sum())

            # Gap calculation
            gap_pct = (premarket_price - prev_close) / prev_close * 100
            if gap_pct < self.MIN_GAP_PCT:
                return None

            # Volume ratio: pre-market vol vs avg daily regular-hours vol (past days)
            daily_vols = regular_prev.groupby(regular_prev.index.date)['Volume'].sum()
            if daily_vols.empty:
                return None
            avg_daily_vol = float(daily_vols.mean())
            if avg_daily_vol <= 0:
                return None

            volume_ratio = premarket_volume / avg_daily_vol
            if volume_ratio < self.MIN_VOLUME_RATIO:
                return None

            # Classify catalyst and confidence
            catalyst_type, confidence, day_return_estimate = self._classify_catalyst(
                gap_pct, volume_ratio
            )
            if confidence < min_confidence:
                return None

            rotation_benefit, worth_rotating = self._calculate_rotation_benefit(day_return_estimate)

            reasons = [
                f"Gap: {gap_pct:+.1f}%",
                f"Volume: {volume_ratio:.2f}x daily avg",
                f"Catalyst: {catalyst_type}",
                f"Prev close: ${prev_close:.2f} → ${premarket_price:.2f}",
            ]
            if worth_rotating:
                reasons.append(f"Worth rotating (+{rotation_benefit:.1f}% benefit)")

            return PreMarketGapSignal(
                symbol=symbol,
                gap_type='OVERNIGHT_GAP',
                gap_pct=gap_pct,
                confidence=confidence,
                catalyst_type=catalyst_type,
                volume_ratio=volume_ratio,
                prev_close=prev_close,
                current_price=premarket_price,
                day_return_estimate=day_return_estimate,
                rotation_benefit=rotation_benefit,
                worth_rotating=worth_rotating,
                reasons=reasons,
            )

        except Exception as e:
            logger.debug(f"  {symbol}: _analyze_symbol error: {e}")
            return None

    def _classify_catalyst(self, gap_pct: float, volume_ratio: float) -> Tuple[str, int, float]:
        """
        Classify catalyst type and assign confidence.
        Returns (catalyst_type, confidence, estimated_day_return_pct).
        """
        if gap_pct >= self.MAJOR_CATALYST_GAP and volume_ratio >= self.VERY_HIGH_VOLUME_RATIO:
            return 'MAJOR_CATALYST', 90, gap_pct * 0.40
        elif gap_pct >= self.CATALYST_GAP and volume_ratio >= self.HIGH_VOLUME_RATIO:
            return 'CATALYST', 80, gap_pct * 0.35
        elif gap_pct >= self.POSSIBLE_CATALYST_GAP and volume_ratio >= self.MIN_VOLUME_RATIO:
            return 'POSSIBLE_CATALYST', 70, gap_pct * 0.30
        else:
            return 'UNCERTAIN', 50, 0.0

    def _calculate_rotation_benefit(self, gap_return: float) -> Tuple[float, bool]:
        """Net benefit of rotating into gap vs holding current position."""
        net = gap_return - self.ROTATION_COST - self.OPPORTUNITY_COST
        return net, net > 0


# Convenience function
def scan_premarket_gaps(min_confidence: int = 80) -> List[PreMarketGapSignal]:
    """
    Scan for pre-market gaps using full universe.

    Args:
        min_confidence: Minimum confidence (70, 80, or 90)

    Returns:
        List of high-confidence gap signals
    """
    scanner = PreMarketGapScanner()
    return scanner.scan_premarket(min_confidence)


if __name__ == '__main__':
    logger.info("Testing Pre-Market Gap Scanner v6.82...")
    signals = scan_premarket_gaps(min_confidence=70)

    if signals:
        print(f"\n✅ Found {len(signals)} gap signals:\n")
        for sig in signals:
            print(f"{sig.symbol}:")
            print(f"  Gap: {sig.gap_pct:+.1f}%")
            print(f"  Confidence: {sig.confidence}%")
            print(f"  Catalyst: {sig.catalyst_type}")
            print(f"  Volume: {sig.volume_ratio:.2f}x daily avg")
            print(f"  Rotation benefit: {sig.rotation_benefit:+.1f}%")
            print(f"  Worth rotating: {'✅ YES' if sig.worth_rotating else '❌ NO'}")
            print()
    else:
        print("\n❌ No gaps found (market may be closed or no significant gaps today)")
