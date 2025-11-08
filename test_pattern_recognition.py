"""
Test script for Pattern Recognition
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.analysis.technical.pattern_recognizer import PatternRecognizer

def create_sample_data(pattern_type='double_top'):
    """
    สร้างข้อมูลตัวอย่างสำหรับทดสอบ Pattern Recognition
    """
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')

    if pattern_type == 'double_top':
        # สร้าง Double Top pattern
        base_price = 100
        prices = []
        for i in range(100):
            if i < 20:
                prices.append(base_price + i * 0.5)  # ขึ้น
            elif i < 30:
                prices.append(base_price + 20 * 0.5 - (i - 20) * 0.3)  # ลงเล็กน้อย (valley)
            elif i < 50:
                prices.append(base_price + 20 * 0.5 - 10 * 0.3 + (i - 30) * 0.5)  # ขึ้นไปยอดที่ 2
            else:
                prices.append(base_price + 20 * 0.5 - (i - 50) * 0.3)  # ลง

        closes = np.array(prices)
        highs = closes + np.random.uniform(0, 1, 100)
        lows = closes - np.random.uniform(0, 1, 100)
        opens = closes + np.random.uniform(-0.5, 0.5, 100)

    elif pattern_type == 'bullish_engulfing':
        # สร้าง Bullish Engulfing pattern (แท่งสุดท้าย)
        base_price = 100
        closes = base_price + np.random.uniform(-2, 2, 100)
        # แท่งที่ 98 = แดง (ขาลง)
        closes[-2] = 98
        opens = closes.copy()
        opens[-2] = 100
        # แท่งที่ 99 = เขียวใหญ่ (กลืนแท่งแดง)
        closes[-1] = 102
        opens[-1] = 97

        highs = np.maximum(opens, closes) + np.random.uniform(0, 0.5, 100)
        lows = np.minimum(opens, closes) - np.random.uniform(0, 0.5, 100)

    else:  # random
        base_price = 100
        closes = base_price + np.cumsum(np.random.uniform(-1, 1, 100))
        highs = closes + np.random.uniform(0, 1, 100)
        lows = closes - np.random.uniform(0, 1, 100)
        opens = closes + np.random.uniform(-0.5, 0.5, 100)

    df = pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)

    return df

def test_pattern_recognition():
    """
    ทดสอบ Pattern Recognition Module
    """
    print("=" * 60)
    print("🧪 ทดสอบ Pattern Recognition Module")
    print("=" * 60)

    # Test 1: Double Top Pattern
    print("\n📊 Test 1: Double Top Pattern")
    print("-" * 60)
    price_data = create_sample_data('double_top')
    recognizer = PatternRecognizer(price_data, 'TEST_DOUBLE_TOP')

    result = recognizer.detect_all_patterns()

    print(f"Symbol: {result['symbol']}")
    print(f"Total Patterns Detected: {result['total_patterns']}")
    print(f"Summary: {result['summary']}")

    if result['patterns_detected']:
        print("\n🔍 Patterns พบ:")
        for i, pattern in enumerate(result['patterns_detected'], 1):
            print(f"\n  {i}. {pattern['name']} ({pattern['type']})")
            print(f"     Signal: {pattern['signal']}")
            print(f"     Confidence: {pattern['confidence']}%")
            print(f"     Description: {pattern['description']}")
            print(f"     Interpretation: {pattern['interpretation']}")
            if 'key_levels' in pattern:
                print(f"     Key Levels: {pattern['key_levels']}")
    else:
        print("❌ ไม่พบ Pattern (อาจเป็นเพราะข้อมูลสุ่มไม่สมบูรณ์)")

    # Test 2: Bullish Engulfing
    print("\n\n📊 Test 2: Bullish Engulfing Pattern")
    print("-" * 60)
    price_data2 = create_sample_data('bullish_engulfing')
    recognizer2 = PatternRecognizer(price_data2, 'TEST_ENGULFING')

    result2 = recognizer2.detect_all_patterns()

    print(f"Symbol: {result2['symbol']}")
    print(f"Total Patterns Detected: {result2['total_patterns']}")
    print(f"Summary: {result2['summary']}")

    if result2['patterns_detected']:
        print("\n🔍 Patterns พบ:")
        for i, pattern in enumerate(result2['patterns_detected'], 1):
            print(f"\n  {i}. {pattern['name']} ({pattern['type']})")
            print(f"     Signal: {pattern['signal']}")
            print(f"     Confidence: {pattern['confidence']}%")
            print(f"     Description: {pattern['description']}")
    else:
        print("❌ ไม่พบ Pattern")

    # Test 3: Random Data
    print("\n\n📊 Test 3: Random Data (ควรไม่พบ Pattern ชัดเจน)")
    print("-" * 60)
    price_data3 = create_sample_data('random')
    recognizer3 = PatternRecognizer(price_data3, 'TEST_RANDOM')

    result3 = recognizer3.detect_all_patterns()

    print(f"Symbol: {result3['symbol']}")
    print(f"Total Patterns Detected: {result3['total_patterns']}")
    print(f"Summary: {result3['summary']}")

    if result3['patterns_detected']:
        print("\n🔍 Patterns พบ (unexpected):")
        for i, pattern in enumerate(result3['patterns_detected'], 1):
            print(f"  {i}. {pattern['name']} - {pattern['signal']}")

    print("\n" + "=" * 60)
    print("✅ ทดสอบเสร็จสิ้น")
    print("=" * 60)

if __name__ == "__main__":
    test_pattern_recognition()
