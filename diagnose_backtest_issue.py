#!/usr/bin/env python3
"""
Diagnose Why Aug-Dec Has No Trades in Full Backtest
====================================================

Compare:
- Quick test (separate months): Sept 5 trades, Oct 8 trades
- Full test (continuous): Aug-Dec 0 trades

Check each layer on specific dates to find the blocker.
"""

import sys
from datetime import datetime
from src.complete_growth_system import CompleteGrowthSystem
from src.market_regime_detector import MarketRegimeDetector

def diagnose_date(date_str: str, system: CompleteGrowthSystem, regime_detector: MarketRegimeDetector):
    """Run detailed diagnosis for a specific date"""

    date = datetime.strptime(date_str, '%Y-%m-%d')

    print("=" * 80)
    print(f"🔍 DIAGNOSING {date_str}")
    print("=" * 80)

    # Step 1: Check Market Regime
    print("\n📊 STEP 1: Market Regime")
    try:
        regime_info = regime_detector.get_current_regime(date)
        regime = regime_info['regime']
        details = regime_info['details']

        print(f"   Regime: {regime}")
        print(f"   Strength: {details.get('strength', 'N/A')}")
        print(f"   SPY Trend: {details.get('spy_trend', 'N/A')}")
        print(f"   RSI: {details.get('rsi', 'N/A'):.1f}" if details.get('rsi') else "   RSI: N/A")

        if regime in ['WEAK', 'BEAR']:
            print(f"   ⚠️  REGIME FILTER ACTIVE: {regime} regime - may block entries!")
    except Exception as e:
        print(f"   ❌ Error getting regime: {e}")
        regime = 'UNKNOWN'

    # Step 2: Check Macro Layer
    print("\n🌍 STEP 2: Macro Environment")
    try:
        # Get macro regime directly
        macro = system.macro_detector.get_macro_regime(date)

        print(f"   Fed Stance: {macro['fed_stance']}")
        print(f"   Market Health: {macro['market_health']}")
        print(f"   Sector Stage: {macro['sector_stage']}")
        print(f"   Risk Score: {macro['risk_score']}/3")
        print(f"   Risk Status: {'RISK_ON ✅' if macro['risk_on'] else 'RISK_OFF ❌'}")

        if not macro['risk_on']:
            print("\n   🚨 MACRO FILTER BLOCKING: RISK_OFF environment!")
            print(f"      Fed: {macro['fed_stance']} (need CUTTING)")
            print(f"      Health: {macro['market_health']} (need STRONG)")
            print(f"      Sector: {macro['sector_stage']} (need EARLY/MID_BULL)")
            print(f"      Risk Score: {macro['risk_score']}/3 (need ≥2)")
            return

    except Exception as e:
        print(f"   ❌ Error checking macro: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: If macro passes, check full screening
    print(f"\n🎯 STEP 3: Full Screening (Fundamental + Technical)")
    try:
        candidates = system.screen_for_entries(date, quiet=True)

        if candidates:
            print(f"   ✅ Found {len(candidates)} candidates:")
            for i, stock in enumerate(candidates[:5], 1):
                print(f"   {i}. {stock['symbol']}: Score {stock['total_score']}/200 "
                      f"(F:{stock['fundamental']['quality_score']}, C:{stock['catalyst']['catalyst_score']})")
        else:
            print("   ❌ NO CANDIDATES FOUND after fundamental/technical screening")

    except Exception as e:
        print(f"   ❌ Error during screening: {e}")

    print()


if __name__ == "__main__":
    print("=" * 80)
    print("🔬 BACKTEST DIAGNOSIS - Why No Trades Aug-Dec?")
    print("=" * 80)
    print("\nTesting key dates where quick test found trades but full test didn't:")
    print("- Sept 10: Quick test entered AVGO")
    print("- Sept 26: Quick test entered AMAT")
    print("- Oct 5: Quick test should find candidates")
    print()

    system = CompleteGrowthSystem()
    regime_detector = MarketRegimeDetector()

    # Test dates from quick backtest that had entries
    test_dates = [
        '2025-08-04',  # Day after last July exit - why no Aug trades?
        '2025-09-10',  # Quick test: AVGO entry
        '2025-09-26',  # Quick test: AMAT entry
        '2025-10-01',  # Quick test: LRCX entry
        '2025-10-06',  # Quick test: AMD entry
    ]

    for date_str in test_dates:
        diagnose_date(date_str, system, regime_detector)

    # Summary
    print("=" * 80)
    print("📋 DIAGNOSIS SUMMARY")
    print("=" * 80)
    print("""
Most Likely Causes:
1. REGIME_BEAR exits on Aug 4 → System may stay in RISK_OFF for rest of backtest
2. Continuous backtest maintains state (e.g., bearish regime) across months
3. Quick test starts fresh each month → ignores previous regime changes

Solution:
- Check if RISK_OFF persists from Aug 4 onwards
- May need to allow regime recovery (BEAR → BULL transition detection)
- Or allow entries in SIDEWAYS regime with tighter risk controls
""")
