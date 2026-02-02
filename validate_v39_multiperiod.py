#!/usr/bin/env python3
"""
V3.9 MULTI-PERIOD VALIDATION

Tests v3.9 exit strategy (Trail +2%, Lock 70%) vs baseline (Trail +3%, Lock 60%)
across 3 different time periods to confirm not overfitting.

Periods:
1. Recent 2.5 months (Nov 15 - Jan 31)
2. Mid period 2.5 months (Sep 1 - Nov 14)
3. Earlier period 2.5 months (Jun 15 - Aug 31)
"""

import subprocess
import json
import re
from datetime import datetime, timedelta

# Test configurations
CONFIGS = {
    "baseline": {"activation": 3.0, "lock": 60},
    "v3.9": {"activation": 2.0, "lock": 70}
}

# Test periods (end_date, months_back for that period)
PERIODS = [
    {"name": "Period 1 (Nov-Jan)", "end": "2026-01-31", "start": "2025-11-15"},
    {"name": "Period 2 (Sep-Nov)", "end": "2025-11-14", "start": "2025-09-01"},
    {"name": "Period 3 (Jun-Aug)", "end": "2025-08-31", "start": "2025-06-15"},
]

def modify_backtest_config(activation: float, lock: int, start_date: str, end_date: str):
    """Modify STANDARD_BACKTEST.py for specific config and period"""

    with open('STANDARD_BACKTEST.py', 'r') as f:
        content = f.read()

    # Replace trailing config
    content = re.sub(
        r'TRAIL_ACTIVATION_PCT = [\d.]+',
        f'TRAIL_ACTIVATION_PCT = {activation}',
        content
    )
    content = re.sub(
        r'TRAIL_PERCENT = \d+',
        f'TRAIL_PERCENT = {lock}',
        content
    )

    # Calculate months back from end_date to start_date
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    months_back = round((end_dt - start_dt).days / 30)

    # Replace MONTHS_BACK
    content = re.sub(
        r'MONTHS_BACK = \d+',
        f'MONTHS_BACK = {months_back}',
        content
    )

    # Inject end_date override after Config class definition
    # Look for specific date override pattern or add it
    if 'BACKTEST_END_DATE' in content:
        content = re.sub(
            r"BACKTEST_END_DATE = ['\"][\d-]+['\"]",
            f"BACKTEST_END_DATE = '{end_date}'",
            content
        )
    else:
        # Add it after MONTHS_BACK line
        content = re.sub(
            r'(MONTHS_BACK = \d+)',
            f"\\1\n    BACKTEST_END_DATE = '{end_date}'",
            content
        )

    with open('STANDARD_BACKTEST.py', 'w') as f:
        f.write(content)

    return content

def run_backtest() -> dict:
    """Run backtest and parse results"""
    try:
        result = subprocess.run(
            ['python3', 'STANDARD_BACKTEST.py'],
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout

        # Parse results
        total_return = re.search(r'Total Return: ([+-]?[\d.]+)%', output)
        win_rate = re.search(r'Winners: \d+ \(([\d.]+)%\)', output)
        monthly_avg = re.search(r'MONTHLY AVERAGE: ([+-]?[\d.]+)%', output)

        return {
            'total_return': float(total_return.group(1)) if total_return else 0,
            'win_rate': float(win_rate.group(1)) if win_rate else 0,
            'monthly_avg': float(monthly_avg.group(1)) if monthly_avg else 0,
        }
    except Exception as e:
        print(f"Error: {e}")
        return {'total_return': 0, 'win_rate': 0, 'monthly_avg': 0}

def main():
    print("=" * 70)
    print("V3.9 MULTI-PERIOD VALIDATION")
    print("=" * 70)
    print()
    print("Goal: Confirm v3.9 beats baseline across multiple time periods")
    print("      (not overfitting to one specific period)")
    print()

    # Save original file
    with open('STANDARD_BACKTEST.py', 'r') as f:
        original_content = f.read()

    results = []

    try:
        for period in PERIODS:
            print(f"\n{'='*70}")
            print(f"Testing: {period['name']}")
            print(f"         {period['start']} to {period['end']}")
            print(f"{'='*70}")

            period_results = {"period": period['name']}

            for config_name, config in CONFIGS.items():
                print(f"\n  [{config_name}] Trail +{config['activation']}%, Lock {config['lock']}%")
                print(f"       Running backtest...")

                modify_backtest_config(
                    config['activation'],
                    config['lock'],
                    period['start'],
                    period['end']
                )

                result = run_backtest()
                period_results[config_name] = result

                print(f"       Return: {result['total_return']:+.2f}%")
                print(f"       Win Rate: {result['win_rate']:.1f}%")

            # Calculate improvement
            improvement = period_results['v3.9']['total_return'] - period_results['baseline']['total_return']
            period_results['improvement'] = improvement

            if improvement > 0:
                print(f"\n  ✅ v3.9 WINS by {improvement:+.2f}%")
            else:
                print(f"\n  ❌ Baseline wins by {-improvement:+.2f}%")

            results.append(period_results)

    finally:
        # Restore original
        with open('STANDARD_BACKTEST.py', 'w') as f:
            f.write(original_content)

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    print(f"\n{'Period':<25} {'Baseline':>12} {'v3.9':>12} {'Diff':>10}")
    print("-" * 70)

    wins = 0
    for r in results:
        base_ret = r['baseline']['total_return']
        v39_ret = r['v3.9']['total_return']
        diff = r['improvement']

        indicator = "✅" if diff > 0 else "❌"
        print(f"{r['period']:<25} {base_ret:>+11.2f}% {v39_ret:>+11.2f}% {diff:>+9.2f}% {indicator}")

        if diff > 0:
            wins += 1

    print("-" * 70)
    print(f"\nv3.9 wins: {wins}/{len(results)} periods")

    if wins == len(results):
        print("\n✅ VALIDATED: v3.9 beats baseline in ALL periods")
        print("   → Safe to deploy to production")
    elif wins > len(results) / 2:
        print(f"\n⚠️  PARTIAL: v3.9 wins {wins}/{len(results)} periods")
        print("   → Generally better but not consistent")
    else:
        print(f"\n❌ FAILED: v3.9 only wins {wins}/{len(results)} periods")
        print("   → May be overfitting, reconsider")

    # Save results
    with open('v39_validation_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to: v39_validation_results.json")

if __name__ == "__main__":
    main()
