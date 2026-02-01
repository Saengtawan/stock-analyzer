#!/usr/bin/env python3
"""
Extended Backtest - Use actual scan results from recent period
Test on known good entry points
"""

import sys
sys.path.append('src')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from exit_rules import ExitRulesEngine, FixedTPSLRules


def backtest_single_strategy(strategy_name, exit_engine, test_cases):
    """Backtest a single strategy on multiple test cases"""

    all_trades = []

    print(f"\n{'='*100}")
    print(f"📊 {strategy_name}")
    print(f"{'='*100}\n")

    for case in test_cases:
        symbol = case['symbol']
        entry_date = pd.Timestamp(case['entry_date']).tz_localize('America/New_York')

        # Download data
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=entry_date - timedelta(days=60),
                                 end=entry_date + timedelta(days=30))

            if hist.empty:
                continue

            # Get entry price
            entry_idx = None
            for i, date in enumerate(hist.index):
                if date >= entry_date:
                    entry_idx = i
                    break

            if entry_idx is None:
                continue

            entry_price = hist['Close'].iloc[entry_idx]
            entry_actual = hist.index[entry_idx]

            # Simulate holding
            exit_idx = None
            exit_reason = None
            max_days = 20 if 'Filter' in strategy_name else 14

            for day in range(1, max_days + 1):
                check_idx = entry_idx + day
                if check_idx >= len(hist):
                    break

                position = {
                    'symbol': symbol,
                    'entry_date': entry_actual.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'days_held': day,
                }

                check_date = hist.index[check_idx]

                # Check exit
                if 'Filter' in strategy_name:
                    spy = yf.Ticker('SPY')
                    spy_hist = spy.history(start=entry_date - timedelta(days=60),
                                          end=entry_date + timedelta(days=30))
                    should_exit, reason, details = exit_engine.check_exit(
                        position, check_date.strftime('%Y-%m-%d'), hist, spy_hist
                    )
                else:
                    should_exit, reason, details = exit_engine.check_exit(
                        position, check_date.strftime('%Y-%m-%d'), hist
                    )

                if should_exit:
                    exit_idx = check_idx
                    exit_reason = reason
                    break

            # If no exit, hold to max
            if exit_idx is None:
                exit_idx = min(entry_idx + max_days, len(hist) - 1)
                exit_reason = 'MAX_HOLD'

            exit_price = hist['Close'].iloc[exit_idx]
            exit_date = hist.index[exit_idx]
            days_held = exit_idx - entry_idx

            # Calculate P&L
            actual_return = ((exit_price - entry_price) / entry_price) * 100

            # Max return
            holding = hist.iloc[entry_idx+1:exit_idx+1]
            max_high = holding['High'].max() if not holding.empty else exit_price
            max_return = ((max_high - entry_price) / entry_price) * 100

            trade = {
                'symbol': symbol,
                'entry_date': entry_actual,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'actual_return': actual_return,
                'max_return': max_return,
                'days_held': days_held,
                'exit_reason': exit_reason,
            }

            all_trades.append(trade)

            status = "✅" if actual_return > 0 else "❌"
            print(f"{status} {symbol:6s}: Entry ${entry_price:.2f} → Exit ${exit_price:.2f} "
                  f"({actual_return:+.1f}%, max {max_return:+.1f}%) "
                  f"Day {days_held} [{exit_reason}]")

        except Exception as e:
            print(f"⚠️  {symbol}: Error - {e}")
            continue

    return all_trades


def analyze_and_compare():
    """Analyze and compare strategies"""

    # Test cases - stocks we know passed filters recently
    test_cases = [
        # From Dec 5, 2025 diagnostic (9 stocks that passed)
        {'symbol': 'META', 'entry_date': '2025-12-05'},
        {'symbol': 'TSLA', 'entry_date': '2025-12-05'},
        {'symbol': 'PLTR', 'entry_date': '2025-12-05'},
        {'symbol': 'TEAM', 'entry_date': '2025-12-05'},
        {'symbol': 'DASH', 'entry_date': '2025-12-05'},
        {'symbol': 'QCOM', 'entry_date': '2025-12-05'},
        {'symbol': 'AMAT', 'entry_date': '2025-12-05'},
        {'symbol': 'KLAC', 'entry_date': '2025-12-05'},
        {'symbol': 'ABNB', 'entry_date': '2025-12-05'},

        # From earlier successful picks (if had data)
        {'symbol': 'LRCX', 'entry_date': '2025-11-25'},
        {'symbol': 'AVGO', 'entry_date': '2025-11-25'},
        {'symbol': 'GOOGL', 'entry_date': '2025-11-20'},
    ]

    print("=" * 100)
    print("🔬 EXTENDED BACKTEST COMPARISON")
    print("=" * 100)
    print(f"\nTesting {len(test_cases)} positions")
    print("Entry dates: Recent signals that passed filters\n")

    # Scenario A: Fixed TP/SL
    fixed_rules = FixedTPSLRules(take_profit=5.0, stop_loss=-8.0, max_hold=14)
    trades_a = backtest_single_strategy("SCENARIO A: Fixed TP 5%, SL -8%",
                                       fixed_rules, test_cases)

    # Scenario B: Filter-based
    filter_rules = ExitRulesEngine()
    trades_b = backtest_single_strategy("SCENARIO B: Filter-based Dynamic Exit",
                                       filter_rules, test_cases)

    # Analysis
    def analyze(trades, name):
        if not trades:
            return {}

        returns = [t['actual_return'] for t in trades]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r <= 0]

        stats = {
            'total': len(trades),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': len(winners) / len(trades) * 100,
            'avg_return': np.mean(returns),
            'avg_winner': np.mean(winners) if winners else 0,
            'avg_loser': np.mean(losers) if losers else 0,
            'best': max(returns),
            'worst': min(returns),
            'total_pnl': sum([r * 10 for r in returns]),  # $1000 per trade
            'avg_days': np.mean([t['days_held'] for t in trades]),
        }

        stats['expectancy'] = (stats['winners']/stats['total'] * stats['avg_winner'] +
                               stats['losers']/stats['total'] * stats['avg_loser'])

        print(f"\n{'='*100}")
        print(f"📊 {name} - SUMMARY")
        print(f"{'='*100}")
        print(f"\n📈 Performance:")
        print(f"   Trades: {stats['total']}")
        print(f"   Win Rate: {stats['win_rate']:.1f}% ({stats['winners']}/{stats['total']})")
        print(f"   Avg Return: {stats['avg_return']:+.2f}%")
        print(f"   Expectancy: {stats['expectancy']:+.2f}%")
        print(f"\n💰 Returns:")
        print(f"   Winners Avg: {stats['avg_winner']:+.2f}%")
        print(f"   Losers Avg: {stats['avg_loser']:+.2f}%")
        print(f"   Best: {stats['best']:+.2f}%")
        print(f"   Worst: {stats['worst']:+.2f}%")
        print(f"\n💵 P&L ($1000/trade):")
        print(f"   Total: ${stats['total_pnl']:+,.2f}")
        print(f"\n⏱️  Timing:")
        print(f"   Avg Hold: {stats['avg_days']:.1f} days")

        # Exit reasons
        reasons = {}
        for t in trades:
            r = t['exit_reason']
            reasons[r] = reasons.get(r, 0) + 1

        print(f"\n🚪 Exit Reasons:")
        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"   {reason}: {count} ({count/stats['total']*100:.1f}%)")

        return stats

    stats_a = analyze(trades_a, "SCENARIO A")
    stats_b = analyze(trades_b, "SCENARIO B")

    # Comparison
    if stats_a and stats_b:
        print(f"\n\n{'='*100}")
        print("🏆 HEAD-TO-HEAD COMPARISON")
        print(f"{'='*100}\n")

        comparisons = [
            ('Win Rate', 'win_rate', '%', 'higher'),
            ('Avg Return', 'avg_return', '%', 'higher'),
            ('Expectancy', 'expectancy', '%', 'higher'),
            ('Total P&L', 'total_pnl', '$', 'higher'),
            ('Best Trade', 'best', '%', 'higher'),
            ('Worst Trade', 'worst', '%', 'higher'),
            ('Avg Hold Days', 'avg_days', 'd', 'lower'),
        ]

        score_a = 0
        score_b = 0

        print(f"{'Metric':<20} {'Fixed TP/SL':<20} {'Filter Exit':<20} {'Better':<10}")
        print("-" * 75)

        for name, key, unit, direction in comparisons:
            val_a = stats_a[key]
            val_b = stats_b[key]

            if direction == 'higher':
                better = 'B ✅' if val_b > val_a else 'A ✅'
                if val_b > val_a:
                    score_b += 1
                else:
                    score_a += 1
            else:
                better = 'B ✅' if val_b < val_a else 'A ✅'
                if val_b < val_a:
                    score_b += 1
                else:
                    score_a += 1

            if unit == '$':
                str_a = f"${val_a:+,.0f}"
                str_b = f"${val_b:+,.0f}"
            elif unit in ['%', 'd']:
                str_a = f"{val_a:+.1f}{unit}"
                str_b = f"{val_b:+.1f}{unit}"
            else:
                str_a = f"{val_a:.1f}"
                str_b = f"{val_b:.1f}"

            print(f"{name:<20} {str_a:<20} {str_b:<20} {better:<10}")

        print(f"\n{'='*100}")
        print(f"🏆 FINAL SCORE: Scenario A ({score_a}) vs Scenario B ({score_b})")

        if score_b > score_a:
            diff = stats_b['total_pnl'] - stats_a['total_pnl']
            print(f"\n✅ SCENARIO B WINS!")
            print(f"   Filter-based exit is BETTER by ${diff:+,.0f}")
            print(f"   Key advantage: {stats_b['expectancy'] - stats_a['expectancy']:+.2f}% better expectancy")
        elif score_a > score_b:
            diff = stats_a['total_pnl'] - stats_b['total_pnl']
            print(f"\n⚠️  SCENARIO A WINS")
            print(f"   Fixed TP/SL is better by ${diff:+,.0f}")
        else:
            print(f"\n🤝 TIE!")

        print(f"{'='*100}\n")


if __name__ == "__main__":
    analyze_and_compare()
