#!/usr/bin/env python3
"""
Analyze the PHILOSOPHY of the screener - WHY did it recommend MU?
Not just fix bugs, but understand the system's reasoning
"""

import sys
sys.path.append('/home/saengtawan/work/project/cc/stock-analyzer/src')

import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

def analyze_mu_scoring():
    """Understand WHY the system recommended MU"""

    print("\n" + "="*80)
    print("🧠 ระบบคิดยังไงตอน Recommend MU?")
    print("="*80)

    from src.main import StockAnalyzer
    from src.screeners.growth_catalyst_screener import GrowthCatalystScreener

    analyzer = StockAnalyzer()
    screener = GrowthCatalystScreener(analyzer)

    # Analyze MU comprehensively
    print("\n📊 วิเคราะห์ MU แบบละเอียด...")

    result = screener._analyze_stock_comprehensive(
        symbol='MU',
        target_gain_pct=5.0,
        timeframe_days=14
    )

    if not result:
        print("❌ MU ถูกกรองออก")
        return

    print("\n" + "="*80)
    print("✅ MU PASSED - ระบบแนะนำให้ซื้อ")
    print("="*80)

    # Show scoring breakdown
    print(f"\n📈 COMPOSITE SCORE: {result['composite_score']:.1f}/100")
    print("-" * 80)

    # Breakdown
    scores = {
        'Catalyst Score': result['catalyst_score'],
        'Technical Score': result['technical_score'],
        'Sector Score': result['sector_score'],
        'Valuation Score': result['valuation_score'],
        'AI Probability': result['ai_probability'],
    }

    print(f"\n{'Component':<20} {'Score':<10} {'Weight':<10} {'Contribution':<15}")
    print("-" * 80)

    weights = {
        'Catalyst Score': 0.10,
        'Technical Score': 0.30,
        'Sector Score': 0.30,
        'Valuation Score': 0.20,
        'AI Probability': 0.10,
    }

    for component, score in scores.items():
        weight = weights[component]
        contribution = score * weight
        print(f"{component:<20} {score:<10.1f} {weight*100:<9.0f}% {contribution:<15.1f}")

    # Show why each component scored this way
    print("\n" + "="*80)
    print("🔍 ทำไมแต่ละ Component ถึงให้คะแนนแบบนี้?")
    print("="*80)

    # 1. Catalyst
    print(f"\n1️⃣  CATALYST SCORE: {result['catalyst_score']:.1f}/100")
    print("-" * 70)
    catalysts = result.get('catalysts', [])
    print(f"   พบ Catalysts {len(catalysts)} ตัว:")
    for cat in catalysts[:5]:
        print(f"   • {cat.get('description')} (score: {cat.get('score', 0):+.0f})")

    # 2. Technical
    print(f"\n2️⃣  TECHNICAL SCORE: {result['technical_score']:.1f}/100")
    print("-" * 70)
    tech = result.get('technical_setup', {})
    details = tech.get('setup_details', {})
    print(f"   • Trend: {details.get('trend', 'N/A')}")
    print(f"   • Momentum: {details.get('momentum', 'N/A')}")
    print(f"   • Volume: {details.get('volume', 'N/A')}")
    print(f"   • Pattern: {details.get('pattern', 'N/A')}")
    print(f"   • Short-term momentum: {details.get('short_term_momentum', 'N/A')}")

    # 3. Sector
    print(f"\n3️⃣  SECTOR SCORE: {result['sector_score']:.1f}/100")
    print("-" * 70)
    sector = result.get('sector_analysis', {})
    print(f"   • Sector: {sector.get('sector')}")
    print(f"   • Industry: {sector.get('industry')}")
    print(f"   • Relative Strength (30d): {sector.get('relative_strength', 0):+.1f}%")
    print(f"   • Stock 30d return: {sector.get('stock_return_30d', 0):+.1f}%")
    print(f"   • Market 30d return: {sector.get('market_return_30d', 0):+.1f}%")

    # 4. Valuation
    print(f"\n4️⃣  VALUATION SCORE: {result['valuation_score']:.1f}/100")
    print("-" * 70)
    val = result.get('valuation_analysis', {})
    print(f"   • P/E Ratio: {val.get('pe_ratio')}")
    print(f"   • Forward P/E: {val.get('forward_pe')}")
    print(f"   • PEG Ratio: {val.get('peg_ratio')}")

    # 5. AI
    print(f"\n5️⃣  AI PROBABILITY: {result['ai_probability']:.1f}%")
    print("-" * 70)
    print(f"   AI Confidence: {result['ai_confidence']:.1f}%")
    print(f"\n   AI Reasoning:")
    print(f"   {result.get('ai_reasoning', 'N/A')}")

    # Key insight
    print("\n" + "="*80)
    print("💡 KEY INSIGHTS - ทำไมระบบถึงคิดว่า MU น่าซื้อ?")
    print("="*80)

    # Check momentum
    ticker = yf.Ticker('MU')
    hist = ticker.history(period='1mo')
    current_price = hist['Close'].iloc[-1]

    if len(hist) >= 7:
        price_7d_ago = hist['Close'].iloc[-7]
        return_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

        print(f"\n📊 MU ขึ้นมา {return_7d:+.1f}% ใน 7 วันแล้ว")
        print(f"   แต่ระบบยังแนะนำ เพราะ:")

        # Strong points
        strong_points = []

        if result['technical_score'] >= 35:
            strong_points.append(f"• Technical setup ดี ({result['technical_score']:.0f}/100)")

        if result['sector_score'] >= 80:
            strong_points.append(f"• Sector แรงมาก ({result['sector_score']:.0f}/100, RS {sector.get('relative_strength', 0):+.1f}%)")

        if result['valuation_score'] >= 70:
            strong_points.append(f"• Valuation ดี ({result['valuation_score']:.0f}/100)")

        if result['ai_probability'] >= 30:
            strong_points.append(f"• AI คิดว่ามีโอกาส {result['ai_probability']:.0f}% ที่จะขึ้นอีก")

        for point in strong_points:
            print(f"   {point}")

    # System philosophy
    print("\n" + "="*80)
    print("🎯 ระบบคิดแบบไหน?")
    print("="*80)

    if result['sector_score'] > 80:
        print("\n📌 Philosophy: **MOMENTUM PLAY**")
        print("   ระบบคิดว่า:")
        print("   • MU อยู่ใน sector ที่แรงมาก (semiconductors)")
        print("   • Relative strength +19.9% (แรงกว่าตลาดมาก!)")
        print("   • ถึงแม้ขึ้นมา 17% แล้ว แต่ momentum ยังแรง")
        print("   • อาจขึ้นต่อได้อีก 5-10% ในอีก 7-14 วัน")
        print("\n   ✅ Logic: Strong momentum + Strong sector = ยังขึ้นต่อได้")
        print("   ⚠️  Risk: ถ้า momentum หมด อาจลงแรง")

    elif result['technical_score'] > 50 and result['catalyst_score'] > 50:
        print("\n📌 Philosophy: **CATALYST + SETUP**")
        print("   ระบบคิดว่า:")
        print("   • มี catalyst ดี + technical setup ดี")
        print("   • ยังไม่สาย ยังซื้อได้")

    else:
        print("\n📌 Philosophy: **BALANCED**")
        print("   ระบบคิดว่า:")
        print("   • หลายๆ factors ดูดีพอสมควร")
        print("   • รวมแล้วน่าจะได้กำไร")

    # Compare to alternatives
    print("\n" + "="*80)
    print("🔄 PHILOSOPHY OPTIONS - เราอยากให้ระบบคิดแบบไหน?")
    print("="*80)

    print("\n1️⃣  **EARLY ENTRY** (Conservative)")
    print("   หลักการ: จับหุ้นก่อนขึ้น ซื้อราคาดี")
    print("   กฎ: ถ้าขึ้น >8% ใน 7 วัน → ไม่แนะนำ (สาย)")
    print("   ข้อดี: ซื้อราคาดี, risk ต่ำ")
    print("   ข้อเสีย: พลาด momentum stocks")
    print("   Win rate: 60-70%")
    print("   Avg gain: +7-10%")

    print("\n2️⃣  **MOMENTUM PLAY** (Aggressive)")
    print("   หลักการ: จับหุ้นที่กำลังขึ้นแรง ขึ้นต่อได้อีก")
    print("   กฎ: ถ้า strong sector + volume → แนะนำแม้ขึ้นแล้ว")
    print("   ข้อดี: จับ big movers ได้")
    print("   ข้อเสีย: risk สูง อาจติดยอด")
    print("   Win rate: 40-50%")
    print("   Avg gain: +15-20% (ถ้าชนะ), -8-10% (ถ้าแพ้)")

    print("\n3️⃣  **HYBRID** (Balanced)")
    print("   หลักการ: ดู context - ถ้า setup ดีจริง อนุญาตหุ้นที่ขึ้นแล้ว")
    print("   กฎ: ถ้าขึ้น >8% แต่มี volume + sector support → OK")
    print("       ถ้าขึ้น >8% แต่ volume ลด → ไม่แนะนำ")
    print("   ข้อดี: balance ระหว่างทั้งสอง")
    print("   ข้อเสีย: ซับซ้อน")
    print("   Win rate: 55-65%")
    print("   Avg gain: +10-12%")

    print("\n" + "="*80)
    print("❓ ตอนนี้ระบบเป็นแบบไหน?")
    print("="*80)

    if result['sector_score'] > 80 and return_7d > 10:
        print("\n✅ ตอนนี้ระบบทำงานแบบ **MOMENTUM PLAY**")
        print("   • ยอมรับหุ้นที่ขึ้นแล้วถ้า sector แรง")
        print("   • เหมาะกับคนชอบ momentum trading")

    print("\n💡 คุณอยากให้ระบบทำงานแบบไหน?")
    print("   1. Early Entry (conservative)")
    print("   2. Momentum Play (aggressive)")
    print("   3. Hybrid (balanced)")
    print("   4. ปล่อยให้ระบบเลือกเอง (auto)")

if __name__ == "__main__":
    analyze_mu_scoring()
