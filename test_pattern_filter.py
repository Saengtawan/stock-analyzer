"""
Test Pattern Filter - ทดสอบการกรอง Pattern ที่หมดอายุ
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.analysis.technical.pattern_recognizer import PatternRecognizer

def create_mara_like_data():
    """
    สร้างข้อมูลคล้าย MARA: ราคาปัจจุบัน $18.74 แต่มี Pattern ที่ $13-15 (หมดอายุ)
    """
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')

    prices = []
    for i in range(100):
        if i < 30:
            # ช่วงแรก: ราคาอยู่ที่ $13-15 (มี Double Top ที่นี่)
            prices.append(13 + np.sin(i * 0.3) * 1.5 + np.random.uniform(-0.2, 0.2))
        elif i < 50:
            # ช่วงกลาง: ขึ้นค่อยๆ จาก $14 → $17
            prices.append(14 + (i - 30) * 0.15 + np.random.uniform(-0.2, 0.2))
        else:
            # ช่วงท้าย: ราคาอยู่ที่ $18-19 (ราคาปัจจุบัน)
            prices.append(18 + np.sin((i - 50) * 0.2) * 0.5 + np.random.uniform(-0.3, 0.3))

    closes = np.array(prices)
    # Force ราคาสุดท้ายเป็น $18.74
    closes[-1] = 18.74

    highs = closes + np.random.uniform(0, 0.3, 100)
    lows = closes - np.random.uniform(0, 0.3, 100)
    opens = closes + np.random.uniform(-0.2, 0.2, 100)

    df = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.randint(5000000, 15000000, 100)
    }, index=dates)

    return df

def test_pattern_filter():
    """
    ทดสอบการกรอง Pattern ที่หมดอายุ
    """
    print("=" * 70)
    print("🧪 ทดสอบการกรอง Pattern ที่หมดอายุ (Expired Pattern Filter)")
    print("=" * 70)

    # สร้างข้อมูลคล้าย MARA
    price_data = create_mara_like_data()
    current_price = price_data['close'].iloc[-1]

    print(f"\n📊 ข้อมูลทดสอบ:")
    print(f"   - ช่วงแรก (วันที่ 0-30): ราคา $13-15 (มี Pattern เก่า)")
    print(f"   - ช่วงกลาง (วันที่ 30-50): ราคาขึ้นเป็น $14-17")
    print(f"   - ช่วงท้าย (วันที่ 50-100): ราคา $18-19")
    print(f"   - ราคาปัจจุบัน: ${current_price:.2f}")

    # รัน Pattern Recognition
    recognizer = PatternRecognizer(price_data, 'TEST_MARA')
    result = recognizer.detect_all_patterns()

    print(f"\n🔍 ผลการตรวจจับ:")
    print(f"   - Total Patterns Detected: {result['total_patterns']}")
    print(f"   - Summary: {result['summary']}")

    if result['patterns_detected']:
        print(f"\n✅ Patterns ที่ผ่านการกรอง (ยังไม่หมดอายุ):")
        for i, pattern in enumerate(result['patterns_detected'], 1):
            print(f"\n  {i}. {pattern['name']} ({pattern['type']})")
            print(f"     Signal: {pattern['signal']}")
            print(f"     Confidence: {pattern['confidence']}%")

            if 'key_levels' in pattern:
                print(f"     Key Levels:")
                for key, value in pattern['key_levels'].items():
                    distance_pct = abs(value - current_price) / current_price * 100
                    print(f"       • {key}: ${value:.2f} (ห่าง {distance_pct:.1f}%)")
    else:
        print("\n❌ ไม่พบ Pattern ที่ใช้งานได้ (ทั้งหมดถูกกรองออก)")

    print("\n" + "=" * 70)
    print("✅ ทดสอบเสร็จสิ้น")
    print("=" * 70)
    print("\n💡 สรุป:")
    print("   - Pattern ที่ Key Levels ห่างจากราคาปัจจุบันเกิน 10% จะถูกกรองออก")
    print("   - เหลือแค่ Pattern ที่ยัง relevant กับราคาปัจจุบัน")

if __name__ == "__main__":
    test_pattern_filter()
