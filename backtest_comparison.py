#!/usr/bin/env python3
"""
Comprehensive Backtest Comparison:
- Scenario A: Fixed TP/SL (5%, -8%)
- Scenario B: Dynamic Filter-based Exit

2-Month backtest (Nov-Dec 2025)
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from exit_rules import ExitRulesEngine, FixedTPSLRules

STOCK_UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'TEAM', 'DASH', 'SHOP',
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC', 'LRCX', 'TSM',
    'UBER', 'ABNB', 'COIN', 'ROKU',
]

FILTERS = {
    'rsi_min': 49.0,
    'momentum_7d_min': 3.5,
    'rs_14d_min': 1.9,
    'dist_ma20_min': -2.8,
}


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def apply_entry_filters(symbol, entry_date, hist_data, spy_data):
    """Check if stock passes entry filters"""
    try:
        data = hist_data[hist_data.index <= entry_date].copy()
        if len(data) < 50:
            return False

        close = data['Close']
        entry_price = close.iloc[-1]

        # RSI
        rsi = calculate_rsi(close)
        if rsi.iloc[-1] < FILTERS['rsi_min']:
            return False

        # Momentum 7d
        if len(close) >= 7:
            momentum = ((entry_price - close.iloc[-7]) / close.iloc[-7]) * 100
            if momentum < FILTERS['momentum_7d_min']:
                return False
        else:
            return False

        # RS 14d
        if len(close) >= 14:
            stock_ret = ((entry_price / close.iloc[-14]) - 1) * 100
            spy_at = spy_data[spy_data.index <= entry_date]
            if len(spy_at) >= 14:
                spy_ret = ((spy_at['Close'].iloc[-1] / spy_at['Close'].iloc[-14]) - 1) * 100
                if (stock_ret - spy_ret) < FILTERS['rs_14d_min']:
                    return False
            else:
                return False
        else:
            return False

        # MA20
        if len(close) >= 20:
            ma20 = close.rolling(20).mean().iloc[-1]
            if ((entry_price - ma20) / ma20) * 100 < FILTERS['dist_ma20_min']:
                return False

        return True

    except:
        return False


def run_scenario_a_fixed_tpsl(stock_data, spy_data, entry_dates):
    """Scenario A: Fixed TP 5%, SL -8%, Max Hold 14d"""

    print("\n" + "=" * 100)
    print("📊 SCENARIO A: FIXED TP/SL (5%, -8%)")
    print("=" * 100)

    rules = FixedTPSLRules(take_profit=5.0, stop_loss=-8.0, max_hold=14)
    all_trades = []

    for entry_date in entry_dates:
        # Find stocks that pass filters
        passed_stocks = []
        for symbol, hist in stock_data.items():
            if apply_entry_filters(symbol, entry_date, hist, spy_data):
                passed_stocks.append(symbol)

        if not passed_stocks:
            continue

        print(f"\n📅 {entry_date.strftime('%Y-%m-%d')}: {len(passed_stocks)} stocks")

        # Simulate trades
        for symbol in passed_stocks:
            hist = stock_data[symbol]

            # Get entry price
            entry_idx = None
            for i, date in enumerate(hist.index):
                if date >= entry_date:
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx + 14 >= len(hist):
                continue

            entry_price = hist['Close'].iloc[entry_idx]
            entry_actual_date = hist.index[entry_idx]

            # Simulate daily checks
            exit_idx = None
            exit_reason = None

            for day in range(1, 15):  # Check each day up to 14
                check_idx = entry_idx + day
                if check_idx >= len(hist):
                    break

                position = {
                    'symbol': symbol,
                    'entry_date': entry_actual_date.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'days_held': day,
                }

                check_date = hist.index[check_idx]
                should_exit, reason, details = rules.check_exit(
                    position, check_date.strftime('%Y-%m-%d'), hist
                )

                if should_exit:
                    exit_idx = check_idx
                    exit_reason = reason
                    break

            # If no exit signal, hold to day 14
            if exit_idx is None:
                exit_idx = min(entry_idx + 14, len(hist) - 1)
                exit_reason = 'MAX_HOLD'

            exit_price = hist['Close'].iloc[exit_idx]
            exit_date = hist.index[exit_idx]
            days_held = exit_idx - entry_idx

            # Calculate returns
            actual_return = ((exit_price - entry_price) / entry_price) * 100

            # Also check max return during period
            holding_data = hist.iloc[entry_idx+1:exit_idx+1]
            max_high = holding_data['High'].max() if not holding_data.empty else exit_price
            max_return = ((max_high - entry_price) / entry_price) * 100

            trade = {
                'symbol': symbol,
                'entry_date': entry_actual_date,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'actual_return': actual_return,
                'max_return': max_return,
                'days_held': days_held,
                'exit_reason': exit_reason,
                'reached_5pct': max_return >= 5.0,
            }

            all_trades.append(trade)

    return all_trades


def run_scenario_b_filter_exit(stock_data, spy_data, entry_dates):
    """Scenario B: Dynamic filter-based exit"""

    print("\n" + "=" * 100)
    print("📊 SCENARIO B: DYNAMIC FILTER-BASED EXIT")
    print("=" * 100)

    rules = ExitRulesEngine()
    all_trades = []

    for entry_date in entry_dates:
        # Find stocks that pass filters
        passed_stocks = []
        for symbol, hist in stock_data.items():
            if apply_entry_filters(symbol, entry_date, hist, spy_data):
                passed_stocks.append(symbol)

        if not passed_stocks:
            continue

        print(f"\n📅 {entry_date.strftime('%Y-%m-%d')}: {len(passed_stocks)} stocks")

        # Simulate trades
        for symbol in passed_stocks:
            hist = stock_data[symbol]

            # Get entry price
            entry_idx = None
            for i, date in enumerate(hist.index):
                if date >= entry_date:
                    entry_idx = i
                    break

            if entry_idx is None or entry_idx + 20 >= len(hist):  # Need 20 days
                continue

            entry_price = hist['Close'].iloc[entry_idx]
            entry_actual_date = hist.index[entry_idx]

            # Simulate daily checks (up to 20 days)
            exit_idx = None
            exit_reason = None
            exit_details = {}

            for day in range(1, 21):  # Check up to 20 days
                check_idx = entry_idx + day
                if check_idx >= len(hist):
                    break

                position = {
                    'symbol': symbol,
                    'entry_date': entry_actual_date.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'days_held': day,
                }

                check_date = hist.index[check_idx]
                should_exit, reason, details = rules.check_exit(
                    position, check_date.strftime('%Y-%m-%d'), hist, spy_data
                )

                if should_exit:
                    exit_idx = check_idx
                    exit_reason = reason
                    exit_details = details
                    break

            # If no exit signal, hold to day 20
            if exit_idx is None:
                exit_idx = min(entry_idx + 20, len(hist) - 1)
                exit_reason = 'MAX_HOLD'

            exit_price = hist['Close'].iloc[exit_idx]
            exit_date = hist.index[exit_idx]
            days_held = exit_idx - entry_idx

            # Calculate returns
            actual_return = ((exit_price - entry_price) / entry_price) * 100

            # Max return during period
            holding_data = hist.iloc[entry_idx+1:exit_idx+1]
            max_high = holding_data['High'].max() if not holding_data.empty else exit_price
            max_return = ((max_high - entry_price) / entry_price) * 100

            trade = {
                'symbol': symbol,
                'entry_date': entry_actual_date,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'actual_return': actual_return,
                'max_return': max_return,
                'days_held': days_held,
                'exit_reason': exit_reason,
                'reached_5pct': max_return >= 5.0,
                'exit_score': exit_details.get('score', -1),
            }

            all_trades.append(trade)

    return all_trades


def analyze_results(trades, scenario_name):
    """Analyze and display results"""

    if not trades:
        print(f"\n❌ {scenario_name}: No trades")
        return {}

    # Calculate stats
    total_trades = len(trades)
    winners = [t for t in trades if t['actual_return'] > 0]
    losers = [t for t in trades if t['actual_return'] <= 0]
    big_winners = [t for t in trades if t['reached_5pct']]

    returns = [t['actual_return'] for t in trades]
    avg_return = np.mean(returns)
    avg_winner = np.mean([t['actual_return'] for t in winners]) if winners else 0
    avg_loser = np.mean([t['actual_return'] for t in losers]) if losers else 0

    win_rate = len(winners) / total_trades * 100
    hit_rate_5pct = len(big_winners) / total_trades * 100

    # Expectancy
    expectancy = (len(winners)/total_trades * avg_winner) + (len(losers)/total_trades * avg_loser)

    # P&L simulation ($1000 per trade)
    total_pnl = sum([t['actual_return'] * 10 for t in trades])  # $1000 * return%

    # Average holding period
    avg_days = np.mean([t['days_held'] for t in trades])

    stats = {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'expectancy': expectancy,
        'total_pnl': total_pnl,
        'hit_rate_5pct': hit_rate_5pct,
        'avg_days': avg_days,
        'best_trade': max(returns),
        'worst_trade': min(returns),
    }

    print(f"\n{'='*100}")
    print(f"📊 {scenario_name} RESULTS")
    print(f"{'='*100}")
    print(f"\n📈 Performance:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total_trades})")
    print(f"   5%+ Hit Rate: {hit_rate_5pct:.1f}% ({len(big_winners)}/{total_trades})")
    print(f"\n💰 Returns:")
    print(f"   Average Return: {avg_return:+.2f}%")
    print(f"   Winners Avg: {avg_winner:+.2f}%")
    print(f"   Losers Avg: {avg_loser:+.2f}%")
    print(f"   Expectancy: {expectancy:+.2f}%")
    print(f"\n💵 P&L ($1000/trade):")
    print(f"   Total P&L: ${total_pnl:+,.2f}")
    print(f"\n⏱️  Timing:")
    print(f"   Avg Holding: {avg_days:.1f} days")
    print(f"   Best Trade: {stats['best_trade']:+.2f}%")
    print(f"   Worst Trade: {stats['worst_trade']:+.2f}%")

    # Exit reasons
    print(f"\n🚪 Exit Reasons:")
    exit_reasons = {}
    for t in trades:
        reason = t['exit_reason']
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    for reason, count in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        pct = count / total_trades * 100
        print(f"   {reason}: {count} ({pct:.1f}%)")

    return stats


def compare_scenarios(stats_a, stats_b):
    """Compare two scenarios"""

    print(f"\n\n{'='*100}")
    print("🔬 SCENARIO COMPARISON")
    print(f"{'='*100}\n")

    metrics = [
        ('Total Trades', 'total_trades', ''),
        ('Win Rate', 'win_rate', '%'),
        ('5%+ Hit Rate', 'hit_rate_5pct', '%'),
        ('Avg Return', 'avg_return', '%'),
        ('Expectancy', 'expectancy', '%'),
        ('Total P&L', 'total_pnl', '$'),
        ('Avg Holding Days', 'avg_days', 'd'),
        ('Best Trade', 'best_trade', '%'),
        ('Worst Trade', 'worst_trade', '%'),
    ]

    print(f"{'Metric':<20} {'Scenario A':<20} {'Scenario B':<20} {'Winner':<15}")
    print("-" * 80)

    for name, key, unit in metrics:
        val_a = stats_a.get(key, 0)
        val_b = stats_b.get(key, 0)

        # Determine winner (higher is better except for worst_trade and avg_days)
        if key in ['worst_trade']:
            winner = 'B 🏆' if val_b > val_a else 'A 🏆'
        elif key in ['avg_days']:
            winner = 'B 🏆' if val_b < val_a else 'A 🏆'
        else:
            winner = 'B 🏆' if val_b > val_a else 'A 🏆'

        if unit == '$':
            str_a = f"${val_a:+,.2f}"
            str_b = f"${val_b:+,.2f}"
        elif unit in ['%', 'd']:
            str_a = f"{val_a:+.2f}{unit}"
            str_b = f"{val_b:+.2f}{unit}"
        else:
            str_a = f"{val_a:.0f}"
            str_b = f"{val_b:.0f}"

        print(f"{name:<20} {str_a:<20} {str_b:<20} {winner:<15}")

    # Overall verdict
    print(f"\n{'='*100}")

    # Calculate overall score
    score_b = 0
    score_a = 0

    if stats_b['win_rate'] > stats_a['win_rate']:
        score_b += 1
    else:
        score_a += 1

    if stats_b['avg_return'] > stats_a['avg_return']:
        score_b += 1
    else:
        score_a += 1

    if stats_b['expectancy'] > stats_a['expectancy']:
        score_b += 1
    else:
        score_a += 1

    if stats_b['total_pnl'] > stats_a['total_pnl']:
        score_b += 1
    else:
        score_a += 1

    if stats_b['worst_trade'] > stats_a['worst_trade']:  # Less bad
        score_b += 1
    else:
        score_a += 1

    print(f"\n🏆 OVERALL WINNER:")
    if score_b > score_a:
        print(f"   SCENARIO B (Filter-based Exit) wins {score_b}-{score_a}")
        print(f"   ✅ Better strategy!")
    elif score_a > score_b:
        print(f"   SCENARIO A (Fixed TP/SL) wins {score_a}-{score_b}")
        print(f"   ⚠️  Original strategy performed better")
    else:
        print(f"   TIE {score_a}-{score_b}")
        print(f"   Both strategies similar")

    print(f"{'='*100}\n")


def main():
    print("=" * 100)
    print("🔬 COMPREHENSIVE BACKTEST COMPARISON")
    print("=" * 100)

    # Download data
    print("\n📥 Downloading data...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)

    stock_data = {}
    for symbol in STOCK_UNIVERSE:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty:
                stock_data[symbol] = hist
        except:
            pass

    spy = yf.Ticker('SPY')
    spy_data = spy.history(start=start_date, end=end_date)

    print(f"✅ Downloaded {len(stock_data)} stocks")

    # Generate entry dates (same as before)
    all_dates = spy_data.index
    entry_indices = []
    start_idx = len(all_dates) - 60
    while start_idx < len(all_dates) - 20:  # Need 20 days for scenario B
        entry_indices.append(start_idx)
        start_idx += 7

    entry_dates = [all_dates[i] for i in entry_indices]

    print(f"📅 Testing {len(entry_dates)} entry points")

    # Run Scenario A
    trades_a = run_scenario_a_fixed_tpsl(stock_data, spy_data, entry_dates)
    stats_a = analyze_results(trades_a, "SCENARIO A: FIXED TP/SL")

    # Run Scenario B
    trades_b = run_scenario_b_filter_exit(stock_data, spy_data, entry_dates)
    stats_b = analyze_results(trades_b, "SCENARIO B: FILTER EXIT")

    # Compare
    if stats_a and stats_b:
        compare_scenarios(stats_a, stats_b)


if __name__ == "__main__":
    main()
