#!/usr/bin/env python3
"""
EXIT STRATEGY COMPARISON TEST

Tests 4 configurations:
1. Baseline (v3.7): Trail +3%, Lock 60%
2. Option A: Trail +2%, Lock 60% (earlier activation)
3. Option B: Trail +3%, Lock 70% (tighter lock)
4. Option A+B: Trail +2%, Lock 70% (both)

Goal: Find which exit strategy improvement helps without hurting
"""

import subprocess
import json
import re

# Test configurations
CONFIGS = [
    {"name": "Baseline (v3.7)", "activation": 3.0, "lock": 60},
    {"name": "Option A (+2%, 60%)", "activation": 2.0, "lock": 60},
    {"name": "Option B (+3%, 70%)", "activation": 3.0, "lock": 70},
    {"name": "Option A+B (+2%, 70%)", "activation": 2.0, "lock": 70},
]

def run_backtest(activation: float, lock: int) -> dict:
    """Run backtest with specific trailing config"""

    # Modify Config in STANDARD_BACKTEST.py temporarily
    with open('STANDARD_BACKTEST.py', 'r') as f:
        content = f.read()

    # Save original
    original = content

    # Replace values
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

    # Write modified version
    with open('STANDARD_BACKTEST.py', 'w') as f:
        f.write(content)

    try:
        # Run backtest
        result = subprocess.run(
            ['python3', 'STANDARD_BACKTEST.py'],
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout

        # Parse results
        total_return = re.search(r'Total Return: ([+-][\d.]+)%', output)
        win_rate = re.search(r'Winners: \d+ \(([\d.]+)%\)', output)
        monthly_avg = re.search(r'MONTHLY AVERAGE: ([+-][\d.]+)%', output)
        avg_win = re.search(r'Avg Win: ([+-][\d.]+)%', output)

        # Parse exit breakdown
        trail_stop = re.search(r'TRAIL_STOP\s+:\s+(\d+).*avg ([+-][\d.]+)%', output)
        stop_loss = re.search(r'STOP_LOSS\s+:\s+(\d+)', output)
        take_profit = re.search(r'TAKE_PROFIT\s+:\s+(\d+)', output)

        return {
            'total_return': float(total_return.group(1)) if total_return else 0,
            'win_rate': float(win_rate.group(1)) if win_rate else 0,
            'monthly_avg': float(monthly_avg.group(1)) if monthly_avg else 0,
            'avg_win': float(avg_win.group(1)) if avg_win else 0,
            'trail_stops': int(trail_stop.group(1)) if trail_stop else 0,
            'trail_avg': float(trail_stop.group(2)) if trail_stop else 0,
            'stop_losses': int(stop_loss.group(1)) if stop_loss else 0,
            'take_profits': int(take_profit.group(1)) if take_profit else 0,
        }
    finally:
        # Restore original
        with open('STANDARD_BACKTEST.py', 'w') as f:
            f.write(original)

def main():
    print("=" * 70)
    print("EXIT STRATEGY COMPARISON TEST")
    print("=" * 70)
    print()

    results = []

    for i, config in enumerate(CONFIGS, 1):
        print(f"\n[{i}/4] Testing: {config['name']}")
        print(f"      Trail Activation: +{config['activation']}%")
        print(f"      Trail Lock: {config['lock']}%")
        print("      Running backtest...")

        result = run_backtest(config['activation'], config['lock'])
        result['name'] = config['name']
        result['activation'] = config['activation']
        result['lock'] = config['lock']
        results.append(result)

        print(f"      Total Return: {result['total_return']:+.2f}%")
        print(f"      Win Rate: {result['win_rate']:.1f}%")

    # Print comparison table
    print("\n" + "=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)

    print(f"\n{'Config':<25} {'Return':>10} {'WinRate':>10} {'Monthly':>10} {'AvgWin':>10}")
    print("-" * 70)

    baseline = results[0]
    for r in results:
        diff = r['total_return'] - baseline['total_return']
        diff_str = f"({diff:+.1f}%)" if r != baseline else "(base)"
        print(f"{r['name']:<25} {r['total_return']:>+9.2f}% {r['win_rate']:>9.1f}% {r['monthly_avg']:>+9.2f}% {r['avg_win']:>+9.2f}%")

    print("\n" + "-" * 70)
    print("EXIT BREAKDOWN:")
    print(f"{'Config':<25} {'Trail#':>8} {'TrailAvg':>10} {'SL#':>8} {'TP#':>8}")
    print("-" * 70)
    for r in results:
        print(f"{r['name']:<25} {r['trail_stops']:>8} {r['trail_avg']:>+9.2f}% {r['stop_losses']:>8} {r['take_profits']:>8}")

    # Find best
    print("\n" + "=" * 70)
    best = max(results, key=lambda x: x['total_return'])
    print(f"BEST: {best['name']} with {best['total_return']:+.2f}% return")

    if best['name'] != 'Baseline (v3.7)':
        improvement = best['total_return'] - baseline['total_return']
        print(f"      Improvement over baseline: {improvement:+.2f}%")
    else:
        print("      Baseline is still best - no change needed")
    print("=" * 70)

    # Save results
    with open('exit_strategy_comparison.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to: exit_strategy_comparison.json")

if __name__ == "__main__":
    main()
