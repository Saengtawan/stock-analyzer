#!/usr/bin/env python3
"""
V3.9 SENSITIVITY TEST

Tests 9 combinations around the chosen parameters:
- Trail Activation: 1.5%, 2.0%, 2.5%
- Trail Lock: 65%, 70%, 75%

Goal: Confirm 2%/70% is a "wide sweet spot" not a "lucky point"
"""

import subprocess
import json
import re

# Grid parameters
ACTIVATIONS = [1.5, 2.0, 2.5]
LOCKS = [65, 70, 75]

def run_backtest(activation: float, lock: int) -> dict:
    """Run backtest with specific config"""

    # Read and modify STANDARD_BACKTEST.py
    with open('STANDARD_BACKTEST.py', 'r') as f:
        content = f.read()
    original = content

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

    with open('STANDARD_BACKTEST.py', 'w') as f:
        f.write(content)

    try:
        result = subprocess.run(
            ['python3', 'STANDARD_BACKTEST.py'],
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout

        total_return = re.search(r'Total Return: ([+-]?[\d.]+)%', output)
        win_rate = re.search(r'Winners: \d+ \(([\d.]+)%\)', output)
        monthly_avg = re.search(r'MONTHLY AVERAGE: ([+-]?[\d.]+)%', output)

        # Parse monthly breakdown for consistency check
        monthly_lines = re.findall(r'(\d{4}-\d{2})\s+\d+\s+[\d.]+%\s+([+-]?[\d.]+)%', output)
        positive_months = sum(1 for _, pnl in monthly_lines if float(pnl) > 0)
        total_months = len(monthly_lines)

        return {
            'total_return': float(total_return.group(1)) if total_return else 0,
            'win_rate': float(win_rate.group(1)) if win_rate else 0,
            'monthly_avg': float(monthly_avg.group(1)) if monthly_avg else 0,
            'positive_months': positive_months,
            'total_months': total_months,
        }
    finally:
        with open('STANDARD_BACKTEST.py', 'w') as f:
            f.write(original)

def main():
    print("=" * 70)
    print("V3.9 SENSITIVITY TEST")
    print("=" * 70)
    print()
    print("Testing 9 combinations around 2%/70%:")
    print("  Activation: 1.5%, 2.0%, 2.5%")
    print("  Lock: 65%, 70%, 75%")
    print()
    print("Goal: Confirm wide sweet spot (not lucky point)")
    print()

    results = []
    total = len(ACTIVATIONS) * len(LOCKS)
    count = 0

    for activation in ACTIVATIONS:
        for lock in LOCKS:
            count += 1
            print(f"[{count}/{total}] Testing: +{activation}% / {lock}%...", end=" ", flush=True)

            result = run_backtest(activation, lock)
            result['activation'] = activation
            result['lock'] = lock
            results.append(result)

            print(f"Return: {result['total_return']:+.2f}%, WR: {result['win_rate']:.1f}%")

    # Sort by return
    results.sort(key=lambda x: x['total_return'], reverse=True)

    # Print results table
    print("\n" + "=" * 70)
    print("SENSITIVITY TEST RESULTS")
    print("=" * 70)

    print(f"\n{'Activation':<12} {'Lock':<8} {'Return':>10} {'WinRate':>10} {'Monthly':>10} {'Months+':>10}")
    print("-" * 70)

    for r in results:
        marker = " ⭐" if r['activation'] == 2.0 and r['lock'] == 70 else ""
        print(f"+{r['activation']:.1f}%{'':<7} {r['lock']}%{'':<4} {r['total_return']:>+9.2f}% {r['win_rate']:>9.1f}% {r['monthly_avg']:>+9.2f}% {r['positive_months']}/{r['total_months']}{marker}")

    # Analysis
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    # Check if 2%/70% is in top 3
    top3 = results[:3]
    chosen = next((r for r in results if r['activation'] == 2.0 and r['lock'] == 70), None)
    chosen_rank = next((i+1 for i, r in enumerate(results) if r['activation'] == 2.0 and r['lock'] == 70), 0)

    print(f"\nChosen config (2%/70%) rank: #{chosen_rank} of 9")

    # Check variance around chosen
    returns = [r['total_return'] for r in results]
    avg_return = sum(returns) / len(returns)
    min_return = min(returns)
    max_return = max(returns)

    print(f"\nReturn range: {min_return:+.2f}% to {max_return:+.2f}%")
    print(f"Average: {avg_return:+.2f}%")

    # Count how many configs are "good" (>+15%)
    good_configs = [r for r in results if r['total_return'] >= 15]
    print(f"\nConfigs with return >= +15%: {len(good_configs)}/9")

    # Verdict
    print("\n" + "-" * 70)
    if len(good_configs) >= 6:
        print("✅ ROBUST: Wide sweet spot - most configs perform well")
        print("   Result is NOT overfitting to specific parameters")
    elif len(good_configs) >= 4:
        print("⚠️  MODERATE: Some sensitivity to parameters")
        print("   2%/70% appears to be in a good region")
    else:
        print("❌ FRAGILE: High sensitivity to parameters")
        print("   May be overfitting - proceed with caution")

    # Monthly consistency check
    print("\n" + "-" * 70)
    print("MONTHLY CONSISTENCY:")
    if chosen:
        print(f"  Positive months: {chosen['positive_months']}/{chosen['total_months']}")
        if chosen['positive_months'] >= chosen['total_months'] - 1:
            print("  ✅ Very consistent (at most 1 negative month)")
        elif chosen['positive_months'] >= chosen['total_months'] * 0.7:
            print("  ⚠️  Moderately consistent")
        else:
            print("  ❌ Inconsistent - check monthly breakdown")

    # Save results
    with open('sensitivity_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to: sensitivity_test_results.json")

if __name__ == "__main__":
    main()
