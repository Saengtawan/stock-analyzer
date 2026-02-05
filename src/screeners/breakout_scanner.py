#!/usr/bin/env python3
"""
BREAKOUT SCANNER v1.0 (v4.9.4)

Scans for breakout continuation candidates.
Runs during morning (9:35 ET) and afternoon (14:00 ET) scans.

Criteria:
1. Price broke above 20-day high (today or yesterday)
2. Volume > 1.5x 20-day average
3. In BULL/STRONG BULL sector
4. RSI 50-70 (momentum but not overbought)
5. ATR% > 2% (enough volatility for profit)
6. Not extended > 5% above breakout level
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Optional
from loguru import logger


class BreakoutScanner:
    """
    Scan for breakout continuation candidates.
    Complementary to dip-bounce — catches upward momentum plays.
    """

    # Default parameters
    MIN_VOLUME_MULT = 1.5       # Volume > 1.5x 20-day average
    RSI_MIN = 50
    RSI_MAX = 70
    MIN_ATR_PCT = 2.0           # Minimum volatility
    MAX_EXTENSION_PCT = 5.0     # Not extended > 5% above breakout level
    LOOKBACK_DAYS = 20          # 20-day high breakout

    def __init__(self, data_manager=None):
        """
        Args:
            data_manager: Optional data cache dict {symbol: DataFrame}
        """
        self.data_cache = data_manager or {}

    def scan(self, universe: dict = None, sector_regime=None,
             min_score: int = 75, min_volume_mult: float = 1.5,
             target_pct: float = 8.0, sl_pct: float = 3.0) -> List:
        """
        Scan for breakout candidates.

        Args:
            universe: Dict of {symbol: DataFrame} with OHLCV data
            sector_regime: SectorRegimeDetector instance
            min_score: Minimum score threshold
            min_volume_mult: Minimum volume multiplier
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
            logger.warning("BreakoutScanner: No data available")
            return []

        candidates = []

        for symbol, df in data.items():
            try:
                signal = self._analyze_stock(
                    symbol, df, sector_regime,
                    min_score, min_volume_mult, target_pct, sl_pct
                )
                if signal:
                    candidates.append(signal)
            except Exception as e:
                logger.debug(f"Breakout: Error analyzing {symbol}: {e}")

        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)

        if candidates:
            logger.info(f"Breakout: Found {len(candidates)} candidates")
        else:
            logger.info("Breakout: No candidates found")

        return candidates[:5]  # Top 5

    def _analyze_stock(self, symbol: str, df: pd.DataFrame,
                       sector_regime=None, min_score: int = 75,
                       min_volume_mult: float = 1.5,
                       target_pct: float = 8.0, sl_pct: float = 3.0):
        """Analyze a single stock for breakout potential."""
        try:
            from screeners.rapid_rotation_screener import RapidRotationSignal
        except ImportError:
            from src.screeners.rapid_rotation_screener import RapidRotationSignal

        if df is None or len(df) < 25:
            return None

        # Get arrays (support both 'close' and 'Close' column names)
        def get_col(df, name):
            if name.lower() in df.columns:
                return df[name.lower()].values
            elif name in df.columns:
                return df[name].values
            return None

        close = get_col(df, 'Close')
        high = get_col(df, 'High')
        low = get_col(df, 'Low')
        volume = get_col(df, 'Volume')

        if close is None or high is None or volume is None:
            return None

        current_close = float(close[-1])
        current_high = float(high[-1])

        if current_close <= 0:
            return None

        # --- Core breakout check ---
        # 20-day high (excluding today)
        lookback = min(self.LOOKBACK_DAYS, len(high) - 1)
        if lookback < 10:
            return None

        prior_high_20d = float(np.max(high[-(lookback + 1):-1]))

        # Must break above 20-day high
        if current_high < prior_high_20d:
            # Check if yesterday broke out (continuation)
            if len(high) >= 2 and float(high[-2]) >= prior_high_20d:
                breakout_level = prior_high_20d
            else:
                return None  # No breakout
        else:
            breakout_level = prior_high_20d

        # Check not too extended above breakout
        extension_pct = ((current_close / breakout_level) - 1) * 100
        if extension_pct > self.MAX_EXTENSION_PCT:
            return None  # Too extended

        # --- Scoring ---
        score = 0
        reasons = []

        # 1. Breakout confirmed (base score)
        score += 30
        reasons.append(f"Breakout above 20d high ${breakout_level:.2f} (+{extension_pct:.1f}%)")

        # 2. Volume confirmation
        avg_volume_20 = float(np.mean(volume[-20:])) if len(volume) >= 20 else float(np.mean(volume))
        if avg_volume_20 > 0:
            vol_ratio = float(volume[-1]) / avg_volume_20
            if vol_ratio >= min_volume_mult:
                vol_score = min(int(vol_ratio * 10), 25)
                score += vol_score
                reasons.append(f"Vol {vol_ratio:.1f}x avg")
            else:
                return None  # Must have volume confirmation

        # 3. RSI check (50-70 = momentum but not overbought)
        rsi = self._calculate_rsi(close)
        if rsi is not None:
            if self.RSI_MIN <= rsi <= self.RSI_MAX:
                score += 15
                reasons.append(f"RSI {rsi:.0f}")
            elif rsi > 75:
                return None  # Too overbought for breakout entry
            elif rsi < 45:
                score -= 5  # Weak momentum

        # 4. ATR check
        atr_pct = self._calculate_atr_pct(high, low, close)
        if atr_pct is not None:
            if atr_pct >= self.MIN_ATR_PCT:
                score += 10
                reasons.append(f"ATR {atr_pct:.1f}%")
            else:
                return None  # Not enough volatility
        else:
            atr_pct = 3.0

        # 5. Sector regime bonus
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
                        reasons.append("Sector STRONG BULL")
                    elif regime == 'BULL':
                        sector_score_val = 5
                        score += 5
                        reasons.append("Sector BULL")
                    elif regime in ('BEAR', 'STRONG BEAR'):
                        return None  # Skip BEAR sectors
            except Exception:
                pass

        # 6. Price above SMA20 (should be, since breaking out)
        if len(close) >= 20:
            sma20 = float(np.mean(close[-20:]))
            if current_close > sma20:
                score += 5
                reasons.append("Above SMA20")

        # 7. Momentum bonus
        mom_5d = ((current_close / float(close[-5])) - 1) * 100 if len(close) >= 5 else 0
        if mom_5d > 2:
            score += 5
            reasons.append(f"Mom 5d +{mom_5d:.1f}%")

        # Check minimum score
        if score < min_score:
            return None

        # Calculate entry/SL/TP
        entry_price = current_close
        # SL just below breakout level (logical support)
        sl_from_breakout = ((entry_price - breakout_level) / entry_price) * 100 + 1.0
        actual_sl_pct = max(sl_pct, sl_from_breakout)  # At least sl_pct or below breakout
        actual_sl_pct = min(actual_sl_pct, 5.0)  # Cap at 5%

        stop_loss_price = round(entry_price * (1 - actual_sl_pct / 100), 2)
        take_profit_price = round(entry_price * (1 + target_pct / 100), 2)
        risk_reward = target_pct / actual_sl_pct if actual_sl_pct > 0 else 0

        mom_20d = ((current_close / float(close[-20])) - 1) * 100 if len(close) >= 20 else 0
        high_52w = float(np.max(close[-252:])) if len(close) >= 252 else float(np.max(close))
        dist_from_high = ((current_close / high_52w) - 1) * 100 if high_52w > 0 else 0

        return RapidRotationSignal(
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
            sl_method="breakout_level",
            tp_method="breakout_target",
            volume_ratio=round(vol_ratio, 2),
        )

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
        """Get sector from yfinance info (cached)"""
        if not hasattr(self, '_sector_cache'):
            self._sector_cache = {}
        if symbol in self._sector_cache:
            return self._sector_cache[symbol]
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            sector = info.get('sector', '')
            self._sector_cache[symbol] = sector
            return sector
        except Exception:
            return ''
