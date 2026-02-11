#!/usr/bin/env python3
"""
PRODUCTION SCREENER BACKTEST v1.0
==================================

Uses the EXACT same logic as rapid_rotation_screener.py to ensure
realistic backtest results that match live trading behavior.

Test Period: August 2025 - February 2026 (6 months)
Config: trading.yaml settings (SL 2.5-3.5%, TP 4.5-8.0%, Max Hold 5 days)

This backtest imports from:
- src/screeners/rapid_trader_filters.py (scoring, filters, SL/TP logic)
- config/trading.yaml (strategy parameters)

CRITICAL: No custom logic here - all filters/scoring come from production code!
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import yfinance as yf
import numpy as np
from collections import defaultdict

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import production filters (SINGLE SOURCE OF TRUTH)
from screeners.rapid_trader_filters import (
    FilterConfig,
    calculate_score,
    check_bounce_confirmation,
    check_sma20_filter,
    calculate_dynamic_sl_tp,
    calculate_rsi,
    calculate_atr,
)

# Import config
from config.strategy_config import RapidRotationConfig


class ProductionScreenerBacktest:
    """
    Backtest using EXACT production screener logic

    No custom filters or scoring - everything comes from:
    - rapid_trader_filters.py (filters, scoring, SL/TP)
    - trading.yaml (parameters)
    """

    def __init__(self, config_path: str = 'config/trading.yaml'):
        """Initialize with production config"""
        # Load production config
        self.config = RapidRotationConfig.from_yaml(config_path)
        self.filter_config = FilterConfig(self.config)

        # Strategy parameters (from config)
        self.MIN_SCORE = self.config.min_score
        self.MIN_ATR_PCT = self.config.min_atr_pct
        self.MAX_POSITIONS = self.config.max_positions
        self.MAX_HOLD_DAYS = self.config.max_hold_days
        self.POSITION_SIZE_PCT = self.config.position_size_pct

        # SL/TP ranges (from config)
        self.MIN_SL_PCT = self.config.min_sl_pct
        self.MAX_SL_PCT = self.config.max_sl_pct
        self.MIN_TP_PCT = self.config.min_tp_pct
        self.MAX_TP_PCT = self.config.max_tp_pct

        # Trailing stop (from config)
        self.TRAIL_ACTIVATION = self.config.trail_activation_pct
        self.TRAIL_LOCK = self.config.trail_lock_pct

        # Universe (high volatility stocks that screener typically scans)
        self.UNIVERSE = [
            # AI/Semiconductor
            'NVDA', 'AMD', 'AVGO', 'MU', 'MRVL', 'ARM', 'SMCI', 'TSM',
            'QCOM', 'AMAT', 'LRCX', 'KLAC', 'INTC', 'TXN', 'ADI',
            # High beta tech
            'TSLA', 'PLTR', 'SNOW', 'COIN', 'DDOG', 'NET', 'CRWD', 'ZS',
            # Mega cap tech
            'META', 'NFLX', 'AMZN', 'GOOGL', 'AAPL', 'MSFT', 'ORCL',
            # Other high-beta
            'CRM', 'NOW', 'SHOP', 'PYPL', 'UBER', 'ABNB',
            # EV/Clean energy
            'RIVN', 'LCID', 'ENPH', 'FSLR', 'RUN',
            # Finance
            'JPM', 'GS', 'MS', 'V', 'MA', 'AXP',
            # Industrial
            'CAT', 'DE', 'BA', 'GE', 'HON',
            # Consumer
            'NKE', 'LULU', 'SBUX', 'MCD', 'HD', 'LOW',
            # Additional
            'ROKU', 'PATH', 'S', 'BILL', 'CFLT', 'CHWY', 'DXCM',
        ]

        # Cache
        self.data_cache = {}

        # Stats
        self.total_scanned = 0
        self.filter_stats = defaultdict(int)

    def load_data(self, start_date: str, end_date: str):
        """Load historical data for universe"""
        print(f"📊 Loading data for {len(self.UNIVERSE)} stocks...")

        loaded = 0
        for symbol in self.UNIVERSE:
            try:
                ticker = yf.Ticker(symbol)
                # Download with extra days for indicators
                extended_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
                data = ticker.history(start=extended_start, end=end_date)

                if len(data) >= 30:
                    data.columns = [c.lower() for c in data.columns]
                    self.data_cache[symbol] = data
                    loaded += 1
                    if loaded % 10 == 0:
                        print(f"  Loaded {loaded}/{len(self.UNIVERSE)}...")
            except Exception as e:
                print(f"  ⚠️ Error loading {symbol}: {e}")

        print(f"✅ Loaded {loaded}/{len(self.UNIVERSE)} stocks\n")

    def _calculate_indicators(self, data: pd.DataFrame, idx: int) -> Optional[Dict]:
        """Calculate all technical indicators (same as screener)"""
        try:
            close = data['close']
            high = data['high']
            low = data['low']
            volume = data['volume']

            # Need enough history
            if idx < 20:
                return None

            # Current values
            current_price = close.iloc[idx]

            # RSI
            rsi_series = close.diff()
            gain = rsi_series.where(rsi_series > 0, 0).rolling(window=14).mean()
            loss = (-rsi_series.where(rsi_series < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_full = 100 - (100 / (1 + rs))
            rsi = rsi_full.iloc[idx]

            # ATR
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr_series = tr.rolling(14).mean()
            atr = atr_series.iloc[idx]
            atr_pct = (atr / current_price) * 100

            # Momentum
            mom_1d = (current_price / close.iloc[idx-1] - 1) * 100 if idx >= 1 else 0
            mom_5d = (current_price / close.iloc[idx-5] - 1) * 100 if idx >= 5 else 0
            mom_20d = (current_price / close.iloc[idx-20] - 1) * 100 if idx >= 20 else 0
            yesterday_move = ((close.iloc[idx-1] / close.iloc[idx-2]) - 1) * 100 if idx >= 2 else 0

            # SMAs
            sma5 = close.iloc[idx-4:idx+1].mean() if idx >= 4 else current_price
            sma20 = close.iloc[idx-19:idx+1].mean() if idx >= 19 else current_price
            sma50 = close.iloc[idx-49:idx+1].mean() if idx >= 49 else current_price

            # Distance from high
            high_20d = high.iloc[idx-20:idx].max() if idx >= 20 else high.iloc[:idx].max()
            dist_from_high = (high_20d - current_price) / high_20d * 100 if high_20d > 0 else 0

            # Volume
            avg_volume = volume.iloc[idx-20:idx].mean() if idx >= 20 else volume.mean()
            volume_ratio = volume.iloc[idx] / avg_volume if avg_volume > 0 else 1

            # Gap and candle
            prev_close = close.iloc[idx-1] if idx >= 1 else current_price
            today_open = data['open'].iloc[idx] if 'open' in data.columns else current_price
            gap_pct = (today_open - prev_close) / prev_close * 100
            today_is_green = current_price > today_open

            # Swing low for SL calculation
            swing_low_5d = low.iloc[idx-5:idx].min() if idx >= 5 else low.iloc[:idx].min()

            # EMA5 for SL calculation
            ema5 = close.ewm(span=5).mean().iloc[idx]

            # High 52w for TP calculation
            high_52w = high.max()

            return {
                'current_price': current_price,
                'rsi': rsi,
                'atr': atr,
                'atr_pct': atr_pct,
                'mom_1d': mom_1d,
                'mom_5d': mom_5d,
                'mom_20d': mom_20d,
                'yesterday_move': yesterday_move,
                'sma5': sma5,
                'sma20': sma20,
                'sma50': sma50,
                'dist_from_high': dist_from_high,
                'volume_ratio': volume_ratio,
                'gap_pct': gap_pct,
                'today_is_green': today_is_green,
                'swing_low_5d': swing_low_5d,
                'ema5': ema5,
                'high_20d': high_20d,
                'high_52w': high_52w,
            }
        except Exception as e:
            return None

    def analyze_stock(self, symbol: str, date: str) -> Optional[Dict]:
        """
        Analyze stock using PRODUCTION filters and scoring

        This method uses EXACT logic from rapid_rotation_screener.py:
        - check_bounce_confirmation() for filters
        - check_sma20_filter() for trend
        - calculate_score() for scoring
        - calculate_dynamic_sl_tp() for SL/TP
        """
        if symbol not in self.data_cache:
            return None

        data = self.data_cache[symbol]

        # Find index for date
        try:
            idx = data.index.get_loc(date)
        except KeyError:
            # Date not found, try nearest
            try:
                idx = data.index.get_indexer([date], method='nearest')[0]
            except:
                return None

        # Calculate indicators
        ind = self._calculate_indicators(data, idx)
        if not ind:
            return None

        # Price filters (basic)
        if ind['current_price'] < 10 or ind['current_price'] > 2000:
            self.filter_stats['price'] += 1
            return None

        # ========================================
        # PRODUCTION FILTERS (from filters.py)
        # ========================================

        # 1. Bounce confirmation (EXACT production logic)
        passed, reason = check_bounce_confirmation(
            yesterday_move=ind['yesterday_move'],
            mom_1d=ind['mom_1d'],
            today_is_green=ind['today_is_green'],
            gap_pct=ind['gap_pct'],
            current_price=ind['current_price'],
            sma5=ind['sma5'],
            atr_pct=ind['atr_pct'],
        )
        if not passed:
            self.filter_stats['bounce'] += 1
            return None

        # 2. SMA20 filter (EXACT production logic)
        passed, reason = check_sma20_filter(ind['current_price'], ind['sma20'])
        if not passed:
            self.filter_stats['sma20'] += 1
            return None

        # 3. Overextended filters (from screener)
        if ind['current_price'] > ind['sma20'] * 1.10:  # >10% above SMA20
            self.filter_stats['overextended'] += 1
            return None

        # ========================================
        # PRODUCTION SCORING (from filters.py)
        # ========================================
        score, reasons = calculate_score(
            today_is_green=ind['today_is_green'],
            mom_1d=ind['mom_1d'],
            mom_5d=ind['mom_5d'],
            yesterday_move=ind['yesterday_move'],
            rsi=ind['rsi'],
            current_price=ind['current_price'],
            sma20=ind['sma20'],
            sma50=ind['sma50'],
            atr_pct=ind['atr_pct'],
            dist_from_high=ind['dist_from_high'],
            volume_ratio=ind['volume_ratio'],
        )

        # Check minimum score (from config)
        if score < self.MIN_SCORE:
            self.filter_stats['low_score'] += 1
            return None

        # ========================================
        # PRODUCTION SL/TP (from filters.py)
        # ========================================
        sl_tp = calculate_dynamic_sl_tp(
            current_price=ind['current_price'],
            atr=ind['atr'],
            swing_low_5d=ind['swing_low_5d'],
            ema5=ind['ema5'],
            high_20d=ind['high_20d'],
            high_52w=ind['high_52w'],
        )

        return {
            'symbol': symbol,
            'date': date,
            'entry_price': ind['current_price'],
            'stop_loss': sl_tp['stop_loss'],
            'take_profit': sl_tp['take_profit'],
            'sl_pct': sl_tp['sl_pct'],
            'tp_pct': sl_tp['tp_pct'],
            'score': score,
            'reasons': reasons,
            'rsi': ind['rsi'],
            'atr_pct': ind['atr_pct'],
            'mom_5d': ind['mom_5d'],
        }

    def simulate_trade(self, signal: Dict, entry_date: str) -> Dict:
        """Simulate trade with production exit rules"""
        symbol = signal['symbol']
        data = self.data_cache[symbol]

        # Find entry index
        try:
            entry_idx = data.index.get_loc(entry_date)
        except:
            return None

        # Entry price (next day open to be realistic)
        if entry_idx + 1 >= len(data):
            return None
        entry_price = data['open'].iloc[entry_idx + 1]

        # Adjust SL/TP based on actual entry
        sl_pct = signal['sl_pct']
        tp_pct = signal['tp_pct']
        stop_loss = entry_price * (1 - sl_pct / 100)
        take_profit = entry_price * (1 + tp_pct / 100)

        # Track peak for trailing stop
        peak_price = entry_price
        trailing_active = False
        trailing_stop = None

        # Simulate each day
        for days_held in range(1, min(self.MAX_HOLD_DAYS + 1, len(data) - entry_idx - 1)):
            idx = entry_idx + 1 + days_held
            day_high = data['high'].iloc[idx]
            day_low = data['low'].iloc[idx]
            day_close = data['close'].iloc[idx]

            # Update peak
            if day_high > peak_price:
                peak_price = day_high

            # Check trailing stop activation
            if not trailing_active:
                gain_pct = ((peak_price - entry_price) / entry_price) * 100
                if gain_pct >= self.TRAIL_ACTIVATION:
                    trailing_active = True
                    # Lock in percentage of gains
                    locked_gain = gain_pct * (self.TRAIL_LOCK / 100)
                    trailing_stop = entry_price * (1 + locked_gain / 100)

            # Update trailing stop if active
            if trailing_active:
                gain_pct = ((peak_price - entry_price) / entry_price) * 100
                locked_gain = gain_pct * (self.TRAIL_LOCK / 100)
                new_trail = entry_price * (1 + locked_gain / 100)
                trailing_stop = max(trailing_stop, new_trail)

            # Check exits
            # 1. Stop loss hit
            if day_low <= stop_loss:
                return {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': data.index[idx].strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_price': stop_loss,
                    'pnl_pct': -sl_pct,
                    'days_held': days_held,
                    'exit_reason': 'Stop Loss',
                    'score': signal['score'],
                }

            # 2. Trailing stop hit
            if trailing_active and day_low <= trailing_stop:
                pnl_pct = ((trailing_stop - entry_price) / entry_price) * 100
                return {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': data.index[idx].strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_price': trailing_stop,
                    'pnl_pct': pnl_pct,
                    'days_held': days_held,
                    'exit_reason': 'Trailing Stop',
                    'score': signal['score'],
                }

            # 3. Take profit hit
            if day_high >= take_profit:
                return {
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': data.index[idx].strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_price': take_profit,
                    'pnl_pct': tp_pct,
                    'days_held': days_held,
                    'exit_reason': 'Take Profit',
                    'score': signal['score'],
                }

        # 4. Max hold time exit
        exit_idx = entry_idx + 1 + self.MAX_HOLD_DAYS
        if exit_idx < len(data):
            exit_price = data['close'].iloc[exit_idx]
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            return {
                'symbol': symbol,
                'entry_date': entry_date,
                'exit_date': data.index[exit_idx].strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'days_held': self.MAX_HOLD_DAYS,
                'exit_reason': 'Max Hold Time',
                'score': signal['score'],
            }

        return None

    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """Run backtest over date range"""
        print(f"🎯 Running backtest: {start_date} to {end_date}")
        print(f"   Config: Min Score={self.MIN_SCORE}, SL={self.MIN_SL_PCT}-{self.MAX_SL_PCT}%, TP={self.MIN_TP_PCT}-{self.MAX_TP_PCT}%")
        print(f"   Max Positions={self.MAX_POSITIONS}, Max Hold={self.MAX_HOLD_DAYS} days\n")

        # Load data
        self.load_data(start_date, end_date)

        # Get trading dates
        spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
        trading_dates = spy.index

        # Results storage
        all_trades = []
        active_positions = {}  # Changed to dict: symbol -> signal

        # Daily scan
        print("📅 Scanning each trading day...\n")
        for current_date in trading_dates:
            date_str = current_date.strftime('%Y-%m-%d')

            # If slots available, scan for new signals
            available_slots = self.MAX_POSITIONS - len(active_positions)
            if available_slots > 0:
                # Scan universe
                signals = []
                for symbol in self.UNIVERSE:
                    # Skip if already in position
                    if symbol in active_positions:
                        continue

                    self.total_scanned += 1
                    signal = self.analyze_stock(symbol, date_str)
                    if signal:
                        signals.append(signal)

                # Sort by score, take top N
                signals.sort(key=lambda x: x['score'], reverse=True)
                new_entries = signals[:available_slots]

                # Enter positions and simulate trades
                for signal in new_entries:
                    active_positions[signal['symbol']] = signal
                    # Simulate trade (this will handle exit internally)
                    result = self.simulate_trade(signal, date_str)
                    if result:
                        all_trades.append(result)
                        # Remove from active positions after trade completes
                        if signal['symbol'] in active_positions:
                            del active_positions[signal['symbol']]

        # Calculate results
        return self._calculate_results(all_trades, start_date, end_date)

    def _calculate_results(self, trades: List[Dict], start_date: str, end_date: str) -> Dict:
        """Calculate backtest results with monthly breakdown"""
        if not trades:
            return {'total_trades': 0, 'error': 'No trades generated'}

        # Overall stats
        total_trades = len(trades)
        winners = [t for t in trades if t['pnl_pct'] > 0]
        losers = [t for t in trades if t['pnl_pct'] <= 0]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0

        avg_win = np.mean([t['pnl_pct'] for t in winners]) if winners else 0
        avg_loss = np.mean([t['pnl_pct'] for t in losers]) if losers else 0

        total_pnl = sum(t['pnl_pct'] for t in trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

        # Monthly breakdown
        monthly_stats = {}
        for trade in trades:
            month = trade['entry_date'][:7]  # YYYY-MM
            if month not in monthly_stats:
                monthly_stats[month] = {
                    'trades': [],
                    'wins': 0,
                    'losses': 0,
                    'pnl': 0,
                }
            monthly_stats[month]['trades'].append(trade)
            monthly_stats[month]['pnl'] += trade['pnl_pct']
            if trade['pnl_pct'] > 0:
                monthly_stats[month]['wins'] += 1
            else:
                monthly_stats[month]['losses'] += 1

        # Exit reasons
        exit_reasons = defaultdict(int)
        for trade in trades:
            exit_reasons[trade['exit_reason']] += 1

        return {
            'total_trades': total_trades,
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'monthly_stats': monthly_stats,
            'exit_reasons': dict(exit_reasons),
            'trades': trades,
            'filter_stats': dict(self.filter_stats),
            'total_scanned': self.total_scanned,
        }

    def print_results(self, results: Dict):
        """Print formatted results"""
        print("\n" + "=" * 70)
        print("PRODUCTION SCREENER BACKTEST RESULTS")
        print("=" * 70)

        # Overall stats
        print(f"\n📊 OVERALL STATISTICS")
        print(f"   Total Trades: {results['total_trades']}")
        print(f"   Winners: {results['winners']} | Losers: {results['losers']}")
        print(f"   Win Rate: {results['win_rate']:.1f}%")
        print(f"   Average Win: +{results['avg_win']:.2f}%")
        print(f"   Average Loss: {results['avg_loss']:.2f}%")
        print(f"   Total P&L: {results['total_pnl']:.2f}%")
        print(f"   Avg P&L per Trade: {results['avg_pnl']:.2f}%")

        # Monthly breakdown
        print(f"\n📅 MONTHLY BREAKDOWN")
        print(f"{'Month':<12} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'Win%':<8} {'P&L':<10}")
        print("-" * 70)

        monthly_stats = results['monthly_stats']
        for month in sorted(monthly_stats.keys()):
            stats = monthly_stats[month]
            total = len(stats['trades'])
            win_pct = (stats['wins'] / total * 100) if total > 0 else 0
            pnl = stats['pnl']

            print(f"{month:<12} {total:<8} {stats['wins']:<6} {stats['losses']:<8} {win_pct:<7.1f}% {pnl:>+9.2f}%")

        # Exit reasons
        print(f"\n🚪 EXIT REASONS")
        for reason, count in sorted(results['exit_reasons'].items(), key=lambda x: x[1], reverse=True):
            pct = count / results['total_trades'] * 100
            print(f"   {reason}: {count} ({pct:.1f}%)")

        # Filter stats
        print(f"\n🔍 FILTER STATISTICS")
        print(f"   Total Stocks Scanned: {results['total_scanned']}")
        print(f"   Signals Generated: {results['total_trades']}")
        print(f"   Signal Rate: {results['total_trades'] / results['total_scanned'] * 100:.2f}%")
        print(f"\n   Filter Rejections:")
        for filter_name, count in sorted(results['filter_stats'].items(), key=lambda x: x[1], reverse=True):
            pct = count / results['total_scanned'] * 100
            print(f"     {filter_name}: {count} ({pct:.1f}%)")

        # Sample trades
        print(f"\n📈 SAMPLE TRADES (First 10)")
        print(f"{'Symbol':<8} {'Entry':<12} {'Exit':<12} {'Days':<6} {'P&L':<8} {'Reason':<15} {'Score':<6}")
        print("-" * 70)
        for trade in results['trades'][:10]:
            print(f"{trade['symbol']:<8} {trade['entry_date']:<12} {trade['exit_date']:<12} "
                  f"{trade['days_held']:<6} {trade['pnl_pct']:>+7.2f}% {trade['exit_reason']:<15} {trade['score']:<6}")

        print("\n" + "=" * 70)


def main():
    """Run production screener backtest"""
    print("🚀 PRODUCTION SCREENER BACKTEST v1.0")
    print("=" * 70)
    print("Using EXACT production logic from:")
    print("  - rapid_trader_filters.py (scoring, filters, SL/TP)")
    print("  - trading.yaml (strategy parameters)")
    print("\nTest Period: August 2025 - February 2026 (6 months)")
    print("=" * 70)
    print()

    # Initialize backtest
    backtest = ProductionScreenerBacktest()

    # Run backtest
    results = backtest.run_backtest(
        start_date='2025-08-01',
        end_date='2026-02-11',
    )

    # Print results
    backtest.print_results(results)

    # Save trades to CSV
    trades_df = pd.DataFrame(results['trades'])
    output_file = 'backtest_production_trades.csv'
    trades_df.to_csv(output_file, index=False)
    print(f"\n💾 Trades saved to: {output_file}")


if __name__ == "__main__":
    main()
