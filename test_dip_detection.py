#!/usr/bin/env python3
"""
Test Dip Detection with Relaxed Thresholds
ทดสอบว่า MARA และ COIN ตรวจจับได้หรือไม่
"""

import sys
sys.path.insert(0, 'src')

from api.data_manager import DataManager
from analysis.technical.technical_analyzer import TechnicalAnalyzer
from datetime import datetime

def test_stock(symbol):
    """ทดสอบหุ้นตัวหนึ่ง"""
    print(f'\n{"=" * 80}')
    print(f'📊 Testing: {symbol}')
    print(f'{"=" * 80}')

    try:
        # ดึงข้อมูล
        data_manager = DataManager()
        stock_data = data_manager.get_price_data(symbol, period='3mo', interval='1d')

        if stock_data.empty:
            print(f'❌ ไม่สามารถดึงข้อมูล {symbol} ได้')
            return

        # วิเคราะห์
        analyzer = TechnicalAnalyzer(stock_data)
        results = analyzer.analyze()

        # ดึงข้อมูล
        current_price = results.get('last_price', 0)
        indicators = results.get('indicators', {})
        rsi = indicators.get('rsi', 0)

        market_state = results.get('market_state_analysis', {})
        overext = market_state.get('overextension', {})
        dip = market_state.get('dip_opportunity', {})

        # คำนวณ pullback
        price_data = stock_data
        if len(price_data) >= 20:
            recent_high = price_data['high'].tail(20).max()
            pullback_pct = ((current_price - recent_high) / recent_high) * 100
        else:
            pullback_pct = 0

        print(f'\n💰 Current Price: ${current_price:.2f}')
        print(f'📈 RSI: {rsi:.1f}')
        print(f'📉 Pullback from 20d high: {pullback_pct:.1f}%')
        print()

        # แสดง Overextension
        print(f'🔴 OVEREXTENSION:')
        print(f'   Is Overextended: {overext.get("is_overextended")}')
        print(f'   Risk Level: {overext.get("risk_level")}')
        print(f'   Severity Score: {overext.get("severity_score")}/100')
        if overext.get('warnings'):
            print(f'   Warnings:')
            for w in overext.get('warnings', []):
                print(f'      • {w}')
        print()

        # แสดง Dip
        print(f'💚 DIP OPPORTUNITY:')
        print(f'   Is Dip: {dip.get("is_dip")}')
        print(f'   Dip Quality: {dip.get("dip_quality")}')
        print(f'   Opportunity Score: {dip.get("opportunity_score")}/100')
        print(f'   DEBUG - Details: {dip.get("details")}')
        if dip.get('positives'):
            print(f'   Positives:')
            for p in dip.get('positives', []):
                print(f'      • {p}')
        print()
        print(f'   💡 Suggestion: {dip.get("entry_suggestion")}')

        # สรุป
        print()
        if dip.get('is_dip'):
            print('✅ SUCCESS: จับได้ว่าเป็นจุดช้อน!')
        elif overext.get('is_overextended'):
            print('⚠️ WARNING: จับได้ว่าติดดอย!')
        else:
            print('❌ FAIL: ไม่จับได้ (คะแนนไม่ถึง)')

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

def main():
    print('\n' + '=' * 80)
    print('🧪 DIP DETECTION TEST - RELAXED THRESHOLDS')
    print('=' * 80)
    print()
    print('Relaxed Criteria:')
    print('  Overextension: severity_score >= 35')
    print('    - RSI > 70 (20 pts), > 75 (28 pts), > 80 (35 pts)')
    print('    - Price > SMA20 by 5% (15 pts), 7% (22 pts), 10% (30 pts)')
    print('    - 5d gain > 10% (12 pts), > 15% (20 pts), > 20% (28 pts)')
    print()
    print('  Dip: opportunity_score >= 40')
    print('    - Pullback 5-10% (28 pts), 10-15% (35 pts), 15-25% (38 pts)')
    print('    - RSI 30-55 (25 pts), 38-48 (32 pts)')
    print('    - Near Support <= 2% (25 pts), <= 3% (15 pts)')
    print('    - Volume decreasing (10 pts)')
    print()

    # ทดสอบหุ้นที่น่าจะเป็น DIP
    stocks_to_test = ['MARA', 'COIN', 'SMCI', 'NVDA', 'TSLA']

    for symbol in stocks_to_test:
        test_stock(symbol)

    print('\n' + '=' * 80)
    print('✅ Testing Complete')
    print('=' * 80)

if __name__ == '__main__':
    main()
