#!/usr/bin/env python3
"""
Demo Script: แสดงตัวอย่าง Overextension และ Dip Detection

วิธีใช้:
python test_overextension_dip_demo.py

หรือใช้ในเว็บโดยวิเคราะห์หุ้นที่มีลักษณะดังนี้:
- Overextended: หุ้นที่ rally แรงมาก เช่น AI stocks ช่วง boom
- Dip: หุ้นที่ pullback จากจุดสูงสุด
"""

import sys
sys.path.insert(0, 'src')

from analysis.technical.technical_analyzer import TechnicalAnalyzer
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_overextended_stock_data():
    """สร้างข้อมูลหุ้นที่ติดดอย (RSI สูง, ราคาขึ้นเร็ว)"""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')

    # สร้างราคาที่ขึ้นแรงมาก (rally)
    base_price = 100
    prices = []
    for i in range(60):
        if i < 40:
            # ขึ้นปกติก่อน
            price = base_price + (i * 0.5) + np.random.randn() * 0.5
        else:
            # ขึ้นแรงมากในช่วงท้าย (rapid rally)
            price = prices[-1] + 2 + np.random.randn() * 0.5
        prices.append(max(price, base_price))

    # สร้าง OHLCV
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        high = close + abs(np.random.randn() * 0.3)
        low = close - abs(np.random.randn() * 0.3)
        open_price = (high + low) / 2
        volume = 1000000 + np.random.randint(-100000, 100000)

        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'symbol': 'OVEREXT'
        })

    return pd.DataFrame(data)

def create_dip_stock_data():
    """สร้างข้อมูลหุ้นที่เป็นจุดช้อน (pullback จากจุดสูง)"""
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')

    # สร้างราคาที่ขึ้นแล้วลงมา (dip)
    base_price = 100
    prices = []
    for i in range(60):
        if i < 30:
            # ขึ้นก่อน
            price = base_price + (i * 1.5) + np.random.randn() * 0.5
        elif i < 40:
            # จุดสูงสุด
            price = prices[-1] + np.random.randn() * 0.5
        else:
            # ลงมา (pullback 15%)
            price = prices[-1] - 1.2 + np.random.randn() * 0.3
        prices.append(max(price, base_price * 0.8))

    # สร้าง OHLCV
    data = []
    for i, (date, close) in enumerate(zip(dates, prices)):
        high = close + abs(np.random.randn() * 0.3)
        low = close - abs(np.random.randn() * 0.3)
        open_price = (high + low) / 2
        # Volume ลดลงในช่วง dip (selling exhaustion)
        volume = 1000000 - (i * 10000) if i >= 40 else 1000000 + np.random.randint(-100000, 100000)

        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': max(volume, 500000),
            'symbol': 'DIP'
        })

    return pd.DataFrame(data)

def analyze_demo_stock(stock_data, stock_name):
    """วิเคราะห์หุ้นตัวอย่าง"""
    print(f'\n{"=" * 80}')
    print(f'📊 {stock_name}')
    print(f'{"=" * 80}')

    analyzer = TechnicalAnalyzer(stock_data)
    results = analyzer.analyze()

    market_state = results.get('market_state_analysis', {})
    overext = market_state.get('overextension', {})
    dip = market_state.get('dip_opportunity', {})
    indicators = results.get('indicators', {})

    current_price = results.get('last_price', 0)
    rsi = indicators.get('rsi', 0)

    print(f'Current Price: ${current_price:.2f}')
    print(f'RSI: {rsi:.1f}')
    print(f'Market State: {market_state.get("current_state", "UNKNOWN")}')
    print()

    # แสดง Overextension
    if overext.get('is_overextended'):
        print('🔴 คำเตือน: ราคาขึ้นเกินแล้ว - อย่าซื้อตอนนี้!')
        print()
        print(f'ระดับเสี่ยง: {overext.get("risk_level")} (คะแนน {overext.get("severity_score")}/100)')
        print()
        print('สาเหตุ:')
        for warning in overext.get('warnings', []):
            print(f'  • {warning}')
        print()
        print(f'💡 คำแนะนำ: {overext.get("recommendation")}')
    else:
        print('✅ ไม่ติดดอย (Overextension: NO)')

    print()

    # แสดง Dip Opportunity
    if dip.get('is_dip'):
        print('💰 จุดช้อนที่ดี - โอกาสเข้าซื้อ!')
        print()
        print(f'คุณภาพ: {dip.get("dip_quality")} (คะแนนโอกาส {dip.get("opportunity_score")}/100)')
        print()
        print('จุดเด่น:')
        for positive in dip.get('positives', []):
            print(f'  • {positive}')
        print()
        print(f'💡 คำแนะนำ: {dip.get("entry_suggestion")}')
        if dip.get('expected_bounce'):
            print(f'{dip.get("expected_bounce")}')
    else:
        print('❌ ไม่ใช่จุดช้อน (Dip: NO)')

    print()

if __name__ == '__main__':
    print('\n' + '=' * 80)
    print('🧪 DEMO: Overextension & Dip Detection')
    print('=' * 80)
    print()
    print('นี่คือตัวอย่างการทำงานของระบบ โดยใช้ข้อมูลจำลอง')
    print('ในการใช้งานจริง ให้วิเคราะห์หุ้นผ่านเว็บ UI')
    print()

    # ทดสอบหุ้นที่ติดดอย
    print('📍 Test 1: หุ้นที่ราคาขึ้นเกิน (Overextended)')
    overext_data = create_overextended_stock_data()
    analyze_demo_stock(overext_data, 'OVEREXTENDED STOCK (จำลอง)')

    # ทดสอบหุ้นที่เป็นจุดช้อน
    print('\n📍 Test 2: หุ้นที่เป็นจุดช้อน (Dip Opportunity)')
    dip_data = create_dip_stock_data()
    analyze_demo_stock(dip_data, 'DIP OPPORTUNITY STOCK (จำลอง)')

    print('=' * 80)
    print('✅ Demo เสร็จสิ้น')
    print()
    print('📝 วิธีใช้งานจริง:')
    print('1. เปิด http://localhost:5000/analyze')
    print('2. กรอกรหัสหุ้น เช่น MARA, NVDA, TSLA')
    print('3. กดวิเคราะห์')
    print('4. ถ้าหุ้นมีสภาพ overextended หรือ dip จะเห็น box แสดงอัตโนมัติ')
    print('=' * 80)
