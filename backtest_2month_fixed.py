#!/usr/bin/env python3
"""
Fixed Comprehensive 2-Month Backtest (Nov-Dec 2025)
Use actual available data dates
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

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

TARGET_RETURN = 5.0
HOLDING_PERIOD = 14


def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def apply_filters(symbol, entry_date, hist_data, spy_data):
    """Apply v8.0 filters at entry date"""
    try:
        data = hist_data[hist_data.index <= entry_date].copy()
        if len(data) < 50:
            return False, {}

        close = data['Close']
        entry_price = close.iloc[-1]

        # RSI
        rsi = calculate_rsi(close)
        rsi_value = rsi.iloc[-1]
        if rsi_value < FILTERS['rsi_min']:
            return False, {}

        # Momentum 7d
        if len(close) >= 7:
            price_7d_ago = close.iloc[-7]
            momentum_7d = ((entry_price - price_7d_ago) / price_7d_ago) * 100
            if momentum_7d < FILTERS['momentum_7d_min']:
                return False, {}
        else:
            return False, {}

        # 14-day RS
        if len(close) >= 14:
            price_14d_ago = close.iloc[-14]
            stock_return_14d = ((entry_price / price_14d_ago) - 1) * 100

            spy_at_entry = spy_data[spy_data.index <= entry_date]
            if len(spy_at_entry) >= 14:
                spy_price_now = spy_at_entry['Close'].iloc[-1]
                spy_price_14d_ago = spy_at_entry['Close'].iloc[-14]
                spy_return_14d = ((spy_price_now / spy_price_14d_ago) - 1) * 100
                rs_14d = stock_return_14d - spy_return_14d
                if rs_14d < FILTERS['rs_14d_min']:
                    return False, {}
            else:
                return False, {}
        else:
            return False, {}

        # Distance from MA20
        if len(close) >= 20:
            ma20 = close.rolling(window=20).mean().iloc[-1]
            dist_ma20 = ((entry_price - ma20) / ma20) * 100
            if dist_ma20 < FILTERS['dist_ma20_min']:
                return False, {}
        else:
            return False, {}

        return True, {'rsi': rsi_value, 'momentum_7d': momentum_7d, 'rs_14d': rs_14d, 'dist_ma20': dist_ma20}

    except Exception as e:
        return False, {}


def simulate_trade(symbol, entry_date, hist_data, holding_days=14):
    """Simulate trade"""
    try:
        # Find entry index
        entry_idx = None
        for i, date in enumerate(hist_data.index):
            if date >= entry_date:
                entry_idx = i
                break

        if entry_idx is None or entry_idx == 0:
            return None

        entry_price = hist_data['Close'].iloc[entry_idx]
        entry_actual_date = hist_data.index[entry_idx]

        # Get holding period data
        end_idx = min(entry_idx + holding_days, len(hist_data) - 1)

        if end_idx <= entry_idx:
            return None

        holding_data = hist_data.iloc[entry_idx+1:end_idx+1]

        if holding_data.empty:
            return None

        exit_price = holding_data['Close'].iloc[-1]
        exit_date = holding_data.index[-1]
        max_high = holding_data['High'].max()

        actual_return = ((exit_price - entry_price) / entry_price) * 100
        max_return = ((max_high - entry_price) / entry_price) * 100

        return {
            'symbol': symbol,
            'entry_date': entry_actual_date,
            'exit_date': exit_date,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'actual_return': actual_return,
            'max_return': max_return,
            'reached_target': max_return >= TARGET_RETURN,
            'holding_days': len(holding_data),
        }

    except Exception as e:
        return None


def run_backtest():
    print("=" * 100)
    print("📊 COMPREHENSIVE 2-MONTH BACKTEST (Nov-Dec 2025)")
    print("=" * 100)

    # Download data
    print("\n📥 Downloading historical data...")
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

    if spy_data.empty:
        print("❌ No SPY data")
        return

    print(f"✅ Downloaded {len(stock_data)} stocks")

    # Generate entry points using actual trading dates
    # Get dates from SPY (market trading days only)
    all_dates = spy_data.index

    # Start from 60 days ago, test every 7 trading days
    # Need to leave 14 days for exit
    if len(all_dates) < 74:  # Need at least 60 + 14 days
        print("❌ Insufficient data")
        return

    # Entry points: -60, -53, -46, -39, -32, -25 days from latest
    # This gives us ~8-9 entry points over 2 months
    entry_indices = []
    start_idx = len(all_dates) - 60
    while start_idx < len(all_dates) - 14:
        entry_indices.append(start_idx)
        start_idx += 7

    entry_dates = [all_dates[i] for i in entry_indices]

    latest_date = all_dates[-1]
    print(f"📅 Latest data: {latest_date.strftime('%Y-%m-%d')}")
    print(f"📅 Testing {len(entry_dates)} entry points")
    print(f"    From: {entry_dates[0].strftime('%Y-%m-%d')}")
    print(f"    To: {entry_dates[-1].strftime('%Y-%m-%d')}")

    # Run backtest
    all_trades = []

    for i, entry_date in enumerate(entry_dates):
        print(f"\n{'='*100}")
        print(f"📍 ENTRY {i+1}/{len(entry_dates)}: {entry_date.strftime('%Y-%m-%d')}")
        print(f"{'='*100}")

        passed_stocks = []

        # Apply filters
        for symbol in stock_data.keys():
            passed, _ = apply_filters(symbol, entry_date, stock_data[symbol], spy_data)
            if passed:
                passed_stocks.append(symbol)

        print(f"✅ Passed filters: {len(passed_stocks)} stocks")
        if passed_stocks:
            print(f"   {', '.join(passed_stocks)}")

        # Execute trades
        trades_this_period = []
        for symbol in passed_stocks:
            trade = simulate_trade(symbol, entry_date, stock_data[symbol], HOLDING_PERIOD)
            if trade:
                trades_this_period.append(trade)
                all_trades.append(trade)

        # Show results
        if trades_this_period:
            winners = [t for t in trades_this_period if t['reached_target']]
            win_rate = len(winners) / len(trades_this_period) * 100
            avg_return = np.mean([t['actual_return'] for t in trades_this_period])

            print(f"\n📊 Results: Win Rate {win_rate:.0f}% ({len(winners)}/{len(trades_this_period)}), Avg Return {avg_return:+.1f}%")

            for t in sorted(trades_this_period, key=lambda x: x['actual_return'], reverse=True):
                status = "✅" if t['reached_target'] else "❌"
                print(f"   {status} {t['symbol']:6s}: {t['actual_return']:+5.1f}% (max: {t['max_return']:+5.1f}%)")

    # Summary
    print(f"\n\n{'='*100}")
    print("📊 OVERALL SUMMARY")
    print(f"{'='*100}\n")

    if not all_trades:
        print("❌ No trades executed")
        return

    winners = [t for t in all_trades if t['reached_target']]
    losers = [t for t in all_trades if not t['reached_target']]

    total_trades = len(all_trades)
    win_rate = len(winners) / total_trades * 100

    avg_return = np.mean([t['actual_return'] for t in all_trades])
    avg_winner = np.mean([t['max_return'] for t in winners]) if winners else 0
    avg_loser = np.mean([t['actual_return'] for t in losers]) if losers else 0

    # Expectancy
    expectancy = (len(winners)/total_trades * avg_winner) + (len(losers)/total_trades * avg_loser)

    # If we invested $100 in each trade
    total_invested = total_trades * 100
    total_value = sum([(1 + t['actual_return']/100) * 100 for t in all_trades])
    total_profit = total_value - total_invested

    print(f"📈 PERFORMANCE METRICS:")
    print(f"   Total Trades: {total_trades}")
    print(f"   Win Rate: {win_rate:.1f}% ({len(winners)}/{total_trades})")
    print(f"   Average Return: {avg_return:+.2f}%")
    print(f"   Expectancy: {expectancy:+.2f}%")
    print()
    print(f"💰 RETURNS:")
    print(f"   Winners: {len(winners)} (Avg: {avg_winner:+.2f}%)")
    print(f"   Losers: {len(losers)} (Avg: {avg_loser:+.2f}%)")
    print(f"   Best Trade: {max([t['max_return'] for t in all_trades]):+.2f}%")
    print(f"   Worst Trade: {min([t['actual_return'] for t in all_trades]):+.2f}%")
    print()
    print(f"💵 P&L SIMULATION ($100 per trade):")
    print(f"   Total Invested: ${total_invested:,.2f}")
    print(f"   Final Value: ${total_value:,.2f}")
    print(f"   Profit/Loss: ${total_profit:+,.2f} ({total_profit/total_invested*100:+.1f}%)")
    print()

    # Top winners/losers
    print(f"🏆 TOP 10 WINNERS:")
    for i, t in enumerate(sorted(winners, key=lambda x: x['max_return'], reverse=True)[:10], 1):
        print(f"   {i:2d}. {t['symbol']:6s} {t['entry_date'].strftime('%m/%d')}: {t['max_return']:+6.2f}% (exit: {t['actual_return']:+.1f}%)")

    print(f"\n💔 TOP 10 LOSERS:")
    for i, t in enumerate(sorted(all_trades, key=lambda x: x['actual_return'])[:10], 1):
        print(f"   {i:2d}. {t['symbol']:6s} {t['entry_date'].strftime('%m/%d')}: {t['actual_return']:+6.2f}% (max: {t['max_return']:+.1f}%)")

    # Final verdict
    print(f"\n{'='*100}")
    if win_rate >= 70 and expectancy > 3.0:
        print("✅ EXCELLENT: Strategy performing very well!")
    elif win_rate >= 60 and expectancy > 2.0:
        print("👍 GOOD: Strategy shows strong promise")
    elif win_rate >= 50 and expectancy > 0:
        print("⚠️  FAIR: Strategy is marginally profitable")
    else:
        print("❌ POOR: Strategy needs improvement")

    print(f"{'='*100}\n")


if __name__ == "__main__":
    run_backtest()
