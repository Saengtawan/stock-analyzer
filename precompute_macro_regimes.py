#!/usr/bin/env python3
"""
Pre-compute Macro Regimes for 2025
===================================

Run macro detection ONCE for all dates and save to JSON.
Backtest will load from file = fast + reliable!
"""

import json
from datetime import datetime, timedelta
from src.macro_regime_detector import MacroRegimeDetector
import time

def precompute_macro_regimes(start_date: str, end_date: str, output_file: str):
    """Pre-compute macro regimes for date range"""

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    detector = MacroRegimeDetector()
    regimes = {}

    print("=" * 80)
    print("🔧 PRE-COMPUTING MACRO REGIMES")
    print("=" * 80)
    print(f"Period: {start_date} to {end_date}")
    print(f"Output: {output_file}")
    print()

    # Compute once per week (not every day)
    current_date = start
    week_count = 0

    while current_date <= end:
        week_key = current_date.strftime("%Y-W%W")

        # Skip if already computed this week
        if week_key in regimes:
            current_date += timedelta(days=1)
            continue

        week_count += 1
        print(f"Computing week {week_key} ({current_date.strftime('%Y-%m-%d')})...", end=" ")

        try:
            # Get macro regime
            macro = detector.get_macro_regime(current_date)

            # Convert to serializable format
            regime_data = {
                'risk_on': macro['risk_on'],
                'risk_score': macro['risk_score'],
                'fed_stance': macro['fed_stance'],
                'market_health': macro['market_health'],
                'sector_stage': macro['sector_stage'],
            }

            regimes[week_key] = regime_data

            status = "✅" if macro['risk_on'] else "❌"
            print(f"{status} {macro['sector_stage']}, Risk: {macro['risk_score']}/3")

            # Small delay to avoid rate limiting
            time.sleep(1)

        except Exception as e:
            print(f"❌ ERROR: {e}")
            # If error, mark as UNKNOWN
            regimes[week_key] = {
                'risk_on': False,
                'risk_score': 0,
                'fed_stance': 'UNKNOWN',
                'market_health': 'UNKNOWN',
                'sector_stage': 'UNKNOWN',
            }

        # Move to next week
        current_date += timedelta(days=7)

    # Apply fallback for UNKNOWN weeks
    print()
    print("=" * 80)
    print("🔄 APPLYING FALLBACK FOR UNKNOWN WEEKS")
    print("=" * 80)

    week_keys = sorted(regimes.keys())
    for i, week_key in enumerate(week_keys):
        regime = regimes[week_key]

        if regime['sector_stage'] == 'UNKNOWN' and i > 0:
            # Use previous week as fallback
            prev_week_key = week_keys[i-1]
            prev_regime = regimes[prev_week_key]

            if prev_regime['sector_stage'] != 'UNKNOWN':
                print(f"Week {week_key}: Using {prev_week_key} fallback")
                print(f"  {prev_regime['sector_stage']}, Risk: {prev_regime['risk_score']}/3")
                regimes[week_key] = prev_regime.copy()

    # Save to file
    print()
    print("=" * 80)
    print("💾 SAVING TO FILE")
    print("=" * 80)

    output = {
        'generated_at': datetime.now().isoformat(),
        'period': {
            'start': start_date,
            'end': end_date,
        },
        'total_weeks': len(regimes),
        'regimes': regimes,
    }

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"✅ Saved {len(regimes)} weeks to {output_file}")
    print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    risk_on_weeks = sum(1 for r in regimes.values() if r['risk_on'])
    risk_off_weeks = len(regimes) - risk_on_weeks

    print(f"Total Weeks: {len(regimes)}")
    print(f"RISK_ON:  {risk_on_weeks} ({risk_on_weeks/len(regimes)*100:.1f}%)")
    print(f"RISK_OFF: {risk_off_weeks} ({risk_off_weeks/len(regimes)*100:.1f}%)")
    print()

    # Show breakdown by stage
    stages = {}
    for r in regimes.values():
        stage = r['sector_stage']
        stages[stage] = stages.get(stage, 0) + 1

    print("Sector Stages:")
    for stage, count in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"  {stage:15s}: {count:2d} weeks ({count/len(regimes)*100:.1f}%)")

    return regimes


if __name__ == "__main__":
    # Pre-compute for entire 2025
    precompute_macro_regimes(
        start_date='2025-01-01',
        end_date='2025-12-31',
        output_file='macro_regimes_2025.json'
    )

    print()
    print("=" * 80)
    print("✅ PRE-COMPUTATION COMPLETE!")
    print("=" * 80)
    print()
    print("Next step: Run backtest with:")
    print("  python3 backtest_complete_6layer.py")
    print()
