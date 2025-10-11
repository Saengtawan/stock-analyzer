#!/usr/bin/env python3
"""
Quick API Test - ทดสอบว่า API ส่งข้อมูล price_change_analysis หรือไม่
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from main import StockAnalyzer
import json

def test_price_change_analysis():
    """ทดสอบ Price Change Analysis"""
    print("🧪 Testing Price Change Analysis API...")
    print("=" * 60)

    # สร้าง analyzer
    analyzer = StockAnalyzer(trading_strategy='swing_trading')

    # วิเคราะห์หุ้น
    symbol = "PATH"
    print(f"\n📊 Analyzing {symbol}...")

    results = analyzer.analyze_stock(
        symbol=symbol,
        time_horizon='short',
        account_value=100000
    )

    # ตรวจสอบว่ามี enhanced_analysis หรือไม่
    if 'enhanced_analysis' in results:
        print("\n✅ Found 'enhanced_analysis'")

        # ตรวจสอบว่ามี price_change_analysis หรือไม่
        if 'price_change_analysis' in results['enhanced_analysis']:
            print("✅ Found 'price_change_analysis'\n")

            pca = results['enhanced_analysis']['price_change_analysis']

            # แสดงข้อมูลสำคัญ
            print("📊 Price Change Analysis Data:")
            print(f"   Current Price: ${pca.get('current_price', 'N/A')}")
            print(f"   Previous Price: ${pca.get('previous_price', 'N/A')}")
            print(f"   Change: {pca.get('change_percent', 0):.2f}%")
            print(f"   Direction: {pca.get('direction', 'N/A')}")

            # แสดงสาเหตุ
            reasons = pca.get('reasons', [])
            if reasons:
                print(f"\n🔍 Top {len(reasons)} Reasons:")
                for i, reason in enumerate(reasons[:3], 1):
                    print(f"   {i}. {reason.get('reason', 'N/A')}")

            # แสดง Profit Taking Analysis
            pta = pca.get('profit_taking_analysis', {})
            if pta and pta.get('applicable'):
                print(f"\n💡 Profit Taking Analysis:")
                print(f"   Recommendation: {pta.get('recommendation', 'N/A')}")
                print(f"   Action: {pta.get('action', 'N/A')}")
                print(f"   Hold Probability: {pta.get('hold_probability', 0):.1f}%")
                print(f"   Sell Probability: {pta.get('sell_probability', 0):.1f}%")

            print("\n" + "=" * 60)
            print("✅ SUCCESS! API is working correctly!")
            print("=" * 60)

            # บันทึกผลลัพธ์
            with open('api_test_result.json', 'w', encoding='utf-8') as f:
                json.dump(pca, f, ensure_ascii=False, indent=2)
            print("\n💾 Full result saved to: api_test_result.json")

        else:
            print("❌ ERROR: 'price_change_analysis' NOT FOUND!")
            print(f"Available keys: {list(results['enhanced_analysis'].keys())}")
    else:
        print("❌ ERROR: 'enhanced_analysis' NOT FOUND!")
        print(f"Available keys: {list(results.keys())}")

if __name__ == "__main__":
    try:
        test_price_change_analysis()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
