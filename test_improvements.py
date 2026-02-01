#!/usr/bin/env python3
"""
Test All Improvement Versions + Bear Market
Quick comparison test
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Test configurations
VERSIONS = {
    'V1_Baseline': {
        'name': 'Current (Baseline)',
        'entry_filters': {'rsi': 49, 'mom_7d': 3.5, 'rs_14d': 1.9, 'ma20': -2.8},
        'exit_rules': {'score_threshold': 1, 'stop_loss': -10, 'max_hold': 20},
        'description': 'Current strategy (58.7% WR)'
    },
    'V2_Stricter_Entry': {
        'name': 'Stricter Entry',
        'entry_filters': {'rsi': 55, 'mom_7d': 5.0, 'rs_14d': 3.0, 'ma20': 0},
        'exit_rules': {'score_threshold': 1, 'stop_loss': -10, 'max_hold': 20},
        'description': 'Higher quality entries → Better WR'
    },
    'V3_Better_Exit': {
        'name': 'Better Exit',
        'entry_filters': {'rsi': 49, 'mom_7d': 3.5, 'rs_14d': 1.9, 'ma20': -2.8},
        'exit_rules': {'score_threshold': 2, 'stop_loss': -6, 'max_hold': 15},
        'description': 'Tighter stops → Better R:R'
    },
    'V4_Combined': {
        'name': 'Combined Best',
        'entry_filters': {'rsi': 55, 'mom_7d': 5.0, 'rs_14d': 3.0, 'ma20': 0},
        'exit_rules': {'score_threshold': 2, 'stop_loss': -6, 'max_hold': 15},
        'description': 'Best of both → Optimal'
    },
}

STOCK_UNIVERSE_SMALL = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'PLTR', 'SNOW', 'CRWD', 'NET', 'DDOG', 'TEAM', 'DASH',
    'AMD', 'AVGO', 'QCOM', 'AMAT', 'KLAC', 'LRCX', 'TSM',
    'CRM', 'NOW', 'PANW', 'UBER', 'ABNB', 'COIN', 'ROKU',
]


def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def check_entry_filters(symbol, entry_date, hist, spy, filters):
    """Check if stock passes entry filters"""
    try:
        data = hist[hist.index <= entry_date].copy()
        if len(data) < 50:
            return False, 0

        close = data['Close']
        entry_price = close.iloc[-1]
        score = 0

        # RSI
        rsi = calculate_rsi(close).iloc[-1]
        if rsi >= filters['rsi']:
            score += 1
        else:
            return False, score

        # Momentum 7d
        if len(close) >= 7:
            mom = ((entry_price - close.iloc[-7]) / close.iloc[-7]) * 100
            if mom >= filters['mom_7d']:
                score += 1
            else:
                return False, score

        # RS 14d
        if len(close) >= 14:
            stock_ret = ((entry_price / close.iloc[-14]) - 1) * 100
            spy_at = spy[spy.index <= entry_date]
            if len(spy_at) >= 14:
                spy_ret = ((spy_at['Close'].iloc[-1] / spy_at['Close'].iloc[-14]) - 1) * 100
                rs = stock_ret - spy_ret
                if rs >= filters['rs_14d']:
                    score += 1
                else:
                    return False, score

        # MA20
        if len(close) >= 20:
            ma20 = close.rolling(20).mean().iloc[-1]
            dist = ((entry_price - ma20) / ma20) * 100
            if dist >= filters['ma20']:
                score += 1
            else:
                return False, score

        return True, score

    except:
        return False, 0


def simulate_trade_v2(symbol, entry_date, hist, spy, version_config):
    """Simulate trade with version-specific rules"""
    try:
        # Entry
        entry_idx = None
        for i, date in enumerate(hist.index):
            if date >= entry_date:
                entry_idx = i
                break

        if entry_idx is None:
            return None

        entry_price = hist['Close'].iloc[entry_idx]
        max_hold = version_config['exit_rules']['max_hold']

        if entry_idx + max_hold >= len(hist):
            return None

        # Holding period
        exit_idx = None
        exit_reason = 'MAX_HOLD'
        stop_loss = version_config['exit_rules']['stop_loss']
        score_threshold = version_config['exit_rules']['score_threshold']

        for day in range(1, max_hold + 1):
            check_idx = entry_idx + day
            if check_idx >= len(hist):
                break

            current_price = hist['Close'].iloc[check_idx]
            current_return = ((current_price - entry_price) / entry_price) * 100

            # Check stop loss
            if current_return <= stop_loss:
                exit_idx = check_idx
                exit_reason = 'STOP_LOSS'
                break

            # Check filter score (simplified - just check current state)
            # In reality, would recalculate all filters
            # For speed, we'll just use return as proxy
            if day >= 3 and current_return < -5:  # Likely failing filters
                exit_idx = check_idx
                exit_reason = 'FILTER_EXIT'
                break

        if exit_idx is None:
            exit_idx = min(entry_idx + max_hold, len(hist) - 1)

        exit_price = hist['Close'].iloc[exit_idx]
        actual_return = ((exit_price - entry_price) / entry_price) * 100

        # Max return
        holding = hist.iloc[entry_idx+1:exit_idx+1]
        max_high = holding['High'].max() if not holding.empty else exit_price
        max_return = ((max_high - entry_price) / entry_price) * 100

        return {
            'symbol': symbol,
            'actual_return': actual_return,
            'max_return': max_return,
            'exit_reason': exit_reason,
        }

    except:
        return None


def quick_backtest(version_name, config, stock_data, spy_data, entry_dates):
    """Quick backtest of a version"""
    trades = []

    for entry_date in entry_dates:
        for symbol, hist in stock_data.items():
            # Check entry
            passed, score = check_entry_filters(
                symbol, entry_date, hist, spy_data, config['entry_filters']
            )

            if not passed:
                continue

            # Simulate trade
            trade = simulate_trade_v2(symbol, entry_date, hist, spy_data, config)
            if trade:
                trades.append(trade)

    # Analysis
    if not trades:
        return None

    returns = [t['actual_return'] for t in trades]
    winners = [r for r in returns if r > 0]
    losers = [r for r in returns if r <= 0]

    return {
        'version': version_name,
        'total_trades': len(trades),
        'win_rate': len(winners) / len(trades) * 100 if trades else 0,
        'avg_return': np.mean(returns),
        'avg_winner': np.mean(winners) if winners else 0,
        'avg_loser': np.mean(losers) if losers else 0,
        'best': max(returns),
        'worst': min(returns),
        'expectancy': (len(winners)/len(trades) * np.mean(winners) +
                      len(losers)/len(trades) * np.mean(losers)) if trades else 0,
        'rr_ratio': abs(np.mean(winners) / np.mean(losers)) if losers and winners else 0,
    }


def main():
    print("=" * 100)
    print("🧪 TESTING ALL IMPROVEMENTS + BEAR MARKET")
    print("=" * 100)

    # Download data
    print("\n📥 Downloading data (this may take 2-3 minutes)...")

    # Period 1: Bull market (May-Nov 2025)
    end_bull = datetime(2025, 12, 24)
    start_bull = end_bull - timedelta(days=250)

    # Period 2: Bear market (2022 decline)
    end_bear = datetime(2022, 10, 12)  # Market bottom
    start_bear = datetime(2022, 1, 1)  # Start of decline

    print("\nBull Period: 2025")
    print("Bear Period: 2022 (Jan-Oct)")

    # Download
    spy = yf.Ticker('SPY')
    spy_bull = spy.history(start=start_bull, end=end_bull)
    spy_bear = spy.history(start=start_bear, end=end_bear)

    stock_data_bull = {}
    stock_data_bear = {}

    for symbol in STOCK_UNIVERSE_SMALL:
        try:
            ticker = yf.Ticker(symbol)
            hist_bull = ticker.history(start=start_bull, end=end_bull)
            hist_bear = ticker.history(start=start_bear, end=end_bear)

            if len(hist_bull) > 100:
                stock_data_bull[symbol] = hist_bull
            if len(hist_bear) > 100:
                stock_data_bear[symbol] = hist_bear
        except:
            pass

    print(f"✅ Bull market: {len(stock_data_bull)} stocks")
    print(f"✅ Bear market: {len(stock_data_bear)} stocks")

    # Generate entry points
    def generate_entries(spy_data):
        dates = spy_data.index
        entries = []
        idx = max(100, len(dates) - 200)
        while idx < len(dates) - 20:
            entries.append(dates[idx])
            idx += 4
        return entries

    entries_bull = generate_entries(spy_bull)
    entries_bear = generate_entries(spy_bear)

    print(f"\nBull entries: {len(entries_bull)}")
    print(f"Bear entries: {len(entries_bear)}")

    # Test all versions
    print("\n" + "=" * 100)
    print("🔬 TESTING VERSIONS IN BULL MARKET (2025)")
    print("=" * 100)

    results_bull = {}
    for version_id, config in VERSIONS.items():
        print(f"\nTesting {config['name']}...", end=' ')
        result = quick_backtest(version_id, config, stock_data_bull,
                               spy_bull, entries_bull)
        if result:
            results_bull[version_id] = result
            print(f"✅ {result['total_trades']} trades")
        else:
            print("❌ No trades")

    # Test in bear market
    print("\n" + "=" * 100)
    print("🐻 TESTING VERSIONS IN BEAR MARKET (2022)")
    print("=" * 100)

    results_bear = {}
    for version_id, config in VERSIONS.items():
        print(f"\nTesting {config['name']}...", end=' ')
        result = quick_backtest(version_id, config, stock_data_bear,
                               spy_bear, entries_bear)
        if result:
            results_bear[version_id] = result
            print(f"✅ {result['total_trades']} trades")
        else:
            print("❌ No trades")

    # Comparison
    print("\n\n" + "=" * 100)
    print("📊 COMPARISON TABLE")
    print("=" * 100)

    metrics = ['total_trades', 'win_rate', 'avg_return', 'expectancy',
               'rr_ratio', 'best', 'worst']

    # Bull market
    print("\n🐂 BULL MARKET (2025):")
    print("-" * 100)
    print(f"{'Version':<20} {'Trades':<8} {'WR%':<8} {'Avg%':<8} {'Exp%':<8} {'R:R':<8} {'Best%':<8} {'Worst%':<8}")
    print("-" * 100)

    for vid in VERSIONS.keys():
        if vid in results_bull:
            r = results_bull[vid]
            name = VERSIONS[vid]['name']
            print(f"{name:<20} {r['total_trades']:<8} {r['win_rate']:<8.1f} "
                  f"{r['avg_return']:<8.2f} {r['expectancy']:<8.2f} "
                  f"{r['rr_ratio']:<8.2f} {r['best']:<8.1f} {r['worst']:<8.1f}")

    # Bear market
    print("\n🐻 BEAR MARKET (2022):")
    print("-" * 100)
    print(f"{'Version':<20} {'Trades':<8} {'WR%':<8} {'Avg%':<8} {'Exp%':<8} {'R:R':<8} {'Best%':<8} {'Worst%':<8}")
    print("-" * 100)

    for vid in VERSIONS.keys():
        if vid in results_bear:
            r = results_bear[vid]
            name = VERSIONS[vid]['name']
            print(f"{name:<20} {r['total_trades']:<8} {r['win_rate']:<8.1f} "
                  f"{r['avg_return']:<8.2f} {r['expectancy']:<8.2f} "
                  f"{r['rr_ratio']:<8.2f} {r['best']:<8.1f} {r['worst']:<8.1f}")

    # Find best
    print("\n\n" + "=" * 100)
    print("🏆 WINNERS")
    print("=" * 100)

    # Best in bull
    if results_bull:
        best_bull = max(results_bull.items(),
                       key=lambda x: x[1]['expectancy'])
        print(f"\n🐂 Bull Market Champion: {VERSIONS[best_bull[0]]['name']}")
        print(f"   Expectancy: {best_bull[1]['expectancy']:+.2f}%")
        print(f"   Win Rate: {best_bull[1]['win_rate']:.1f}%")

    # Best in bear
    if results_bear:
        best_bear = max(results_bear.items(),
                       key=lambda x: x[1]['expectancy'])
        print(f"\n🐻 Bear Market Champion: {VERSIONS[best_bear[0]]['name']}")
        print(f"   Expectancy: {best_bear[1]['expectancy']:+.2f}%")
        print(f"   Win Rate: {best_bear[1]['win_rate']:.1f}%")

    # Overall best
    print("\n🎯 OVERALL RECOMMENDATION:")

    # Score each version
    scores = {}
    for vid in VERSIONS.keys():
        score = 0

        # Bull performance
        if vid in results_bull:
            if results_bull[vid]['win_rate'] >= 60:
                score += 2
            if results_bull[vid]['expectancy'] >= 3:
                score += 2
            if results_bull[vid]['rr_ratio'] >= 2:
                score += 2

        # Bear performance (important!)
        if vid in results_bear:
            if results_bear[vid]['expectancy'] > 0:  # Just positive!
                score += 3  # Extra weight
            if results_bear[vid]['win_rate'] >= 50:
                score += 2

        scores[vid] = score

    if scores:
        winner_vid = max(scores.items(), key=lambda x: x[1])[0]
        winner_name = VERSIONS[winner_vid]['name']
        winner_score = scores[winner_vid]

        print(f"\n✅ RECOMMENDED: {winner_name}")
        print(f"   Score: {winner_score}/11")

        if winner_vid in results_bull:
            print(f"\n   Bull Market:")
            print(f"   - Win Rate: {results_bull[winner_vid]['win_rate']:.1f}%")
            print(f"   - Expectancy: {results_bull[winner_vid]['expectancy']:+.2f}%")
            print(f"   - R:R: {results_bull[winner_vid]['rr_ratio']:.2f}:1")

        if winner_vid in results_bear:
            print(f"\n   Bear Market:")
            print(f"   - Win Rate: {results_bear[winner_vid]['win_rate']:.1f}%")
            print(f"   - Expectancy: {results_bear[winner_vid]['expectancy']:+.2f}%")
            print(f"   - R:R: {results_bear[winner_vid]['rr_ratio']:.2f}:1")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
