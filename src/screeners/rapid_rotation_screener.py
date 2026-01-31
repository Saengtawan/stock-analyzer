#!/usr/bin/env python3
"""
RAPID ROTATION SCREENER v2.1 - ANTI-PDT Edition

Strategy:
- Buy TRUE DIPS only (mom_1d < 0, below SMA5)
- Skip gap-up days (gap > 1.5%)
- Dynamic SL based on ATR (1.5%-2.5%)
- Max 4-day hold (quick rotation)

v2.1 Anti-PDT Filters:
- FILTER 1: Mom 1d must be negative (true dip)
- FILTER 2: Skip gap-up entries > 1.5%
- FILTER 3: Price must be below SMA5
- FILTER 4: ATR-based SL (wider for volatile stocks)

Root Cause Analysis showed:
- 57% of losers hit SL same day (PDT risk!)
- Winners had mom_1d = -2.49%, Losers had +0.20%
- Losers bought after bounce, winners bought true dips
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import yfinance as yf


@dataclass
class RapidRotationSignal:
    """Signal for rapid rotation strategy"""
    symbol: str
    score: int
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    atr_pct: float
    rsi: float
    momentum_5d: float
    momentum_20d: float
    distance_from_high: float
    reasons: List[str]

    @property
    def expected_gain(self) -> float:
        return ((self.take_profit - self.entry_price) / self.entry_price) * 100

    @property
    def max_loss(self) -> float:
        return ((self.entry_price - self.stop_loss) / self.entry_price) * 100


class RapidRotationScreener:
    """
    Screener for rapid rotation strategy

    Looks for:
    1. High volatility stocks (ATR > 2%)
    2. Pullbacks in uptrends (dip buying)
    3. Quick profit opportunities (3-5% targets)
    """

    # Universe of high-volatility, liquid stocks
    DEFAULT_UNIVERSE = [
        # AI/Semiconductor - highest volatility
        'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
        'QCOM', 'AMAT', 'LRCX', 'KLAC',
        # High beta tech
        'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG',
        # Mega cap tech (still volatile)
        'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
        # Other high-beta
        'CRM', 'NOW', 'SHOP',
        # EV/Clean energy
        'RIVN', 'LCID', 'ENPH', 'FSLR',
    ]

    # Configuration
    MIN_ATR_PCT = 2.0  # Minimum volatility
    MIN_SCORE = 60  # Minimum score (lowered for more opportunities)

    # Exit parameters - APPROACH 2 (Tight SL)
    BASE_TP_PCT = 4.0  # Base take profit %
    BASE_SL_PCT = 1.5  # Base stop loss % - TIGHT! Cut losses fast
    MAX_HOLD_DAYS = 4  # Max 4 days - quick rotation

    def __init__(self, universe: List[str] = None):
        self.universe = universe or self.DEFAULT_UNIVERSE
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def load_data(self, days: int = 60) -> None:
        """Load historical data for universe"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)

        for symbol in self.universe:
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date.strftime('%Y-%m-%d'))
                if len(data) >= 30:
                    data.columns = [c.lower() for c in data.columns]
                    self.data_cache[symbol] = data
            except Exception as e:
                print(f"Error loading {symbol}: {e}")

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ATR"""
        high = data['high']
        low = data['low']
        close = data['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        return tr.rolling(period).mean()

    def analyze_stock(self, symbol: str) -> Optional[RapidRotationSignal]:
        """
        Analyze a single stock for rapid rotation opportunity

        Returns signal if criteria met, None otherwise
        """
        if symbol not in self.data_cache:
            return None

        data = self.data_cache[symbol]
        if len(data) < 30:
            return None

        idx = len(data) - 1
        close = data['close']
        high = data['high']
        low = data['low']
        volume = data['volume']

        current_price = close.iloc[idx]

        # Skip penny stocks and very expensive stocks
        if current_price < 20 or current_price > 1000:
            return None

        # Calculate indicators
        rsi = self.calculate_rsi(close).iloc[idx]
        atr = self.calculate_atr(data).iloc[idx]
        atr_pct = (atr / current_price) * 100

        # Momentum
        mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
        mom_10d = (current_price / close.iloc[idx-10] - 1) * 100 if idx >= 10 else 0
        mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0

        # SMAs
        sma20 = close.iloc[idx-20:idx].mean() if idx >= 20 else close.mean()
        sma50 = close.iloc[idx-50:idx].mean() if idx >= 50 else close.mean()

        # Distance from recent high
        high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.max()
        dist_from_high = (high_20d - current_price) / high_20d * 100

        # Volume
        avg_volume = volume.iloc[idx-20:idx].mean() if idx >= 20 else volume.mean()
        volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

        # Support level
        support = low.iloc[idx-10:idx].min() if idx >= 10 else low.min()

        # SMA5 for pullback detection
        sma5 = close.iloc[idx-5:idx].mean() if idx >= 5 else close.mean()

        # Gap calculation (vs previous close)
        prev_close = close.iloc[idx-1] if idx >= 1 else current_price
        open_price = data['open'].iloc[idx] if 'open' in data.columns else current_price
        gap_pct = (open_price - prev_close) / prev_close * 100

        # 1-day momentum (critical for same-day SL avoidance!)
        mom_1d = (current_price / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0

        # ==============================
        # ANTI-PDT FILTERS (v2.1)
        # ==============================
        # These filters prevent same-day SL hits

        # FILTER 1: Must be TRUE DIP (negative 1-day momentum)
        # Analysis showed: Winners avg mom_1d = -2.49%, Losers = +0.20%
        if mom_1d > 0.5:  # Don't buy if already bouncing up today
            return None

        # FILTER 2: Skip gap-up entries (often reverse same-day)
        if gap_pct > 1.5:
            return None

        # FILTER 3: Must be below SMA5 (real pullback)
        # Winners were 82% below SMA5, Losers only 63%
        if current_price > sma5 * 1.01:  # Allow 1% tolerance
            return None

        # ==============================
        # SCORING CRITERIA
        # ==============================
        score = 0
        reasons = []

        # 1. Must have minimum volatility
        if atr_pct < self.MIN_ATR_PCT:
            return None

        # 2. Pullback scoring (dip buying) - STRENGTHENED
        if -8 <= mom_5d <= -3:
            score += 35
            reasons.append(f"Strong dip {mom_5d:.1f}%")
        elif -3 < mom_5d <= 0:
            score += 25
            reasons.append(f"Mild pullback {mom_5d:.1f}%")
        # Removed "consolidating" - only buy dips, not flat

        # 2b. Extra points for true 1-day dip
        if mom_1d <= -1.5:
            score += 15
            reasons.append(f"Today dip {mom_1d:.1f}%")

        # 3. RSI scoring
        if 30 <= rsi <= 45:
            score += 30
            reasons.append(f"Oversold RSI={rsi:.0f}")
        elif 45 < rsi <= 55:
            score += 20
            reasons.append(f"Neutral RSI={rsi:.0f}")
        elif rsi < 30:
            score += 15  # Too oversold might continue falling
            reasons.append(f"Very oversold RSI={rsi:.0f}")

        # 4. Trend scoring
        if current_price > sma50 and mom_20d > 0:
            score += 20
            reasons.append("Strong uptrend")
        elif current_price > sma20:
            score += 15
            reasons.append("Above SMA20")
        elif mom_20d > 5:
            score += 10
            reasons.append("Recovery mode")

        # 5. Volatility bonus
        if atr_pct > 4:
            score += 15
            reasons.append(f"High volatility {atr_pct:.1f}%")
        elif atr_pct > 3:
            score += 10
            reasons.append(f"Good volatility {atr_pct:.1f}%")

        # 6. Room to run
        if 5 <= dist_from_high <= 15:
            score += 10
            reasons.append(f"Room to recover {dist_from_high:.0f}%")

        # 7. Volume confirmation
        if volume_ratio > 1.2:
            score += 5
            reasons.append("High volume")

        # Check minimum score
        if score < self.MIN_SCORE:
            return None

        # ==============================
        # CALCULATE SL/TP (v2.1 - ATR-based to avoid same-day stops)
        # ==============================

        # Dynamic TP based on ATR (higher volatility = higher target)
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = self.BASE_TP_PCT * tp_multiplier

        # DYNAMIC SL based on ATR to prevent same-day stops
        # High volatility stocks need wider SL
        if atr_pct > 5:
            sl_pct = 2.5  # Wide SL for very volatile
        elif atr_pct > 4:
            sl_pct = 2.0  # Medium-wide SL
        elif atr_pct > 3:
            sl_pct = 1.75  # Slightly wider
        else:
            sl_pct = self.BASE_SL_PCT  # Base 1.5%

        # Can also use support level if closer
        sl_from_support = (current_price - support * 0.995) / current_price * 100
        sl_pct = max(sl_pct, min(sl_from_support * 0.8, 2.5))  # Cap at 2.5%

        stop_loss = current_price * (1 - sl_pct / 100)
        take_profit = current_price * (1 + tp_pct / 100)

        risk_reward = tp_pct / sl_pct

        return RapidRotationSignal(
            symbol=symbol,
            score=score,
            entry_price=round(current_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_reward=round(risk_reward, 2),
            atr_pct=round(atr_pct, 2),
            rsi=round(rsi, 1),
            momentum_5d=round(mom_5d, 2),
            momentum_20d=round(mom_20d, 2),
            distance_from_high=round(dist_from_high, 2),
            reasons=reasons
        )

    def screen(self, top_n: int = 5) -> List[RapidRotationSignal]:
        """
        Screen universe for rapid rotation opportunities

        Returns top N signals sorted by score
        """
        if not self.data_cache:
            self.load_data()

        signals = []
        for symbol in self.universe:
            signal = self.analyze_stock(symbol)
            if signal:
                signals.append(signal)

        # Sort by score descending
        signals.sort(key=lambda x: x.score, reverse=True)

        return signals[:top_n]

    def get_portfolio_signals(self,
                              max_positions: int = 4,
                              existing_positions: List[str] = None) -> List[RapidRotationSignal]:
        """
        Get signals for portfolio management

        Args:
            max_positions: Maximum positions to hold
            existing_positions: Symbols already in portfolio

        Returns:
            List of signals to consider for entry
        """
        existing = set(existing_positions or [])

        signals = self.screen(top_n=10)

        # Filter out existing positions
        new_signals = [s for s in signals if s.symbol not in existing]

        # Return up to max_positions - current
        available_slots = max_positions - len(existing)

        return new_signals[:available_slots]


def main():
    """Run the screener"""
    print("=" * 70)
    print("RAPID ROTATION SCREENER")
    print("Target: 5%+/month through compounding small gains")
    print("=" * 70)
    print()

    screener = RapidRotationScreener()
    print("Loading data...")
    screener.load_data()
    print(f"Loaded {len(screener.data_cache)} stocks")
    print()

    signals = screener.screen(top_n=10)

    if not signals:
        print("No signals found today")
        return

    print(f"Found {len(signals)} signals:")
    print("-" * 70)
    print()

    for i, signal in enumerate(signals, 1):
        print(f"{i}. {signal.symbol} (Score: {signal.score})")
        print(f"   Entry: ${signal.entry_price:.2f}")
        print(f"   Stop Loss: ${signal.stop_loss:.2f} ({signal.max_loss:.1f}%)")
        print(f"   Take Profit: ${signal.take_profit:.2f} (+{signal.expected_gain:.1f}%)")
        print(f"   Risk/Reward: {signal.risk_reward:.2f}")
        print(f"   RSI: {signal.rsi:.0f} | 5d Mom: {signal.momentum_5d:+.1f}%")
        print(f"   ATR: {signal.atr_pct:.1f}% | Dist from High: {signal.distance_from_high:.1f}%")
        print(f"   Reasons: {', '.join(signal.reasons)}")
        print()

    print("=" * 70)
    print("EXIT RULES (v2.0 - Tight SL):")
    print("- Take Profit: Hit TP price (~4%)")
    print("- Stop Loss: 1.5% - cut losses FAST!")
    print("- Time Stop: Exit after 4 days max")
    print("- Trail: After +2.5%, trail at 60% of gains")
    print("=" * 70)


if __name__ == "__main__":
    main()
