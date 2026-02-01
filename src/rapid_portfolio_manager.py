#!/usr/bin/env python3
"""
RAPID PORTFOLIO MANAGER v3.3 - DYNAMIC TRAILING STOP

v3.3 Changes - TRUE DYNAMIC SL/TRAILING:
- SL ปรับตาม ATR (volatile มาก = trail กว้าง)
- Trail ตาม swing low ล่าสุด (structure-based)
- Trail ใต้ EMA 5/10 (MA-based)
- Auto-update SL ทุกครั้งที่ check positions
- แสดง SL เดิม vs SL ปัจจุบันใน UI

หลักการ Dynamic Trailing:
1. เมื่อราคาขึ้น → Update highest_price
2. คำนวณ trailing distance = MAX(ATR*2, ต่ำกว่า swing low, ใต้ EMA5)
3. SL ใหม่ = highest_price - trailing_distance
4. SL ใหม่ต้องสูงกว่า SL เดิมเสมอ (ไม่ลด SL)

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
    """Position in portfolio with dynamic SL tracking"""
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    initial_stop_loss: float    # SL ตอน entry
    current_stop_loss: float    # SL ปัจจุบัน (dynamic)
    take_profit: float
    cost_basis: float
    highest_price: float        # ราคาสูงสุดที่เคยถึง
    trailing_active: bool = False  # Trailing เริ่มทำงานแล้ว?

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


class RapidPortfolioManager:
    """
    Portfolio Manager v3.3 - DYNAMIC TRAILING STOP

    Dynamic SL Logic:
    1. ATR-based: trailing distance = 2 x ATR (ปรับตามความผันผวน)
    2. Structure-based: ใช้ swing low ล่าสุดเป็น reference
    3. MA-based: trail ใต้ EMA 5

    SL จะ update อัตโนมัติ:
    - เมื่อราคาทำ new high → คำนวณ SL ใหม่
    - SL ใหม่ต้องสูงกว่า SL เดิมเสมอ
    """

    PORTFOLIO_FILE = "rapid_portfolio.json"

    # v3.3: Dynamic parameters
    TRAIL_ACTIVATION_PCT = 3.0   # เริ่ม trailing หลังกำไร 3%
    ATR_MULTIPLIER = 2.0         # Trail distance = ATR * 2
    MAX_HOLD_DAYS = 5

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
                            pos_data['initial_stop_loss'] = pos_data.get('stop_loss', pos_data['entry_price'] * 0.965)
                        if 'current_stop_loss' not in pos_data:
                            pos_data['current_stop_loss'] = pos_data.get('stop_loss', pos_data['initial_stop_loss'])
                        if 'highest_price' not in pos_data:
                            pos_data['highest_price'] = pos_data['entry_price']
                        if 'trailing_active' not in pos_data:
                            pos_data['trailing_active'] = False
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
                     stop_loss: float, take_profit: float) -> None:
        """Add new position with dynamic SL tracking"""
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
            trailing_active=False
        )
        self.save_portfolio()

        sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        tp_pct = ((take_profit - entry_price) / entry_price) * 100

        print(f"✅ Added: {symbol} x{shares} @ ${entry_price:.2f}")
        print(f"   Initial SL: ${stop_loss:.2f} ({sl_pct:.1f}%)")
        print(f"   Take Profit: ${take_profit:.2f} (+{tp_pct:.1f}%)")
        print(f"   💡 SL will update dynamically as price rises")

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
            # Fallback: use 3.5% from highest
            fallback_sl = highest_price * 0.965
            return {
                'atr_based_sl': fallback_sl,
                'swing_low_sl': fallback_sl,
                'ma_based_sl': fallback_sl,
                'recommended_sl': fallback_sl,
                'trailing_distance_pct': 3.5,
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

    def update_position_sl(self, symbol: str, current_price: float) -> Tuple[bool, float]:
        """
        Update position's stop loss if price made new high

        Returns:
            Tuple of (was_updated, new_sl)
        """
        if symbol not in self.positions:
            return False, 0

        pos = self.positions[symbol]
        was_updated = False
        new_sl = pos.current_stop_loss

        # Check if new high
        if current_price > pos.highest_price:
            pos.highest_price = current_price

            # Check if trailing should activate
            pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100

            if pnl_pct >= self.TRAIL_ACTIVATION_PCT:
                pos.trailing_active = True

                # Calculate new dynamic SL
                sl_info = self.calculate_dynamic_sl(
                    symbol, current_price, pos.highest_price, pos.entry_price
                )

                recommended_sl = sl_info['recommended_sl']

                # Only update if new SL is higher than current
                if recommended_sl > pos.current_stop_loss:
                    pos.current_stop_loss = recommended_sl
                    new_sl = recommended_sl
                    was_updated = True

            self.save_portfolio()

        return was_updated, new_sl

    def analyze_position(self, symbol: str) -> Optional[PositionStatus]:
        """
        Analyze a position with dynamic SL

        v3.3: Auto-updates SL when checking
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        current_price = self.get_current_price(symbol)

        if current_price is None:
            return None

        # v3.3: Auto-update SL on check
        sl_updated, new_sl = self.update_position_sl(symbol, current_price)

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

        # Add SL update info
        if sl_updated:
            reasons.append(f"📈 SL updated to ${new_sl:.2f}")

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
            trailing_active=pos.trailing_active
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
    print("🚀 RAPID PORTFOLIO MANAGER v3.3 - DYNAMIC TRAILING STOP")
    print("=" * 70)
    print()
    print("v3.3 Features:")
    print("  - ATR-based dynamic trailing (volatile = wider trail)")
    print("  - Swing low protection (structure-based)")
    print("  - EMA-based trailing (trend following)")
    print("  - Auto-update SL when price rises")
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
