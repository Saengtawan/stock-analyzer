#!/usr/bin/env python3
"""
Comprehensive Backtest for v5.4 PEAK AVOIDANCE Strategy

Using actual screener's momentum gates to validate performance.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

# Initialize
dm = DataManager()

# Larger universe for comprehensive test
TEST_STOCKS = [
    # Mega Tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    # Cloud & Software
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    # Financials
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    # Healthcare
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    # Consumer
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    # Industrial
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    # International
    'NVO', 'ASML', 'TSM', 'BABA', 'PDD', 'JD', 'TCEHY', 'SAP', 'TM', 'UL',
]


def calculate_momentum_metrics(df, as_of_idx):
    """Calculate metrics matching screener's logic"""
    if df is None or as_of_idx < 252:
        return None

    df_slice = df.iloc[:as_of_idx+1]
    lookback = min(252, len(df_slice))

    close = df_slice['close'].iloc[-lookback:]
    high = df_slice['high'].iloc[-lookback:]

    current_price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs.iloc[-1]))

    # Moving averages
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    price_above_ma20 = ((current_price - ma20) / ma20) * 100
    price_above_ma50 = ((current_price - ma50) / ma50) * 100

    # Momentum
    mom_5d = ((current_price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((current_price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

    # 52-week position
    high_52w = high.max()
    low_52w = close.min()
    position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

    # Days from 52-week high
    high_idx = high.idxmax()
    current_idx = close.index[-1]
    days_from_high = current_idx - high_idx

    return {
        'rsi': float(rsi),
        'price_above_ma20': float(price_above_ma20),
        'price_above_ma50': float(price_above_ma50),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_30d': float(mom_30d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
    }


def passes_v53_gates(m):
    """v5.3 momentum gates"""
    if m is None:
        return False

    if m['position_52w'] < 55 or m['position_52w'] > 90:
        return False
    if m['momentum_30d'] < 6 or m['momentum_30d'] > 16:
        return False
    if m['momentum_5d'] < 0.5 or m['momentum_5d'] > 12:
        return False
    if m['rsi'] < 45 or m['rsi'] > 62:
        return False
    if m['price_above_ma20'] <= 0:
        return False

    return True


def passes_v54_gates(m):
    """v5.4 momentum gates (with new filters)"""
    if m is None:
        return False

    if m['position_52w'] < 55 or m['position_52w'] > 90:
        return False
    if m['days_from_high'] < 50:  # NEW!
        return False
    if m['momentum_30d'] < 6 or m['momentum_30d'] > 16:
        return False
    if m['momentum_10d'] <= 0:  # NEW!
        return False
    if m['momentum_5d'] < 0.5 or m['momentum_5d'] > 12:
        return False
    if m['rsi'] < 45 or m['rsi'] > 62:
        return False
    if m['price_above_ma20'] <= 0:
        return False

    return True


def backtest_stock(symbol, df, version='v5.4'):
    """Backtest a single stock over 6 months"""
    results = []
    check_func = passes_v54_gates if version == 'v5.4' else passes_v53_gates

    # Scan through last 6 months (excluding last 30 days for exit)
    for days_back in range(30, 180):
        test_idx = len(df) - 1 - days_back
        if test_idx < 252:
            continue

        metrics = calculate_momentum_metrics(df, test_idx)
        if not check_func(metrics):
            continue

        # Entry
        entry_price = df.iloc[test_idx]['close']
        entry_date = pd.to_datetime(df.iloc[test_idx]['date']).strftime('%Y-%m-%d')

        # Exit (30 days or stop loss)
        exit_idx = test_idx + 30
        hit_stop = False

        for i in range(test_idx + 1, min(exit_idx + 1, len(df))):
            if (df.iloc[i]['low'] - entry_price) / entry_price <= -0.06:
                hit_stop = True
                exit_idx = i
                break

        exit_price = entry_price * 0.94 if hit_stop else df.iloc[min(exit_idx, len(df)-1)]['close']
        return_pct = ((exit_price - entry_price) / entry_price) * 100

        results.append({
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return_pct': return_pct,
            'hit_stop': hit_stop,
            'days_from_high': metrics['days_from_high'],
            'mom_10d': metrics['momentum_10d'],
        })

    return results


def run_backtest(version):
    """Run complete backtest"""
    print(f"\n{'='*60}")
    print(f"Running {version} Backtest...")
    print(f"{'='*60}")

    all_results = []

    for i, symbol in enumerate(TEST_STOCKS):
        try:
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is None or len(df) < 280:
                continue

            results = backtest_stock(symbol, df, version)
            all_results.extend(results)

            if (i + 1) % 20 == 0:
                print(f"  Processed {i+1}/{len(TEST_STOCKS)} stocks...")

        except Exception as e:
            continue

    # Deduplicate (remove entries within 10 days of same stock)
    if all_results:
        df_results = pd.DataFrame(all_results)
        df_results['entry_date'] = pd.to_datetime(df_results['entry_date'])
        df_results = df_results.sort_values(['symbol', 'entry_date'])
        df_results['days_diff'] = df_results.groupby('symbol')['entry_date'].diff().dt.days
        df_results = df_results[(df_results['days_diff'].isna()) | (df_results['days_diff'] > 10)]

        return df_results

    return pd.DataFrame()


def analyze_results(df, version):
    """Analyze backtest results"""
    if df.empty:
        print(f"\n{version}: No trades!")
        return None

    total = len(df)
    winners = df[df['return_pct'] > 0]
    losers = df[df['return_pct'] <= 0]
    stops = df[df['hit_stop'] == True]

    win_rate = len(winners) / total * 100
    avg_return = df['return_pct'].mean()
    avg_win = winners['return_pct'].mean() if len(winners) > 0 else 0
    avg_loss = losers['return_pct'].mean() if len(losers) > 0 else 0
    total_return = df['return_pct'].sum()

    print(f"\n{'='*60}")
    print(f"{version} RESULTS")
    print(f"{'='*60}")
    print(f"Total Trades:    {total}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Avg Return:      {avg_return:+.2f}%")
    print(f"Avg Winner:      {avg_win:+.2f}%")
    print(f"Avg Loser:       {avg_loss:+.2f}%")
    print(f"Total Return:    {total_return:+.2f}%")
    print(f"Stop Losses:     {len(stops)} ({len(stops)/total*100:.1f}%)")

    if len(losers) > 0:
        print(f"\n--- LOSERS ---")
        for _, row in losers.sort_values('return_pct').head(5).iterrows():
            print(f"  {row['symbol']:6} {row['entry_date'].strftime('%Y-%m-%d')} "
                  f"Return: {row['return_pct']:+.1f}%  "
                  f"DaysFromHigh: {row['days_from_high']}  "
                  f"Mom10d: {row['mom_10d']:+.1f}%")

    return {
        'total': total,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'stops': len(stops),
    }


# Main
if __name__ == "__main__":
    print("\n" + "="*70)
    print("v5.4 PEAK AVOIDANCE - COMPREHENSIVE BACKTEST")
    print("="*70)
    print(f"\nUniverse: {len(TEST_STOCKS)} stocks")
    print("Period: Last 6 months")
    print("\nv5.4 NEW FILTERS:")
    print("  1. Days from 52w High > 50 (avoid peak buying)")
    print("  2. Mom 10d > 0% (confirm trend not weakening)")

    # Run both versions
    df_v53 = run_backtest('v5.3')
    df_v54 = run_backtest('v5.4')

    # Analyze
    stats_v53 = analyze_results(df_v53, 'v5.3')
    stats_v54 = analyze_results(df_v54, 'v5.4')

    # Comparison
    print("\n" + "="*70)
    print("COMPARISON: v5.3 vs v5.4")
    print("="*70)

    if stats_v53 and stats_v54:
        print(f"                   v5.3      v5.4      Change")
        print(f"  Trades:          {stats_v53['total']:4}      {stats_v54['total']:4}      {stats_v54['total'] - stats_v53['total']:+d}")
        print(f"  Win Rate:        {stats_v53['win_rate']:5.1f}%    {stats_v54['win_rate']:5.1f}%    {stats_v54['win_rate'] - stats_v53['win_rate']:+.1f}%")
        print(f"  Avg Return:      {stats_v53['avg_return']:+5.2f}%    {stats_v54['avg_return']:+5.2f}%    {stats_v54['avg_return'] - stats_v53['avg_return']:+.2f}%")
        print(f"  Stop Losses:     {stats_v53['stops']:4}      {stats_v54['stops']:4}      {stats_v54['stops'] - stats_v53['stops']:+d}")

    # Check filtered losers
    if not df_v53.empty and not df_v54.empty:
        v53_losers = set(df_v53[df_v53['return_pct'] < 0]['symbol'].unique())
        v54_losers = set(df_v54[df_v54['return_pct'] < 0]['symbol'].unique())
        filtered = v53_losers - v54_losers

        print(f"\n--- FILTERED LOSERS ---")
        if filtered:
            print(f"  v5.4 eliminated these losing stocks: {filtered}")
        else:
            print(f"  No losers filtered (v5.4 losers: {v54_losers})")

    print("\n" + "="*70)
    print("BACKTEST COMPLETE")
    print("="*70)
