#!/usr/bin/env python3
"""
First Principles Analysis: What data do we have and what can it tell us?
"""

import yfinance as yf
import pandas as pd

def analyze_data_sources():
    """
    Analyze what data we have and what it can tell us about stock movements
    """

    print("\n" + "="*80)
    print("🔍 FIRST PRINCIPLES: ข้อมูลที่มี และช่วยอะไรได้")
    print("="*80)

    # Use MU as example (we know it gained 10% recently)
    symbol = 'MU'
    ticker = yf.Ticker(symbol)

    print(f"\n📊 Example: {symbol}")
    print("="*80)

    # 1. Price & Volume Data
    print("\n1️⃣  PRICE & VOLUME DATA (Historical OHLCV)")
    print("-" * 70)

    hist = ticker.history(period='3mo')

    print(f"   Data available: {len(hist)} days")
    print(f"   Columns: {list(hist.columns)}")

    print(f"\n   ✅ สามารถคำนวณ:")
    print(f"      • Momentum (ขึ้น/ลง กี่ %)")
    print(f"      • Volatility (ผันผวนแค่ไหน)")
    print(f"      • Volume patterns (มีคนซื้อเยอะไหม)")
    print(f"      • Support/Resistance (ระดับราคาสำคัญ)")

    print(f"\n   ❌ ไม่สามารถบอก:")
    print(f"      • ทำไมขึ้น/ลง")
    print(f"      • จะขึ้นต่อไหม")
    print(f"      • มี catalyst อะไร")

    # 2. Financial/Fundamental Data
    print("\n2️⃣  FUNDAMENTAL DATA (Company Financials)")
    print("-" * 70)

    info = ticker.info

    fundamental_data = {
        'P/E Ratio': info.get('trailingPE'),
        'Forward P/E': info.get('forwardPE'),
        'PEG Ratio': info.get('pegRatio'),
        'Market Cap': info.get('marketCap'),
        'Revenue': info.get('totalRevenue'),
        'Profit Margin': info.get('profitMargins'),
        'Debt/Equity': info.get('debtToEquity'),
        'ROE': info.get('returnOnEquity'),
    }

    print(f"\n   Data available:")
    for key, value in fundamental_data.items():
        if value:
            print(f"      • {key}: {value}")

    print(f"\n   ✅ สามารถบอก:")
    print(f"      • บริษัทมี fundamentals ดีไหม")
    print(f"      • ราคาแพงหรือถูกเมื่อเทียบกับรายได้")
    print(f"      • บริษัทมีหนี้เยอะไหม")

    print(f"\n   ❌ ไม่สามารถบอก:")
    print(f"      • จะขึ้น/ลง ใน 7-14 วันข้างหน้า")
    print(f"      • Short-term catalyst")

    # 3. Earnings & Events
    print("\n3️⃣  EARNINGS & EVENTS DATA")
    print("-" * 70)

    earnings_date = info.get('earningsDate')

    print(f"\n   Data available:")
    print(f"      • Next earnings: {earnings_date}")
    print(f"      • Number of analysts: {info.get('numberOfAnalystOpinions')}")
    print(f"      • Recommendation: {info.get('recommendationKey')}")

    print(f"\n   ✅ สามารถบอก:")
    print(f"      • เมื่อไหร่จะมี earnings (catalyst)")
    print(f"      • Analysts คิดว่าอย่างไร")

    print(f"\n   ❌ ไม่สามารถบอก:")
    print(f"      • Earnings จะดีหรือแย่")
    print(f"      • ราคาจะขึ้นหรือลงหลัง earnings")

    # 4. Technical Indicators
    print("\n4️⃣  TECHNICAL INDICATORS (Derived from price)")
    print("-" * 70)

    # Calculate common indicators
    ma20 = hist['Close'].rolling(20).mean().iloc[-1]
    ma50 = hist['Close'].rolling(50).mean().iloc[-1]
    current_price = hist['Close'].iloc[-1]

    delta = hist['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = rsi.iloc[-1]

    print(f"\n   Calculated:")
    print(f"      • MA20: ${ma20:.2f} ({(current_price/ma20-1)*100:+.1f}%)")
    print(f"      • MA50: ${ma50:.2f} ({(current_price/ma50-1)*100:+.1f}%)")
    print(f"      • RSI: {current_rsi:.1f}")

    print(f"\n   ✅ สามารถบอก:")
    print(f"      • Trend (ขาขึ้น/ขาลง)")
    print(f"      • Overbought/Oversold")
    print(f"      • Momentum strength")

    print(f"\n   ❌ ไม่สามารถบอก:")
    print(f"      • ทำไมเกิด trend นี้")
    print(f"      • จะ reverse เมื่อไหร่")

    # 5. Market/Sector Data
    print("\n5️⃣  MARKET & SECTOR DATA")
    print("-" * 70)

    print(f"\n   Data available:")
    print(f"      • Sector: {info.get('sector')}")
    print(f"      • Industry: {info.get('industry')}")
    print(f"      • Beta: {info.get('beta')}")

    print(f"\n   ✅ สามารถบอก:")
    print(f"      • หุ้นนี้เคลื่อนไหวตาม sector ไหม")
    print(f"      • Correlation กับตลาด")

    print(f"\n   ❌ ไม่สามารถบอก:")
    print(f"      • Sector rotation จะเกิดเมื่อไหร่")

    # Summary
    print("\n" + "="*80)
    print("📋 SUMMARY: ข้อมูลที่มี")
    print("="*80)

    data_types = {
        'Price/Volume': {
            'ใช้ได้': ['Momentum', 'Volatility', 'Liquidity'],
            'ไม่ได้': ['Why price moved', 'Future direction']
        },
        'Fundamentals': {
            'ใช้ได้': ['Company quality', 'Valuation'],
            'ไม่ได้': ['Short-term moves', 'Timing']
        },
        'Earnings/Events': {
            'ใช้ได้': ['Catalyst timing', 'Analyst sentiment'],
            'ไม่ได้': ['Result prediction', 'Price reaction']
        },
        'Technical': {
            'ใช้ได้': ['Trend', 'Momentum strength'],
            'ไม่ได้': ['Causation', 'Future moves']
        },
        'Market/Sector': {
            'ใช้ได้': ['Relative strength', 'Correlation'],
            'ไม่ได้': ['Timing', 'Rotation prediction']
        }
    }

    for category, info_dict in data_types.items():
        print(f"\n{category}:")
        print(f"   ✅ ใช้ได้: {', '.join(info_dict['ใช้ได้'])}")
        print(f"   ❌ ไม่ได้: {', '.join(info_dict['ไม่ได้'])}")

    # Key insight
    print("\n" + "="*80)
    print("💡 KEY INSIGHT")
    print("="*80)

    print(f"\n⚠️  **ข้อมูลทั้งหมดที่มี ไม่มีอันไหนบอกได้ว่า:**")
    print(f"   • หุ้นจะขึ้น 5-10% ใน 7-14 วันข้างหน้า")
    print(f"   • ทำไมหุ้นถึงขึ้น")
    print(f"\n✅ **ข้อมูลบอกได้แค่:**")
    print(f"   • หุ้นนี้มีคุณภาพดีไหม (fundamentals)")
    print(f"   • กำลังขึ้น/ลง อยู่ตอนนี้ (momentum)")
    print(f"   • มี catalyst เมื่อไหร่ (earnings)")
    print(f"   • แพง/ถูก เมื่อเทียบกับ fundamentals (valuation)")

    print(f"\n🤔 **คำถาม: ถ้าข้อมูลไม่สามารถบอกอนาคตได้**")
    print(f"   → แล้วเราจะ predict ได้ยังไง?")
    print(f"   → หรือว่าเราไม่ควร predict?")

if __name__ == "__main__":
    analyze_data_sources()
