#!/usr/bin/env python3
"""
Phase B: Full Backtest Engine
Simulate entry timing strategies over 6 months of historical data
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

class EntryTimingBacktest:
    """
    Backtest different entry timing strategies
    """

    def __init__(self, symbols: List[str], start_date: str, end_date: str):
        """
        Initialize backtest

        Args:
            symbols: List of stock symbols to backtest
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        """
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.data = {}
        self.results = []

    def load_data(self):
        """Load historical data for all symbols"""
        print(f"📥 Loading data for {len(self.symbols)} symbols...")
        print(f"   Date range: {self.start_date} to {self.end_date}")

        for i, symbol in enumerate(self.symbols, 1):
            try:
                # Download with 1-minute interval for intraday analysis
                df = yf.download(
                    symbol,
                    start=self.start_date,
                    end=self.end_date,
                    interval='1d',  # Daily data (minute data limited to 7 days)
                    progress=False
                )

                if len(df) > 0:
                    # Flatten multi-index columns if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.droplevel(1)
                    self.data[symbol] = df
                    print(f"   [{i}/{len(self.symbols)}] ✅ {symbol}: {len(df)} days")
                else:
                    print(f"   [{i}/{len(self.symbols)}] ❌ {symbol}: No data")

            except Exception as e:
                print(f"   [{i}/{len(self.symbols)}] ❌ {symbol}: Error - {e}")

        print(f"\n✅ Loaded {len(self.data)}/{len(self.symbols)} symbols")

    def detect_signals(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detect Dip-Bounce signals

        Simplified logic:
        - Dip: Close < SMA20 AND dropped yesterday
        - Bounce: Close > Open today (green candle)

        Returns:
            DataFrame with signal dates and characteristics
        """
        signals = []

        # Calculate indicators
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
        df['ATR_pct'] = (df['ATR'] / df['Close']) * 100
        df['Volume_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()

        # Calculate daily changes
        df['Gap_pct'] = ((df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)) * 100
        df['Day_change_pct'] = ((df['Close'] - df['Open']) / df['Open']) * 100
        df['Prev_day_change'] = df['Close'].pct_change() * 100

        for date, row in df.iterrows():
            # Skip if not enough data
            if pd.isna(row['SMA20']) or pd.isna(row['SMA50']):
                continue

            # Dip-Bounce logic (relaxed for more signals)
            # Criteria: Yesterday dip + Today bounce/recovery + Not in strong downtrend
            is_dip = row['Prev_day_change'] < -0.5  # Dropped >0.5% yesterday (relaxed)
            is_bounce = row['Day_change_pct'] > 0  # Green candle today (relaxed)
            not_downtrend = row['Close'] > row['SMA50'] * 0.95  # Not >5% below SMA50

            if is_dip and is_bounce and not_downtrend:
                signals.append({
                    'date': date,
                    'symbol': symbol,
                    'open': row['Open'],
                    'high': row['High'],
                    'low': row['Low'],
                    'close': row['Close'],
                    'gap_pct': row['Gap_pct'],
                    'atr_pct': row['ATR_pct'],
                    'volume_ratio': row['Volume_ratio'],
                    'prev_day_change': row['Prev_day_change'],
                    'day_change': row['Day_change_pct']
                })

        return pd.DataFrame(signals)

    def simulate_entry(
        self,
        signal: Dict,
        entry_time_minutes: int,
        hold_days: int = 3
    ) -> Dict:
        """
        Simulate entry at specific time after open

        Args:
            signal: Signal dictionary
            entry_time_minutes: Minutes after 9:30 open (0, 5, 10, 15, 20, 30)
            hold_days: How many days to hold

        Returns:
            Trade result dict
        """
        symbol = signal['symbol']
        signal_date = signal['date']

        # Get price data for entry day
        day_open = signal['open']
        day_high = signal['high']
        day_low = signal['low']
        day_close = signal['close']
        day_range = day_high - day_low

        # Estimate entry price based on time
        # Simplified model: assume linear price movement through the day
        if entry_time_minutes == 0:
            # Open price
            entry_price = day_open
        elif entry_time_minutes <= 30:
            # Early: assume price between open and high/low
            # If gap up: likely near high in first 30min
            # If gap down: likely near low in first 30min
            if signal['gap_pct'] > 0.5:
                # Gap up: entry near high (bad)
                entry_price = day_open + (day_range * 0.7)  # 70% up from low
            elif signal['gap_pct'] < -0.5:
                # Gap down: entry near low (good for dip buying)
                entry_price = day_low + (day_range * 0.3)  # 30% up from low
            else:
                # Flat: mid-range
                entry_price = day_open + (day_range * 0.5)
        else:
            # Late: closer to close price
            entry_price = day_low + (day_range * 0.6)

        # Get exit price (hold for N days)
        try:
            df = self.data[symbol]
            signal_idx = df.index.get_loc(signal_date)

            if signal_idx + hold_days < len(df):
                exit_date = df.index[signal_idx + hold_days]
                exit_price = df.loc[exit_date, 'Close']

                # Calculate return
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100

                return {
                    'symbol': symbol,
                    'signal_date': signal_date,
                    'entry_time_min': entry_time_minutes,
                    'entry_price': entry_price,
                    'exit_date': exit_date,
                    'exit_price': exit_price,
                    'pnl_pct': pnl_pct,
                    'win': pnl_pct > 0,
                    'gap_pct': signal['gap_pct'],
                    'atr_pct': signal['atr_pct'],
                    'hold_days': hold_days
                }
            else:
                # Not enough data to exit
                return None

        except Exception as e:
            print(f"   Error simulating {symbol}: {e}")
            return None

    def run_backtest(self, entry_times: List[int] = [0, 5, 10, 15, 20, 30, 60]):
        """
        Run full backtest for all entry times

        Args:
            entry_times: List of minutes after open to test
        """
        print(f"\n🔬 Running backtest for {len(entry_times)} entry times...")
        print(f"   Entry times (min after open): {entry_times}")

        all_trades = []

        for symbol in self.data.keys():
            df = self.data[symbol]
            signals = self.detect_signals(symbol, df)

            if len(signals) == 0:
                continue

            print(f"\n📊 {symbol}: {len(signals)} signals detected")

            for _, signal in signals.iterrows():
                for entry_time in entry_times:
                    trade = self.simulate_entry(signal.to_dict(), entry_time)
                    if trade:
                        all_trades.append(trade)

        self.results = pd.DataFrame(all_trades)
        print(f"\n✅ Backtest complete: {len(self.results)} trades simulated")

    def analyze_results(self):
        """Analyze backtest results"""
        if len(self.results) == 0:
            print("❌ No results to analyze")
            return

        print("\n" + "=" * 80)
        print("📈 BACKTEST RESULTS - ENTRY TIMING ANALYSIS")
        print("=" * 80)

        # Group by entry time
        by_entry_time = self.results.groupby('entry_time_min').agg({
            'pnl_pct': ['count', 'mean', 'std'],
            'win': 'mean'
        }).round(2)

        by_entry_time.columns = ['Trades', 'Avg_Return_%', 'Std_%', 'Win_Rate']
        by_entry_time['Win_Rate'] = (by_entry_time['Win_Rate'] * 100).round(1)

        print("\n🕒 ENTRY TIME PERFORMANCE:")
        print(by_entry_time.to_string())

        # Group by gap category and entry time
        def categorize_gap(gap):
            if gap < -1.5:
                return 'Gap Down (<-1.5%)'
            elif gap < -0.5:
                return 'Mild Gap Down'
            elif gap <= 0.5:
                return 'Flat'
            elif gap <= 1.5:
                return 'Mild Gap Up'
            else:
                return 'Gap Up (>1.5%)'

        self.results['gap_category'] = self.results['gap_pct'].apply(categorize_gap)

        print("\n" + "=" * 80)
        print("📊 GAP CATEGORY + ENTRY TIME PERFORMANCE")
        print("=" * 80)

        for gap_cat in self.results['gap_category'].unique():
            gap_data = self.results[self.results['gap_category'] == gap_cat]

            gap_analysis = gap_data.groupby('entry_time_min').agg({
                'pnl_pct': ['count', 'mean'],
                'win': 'mean'
            })

            if len(gap_analysis) == 0:
                continue

            gap_analysis.columns = ['Trades', 'Avg_Return_%', 'Win_Rate_%']
            gap_analysis['Win_Rate_%'] = (gap_analysis['Win_Rate_%'] * 100).round(1)
            gap_analysis['Avg_Return_%'] = gap_analysis['Avg_Return_%'].round(2)

            print(f"\n{gap_cat}:")
            print(gap_analysis.to_string())

        # Find optimal entry time
        print("\n" + "=" * 80)
        print("🎯 OPTIMAL ENTRY TIMES")
        print("=" * 80)

        for gap_cat in self.results['gap_category'].unique():
            gap_data = self.results[self.results['gap_category'] == gap_cat]
            best_time = gap_data.groupby('entry_time_min')['pnl_pct'].mean().idxmax()
            best_return = gap_data.groupby('entry_time_min')['pnl_pct'].mean().max()
            best_wr = gap_data[gap_data['entry_time_min'] == best_time]['win'].mean() * 100

            print(f"{gap_cat:25s} → {best_time:3d} min ({best_return:+.2f}% avg, {best_wr:.1f}% WR)")

        print("\n" + "=" * 80)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == '__main__':
    print("=" * 80)
    print("PHASE B: FULL BACKTEST ENGINE")
    print("Entry Timing Optimization via Historical Simulation")
    print("=" * 80)

    # Define test parameters
    symbols = [
        # Recently traded
        'AIT', 'FAST', 'LMT', 'GOOGL', 'MCHP', 'SYNA', 'PRGO', 'GBCI', 'NOV',
        # Common Dip-Bounce candidates
        'PBF', 'HWKN', 'HTLD', 'MPWR', 'XPRO', 'FCX', 'MGY', 'CHRD', 'OXY',
        # Add more diverse stocks
        'AAPL', 'MSFT', 'NVDA', 'AMD', 'TSLA'
    ]

    # 6 months back
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')

    # Initialize backtest
    bt = EntryTimingBacktest(symbols, start_date, end_date)

    # Load data
    bt.load_data()

    # Run backtest for different entry times
    # 0 = 9:30 (open), 5 = 9:35, 10 = 9:40, 15 = 9:45, 20 = 9:50, 30 = 10:00, 60 = 10:30
    entry_times = [0, 5, 10, 15, 20, 30, 60]
    bt.run_backtest(entry_times)

    # Analyze
    bt.analyze_results()

    print("\n✅ Backtest complete!")
    print("\nNEXT STEPS:")
    print("1. Review optimal entry times for each gap category")
    print("2. Implement adaptive entry timing in Entry Protection Filter")
    print("3. Add Layer 4 with gap-aware timing logic")
