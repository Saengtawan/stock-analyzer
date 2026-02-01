#!/usr/bin/env python3
"""
Backtest v5.4 PEAK AVOIDANCE Strategy

New filters in v5.4:
1. Days from 52w High > 50 (filters COST, HON)
2. Mom 10d > 0% (filters NVO)

Compare v5.3 vs v5.4 to verify losers are filtered out.
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

# Test universe - stocks that appeared in screening during backtest period
TEST_STOCKS = [
    # v5.3 Winners
    'NVDA', 'META', 'AMZN', 'AAPL', 'GOOGL', 'MSFT', 'NFLX', 'CRM', 'NOW', 'AVGO',
    'AMD', 'ADBE', 'ORCL', 'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB',
    'SHOP', 'SQ', 'PYPL', 'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'DG', 'DLTR',
    'CAT', 'DE', 'HON', 'GE', 'MMM', 'RTX', 'LMT', 'NOC', 'BA',
    'DIS', 'CMCSA', 'T', 'VZ', 'TMUS', 'CHTR',
    'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY',
    'NVO', 'NOVO-B', 'ASML', 'TSM', 'BABA', 'PDD', 'JD',
    # Additional momentum stocks
    'TSLA', 'COIN', 'MARA', 'RIOT', 'MSTR', 'HOOD', 'SOFI', 'AFRM', 'UPST',
    'PLTR', 'PATH', 'AI', 'BBAI', 'SOUN', 'IONQ', 'RGTI',
]

def calculate_metrics(df, lookback=252):
    """Calculate all momentum metrics including v5.4 days_from_high"""
    if df is None or len(df) < lookback:
        return None

    close = df['Close'].iloc[-lookback:]
    high = df['High'].iloc[-lookback:]

    current_price = close.iloc[-1]

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

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

    # v5.4: Days from 52-week high
    high_52w_idx = high.idxmax()
    current_idx = high.index[-1]
    days_from_high = len(high.loc[high_52w_idx:current_idx]) - 1

    return {
        'rsi': float(rsi.iloc[-1]),
        'price_above_ma20': float(price_above_ma20),
        'price_above_ma50': float(price_above_ma50),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_30d': float(mom_30d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
    }


def passes_v53_gates(metrics):
    """v5.3 criteria (without days_from_high and mom_10d filters)"""
    if metrics is None:
        return False, "No metrics"

    # 52w position: 55-90%
    pos = metrics['position_52w']
    if pos < 55 or pos > 90:
        return False, f"52w pos {pos:.0f}%"

    # Mom 30d: 6-16%
    mom30 = metrics['momentum_30d']
    if mom30 < 6 or mom30 > 16:
        return False, f"Mom30 {mom30:.1f}%"

    # Mom 5d: 0.5-12%
    mom5 = metrics['momentum_5d']
    if mom5 < 0.5 or mom5 > 12:
        return False, f"Mom5 {mom5:.1f}%"

    # RSI: 45-62
    rsi = metrics['rsi']
    if rsi < 45 or rsi > 62:
        return False, f"RSI {rsi:.0f}"

    # Above MA20
    if metrics['price_above_ma20'] <= 0:
        return False, "Below MA20"

    return True, "PASS"


def passes_v54_gates(metrics):
    """v5.4 criteria (with days_from_high and mom_10d filters)"""
    if metrics is None:
        return False, "No metrics"

    # 52w position: 55-90%
    pos = metrics['position_52w']
    if pos < 55 or pos > 90:
        return False, f"52w pos {pos:.0f}%"

    # v5.4 NEW: Days from 52w high > 50
    days = metrics['days_from_high']
    if days < 50:
        return False, f"Days from high {days} < 50"

    # Mom 30d: 6-16%
    mom30 = metrics['momentum_30d']
    if mom30 < 6 or mom30 > 16:
        return False, f"Mom30 {mom30:.1f}%"

    # v5.4 NEW: Mom 10d > 0%
    mom10 = metrics['momentum_10d']
    if mom10 <= 0:
        return False, f"Mom10 {mom10:.1f}% <= 0"

    # Mom 5d: 0.5-12%
    mom5 = metrics['momentum_5d']
    if mom5 < 0.5 or mom5 > 12:
        return False, f"Mom5 {mom5:.1f}%"

    # RSI: 45-62
    rsi = metrics['rsi']
    if rsi < 45 or rsi > 62:
        return False, f"RSI {rsi:.0f}"

    # Above MA20
    if metrics['price_above_ma20'] <= 0:
        return False, "Below MA20"

    return True, "PASS"


def backtest_strategy(stocks, start_date, end_date, version='v5.4'):
    """Run backtest for specified version"""

    results = []
    check_function = passes_v54_gates if version == 'v5.4' else passes_v53_gates

    print(f"\n{'='*70}")
    print(f"BACKTESTING {version} from {start_date} to {end_date}")
    print(f"{'='*70}")

    for symbol in stocks:
        try:
            # Get historical data
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is None or len(df) < 300:
                continue

            # Find trading days in backtest period
            df.index = pd.to_datetime(df.index)
            mask = (df.index >= start_date) & (df.index <= end_date)
            backtest_dates = df.index[mask]

            for entry_date in backtest_dates:
                # Get data up to entry date
                entry_idx = df.index.get_loc(entry_date)
                if entry_idx < 252:
                    continue

                df_entry = df.iloc[:entry_idx+1]
                metrics = calculate_metrics(df_entry)

                if metrics is None:
                    continue

                passed, reason = check_function(metrics)

                if passed:
                    # Calculate 30-day forward return
                    entry_price = df.iloc[entry_idx]['Close']

                    # Find exit (30 days or stop loss)
                    exit_idx = min(entry_idx + 30, len(df) - 1)

                    # Check for -6% stop loss
                    hit_stop = False
                    for i in range(entry_idx + 1, exit_idx + 1):
                        if i >= len(df):
                            break
                        low_price = df.iloc[i]['Low']
                        if (low_price - entry_price) / entry_price <= -0.06:
                            exit_idx = i
                            hit_stop = True
                            break

                    exit_price = df.iloc[exit_idx]['Close']
                    if hit_stop:
                        exit_price = entry_price * 0.94  # Stop at -6%

                    return_pct = ((exit_price - entry_price) / entry_price) * 100

                    results.append({
                        'symbol': symbol,
                        'entry_date': entry_date.strftime('%Y-%m-%d'),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'return_pct': return_pct,
                        'hit_stop': hit_stop,
                        'position_52w': metrics['position_52w'],
                        'days_from_high': metrics['days_from_high'],
                        'mom_5d': metrics['momentum_5d'],
                        'mom_10d': metrics['momentum_10d'],
                        'mom_30d': metrics['momentum_30d'],
                        'rsi': metrics['rsi'],
                    })

        except Exception as e:
            continue

    return results


def analyze_results(results, version):
    """Analyze backtest results"""
    if not results:
        print(f"\n{version}: No trades found!")
        return

    df = pd.DataFrame(results)

    # Remove duplicates (same stock within 10 days)
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df = df.sort_values(['symbol', 'entry_date'])
    df['days_since_last'] = df.groupby('symbol')['entry_date'].diff().dt.days
    df = df[(df['days_since_last'].isna()) | (df['days_since_last'] > 10)]

    total_trades = len(df)
    winners = df[df['return_pct'] > 0]
    losers = df[df['return_pct'] <= 0]
    stop_losses = df[df['hit_stop'] == True]

    win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0
    avg_return = df['return_pct'].mean()
    avg_winner = winners['return_pct'].mean() if len(winners) > 0 else 0
    avg_loser = losers['return_pct'].mean() if len(losers) > 0 else 0

    print(f"\n{'='*70}")
    print(f"{version} RESULTS")
    print(f"{'='*70}")
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Avg Return:      {avg_return:+.2f}%")
    print(f"Avg Winner:      {avg_winner:+.2f}%")
    print(f"Avg Loser:       {avg_loser:+.2f}%")
    print(f"Stop Losses:     {len(stop_losses)} ({len(stop_losses)/total_trades*100:.1f}%)")

    # Show losers
    if len(losers) > 0:
        print(f"\n--- LOSERS ({version}) ---")
        losers_sorted = losers.sort_values('return_pct')
        for _, row in losers_sorted.iterrows():
            print(f"  {row['symbol']:6} {row['entry_date'].strftime('%Y-%m-%d')} "
                  f"Return: {row['return_pct']:+.1f}%  "
                  f"DaysFromHigh: {row['days_from_high']}  "
                  f"Mom10d: {row['mom_10d']:+.1f}%  "
                  f"Stop: {'YES' if row['hit_stop'] else 'NO'}")

    # Show top 5 winners
    print(f"\n--- TOP 5 WINNERS ({version}) ---")
    top_winners = winners.nlargest(5, 'return_pct')
    for _, row in top_winners.iterrows():
        print(f"  {row['symbol']:6} {row['entry_date'].strftime('%Y-%m-%d')} "
              f"Return: {row['return_pct']:+.1f}%  "
              f"DaysFromHigh: {row['days_from_high']}  "
              f"Mom10d: {row['mom_10d']:+.1f}%")

    return df


# Main backtest
if __name__ == "__main__":
    # Backtest period: 6 months
    end_date = datetime.now() - timedelta(days=30)  # Give 30 days for exit
    start_date = end_date - timedelta(days=180)

    print("\n" + "="*70)
    print("v5.4 PEAK AVOIDANCE BACKTEST")
    print("="*70)
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Universe: {len(TEST_STOCKS)} stocks")
    print("\nv5.4 NEW FILTERS:")
    print("  1. Days from 52w High > 50 (filters stocks near peak)")
    print("  2. Mom 10d > 0% (filters weakening momentum)")

    # Run both versions
    results_v53 = backtest_strategy(TEST_STOCKS, start_date, end_date, version='v5.3')
    results_v54 = backtest_strategy(TEST_STOCKS, start_date, end_date, version='v5.4')

    # Analyze
    df_v53 = analyze_results(results_v53, 'v5.3')
    df_v54 = analyze_results(results_v54, 'v5.4')

    # Compare
    print("\n" + "="*70)
    print("COMPARISON: v5.3 vs v5.4")
    print("="*70)

    if df_v53 is not None and df_v54 is not None:
        v53_trades = len(df_v53)
        v54_trades = len(df_v54)
        v53_win = (df_v53['return_pct'] > 0).sum() / v53_trades * 100 if v53_trades > 0 else 0
        v54_win = (df_v54['return_pct'] > 0).sum() / v54_trades * 100 if v54_trades > 0 else 0
        v53_stops = df_v53['hit_stop'].sum()
        v54_stops = df_v54['hit_stop'].sum()

        print(f"                   v5.3      v5.4      Change")
        print(f"  Trades:          {v53_trades:4}      {v54_trades:4}      {v54_trades - v53_trades:+d}")
        print(f"  Win Rate:        {v53_win:5.1f}%    {v54_win:5.1f}%    {v54_win - v53_win:+.1f}%")
        print(f"  Avg Return:      {df_v53['return_pct'].mean():+5.2f}%    {df_v54['return_pct'].mean():+5.2f}%    {df_v54['return_pct'].mean() - df_v53['return_pct'].mean():+.2f}%")
        print(f"  Stop Losses:     {v53_stops:4}      {v54_stops:4}      {v54_stops - v53_stops:+d}")

        # Check if specific losers were filtered
        print("\n--- LOSER FILTER CHECK ---")
        v53_losers = set(df_v53[df_v53['return_pct'] < 0]['symbol'].unique())
        v54_losers = set(df_v54[df_v54['return_pct'] < 0]['symbol'].unique())
        filtered_losers = v53_losers - v54_losers

        if filtered_losers:
            print(f"  v5.4 filtered out these losers: {filtered_losers}")
        else:
            print(f"  v5.4 losers: {v54_losers}")
            print(f"  v5.3 losers: {v53_losers}")

    print("\n" + "="*70)
    print("BACKTEST COMPLETE")
    print("="*70)
