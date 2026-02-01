#!/usr/bin/env python3
"""
Complete 6-Layer System Backtest
=================================

Test Period: June 1 - Dec 26, 2025 (6 months)
Expected: Win rate 50-60%, Monthly return 10-15%

Layer 1-3: Macro (Fed, Breadth, Sector)
Layer 4: Fundamental (Earnings, Revenue)
Layer 5: Catalyst (Breakout, Volume, Momentum)
Layer 6: Technical (RSI, RS, Volatility, Momentum)
"""

import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# Import complete system
from src.complete_growth_system import CompleteGrowthSystem
from src.market_regime_detector import MarketRegimeDetector


class CompleteSystemBacktest:
    """
    Backtest for Complete 6-Layer System
    """

    def __init__(self, start_date: str, end_date: str, use_precomputed_macro: bool = True):
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d')

        # Initialize complete system
        self.system = CompleteGrowthSystem()
        self.regime_detector = MarketRegimeDetector()

        # Trading state
        self.positions = []  # Open positions
        self.closed_trades = []  # Completed trades

        # Performance tracking
        self.daily_equity = []

        # Cache for macro data (to avoid repeated API calls)
        self.macro_cache = {}  # date -> macro_regime

        # Load pre-computed macro regimes if available
        self.use_precomputed_macro = use_precomputed_macro
        self.precomputed_regimes = {}

        if use_precomputed_macro:
            self._load_precomputed_macro()

    def _load_precomputed_macro(self):
        """Load pre-computed macro regimes from JSON file"""
        import json
        import os

        macro_file = 'macro_regimes_2025.json'

        if not os.path.exists(macro_file):
            print(f"⚠️  Pre-computed macro file not found: {macro_file}")
            print(f"   Run: python3 precompute_macro_regimes.py")
            print(f"   Falling back to real-time macro detection...")
            self.use_precomputed_macro = False
            return

        try:
            with open(macro_file, 'r') as f:
                data = json.load(f)

            self.precomputed_regimes = data['regimes']

            print(f"✅ Loaded {len(self.precomputed_regimes)} weeks of pre-computed macro data")
            print(f"   Period: {data['period']['start']} to {data['period']['end']}")
            print()

        except Exception as e:
            print(f"❌ Error loading pre-computed macro: {e}")
            print(f"   Falling back to real-time macro detection...")
            self.use_precomputed_macro = False

    def run_backtest(self):
        """Run complete backtest"""

        print("="*80)
        print("🚀 COMPLETE 6-LAYER SYSTEM BACKTEST")
        print("="*80)
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print()

        current_date = self.start_date

        while current_date <= self.end_date:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue

            # Update open positions FIRST
            self._update_positions(current_date)

            # Check for new entries if less than max positions (allow 2-3 concurrent)
            # OPTIMIZED: Only check Mon/Thu to reduce API calls (2x/week instead of 5x/week)
            MAX_POSITIONS = 3
            weekday = current_date.weekday()  # 0=Mon, 4=Fri

            if len(self.positions) < MAX_POSITIONS and weekday in [0, 3]:  # Monday or Thursday
                self._check_entries(current_date)

            # Move to next day
            current_date += timedelta(days=1)

        # Close any remaining positions
        self._close_all_positions(self.end_date)

        # Print results
        self._print_results()

    def _get_cached_macro(self, date: datetime):
        """Get macro regime with weekly caching to reduce API calls"""

        # Cache key: week number (e.g., "2025-W37")
        week_key = date.strftime("%Y-W%W")

        if week_key not in self.macro_cache:
            # Option 1: Use pre-computed data (FAST!)
            if self.use_precomputed_macro and week_key in self.precomputed_regimes:
                macro = self.precomputed_regimes[week_key]
                self.macro_cache[week_key] = macro
                # No print - too verbose

            # Option 2: Calculate in real-time (SLOW)
            else:
                macro = self.system.macro_detector.get_macro_regime(date)

                # FALLBACK: If macro returns UNKNOWN, use previous week's macro
                if macro['sector_stage'] == 'UNKNOWN' and macro['risk_score'] == 0:
                    # Try to use previous week's macro as fallback
                    prev_week_num = int(date.strftime("%W")) - 1
                    prev_year = date.strftime("%Y")
                    prev_week_key = f"{prev_year}-W{prev_week_num:02d}"

                    if prev_week_key in self.macro_cache:
                        prev_macro = self.macro_cache[prev_week_key]
                        print(f"   [⚠️  Macro API failed for week {week_key}, using {prev_week_key} fallback: {prev_macro['sector_stage']}, Risk: {prev_macro['risk_score']}/3]")
                        macro = prev_macro
                    else:
                        print(f"   [❌ Macro API failed for week {week_key}: UNKNOWN, Risk: 0/3]")
                else:
                    print(f"   [Macro cached for week {week_key}: {macro['sector_stage']}, Risk: {macro['risk_score']}/3]")

                self.macro_cache[week_key] = macro

        return self.macro_cache[week_key]

    def _screen_with_cache(self, date: datetime):
        """Screen for entries using cached macro regime"""

        # Get cached macro
        macro_regime = self._get_cached_macro(date)

        if not macro_regime['risk_on']:
            return []

        # Screen for fundamental + catalyst
        fundamental_passed = self.system.fundamental_screener.screen_universe(
            self.system.STOCK_UNIVERSE, date
        )

        if not fundamental_passed:
            return []

        # Check technical entry for each
        final_candidates = []

        for stock in fundamental_passed:
            symbol = stock['symbol']

            technical_ok, technical_details = self.system._check_technical_entry(
                symbol, date, macro_regime
            )

            if technical_ok:
                final_candidates.append({
                    'symbol': symbol,
                    'macro': macro_regime,
                    'fundamental': stock['fundamental'],
                    'catalyst': stock['catalyst'],
                    'technical': technical_details,
                    'total_score': stock['total_score'] + technical_details.get('score', 0),
                })

        # Sort by score
        final_candidates.sort(key=lambda x: x['total_score'], reverse=True)

        return final_candidates

    def _check_entries(self, date: datetime):
        """Check for new entry signals"""

        # OPTIMIZED: Removed sleep delay for faster backtesting
        # Macro is pre-computed, so no rate limiting risk there

        # Screen for entries using complete 6-layer system (quiet mode)
        # Use cached macro regime to avoid repeated API calls
        try:
            candidates = self._screen_with_cache(date)

            if not candidates:
                return

            # CRITICAL FIX: Filter out symbols we already hold (prevent AVGO × 3!)
            existing_symbols = {pos['symbol'] for pos in self.positions}
            available_candidates = [c for c in candidates if c['symbol'] not in existing_symbols]

            if not available_candidates:
                # All candidates are already held
                return

            # Take top available candidate (not already held)
            stock = available_candidates[0]
            symbol = stock['symbol']

            # Get entry price
            entry_price = stock['technical']['entry_price']

            # Calculate adaptive TP/SL
            volatility = stock['technical']['volatility']
            rs = stock['technical']['rs']
            beta = stock['technical']['beta']

            # Get regime for TP/SL calculation
            regime_info = self.regime_detector.get_current_regime(date)
            regime = regime_info['regime']
            strength = regime_info['details'].get('strength', 50)

            # Adaptive TP (based on volatility and RS)
            base_tp = 0.10  # 10% base
            if volatility > 50:
                base_tp += 0.03  # +3% for high volatility
            if rs > 15:
                base_tp += 0.02  # +2% for strong RS

            take_profit = entry_price * (1 + base_tp)

            # Adaptive SL (based on volatility and regime)
            base_sl = 0.06  # 6% base
            if volatility < 40:
                base_sl = 0.05  # Tighter for low volatility
            if regime == 'WEAK':
                base_sl = 0.04  # Tighter in weak regime

            stop_loss = entry_price * (1 - base_sl)

            # Create position
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
            print(f"   Score: {stock['total_score']}/200 (Fund: {stock['fundamental']['quality_score']}, Cat: {stock['catalyst']['catalyst_score']})")
            print(f"   Macro: {stock['macro']['sector_stage']}, Regime: {regime}")
            print()

        except Exception as e:
            # Skip if error (e.g., data unavailable)
            pass

    def _update_positions(self, date: datetime):
        """Update open positions and check exits"""

        if not self.positions:
            return

        positions_to_close = []

        for i, pos in enumerate(self.positions):
            symbol = pos['symbol']
            entry_date = pos['entry_date']
            days_held = (date - entry_date).days

            # Get current price
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=date, end=date + timedelta(days=1))

                if hist.empty:
                    continue

                current_price = hist['Close'].iloc[0]
                pos['current_price'] = current_price

                # Update peak price
                if current_price > pos['peak_price']:
                    pos['peak_price'] = current_price

                # Calculate returns
                current_return_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100

                # Dynamic stop loss tightening (NEW!)
                # After +5% profit → move SL to +2%
                # After +3% profit → move SL to breakeven
                if current_return_pct >= 5.0:
                    new_sl = pos['entry_price'] * 1.02  # Lock in +2%
                    if new_sl > pos['stop_loss']:
                        pos['stop_loss'] = new_sl
                elif current_return_pct >= 3.0:
                    new_sl = pos['entry_price']  # Move to breakeven
                    if new_sl > pos['stop_loss']:
                        pos['stop_loss'] = new_sl

                # Check exit conditions
                exit_reason = None

                # 1. Take profit hit
                if current_price >= pos['take_profit']:
                    exit_reason = 'TARGET_HIT'

                # 2. Stop loss hit
                elif current_price <= pos['stop_loss']:
                    exit_reason = 'HARD_STOP'

                # 3. Trailing peak exit (down 6-7% from peak after 5+ days)
                # RELAXED from -3/-4 to -6/-7 to let winners run further
                elif days_held >= 5:
                    drawdown_from_peak = ((current_price - pos['peak_price']) / pos['peak_price']) * 100

                    # More aggressive trailing for high volatility
                    trailing_threshold = -7.0 if pos['volatility'] > 50 else -6.0

                    if drawdown_from_peak < trailing_threshold:
                        exit_reason = 'TRAILING_PEAK'

                # 4. Regime change to WEAK/BEAR
                try:
                    regime_info = self.regime_detector.get_current_regime(date)
                    regime = regime_info['regime']

                    if regime == 'WEAK' and current_return_pct < 2:
                        # Exit if WEAK and not yet profitable
                        exit_reason = 'REGIME_WEAK'
                    elif regime == 'BEAR':
                        # Always exit in BEAR
                        exit_reason = 'REGIME_BEAR'
                except:
                    pass

                # 5. Max hold period (30 days)
                if days_held >= 30:
                    exit_reason = 'MAX_HOLD'

                # If exit triggered, close position
                if exit_reason:
                    positions_to_close.append((i, exit_reason, date, current_price))

            except Exception:
                continue

        # Close positions (in reverse to avoid index issues)
        for i, exit_reason, exit_date, exit_price in reversed(positions_to_close):
            pos = self.positions.pop(i)
            self._close_position(pos, exit_date, exit_price, exit_reason)

    def _close_position(self, pos: Dict, exit_date: datetime, exit_price: float, exit_reason: str):
        """Close a position"""

        entry_price = pos['entry_price']
        return_pct = ((exit_price - entry_price) / entry_price) * 100
        days_held = (exit_date - pos['entry_date']).days

        trade = {
            'symbol': pos['symbol'],
            'entry_date': pos['entry_date'],
            'exit_date': exit_date,
            'days_held': days_held,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return_pct': return_pct,
            'exit_reason': exit_reason,
            'volatility': pos['volatility'],
            'rs': pos['rs'],
            'beta': pos['beta'],
            'fundamental_score': pos['fundamental_score'],
            'catalyst_score': pos['catalyst_score'],
            'total_score': pos['total_score'],
            'macro_stage': pos['macro']['sector_stage'],
        }

        self.closed_trades.append(trade)

        result = "🟢" if return_pct > 0 else "🔴"
        print(f"{result} {exit_date.strftime('%Y-%m-%d')}: EXIT {pos['symbol']} @ ${exit_price:.2f} ({return_pct:+.2f}%) - {exit_reason} ({days_held}d)")

    def _close_all_positions(self, date: datetime):
        """Close all remaining positions at end of backtest"""

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

    def _print_results(self):
        """Print backtest results"""

        if not self.closed_trades:
            print("\n❌ No trades executed!")
            return

        df = pd.DataFrame(self.closed_trades)

        # Overall statistics
        total_trades = len(df)
        winners = len(df[df['return_pct'] > 0])
        losers = len(df[df['return_pct'] <= 0])
        win_rate = (winners / total_trades) * 100

        avg_return = df['return_pct'].mean()
        avg_winner = df[df['return_pct'] > 0]['return_pct'].mean() if winners > 0 else 0
        avg_loser = df[df['return_pct'] <= 0]['return_pct'].mean() if losers > 0 else 0

        total_return = df['return_pct'].sum()

        # Monthly breakdown
        df['month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
        monthly = df.groupby('month').agg({
            'return_pct': ['count', lambda x: (x > 0).sum(), 'mean', 'sum']
        }).round(2)

        # Exit reasons
        exit_reasons = df['exit_reason'].value_counts()

        # Stock quality
        avg_volatility = df['volatility'].mean()
        avg_rs = df['rs'].mean()
        avg_fundamental = df['fundamental_score'].mean()
        avg_catalyst = df['catalyst_score'].mean()

        # Print results
        print("\n" + "="*80)
        print("📊 COMPLETE 6-LAYER SYSTEM RESULTS")
        print("="*80)

        print(f"\n🎯 Overall Performance:")
        print(f"   Total Trades: {total_trades}")
        print(f"   Win Rate: {win_rate:.1f}% ({winners}W / {losers}L)")
        print(f"   Avg Return: {avg_return:+.2f}%")
        print(f"   Avg Winner: {avg_winner:+.2f}%")
        print(f"   Avg Loser: {avg_loser:+.2f}%")
        print(f"   Total Return: {total_return:+.2f}%")

        # Calculate expected monthly return
        test_months = (self.end_date - self.start_date).days / 30
        monthly_return = total_return / test_months if test_months > 0 else 0
        print(f"   Monthly Return: {monthly_return:+.2f}%")

        print(f"\n📈 Stock Quality:")
        print(f"   Avg Volatility: {avg_volatility:.1f}%")
        print(f"   Avg RS: {avg_rs:+.1f}%")
        print(f"   Avg Fundamental Score: {avg_fundamental:.0f}/100")
        print(f"   Avg Catalyst Score: {avg_catalyst:.0f}/100")

        print(f"\n🚪 Exit Reasons:")
        for reason, count in exit_reasons.items():
            pct = (count / total_trades) * 100
            print(f"   {reason:20s}: {count:3d} ({pct:5.1f}%)")

        print(f"\n📅 Monthly Breakdown:")
        print(monthly.to_string())

        print(f"\n📋 All Trades:")
        for i, trade in enumerate(df.to_dict('records'), 1):
            result = "🟢" if trade['return_pct'] > 0 else "🔴"
            print(f"{i:2d}. {result} {trade['entry_date'].strftime('%Y-%m-%d')} {trade['symbol']:6s} "
                  f"{trade['return_pct']:+6.2f}% ({trade['days_held']:2d}d) {trade['exit_reason']:15s} "
                  f"Score:{trade['total_score']:3d} {trade['macro_stage']}")

        # Target comparison
        print("\n" + "="*80)
        print("🎯 TARGET COMPARISON:")
        print("="*80)
        print(f"   Win Rate:       {win_rate:.1f}% (Target: 50-60%)")
        print(f"   Avg Return:     {avg_return:+.2f}% (Target: +5-8%)")
        print(f"   Monthly Return: {monthly_return:+.2f}% (Target: +10-15%)")
        print()

        if win_rate >= 50 and monthly_return >= 10:
            print("✅ TARGETS ACHIEVED!")
        elif win_rate >= 40 and monthly_return >= 5:
            print("⚠️  PARTIAL SUCCESS - Close to targets")
        else:
            print("❌ TARGETS NOT MET - Need improvement")


if __name__ == "__main__":
    # Run backtest
    backtest = CompleteSystemBacktest(
        start_date='2025-06-01',
        end_date='2025-12-26'
    )

    backtest.run_backtest()
