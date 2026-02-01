#!/usr/bin/env python3
"""
Detailed Analysis of v5.4 Backtest Results
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from api.data_manager import DataManager

dm = DataManager()

TEST_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AVGO', 'AMD', 'ORCL',
    'CRM', 'ADBE', 'NOW', 'NFLX', 'INTC', 'QCOM', 'TXN', 'MU', 'AMAT', 'LRCX',
    'PANW', 'CRWD', 'SNOW', 'DDOG', 'ZS', 'NET', 'MDB', 'SHOP', 'PYPL', 'PLTR',
    'V', 'MA', 'AXP', 'JPM', 'GS', 'MS', 'BLK', 'C', 'BAC', 'WFC',
    'UNH', 'LLY', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO', 'DHR', 'ABT', 'ISRG',
    'HD', 'LOW', 'TJX', 'ROST', 'TGT', 'WMT', 'COST', 'NKE', 'SBUX', 'MCD',
    'CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'NOC', 'BA', 'UPS', 'FDX',
    'NVO', 'ASML', 'TSM', 'BABA', 'PDD', 'JD', 'TCEHY', 'SAP', 'TM', 'UL',
]


def calculate_metrics(df, idx):
    if df is None or idx < 252:
        return None

    df_slice = df.iloc[:idx+1]
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

    # MA
    ma20 = close.rolling(20).mean().iloc[-1]
    price_above_ma20 = ((current_price - ma20) / ma20) * 100

    # Momentum
    mom_5d = ((current_price / close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
    mom_10d = ((current_price / close.iloc[-11]) - 1) * 100 if len(close) >= 11 else 0
    mom_30d = ((current_price / close.iloc[-31]) - 1) * 100 if len(close) >= 31 else 0

    # 52w
    high_52w = high.max()
    low_52w = close.min()
    position_52w = ((current_price - low_52w) / (high_52w - low_52w)) * 100 if high_52w != low_52w else 50

    high_idx = high.idxmax()
    days_from_high = close.index[-1] - high_idx

    return {
        'rsi': float(rsi),
        'price_above_ma20': float(price_above_ma20),
        'momentum_5d': float(mom_5d),
        'momentum_10d': float(mom_10d),
        'momentum_30d': float(mom_30d),
        'position_52w': float(position_52w),
        'days_from_high': int(days_from_high),
    }


def passes_v54(m):
    if m is None:
        return False
    if m['position_52w'] < 55 or m['position_52w'] > 90:
        return False
    if m['days_from_high'] < 50:
        return False
    if m['momentum_30d'] < 6 or m['momentum_30d'] > 16:
        return False
    if m['momentum_10d'] <= 0:
        return False
    if m['momentum_5d'] < 0.5 or m['momentum_5d'] > 12:
        return False
    if m['rsi'] < 45 or m['rsi'] > 62:
        return False
    if m['price_above_ma20'] <= 0:
        return False
    return True


def run_detailed_backtest():
    results = []

    for symbol in TEST_STOCKS:
        try:
            df = dm.get_price_data(symbol, period="2y", interval="1d")
            if df is None or len(df) < 280:
                continue

            for days_back in range(30, 180):
                test_idx = len(df) - 1 - days_back
                if test_idx < 252:
                    continue

                metrics = calculate_metrics(df, test_idx)
                if not passes_v54(metrics):
                    continue

                entry_price = df.iloc[test_idx]['close']
                entry_date = pd.to_datetime(df.iloc[test_idx]['date'])

                # Find exit
                exit_idx = test_idx + 30
                hit_stop = False
                days_held = 30

                for i in range(test_idx + 1, min(exit_idx + 1, len(df))):
                    pnl = (df.iloc[i]['low'] - entry_price) / entry_price
                    if pnl <= -0.06:
                        hit_stop = True
                        exit_idx = i
                        days_held = i - test_idx
                        break

                exit_date = pd.to_datetime(df.iloc[min(exit_idx, len(df)-1)]['date'])
                exit_price = entry_price * 0.94 if hit_stop else df.iloc[min(exit_idx, len(df)-1)]['close']
                return_pct = ((exit_price - entry_price) / entry_price) * 100

                results.append({
                    'symbol': symbol,
                    'entry_date': entry_date,
                    'exit_date': exit_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'return_pct': return_pct,
                    'days_held': days_held,
                    'hit_stop': hit_stop,
                    'exit_reason': 'STOP_LOSS -6%' if hit_stop else 'TIME_EXIT 30d',
                })

        except Exception as e:
            continue

    return pd.DataFrame(results)


# Main
if __name__ == "__main__":
    print("Loading data and running backtest...")
    df = run_detailed_backtest()

    if df.empty:
        print("No trades found!")
        exit()

    # Deduplicate
    df = df.sort_values(['symbol', 'entry_date'])
    df['days_diff'] = df.groupby('symbol')['entry_date'].diff().dt.days
    df = df[(df['days_diff'].isna()) | (df['days_diff'] > 10)]
    df = df.drop('days_diff', axis=1)

    # Sort by date
    df = df.sort_values('entry_date')

    print("\n" + "="*80)
    print("v5.4 DETAILED TRADE ANALYSIS")
    print("="*80)

    # 1. Trades per month
    df['month'] = df['entry_date'].dt.to_period('M')
    monthly = df.groupby('month').agg({
        'symbol': 'count',
        'return_pct': ['mean', 'sum']
    })
    monthly.columns = ['trades', 'avg_return', 'total_return']

    print("\n📅 TRADES PER MONTH:")
    print("-"*50)
    for month, row in monthly.iterrows():
        print(f"  {month}: {row['trades']:2} trades  |  Avg: {row['avg_return']:+.1f}%  |  Total: {row['total_return']:+.1f}%")

    avg_per_month = len(df) / len(monthly)
    print(f"\n  Average: {avg_per_month:.1f} trades/month")

    # 2. Holding period
    print("\n⏱️  HOLDING PERIOD:")
    print("-"*50)
    print(f"  Average:  {df['days_held'].mean():.1f} days")
    print(f"  Min:      {df['days_held'].min()} days")
    print(f"  Max:      {df['days_held'].max()} days")

    stop_loss_trades = df[df['hit_stop'] == True]
    time_exit_trades = df[df['hit_stop'] == False]

    print(f"\n  Stop Loss exits: {len(stop_loss_trades)} trades (avg {stop_loss_trades['days_held'].mean():.1f} days)")
    print(f"  Time exits:      {len(time_exit_trades)} trades (held full 30 days)")

    # 3. All trades detail
    print("\n📊 ALL TRADES (sorted by date):")
    print("-"*100)
    print(f"{'Symbol':<8} {'Entry Date':<12} {'Exit Date':<12} {'Entry $':<10} {'Exit $':<10} {'Return':<10} {'Days':<6} {'Reason'}")
    print("-"*100)

    for _, row in df.iterrows():
        status = "🔴" if row['return_pct'] < 0 else "🟢"
        print(f"{status} {row['symbol']:<6} {row['entry_date'].strftime('%Y-%m-%d'):<12} "
              f"{row['exit_date'].strftime('%Y-%m-%d'):<12} "
              f"${row['entry_price']:>7.2f}   ${row['exit_price']:>7.2f}   "
              f"{row['return_pct']:>+6.1f}%    {row['days_held']:<6} {row['exit_reason']}")

    # 4. Winners vs Losers
    winners = df[df['return_pct'] > 0]
    losers = df[df['return_pct'] <= 0]

    print("\n" + "="*80)
    print("💰 WINNERS vs LOSERS")
    print("="*80)

    print(f"\n🟢 WINNERS: {len(winners)} trades ({len(winners)/len(df)*100:.1f}%)")
    print("-"*60)
    for _, row in winners.sort_values('return_pct', ascending=False).iterrows():
        print(f"  {row['symbol']:<6} {row['entry_date'].strftime('%Y-%m-%d')}  Return: {row['return_pct']:+6.1f}%  Held: {row['days_held']} days")

    print(f"\n🔴 LOSERS: {len(losers)} trades ({len(losers)/len(df)*100:.1f}%)")
    print("-"*60)
    for _, row in losers.sort_values('return_pct').iterrows():
        print(f"  {row['symbol']:<6} {row['entry_date'].strftime('%Y-%m-%d')}  Return: {row['return_pct']:+6.1f}%  Held: {row['days_held']} days  {row['exit_reason']}")

    # 5. Capital stuck analysis
    print("\n" + "="*80)
    print("💸 CAPITAL STUCK ANALYSIS (ทุนชงัก)")
    print("="*80)

    # Simulate with $10,000 starting capital, $1,000 per trade
    capital = 10000
    position_size = 1000
    max_positions = 5

    timeline = []
    active_positions = []

    # Sort all events by date
    events = []
    for _, row in df.iterrows():
        events.append(('entry', row['entry_date'], row))
        events.append(('exit', row['exit_date'], row))

    events.sort(key=lambda x: x[1])

    for event_type, event_date, trade in events:
        if event_type == 'entry':
            active_positions.append(trade)
        else:
            # Remove from active
            active_positions = [p for p in active_positions if not (
                p['symbol'] == trade['symbol'] and
                p['entry_date'] == trade['entry_date']
            )]

        timeline.append({
            'date': event_date,
            'active_count': len(active_positions),
            'symbols': [p['symbol'] for p in active_positions],
        })

    max_concurrent = max(t['active_count'] for t in timeline)

    print(f"\n  Max concurrent positions: {max_concurrent}")
    print(f"  Position size: ${position_size:,}")
    print(f"  Max capital deployed: ${max_concurrent * position_size:,}")

    # Find dates with max positions
    stuck_dates = [t for t in timeline if t['active_count'] >= 4]
    if stuck_dates:
        print(f"\n  ⚠️  Dates with 4+ positions (capital might be tight):")
        seen_dates = set()
        for t in stuck_dates:
            date_str = t['date'].strftime('%Y-%m-%d')
            if date_str not in seen_dates:
                seen_dates.add(date_str)
                print(f"     {date_str}: {t['active_count']} positions ({', '.join(t['symbols'])})")
    else:
        print(f"\n  ✅ No capital stuck issues - max {max_concurrent} concurrent positions")

    # 6. Final Summary
    print("\n" + "="*80)
    print("📈 FINAL SUMMARY")
    print("="*80)

    total_trades = len(df)
    total_return = df['return_pct'].sum()
    avg_return = df['return_pct'].mean()
    win_rate = len(winners) / total_trades * 100

    # If investing $1000 per trade
    profit_per_trade = df['return_pct'] * 10  # $1000 * return% / 100
    total_profit_usd = profit_per_trade.sum()

    print(f"""
  Total Trades:     {total_trades}
  Win Rate:         {win_rate:.1f}%

  Avg Return/Trade: {avg_return:+.2f}%
  Total Return:     {total_return:+.2f}%

  If $1,000 per trade:
  -------------------
  Total Invested:   ${total_trades * 1000:,}
  Total Profit:     ${total_profit_usd:+,.2f}
  ROI:              {total_profit_usd / (total_trades * 1000) * 100:+.2f}%

  Period:           {df['entry_date'].min().strftime('%Y-%m-%d')} to {df['entry_date'].max().strftime('%Y-%m-%d')}
  Duration:         {(df['entry_date'].max() - df['entry_date'].min()).days} days ({(df['entry_date'].max() - df['entry_date'].min()).days / 30:.1f} months)
""")

    # Losers impact
    loser_loss = losers['return_pct'].sum() * 10
    winner_gain = winners['return_pct'].sum() * 10

    print(f"  Winners total:  ${winner_gain:+,.2f}")
    print(f"  Losers total:   ${loser_loss:+,.2f}")
    print(f"  Net:            ${total_profit_usd:+,.2f}")
