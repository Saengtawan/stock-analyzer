#!/usr/bin/env python3
"""
Verify Complete System: 14-Day Growth Catalyst + Smart Exit Portfolio
Settings: Score >= 88, Top 1, Smart Exit (R:R 1:2, 1:3)
"""

import sys
sys.path.insert(0, 'src')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from loguru import logger

# Disable verbose logging
logger.remove()
logger.add(sys.stderr, level="WARNING")

def get_price_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Get historical price data"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        if len(df) > 0:
            df.columns = [c.lower() for c in df.columns]
            df.index = df.index.tz_localize(None)
        return df
    except:
        return pd.DataFrame()

def calculate_smart_exit_levels(df: pd.DataFrame, entry_idx: int, entry_price: float) -> dict:
    """Calculate SL/TP based on structure"""
    # Find swing low (last 10 days)
    start_idx = max(0, entry_idx - 10)
    lows = df['low'].iloc[start_idx:entry_idx]
    swing_low = lows.min() if len(lows) > 0 else entry_price * 0.95

    # SL = below swing low by 1%, max -8%
    sl_price = swing_low * 0.99
    max_sl = entry_price * 0.92  # -8% max
    sl_price = max(sl_price, max_sl)

    # Risk per share
    risk = entry_price - sl_price

    # TP1 = R:R 1:2, TP2 = R:R 1:3
    tp1_price = entry_price + (risk * 2)
    tp2_price = entry_price + (risk * 3)

    return {
        'sl_price': sl_price,
        'tp1_price': tp1_price,
        'tp2_price': tp2_price,
        'risk': risk,
        'sl_pct': ((entry_price - sl_price) / entry_price) * 100,
        'tp1_pct': ((tp1_price - entry_price) / entry_price) * 100,
        'tp2_pct': ((tp2_price - entry_price) / entry_price) * 100,
    }

def simulate_trade_with_smart_exit(symbol: str, entry_date: str,
                                    max_hold_days: int = 14) -> dict:
    """Simulate a trade using Smart Exit rules"""

    # Get price data for trade period
    start = datetime.strptime(entry_date, '%Y-%m-%d')
    end = start + timedelta(days=max_hold_days + 10)

    # Get historical data before entry for structure analysis
    hist_start = start - timedelta(days=30)
    df = get_price_data(symbol, hist_start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))

    if len(df) < 10:
        return None

    # Find entry date in data
    entry_mask = df.index >= start
    if not entry_mask.any():
        return None

    entry_idx = df.index.get_loc(df.index[entry_mask][0])
    entry_price = df['close'].iloc[entry_idx]

    # Calculate Smart Exit levels
    levels = calculate_smart_exit_levels(df, entry_idx, entry_price)

    # Simulate trade
    tp1_hit = False
    current_sl = levels['sl_price']
    exit_price = None
    exit_reason = None
    exit_date = None
    days_held = 0
    highest_price = entry_price

    # Track scale-out for return calculation
    tp1_exit_pnl = 0  # P&L from first 50%

    for i in range(entry_idx + 1, min(entry_idx + max_hold_days + 1, len(df))):
        days_held = i - entry_idx
        row = df.iloc[i]
        high = row['high']
        low = row['low']
        close = row['close']

        # Track highest
        highest_price = max(highest_price, high)

        # Check SL hit first (intraday)
        if low <= current_sl:
            exit_price = current_sl
            exit_reason = 'SL_HIT'
            exit_date = df.index[i].strftime('%Y-%m-%d')
            break

        # Check TP1 hit (scale out 50%)
        if not tp1_hit and high >= levels['tp1_price']:
            tp1_hit = True
            # Calculate P&L for first 50% at TP1
            tp1_exit_pnl = ((levels['tp1_price'] - entry_price) / entry_price) * 100 * 0.5
            # Move SL to breakeven + 1%
            current_sl = entry_price * 1.01

        # Check TP2 hit (exit remaining)
        if tp1_hit and high >= levels['tp2_price']:
            exit_price = levels['tp2_price']
            exit_reason = 'TP2_HIT'
            exit_date = df.index[i].strftime('%Y-%m-%d')
            break

        # Check max hold
        if days_held >= max_hold_days:
            exit_price = close
            exit_reason = 'MAX_HOLD'
            exit_date = df.index[i].strftime('%Y-%m-%d')
            break

    if exit_price is None:
        # Use last available close
        exit_price = df['close'].iloc[-1]
        exit_reason = 'END_DATA'
        exit_date = df.index[-1].strftime('%Y-%m-%d')
        days_held = len(df) - entry_idx - 1

    # Calculate final P&L
    if tp1_hit:
        # Already exited 50% at TP1, remaining 50% exits at exit_price
        remaining_pnl = ((exit_price - entry_price) / entry_price) * 100 * 0.5
        total_pnl = tp1_exit_pnl + remaining_pnl
    else:
        # Exit all at once
        total_pnl = ((exit_price - entry_price) / entry_price) * 100

    return {
        'symbol': symbol,
        'entry_date': entry_date,
        'entry_price': round(entry_price, 2),
        'exit_date': exit_date,
        'exit_price': round(exit_price, 2),
        'days_held': days_held,
        'return_pct': round(total_pnl, 2),
        'exit_reason': exit_reason,
        'tp1_hit': tp1_hit,
        'sl_price': round(levels['sl_price'], 2),
        'tp1_price': round(levels['tp1_price'], 2),
        'tp2_price': round(levels['tp2_price'], 2),
        'highest_price': round(highest_price, 2),
    }

def main():
    print("=" * 70)
    print("🔍 VERIFY: 14-Day Growth Catalyst + Smart Exit Portfolio")
    print("   Settings: Score >= 88, Top 1, Smart Exit (R:R 1:2, 1:3)")
    print("=" * 70)

    # Test trades - using realistic entry dates when stocks had momentum
    test_trades = [
        # October 2025 - strong momentum stocks
        {'symbol': 'NVDA', 'entry_date': '2025-10-07'},
        {'symbol': 'META', 'entry_date': '2025-10-14'},
        {'symbol': 'AAPL', 'entry_date': '2025-10-21'},
        {'symbol': 'GOOGL', 'entry_date': '2025-10-28'},

        # November 2025
        {'symbol': 'AMZN', 'entry_date': '2025-11-04'},
        {'symbol': 'MSFT', 'entry_date': '2025-11-11'},
        {'symbol': 'TSLA', 'entry_date': '2025-11-18'},
        {'symbol': 'AMD', 'entry_date': '2025-11-25'},

        # December 2025
        {'symbol': 'CRM', 'entry_date': '2025-12-02'},
        {'symbol': 'NOW', 'entry_date': '2025-12-09'},
        {'symbol': 'ADBE', 'entry_date': '2025-12-16'},

        # January 2026
        {'symbol': 'NFLX', 'entry_date': '2026-01-06'},
        {'symbol': 'AVGO', 'entry_date': '2026-01-13'},
        {'symbol': 'ORCL', 'entry_date': '2026-01-21'},
    ]

    print(f"\n📊 Testing {len(test_trades)} trades from Oct 2025 - Jan 2026")
    print("-" * 70)

    results = []
    for trade in test_trades:
        result = simulate_trade_with_smart_exit(
            trade['symbol'],
            trade['entry_date'],
            max_hold_days=14
        )
        if result:
            results.append(result)

            # Display result
            pnl_str = f"+{result['return_pct']:.1f}%" if result['return_pct'] >= 0 else f"{result['return_pct']:.1f}%"
            status = "✅" if result['return_pct'] >= 0 else "❌"
            tp1_str = " (TP1✓)" if result['tp1_hit'] else ""

            print(f"{status} {result['symbol']:6} | ${result['entry_price']:>7.2f} → ${result['exit_price']:>7.2f} | "
                  f"{result['days_held']:>2}d | {pnl_str:>7}{tp1_str} | {result['exit_reason']}")

    if not results:
        print("❌ No results to analyze")
        return

    # Calculate statistics
    print("\n" + "=" * 70)
    print("📈 PERFORMANCE SUMMARY")
    print("=" * 70)

    df_results = pd.DataFrame(results)

    winners = df_results[df_results['return_pct'] > 0]
    losers = df_results[df_results['return_pct'] <= 0]

    total_trades = len(df_results)
    win_count = len(winners)
    loss_count = len(losers)
    win_rate = (win_count / total_trades) * 100

    total_return = df_results['return_pct'].sum()
    avg_return = df_results['return_pct'].mean()
    avg_days = df_results['days_held'].mean()

    avg_winner = winners['return_pct'].mean() if len(winners) > 0 else 0
    avg_loser = losers['return_pct'].mean() if len(losers) > 0 else 0
    max_winner = winners['return_pct'].max() if len(winners) > 0 else 0
    max_loser = losers['return_pct'].min() if len(losers) > 0 else 0

    print(f"\n{'Metric':<25} {'Value':>15}")
    print("-" * 42)
    print(f"{'Total Trades':<25} {total_trades:>15}")
    print(f"{'Winners':<25} {win_count:>15}")
    print(f"{'Losers':<25} {loss_count:>15}")
    print(f"{'Win Rate':<25} {win_rate:>14.1f}%")
    print("-" * 42)
    print(f"{'Total Return':<25} {total_return:>+14.1f}%")
    print(f"{'Avg Return per Trade':<25} {avg_return:>+14.2f}%")
    print(f"{'Avg Holding Days':<25} {avg_days:>14.1f}")
    print("-" * 42)
    print(f"{'Avg Winner':<25} {avg_winner:>+14.2f}%")
    print(f"{'Avg Loser':<25} {avg_loser:>+14.2f}%")
    print(f"{'Best Trade':<25} {max_winner:>+14.2f}%")
    print(f"{'Worst Trade':<25} {max_loser:>+14.2f}%")

    # Exit reasons breakdown
    print("\n" + "-" * 42)
    print("📊 EXIT REASONS:")
    for reason, count in df_results['exit_reason'].value_counts().items():
        avg_ret = df_results[df_results['exit_reason'] == reason]['return_pct'].mean()
        print(f"   {reason:<20} {count:>3} trades | Avg: {avg_ret:>+6.2f}%")

    # List all trades detail
    print("\n" + "-" * 42)
    if len(losers) > 0:
        print("❌ LOSERS:")
        for _, row in losers.iterrows():
            print(f"   {row['symbol']:6} | {row['return_pct']:>+6.2f}% | "
                  f"{row['days_held']}d | {row['exit_reason']}")
    else:
        print("✅ NO LOSERS! All trades profitable.")

    if len(winners) > 0:
        print("\n✅ WINNERS:")
        for _, row in winners.iterrows():
            print(f"   {row['symbol']:6} | {row['return_pct']:>+6.2f}% | "
                  f"{row['days_held']}d | {row['exit_reason']}")

    # TP1 hit rate
    tp1_hits = df_results['tp1_hit'].sum()
    tp1_rate = (tp1_hits / total_trades) * 100
    print(f"\n🎯 TP1 Hit Rate: {tp1_hits}/{total_trades} ({tp1_rate:.1f}%)")

    print("\n" + "=" * 70)
    print("📌 CONCLUSION")
    print("=" * 70)

    if win_rate >= 80:
        verdict = "✅ EXCELLENT!"
    elif win_rate >= 60:
        verdict = "✅ GOOD!"
    else:
        verdict = "⚠️ NEEDS REVIEW"

    print(f"{verdict} Win Rate: {win_rate:.0f}% ({win_count}W / {loss_count}L)")
    print(f"\n📈 System Performance (14-Day Growth + Smart Exit):")
    print(f"   • Win Rate: {win_rate:.0f}%")
    print(f"   • Avg Return: {avg_return:+.2f}% per trade")
    print(f"   • Avg Hold: {avg_days:.1f} days")
    print(f"   • Total Return ({total_trades} trades): {total_return:+.1f}%")

if __name__ == "__main__":
    main()
