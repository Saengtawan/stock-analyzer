"""
ตัวอย่างการใช้งาน Price Change Analyzer
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

from src.main import StockAnalyzer
import json

def format_price_change_analysis(analysis_result):
    """แสดงผลการวิเคราะห์การเปลี่ยนแปลงราคา"""

    price_change = analysis_result.get('enhanced_analysis', {}).get('price_change_analysis', {})

    if not price_change or 'error' in price_change:
        print("❌ ไม่สามารถวิเคราะห์การเปลี่ยนแปลงราคาได้")
        return

    print("\n" + "="*80)
    print("📊 การวิเคราะห์การเปลี่ยนแปลงราคา - Why Price Moved?")
    print("="*80)

    # 1. การเปลี่ยนแปลงราคาล่าสุด
    print(f"\n💰 ราคาปัจจุบัน: ${price_change.get('current_price', 0):.2f}")
    print(f"💰 ราคาก่อนหน้า: ${price_change.get('previous_price', 0):.2f}")

    change_amount = price_change.get('change_amount', 0)
    change_percent = price_change.get('change_percent', 0)
    direction = price_change.get('direction', 'NEUTRAL')

    if direction == 'UP':
        print(f"📈 เปลี่ยนแปลง: +${abs(change_amount):.2f} (+{abs(change_percent):.2f}%)")
    elif direction == 'DOWN':
        print(f"📉 เปลี่ยนแปลง: -${abs(change_amount):.2f} (-{abs(change_percent):.2f}%)")
    else:
        print(f"↔️ เปลี่ยนแปลง: ${change_amount:.2f} ({change_percent:.2f}%)")

    # 2. สรุปสั้นๆ
    summary = price_change.get('summary', '')
    if summary:
        print(f"\n📝 สรุป: {summary}")

    # 3. สาเหตุการเปลี่ยนแปลงราคา
    reasons = price_change.get('reasons', [])
    if reasons:
        print(f"\n🔍 สาเหตุที่ราคา{'ขึ้น' if direction == 'UP' else 'ลง' if direction == 'DOWN' else 'ไม่เปลี่ยนแปลง'}:")
        for i, reason in enumerate(reasons[:5], 1):
            importance = reason.get('importance', 0)
            stars = '⭐' * min(int(importance / 20), 5)
            print(f"\n   {i}. {reason.get('reason', 'N/A')} {stars}")
            print(f"      📌 {reason.get('detail', 'N/A')}")

    # 4. การเปลี่ยนแปลงในช่วงเวลาต่างๆ
    period_changes = price_change.get('period_changes', {})
    if period_changes:
        print(f"\n📅 การเปลี่ยนแปลงราคาในช่วงเวลาต่างๆ:")
        period_names = {
            '1_day': '1 วัน',
            '5_days': '1 สัปดาห์',
            '20_days': '1 เดือน',
            '60_days': '3 เดือน',
            '252_days': '1 ปี'
        }
        for period, data in period_changes.items():
            period_name = period_names.get(period, period)
            change_pct = data.get('change_percent', 0)
            direction_symbol = '📈' if change_pct > 0 else '📉' if change_pct < 0 else '↔️'
            print(f"   {direction_symbol} {period_name}: {change_pct:+.2f}%")

    # 5. แรงซื้อ/แรงขาย
    pressure = price_change.get('buying_selling_pressure', {})
    if pressure:
        print(f"\n💪 แรงซื้อ/แรงขาย:")
        pressure_type = pressure.get('pressure', 'NEUTRAL')
        strength = pressure.get('strength', 0)

        if pressure_type == 'BUYING':
            print(f"   🟢 แรงซื้อ: {strength:.1f}% ({pressure.get('buying_days', 0)}/5 วัน)")
        elif pressure_type == 'SELLING':
            print(f"   🔴 แรงขาย: {strength:.1f}% ({pressure.get('selling_days', 0)}/5 วัน)")
        else:
            print(f"   ⚪ สมดุล: {strength:.1f}%")

        interpretation = pressure.get('interpretation', '')
        if interpretation:
            print(f"   📊 {interpretation}")

    # 6. ความแข็งแกร่งของเทรนด์
    trend = price_change.get('trend_strength', {})
    if trend:
        print(f"\n📈 ความแข็งแกร่งของเทรนด์:")
        trend_type = trend.get('trend', 'NEUTRAL')
        strength = trend.get('strength', 0)

        if trend_type == 'UPTREND':
            print(f"   🟢 เทรนด์ขาขึ้น (ความแข็งแกร่ง: {strength:.1f}/100)")
        elif trend_type == 'DOWNTREND':
            print(f"   🔴 เทรนด์ขาลง (ความแข็งแกร่ง: {strength:.1f}/100)")
        else:
            print(f"   ⚪ Sideways (ความแข็งแกร่ง: {strength:.1f}/100)")

        interpretation = trend.get('interpretation', '')
        if interpretation:
            print(f"   📊 {interpretation}")

    # 7. จุดสำคัญที่ส่งผลต่อราคา
    key_levels = price_change.get('key_levels', {})
    if key_levels:
        print(f"\n🎯 จุดสำคัญ (Support/Resistance):")
        print(f"   ⬆️ Resistance: ${key_levels.get('resistance_1', 0):.2f} (+{key_levels.get('distance_to_resistance', 0):.2f}%)")
        print(f"   ⬇️ Support: ${key_levels.get('support_1', 0):.2f} (-{key_levels.get('distance_to_support', 0):.2f}%)")

    # 8. ปริมาณการซื้อขาย
    volume_analysis = price_change.get('volume_analysis', {})
    if volume_analysis and volume_analysis.get('volume_status') != 'N/A':
        print(f"\n📊 ปริมาณการซื้อขาย:")
        volume_status = volume_analysis.get('volume_status', 'NORMAL')

        status_symbols = {
            'VERY_HIGH': '🔥🔥🔥',
            'HIGH': '🔥🔥',
            'NORMAL': '✅',
            'LOW': '⚠️',
            'VERY_LOW': '⚠️⚠️'
        }

        symbol = status_symbols.get(volume_status, '✅')
        print(f"   {symbol} สถานะ: {volume_status}")
        print(f"   📊 {volume_analysis.get('interpretation', '')}")

    # 9. การประเมินว่าควรขายกำไรหรือยัง (NEW!)
    profit_taking = price_change.get('profit_taking_analysis', {})
    if profit_taking and profit_taking.get('applicable', False):
        print(f"\n{'='*80}")
        print("💡 การประเมิน: ควรขายกำไรหรือยัง?")
        print(f"{'='*80}")

        action = profit_taking.get('action', 'N/A')
        confidence = profit_taking.get('confidence', 'LOW')
        hold_prob = profit_taking.get('hold_probability', 0)
        sell_prob = profit_taking.get('sell_probability', 0)

        # แสดงคำแนะนำหลัก
        confidence_symbols = {
            'HIGH': '🟢',
            'MEDIUM': '🟡',
            'LOW': '🔴'
        }
        conf_symbol = confidence_symbols.get(confidence, '⚪')

        print(f"\n{conf_symbol} คำแนะนำ: {action}")
        print(f"   ความมั่นใจ: {confidence}")

        # แสดงความน่าจะเป็น
        print(f"\n📊 ความน่าจะเป็น:")
        print(f"   💎 โอกาสที่ควรถือต่อ: {hold_prob:.1f}%")
        print(f"   💰 โอกาสที่ควรขายกำไร: {sell_prob:.1f}%")

        # แสดง Progress Bar
        hold_bar = '█' * int(hold_prob / 5)
        sell_bar = '█' * int(sell_prob / 5)
        print(f"\n   💎 ถือต่อ  : [{hold_bar:<20}] {hold_prob:.1f}%")
        print(f"   💰 ขายกำไร: [{sell_bar:<20}] {sell_prob:.1f}%")

        # แสดงเหตุผลที่ควรถือต่อ
        reasons_hold = profit_taking.get('reasons_to_hold', [])
        if reasons_hold:
            print(f"\n✅ เหตุผลที่ควรถือต่อ:")
            for i, reason in enumerate(reasons_hold[:3], 1):
                print(f"   {i}. {reason.get('reason', 'N/A')}")
                print(f"      📝 {reason.get('detail', 'N/A')}")

        # แสดงเหตุผลที่ควรขาย
        reasons_sell = profit_taking.get('reasons_to_sell', [])
        if reasons_sell:
            print(f"\n⚠️ เหตุผลที่ควรขายกำไร:")
            for i, reason in enumerate(reasons_sell[:3], 1):
                print(f"   {i}. {reason.get('reason', 'N/A')}")
                print(f"      📝 {reason.get('detail', 'N/A')}")

        # แสดงคำอธิบายละเอียด
        explanation = profit_taking.get('explanation', '')
        if explanation:
            print(f"\n📖 คำอธิบายเพิ่มเติม:")
            print(f"   {explanation.replace(chr(10), chr(10) + '   ')}")

    print("\n" + "="*80)


def main():
    """ตัวอย่างการใช้งาน"""
    print("🚀 ระบบวิเคราะห์การเปลี่ยนแปลงราคาหุ้น")
    print("="*80)

    # เลือกหุ้นที่ต้องการวิเคราะห์
    symbol = input("\nใส่ชื่อหุ้น (เช่น AAPL, MSFT, TSLA): ").strip().upper()

    if not symbol:
        symbol = "AAPL"  # ค่า default

    print(f"\n📊 กำลังวิเคราะห์ {symbol}...")

    try:
        # สร้าง analyzer
        analyzer = StockAnalyzer(trading_strategy='swing_trading')

        # วิเคราะห์หุ้น
        results = analyzer.analyze_stock(
            symbol=symbol,
            time_horizon='medium',
            include_ai_analysis=False  # ปิด AI เพื่อความเร็ว
        )

        if 'error' in results:
            print(f"❌ เกิดข้อผิดพลาด: {results['error']}")
            return

        # แสดงผลการวิเคราะห์การเปลี่ยนแปลงราคา
        format_price_change_analysis(results)

        # แสดงข้อมูลเพิ่มเติม
        print("\n📈 ข้อมูลเพิ่มเติม:")
        print(f"   • คำแนะนำ: {results.get('final_recommendation', {}).get('recommendation', 'N/A')}")
        print(f"   • คะแนน: {results.get('signal_analysis', {}).get('final_score', {}).get('total_score', 0):.1f}/10")
        print(f"   • ความมั่นใจ: {results.get('confidence_level', 'N/A')}")

        # บันทึกผลลัพธ์
        save = input("\n💾 บันทึกผลลัพธ์เป็นไฟล์? (y/n): ").strip().lower()
        if save == 'y':
            filename = f"{symbol}_price_change_analysis.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results.get('enhanced_analysis', {}).get('price_change_analysis', {}),
                         f, ensure_ascii=False, indent=2)
            print(f"✅ บันทึกไฟล์: {filename}")

    except Exception as e:
        print(f"\n❌ เกิดข้อผิดพลาด: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
