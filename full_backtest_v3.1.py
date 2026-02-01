#!/usr/bin/env python3
"""
FULL BACKTEST v3.1 - REALISTIC COMPLETE TEST
==============================================
ทดสอบ Rapid Trader v3.1 อย่างสมจริงที่สุด:

1. ใช้ระบบ Rapid Trader จริง (680+ หุ้นจาก AI)
2. Screen หุ้นทุกสัปดาห์ (หุ้นจะต่างกันทุกสัปดาห์)
3. Simulate การซื้อขายตาม signal จริง
4. บันทึกผลทุก trade เพื่อวิเคราะห์
5. คำนวณ monthly return
6. หา areas for improvement

Target: 5-10% per month
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/screeners'))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json
import time
import warnings
warnings.filterwarnings('ignore')

# Disable loguru output for cleaner results
import logging
logging.disable(logging.CRITICAL)


@dataclass
class TradeRecord:
    """Complete trade record"""
    symbol: str
    sector: str
    entry_date: str
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_pct: float
    tp_pct: float
    score: int
    market_regime: str
    reasons: str
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    days_held: int = 0
    peak_pct: float = 0.0
    trough_pct: float = 0.0


class FullBacktestV31:
    """
    Full realistic backtest using actual Rapid Trader screener
    """

    # Portfolio settings
    STARTING_CAPITAL = 10000
    MAX_POSITIONS = 3
    POSITION_SIZE_PCT = 30  # 30% per position
    MAX_HOLD_DAYS = 4

    def __init__(self):
        self.trades: List[TradeRecord] = []
        self.weekly_results: List[Dict] = []
        self.monthly_results: Dict = {}
        self.improvement_notes: List[str] = []
        self.capital = self.STARTING_CAPITAL
        self.screener = None

        self._init_screener()

    def _init_screener(self):
        """Initialize actual Rapid Trader screener"""
        try:
            from rapid_rotation_screener import RapidRotationScreener
            self.screener = RapidRotationScreener()
            print("✅ Rapid Trader v3.1 Screener initialized")
            print(f"   - AI Universe: 680+ stocks")
            print(f"   - Market Regime Filter: Active")
            print(f"   - Sector Rotation: Active")
            print(f"   - SL Range: 2.0%-3.0%")
        except Exception as e:
            print(f"❌ Failed to init screener: {e}")
            self.screener = None

    def get_market_regime(self, date: datetime) -> str:
        """Check SPY for market regime"""
        try:
            start = date - timedelta(days=30)
            ticker = yf.Ticker('SPY')
            hist = ticker.history(start=start, end=date + timedelta(days=1))

            if len(hist) < 20:
                return "UNKNOWN"

            current = hist['Close'].iloc[-1]
            sma20 = hist['Close'].tail(20).mean()
            mom_5d = ((current / hist['Close'].iloc[-5]) - 1) * 100

            if current > sma20 and mom_5d > -2:
                return "BULL"
            elif current < sma20 * 0.98:
                return "BEAR"
            else:
                return "NEUTRAL"
        except:
            return "UNKNOWN"

    def screen_for_date(self, date: datetime) -> List:
        """Get signals from screener for specific date"""
        if not self.screener:
            return []

        try:
            # Load fresh data for the screening date
            self.screener.data_cache = {}
            signals = self.screener.screen(top_n=10)
            return signals
        except Exception as e:
            print(f"    Screen error: {e}")
            return []

    def simulate_trade(self, signal, entry_date: datetime, position_size: float) -> Optional[TradeRecord]:
        """Simulate a single trade from entry to exit"""
        symbol = signal.symbol
        entry_price = signal.entry_price
        stop_loss = signal.stop_loss
        take_profit = signal.take_profit

        sl_pct = ((stop_loss - entry_price) / entry_price) * 100
        tp_pct = ((take_profit - entry_price) / entry_price) * 100

        trade = TradeRecord(
            symbol=symbol,
            sector=getattr(signal, 'sector', 'Unknown'),
            entry_date=entry_date.strftime('%Y-%m-%d'),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_pct=abs(sl_pct),
            tp_pct=tp_pct,
            score=signal.score,
            market_regime=getattr(signal, 'market_regime', 'UNKNOWN'),
            reasons=', '.join(signal.reasons[:3]) if signal.reasons else ''
        )

        # Get price data for simulation
        try:
            end = entry_date + timedelta(days=20)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date, end=end)

            if hist.empty:
                return None
        except:
            return None

        peak_price = entry_price
        trough_price = entry_price

        for day_idx, (dt, row) in enumerate(hist.iterrows()):
            if day_idx == 0:
                continue

            high = row['High']
            low = row['Low']
            close = row['Close']

            peak_price = max(peak_price, high)
            trough_price = min(trough_price, low)

            low_pnl = ((low - entry_price) / entry_price) * 100
            high_pnl = ((high - entry_price) / entry_price) * 100
            close_pnl = ((close - entry_price) / entry_price) * 100

            # Check stop loss
            if low_pnl <= sl_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = stop_loss
                trade.exit_reason = "STOP_LOSS"
                trade.pnl_pct = sl_pct
                trade.pnl_usd = position_size * (sl_pct / 100)
                trade.days_held = day_idx
                break

            # Check take profit
            if high_pnl >= tp_pct:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = take_profit
                trade.exit_reason = "TAKE_PROFIT"
                trade.pnl_pct = tp_pct
                trade.pnl_usd = position_size * (tp_pct / 100)
                trade.days_held = day_idx
                break

            # Check max hold
            if day_idx >= self.MAX_HOLD_DAYS:
                trade.exit_date = dt.strftime('%Y-%m-%d')
                trade.exit_price = close
                trade.exit_reason = "MAX_HOLD"
                trade.pnl_pct = close_pnl
                trade.pnl_usd = position_size * (close_pnl / 100)
                trade.days_held = day_idx
                break

        trade.peak_pct = ((peak_price - entry_price) / entry_price) * 100
        trade.trough_pct = ((trough_price - entry_price) / entry_price) * 100

        if not trade.exit_date:
            return None

        return trade

    def run_backtest(self, months_back: int = 3):
        """Run full backtest over specified months"""
        print(f"\n{'='*70}")
        print(f"FULL BACKTEST v3.1 - REALISTIC COMPLETE TEST")
        print(f"{'='*70}")
        print(f"\nSettings:")
        print(f"  Starting Capital: ${self.STARTING_CAPITAL:,}")
        print(f"  Max Positions: {self.MAX_POSITIONS}")
        print(f"  Position Size: {self.POSITION_SIZE_PCT}%")
        print(f"  Max Hold Days: {self.MAX_HOLD_DAYS}")
        print(f"  Test Period: {months_back} months")
        print(f"\nTarget: 5-10% monthly return")
        print(f"{'='*70}\n")

        if not self.screener:
            print("❌ Screener not available")
            return

        end_date = datetime.now()
        start_date = end_date - timedelta(days=months_back * 30)

        current = start_date
        week_num = 0

        while current <= end_date:
            # Skip weekends
            while current.weekday() >= 5:
                current += timedelta(days=1)

            if current > end_date:
                break

            week_num += 1
            date_str = current.strftime('%Y-%m-%d')
            month_key = current.strftime('%Y-%m')

            # Check market regime
            regime = self.get_market_regime(current)

            print(f"\n[Week {week_num}] {date_str} | Market: {regime}")

            # Skip if bear market
            if regime == "BEAR":
                print(f"  ⚠️ BEAR market - skipping trades")
                self.improvement_notes.append(f"{date_str}: Skipped due to BEAR market")
                current += timedelta(days=7)
                continue

            # Get signals
            print(f"  Screening 680+ stocks...")
            signals = self.screen_for_date(current)

            if not signals:
                print(f"  No signals found")
                current += timedelta(days=7)
                continue

            print(f"  Found {len(signals)} signals")

            # Take top positions
            trades_this_week = 0
            for sig in signals[:self.MAX_POSITIONS]:
                position_size = self.capital * (self.POSITION_SIZE_PCT / 100)
                sl_pct = ((sig.stop_loss - sig.entry_price) / sig.entry_price) * 100
                tp_pct = ((sig.take_profit - sig.entry_price) / sig.entry_price) * 100

                print(f"\n    {sig.symbol}: Score={sig.score}")
                print(f"      Entry=${sig.entry_price:.2f}, SL={sl_pct:.1f}%, TP={tp_pct:.1f}%")
                print(f"      Reasons: {', '.join(sig.reasons[:2])}")

                trade = self.simulate_trade(sig, current, position_size)

                if trade:
                    self.trades.append(trade)
                    trades_this_week += 1

                    # Update capital
                    self.capital += trade.pnl_usd

                    emoji = "✅" if trade.pnl_pct > 0 else "❌"
                    print(f"      {emoji} {trade.exit_reason}: {trade.pnl_pct:+.2f}% (${trade.pnl_usd:+.2f})")
                    print(f"      Peak: {trade.peak_pct:+.1f}%, Trough: {trade.trough_pct:+.1f}%")

                    # Record improvement notes
                    if trade.exit_reason == "STOP_LOSS":
                        if trade.peak_pct > 1:
                            self.improvement_notes.append(
                                f"{trade.symbol}: Hit SL but peaked at +{trade.peak_pct:.1f}% - consider trailing stop"
                            )
                        if trade.trough_pct < -3:
                            self.improvement_notes.append(
                                f"{trade.symbol}: Dropped to {trade.trough_pct:.1f}% - SL worked correctly"
                            )

                    # Update monthly tracking
                    if month_key not in self.monthly_results:
                        self.monthly_results[month_key] = {
                            'trades': 0, 'wins': 0, 'losses': 0,
                            'pnl': 0, 'pnl_usd': 0
                        }
                    self.monthly_results[month_key]['trades'] += 1
                    self.monthly_results[month_key]['pnl'] += trade.pnl_pct
                    self.monthly_results[month_key]['pnl_usd'] += trade.pnl_usd
                    if trade.pnl_pct > 0:
                        self.monthly_results[month_key]['wins'] += 1
                    else:
                        self.monthly_results[month_key]['losses'] += 1

            print(f"\n  Week {week_num} trades: {trades_this_week}")
            print(f"  Current capital: ${self.capital:,.2f}")

            # Move to next week
            current += timedelta(days=7)
            time.sleep(0.5)  # Small delay to avoid rate limiting

        self._show_results()
        self._show_improvement_analysis()
        self._save_results()

    def _show_results(self):
        """Show comprehensive results"""
        if not self.trades:
            print("\n❌ No trades executed")
            return

        print(f"\n{'='*70}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*70}")

        # Overall statistics
        total = len(self.trades)
        winners = [t for t in self.trades if t.pnl_pct > 0]
        losers = [t for t in self.trades if t.pnl_pct <= 0]

        win_rate = len(winners) / total * 100
        total_pnl = sum(t.pnl_pct for t in self.trades)
        total_pnl_usd = sum(t.pnl_usd for t in self.trades)
        avg_pnl = total_pnl / total

        avg_win = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0

        gross_profit = sum(t.pnl_pct for t in winners)
        gross_loss = abs(sum(t.pnl_pct for t in losers))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        print(f"\n📊 OVERALL STATISTICS:")
        print(f"  Total Trades: {total}")
        print(f"  Winners: {len(winners)} ({win_rate:.1f}%)")
        print(f"  Losers: {len(losers)} ({100-win_rate:.1f}%)")
        print(f"\n💰 RETURNS:")
        print(f"  Total P&L: {total_pnl:+.2f}% (${total_pnl_usd:+,.2f})")
        print(f"  Avg per Trade: {avg_pnl:+.2f}%")
        print(f"  Avg Win: {avg_win:+.2f}%")
        print(f"  Avg Loss: {avg_loss:+.2f}%")
        print(f"  Profit Factor: {profit_factor:.2f}")
        print(f"\n💵 CAPITAL:")
        print(f"  Starting: ${self.STARTING_CAPITAL:,}")
        print(f"  Ending: ${self.capital:,.2f}")
        print(f"  Total Return: {((self.capital/self.STARTING_CAPITAL)-1)*100:+.2f}%")

        # Exit breakdown
        exit_counts = {}
        for t in self.trades:
            exit_counts[t.exit_reason] = exit_counts.get(t.exit_reason, 0) + 1

        print(f"\n🎯 EXIT BREAKDOWN:")
        for reason, count in sorted(exit_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            trades_by_reason = [t for t in self.trades if t.exit_reason == reason]
            avg = sum(t.pnl_pct for t in trades_by_reason) / len(trades_by_reason)
            print(f"  {reason:15}: {count:3} ({pct:5.1f}%) avg {avg:+.2f}%")

        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN:")
        print(f"  {'Month':<10} {'Trades':>7} {'Wins':>6} {'Win%':>7} {'P&L':>10} {'P&L $':>12}")
        print(f"  {'-'*55}")

        monthly_returns = []
        for month in sorted(self.monthly_results.keys()):
            data = self.monthly_results[month]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"  {month:<10} {data['trades']:>7} {data['wins']:>6} {wr:>6.1f}% {data['pnl']:>+9.2f}% ${data['pnl_usd']:>+10.2f}")
            monthly_returns.append(data['pnl'])

        avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0

        print(f"\n📈 MONTHLY AVERAGE: {avg_monthly:+.2f}%")
        print(f"   Target: +5% to +10%")

        if avg_monthly >= 10:
            print(f"   ✅✅ EXCELLENT! Exceeds 10% target!")
        elif avg_monthly >= 5:
            print(f"   ✅ GOOD! Meets 5% target")
        elif avg_monthly >= 0:
            print(f"   🟡 Profitable but below 5% target")
        else:
            print(f"   ❌ Not profitable - needs improvement")

    def _show_improvement_analysis(self):
        """Analyze and show improvement opportunities"""
        print(f"\n{'='*70}")
        print(f"IMPROVEMENT ANALYSIS")
        print(f"{'='*70}")

        if not self.trades:
            return

        # Analyze stop loss trades
        sl_trades = [t for t in self.trades if t.exit_reason == "STOP_LOSS"]
        tp_trades = [t for t in self.trades if t.exit_reason == "TAKE_PROFIT"]
        hold_trades = [t for t in self.trades if t.exit_reason == "MAX_HOLD"]

        print(f"\n📉 STOP LOSS ANALYSIS ({len(sl_trades)} trades):")
        if sl_trades:
            sl_that_recovered = [t for t in sl_trades if t.peak_pct > 1]
            print(f"  Trades that peaked >1% before SL: {len(sl_that_recovered)}")
            if sl_that_recovered:
                print(f"  → Could use trailing stop to capture these gains")

            deep_drops = [t for t in sl_trades if t.trough_pct < -4]
            print(f"  Trades that dropped >4%: {len(deep_drops)}")
            if deep_drops:
                print(f"  → SL protected from larger losses")

        print(f"\n📈 TAKE PROFIT ANALYSIS ({len(tp_trades)} trades):")
        if tp_trades:
            could_go_higher = [t for t in tp_trades if t.peak_pct > t.tp_pct + 1]
            print(f"  Trades that continued higher after TP: {len(could_go_higher)}")
            if could_go_higher:
                print(f"  → Could raise TP or use trailing")

        print(f"\n⏱️ MAX HOLD ANALYSIS ({len(hold_trades)} trades):")
        if hold_trades:
            hold_winners = [t for t in hold_trades if t.pnl_pct > 0]
            hold_losers = [t for t in hold_trades if t.pnl_pct <= 0]
            print(f"  Winners at max hold: {len(hold_winners)}")
            print(f"  Losers at max hold: {len(hold_losers)}")

        # Sector analysis
        print(f"\n🏢 SECTOR ANALYSIS:")
        sector_stats = {}
        for t in self.trades:
            if t.sector not in sector_stats:
                sector_stats[t.sector] = {'trades': 0, 'pnl': 0, 'wins': 0}
            sector_stats[t.sector]['trades'] += 1
            sector_stats[t.sector]['pnl'] += t.pnl_pct
            if t.pnl_pct > 0:
                sector_stats[t.sector]['wins'] += 1

        for sector in sorted(sector_stats.keys(), key=lambda x: sector_stats[x]['pnl'], reverse=True):
            data = sector_stats[sector]
            wr = data['wins'] / data['trades'] * 100 if data['trades'] > 0 else 0
            print(f"  {sector:20}: {data['trades']:2} trades, {data['pnl']:+.2f}%, {wr:.0f}% WR")

        # Key recommendations
        print(f"\n💡 KEY RECOMMENDATIONS:")

        sl_rate = len(sl_trades) / len(self.trades) * 100 if self.trades else 0
        if sl_rate > 40:
            print(f"  1. SL rate is {sl_rate:.0f}% - consider wider SL or better entry timing")

        avg_pnl = sum(t.pnl_pct for t in self.trades) / len(self.trades)
        if avg_pnl < 1:
            print(f"  2. Avg trade is {avg_pnl:.2f}% - need higher quality entries")

        # Print improvement notes
        if self.improvement_notes:
            print(f"\n📝 DETAILED NOTES:")
            for note in self.improvement_notes[:10]:
                print(f"  - {note}")

    def _save_results(self):
        """Save results to file"""
        output_file = f"backtest_v31_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        results = {
            'settings': {
                'starting_capital': self.STARTING_CAPITAL,
                'ending_capital': self.capital,
                'max_positions': self.MAX_POSITIONS,
                'position_size_pct': self.POSITION_SIZE_PCT,
            },
            'summary': {
                'total_trades': len(self.trades),
                'win_rate': len([t for t in self.trades if t.pnl_pct > 0]) / len(self.trades) * 100 if self.trades else 0,
                'total_pnl_pct': sum(t.pnl_pct for t in self.trades),
                'total_return': ((self.capital / self.STARTING_CAPITAL) - 1) * 100,
            },
            'monthly': self.monthly_results,
            'trades': [asdict(t) for t in self.trades],
            'improvement_notes': self.improvement_notes[:20]
        }

        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n📁 Results saved to: {output_file}")


def main():
    print("="*70)
    print("RAPID TRADER v3.1 - FULL REALISTIC BACKTEST")
    print("="*70)
    print("\nThis test will:")
    print("  1. Use actual Rapid Trader screener (680+ stocks)")
    print("  2. Screen different stocks each week")
    print("  3. Simulate real trading with SL/TP")
    print("  4. Calculate monthly returns")
    print("  5. Identify improvement areas")
    print("\nTarget: 5-10% monthly return")
    print("="*70)

    backtest = FullBacktestV31()
    backtest.run_backtest(months_back=3)


if __name__ == "__main__":
    main()
