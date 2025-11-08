#!/usr/bin/env python3
"""
Test Falling Knife Detection
ทดสอบการแยก Falling Knife (ตกต่อเนื่อง) vs Healthy Pullback (ตกชั่วคราว)
"""

import sys
sys.path.insert(0, 'src')

from api.data_manager import DataManager
from analysis.technical.technical_analyzer import TechnicalAnalyzer

def test_stock(symbol):
    """ทดสอบหุ้นตัวหนึ่ง"""
    print(f'\n{"=" * 80}')
    print(f'📊 Testing: {symbol}')
    print(f'{"=" * 80}')

    try:
        # ดึงข้อมูล (ต้องใช้ 200 วันเพื่อคำนวณ MA200)
        data_manager = DataManager()
        stock_data = data_manager.get_price_data(symbol, period='1y', interval='1d')

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
        dip = market_state.get('dip_opportunity', {})
        falling_knife = market_state.get('falling_knife', {})

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

        # แสดง Dip
        print(f'💚 DIP OPPORTUNITY:')
        print(f'   Is Dip: {dip.get("is_dip")}')
        print(f'   Quality: {dip.get("dip_quality")}')
        print(f'   Score: {dip.get("opportunity_score")}/100')
        if dip.get('falling_knife_penalty'):
            print(f'   ⚠️ Falling Knife Penalty: -{dip.get("falling_knife_penalty")} pts')
        print()

        # แสดง Falling Knife
        print(f'🔪 FALLING KNIFE ANALYSIS:')
        print(f'   Is Falling Knife: {falling_knife.get("is_falling_knife")}')
        print(f'   Risk Level: {falling_knife.get("risk_level")}')
        print(f'   Risk Score: {falling_knife.get("risk_score")}/100')
        print()

        if falling_knife.get('warnings'):
            print(f'   ⚠️ Warnings:')
            for w in falling_knife.get('warnings', []):
                print(f'      • {w}')
            print()

        if falling_knife.get('reasons'):
            print(f'   ✅ Positive Signs:')
            for r in falling_knife.get('reasons', []):
                print(f'      • {r}')
            print()

        print(f'   💡 Recommendation:')
        print(f'      {falling_knife.get("recommendation")}')
        print()

        # สรุป
        print(f'📝 SUMMARY:')
        if falling_knife.get('is_falling_knife'):
            print(f'   🔪 FALLING KNIFE ({falling_knife.get("risk_level")} risk)')
            print(f'      → อย่าช้อน! ตกต่อเนื่อง')
        elif dip.get('is_dip'):
            print(f'   💰 HEALTHY PULLBACK')
            print(f'      → จุดช้อนที่ดี ช้อนได้!')
        else:
            print(f'   ⏸️ NEUTRAL')
            print(f'      → รอดูต่อ')

    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()

def main():
    print('\n' + '=' * 80)
    print('🧪 FALLING KNIFE DETECTION TEST')
    print('=' * 80)
    print()
    print('ทดสอบว่าระบบแยกได้หรือไม่ระหว่าง:')
    print('  🔪 Falling Knife = ตกต่อเนื่อง (อย่าช้อน)')
    print('  💰 Healthy Pullback = ตกชั่วคราว (ช้อนได้)')
    print()

    # ทดสอบหุ้นหลากหลายแบบ
    stocks_to_test = [
        'MARA',   # Crypto mining - มักผันผวน
        'COIN',   # Crypto exchange - ผันผวนมาก
        'NVDA',   # AI leader - uptrend แข็งแรง
        'SMCI',   # AI infrastructure - ผันผวน
        'TSLA',   # EV leader
        'INTC',   # Chip - downtrend ยาว (ควรเป็น Falling Knife)
    ]

    for symbol in stocks_to_test:
        test_stock(symbol)

    print('\n' + '=' * 80)
    print('✅ Testing Complete')
    print('=' * 80)

if __name__ == '__main__':
    main()
