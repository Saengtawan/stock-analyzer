#!/usr/bin/env python3
"""
Comprehensive 2-Month Backtest (Nov-Dec 2025)
Test Growth Catalyst v8.0 strategy with multiple entry points
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Universe of stocks to scan
STOCK_UNIVERSE = [
    # Mega caps
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    # Tech growth
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'TEAM', 'DASH', 'SHOP',
    # Semiconductors
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC', 'LRCX', 'TSM', 'ASML',
    # Cloud/SaaS
    'CRM', 'NOW', 'WDAY', 'PANW', 'ZS', 'OKTA', 'MDB',
    # Consumer/Fintech
    'UBER', 'ABNB', 'COIN', 'SQ', 'HOOD', 'ROKU',
    # AI/Data
    'MRVL', 'MU', 'SNPS', 'CDNS', 'ARM',
]

# v8.0 Filter Thresholds
FILTERS = {
    'rsi_min': 49.0,
    'momentum_7d_min': 3.5,
    'rs_14d_min': 1.9,
    'dist_ma20_min': -2.8,
}

# Strategy Parameters
TARGET_RETURN = 5.0  # 5% target
HOLDING_PERIOD = 14  # 14 days


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def apply_filters(symbol, entry_date, hist_data, spy_data):
    """
    Apply v8.0 filters at a specific entry date
    Returns (passed: bool, filters_dict: dict, reason: str)
    """
    try:
        # Get data up to entry date
        data = hist_data[hist_data.index <= entry_date].copy()

        if len(data) < 50:
            return False, {}, "Insufficient data"

        close = data['Close']
        entry_price = close.iloc[-1]

        filters_result = {}

        # Filter 1: RSI > 49
        rsi = calculate_rsi(close)
        rsi_value = rsi.iloc[-1]
        filters_result['rsi'] = rsi_value

        if rsi_value < FILTERS['rsi_min']:
            return False, filters_result, f"RSI {rsi_value:.1f} < {FILTERS['rsi_min']}"

        # Filter 2: Momentum 7d > 3.5%
        if len(close) >= 7:
            price_7d_ago = close.iloc[-7]
            momentum_7d = ((entry_price - price_7d_ago) / price_7d_ago) * 100
            filters_result['momentum_7d'] = momentum_7d

            if momentum_7d < FILTERS['momentum_7d_min']:
                return False, filters_result, f"Momentum {momentum_7d:.1f}% < {FILTERS['momentum_7d_min']}%"
        else:
            return False, filters_result, "Not enough data for 7d momentum"

        # Filter 3: 14-day RS > 1.9%
        if len(close) >= 14:
            price_14d_ago = close.iloc[-14]
            stock_return_14d = ((entry_price / price_14d_ago) - 1) * 100

            # Get SPY return
            spy_at_entry = spy_data[spy_data.index <= entry_date]
            if len(spy_at_entry) >= 14:
                spy_price_now = spy_at_entry['Close'].iloc[-1]
                spy_price_14d_ago = spy_at_entry['Close'].iloc[-14]
                spy_return_14d = ((spy_price_now / spy_price_14d_ago) - 1) * 100
                rs_14d = stock_return_14d - spy_return_14d
                filters_result['rs_14d'] = rs_14d

                if rs_14d < FILTERS['rs_14d_min']:
                    return False, filters_result, f"RS {rs_14d:.1f}% < {FILTERS['rs_14d_min']}%"
            else:
                return False, filters_result, "Not enough SPY data"
        else:
            return False, filters_result, "Not enough data for 14d RS"

        # Filter 4: Distance from MA20 > -2.8%
        if len(close) >= 20:
            ma20 = close.rolling(window=20).mean().iloc[-1]
            dist_ma20 = ((entry_price - ma20) / ma20) * 100
            filters_result['dist_ma20'] = dist_ma20

            if dist_ma20 < FILTERS['dist_ma20_min']:
                return False, filters_result, f"MA20 dist {dist_ma20:.1f}% < {FILTERS['dist_ma20_min']}%"
        else:
            return False, filters_result, "Not enough data for MA20"

        # All filters passed
        return True, filters_result, "PASSED"

    except Exception as e:
        return False, {}, f"Error: {str(e)}"


def simulate_trade(symbol, entry_date, exit_date, hist_data):
    """
    Simulate a trade from entry to exit date
    Returns trade result dict
    """
    try:
        # Get entry price
        entry_data = hist_data[hist_data.index <= entry_date]
        if entry_data.empty:
            return None

        entry_price = entry_data['Close'].iloc[-1]

        # Get data during holding period
        holding_data = hist_data[(hist_data.index > entry_date) & (hist_data.index <= exit_date)]

        if holding_data.empty:
            return None

        # Calculate returns
        max_high = holding_data['High'].max()
        exit_price = holding_data['Close'].iloc[-1]

        actual_return = ((exit_price - entry_price) / entry_price) * 100
        max_return = ((max_high - entry_price) / entry_price) * 100

        # Check if target reached
        reached_target = max_return >= TARGET_RETURN

        return {
            'symbol': symbol,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'max_high': max_high,
            'actual_return': actual_return,
            'max_return': max_return,
            'reached_target': reached_target,
            'holding_days': len(holding_data),
        }

    except Exception as e:
        return None


def run_backtest():
    """Run comprehensive 2-month backtest"""

    print("=" * 100)
    print("📊 COMPREHENSIVE 2-MONTH BACKTEST (Nov-Dec 2025)")
    print("=" * 100)
    print(f"\nStrategy: Growth Catalyst v8.0")
    print(f"Target: {TARGET_RETURN}% in {HOLDING_PERIOD} days")
    print(f"Universe: {len(STOCK_UNIVERSE)} stocks")
    print(f"\nFilters:")
    print(f"  • RSI > {FILTERS['rsi_min']}")
    print(f"  • Momentum 7d > {FILTERS['momentum_7d_min']}%")
    print(f"  • 14-day RS > {FILTERS['rs_14d_min']}%")
    print(f"  • Distance from MA20 > {FILTERS['dist_ma20_min']}%")
    print()

    # Download historical data (4 months to ensure enough data for calculations)
    print("📥 Downloading historical data...")
    end_date = datetime(2025, 12, 25)
    start_date = end_date - timedelta(days=120)

    # Download all stocks
    stock_data = {}
    for symbol in STOCK_UNIVERSE:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty:
                stock_data[symbol] = hist
        except:
            pass

    # Download SPY
    spy = yf.Ticker('SPY')
    spy_data = spy.history(start=start_date, end=end_date)

    print(f"✅ Downloaded data for {len(stock_data)} stocks\n")

    # Generate entry points (every 7 days for 2 months = ~8 entry points)
    backtest_start = datetime(2025, 11, 1)
    backtest_end = datetime(2025, 12, 11)  # Last entry date (needs 14 days to exit by Dec 25)

    entry_dates = []
    current = backtest_start
    while current <= backtest_end:
        entry_dates.append(current)
        current += timedelta(days=7)

    print(f"📅 Testing {len(entry_dates)} entry points from {backtest_start.date()} to {backtest_end.date()}")
    print(f"Entry dates: {[d.strftime('%Y-%m-%d') for d in entry_dates]}\n")

    # Run backtest
    all_trades = []

    for i, entry_date in enumerate(entry_dates):
        print(f"\n{'='*100}")
        print(f"📍 ENTRY POINT {i+1}/{len(entry_dates)}: {entry_date.strftime('%Y-%m-%d')}")
        print(f"{'='*100}")

        exit_date = entry_date + timedelta(days=HOLDING_PERIOD)

        passed_stocks = []
        failed_stocks = []

        # Scan universe and apply filters
        for symbol in STOCK_UNIVERSE:
            if symbol not in stock_data:
                continue

            passed, filters, reason = apply_filters(symbol, entry_date, stock_data[symbol], spy_data)

            if passed:
                passed_stocks.append(symbol)
            else:
                failed_stocks.append((symbol, reason))

        print(f"\n🔍 Scan Results:")
        print(f"  Passed filters: {len(passed_stocks)}/{len(stock_data)} stocks")
        print(f"  Failed filters: {len(failed_stocks)}")

        if passed_stocks:
            print(f"\n  ✅ Passed: {', '.join(passed_stocks)}")

        # Execute trades for passed stocks
        trades_this_period = []
        for symbol in passed_stocks:
            trade = simulate_trade(symbol, entry_date, exit_date, stock_data[symbol])
            if trade:
                trades_this_period.append(trade)
                all_trades.append(trade)

        # Show results for this entry point
        if trades_this_period:
            winners = [t for t in trades_this_period if t['reached_target']]
            win_rate = len(winners) / len(trades_this_period) * 100
            avg_return = np.mean([t['actual_return'] for t in trades_this_period])

            print(f"\n  📊 Results:")
            print(f"    Win Rate: {win_rate:.1f}% ({len(winners)}/{len(trades_this_period)})")
            print(f"    Avg Return: {avg_return:+.2f}%")

            for trade in trades_this_period:
                status = "✅" if trade['reached_target'] else "❌"
                print(f"    {status} {trade['symbol']}: {trade['actual_return']:+.1f}% (max: {trade['max_return']:+.1f}%)")

    # Overall Summary
    print(f"\n\n{'='*100}")
    print("📊 OVERALL BACKTEST SUMMARY (2 Months)")
    print(f"{'='*100}\n")

    if not all_trades:
        print("❌ No trades executed")
        return

    # Calculate statistics
    winners = [t for t in all_trades if t['reached_target']]
    losers = [t for t in all_trades if not t['reached_target']]

    total_trades = len(all_trades)
    win_rate = len(winners) / total_trades * 100

    avg_return = np.mean([t['actual_return'] for t in all_trades])
    avg_winner = np.mean([t['max_return'] for t in winners]) if winners else 0
    avg_loser = np.mean([t['actual_return'] for t in losers]) if losers else 0

    total_return = sum([t['actual_return'] for t in all_trades])

    # Calculate expectancy
    win_prob = len(winners) / total_trades
    lose_prob = len(losers) / total_trades
    expectancy = (win_prob * avg_winner) + (lose_prob * avg_loser)

    # Max drawdown (consecutive losers)
    consecutive_losers = 0
    max_consecutive_losers = 0
    for trade in all_trades:
        if not trade['reached_target']:
            consecutive_losers += 1
            max_consecutive_losers = max(max_consecutive_losers, consecutive_losers)
        else:
            consecutive_losers = 0

    print(f"📈 Performance Metrics:")
    print(f"  Total Trades: {total_trades}")
    print(f"  Win Rate: {win_rate:.1f}% ({len(winners)}/{total_trades})")
    print(f"  Lose Rate: {100-win_rate:.1f}% ({len(losers)}/{total_trades})")
    print()
    print(f"💰 Returns:")
    print(f"  Average Return: {avg_return:+.2f}%")
    print(f"  Winners Avg: {avg_winner:+.2f}%")
    print(f"  Losers Avg: {avg_loser:+.2f}%")
    print(f"  Total Return: {total_return:+.2f}%")
    print(f"  Expectancy: {expectancy:+.2f}%")
    print()
    print(f"📉 Risk Metrics:")
    print(f"  Max Consecutive Losses: {max_consecutive_losers}")
    print(f"  Worst Trade: {min([t['actual_return'] for t in all_trades]):+.2f}%")
    print(f"  Best Trade: {max([t['max_return'] for t in all_trades]):+.2f}%")
    print()

    # Show top winners and losers
    print(f"🏆 Top 10 Winners:")
    top_winners = sorted(winners, key=lambda x: x['max_return'], reverse=True)[:10]
    for i, trade in enumerate(top_winners, 1):
        print(f"  {i:2d}. {trade['symbol']:6s} {trade['entry_date'].strftime('%Y-%m-%d')}: {trade['max_return']:+6.2f}% (exit: {trade['actual_return']:+.2f}%)")

    print(f"\n💔 Top 10 Losers:")
    top_losers = sorted(all_trades, key=lambda x: x['actual_return'])[:10]
    for i, trade in enumerate(top_losers, 1):
        print(f"  {i:2d}. {trade['symbol']:6s} {trade['entry_date'].strftime('%Y-%m-%d')}: {trade['actual_return']:+6.2f}% (max: {trade['max_return']:+.2f}%)")

    # Month by month breakdown
    print(f"\n\n📅 Monthly Breakdown:")

    nov_trades = [t for t in all_trades if t['entry_date'].month == 11]
    dec_trades = [t for t in all_trades if t['entry_date'].month == 12]

    if nov_trades:
        nov_win_rate = len([t for t in nov_trades if t['reached_target']]) / len(nov_trades) * 100
        nov_avg = np.mean([t['actual_return'] for t in nov_trades])
        print(f"\n  November 2025:")
        print(f"    Trades: {len(nov_trades)}")
        print(f"    Win Rate: {nov_win_rate:.1f}%")
        print(f"    Avg Return: {nov_avg:+.2f}%")

    if dec_trades:
        dec_win_rate = len([t for t in dec_trades if t['reached_target']]) / len(dec_trades) * 100
        dec_avg = np.mean([t['actual_return'] for t in dec_trades])
        print(f"\n  December 2025:")
        print(f"    Trades: {len(dec_trades)}")
        print(f"    Win Rate: {dec_win_rate:.1f}%")
        print(f"    Avg Return: {dec_avg:+.2f}%")

    # Final verdict
    print(f"\n\n{'='*100}")
    if win_rate >= 70 and expectancy > 3.0:
        print("✅ EXCELLENT: Strategy is performing very well!")
    elif win_rate >= 60 and expectancy > 2.0:
        print("👍 GOOD: Strategy shows promise")
    elif win_rate >= 50 and expectancy > 0:
        print("⚠️  FAIR: Strategy is marginally profitable")
    else:
        print("❌ POOR: Strategy needs improvement")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    run_backtest()
