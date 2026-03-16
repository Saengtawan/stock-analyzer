#!/usr/bin/env python3
"""
OVERNIGHT GAP SCANNER v1.0 (v4.9.4)

Scans for stocks likely to gap up overnight.
Buy: 15:30-15:50 ET (before close)
Sell: 9:31-10:00 ET next day (NOT a day trade)

Criteria:
1. Close near high of day (within 4% of intraday high)
2. Volume > 1.2x 20-day average
3. RSI 40-65 (not overbought)
4. Positive momentum today (close > open)
5. [v6.57] Intraday selling pressure < 3% (open→low drop)
6. [v6.57] Sector NOT Financial Services (macro-driven gaps)

v6.57 Additions (backtest 17 trades: WR 59%→77%, avg -0.30%→+1.44%):
- open_to_low < 3%: avoids stocks where sellers were active (PIPR, VNO, RNG all had >5%)
- no Financial Services: banks gap on Fed/earnings, not intraday momentum (FNB)
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Optional
from loguru import logger


class OvernightGapScanner:
    """
    Scan for stocks likely to gap up overnight.
    Uses end-of-day strength + volume + sector regime signals.
    """

    # Default parameters
    MIN_CLOSE_TO_HIGH_PCT = 96.0   # v6.35: 98→96 (within 4% of daily high, more signals while keeping quality)
    MIN_VOLUME_RATIO = 1.2          # Volume > 1.2x 20-day average
    RSI_MIN = 40
    RSI_MAX = 65
    MIN_ATR_PCT = 1.5               # Minimum volatility for profit potential
    MAX_ATR_PCT = 6.0               # Max volatility (too risky overnight)
    MAX_INTRADAY_SELLING_PCT = 3.0  # v6.57: Max open→low drop % (intraday selling pressure)
    BLOCKED_SECTORS = (
        'Financial Services',   # v6.57: Macro-driven gaps, not momentum
        'Consumer Cyclical',    # v7.4: OVN WR5d=0% avg=-3.47% (n=3)
        'Consumer_Travel',      # v7.4: Consumer sub-sector (MTN etc.)
        'Consumer_Auto',        # v7.4: Consumer sub-sector
        'Consumer_Retail',      # v7.4: Consumer sub-sector
        'Consumer_Food',        # v7.4: Consumer sub-sector
        'Consumer_Staples',     # v7.4: Consumer sub-sector (defensive but same block)
        'Consumer Defensive',   # v7.4: Consumer sub-sector
        'Communication Services',  # v7.4: OVN WR5d=0% avg=-5.98% (n=14)
    )

    def __init__(self, data_manager=None):
        """
        Args:
            data_manager: Optional data cache dict {symbol: DataFrame}
        """
        self.data_cache = data_manager or {}

        # v6.33: Sector filter for win rate improvement
        try:
            from filters.sector_filter import SectorFilter
            self.sector_filter = SectorFilter(enabled=True)
        except ImportError:
            logger.warning("Sector filter not available")
            self.sector_filter = None

        # v6.73: Pre-load sector map from universe DB (replaces yf.Ticker.info calls)
        self._sector_cache = {}
        try:
            from database.repositories.universe_repository import UniverseRepository
            universe = UniverseRepository().get_all()
            self._sector_cache = {sym: data.get('sector', '') for sym, data in universe.items()}
            logger.debug(f"OVN: Loaded {len(self._sector_cache)} sectors from universe DB")
        except Exception as e:
            logger.warning(f"OVN: Could not load sector cache from DB: {e}")

    def scan(self, universe: dict = None, sector_regime=None,
             min_score: int = 70, position_pct: float = 35,
             target_pct: float = 3.0, sl_pct: float = 1.5) -> List:
        """
        Scan for overnight gap candidates.

        Args:
            universe: Dict of {symbol: DataFrame} with OHLCV data
            sector_regime: SectorRegimeDetector instance
            min_score: Minimum score threshold
            position_pct: Position size percentage
            target_pct: Target profit percentage
            sl_pct: Stop loss percentage

        Returns:
            List of RapidRotationSignal compatible signals
        """
        try:
            from screeners.rapid_rotation_screener import RapidRotationSignal
        except ImportError:
            from src.screeners.rapid_rotation_screener import RapidRotationSignal

        data = universe or self.data_cache
        if not data:
            logger.warning("OvernightGapScanner: No data available")
            return []

        candidates = []

        for symbol, df in data.items():
            try:
                signal = self._analyze_stock(
                    symbol, df, sector_regime,
                    min_score, target_pct, sl_pct
                )
                if signal:
                    candidates.append(signal)
            except Exception as e:
                logger.debug(f"OvernightGap: Error analyzing {symbol}: {e}")

        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)

        # v6.33: Apply sector filter (remove weak sectors)
        if self.sector_filter and self.sector_filter.enabled and candidates:
            candidates = self.sector_filter.filter_signals(candidates)

        if candidates:
            logger.info(f"OvernightGap: Found {len(candidates)} candidates")
        else:
            logger.info("OvernightGap: No candidates found")

        return candidates[:5]  # Top 5

    def _analyze_stock(self, symbol: str, df: pd.DataFrame,
                       sector_regime=None, min_score: int = 70,
                       target_pct: float = 3.0, sl_pct: float = 1.5):
        """Analyze a single stock for overnight gap potential."""
        try:
            from screeners.rapid_rotation_screener import RapidRotationSignal
        except ImportError:
            from src.screeners.rapid_rotation_screener import RapidRotationSignal

        if df is None or len(df) < 25:
            return None

        # Get latest data (support both 'close' and 'Close' column names)
        def get_col(df, name):
            if name.lower() in df.columns:
                return df[name.lower()].values
            elif name in df.columns:
                return df[name].values
            return None

        close = get_col(df, 'Close')
        high = get_col(df, 'High')
        low = get_col(df, 'Low')
        open_prices = get_col(df, 'Open')
        volume = get_col(df, 'Volume')

        if close is None or high is None or volume is None:
            return None

        current_close = float(close[-1])
        current_high = float(high[-1])
        current_low = float(low[-1])
        current_open = float(open_prices[-1]) if open_prices is not None else current_close
        current_volume = float(volume[-1])

        if current_close <= 0 or current_high <= 0:
            return None

        # --- Scoring ---
        score = 0
        reasons = []

        # 1. Close near high of day (within 1%)
        close_to_high_pct = (current_close / current_high) * 100 if current_high > 0 else 0
        if close_to_high_pct >= self.MIN_CLOSE_TO_HIGH_PCT:
            score += 30
            reasons.append(f"Close near HOD ({close_to_high_pct:.1f}%)")
        else:
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ovn', symbol=symbol, reject_reason='not_close_to_high',
                    scan_price=round(current_close, 2),
                )
            except Exception:
                pass
            return None  # Must close near high

        # 2. Positive day (close > open)
        if current_close > current_open:
            day_gain = ((current_close - current_open) / current_open) * 100
            score += min(int(day_gain * 5), 20)  # Up to 20 pts for strong day
            reasons.append(f"Green day +{day_gain:.1f}%")
        else:
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ovn', symbol=symbol, reject_reason='red_day',
                    scan_price=round(current_close, 2),
                )
            except Exception:
                pass
            return None  # Must be a green day

        # v6.57: Intraday selling pressure — how far did price drop from open intraday?
        # If open→low drop > 3%, sellers were active during the day even if price recovered.
        # Backtest: catches PIPR(-8.82%), VNO(-8.02%), RNG(-2.34%) with zero false positives.
        if current_open > 0:
            open_to_low_pct = (current_open - current_low) / current_open * 100
            if open_to_low_pct >= self.MAX_INTRADAY_SELLING_PCT:
                logger.debug(f"OVN: {symbol} blocked — intraday selling pressure {open_to_low_pct:.1f}% >= {self.MAX_INTRADAY_SELLING_PCT}%")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='ovn', symbol=symbol, reject_reason='intraday_selling',
                        scan_price=round(current_close, 2),
                    )
                except Exception:
                    pass
                return None

        # 3. Volume above average
        avg_volume_20 = float(np.mean(volume[-20:])) if len(volume) >= 20 else float(np.mean(volume))
        if avg_volume_20 > 0:
            vol_ratio = current_volume / avg_volume_20
            if vol_ratio >= self.MIN_VOLUME_RATIO:
                score += min(int(vol_ratio * 10), 20)  # Up to 20 pts
                reasons.append(f"Vol {vol_ratio:.1f}x avg")
            else:
                # v7.5: Log volume rejection (after close_near_high + green_day passed — real candidate)
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='ovn', symbol=symbol, reject_reason='volume_too_low',
                        scan_price=round(current_close, 2), volume_ratio=round(vol_ratio, 3),
                    )
                except Exception:
                    pass
                return None  # Must have above-average volume

        # v7.5: Block stocks with earnings TODAY (D=0) — overnight hold through earnings
        # is uncontrolled risk. PEM handles earnings-day plays with same-day exit.
        if self._has_earnings_today(symbol):
            logger.debug(f"OVN: {symbol} blocked — earnings today (D=0)")
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ovn', symbol=symbol, reject_reason='earnings_today',
                    scan_price=round(current_close, 2), volume_ratio=round(vol_ratio, 3),
                )
            except Exception:
                pass
            return None

        # v6.57: Block Financial Services sector — banks/brokers gap on Fed/earnings news,
        # not intraday momentum. Cached after first fetch, minimal overhead per scan.
        stock_sector = self._get_sector_from_cache(symbol)
        if stock_sector in self.BLOCKED_SECTORS:
            logger.debug(f"OVN: {symbol} blocked — sector '{stock_sector}' in BLOCKED_SECTORS")
            # v7.5: Log sector rejection
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ovn', symbol=symbol, reject_reason='sector_blocked',
                    scan_price=round(current_close, 2), volume_ratio=round(vol_ratio, 3),
                )
            except Exception:
                pass
            return None

        # 4. RSI check (40-65 = not overbought, momentum still up)
        rsi = self._calculate_rsi(close)
        if rsi is not None:
            if rsi > self.RSI_MAX:
                logger.debug(f"OVN: {symbol} blocked — RSI {rsi:.1f} > {self.RSI_MAX} (overbought)")
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='ovn', symbol=symbol, reject_reason='rsi_too_high',
                        scan_price=round(current_close, 2), rsi=round(rsi, 1),
                        volume_ratio=round(vol_ratio, 3),
                    )
                except Exception:
                    pass
                return None
            elif self.RSI_MIN <= rsi <= self.RSI_MAX:
                score += 15
                reasons.append(f"RSI {rsi:.0f}")

        # 5. ATR check
        atr_pct = self._calculate_atr_pct(high, low, close)
        if atr_pct is not None:
            if self.MIN_ATR_PCT <= atr_pct <= self.MAX_ATR_PCT:
                score += 10
                reasons.append(f"ATR {atr_pct:.1f}%")
            elif atr_pct > self.MAX_ATR_PCT:
                # v7.5: Log ATR rejection
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='ovn', symbol=symbol, reject_reason='atr_too_high',
                        scan_price=round(current_close, 2), atr_pct=round(atr_pct, 2),
                    )
                except Exception:
                    pass
                return None  # Too volatile for overnight
            elif atr_pct < self.MIN_ATR_PCT:
                # v7.5: Log ATR rejection
                try:
                    from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                    ScreenerRejectionRepository().log_rejection(
                        screener='ovn', symbol=symbol, reject_reason='atr_too_low',
                        scan_price=round(current_close, 2), atr_pct=round(atr_pct, 2),
                    )
                except Exception:
                    pass
                return None  # Not enough movement potential
        else:
            atr_pct = 3.0  # Default

        # 6. Sector regime bonus
        sector = ""
        sector_score_val = 0
        if sector_regime:
            try:
                sector = self._get_sector_from_cache(symbol)
                if sector:
                    regime = sector_regime.get_sector_regime(sector)
                    if regime == 'STRONG BULL':
                        sector_score_val = 10
                        score += 10
                        reasons.append(f"Sector STRONG BULL")
                    elif regime == 'BULL':
                        sector_score_val = 5
                        score += 5
                        reasons.append(f"Sector BULL")
                    elif regime in ('BEAR', 'STRONG BEAR'):
                        try:
                            from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                            ScreenerRejectionRepository().log_rejection(
                                screener='ovn', symbol=symbol, reject_reason='bear_sector',
                                scan_price=round(current_close, 2), sector=sector,
                            )
                        except Exception:
                            pass
                        return None  # Skip BEAR sectors
            except Exception:
                pass

        # 7. Price above SMA20 (bonus only, no penalty - overnight gap doesn't need uptrend)
        if len(close) >= 20:
            sma20 = float(np.mean(close[-20:]))
            if current_close > sma20:
                score += 10
                reasons.append("Above SMA20")
            # No penalty if below - overnight gap strategy works differently

        # Check minimum score
        if score < min_score:
            try:
                from database.repositories.screener_rejection_repository import ScreenerRejectionRepository
                ScreenerRejectionRepository().log_rejection(
                    screener='ovn', symbol=symbol, reject_reason='low_score',
                    scan_price=round(current_close, 2), score=score,
                    rsi=round(rsi, 1) if rsi else None,
                    atr_pct=round(atr_pct, 2) if atr_pct else None,
                    sector=sector or None,
                )
            except Exception:
                pass
            return None

        # Calculate entry/SL/TP
        entry_price = current_close
        stop_loss_price = round(entry_price * (1 - sl_pct / 100), 2)
        take_profit_price = round(entry_price * (1 + target_pct / 100), 2)
        risk_reward = target_pct / sl_pct if sl_pct > 0 else 0

        # Momentum calculations
        mom_5d = ((current_close / float(close[-5])) - 1) * 100 if len(close) >= 5 else 0
        mom_20d = ((current_close / float(close[-20])) - 1) * 100 if len(close) >= 20 else 0
        high_52w = float(np.max(close[-252:])) if len(close) >= 252 else float(np.max(close))
        dist_from_high = ((current_close / high_52w) - 1) * 100 if high_52w > 0 else 0

        sig = RapidRotationSignal(
            symbol=symbol,
            score=score,
            entry_price=entry_price,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
            risk_reward=round(risk_reward, 2),
            atr_pct=round(atr_pct, 2),
            rsi=round(rsi, 1) if rsi else 50.0,
            momentum_5d=round(mom_5d, 2),
            momentum_20d=round(mom_20d, 2),
            distance_from_high=round(dist_from_high, 2),
            reasons=reasons,
            sector=sector,
            market_regime="",
            sector_score=sector_score_val,
            alt_data_score=0,
            sl_method="overnight_gap_fixed",
            tp_method="overnight_gap_fixed",
            volume_ratio=round(vol_ratio, 2),
        )
        # v7.5: Attach close_to_high_pct for signal_outcomes logging
        sig.close_to_high_pct = round(close_to_high_pct, 2)
        return sig

    def _calculate_rsi(self, close, period: int = 14) -> Optional[float]:
        """Calculate RSI"""
        if len(close) < period + 1:
            return None
        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_atr_pct(self, high, low, close, period: int = 14) -> Optional[float]:
        """Calculate ATR as percentage of price"""
        if len(close) < period + 1:
            return None
        tr_values = []
        for i in range(-period, 0):
            h = float(high[i])
            l = float(low[i])
            c_prev = float(close[i - 1])
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)
        atr = np.mean(tr_values)
        current_price = float(close[-1])
        return (atr / current_price) * 100 if current_price > 0 else None

    def _get_sector_from_cache(self, symbol: str) -> str:
        """Get sector from universe DB cache (v6.73: no yfinance)."""
        return self._sector_cache.get(symbol, '')

    def _has_earnings_today(self, symbol: str) -> bool:
        """
        v7.5: Check if symbol has earnings TODAY (D=0).

        Uses earnings_calendar table directly — same source as PED screener.
        OVN holds overnight, so earnings D=0 = uncontrolled gap risk.
        """
        try:
            import sqlite3
            from pathlib import Path
            from datetime import date
            db_path = str(Path(__file__).resolve().parent.parent.parent / 'data' / 'trade_history.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT next_earnings_date FROM earnings_calendar WHERE symbol = ?",
                    (symbol,)
                ).fetchone()
                if row and row['next_earnings_date'] == date.today().isoformat():
                    return True
            finally:
                conn.close()
        except Exception:
            pass  # Fail-open: if DB unavailable, don't block
        return False
