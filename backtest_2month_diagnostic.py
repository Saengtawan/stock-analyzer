#!/usr/bin/env python3
"""
Diagnostic Backtest - See which filters are blocking stocks
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import Counter

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


def analyze_filters(symbol, entry_date, hist_data, spy_data):
    """Analyze which filters pass/fail and by how much"""
    try:
        data = hist_data[hist_data.index <= entry_date].copy()
        if len(data) < 50:
            return None

        close = data['Close']
        entry_price = close.iloc[-1]

        result = {
            'symbol': symbol,
            'entry_date': entry_date,
            'entry_price': entry_price,
            'filters': {},
            'failed_filters': [],
        }

        # RSI
        rsi = calculate_rsi(close)
        rsi_value = rsi.iloc[-1]
        result['filters']['rsi'] = rsi_value
        if rsi_value < FILTERS['rsi_min']:
            result['failed_filters'].append(f"RSI {rsi_value:.1f} < {FILTERS['rsi_min']}")

        # Momentum 7d
        if len(close) >= 7:
            price_7d_ago = close.iloc[-7]
            momentum_7d = ((entry_price - price_7d_ago) / price_7d_ago) * 100
            result['filters']['momentum_7d'] = momentum_7d
            if momentum_7d < FILTERS['momentum_7d_min']:
                result['failed_filters'].append(f"Momentum {momentum_7d:.1f}% < {FILTERS['momentum_7d_min']}%")

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
                result['filters']['rs_14d'] = rs_14d
                if rs_14d < FILTERS['rs_14d_min']:
                    result['failed_filters'].append(f"RS {rs_14d:.1f}% < {FILTERS['rs_14d_min']}%")

        # Distance from MA20
        if len(close) >= 20:
            ma20 = close.rolling(window=20).mean().iloc[-1]
            dist_ma20 = ((entry_price - ma20) / ma20) * 100
            result['filters']['dist_ma20'] = dist_ma20
            if dist_ma20 < FILTERS['dist_ma20_min']:
                result['failed_filters'].append(f"MA20 {dist_ma20:.1f}% < {FILTERS['dist_ma20_min']}%")

        return result

    except Exception as e:
        return None


def run_diagnostic():
    print("=" * 100)
    print("🔍 DIAGNOSTIC: Which Filters Are Blocking Stocks?")
    print("=" * 100)

    # Download data
    print("\n📥 Downloading data...")
    end_date = datetime(2025, 12, 25)
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

    print(f"✅ Downloaded {len(stock_data)} stocks\n")

    # Find the most recent date with data
    # Use 14 trading days ago from end date
    if spy_data.empty:
        print("❌ No SPY data available")
        return

    latest_date = spy_data.index[-1]
    entry_date = spy_data.index[-14] if len(spy_data) >= 14 else spy_data.index[0]

    print(f"📅 Latest data available: {latest_date.strftime('%Y-%m-%d')}")
    print(f"📅 Testing entry date: {entry_date.strftime('%Y-%m-%d')} (14 days ago)\n")
    print("=" * 100)

    all_results = []
    filter_failures = Counter()

    for symbol in stock_data.keys():
        result = analyze_filters(symbol, entry_date, stock_data[symbol], spy_data)
        if result:
            all_results.append(result)
            for failure in result['failed_filters']:
                # Extract filter name
                filter_name = failure.split()[0]
                filter_failures[filter_name] += 1

    # Sort by number of filters passed
    all_results.sort(key=lambda x: len(x['failed_filters']))

    # Show stocks that passed all or most filters
    print("🏆 STOCKS CLOSEST TO PASSING:\n")
    for i, r in enumerate(all_results[:15], 1):
        failed_count = len(r['failed_filters'])
        passed_count = 4 - failed_count

        status = "✅ PASSED" if failed_count == 0 else f"❌ Failed {failed_count}/4"

        print(f"{i:2d}. {r['symbol']:6s} - {status}")
        print(f"    RSI: {r['filters'].get('rsi', 0):.1f} (need >{FILTERS['rsi_min']})")
        print(f"    Momentum 7d: {r['filters'].get('momentum_7d', 0):+.1f}% (need >{FILTERS['momentum_7d_min']}%)")
        print(f"    RS 14d: {r['filters'].get('rs_14d', 0):+.1f}% (need >{FILTERS['rs_14d_min']}%)")
        print(f"    MA20 dist: {r['filters'].get('dist_ma20', 0):+.1f}% (need >{FILTERS['dist_ma20_min']}%)")

        if r['failed_filters']:
            print(f"    Failed: {', '.join(r['failed_filters'])}")
        print()

    # Summary statistics
    print("\n" + "=" * 100)
    print("📊 FILTER FAILURE STATISTICS:\n")

    total_stocks = len(all_results)

    if total_stocks == 0:
        print("❌ No stocks could be analyzed")
        return

    passed_all = len([r for r in all_results if len(r['failed_filters']) == 0])
    failed_1 = len([r for r in all_results if len(r['failed_filters']) == 1])
    failed_2 = len([r for r in all_results if len(r['failed_filters']) == 2])
    failed_3 = len([r for r in all_results if len(r['failed_filters']) == 3])
    failed_all = len([r for r in all_results if len(r['failed_filters']) == 4])

    print(f"Total Stocks Tested: {total_stocks}")
    print(f"  ✅ Passed All (0 failures): {passed_all} ({passed_all/total_stocks*100:.1f}%)")
    print(f"  🟡 Failed 1 filter: {failed_1} ({failed_1/total_stocks*100:.1f}%)")
    print(f"  🟠 Failed 2 filters: {failed_2} ({failed_2/total_stocks*100:.1f}%)")
    print(f"  🔴 Failed 3 filters: {failed_3} ({failed_3/total_stocks*100:.1f}%)")
    print(f"  ❌ Failed All (4 failures): {failed_all} ({failed_all/total_stocks*100:.1f}%)")

    print(f"\n\n🚫 MOST COMMON FILTER FAILURES:\n")
    for filter_name, count in filter_failures.most_common():
        pct = count / total_stocks * 100
        print(f"  {filter_name}: {count}/{total_stocks} stocks ({pct:.1f}%)")

    # Calculate average values
    print(f"\n\n📊 AVERAGE FILTER VALUES (Current Market):\n")
    avg_rsi = np.mean([r['filters'].get('rsi', 0) for r in all_results])
    avg_momentum = np.mean([r['filters'].get('momentum_7d', 0) for r in all_results])
    avg_rs = np.mean([r['filters'].get('rs_14d', 0) for r in all_results])
    avg_ma20 = np.mean([r['filters'].get('dist_ma20', 0) for r in all_results])

    print(f"  Average RSI: {avg_rsi:.1f} (threshold: >{FILTERS['rsi_min']})")
    print(f"  Average Momentum 7d: {avg_momentum:+.1f}% (threshold: >{FILTERS['momentum_7d_min']}%)")
    print(f"  Average RS 14d: {avg_rs:+.1f}% (threshold: >{FILTERS['rs_14d_min']}%)")
    print(f"  Average MA20 dist: {avg_ma20:+.1f}% (threshold: >{FILTERS['dist_ma20_min']}%)")

    print("\n" + "=" * 100)
    print("\n💡 RECOMMENDATIONS:\n")

    # Check if filters are too strict
    if passed_all == 0:
        print("⚠️  NO STOCKS PASSED ALL FILTERS!")
        print("\nConsider relaxing filters:")

        if avg_rsi < FILTERS['rsi_min']:
            print(f"  • RSI: Lower threshold from {FILTERS['rsi_min']} to ~{avg_rsi:.0f}")

        if avg_momentum < FILTERS['momentum_7d_min']:
            print(f"  • Momentum 7d: Lower from {FILTERS['momentum_7d_min']}% to ~{avg_momentum:.1f}%")

        if avg_rs < FILTERS['rs_14d_min']:
            print(f"  • RS 14d: Lower from {FILTERS['rs_14d_min']}% to ~{avg_rs:.1f}%")

        if avg_ma20 < FILTERS['dist_ma20_min']:
            print(f"  • MA20 dist: Lower from {FILTERS['dist_ma20_min']}% to ~{avg_ma20:.1f}%")

        print(f"\n  OR use a more relaxed version that allows 1-2 filter failures")

    print()


if __name__ == "__main__":
    run_diagnostic()
