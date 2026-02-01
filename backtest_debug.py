#!/usr/bin/env python3
"""
Debug Backtest - Find Why Sept/Oct Trades Missing
==================================================

Run full backtest with detailed logging on specific dates.
"""

import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

from src.complete_growth_system import CompleteGrowthSystem
from src.market_regime_detector import MarketRegimeDetector


class DebugBacktest:
    """Backtest with detailed logging"""

    # Dates we know should have entries (from diagnostic)
    DEBUG_DATES = [
        '2025-09-10',  # Should enter AVGO
        '2025-09-26',  # Should enter AMAT
        '2025-10-01',  # Should enter LRCX/AMAT
        '2025-10-06',  # Should enter AMD
    ]

    def __init__(self, start_date: str, end_date: str):
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d')

        self.system = CompleteGrowthSystem()
        self.regime_detector = MarketRegimeDetector()

        self.positions = []
        self.closed_trades = []

    def run_backtest(self):
        """Run backtest with debug logging"""

        print("=" * 80)
        print("🐛 DEBUG BACKTEST - Detailed Logging")
        print("=" * 80)
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Debug dates: {', '.join(self.DEBUG_DATES)}")
        print()

        current_date = self.start_date

        while current_date <= self.end_date:
            date_str = current_date.strftime('%Y-%m-%d')

            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # Detailed logging on debug dates
            is_debug_date = date_str in self.DEBUG_DATES

            if is_debug_date:
                print(f"\n{'='*80}")
                print(f"🐛 DEBUG DATE: {date_str}")
                print(f"{'='*80}")
                print(f"Open positions: {len(self.positions)}")
                if self.positions:
                    for pos in self.positions:
                        days = (current_date - pos['entry_date']).days
                        print(f"  - {pos['symbol']} (entry: {pos['entry_date'].strftime('%Y-%m-%d')}, {days}d held)")

            # Update open positions FIRST
            self._update_positions(current_date, debug=is_debug_date)

            # Check for new entries
            MAX_POSITIONS = 3
            if len(self.positions) < MAX_POSITIONS:
                if is_debug_date:
                    print(f"\n🔍 Checking for entries ({len(self.positions)}/{MAX_POSITIONS} positions)...")

                self._check_entries(current_date, debug=is_debug_date)
            else:
                if is_debug_date:
                    print(f"\n⏸️  Skipping entry check - max positions reached ({len(self.positions)}/{MAX_POSITIONS})")

            current_date += timedelta(days=1)

        # Close remaining positions
        self._close_all_positions(self.end_date)

        # Print summary
        self._print_summary()

    def _check_entries(self, date: datetime, debug: bool = False):
        """Check for entries with optional debug logging"""

        import time
        time.sleep(0.5)

        try:
            candidates = self.system.screen_for_entries(date, quiet=not debug)

            if debug:
                if candidates:
                    print(f"   ✅ Found {len(candidates)} candidates")
                    for c in candidates[:3]:
                        print(f"      - {c['symbol']}: Score {c['total_score']}/200")
                else:
                    print(f"   ❌ No candidates found")

            if not candidates:
                return

            # Filter out existing symbols
            existing_symbols = {pos['symbol'] for pos in self.positions}
            available_candidates = [c for c in candidates if c['symbol'] not in existing_symbols]

            if not available_candidates:
                if debug:
                    print(f"   ⏸️  All candidates already held: {existing_symbols}")
                return

            # Enter top candidate
            stock = available_candidates[0]
            symbol = stock['symbol']

            entry_price = stock['technical']['entry_price']
            volatility = stock['technical']['volatility']
            rs = stock['technical']['rs']
            beta = stock['technical']['beta']

            regime_info = self.regime_detector.get_current_regime(date)
            regime = regime_info['regime']

            base_tp = 0.10
            if volatility > 50:
                base_tp += 0.03
            if rs > 15:
                base_tp += 0.02

            take_profit = entry_price * (1 + base_tp)

            base_sl = 0.06
            if volatility < 40:
                base_sl = 0.05
            if regime == 'WEAK':
                base_sl = 0.04

            stop_loss = entry_price * (1 - base_sl)

            position = {
                'symbol': symbol,
                'entry_date': date,
                'entry_price': entry_price,
                'current_price': entry_price,
                'take_profit': take_profit,
                'stop_loss': stop_loss,
                'peak_price': entry_price,
                'volatility': volatility,
                'rs': rs,
                'beta': beta,
                'macro': stock['macro'],
                'fundamental_score': stock['fundamental']['quality_score'],
                'catalyst_score': stock['catalyst']['catalyst_score'],
                'total_score': stock['total_score'],
            }

            self.positions.append(position)

            print(f"📈 {date.strftime('%Y-%m-%d')}: ENTER {symbol} @ ${entry_price:.2f}")
            print(f"   TP: ${take_profit:.2f} (+{base_tp*100:.1f}%), SL: ${stop_loss:.2f} (-{base_sl*100:.1f}%)")
            print(f"   Score: {stock['total_score']}/200")
            print()

        except Exception as e:
            if debug:
                print(f"   ❌ Error during entry check: {e}")
                import traceback
                traceback.print_exc()

    def _update_positions(self, date: datetime, debug: bool = False):
        """Update positions with optional debug logging"""

        if not self.positions:
            return

        positions_to_close = []

        for i, pos in enumerate(self.positions):
            symbol = pos['symbol']
            days_held = (date - pos['entry_date']).days

            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=date, end=date + timedelta(days=1))

                if hist.empty:
                    if debug:
                        print(f"   ⚠️  No price data for {symbol} on {date.strftime('%Y-%m-%d')}")
                    continue

                current_price = hist['Close'].iloc[0]
                pos['current_price'] = current_price

                if current_price > pos['peak_price']:
                    pos['peak_price'] = current_price

                current_return_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100

                # Dynamic SL tightening
                if current_return_pct >= 5.0:
                    new_sl = pos['entry_price'] * 1.02
                    if new_sl > pos['stop_loss']:
                        pos['stop_loss'] = new_sl
                elif current_return_pct >= 3.0:
                    new_sl = pos['entry_price']
                    if new_sl > pos['stop_loss']:
                        pos['stop_loss'] = new_sl

                # Check exits
                exit_reason = None

                if current_price >= pos['take_profit']:
                    exit_reason = 'TARGET_HIT'
                elif current_price <= pos['stop_loss']:
                    exit_reason = 'HARD_STOP'
                elif days_held >= 5:
                    drawdown_from_peak = ((current_price - pos['peak_price']) / pos['peak_price']) * 100
                    trailing_threshold = -7.0 if pos['volatility'] > 50 else -6.0
                    if drawdown_from_peak < trailing_threshold:
                        exit_reason = 'TRAILING_PEAK'

                try:
                    regime_info = self.regime_detector.get_current_regime(date)
                    regime = regime_info['regime']

                    if regime == 'WEAK' and current_return_pct < 2:
                        exit_reason = 'REGIME_WEAK'
                    elif regime == 'BEAR':
                        exit_reason = 'REGIME_BEAR'
                except:
                    pass

                if days_held >= 30:
                    exit_reason = 'MAX_HOLD'

                if exit_reason:
                    positions_to_close.append((i, exit_reason, date, current_price))

            except Exception as e:
                if debug:
                    print(f"   ❌ Error updating {symbol}: {e}")
                continue

        # Close positions
        for i, exit_reason, exit_date, exit_price in reversed(positions_to_close):
            pos = self.positions.pop(i)
            self._close_position(pos, exit_date, exit_price, exit_reason)

    def _close_position(self, pos: Dict, exit_date: datetime, exit_price: float, exit_reason: str):
        """Close position"""

        return_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
        days_held = (exit_date - pos['entry_date']).days

        trade = {
            'symbol': pos['symbol'],
            'entry_date': pos['entry_date'],
            'exit_date': exit_date,
            'days_held': days_held,
            'return_pct': return_pct,
            'exit_reason': exit_reason,
        }

        self.closed_trades.append(trade)

        result = "🟢" if return_pct > 0 else "🔴"
        print(f"{result} {exit_date.strftime('%Y-%m-%d')}: EXIT {pos['symbol']} @ ${exit_price:.2f} "
              f"({return_pct:+.2f}%) - {exit_reason} ({days_held}d)")

    def _close_all_positions(self, date: datetime):
        """Close all remaining positions"""

        for pos in self.positions[:]:
            try:
                ticker = yf.Ticker(pos['symbol'])
                hist = ticker.history(start=date, end=date + timedelta(days=1))

                if not hist.empty:
                    exit_price = hist['Close'].iloc[0]
                    self._close_position(pos, date, exit_price, 'BACKTEST_END')
            except:
                pass

        self.positions = []

    def _print_summary(self):
        """Print brief summary"""

        if not self.closed_trades:
            print("\n❌ No trades executed!")
            return

        df = pd.DataFrame(self.closed_trades)

        total = len(df)
        winners = len(df[df['return_pct'] > 0])
        win_rate = (winners / total) * 100
        avg_return = df['return_pct'].mean()
        total_return = df['return_pct'].sum()

        print("\n" + "=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"Total Trades: {total}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Avg Return: {avg_return:+.2f}%")
        print(f"Total Return: {total_return:+.2f}%")


if __name__ == "__main__":
    backtest = DebugBacktest(
        start_date='2025-06-01',
        end_date='2025-12-26'
    )

    backtest.run_backtest()
