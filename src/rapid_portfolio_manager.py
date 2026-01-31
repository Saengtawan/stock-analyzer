#!/usr/bin/env python3
"""
RAPID PORTFOLIO MANAGER v2.1 - ANTI-PDT Edition

หลักการ (v2.1 - Anti-PDT):
1. Dynamic SL based on signal's SL price (1.5%-2.5%)
2. ถือไม่เกิน 4 วัน (quick rotation)
3. เตือนล่วงหน้าก่อนจะเสียหาย
4. แนะนำตัวใหม่ทันทีเมื่อขาย

⚠️  PDT Protection:
- Screener จะกรอง signal ที่มี risk โดน same-day SL ออก
- SL ปรับตาม ATR ของหุ้น (volatile stock = wider SL)
- ไม่เข้าตอน gap-up หรือตอนหุ้นขึ้นแล้ว

Exit Signals (เรียงตามความเร่งด่วน):
🔴 CRITICAL - ต้องขายทันที (ถึง SL price)
🟠 WARNING - เตรียมขาย
🟡 WATCH - จับตาดู
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import yfinance as yf
import pandas as pd
import numpy as np


class ExitSignal(Enum):
    """Exit signal levels"""
    CRITICAL = "CRITICAL"  # ขายทันที!
    WARNING = "WARNING"    # เตรียมขาย
    WATCH = "WATCH"        # จับตาดู
    HOLD = "HOLD"          # ถือต่อ
    TAKE_PROFIT = "TAKE_PROFIT"  # ถึงเป้า


@dataclass
class Position:
    """Position in portfolio"""
    symbol: str
    entry_date: str
    entry_price: float
    shares: int
    stop_loss: float
    take_profit: float
    cost_basis: float

    @property
    def position_value(self) -> float:
        return self.shares * self.entry_price


@dataclass
class PositionStatus:
    """Current status of a position"""
    symbol: str
    entry_price: float
    current_price: float
    pnl_pct: float
    pnl_usd: float
    days_held: int
    signal: ExitSignal
    reasons: List[str]
    action: str
    new_candidates: List[str]  # แนะนำตัวใหม่ถ้าต้องขาย


class RapidPortfolioManager:
    """
    Portfolio Manager v2.0 - TIGHT STOP LOSS + QUICK ROTATION

    Rules (Approach 2 - Tight SL):
    1. Stop Loss: ลง 1.5% = ขายทันที (เดิม 2.5%)
    2. Time Stop: ถือ 4 วันไม่กำไร = ขาย (เดิม 7 วัน)
    3. Early Warning: ลง 1.0% = เตือน
    4. Take Profit: ขึ้น 3-4% = ขาย
    5. Trail Stop: หลังกำไร 2.5%+ ใช้ Trail 60%
    """

    PORTFOLIO_FILE = "rapid_portfolio.json"

    # Exit Parameters v2.0 - TIGHT STOP LOSS!
    STOP_LOSS_PCT = -1.5       # ขายทันทีถ้าลง 1.5% (เดิม -2.5%)
    WARNING_PCT = -1.0         # เตือนถ้าลง 1.0% (เดิม -1.5%)
    WATCH_PCT = -0.5           # จับตาถ้าลง 0.5%
    TAKE_PROFIT_PCT = 4.0      # ขายถ้าขึ้น 4%
    TRAIL_ACTIVATE_PCT = 2.5   # เริ่ม Trail หลังขึ้น 2.5% (เดิม 3.0%)
    TRAIL_PCT = 0.6            # Trail ที่ 60% ของกำไร
    MAX_HOLD_DAYS = 4          # ถือไม่เกิน 4 วัน (เดิม 7 วัน)

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
        """Add new position"""
        self.positions[symbol] = Position(
            symbol=symbol,
            entry_date=datetime.now().strftime('%Y-%m-%d'),
            entry_price=entry_price,
            shares=shares,
            stop_loss=stop_loss,
            take_profit=take_profit,
            cost_basis=shares * entry_price
        )
        self.save_portfolio()
        print(f"Added position: {symbol} x{shares} @ ${entry_price:.2f}")
        print(f"  Stop Loss: ${stop_loss:.2f} | Take Profit: ${take_profit:.2f}")

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

    def get_technical_signals(self, symbol: str) -> Dict:
        """Get technical signals for early warning"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='30d')
            if len(data) < 10:
                return {}

            data.columns = [c.lower() for c in data.columns]
            close = data['close']
            high = data['high']
            low = data['low']

            current = close.iloc[-1]

            # RSI
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

            # Momentum
            mom_1d = (current / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
            mom_3d = (current / close.iloc[-4] - 1) * 100 if len(close) >= 4 else 0
            mom_5d = (current / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0

            # Breaking support?
            low_5d = low.iloc[-5:].min()
            breaking_support = current < low_5d

            # Volume spike down?
            avg_vol = data['volume'].iloc[-10:-1].mean()
            today_vol = data['volume'].iloc[-1]
            volume_spike = today_vol > avg_vol * 1.5 and mom_1d < 0

            return {
                'rsi': rsi,
                'mom_1d': mom_1d,
                'mom_3d': mom_3d,
                'mom_5d': mom_5d,
                'breaking_support': breaking_support,
                'volume_spike_down': volume_spike,
                'low_5d': low_5d,
            }
        except:
            return {}

    def analyze_position(self, symbol: str) -> Optional[PositionStatus]:
        """
        Analyze a position and determine exit signal

        This is the core function that decides:
        - Should we sell?
        - How urgent is it?
        - What should we buy instead?
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        current_price = self.get_current_price(symbol)

        if current_price is None:
            return None

        # Calculate P&L
        pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
        pnl_usd = (current_price - pos.entry_price) * pos.shares

        # Calculate days held
        entry_date = datetime.strptime(pos.entry_date, '%Y-%m-%d')
        days_held = (datetime.now() - entry_date).days

        # Get technical signals
        tech = self.get_technical_signals(symbol)

        # ==============================
        # DETERMINE EXIT SIGNAL
        # ==============================
        signal = ExitSignal.HOLD
        reasons = []
        action = "HOLD"
        new_candidates = []

        # 1. TAKE PROFIT (Best case)
        if current_price >= pos.take_profit:
            signal = ExitSignal.TAKE_PROFIT
            reasons.append(f"Hit TP ${pos.take_profit:.2f}")
            action = "SELL - ถึงเป้า!"
            new_candidates = self._get_replacement_candidates(symbol)

        elif pnl_pct >= self.TAKE_PROFIT_PCT:
            signal = ExitSignal.TAKE_PROFIT
            reasons.append(f"Profit +{pnl_pct:.1f}%")
            action = "SELL - Take Profit!"
            new_candidates = self._get_replacement_candidates(symbol)

        # 2. STOP LOSS (CRITICAL!)
        elif current_price <= pos.stop_loss:
            signal = ExitSignal.CRITICAL
            reasons.append(f"Hit SL ${pos.stop_loss:.2f}")
            action = "🔴 SELL NOW! ถึง Stop Loss"
            new_candidates = self._get_replacement_candidates(symbol)

        elif pnl_pct <= self.STOP_LOSS_PCT:
            signal = ExitSignal.CRITICAL
            reasons.append(f"Loss {pnl_pct:.1f}%")
            action = "🔴 SELL NOW! ลงเกินกำหนด"
            new_candidates = self._get_replacement_candidates(symbol)

        # 3. TRAILING STOP (after profit)
        elif pnl_pct >= self.TRAIL_ACTIVATE_PCT:
            trail_stop_pnl = pnl_pct * self.TRAIL_PCT
            if tech.get('mom_1d', 0) < -1.5:
                signal = ExitSignal.WARNING
                reasons.append(f"Profit +{pnl_pct:.1f}% but dropping")
                action = "🟠 SELL - Lock in profits"
                new_candidates = self._get_replacement_candidates(symbol)

        # 4. TIME STOP
        elif days_held >= self.MAX_HOLD_DAYS:
            if pnl_pct < 1:  # ไม่กำไรพอ
                signal = ExitSignal.WARNING
                reasons.append(f"Held {days_held} days, only +{pnl_pct:.1f}%")
                action = "🟠 SELL - Rotation"
                new_candidates = self._get_replacement_candidates(symbol)

        # 5. WARNING SIGNALS
        elif pnl_pct <= self.WARNING_PCT:
            signal = ExitSignal.WARNING
            reasons.append(f"Down {pnl_pct:.1f}%")

            # Check if likely to hit stop
            if tech.get('breaking_support'):
                reasons.append("Breaking support!")
                action = "🟠 SELL - ทะลุแนวรับ"
                new_candidates = self._get_replacement_candidates(symbol)
            elif tech.get('volume_spike_down'):
                reasons.append("High volume selling!")
                action = "🟠 SELL - Volume ขายหนัก"
                new_candidates = self._get_replacement_candidates(symbol)
            elif tech.get('mom_3d', 0) < -3:
                reasons.append("Momentum weakening")
                action = "🟠 Consider selling"
            else:
                action = "🟠 WATCH CLOSELY"

        # 6. WATCH SIGNALS
        elif pnl_pct <= self.WATCH_PCT:
            signal = ExitSignal.WATCH
            reasons.append(f"Slightly down {pnl_pct:.1f}%")

            if tech.get('rsi', 50) < 40:
                reasons.append(f"RSI weak {tech.get('rsi', 50):.0f}")
            if tech.get('mom_1d', 0) < -1:
                reasons.append(f"Today -{abs(tech.get('mom_1d', 0)):.1f}%")

            action = "🟡 Watch - อาจต้องขาย"

        # 7. HOLD (Good case)
        else:
            signal = ExitSignal.HOLD
            if pnl_pct > 0:
                reasons.append(f"Profit +{pnl_pct:.1f}%")
                action = f"✅ HOLD - กำลังดี"
            else:
                reasons.append("Within tolerance")
                action = "✅ HOLD"

        return PositionStatus(
            symbol=symbol,
            entry_price=pos.entry_price,
            current_price=round(current_price, 2),
            pnl_pct=round(pnl_pct, 2),
            pnl_usd=round(pnl_usd, 2),
            days_held=days_held,
            signal=signal,
            reasons=reasons,
            action=action,
            new_candidates=new_candidates
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

        Use this for daily monitoring
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

        return {
            'positions': len(self.positions),
            'total_cost': round(total_cost, 2),
            'total_value': round(total_value, 2),
            'total_pnl_usd': round(total_pnl_usd, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'avg_pnl_pct': round(sum(pnls) / len(pnls), 2) if pnls else 0,
        }


def main():
    """Run portfolio check"""
    print("=" * 70)
    print("🚀 RAPID PORTFOLIO MANAGER")
    print("ระบบจัดการ Portfolio - ตัดขาดทุนเร็ว, Rotation ไว")
    print("=" * 70)
    print()

    manager = RapidPortfolioManager()

    # Check if we have positions
    if not manager.positions:
        print("ไม่มี Position ใน Portfolio")
        print()
        print("วิธีเพิ่ม Position:")
        print("  manager.add_position('NVDA', shares=10, entry_price=140.00,")
        print("                       stop_loss=136.50, take_profit=145.60)")
        return

    # Get summary
    summary = manager.get_portfolio_summary()
    print(f"📊 PORTFOLIO SUMMARY")
    print("-" * 50)
    print(f"Positions: {summary['positions']}")
    print(f"Total Cost: ${summary['total_cost']:,.2f}")
    print(f"Current Value: ${summary['total_value']:,.2f}")
    print(f"Total P&L: ${summary['total_pnl_usd']:+,.2f} ({summary['total_pnl_pct']:+.2f}%)")
    print()

    # Check all positions
    print("📋 POSITION STATUS")
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
        print(f"   P&L: {status.pnl_pct:+.2f}% (${status.pnl_usd:+.2f})")
        print(f"   Days Held: {status.days_held}")
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

    # Take profits
    take_profits = [s for s in statuses if s.signal == ExitSignal.TAKE_PROFIT]
    if take_profits:
        print("=" * 70)
        print("🎯 TAKE PROFIT - ได้กำไรแล้ว ขายเลย!")
        print("=" * 70)
        for s in take_profits:
            print(f"  🎯 {s.symbol}: +{s.pnl_pct:.2f}%")
            if s.new_candidates:
                print(f"     → Rotate to: {', '.join(s.new_candidates)}")
        print()


if __name__ == "__main__":
    main()
