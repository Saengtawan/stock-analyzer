#!/usr/bin/env python3
"""
REJECTED SIGNAL ANALYSIS TOOL v1.0
===================================

Analyzes rejected signal outcomes to determine filter effectiveness.

Answers questions:
1. Should we buy EARNINGS day=0 stocks? (EARNINGS_REJECT analysis)
2. Is STOCK_D filter too strict? (STOCK_D_REJECT analysis)
3. Is min_score appropriate? (SCORE_REJECT analysis)
4. Are RSI/GAP/MOM filters removing good opportunities?

Usage:
    python3 src/batch/analyze_rejected_signals.py
    python3 src/batch/analyze_rejected_signals.py --min-samples 30
    python3 src/batch/analyze_rejected_signals.py --reject-type EARNINGS_REJECT
"""

import argparse
import json
import os
from datetime import datetime
from typing import Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_all_rejected_outcomes() -> List[Dict]:
    """Load all rejected outcome files."""
    outcomes_dir = os.path.join(PROJECT_ROOT, 'outcomes')
    if not os.path.exists(outcomes_dir):
        return []

    all_outcomes = []
    for filename in os.listdir(outcomes_dir):
        if filename.startswith('rejected_outcomes_') and filename.endswith('.json'):
            filepath = os.path.join(outcomes_dir, filename)
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    all_outcomes.extend(data)
            except Exception as e:
                print(f"Warning: Failed to load {filename}: {e}")

    return all_outcomes


def analyze_reject_type(outcomes: List[Dict], reject_type: str, min_samples: int = 10):
    """Analyze a specific rejection type."""
    # Filter for this reject type with complete data
    data = [
        o for o in outcomes
        if o.get('reject_type') == reject_type
        and o.get('outcome_1d') is not None
        and o.get('outcome_5d') is not None
    ]

    if len(data) < min_samples:
        print(f"\n{reject_type}:")
        print(f"  ⚠️  Insufficient data: {len(data)} samples (need {min_samples})")
        return None

    # Calculate statistics
    avg_1d = sum(o['outcome_1d'] for o in data) / len(data)
    avg_5d = sum(o['outcome_5d'] for o in data) / len(data)

    wins_1d = sum(1 for o in data if o['outcome_1d'] > 0)
    wins_5d = sum(1 for o in data if o['outcome_5d'] > 0)

    win_rate_1d = 100 * wins_1d / len(data)
    win_rate_5d = 100 * wins_5d / len(data)

    # Max gain/loss
    max_gain = max(o['outcome_max_gain_5d'] for o in data if o['outcome_max_gain_5d'])
    max_dd = min(o['outcome_max_dd_5d'] for o in data if o['outcome_max_dd_5d'])

    # By sector (if available)
    by_sector = {}
    for o in data:
        sector = o.get('sector', 'Unknown')
        if sector not in by_sector:
            by_sector[sector] = []
        by_sector[sector].append(o)

    # Decision criteria
    # Strong filter: Low win rate (<50%) OR low avg return (<1%)
    # Weak filter: High win rate (>60%) AND high avg return (>1.5%)
    is_strong_filter = win_rate_1d < 50 or avg_1d < 1.0
    is_weak_filter = win_rate_1d > 60 and avg_1d > 1.5

    print(f"\n{reject_type}:")
    print(f"  Sample size: {len(data)}")
    print(f"  1d performance: {avg_1d:+.2f}% avg, {win_rate_1d:.1f}% win rate")
    print(f"  5d performance: {avg_5d:+.2f}% avg, {win_rate_5d:.1f}% win rate")
    print(f"  5d range: {max_dd:+.2f}% worst → {max_gain:+.2f}% best")

    if len(by_sector) > 1:
        print(f"  By sector:")
        for sector in sorted(by_sector.keys(), key=lambda s: len(by_sector[s]), reverse=True)[:5]:
            sector_data = by_sector[sector]
            sector_avg = sum(o['outcome_1d'] for o in sector_data) / len(sector_data)
            print(f"    {sector}: {len(sector_data)} samples, {sector_avg:+.2f}% avg")

    # Recommendation
    if is_strong_filter:
        print(f"  ✅ RECOMMENDATION: KEEP filter (rejecting weak signals)")
    elif is_weak_filter:
        print(f"  ⚠️  RECOMMENDATION: LOOSEN filter (rejecting good signals)")
    else:
        print(f"  ℹ️  RECOMMENDATION: MONITOR (borderline performance)")

    return {
        'reject_type': reject_type,
        'sample_size': len(data),
        'avg_1d': avg_1d,
        'avg_5d': avg_5d,
        'win_rate_1d': win_rate_1d,
        'win_rate_5d': win_rate_5d,
        'max_gain': max_gain,
        'max_dd': max_dd,
        'recommendation': 'KEEP' if is_strong_filter else ('LOOSEN' if is_weak_filter else 'MONITOR'),
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze rejected signal outcomes")
    parser.add_argument('--min-samples', type=int, default=10, help='Minimum samples for analysis')
    parser.add_argument('--reject-type', type=str, help='Analyze specific reject type only')
    args = parser.parse_args()

    print("=" * 70)
    print("REJECTED SIGNAL ANALYSIS")
    print("=" * 70)

    # Load all rejected outcomes
    outcomes = load_all_rejected_outcomes()

    if not outcomes:
        print("\nNo rejected outcome data found.")
        print("Run: python3 src/batch/outcome_tracker.py --rejected-only")
        return

    print(f"\nTotal rejected outcomes loaded: {len(outcomes)}")

    # Get all rejection types
    reject_types = set(o.get('reject_type') for o in outcomes if o.get('reject_type'))
    print(f"Rejection types found: {', '.join(sorted(reject_types))}")

    # Analyze each type (or specific type)
    results = []
    if args.reject_type:
        result = analyze_reject_type(outcomes, args.reject_type, args.min_samples)
        if result:
            results.append(result)
    else:
        for reject_type in sorted(reject_types):
            result = analyze_reject_type(outcomes, reject_type, args.min_samples)
            if result:
                results.append(result)

    # Summary
    if results:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        keep_filters = [r for r in results if r['recommendation'] == 'KEEP']
        loosen_filters = [r for r in results if r['recommendation'] == 'LOOSEN']
        monitor_filters = [r for r in results if r['recommendation'] == 'MONITOR']

        if keep_filters:
            print(f"\n✅ KEEP ({len(keep_filters)}): Filters working correctly")
            for r in keep_filters:
                print(f"   - {r['reject_type']}: {r['win_rate_1d']:.1f}% win, {r['avg_1d']:+.2f}% avg")

        if loosen_filters:
            print(f"\n⚠️  LOOSEN ({len(loosen_filters)}): Filters too strict")
            for r in loosen_filters:
                print(f"   - {r['reject_type']}: {r['win_rate_1d']:.1f}% win, {r['avg_1d']:+.2f}% avg")

        if monitor_filters:
            print(f"\nℹ️  MONITOR ({len(monitor_filters)}): Borderline performance")
            for r in monitor_filters:
                print(f"   - {r['reject_type']}: {r['win_rate_1d']:.1f}% win, {r['avg_1d']:+.2f}% avg")

    print("\n" + "=" * 70)


if __name__ == '__main__':
    main()
