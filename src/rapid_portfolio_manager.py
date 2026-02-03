#!/usr/bin/env python3
"""
RAPID PORTFOLIO MANAGER v4.6 - ATR-BASED SL/TP

v4.6 Changes - ATR-BASED DYNAMIC SL/TP:
- SL: 1.5×ATR (clamped 2%-4%) per position
- TP: 3×ATR (clamped 4%-8%) per position
- PDT TP: = SL% (R:R 1:1 minimum for Day 0 sells)
- Trail Activation: 3% (unchanged)
- Trail Lock: 80% (unchanged)
- Each position stores its own sl_pct, tp_pct, atr_pct

Design: Engine = source of truth, Portfolio Manager = display + monitor

Exit Signals:
🔴 CRITICAL - ต้องขายทันที (ถึง SL)
🟠 WARNING - เตรียมขาย
🟡 WATCH - จับตาดู
✅ HOLD - ถือต่อ
🎯 TAKE_PROFIT - ถึงเป้า
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import yfinance as yf
import pandas as pd
import numpy as np


class ExitSignal(Enum):
    """Exit signal levels"""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    WATCH = "WATCH"
    HOLD = "HOLD"
    TAKE_PROFIT = "TAKE_PROFIT"


@dataclass
class Position:
    """Position in portfolio with ATR-based SL/TP tracking (v4.6)"""
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    initial_stop_loss: float    # SL ตอน entry
    current_stop_loss: float    # SL ปัจจุบัน (dynamic)
    take_profit: float          # TP ปัจจุบัน (dynamic)
    cost_basis: float
    highest_price: float        # ราคาสูงสุดที่เคยถึง
    trailing_active: bool = False  # Trailing เริ่มทำงานแล้ว?
    initial_take_profit: float = 0.0  # TP ตอน entry (v3.4)
    # v4.6: Per-position ATR-based SL/TP
    sl_pct: float = 2.5         # SL% for this position
    tp_pct: float = 5.0         # TP% for this position
    atr_pct: float = 0.0        # ATR% at entry time

    @property
    def position_value(self) -> float:
        return self.shares * self.entry_price


@dataclass
class PositionStatus:
    """Current status of a position"""
    symbol: str
    entry_price: float
    current_price: float
    highest_price: float
    pnl_pct: float
    pnl_usd: float
    days_held: int
    signal: ExitSignal
    reasons: List[str]
    action: str
    new_candidates: List[str]
    # v3.3: Dynamic SL info
    initial_sl: float
    current_sl: float
    sl_updated: bool
    trailing_active: bool
    # v3.4: Dynamic TP info
    initial_tp: float = 0.0
    current_tp: float = 0.0
    tp_updated: bool = False


class RapidPortfolioManager:
    """
    Portfolio Manager v4.6 - ATR-BASED SL/TP

    ATR-based per-position SL/TP (same as auto_trading_engine.py v4.6)
    - SL: 1.5×ATR (clamped 2%-4%) per position
    - TP: 3×ATR (clamped 4%-8%) per position
    - Trailing: +3% activation, lock 80% of gains
    - Max Hold: 5 calendar days
    """

    # Use absolute path to project root for portfolio file
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    PORTFOLIO_FILE = os.path.join(PROJECT_ROOT, "rapid_portfolio.json")

    # v4.6: ATR-based SL/TP (fallback defaults)
    SL_ATR_MULTIPLIER = 1.5      # SL = 1.5 × ATR
    SL_MIN_PCT = 2.0             # Minimum SL%
    SL_MAX_PCT = 4.0             # Maximum SL%
    TP_ATR_MULTIPLIER = 3.0      # TP = 3 × ATR
    TP_MIN_PCT = 4.0             # Minimum TP%
    TP_MAX_PCT = 8.0             # Maximum TP%
    STOP_LOSS_PCT = 2.5          # Fallback fixed SL%
    TAKE_PROFIT_PCT = 5.0        # Fallback fixed TP%
    TRAIL_ACTIVATION_PCT = 3.0   # Start trailing at +3% gain
    TRAIL_PERCENT = 80           # Lock 80% of peak gains
    MAX_HOLD_DAYS = 5            # Max hold days before force exit

    def __init__(self, portfolio_file: str = None):
        self.portfolio_file = portfolio_file or self.PORTFOLIO_FILE
        self.positions: Dict[str, Position] = {}
        self.load_portfolio()

    def load_portfolio(self) -> None:
        """Load portfolio from file"""
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, 'r') as f:
                    data = json.load(f)
                    for symbol, pos_data in data.get('positions', {}).items():
                        # Handle old format without new fields
                        if 'initial_stop_loss' not in pos_data:
                            pos_data['initial_stop_loss'] = pos_data.get('stop_loss', pos_data['entry_price'] * 0.975)  # v3.6: 2.5% SL
                        if 'current_stop_loss' not in pos_data:
                            pos_data['current_stop_loss'] = pos_data.get('stop_loss', pos_data['initial_stop_loss'])
                        if 'highest_price' not in pos_data:
                            pos_data['highest_price'] = pos_data['entry_price']
                        if 'trailing_active' not in pos_data:
                            pos_data['trailing_active'] = False
                        # v3.4: Handle initial_take_profit for old positions
                        if 'initial_take_profit' not in pos_data:
                            pos_data['initial_take_profit'] = pos_data.get('take_profit', pos_data['entry_price'] * 1.06)
                        # v4.6: Handle per-position ATR fields
                        if 'sl_pct' not in pos_data:
                            pos_data['sl_pct'] = 2.5
                        if 'tp_pct' not in pos_data:
                            pos_data['tp_pct'] = 5.0
                        if 'atr_pct' not in pos_data:
                            pos_data['atr_pct'] = 0.0
                        # Remove old 'stop_loss' field if exists
                        pos_data.pop('stop_loss', None)
                        self.positions[symbol] = Position(**pos_data)
            except Exception as e:
                print(f"Error loading portfolio: {e}")

    def save_portfolio(self) -> None:
        """Save portfolio to file"""
        data = {
            'positions': {s: asdict(p) for s, p in self.positions.items()},
            'last_updated': datetime.now().isoformat()
        }
        with open(self.portfolio_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def add_position(self, symbol: str, shares: int, entry_price: float,
                     stop_loss: float = None, take_profit: float = None,
                     sl_pct: float = None, tp_pct: float = None,
                     atr_pct: float = None) -> None:
        """
        Add new position with ATR-based SL/TP (v4.6)

        If sl_pct/tp_pct provided (from engine), use those.
        Otherwise calculate ATR-based or use fallback fixed values.
        """
        # v4.6: Use provided per-position percentages or fallback
        pos_sl_pct = sl_pct or self.STOP_LOSS_PCT
        pos_tp_pct = tp_pct or self.TAKE_PROFIT_PCT
        pos_atr_pct = atr_pct or 0.0

        if stop_loss is None:
            stop_loss = round(entry_price * (1 - pos_sl_pct / 100), 2)
        if take_profit is None:
            take_profit = round(entry_price * (1 + pos_tp_pct / 100), 2)

        self.positions[symbol] = Position(
            symbol=symbol,
            entry_date=datetime.now().strftime('%Y-%m-%d'),
            entry_price=entry_price,
            shares=shares,
            initial_stop_loss=stop_loss,
            current_stop_loss=stop_loss,
            take_profit=take_profit,
            cost_basis=shares * entry_price,
            highest_price=entry_price,
            trailing_active=False,
            initial_take_profit=take_profit,
            sl_pct=pos_sl_pct,
            tp_pct=pos_tp_pct,
            atr_pct=pos_atr_pct
        )
        self.save_portfolio()

        print(f"✅ Added: {symbol} x{shares} @ ${entry_price:.2f}")
        print(f"   SL: ${stop_loss:.2f} (-{pos_sl_pct:.1f}%)")
        print(f"   TP: ${take_profit:.2f} (+{pos_tp_pct:.1f}%)")
        if pos_atr_pct > 0:
            print(f"   ATR: {pos_atr_pct:.1f}% (SL={self.SL_ATR_MULTIPLIER}x, TP={self.TP_ATR_MULTIPLIER}x)")
        print(f"   Trailing: +{self.TRAIL_ACTIVATION_PCT}% → lock {self.TRAIL_PERCENT}%")

    def remove_position(self, symbol: str) -> Optional[Position]:
        """Remove position"""
        if symbol in self.positions:
            pos = self.positions.pop(symbol)
            self.save_portfolio()
            return pos
        return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if len(data) > 0:
                return data['Close'].iloc[-1]
        except:
            pass
        return None

    def get_stock_data(self, symbol: str, days: int = 30) -> Optional[pd.DataFrame]:
        """Get historical data for dynamic calculations"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=f'{days}d')
            if len(data) >= 10:
                data.columns = [c.lower() for c in data.columns]
                return data
        except:
            pass
        return None

    def calculate_dynamic_sl(self, symbol: str, current_price: float,
                             highest_price: float, entry_price: float) -> Dict:
        """
        Calculate dynamic stop loss based on multiple factors

        Returns:
            Dict with:
            - atr_based_sl: SL based on ATR
            - swing_low_sl: SL based on recent swing low
            - ma_based_sl: SL based on EMA
            - recommended_sl: Best SL to use
            - trailing_distance: Distance from high
        """
        data = self.get_stock_data(symbol)
        if data is None or len(data) < 14:
            # Fallback: use 2.5% from highest (v3.6 tight SL)
            fallback_sl = highest_price * 0.975
            return {
                'atr_based_sl': fallback_sl,
                'swing_low_sl': fallback_sl,
                'ma_based_sl': fallback_sl,
                'recommended_sl': fallback_sl,
                'trailing_distance_pct': 2.5,
                'method': 'fallback'
            }

        close = data['close']
        high = data['high']
        low = data['low']

        # 1. ATR-based SL
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / current_price) * 100

        trailing_distance = atr * self.ATR_MULTIPLIER
        atr_based_sl = highest_price - trailing_distance

        # 2. Swing Low based SL (last 5-10 days)
        swing_low_5d = low.iloc[-5:].min()
        swing_low_10d = low.iloc[-10:].min()
        # Use tighter of the two (5d swing low)
        swing_low_sl = swing_low_5d * 0.995  # Slightly below swing low

        # 3. EMA based SL
        ema5 = close.ewm(span=5).mean().iloc[-1]
        ema10 = close.ewm(span=10).mean().iloc[-1]
        # Trail below EMA5 or EMA10 depending on trend strength
        if current_price > ema5:
            ma_based_sl = ema5 * 0.99  # 1% below EMA5
        else:
            ma_based_sl = ema10 * 0.98  # 2% below EMA10

        # 4. Choose best SL (highest = tightest protection)
        all_sls = [atr_based_sl, swing_low_sl, ma_based_sl]
        recommended_sl = max(all_sls)

        # But don't trail tighter than 1.5% from current price
        min_distance = current_price * 0.015
        if current_price - recommended_sl < min_distance:
            recommended_sl = current_price - min_distance

        # Also don't go below entry price if in profit
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        if pnl_pct > 3:
            # If profit > 3%, SL should at least be at breakeven
            recommended_sl = max(recommended_sl, entry_price * 1.005)

        trailing_distance_pct = ((highest_price - recommended_sl) / highest_price) * 100

        # Determine which method gave the highest SL
        if recommended_sl == atr_based_sl:
            method = f'ATR ({atr_pct:.1f}%)'
        elif recommended_sl == swing_low_sl:
            method = f'Swing Low ${swing_low_5d:.2f}'
        else:
            method = f'EMA ({ema5:.2f})'

        return {
            'atr_based_sl': round(atr_based_sl, 2),
            'swing_low_sl': round(swing_low_sl, 2),
            'ma_based_sl': round(ma_based_sl, 2),
            'recommended_sl': round(recommended_sl, 2),
            'trailing_distance_pct': round(trailing_distance_pct, 2),
            'atr_pct': round(atr_pct, 2),
            'method': method
        }

    def calculate_dynamic_tp(self, symbol: str, current_price: float,
                              highest_price: float, entry_price: float) -> Dict:
        """
        Calculate dynamic take profit based on multiple factors (v3.4)

        Returns:
            Dict with:
            - atr_based_tp: TP based on ATR × 3
            - resistance_tp: TP based on resistance level
            - trailing_tp: TP based on trailing high
            - recommended_tp: Best TP to use
            - method: Which method was used
        """
        data = self.get_stock_data(symbol)
        if data is None or len(data) < 20:
            # Fallback: use current TP + 2%
            fallback_tp = highest_price * 1.06
            return {
                'atr_based_tp': fallback_tp,
                'resistance_tp': fallback_tp,
                'trailing_tp': fallback_tp,
                'recommended_tp': fallback_tp,
                'method': 'fallback'
            }

        close = data['close']
        high = data['high']
        low = data['low']

        # Calculate ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # 1. ATR-based TP (ATR × 3 from current price)
        atr_based_tp = current_price + (atr * 3)

        # 2. Resistance-based TP (swing high 20 days)
        swing_high_20d = high.iloc[-20:].max()
        resistance_tp = swing_high_20d * 0.995  # Just below resistance

        # 3. 52-week high as cap
        high_52w = high.max()
        high_52w_tp = high_52w * 0.98

        # 4. Trailing TP (extend target as price rises)
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        if pnl_pct > 5:
            # If already up 5%, add ATR × 2 to current price
            trailing_tp = current_price + (atr * 2)
        else:
            trailing_tp = atr_based_tp

        # Choose LOWEST TP = most realistic target
        all_tps = [atr_based_tp, resistance_tp, high_52w_tp, trailing_tp]
        recommended_tp = min(all_tps)

        # But ensure TP is at least 4% above current price
        min_tp = current_price * 1.04
        if recommended_tp < min_tp:
            recommended_tp = min_tp

        # And cap at +15% from entry
        max_tp = entry_price * 1.15
        if recommended_tp > max_tp:
            recommended_tp = max_tp

        # Determine which method gave the TP
        if recommended_tp == atr_based_tp:
            method = f'ATR×3'
        elif recommended_tp == resistance_tp:
            method = f'Resistance ${swing_high_20d:.2f}'
        elif recommended_tp == trailing_tp:
            method = 'Trailing'
        else:
            method = '52wHigh'

        return {
            'atr_based_tp': round(atr_based_tp, 2),
            'resistance_tp': round(resistance_tp, 2),
            'trailing_tp': round(trailing_tp, 2),
            'recommended_tp': round(recommended_tp, 2),
            'method': method
        }

    def update_position_sl_tp(self, symbol: str, current_price: float) -> Dict:
        """
        Update position's SL using simple trailing stop (v4.6)

        Synced with auto_trading_engine.py:
        - SL: Per-position ATR-based (until trailing activates)
        - Trailing: +3% activation, lock 80% of gains
        - TP: Per-position ATR-based (never changes after entry)

        Returns:
            Dict with sl_updated, tp_updated, new_sl, new_tp
        """
        if symbol not in self.positions:
            return {'sl_updated': False, 'tp_updated': False, 'new_sl': 0, 'new_tp': 0}

        pos = self.positions[symbol]
        sl_updated = False
        new_sl = pos.current_stop_loss

        # Update peak price
        if current_price > pos.highest_price:
            pos.highest_price = current_price

        # Calculate P&L from entry
        pnl_pct = ((pos.highest_price - pos.entry_price) / pos.entry_price) * 100

        # v4.5: Simple trailing stop (same as engine)
        if pnl_pct >= self.TRAIL_ACTIVATION_PCT:
            pos.trailing_active = True

            # Trailing SL = entry + (gain × lock_pct)
            gain_from_entry = pos.highest_price - pos.entry_price
            trailing_sl = pos.entry_price + (gain_from_entry * self.TRAIL_PERCENT / 100)

            # SL can only go UP (never reduce protection)
            if trailing_sl > pos.current_stop_loss:
                pos.current_stop_loss = round(trailing_sl, 2)
                new_sl = pos.current_stop_loss
                sl_updated = True

        # Save if anything changed
        if sl_updated or current_price > pos.highest_price:
            self.save_portfolio()

        return {
            'sl_updated': sl_updated,
            'tp_updated': False,  # v4.5: TP never changes
            'new_sl': new_sl,
            'new_tp': pos.take_profit
        }

    def analyze_position(self, symbol: str) -> Optional[PositionStatus]:
        """
        Analyze a position with dynamic SL/TP

        v3.4: Auto-updates both SL and TP when checking
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        current_price = self.get_current_price(symbol)

        if current_price is None:
            return None

        # v3.4: Auto-update SL and TP on check
        update_result = self.update_position_sl_tp(symbol, current_price)
        sl_updated = update_result['sl_updated']
        tp_updated = update_result['tp_updated']

        # Calculate P&L
        pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
        pnl_usd = (current_price - pos.entry_price) * pos.shares

        # Calculate days held
        entry_date = datetime.strptime(pos.entry_date, '%Y-%m-%d')
        days_held = (datetime.now() - entry_date).days

        # Determine exit signal
        signal = ExitSignal.HOLD
        reasons = []
        action = "HOLD"
        new_candidates = []

        # 1. TAKE PROFIT
        if current_price >= pos.take_profit:
            signal = ExitSignal.TAKE_PROFIT
            reasons.append(f"Hit TP ${pos.take_profit:.2f}")
            action = "🎯 SELL - ถึงเป้า!"
            new_candidates = self._get_replacement_candidates(symbol)

        # 2. STOP LOSS (using current dynamic SL)
        elif current_price <= pos.current_stop_loss:
            signal = ExitSignal.CRITICAL
            if pos.trailing_active:
                reasons.append(f"Hit Trailing SL ${pos.current_stop_loss:.2f}")
                action = "🔴 SELL - Trailing Stop!"
            else:
                reasons.append(f"Hit SL ${pos.current_stop_loss:.2f}")
                action = "🔴 SELL NOW!"
            new_candidates = self._get_replacement_candidates(symbol)

        # 3. TIME STOP
        elif days_held >= self.MAX_HOLD_DAYS and pnl_pct < 1:
            signal = ExitSignal.WARNING
            reasons.append(f"Held {days_held} days, only +{pnl_pct:.1f}%")
            action = "🟠 SELL - Rotation"
            new_candidates = self._get_replacement_candidates(symbol)

        # 4. WARNING - Close to SL
        elif current_price <= pos.current_stop_loss * 1.01:
            signal = ExitSignal.WARNING
            reasons.append(f"Very close to SL ${pos.current_stop_loss:.2f}")
            action = "🟠 WATCH CLOSELY"

        # 5. TRAILING ACTIVE - Show info
        elif pos.trailing_active:
            signal = ExitSignal.HOLD
            trail_distance = ((pos.highest_price - pos.current_stop_loss) / pos.highest_price) * 100
            reasons.append(f"Trailing active ({trail_distance:.1f}% from high)")
            action = f"✅ HOLD - Trailing SL ${pos.current_stop_loss:.2f}"

        # 6. HOLD
        else:
            signal = ExitSignal.HOLD
            if pnl_pct > 0:
                reasons.append(f"Profit +{pnl_pct:.1f}%")
                action = "✅ HOLD"
            else:
                reasons.append("Within tolerance")
                action = "✅ HOLD"

        # Add SL/TP update info
        if sl_updated:
            reasons.append(f"📈 SL raised to ${pos.current_stop_loss:.2f}")
        if tp_updated:
            reasons.append(f"🎯 TP raised to ${pos.take_profit:.2f}")

        # Get initial TP (handle old positions without it)
        initial_tp = getattr(pos, 'initial_take_profit', pos.take_profit)
        if initial_tp == 0:
            initial_tp = pos.take_profit

        return PositionStatus(
            symbol=symbol,
            entry_price=pos.entry_price,
            current_price=round(current_price, 2),
            highest_price=round(pos.highest_price, 2),
            pnl_pct=round(pnl_pct, 2),
            pnl_usd=round(pnl_usd, 2),
            days_held=days_held,
            signal=signal,
            reasons=reasons,
            action=action,
            new_candidates=new_candidates,
            initial_sl=round(pos.initial_stop_loss, 2),
            current_sl=round(pos.current_stop_loss, 2),
            sl_updated=sl_updated,
            trailing_active=pos.trailing_active,
            # v3.4: TP info
            initial_tp=round(initial_tp, 2),
            current_tp=round(pos.take_profit, 2),
            tp_updated=tp_updated
        )

    def _get_replacement_candidates(self, exclude_symbol: str) -> List[str]:
        """Get candidates to replace sold position"""
        try:
            from screeners.rapid_rotation_screener import RapidRotationScreener
            screener = RapidRotationScreener()
            screener.load_data()

            existing = list(self.positions.keys())
            signals = screener.get_portfolio_signals(
                max_positions=4,
                existing_positions=existing + [exclude_symbol]
            )

            return [s.symbol for s in signals[:3]]
        except:
            return []

    def check_all_positions(self) -> List[PositionStatus]:
        """
        Check all positions and return statuses

        v3.3: Auto-updates SL for all positions
        """
        statuses = []
        for symbol in self.positions:
            status = self.analyze_position(symbol)
            if status:
                statuses.append(status)

        # Sort by urgency
        priority = {
            ExitSignal.CRITICAL: 0,
            ExitSignal.WARNING: 1,
            ExitSignal.WATCH: 2,
            ExitSignal.TAKE_PROFIT: 3,
            ExitSignal.HOLD: 4
        }
        statuses.sort(key=lambda x: priority.get(x.signal, 5))

        return statuses

    def get_portfolio_summary(self) -> Dict:
        """Get overall portfolio summary"""
        if not self.positions:
            return {'status': 'empty', 'positions': 0}

        total_cost = sum(p.cost_basis for p in self.positions.values())
        current_values = []
        pnls = []

        for symbol, pos in self.positions.items():
            price = self.get_current_price(symbol)
            if price:
                current_values.append(price * pos.shares)
                pnls.append((price - pos.entry_price) / pos.entry_price * 100)

        total_value = sum(current_values) if current_values else 0
        total_pnl_pct = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0
        total_pnl_usd = total_value - total_cost

        # Count trailing active
        trailing_count = sum(1 for p in self.positions.values() if p.trailing_active)

        return {
            'positions': len(self.positions),
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_pnl_usd': round(total_pnl_usd, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'avg_pnl_pct': round(sum(pnls) / len(pnls), 2) if pnls else 0,
            'trailing_active': trailing_count,
        }


def main():
    """Run portfolio check"""
    print("=" * 70)
    print("🚀 RAPID PORTFOLIO MANAGER v4.6 - ATR-BASED SL/TP")
    print("=" * 70)
    print()
    print("v4.6 Features:")
    print("  - SL: 1.5×ATR (clamped 2%-4%) per position")
    print("  - TP: 3×ATR (clamped 4%-8%) per position")
    print("  - Trail: +3% activation, lock 80%")
    print("  - PDT TP = SL% (R:R 1:1 minimum)")
    print()

    manager = RapidPortfolioManager()

    if not manager.positions:
        print("ไม่มี Position ใน Portfolio")
        print()
        print("วิธีเพิ่ม Position:")
        print("  manager.add_position('NVDA', shares=10, entry_price=180.00,")
        print("                       stop_loss=173.70, take_profit=190.80)")
        return

    # Get summary
    summary = manager.get_portfolio_summary()
    print(f"📊 PORTFOLIO SUMMARY")
    print("-" * 50)
    print(f"Positions: {summary['positions']}")
    print(f"Trailing Active: {summary['trailing_active']}")
    print(f"Total Cost: ${summary['total_cost']:,.2f}")
    print(f"Current Value: ${summary['total_value']:,.2f}")
    print(f"Total P&L: ${summary['total_pnl_usd']:+,.2f} ({summary['total_pnl_pct']:+.2f}%)")
    print()

    # Check all positions
    print("📋 POSITION STATUS (SL updates automatically)")
    print("-" * 50)
    print()

    statuses = manager.check_all_positions()

    for status in statuses:
        icon = {
            ExitSignal.CRITICAL: "🔴",
            ExitSignal.WARNING: "🟠",
            ExitSignal.WATCH: "🟡",
            ExitSignal.TAKE_PROFIT: "🎯",
            ExitSignal.HOLD: "✅"
        }.get(status.signal, "⚪")

        print(f"{icon} {status.symbol}")
        print(f"   Entry: ${status.entry_price:.2f} → Current: ${status.current_price:.2f}")
        print(f"   Highest: ${status.highest_price:.2f}")
        print(f"   P&L: {status.pnl_pct:+.2f}% (${status.pnl_usd:+.2f})")
        print(f"   Days Held: {status.days_held}")

        # Show SL info
        if status.trailing_active:
            print(f"   📈 TRAILING ACTIVE")
            print(f"   SL: ${status.initial_sl:.2f} → ${status.current_sl:.2f} (updated)")
        else:
            print(f"   SL: ${status.current_sl:.2f}")

        print(f"   Action: {status.action}")
        if status.reasons:
            print(f"   Reasons: {', '.join(status.reasons)}")
        if status.new_candidates:
            print(f"   💡 Replace with: {', '.join(status.new_candidates)}")
        print()

    # Critical alerts
    criticals = [s for s in statuses if s.signal == ExitSignal.CRITICAL]
    if criticals:
        print("=" * 70)
        print("⚠️  CRITICAL ALERTS - ต้องขายทันที!")
        print("=" * 70)
        for s in criticals:
            print(f"  🔴 {s.symbol}: {s.action}")
            print(f"     Loss: {s.pnl_pct:.2f}%")
            if s.new_candidates:
                print(f"     → Replace with: {', '.join(s.new_candidates)}")
        print()


if __name__ == "__main__":
    main()
