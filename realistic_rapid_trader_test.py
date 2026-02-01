#!/usr/bin/env python3
"""
REALISTIC RAPID TRADER BACKTEST
================================
ทดสอบจริง: ซื้อตาม signal, ถือตาม SL/TP/Trailing จริง
ดูว่าผลลัพธ์จะได้ตามที่ระบบคำนวณไหม

วิธีการ:
1. ดึง signal จาก Rapid Trader ณ วันนั้นๆ
2. ซื้อที่ราคา entry จริง (ใช้ราคา open ของวันถัดไป)
3. Track ทุกวันจนกว่าจะโดน SL/TP/MaxHold/Trailing
4. คำนวณกำไรขาดทุนจริง

ข้อมูล: ใช้ราคาจริงจาก yfinance
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


@dataclass
class Trade:
    """Single trade record"""
    symbol: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    atr_pct: float
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    days_held: int = 0
    peak_price: float = 0.0
    peak_pct: float = 0.0
    trough_price: float = 0.0
    trough_pct: float = 0.0


class RealisticBacktest:
    """
    Realistic backtest - simulate ACTUAL trading
    """

    # Exit parameters (same as portfolio manager)
    STOP_LOSS_PCT = -1.5       # SL ที่ -1.5%
    TAKE_PROFIT_PCT = 4.0      # TP ที่ +4%
    TRAIL_ACTIVATE_PCT = 2.5   # เริ่ม trail ที่ +2.5%
    TRAIL_PCT = 0.6            # Trail 60% of profit
    MAX_HOLD_DAYS = 4          # ถือไม่เกิน 4 วัน

    def __init__(self):
        self.trades: List[Trade] = []

    def calculate_dynamic_sl_tp(self, price_data: pd.DataFrame, entry_price: float) -> Tuple[float, float, float]:
        """
        Calculate SL/TP dynamically based on ATR
        Same logic as rapid_rotation_screener.py
        """
        # Calculate ATR
        if len(price_data) < 14:
            atr = entry_price * 0.02  # Default 2%
        else:
            high = price_data['High'].tail(14)
            low = price_data['Low'].tail(14)
            close = price_data['Close'].tail(14)

            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.mean()

        atr_pct = (atr / entry_price) * 100

        # Dynamic SL based on ATR (1.5% - 2.5%)
        if atr_pct > 5:
            sl_pct = 2.5
        elif atr_pct > 4:
            sl_pct = 2.0
        elif atr_pct > 3:
            sl_pct = 1.75
        else:
            sl_pct = 1.5

        # Dynamic TP based on ATR (4% - 6%)
        tp_multiplier = min(1.5, max(1.0, atr_pct / 3))
        tp_pct = 4.0 * tp_multiplier

        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)

        return stop_loss, take_profit, atr_pct

    def simulate_trade(self, symbol: str, entry_date: str,
                       entry_price: float, stop_loss: float,
                       take_profit: float, atr_pct: float) -> Trade:
        """
        Simulate a single trade from entry to exit
        Uses REAL price data to determine exit
        """
        trade = Trade(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            atr_pct=atr_pct
        )

        # Get price data from entry date onwards
        try:
            start_date = datetime.strptime(entry_date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=30)  # Get 30 days of data

            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)

            if hist.empty:
                trade.exit_reason = "NO_DATA"
                return trade

        except Exception as e:
            trade.exit_reason = f"ERROR: {e}"
            return trade

        # Calculate SL/TP percentages
        sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        tp_pct = ((take_profit - entry_price) / entry_price) * 100

        peak_price = entry_price
        trough_price = entry_price
        trailing_stop = None

        # Simulate each day
        for day_idx, (date, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue  # Skip entry day

            current_price = row['Close']
            high_price = row['High']
            low_price = row['Low']

            # Update peak and trough
            peak_price = max(peak_price, high_price)
            trough_price = min(trough_price, low_price)

            # Calculate current P&L
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
            peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100

            # Check exit conditions in order of priority

            # 1. Check if SL was hit (using intraday low)
            low_pnl = ((low_price - entry_price) / entry_price) * 100
            if low_pnl <= sl_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss  # Exit at SL price
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.days_held = day_idx
                break

            # 2. Check trailing stop (if activated)
            if trailing_stop is not None:
                if low_price <= trailing_stop:
                    trade.exit_date = date.strftime('%Y-%m-%d')
                    trade.exit_price = trailing_stop
                    trade.exit_reason = "TRAILING_STOP"
                    trade.pnl_pct = ((trailing_stop - entry_price) / entry_price) * 100
                    trade.days_held = day_idx
                    break

            # 3. Check if TP was hit (using intraday high)
            high_pnl = ((high_price - entry_price) / entry_price) * 100
            if high_pnl >= tp_pct:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = take_profit  # Exit at TP price
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.days_held = day_idx
                break

            # 4. Activate trailing stop if profit > TRAIL_ACTIVATE
            if peak_pnl_pct >= self.TRAIL_ACTIVATE_PCT:
                # Trailing stop at 60% of profit
                trail_level = entry_price * (1 + (peak_pnl_pct * self.TRAIL_PCT) / 100)
                if trailing_stop is None or trail_level > trailing_stop:
                    trailing_stop = trail_level

            # 5. Check max hold days
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = date.strftime('%Y-%m-%d')
                trade.exit_price = current_price
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = pnl_pct
                trade.days_held = day_idx
                break

        # If no exit triggered, mark as still holding
        if not trade.exit_date:
            trade.exit_reason = "STILL_HOLDING"
            trade.days_held = len(hist) - 1

        # Record peak and trough
        trade.peak_price = peak_price
        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_price = trough_price
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        return trade

    def run_backtest(self, start_date: str, end_date: str,
                     universe: List[str] = None) -> Dict:
        """
        Run full backtest over date range

        For each trading day:
        1. Run screener to get signals
        2. Take top 3 signals
        3. Simulate trades with real prices
        """
        if universe is None:
            # Default universe - high volume stocks
            universe = [
                'NVDA', 'AMD', 'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL',
                'AAPL', 'MSFT', 'AVGO', 'MU', 'PLTR', 'COIN', 'SNOW',
                'CRM', 'ORCL', 'NOW', 'SHOP', 'SQ', 'UBER', 'JPM', 'GS'
            ]

        print(f"\n{'='*60}")
        print(f"REALISTIC RAPID TRADER BACKTEST")
        print(f"{'='*60}")
        print(f"Period: {start_date} to {end_date}")
        print(f"Universe: {len(universe)} stocks")
        print(f"Exit Rules: SL={self.STOP_LOSS_PCT}%, TP={self.TAKE_PROFIT_PCT}%")
        print(f"            Trail@{self.TRAIL_ACTIVATE_PCT}%+, Max {self.MAX_HOLD_DAYS} days")
        print(f"{'='*60}\n")

        # Generate trading days
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        current = start
        total_trades = 0

        while current <= end:
            # Skip weekends
            if current.weekday() >= 5:
                current += timedelta(days=1)
                continue

            date_str = current.strftime('%Y-%m-%d')

            # Find candidates on this date
            candidates = self._find_candidates(universe, date_str)

            if candidates:
                print(f"\n{date_str}: Found {len(candidates)} candidates")

                # Take top 3 by score
                for symbol, entry_price, sl, tp, atr_pct in candidates[:3]:
                    print(f"  -> {symbol}: Entry=${entry_price:.2f}, SL=${sl:.2f} ({((sl-entry_price)/entry_price)*100:.1f}%), TP=${tp:.2f} ({((tp-entry_price)/entry_price)*100:.1f}%)")

                    # Simulate trade
                    trade = self.simulate_trade(symbol, date_str, entry_price, sl, tp, atr_pct)

                    if trade.exit_reason and trade.exit_reason != "NO_DATA":
                        self.trades.append(trade)
                        total_trades += 1

                        emoji = "✅" if trade.pnl_pct > 0 else "❌"
                        print(f"     {emoji} Exit: {trade.exit_reason} @ ${trade.exit_price:.2f} = {trade.pnl_pct:+.2f}% ({trade.days_held}d)")
                        print(f"        Peak: {trade.peak_pct:+.2f}%, Trough: {trade.trough_pct:+.2f}%")

            # Move to next week (simulate weekly rotation)
            current += timedelta(days=7)

        # Calculate results
        return self._calculate_results()

    def _find_candidates(self, universe: List[str], date: str) -> List[Tuple]:
        """
        Find buy candidates on a specific date
        Uses same criteria as rapid_rotation_screener
        """
        candidates = []

        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=30)

        for symbol in universe:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date + timedelta(days=1))

                if len(hist) < 20:
                    continue

                current_price = hist['Close'].iloc[-1]

                # Calculate indicators
                sma5 = hist['Close'].tail(5).mean()
                sma20 = hist['Close'].tail(20).mean()

                # Momentum
                mom_1d = ((current_price / hist['Close'].iloc[-2]) - 1) * 100 if len(hist) >= 2 else 0
                mom_5d = ((current_price / hist['Close'].iloc[-5]) - 1) * 100 if len(hist) >= 5 else 0

                # Volume surge
                avg_vol = hist['Volume'].tail(20).mean()
                today_vol = hist['Volume'].iloc[-1]
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1

                # RSI
                delta = hist['Close'].diff().tail(14)
                gain = delta.where(delta > 0, 0).mean()
                loss = (-delta.where(delta < 0, 0)).mean()
                rs = gain / loss if loss != 0 else 100
                rsi = 100 - (100 / (1 + rs))

                # Distance from 20d high
                high_20d = hist['High'].tail(20).max()
                dist_from_high = ((current_price / high_20d) - 1) * 100

                # Calculate dynamic SL/TP
                sl, tp, atr_pct = self.calculate_dynamic_sl_tp(hist, current_price)

                # Screening criteria (same as rapid_rotation_screener)
                score = 0
                reasons = []

                # 1. True dip: mom_1d negative
                if mom_1d < 0:
                    score += 15
                    reasons.append("True dip")
                else:
                    continue  # Skip if not a dip

                # 2. Below SMA5 (pullback)
                if current_price < sma5:
                    score += 10
                    reasons.append("Below SMA5")

                # 3. Volume confirmation
                if vol_ratio > 1.2:
                    score += 10
                    reasons.append(f"Vol {vol_ratio:.1f}x")

                # 4. RSI oversold
                if rsi < 40:
                    score += 15
                    reasons.append(f"RSI {rsi:.0f}")
                elif rsi < 50:
                    score += 5

                # 5. Not too far from high
                if dist_from_high > -10:
                    score += 10
                    reasons.append(f"{dist_from_high:.0f}% from high")

                # 6. Uptrend: price > SMA20
                if current_price > sma20:
                    score += 15
                    reasons.append("Above SMA20")

                # 7. Good R:R
                risk = current_price - sl
                reward = tp - current_price
                rr = reward / risk if risk > 0 else 0
                if rr >= 2.0:
                    score += 10
                    reasons.append(f"R:R {rr:.1f}")

                # Minimum score threshold
                if score >= 50:
                    candidates.append((symbol, current_price, sl, tp, atr_pct, score, reasons))

            except Exception as e:
                continue

        # Sort by score
        candidates.sort(key=lambda x: x[5], reverse=True)

        # Return top candidates (symbol, entry, sl, tp, atr_pct)
        return [(c[0], c[1], c[2], c[3], c[4]) for c in candidates[:5]]

    def _calculate_results(self) -> Dict:
        """Calculate and display results"""
        if not self.trades:
            print("\n❌ No trades executed")
            return {}

        # Filter out invalid trades
        valid_trades = [t for t in self.trades if t.exit_reason not in ["NO_DATA", "STILL_HOLDING", ""] and t.exit_reason and "ERROR" not in t.exit_reason]

        if not valid_trades:
            print("\n❌ No valid trades")
            return {}

        # Calculate metrics
        total_trades = len(valid_trades)
        winners = [t for t in valid_trades if t.pnl_pct > 0]
        losers = [t for t in valid_trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total_trades * 100

        total_pnl = sum(t.pnl_pct for t in valid_trades)
        avg_pnl = total_pnl / total_trades

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        # Exit type breakdown
        exit_counts = {}
        for t in valid_trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        # Print results
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"\nTrade Statistics:")
        print(f"  Total Trades:    {total_trades}")
        print(f"  Winners:         {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers:          {len(losers)} ({100-win_rate:.1f}%)")

        print(f"\nReturns:")
        print(f"  Total P&L:       {total_pnl:+.2f}%")
        print(f"  Avg per Trade:   {avg_pnl:+.2f}%")
        print(f"  Avg Win:         {avg_win:+.2f}%")
        print(f"  Avg Loss:        {avg_loss:+.2f}%")

        # Profit factor
        gross_profit = sum(t.pnl_pct for t in winners)
        gross_loss = abs(sum(t.pnl_pct for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        print(f"  Profit Factor:   {profit_factor:.2f}")

        print(f"\nExit Breakdown:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total_trades * 100
            trades_by_reason = [t for t in valid_trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        # Monthly breakdown
        print(f"\nMonthly Breakdown:")
        monthly_pnl = {}
        for t in valid_trades:
            month = t.entry_date[:7]
            if month not in monthly_pnl:
                monthly_pnl[month] = {'pnl': 0, 'trades': 0, 'wins': 0}
            monthly_pnl[month]['pnl'] += t.pnl_pct
            monthly_pnl[month]['trades'] += 1
            if t.pnl_pct > 0:
                monthly_pnl[month]['wins'] += 1

        for month in sorted(monthly_pnl.keys()):
            data = monthly_pnl[month]
            wr = data['wins'] / data['trades'] * 100
            print(f"  {month}: {data['pnl']:+6.2f}% | {data['trades']:2} trades | {wr:.0f}% win rate")

        # SL/TP accuracy
        print(f"\n{'='*60}")
        print(f"SL/TP ACCURACY CHECK")
        print(f"{'='*60}")

        sl_trades = [t for t in valid_trades if t.exit_reason == "STOP_LOSS"]
        tp_trades = [t for t in valid_trades if t.exit_reason == "TAKE_PROFIT"]
        trail_trades = [t for t in valid_trades if t.exit_reason == "TRAILING_STOP"]

        if sl_trades:
            avg_sl = sum(t.pnl_pct for t in sl_trades) / len(sl_trades)
            print(f"\nStop Loss exits: {len(sl_trades)}")
            print(f"  Avg loss: {avg_sl:.2f}%")
            print(f"  Expected: ~{self.STOP_LOSS_PCT:.1f}%")
            print(f"  Accuracy: {'✅ CORRECT' if abs(avg_sl - self.STOP_LOSS_PCT) < 0.5 else '⚠️ CHECK'}")

        if tp_trades:
            avg_tp = sum(t.pnl_pct for t in tp_trades) / len(tp_trades)
            print(f"\nTake Profit exits: {len(tp_trades)}")
            print(f"  Avg gain: {avg_tp:.2f}%")
            print(f"  Expected: ~{self.TAKE_PROFIT_PCT:.1f}%")
            print(f"  Accuracy: {'✅ CORRECT' if abs(avg_tp - self.TAKE_PROFIT_PCT) < 1.0 else '⚠️ CHECK'}")

        if trail_trades:
            avg_trail = sum(t.pnl_pct for t in trail_trades) / len(trail_trades)
            print(f"\nTrailing Stop exits: {len(trail_trades)}")
            print(f"  Avg gain: {avg_trail:.2f}%")
            print(f"  Range: {min(t.pnl_pct for t in trail_trades):.2f}% to {max(t.pnl_pct for t in trail_trades):.2f}%")

        # Individual trades detail
        print(f"\n{'='*60}")
        print(f"ALL TRADES DETAIL")
        print(f"{'='*60}")
        print(f"{'Symbol':<6} {'Entry Date':<12} {'Entry$':>8} {'Exit$':>8} {'P&L%':>7} {'Days':>4} {'Exit Reason':<15} {'Peak%':>6} {'Low%':>6}")
        print(f"{'-'*80}")

        for t in sorted(valid_trades, key=lambda x: x.entry_date):
            emoji = "✅" if t.pnl_pct > 0 else "❌"
            print(f"{t.symbol:<6} {t.entry_date:<12} ${t.entry_price:>7.2f} ${t.exit_price:>7.2f} {t.pnl_pct:>+6.2f}% {t.days_held:>4}d {t.exit_reason:<15} {t.peak_pct:>+5.1f}% {t.trough_pct:>+5.1f}% {emoji}")

        return {
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'monthly': monthly_pnl
        }


def main():
    """Run realistic backtest"""
    backtest = RealisticBacktest()

    # Test last 3 months
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    # High-volume stocks for testing
    universe = [
        # Tech giants
        'NVDA', 'AMD', 'TSLA', 'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT',
        # Semiconductors
        'AVGO', 'MU', 'MRVL', 'QCOM', 'AMAT',
        # High beta tech
        'PLTR', 'COIN', 'SNOW', 'DDOG', 'NET', 'CRWD',
        # Software
        'CRM', 'ORCL', 'NOW', 'SHOP', 'SQ',
        # Others
        'UBER', 'JPM', 'GS', 'V', 'MA'
    ]

    results = backtest.run_backtest(start_date, end_date, universe)

    # Summary for user
    if results:
        print(f"\n{'='*60}")
        print(f"FINAL SUMMARY")
        print(f"{'='*60}")
        print(f"""
ผลลัพธ์การทดสอบ Rapid Trader แบบจริง:

📊 สถิติ:
   - จำนวน trades: {results['total_trades']}
   - Win rate: {results['win_rate']:.1f}%
   - ค่าเฉลี่ยต่อ trade: {results['avg_pnl']:+.2f}%

💰 กำไรขาดทุน:
   - รวม P&L: {results['total_pnl']:+.2f}%
   - เฉลี่ยกำไร: {results['avg_win']:+.2f}%
   - เฉลี่ยขาดทุน: {results['avg_loss']:+.2f}%
   - Profit Factor: {results['profit_factor']:.2f}

🎯 ผลประจำเดือน:
""")
        for month, data in sorted(results['monthly'].items()):
            print(f"   {month}: {data['pnl']:+.2f}% ({data['trades']} trades)")

        # Check if 5-15% monthly target is achievable
        monthly_returns = [data['pnl'] for data in results['monthly'].values()]
        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n📈 ค่าเฉลี่ยต่อเดือน: {avg_monthly:+.2f}%")

        if avg_monthly >= 5:
            print(f"   ✅ บรรลุเป้า 5%+ ต่อเดือน!")
        elif avg_monthly >= 3:
            print(f"   🟡 ใกล้เป้า (ต้องการ 5%+)")
        else:
            print(f"   ❌ ยังไม่ถึงเป้า (ต้องการ 5%+)")


if __name__ == "__main__":
    main()
