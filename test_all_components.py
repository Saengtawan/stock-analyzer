#!/usr/bin/env python3
"""
Complete System Test - Verify all v3.1 components working
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

from api.data_manager import DataManager
from screeners.growth_catalyst_screener import GrowthCatalystScreener
import logging

logging.basicConfig(level=logging.WARNING)

def test_complete_system():
    print("\n" + "="*80)
    print("🔬 COMPLETE SYSTEM VERIFICATION - v3.1")
    print("="*80)

    data_manager = DataManager()
    screener = GrowthCatalystScreener(data_manager)

    # Test with AMAT (had 3/6 signals in recent scan)
    symbol = 'AMAT'
    print(f"\nTesting {symbol}...")

    result = screener._analyze_stock_comprehensive(symbol, 5.0, 30)

    if not result:
        print("❌ Failed to analyze")
        return

    print("\n" + "="*80)
    print("1️⃣ ALTERNATIVE DATA SOURCES (6 Sources)")
    print("="*80)

    # Check alt data
    alt_data = result.get('alt_data_analysis', {})
    signals = result.get('alt_data_signals', 0)

    print(f"\nTotal Signals: {signals}/6")
    print("\nSignal Breakdown:")

    sources = [
        ('👔 Insider Buying', result.get('has_insider_buying', False)),
        ('📊 Analyst Upgrade', result.get('has_analyst_upgrade', False)),
        ('📉 Squeeze Potential', result.get('has_squeeze_potential', False)),
        ('🗣️ Social Buzz', result.get('has_social_buzz', False)),
        ('🔗 Correlation (Sector Leader)', alt_data.get('follows_strong_leader', False) if alt_data else False),
        ('🌍 Macro (Sector Momentum)', alt_data.get('has_sector_momentum', False) if alt_data else False),
    ]

    active_count = 0
    for name, active in sources:
        status = "✅" if active else "❌"
        print(f"  {status} {name}")
        if active:
            active_count += 1

    if active_count == signals:
        print(f"\n✅ Signal count correct: {active_count}/6")
    else:
        print(f"\n⚠️ Signal mismatch: counted {active_count}, reported {signals}")

    # Win rate check
    print("\n" + "="*80)
    print("2️⃣ WIN RATE VALIDATION")
    print("="*80)

    print(f"\nSignals: {signals}/6")
    if signals >= 3:
        print(f"✅ Qualifies for trading (≥3 signals)")
        print(f"   Expected Win Rate: 58.3% (validated)")
        print(f"   Projected with Sector Rotation: 60-65%")
    else:
        print(f"❌ Below threshold (<3 signals)")
        print(f"   Would be filtered out")

    # Scoring breakdown
    print("\n" + "="*80)
    print("3️⃣ MULTI-SOURCE SCORING")
    print("="*80)

    components = [
        ('Technical', 25, result.get('technical_score', 0)),
        ('Alt Data', 25, result.get('alt_data_score', 0)),
        ('Sector', 20, result.get('sector_score', 0)),
        ('Valuation', 15, result.get('valuation_score', 0)),
        ('Catalyst', 10, result.get('catalyst_score', 0)),
        ('AI Probability', 5, result.get('ai_probability', 0)),
    ]

    print(f"\n{'Component':<20} {'Weight':<10} {'Score':<10} {'Contribution':<15}")
    print("-" * 70)

    total_contrib = 0
    for name, weight, score in components:
        contrib = score * (weight / 100)
        total_contrib += contrib
        print(f"{name:<20} {weight:>3}%{'':<6} {score:>6.1f}/100 {contrib:>10.2f}")

    print("-" * 70)
    print(f"{'Base Composite':<20} {'100%':<10} {'':<10} {total_contrib:>10.2f}")

    # Sector rotation
    boost = result.get('sector_rotation_boost', 1.0)
    final = total_contrib * boost

    print(f"\n{'Sector Rotation':<20} {'Boost':<10} {boost:>6.2f}x")
    print(f"{'Final Composite':<20} {'':<10} {'':<10} {final:>10.2f}")

    actual = result.get('composite_score', 0)
    print(f"{'Actual (reported)':<20} {'':<10} {'':<10} {actual:>10.2f}")

    # Verify
    if abs(final - actual) < 2:
        print(f"\n✅ Scoring calculation correct (±{abs(final - actual):.1f} rounding)")
    else:
        print(f"\n⚠️ Scoring mismatch: {abs(final - actual):.1f} points difference")

    # AI Analysis
    print("\n" + "="*80)
    print("4️⃣ AI-POWERED ANALYSIS")
    print("="*80)

    ai_prob = result.get('ai_probability', 0)
    ai_conf = result.get('ai_confidence', 0)
    ai_reasoning = result.get('ai_reasoning', '')

    print(f"\nAI Probability: {ai_prob:.1f}%")
    print(f"AI Confidence:  {ai_conf:.1f}%")

    if ai_reasoning:
        print(f"\nAI Reasoning:")
        # Truncate if too long
        reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
        print(f"  {reasoning_preview}")
        print(f"\n✅ AI analysis working")
    else:
        print(f"\n⚠️ No AI reasoning provided")

    # Sector rotation detail
    print("\n" + "="*80)
    print("5️⃣ SECTOR ROTATION (v3.1 NEW)")
    print("="*80)

    sector = result.get('sector', 'Unknown')
    sector_status = result.get('sector_rotation_status', 'unknown')
    sector_momentum = result.get('sector_momentum', 0)

    print(f"\nSector: {sector}")
    print(f"Status: {sector_status}")
    print(f"Momentum: {sector_momentum:+.1f}%")
    print(f"Boost: {boost:.2f}x")

    if sector_status == 'hot' and boost > 1.0:
        print(f"\n✅ Hot sector boost applied correctly")
    elif sector_status == 'cold' and boost < 1.0:
        print(f"\n✅ Cold sector penalty applied correctly")
    elif sector_status == 'neutral' and boost == 1.0:
        print(f"\n✅ Neutral sector (no adjustment)")
    else:
        print(f"\n⚠️ Sector boost mismatch")

    # Summary
    print("\n" + "="*80)
    print("📊 COMPLETE SYSTEM CHECK")
    print("="*80)

    checks = [
        ("Alternative Data Sources", signals >= 1),
        ("Signal Threshold Filter", signals >= 3),
        ("Multi-Source Scoring", abs(final - actual) < 2),
        ("AI Analysis", ai_prob > 0),
        ("Sector Rotation", boost != 1.0 or sector_status == 'neutral'),
    ]

    passed = 0
    for check_name, check_result in checks:
        status = "✅" if check_result else "❌"
        print(f"{status} {check_name}")
        if check_result:
            passed += 1

    print(f"\n{'='*80}")
    print(f"Result: {passed}/{len(checks)} checks passed")

    if passed == len(checks):
        print("✅ ALL SYSTEMS OPERATIONAL")
    elif passed >= len(checks) - 1:
        print("⚠️ MOSTLY OPERATIONAL (minor issues)")
    else:
        print("❌ ISSUES DETECTED")

    print("="*80)

    # Final stats
    print("\n" + "="*80)
    print("🎯 KEY METRICS")
    print("="*80)

    print(f"\nSymbol:           {symbol}")
    print(f"Composite Score:  {actual:.1f}/100")
    print(f"Alt Data Signals: {signals}/6")
    print(f"Win Rate:         58.3% (validated)")
    print(f"Sector:           {sector} ({sector_status}, {sector_momentum:+.1f}%)")
    print(f"Recommendation:   {'✅ TRADE' if signals >= 3 else '❌ SKIP'}")


if __name__ == "__main__":
    test_complete_system()
