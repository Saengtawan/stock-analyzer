#!/usr/bin/env python3
"""
Test Tiered Quality System - เปรียบเทียบ 3 แนวทาง
=====================================================

จะทดสอบว่าแนวทางไหนดีที่สุดสำหรับหุ้นราคาต่ำ ($3-$10):

1. **WITH Tiered Quality (Current)**
   - หุ้น $5-10: ต้อง technical ≥ 60, AI ≥ 60%, มี insider buying
   - เข้มงวด ป้องกันหุ้นขยะ

2. **WITHOUT Tiered Quality (User Control)**
   - ใช้ threshold ที่ user ตั้งเท่านั้น (เช่น 30/30%)
   - User มีอิสระเต็มที่

3. **RELAXED Tiered (Middle Ground)**
   - หุ้น $5-10: technical ≥ 40, AI ≥ 40%, ไม่บังคับ insider buying
   - พอประมาณ

วิธีทดสอบ:
- สแกนหาหุ้นราคาต่ำ ($3-10) ทั้ง 3 วิธี
- ดูว่าวิธีไหนเจอหุ้นดีจริง vs หุ้นขยะ
- เปรียบเทียบ win rate, ค่าเฉลี่ย return
"""

import sys
sys.path.insert(0, 'src')

from screeners.growth_catalyst_screener import GrowthCatalystScreener
from main import StockAnalyzer
from loguru import logger
from datetime import datetime, timedelta
import json

logger.remove()
logger.add(sys.stderr, level="ERROR")

print("=" * 80)
print("🧪 TIERED QUALITY SYSTEM TEST")
print("=" * 80)
print("Testing 3 approaches for low-priced stocks ($3-$10):\n")
print("1️⃣  WITH Tiered Quality (STRICT - Current system)")
print("2️⃣  WITHOUT Tiered Quality (USER CONTROL - Your thresholds only)")
print("3️⃣  RELAXED Tiered (MIDDLE GROUND)")
print("=" * 80)

# Initialize
print("\n📦 Initializing...")
analyzer = StockAnalyzer()
screener = GrowthCatalystScreener(analyzer)

# Common search criteria
TARGET_GAIN = 5.0
TIMEFRAME = 30
MIN_CATALYST = 0.0
USER_TECHNICAL = 30.0  # User wants 30
USER_AI = 30.0         # User wants 30%
MAX_STOCKS = 20
UNIVERSE_MULT = 5

print("\n" + "=" * 80)
print("TEST 1: WITH Tiered Quality (CURRENT SYSTEM - STRICT)")
print("=" * 80)
print("Low-price stocks ($5-10) requirements:")
print("  ✓ Technical Score ≥ 60 (override user's 30)")
print("  ✓ AI Probability ≥ 60% (override user's 30%)")
print("  ✓ Insider Buying REQUIRED")
print("  ✓ Alt Data Signals ≥ 3/6")

print("\n🔍 Screening...")
try:
    results_strict = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=TARGET_GAIN,
        timeframe_days=TIMEFRAME,
        min_catalyst_score=MIN_CATALYST,
        min_technical_score=USER_TECHNICAL,
        min_ai_probability=USER_AI,
        max_stocks=MAX_STOCKS,
        universe_multiplier=UNIVERSE_MULT
    )

    print(f"\n📊 Results: {len(results_strict)} stocks")

    # Analyze by price range
    low_price = [s for s in results_strict if 3 <= s['current_price'] <= 10]
    mid_price = [s for s in results_strict if 10 < s['current_price'] <= 20]
    high_price = [s for s in results_strict if s['current_price'] > 20]

    print(f"\n   Price Breakdown:")
    print(f"   $3-10:  {len(low_price)} stocks (Tiered Quality applied)")
    print(f"   $10-20: {len(mid_price)} stocks")
    print(f"   $20+:   {len(high_price)} stocks")

    if low_price:
        print(f"\n   Low-Price Stocks That PASSED Strict Filters:")
        for i, s in enumerate(low_price[:5], 1):
            insider = "✓ Insider" if 'Insider Buying' in s.get('alt_data_signals_list', []) else "✗ No Insider"
            print(f"   {i}. {s['symbol']:6} @ ${s['current_price']:6.2f} | "
                  f"Tech: {s.get('technical_score', 0):4.1f} | "
                  f"AI: {s.get('ai_probability', 0):4.1f}% | "
                  f"Signals: {s.get('alt_data_signals', 0)}/6 | {insider}")
    else:
        print(f"\n   ❌ NO low-price stocks passed strict filters")

except Exception as e:
    print(f"   ❌ Error: {e}")
    results_strict = []

print("\n" + "=" * 80)
print("TEST 2: WITHOUT Tiered Quality (USER CONTROL)")
print("=" * 80)
print("ALL stocks (including $5-10) use USER thresholds:")
print("  ✓ Technical Score ≥ 30 (user's choice)")
print("  ✓ AI Probability ≥ 30% (user's choice)")
print("  ✗ No insider buying requirement")
print("  ✗ No tier-based overrides")

# Temporarily disable tiered quality
print("\n🔍 Screening...")
print("⚠️  WARNING: Disabling tiered quality system temporarily...")

# Save original method
original_get_dynamic = screener.get_dynamic_thresholds

# Override to return user's thresholds always
def mock_get_dynamic_thresholds(price):
    """Return user's thresholds, no tier overrides"""
    return {
        'tier': 'USER_CONTROL',
        'min_catalyst_score': MIN_CATALYST,
        'min_technical_score': USER_TECHNICAL,
        'min_ai_probability': USER_AI,
        'min_market_cap': 500_000_000,
        'min_volume': 10_000_000,
        'require_insider_buying': False,
        'min_analyst_coverage': 0,
        'description': 'User-controlled thresholds (no tier override)'
    }

screener.get_dynamic_thresholds = mock_get_dynamic_thresholds

try:
    results_user_control = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=TARGET_GAIN,
        timeframe_days=TIMEFRAME,
        min_catalyst_score=MIN_CATALYST,
        min_technical_score=USER_TECHNICAL,
        min_ai_probability=USER_AI,
        max_stocks=MAX_STOCKS,
        universe_multiplier=UNIVERSE_MULT
    )

    print(f"\n📊 Results: {len(results_user_control)} stocks")

    # Analyze by price range
    low_price_uc = [s for s in results_user_control if 3 <= s['current_price'] <= 10]
    mid_price_uc = [s for s in results_user_control if 10 < s['current_price'] <= 20]
    high_price_uc = [s for s in results_user_control if s['current_price'] > 20]

    print(f"\n   Price Breakdown:")
    print(f"   $3-10:  {len(low_price_uc)} stocks (NO tiered filtering)")
    print(f"   $10-20: {len(mid_price_uc)} stocks")
    print(f"   $20+:   {len(high_price_uc)} stocks")

    if low_price_uc:
        print(f"\n   Low-Price Stocks Found:")
        for i, s in enumerate(low_price_uc[:10], 1):
            insider = "✓ Insider" if 'Insider Buying' in s.get('alt_data_signals_list', []) else "✗ No Insider"
            print(f"   {i}. {s['symbol']:6} @ ${s['current_price']:6.2f} | "
                  f"Tech: {s.get('technical_score', 0):4.1f} | "
                  f"AI: {s.get('ai_probability', 0):4.1f}% | "
                  f"Signals: {s.get('alt_data_signals', 0)}/6 | {insider}")
    else:
        print(f"\n   ⚠️  Still no low-price stocks found (maybe criteria still too strict)")

except Exception as e:
    print(f"   ❌ Error: {e}")
    results_user_control = []
finally:
    # Restore original method
    screener.get_dynamic_thresholds = original_get_dynamic

print("\n" + "=" * 80)
print("TEST 3: RELAXED Tiered Quality (MIDDLE GROUND)")
print("=" * 80)
print("Low-price stocks ($5-10) requirements:")
print("  ✓ Technical Score ≥ 40 (relaxed from 60)")
print("  ✓ AI Probability ≥ 40% (relaxed from 60%)")
print("  ✗ Insider Buying NOT required (relaxed)")
print("  ✓ Alt Data Signals ≥ 2/6 (relaxed from 3/6)")

def mock_get_relaxed_thresholds(price):
    """Relaxed tier thresholds - middle ground"""
    if price >= 50:
        return {
            'tier': 'HIGH_PRICE',
            'min_catalyst_score': 0.0,
            'min_technical_score': 30.0,
            'min_ai_probability': 30.0,
            'min_market_cap': 500_000_000,
            'min_volume': 10_000_000,
            'require_insider_buying': False,
            'min_analyst_coverage': 0,
            'description': '$50+ stocks'
        }
    elif price >= 20:
        return {
            'tier': 'MID_HIGH_PRICE',
            'min_catalyst_score': 10.0,
            'min_technical_score': 35.0,
            'min_ai_probability': 35.0,
            'min_market_cap': 500_000_000,
            'min_volume': 10_000_000,
            'require_insider_buying': False,
            'min_analyst_coverage': 0,
            'description': '$20-$50 stocks'
        }
    elif price >= 10:
        return {
            'tier': 'MID_PRICE',
            'min_catalyst_score': 20.0,
            'min_technical_score': 40.0,
            'min_ai_probability': 40.0,
            'min_market_cap': 500_000_000,
            'min_volume': 15_000_000,
            'require_insider_buying': False,
            'min_analyst_coverage': 0,
            'description': '$10-$20 stocks - Relaxed'
        }
    elif price >= 5:
        # RELAXED: 40/40%, no insider buying required
        return {
            'tier': 'LOW_MID_PRICE_RELAXED',
            'min_catalyst_score': 20.0,
            'min_technical_score': 40.0,  # ← Relaxed from 60
            'min_ai_probability': 40.0,    # ← Relaxed from 60%
            'min_market_cap': 500_000_000,
            'min_volume': 15_000_000,
            'require_insider_buying': False,  # ← NOT required
            'min_analyst_coverage': 1,
            'description': '$5-$10 stocks - Relaxed quality (40/40%, no insider req)'
        }
    else:  # price >= 3
        return {
            'tier': 'LOW_PRICE_RELAXED',
            'min_catalyst_score': 30.0,
            'min_technical_score': 50.0,  # ← Relaxed from 70
            'min_ai_probability': 50.0,    # ← Relaxed from 70%
            'min_market_cap': 200_000_000,
            'min_volume': 15_000_000,
            'require_insider_buying': False,  # ← NOT required
            'min_analyst_coverage': 1,
            'description': '$3-$5 stocks - Relaxed quality'
        }

screener.get_dynamic_thresholds = mock_get_relaxed_thresholds

print("\n🔍 Screening...")
try:
    results_relaxed = screener.screen_growth_catalyst_opportunities(
        target_gain_pct=TARGET_GAIN,
        timeframe_days=TIMEFRAME,
        min_catalyst_score=MIN_CATALYST,
        min_technical_score=USER_TECHNICAL,
        min_ai_probability=USER_AI,
        max_stocks=MAX_STOCKS,
        universe_multiplier=UNIVERSE_MULT
    )

    print(f"\n📊 Results: {len(results_relaxed)} stocks")

    # Analyze by price range
    low_price_rel = [s for s in results_relaxed if 3 <= s['current_price'] <= 10]
    mid_price_rel = [s for s in results_relaxed if 10 < s['current_price'] <= 20]
    high_price_rel = [s for s in results_relaxed if s['current_price'] > 20]

    print(f"\n   Price Breakdown:")
    print(f"   $3-10:  {len(low_price_rel)} stocks (Relaxed tiered quality)")
    print(f"   $10-20: {len(mid_price_rel)} stocks")
    print(f"   $20+:   {len(high_price_rel)} stocks")

    if low_price_rel:
        print(f"\n   Low-Price Stocks Found:")
        for i, s in enumerate(low_price_rel[:10], 1):
            insider = "✓ Insider" if 'Insider Buying' in s.get('alt_data_signals_list', []) else "✗ No Insider"
            print(f"   {i}. {s['symbol']:6} @ ${s['current_price']:6.2f} | "
                  f"Tech: {s.get('technical_score', 0):4.1f} | "
                  f"AI: {s.get('ai_probability', 0):4.1f}% | "
                  f"Signals: {s.get('alt_data_signals', 0)}/6 | {insider}")
    else:
        print(f"\n   ⚠️  Still no low-price stocks found")

except Exception as e:
    print(f"   ❌ Error: {e}")
    results_relaxed = []
finally:
    # Restore original method
    screener.get_dynamic_thresholds = original_get_dynamic

# Summary comparison
print("\n" + "=" * 80)
print("📊 COMPARISON SUMMARY")
print("=" * 80)

print(f"\n{'Approach':<30} {'Total':>8} {'$3-10':>8} {'$10-20':>8} {'$20+':>8}")
print("-" * 65)

strict_low = len([s for s in results_strict if 3 <= s['current_price'] <= 10])
strict_mid = len([s for s in results_strict if 10 < s['current_price'] <= 20])
strict_high = len([s for s in results_strict if s['current_price'] > 20])
print(f"{'1. WITH Tiered (STRICT)':<30} {len(results_strict):>8} {strict_low:>8} {strict_mid:>8} {strict_high:>8}")

uc_low = len([s for s in results_user_control if 3 <= s['current_price'] <= 10])
uc_mid = len([s for s in results_user_control if 10 < s['current_price'] <= 20])
uc_high = len([s for s in results_user_control if s['current_price'] > 20])
print(f"{'2. WITHOUT Tiered (USER)':<30} {len(results_user_control):>8} {uc_low:>8} {uc_mid:>8} {uc_high:>8}")

rel_low = len([s for s in results_relaxed if 3 <= s['current_price'] <= 10])
rel_mid = len([s for s in results_relaxed if 10 < s['current_price'] <= 20])
rel_high = len([s for s in results_relaxed if s['current_price'] > 20])
print(f"{'3. RELAXED Tiered (MIDDLE)':<30} {len(results_relaxed):>8} {rel_low:>8} {rel_mid:>8} {rel_high:>8}")

# Quality analysis of low-price stocks
print("\n" + "=" * 80)
print("🔍 QUALITY ANALYSIS - Low-Price Stocks ($3-10)")
print("=" * 80)

def analyze_quality(stocks, approach_name):
    if not stocks:
        print(f"\n{approach_name}: No stocks to analyze")
        return

    print(f"\n{approach_name}:")
    print(f"  Count: {len(stocks)}")

    avg_tech = sum(s.get('technical_score', 0) for s in stocks) / len(stocks)
    avg_ai = sum(s.get('ai_probability', 0) for s in stocks) / len(stocks)
    avg_signals = sum(s.get('alt_data_signals', 0) for s in stocks) / len(stocks)
    avg_composite = sum(s.get('composite_score', 0) for s in stocks) / len(stocks)

    with_insider = sum(1 for s in stocks if 'Insider Buying' in s.get('alt_data_signals_list', []))

    print(f"  Avg Technical Score:  {avg_tech:.1f}")
    print(f"  Avg AI Probability:   {avg_ai:.1f}%")
    print(f"  Avg Alt Data Signals: {avg_signals:.1f}/6")
    print(f"  Avg Composite Score:  {avg_composite:.1f}/100")
    print(f"  With Insider Buying:  {with_insider}/{len(stocks)} ({with_insider/len(stocks)*100:.0f}%)")

    # List stocks
    print(f"\n  Top stocks:")
    for i, s in enumerate(sorted(stocks, key=lambda x: x.get('composite_score', 0), reverse=True)[:5], 1):
        print(f"    {i}. {s['symbol']}")

low_price_strict = [s for s in results_strict if 3 <= s['current_price'] <= 10]
low_price_uc = [s for s in results_user_control if 3 <= s['current_price'] <= 10]
low_price_rel = [s for s in results_relaxed if 3 <= s['current_price'] <= 10]

analyze_quality(low_price_strict, "STRICT (Current)")
analyze_quality(low_price_uc, "USER CONTROL (No tier)")
analyze_quality(low_price_rel, "RELAXED (Middle ground)")

# Recommendation
print("\n" + "=" * 80)
print("💡 RECOMMENDATION")
print("=" * 80)

if len(low_price_strict) == 0 and len(low_price_uc) == 0 and len(low_price_rel) == 0:
    print("""
⚠️  NO low-price stocks found in ANY approach!

Possible reasons:
1. Market regime SIDEWAYS - system filtering ALL stocks
2. Alt Data Signals requirement (≥3/6) too strict
3. No good low-price opportunities right now

Next steps:
- Try lowering alt_data_signals requirement (3 → 2)
- Try different market period (when regime is BULL)
- Focus on higher-priced stocks ($10+) for now
""")
elif len(low_price_uc) > 0 and len(low_price_strict) == 0:
    print(f"""
✅ USER CONTROL approach found {len(low_price_uc)} low-price stocks
❌ STRICT approach found 0

Recommendation: USE USER CONTROL (disable tiered quality)
- You have more flexibility
- Can decide yourself which stocks to trust
- Tiered quality is blocking potentially good opportunities

⚠️  But be careful! Manually review each stock:
- Check fundamentals yourself
- Watch for pump & dump patterns
- Start with small position sizes
""")
elif len(low_price_rel) > len(low_price_strict) and len(low_price_rel) > 0:
    print(f"""
✅ RELAXED approach found {len(low_price_rel)} low-price stocks
📊 STRICT approach found {len(low_price_strict)}

Recommendation: USE RELAXED TIERED QUALITY (middle ground)
- Balanced approach: not too strict, not too loose
- Still has some protection against bad stocks
- More opportunities than strict mode

This gives you both flexibility AND safety.
""")
else:
    print("""
Current STRICT approach seems appropriate for now.
Low-price stocks are risky - the strict filters help protect you.
""")

print("\n" + "=" * 80)
print("✅ TEST COMPLETE")
print("=" * 80)
print("\nNext: Review the stocks found and decide which approach to use.")
print("      You can also run a backtest to see historical performance.")
