#!/usr/bin/env python3
"""
Backtest Latest Implementation (v9)
- Static Universe 680 stocks + AI supplement 50-100
- Momentum Gates v6.4 ADAPTIVE
- ATR <= 3%
- Entry Score >= 55
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger
from main import StockAnalyzer
from screeners.growth_catalyst_screener import GrowthCatalystScreener
from api.data_manager import DataManager

# Suppress verbose logging
import logging
logging.getLogger().setLevel(logging.WARNING)
logger.remove()
logger.add(sys.stderr, level="WARNING")


def get_price_data(data_manager, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """Get historical price data for a symbol"""
    try:
        df = data_manager.get_price_data(symbol, period='1y')
        if df is None or df.empty:
            return None

        df.index = pd.to_datetime(df.index)
        mask = (df.index >= start_date) & (df.index <= end_date)
        return df[mask]
    except Exception as e:
        return None


def simulate_trade(df: pd.DataFrame, entry_date: str, max_hold_days: int = 30,
                   target_pct: float = 10.0, stop_loss_pct: float = 7.0) -> Dict:
    """
    Simulate a single trade with exit rules

    Exit conditions:
    1. Target hit (+10%)
    2. Stop loss hit (-7%)
    3. Max hold period (30 days)
    """
    try:
        entry_idx = df.index.get_loc(pd.Timestamp(entry_date))
    except KeyError:
        # Find nearest trading day
        entry_ts = pd.Timestamp(entry_date)
        future_dates = df.index[df.index >= entry_ts]
        if len(future_dates) == 0:
            return None
        entry_idx = df.index.get_loc(future_dates[0])

    entry_price = df.iloc[entry_idx]['Close']
    target_price = entry_price * (1 + target_pct / 100)
    stop_price = entry_price * (1 - stop_loss_pct / 100)

    # Simulate day by day
    for i in range(1, min(max_hold_days + 1, len(df) - entry_idx)):
        current_idx = entry_idx + i
        if current_idx >= len(df):
            break

        high = df.iloc[current_idx]['High']
        low = df.iloc[current_idx]['Low']
        close = df.iloc[current_idx]['Close']
        exit_date = df.index[current_idx]

        # Check stop loss first (intraday)
        if low <= stop_price:
            return {
                'entry_date': df.index[entry_idx],
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': stop_price,
                'return_pct': -stop_loss_pct,
                'hold_days': i,
                'exit_reason': 'STOP_LOSS'
            }

        # Check target hit (intraday)
        if high >= target_price:
            return {
                'entry_date': df.index[entry_idx],
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': target_price,
                'return_pct': target_pct,
                'hold_days': i,
                'exit_reason': 'TARGET_HIT'
            }

    # Max hold period - exit at close
    final_idx = min(entry_idx + max_hold_days, len(df) - 1)
    final_close = df.iloc[final_idx]['Close']
    return_pct = ((final_close - entry_price) / entry_price) * 100

    return {
        'entry_date': df.index[entry_idx],
        'exit_date': df.index[final_idx],
        'entry_price': entry_price,
        'exit_price': final_close,
        'return_pct': return_pct,
        'hold_days': final_idx - entry_idx,
        'exit_reason': 'MAX_HOLD'
    }


def run_backtest(start_date: str, end_date: str, max_stocks_per_day: int = 5):
    """
    Run backtest for the period

    Strategy:
    - Screen stocks each Monday
    - Take top N stocks by entry score
    - Hold up to 30 days or until target/stop hit
    """
    print("=" * 70)
    print("BACKTEST: Latest Implementation v9")
    print("=" * 70)
    print(f"Period: {start_date} to {end_date}")
    print(f"Max stocks per screening: {max_stocks_per_day}")
    print(f"Target: +10%, Stop Loss: -7%, Max Hold: 30 days")
    print("=" * 70)

    # Initialize
    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)
    data_manager = DataManager()

    # Get static universe for faster backtesting
    universe = list(set(GrowthCatalystScreener.STATIC_UNIVERSE))
    print(f"\nUniverse size: {len(universe)} stocks")

    # Generate screening dates (every Monday)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    screening_dates = []
    current = start
    while current <= end:
        if current.weekday() == 0:  # Monday
            screening_dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    print(f"Screening dates: {len(screening_dates)} Mondays")

    # Track all trades
    all_trades = []

    # Run screening for each date
    for screen_date in screening_dates:
        print(f"\n📅 Screening {screen_date}...")

        # Get candidates that pass momentum gates
        candidates = []
        tested = 0

        for symbol in universe:
            if tested >= 200:  # Test max 200 stocks per screening
                break

            try:
                # Get price data
                df = get_price_data(data_manager, symbol,
                                   (pd.Timestamp(screen_date) - timedelta(days=100)).strftime('%Y-%m-%d'),
                                   (pd.Timestamp(screen_date) + timedelta(days=45)).strftime('%Y-%m-%d'))

                if df is None or len(df) < 50:
                    continue

                tested += 1

                # Check if date exists in data
                if pd.Timestamp(screen_date) not in df.index:
                    continue

                # Calculate metrics for momentum gates
                screen_idx = df.index.get_loc(pd.Timestamp(screen_date))
                if screen_idx < 20:
                    continue

                close = df.iloc[screen_idx]['Close']

                # MA20
                ma20 = df['Close'].iloc[screen_idx-20:screen_idx].mean()
                ma20_pct = ((close - ma20) / ma20) * 100

                # 52-week position
                high_52w = df['High'].iloc[max(0, screen_idx-252):screen_idx].max()
                low_52w = df['Low'].iloc[max(0, screen_idx-252):screen_idx].min()
                position_52w = ((close - low_52w) / (high_52w - low_52w)) * 100 if high_52w > low_52w else 50

                # Momentum 20d
                if screen_idx >= 20:
                    close_20d_ago = df['Close'].iloc[screen_idx - 20]
                    momentum_20d = ((close - close_20d_ago) / close_20d_ago) * 100
                else:
                    momentum_20d = 0

                # RSI 14
                delta = df['Close'].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_14 = rsi.iloc[screen_idx] if not pd.isna(rsi.iloc[screen_idx]) else 50

                # ATR %
                tr = pd.DataFrame({
                    'hl': df['High'] - df['Low'],
                    'hc': abs(df['High'] - df['Close'].shift(1)),
                    'lc': abs(df['Low'] - df['Close'].shift(1))
                }).max(axis=1)
                atr = tr.rolling(14).mean()
                atr_pct = (atr.iloc[screen_idx] / close) * 100 if close > 0 else 10

                # Volume ratio
                vol_20 = df['Volume'].iloc[screen_idx-20:screen_idx].mean()
                vol_today = df['Volume'].iloc[screen_idx]
                volume_ratio = vol_today / vol_20 if vol_20 > 0 else 1

                # v6.4 ADAPTIVE Momentum Gates
                gates_passed = True

                # Gate 1: Price > MA20 (within -3%)
                if ma20_pct < -3:
                    gates_passed = False

                # Gate 2: 52-week position 50-90%
                if not (50 <= position_52w <= 90):
                    gates_passed = False

                # Gate 3: Momentum 20d > -5%
                if momentum_20d < -5:
                    gates_passed = False

                # Gate 4: RSI 40-75
                if not (40 <= rsi_14 <= 75):
                    gates_passed = False

                # Gate 5: ATR <= 3%
                if atr_pct > 3:
                    gates_passed = False

                # Gate 6: Volume ratio >= 0.7
                if volume_ratio < 0.7:
                    gates_passed = False

                if gates_passed:
                    # Calculate entry score (simplified)
                    momentum_score = min(100, max(0, 50 + momentum_20d * 2))
                    rsi_score = 100 - abs(rsi_14 - 55) * 2  # Optimal around 55
                    position_score = 100 - abs(position_52w - 70) * 2  # Optimal around 70%

                    entry_score = (momentum_score * 0.4 + rsi_score * 0.3 + position_score * 0.3)

                    candidates.append({
                        'symbol': symbol,
                        'entry_score': entry_score,
                        'close': close,
                        'momentum_20d': momentum_20d,
                        'rsi': rsi_14,
                        'atr_pct': atr_pct,
                        'position_52w': position_52w
                    })

            except Exception as e:
                continue

        print(f"   Tested: {tested}, Passed gates: {len(candidates)}")

        if not candidates:
            continue

        # Sort by entry score and take top N
        candidates.sort(key=lambda x: x['entry_score'], reverse=True)
        selected = candidates[:max_stocks_per_day]

        print(f"   Selected: {[c['symbol'] for c in selected]}")

        # Simulate trades for selected stocks
        for stock in selected:
            df = get_price_data(data_manager, stock['symbol'],
                               (pd.Timestamp(screen_date) - timedelta(days=10)).strftime('%Y-%m-%d'),
                               (pd.Timestamp(screen_date) + timedelta(days=45)).strftime('%Y-%m-%d'))

            if df is None or len(df) < 5:
                continue

            trade = simulate_trade(df, screen_date)
            if trade:
                trade['symbol'] = stock['symbol']
                trade['entry_score'] = stock['entry_score']
                trade['momentum_20d'] = stock['momentum_20d']
                trade['rsi'] = stock['rsi']
                trade['atr_pct'] = stock['atr_pct']
                all_trades.append(trade)

    # Analyze results
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    if not all_trades:
        print("No trades executed!")
        return

    df_trades = pd.DataFrame(all_trades)

    # Basic stats
    total_trades = len(df_trades)
    winners = df_trades[df_trades['return_pct'] > 0]
    losers = df_trades[df_trades['return_pct'] <= 0]

    win_rate = len(winners) / total_trades * 100

    print(f"\n📊 TRADE STATISTICS:")
    print(f"   Total trades: {total_trades}")
    print(f"   Winners: {len(winners)} ({win_rate:.1f}%)")
    print(f"   Losers: {len(losers)} ({100-win_rate:.1f}%)")

    print(f"\n💰 RETURNS:")
    print(f"   Average return: {df_trades['return_pct'].mean():.2f}%")
    print(f"   Average winner: {winners['return_pct'].mean():.2f}%" if len(winners) > 0 else "   No winners")
    print(f"   Average loser: {losers['return_pct'].mean():.2f}%" if len(losers) > 0 else "   No losers")
    print(f"   Best trade: {df_trades['return_pct'].max():.2f}%")
    print(f"   Worst trade: {df_trades['return_pct'].min():.2f}%")

    print(f"\n⏱️ HOLDING PERIOD:")
    print(f"   Average hold: {df_trades['hold_days'].mean():.1f} days")
    print(f"   Min hold: {df_trades['hold_days'].min()} days")
    print(f"   Max hold: {df_trades['hold_days'].max()} days")

    print(f"\n🚪 EXIT REASONS:")
    exit_counts = df_trades['exit_reason'].value_counts()
    for reason, count in exit_counts.items():
        pct = count / total_trades * 100
        print(f"   {reason}: {count} ({pct:.1f}%)")

    # Analyze losers
    print(f"\n❌ LOSER ANALYSIS:")
    if len(losers) > 0:
        big_losers = losers[losers['return_pct'] <= -7]
        medium_losers = losers[(losers['return_pct'] > -7) & (losers['return_pct'] <= -3)]
        small_losers = losers[losers['return_pct'] > -3]

        print(f"   Big losers (≤-7%): {len(big_losers)} trades")
        print(f"   Medium losers (-7% to -3%): {len(medium_losers)} trades")
        print(f"   Small losers (>-3%): {len(small_losers)} trades")

        print(f"\n   Top 10 worst trades:")
        worst = df_trades.nsmallest(10, 'return_pct')
        for _, row in worst.iterrows():
            print(f"   {row['symbol']}: {row['return_pct']:.1f}% ({row['exit_reason']}, {row['hold_days']}d)")

    # Monthly breakdown
    print(f"\n📅 MONTHLY BREAKDOWN:")
    df_trades['month'] = pd.to_datetime(df_trades['entry_date']).dt.to_period('M')
    monthly = df_trades.groupby('month').agg({
        'return_pct': ['count', 'mean', lambda x: (x > 0).sum() / len(x) * 100],
        'hold_days': 'mean'
    }).round(2)
    monthly.columns = ['Trades', 'Avg Return %', 'Win Rate %', 'Avg Hold Days']
    print(monthly.to_string())

    # Total return (if equally weighted)
    total_return = df_trades['return_pct'].sum()
    print(f"\n📈 TOTAL RETURN (sum): {total_return:.2f}%")

    # Profit factor
    gross_profit = winners['return_pct'].sum() if len(winners) > 0 else 0
    gross_loss = abs(losers['return_pct'].sum()) if len(losers) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    print(f"📊 PROFIT FACTOR: {profit_factor:.2f}")

    # Save results
    df_trades.to_csv('backtest_v9_results.csv', index=False)
    print(f"\n💾 Results saved to backtest_v9_results.csv")

    return df_trades


if __name__ == "__main__":
    # Backtest last 2 months
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

    print(f"Running backtest from {start_date} to {end_date}")
    results = run_backtest(start_date, end_date, max_stocks_per_day=5)
