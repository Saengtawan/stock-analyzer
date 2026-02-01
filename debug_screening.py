#!/usr/bin/env python3
"""
Debug Screening - ตรวจสอบว่าทำไม screening ได้ 0 หุ้น
"""

import sys
sys.path.insert(0, 'src')

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
from loguru import logger

# ตั้ง log level ให้เห็นทุกอย่าง
logger.remove()
logger.add(sys.stderr, level="INFO")

print("=" * 80)
print("🔍 DEBUG SCREENING")
print("=" * 80)

# Initialize
print("\n1️⃣ Initializing...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)

# ใช้ criteria เดียวกับที่ user ใช้บน web
print("\n2️⃣ Running screening with WEB UI criteria:")
print("   - Target: 5%")
print("   - Catalyst Score ≥ 0")
print("   - Technical Score ≥ 30")
print("   - AI Probability ≥ 30%")
print("   - Max stocks: 20")
print("   - Universe multiplier: 5x")

print("\n3️⃣ Screening...")
try:
    opportunities = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_catalyst_score=0.0,
        min_technical_score=30.0,
        min_ai_probability=30.0,
        max_stocks=20,
        universe_multiplier=5
    )

    print(f"\n4️⃣ Results:")
    print(f"   Found: {len(opportunities)} opportunities")

    if opportunities:
        print(f"\n   Top 5 results:")
        for i, opp in enumerate(opportunities[:5], 1):
            print(f"   {i}. {opp['symbol']:6} @ ${opp['current_price']:7.2f} | "
                  f"Composite: {opp.get('composite_score', 0):5.1f} | "
                  f"Catalyst: {opp.get('catalyst_score', 0):5.1f} | "
                  f"Tech: {opp.get('technical_score', 0):5.1f} | "
                  f"AI: {opp.get('ai_probability', 0):5.1f}%")

            # Check for warnings
            if opp.get('regime_warning'):
                print(f"      ⚠️  Regime Warning: {opp.get('regime', 'UNKNOWN')}")
    else:
        print("\n   ⚠️  No opportunities found")
        print("\n   Possible reasons:")
        print("   1. Market regime unfavorable (SIDEWAYS)")
        print("   2. No stocks pass all filters")
        print("   3. Technical/AI criteria too strict")

except Exception as e:
    print(f"\n   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ลองผ่อนคลายเกณฑ์
print("\n" + "=" * 80)
print("5️⃣ Testing with RELAXED criteria:")
print("   - Catalyst Score ≥ 0")
print("   - Technical Score ≥ 0  ← RELAXED")
print("   - AI Probability ≥ 0%  ← RELAXED")
print("=" * 80)

try:
    opportunities_relaxed = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=5.0,
        timeframe_days=30,
        min_catalyst_score=0.0,
        min_technical_score=0.0,    # ← RELAXED
        min_ai_probability=0.0,      # ← RELAXED
        max_stocks=20,
        universe_multiplier=5
    )

    print(f"\n   Found: {len(opportunities_relaxed)} opportunities")

    if opportunities_relaxed:
        print(f"\n   Top 5 results:")
        for i, opp in enumerate(opportunities_relaxed[:5], 1):
            print(f"   {i}. {opp['symbol']:6} @ ${opp['current_price']:7.2f} | "
                  f"Composite: {opp.get('composite_score', 0):5.1f} | "
                  f"Tech: {opp.get('technical_score', 0):5.1f} | "
                  f"AI: {opp.get('ai_probability', 0):5.1f}%")

            if opp.get('regime_warning'):
                print(f"      ⚠️  Regime: {opp.get('regime', 'UNKNOWN')}")

        print(f"\n   ✅ Screening works! Just need to relax criteria or wait for better market")
    else:
        print("\n   ⚠️  Still no opportunities - might be regime filter")

except Exception as e:
    print(f"\n   ❌ Error: {e}")

# ทดสอบข้าม regime filter
print("\n" + "=" * 80)
print("6️⃣ Testing with NO filtering (debug mode):")
print("=" * 80)

# ดูว่า screener มี regime check ที่ไหน
print("\n   Checking if opportunities have regime_warning...")
if opportunities_relaxed:
    has_warnings = sum(1 for o in opportunities_relaxed if o.get('regime_warning', False))
    print(f"   {has_warnings}/{len(opportunities_relaxed)} have regime warnings")

    if has_warnings > 0:
        print(f"\n   ⚠️  Regime filter is blocking {has_warnings} stocks!")
        print(f"   This is a SAFETY FEATURE - stocks filtered because market regime not suitable")
        print(f"\n   To see these stocks anyway (not recommended for real trading):")
        print(f"   - Lower Technical Score to 0")
        print(f"   - Lower AI Probability to 0%")
        print(f"   - Check 'regime_warning' field in results")

print("\n" + "=" * 80)
print("✅ DEBUG COMPLETE")
print("=" * 80)
