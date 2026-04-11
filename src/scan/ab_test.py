"""
A/B Test Runner — compare ml_filter vs morning_drive each day.

On each trigger, runs BOTH strategies, records picks from each to
journal with strategy name. After outcomes are filled, compares
actual WR per strategy over a time period.

Usage:
    python3 -m src.scan.ab_test run         # run both strategies now
    python3 -m src.scan.ab_test compare     # show comparison report
"""
import sys
from datetime import datetime
import pytz

from .engine import run_scan, format_result, STRATEGIES
from .journal import get_journal

ET = pytz.timezone('US/Eastern')


def run_both():
    """Run ml_filter and morning_drive back-to-back, record both to journal."""
    print("=" * 60)
    print(f"A/B test run at {datetime.now(ET).strftime('%H:%M:%S %A')}")
    print("=" * 60)

    for strat_name in ['ml_filter', 'morning_drive']:
        print(f"\n── {strat_name} ──")
        result = run_scan(strat_name)
        print(format_result(result))

    print("\nBoth strategies recorded to journal.")
    print("Run outcome_updater after close to fill in results.")
    print("Run 'ab_test compare' to see WR comparison.")


def compare(days: int = 30):
    """Compare ml_filter vs morning_drive actual WR over last N days."""
    journal = get_journal()
    report = journal.report(days=days)

    if not report:
        print("No outcomes recorded yet. Run outcome_updater first.")
        return

    print(f"\n=== A/B Comparison (last {days} days) ===\n")
    print(f"{'Strategy':20s} {'Bucket':20s} {'N':>5s} {'ActualWR':>9s} {'ExpWR':>7s} {'Drift':>7s} {'AvgPnL':>8s}")
    print("-" * 90)

    for row in sorted(report, key=lambda r: (r['strategy'], r['bucket'] or '')):
        strat = row['strategy']
        bucket = row['bucket'] or '-'
        n = row['n']
        awr = row['actual_wr']
        ewr = row['expected_wr']
        drift = row['drift']
        pnl = row['avg_pnl']
        print(f"{strat:20s} {bucket:20s} {n:>5d} {awr:>8.1f}% {ewr:>6.1f}% {drift:>+6.1f}% {pnl:>+7.3f}%")

    # Aggregate by strategy
    agg = {}
    for row in report:
        s = row['strategy']
        if s not in agg:
            agg[s] = {'n': 0, 'wins': 0, 'pnl_sum': 0}
        agg[s]['n'] += row['n']
        agg[s]['wins'] += row['wins']
        agg[s]['pnl_sum'] += (row['avg_pnl'] * row['n'])

    print(f"\n=== Strategy summary ===")
    print(f"{'Strategy':20s} {'Total N':>8s} {'Overall WR':>12s} {'Avg PnL':>10s}")
    for s, data in sorted(agg.items()):
        n = data['n']
        wr = data['wins'] / n * 100 if n > 0 else 0
        avg = data['pnl_sum'] / n if n > 0 else 0
        print(f"{s:20s} {n:>8d} {wr:>11.1f}% {avg:>+9.3f}%")


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if cmd == 'compare':
        days = 30
        for arg in sys.argv[2:]:
            if arg.startswith('--days='):
                days = int(arg.split('=')[1])
        compare(days)
    else:
        run_both()
