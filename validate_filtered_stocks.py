#!/usr/bin/env python3
"""
Validate Filtered Stocks - ตรวจสอบว่าหุ้นที่โดนกรองออกนั้นถูกต้องหรือไม่
=====================================================================

หุ้นที่ระบบเจอแต่กรองออก:
- BILL (49.2), SYNA (50.4), CRSP (52.7), AI (44.3)
- PATH, BCRX, ATEC, RIVN, AZTA, POWI, LITE

มาดูว่า:
1. ราคาเป็นยังไงช่วงที่ผ่านมา (5-30 วัน)
2. ระบบกรองออกถูกหรือผิด
3. ถ้าเราซื้อจะได้กำไรหรือขาดทุน
"""

import sys
sys.path.insert(0, 'src')

import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd

# Stocks that were found but filtered out
FILTERED_STOCKS = [
    ('BILL', 49.2),
    ('SYNA', 50.4),
    ('CRSP', 52.7),
    ('AI', 44.3),
    ('PATH', 41.1),
    ('BCRX', 45.8),
    ('ATEC', 37.6),
    ('RIVN', 38.7),
    ('AZTA', 36.7),
    ('POWI', 39.0),
    ('LITE', 29.0),
]

print("=" * 80)
print("🔍 VALIDATION: ระบบกรองหุ้นเหล่านี้ถูกหรือผิด?")
print("=" * 80)
print("\nหุ้นที่ระบบเจอแต่กรองออก (composite score 29-52):")
for symbol, score in FILTERED_STOCKS:
    print(f"  • {symbol:6} (Score: {score:.1f})")

print("\n" + "=" * 80)
print("📊 วิเคราะห์ราคาย้อนหลัง")
print("=" * 80)

# Check price performance over different periods
periods = {
    '5 วันที่แล้ว': 5,
    '10 วันที่แล้ว': 10,
    '30 วันที่แล้ว': 30,
}

results = []

for symbol, composite_score in FILTERED_STOCKS:
    print(f"\n{symbol} (Composite Score: {composite_score:.1f})")
    print("-" * 60)

    try:
        # Get 60 days of data
        stock = yf.Ticker(symbol)
        hist = stock.history(period='60d')

        if hist.empty:
            print(f"  ❌ No data available")
            continue

        current_price = hist['Close'].iloc[-1]

        stock_results = {
            'symbol': symbol,
            'composite_score': composite_score,
            'current_price': current_price,
        }

        # Check performance over different periods
        for period_name, days in periods.items():
            if len(hist) >= days:
                past_price = hist['Close'].iloc[-days]
                change_pct = ((current_price - past_price) / past_price) * 100

                emoji = "📉" if change_pct < -2 else "📈" if change_pct > 2 else "➡️"
                print(f"  {emoji} {period_name:20}: {change_pct:+6.2f}%")

                stock_results[f'{days}d_return'] = change_pct
            else:
                print(f"  ⚠️  {period_name:20}: ข้อมูลไม่พอ")
                stock_results[f'{days}d_return'] = None

        # Check if trending down
        if len(hist) >= 20:
            ma5 = hist['Close'].tail(5).mean()
            ma20 = hist['Close'].tail(20).mean()

            trend = "📉 DOWNTREND" if ma5 < ma20 else "📈 UPTREND"
            print(f"  {trend} (MA5: ${ma5:.2f}, MA20: ${ma20:.2f})")

            stock_results['trend'] = 'DOWN' if ma5 < ma20 else 'UP'

        results.append(stock_results)

    except Exception as e:
        print(f"  ❌ Error: {e}")

# Summary
print("\n" + "=" * 80)
print("📊 สรุปผลการวิเคราะห์")
print("=" * 80)

if results:
    df = pd.DataFrame(results)

    # Calculate averages
    print(f"\nจำนวนหุ้นที่วิเคราะห์: {len(results)} ตัว\n")

    for days in [5, 10, 30]:
        col = f'{days}d_return'
        if col in df.columns:
            valid_returns = df[col].dropna()
            if len(valid_returns) > 0:
                avg_return = valid_returns.mean()
                winners = (valid_returns > 0).sum()
                losers = (valid_returns < 0).sum()

                emoji = "❌" if avg_return < -2 else "✅" if avg_return > 2 else "⚠️"
                print(f"{emoji} ย้อนหลัง {days} วัน:")
                print(f"   ค่าเฉลี่ย Return: {avg_return:+6.2f}%")
                print(f"   ขึ้น: {winners} ตัว | ลง: {losers} ตัว")
                print()

    # Trend analysis
    if 'trend' in df.columns:
        downtrend_count = (df['trend'] == 'DOWN').sum()
        uptrend_count = (df['trend'] == 'UP').sum()

        print(f"📈 Trend Analysis:")
        print(f"   Uptrend:   {uptrend_count} ตัว")
        print(f"   Downtrend: {downtrend_count} ตัว")

    # Best and worst
    if '10d_return' in df.columns:
        df_sorted = df.sort_values('10d_return', ascending=False)

        print(f"\n✅ Top 3 Performers (10 วัน):")
        for i, row in df_sorted.head(3).iterrows():
            ret = row.get('10d_return', 0)
            print(f"   {row['symbol']:6} {ret:+6.2f}%")

        print(f"\n❌ Bottom 3 Performers (10 วัน):")
        for i, row in df_sorted.tail(3).iterrows():
            ret = row.get('10d_return', 0)
            print(f"   {row['symbol']:6} {ret:+6.2f}%")

# Final verdict
print("\n" + "=" * 80)
print("⚖️  VERDICT: ระบบกรองออกถูกหรือผิด?")
print("=" * 80)

if results:
    df = pd.DataFrame(results)

    # Calculate if filtering was correct
    if '10d_return' in df.columns:
        avg_10d = df['10d_return'].dropna().mean()

        if avg_10d < -2:
            print(f"""
✅ ระบบกรองออก**ถูกต้อง**!

หุ้นเหล่านี้เฉลี่ยลง {avg_10d:.2f}% ใน 10 วันที่ผ่านมา
ถ้าเราซื้อตอนนั้น จะขาดทุนเฉลี่ย {avg_10d:.2f}%!

การที่ระบบกรองออก = **ป้องกันคุณจากการขาดทุน**

🎯 Filters ทำงานได้ดี:
- Alt Data Signals < 3 → ไม่มี confirmation พอ
- Technical/AI scores ต่ำ → momentum ไม่แข็งแกร่ง
- Tiered Quality → ป้องกันหุ้นเสี่ยง

💡 บทเรียน: "0 results" ≠ "broken system"
           "0 results" = "No good opportunities right now"
""")
        elif avg_10d > 2:
            print(f"""
❌ ระบบกรองออก**ผิด**!

หุ้นเหล่านี้เฉลี่ยขึ้น {avg_10d:.2f}% ใน 10 วันที่ผ่านมา
ถ้าเราซื้อได้ จะกำไรเฉลี่ย {avg_10d:.2f}%!

การที่ระบบกรองออก = **พลาดโอกาสทำกำไร**

💡 ควรผ่อนคลาย filters:
- ลด Alt Data Signals จาก 3 → 2
- ลด Technical/AI จาก 30 → 20
- Relax Tiered Quality thresholds
""")
        else:
            print(f"""
⚠️  **กลาง ๆ** (เฉลี่ย {avg_10d:+.2f}%)

หุ้นเหล่านี้แทบไม่ได้ขึ้นหรือลงมาก
ระบบกรองออก = ถูกต้องพอสมควร

อาจจะ:
- ผ่อนคลาย filters เล็กน้อยถ้าต้องการหาโอกาสเพิ่ม
- หรือรอ market regime ดีขึ้นแล้วค่อยเทรด

Current market (SIDEWAYS) → ควรระมัดระวัง
""")

print("\n" + "=" * 80)
print("✅ VALIDATION COMPLETE")
print("=" * 80)
print("\nคำแนะนำ: ให้คุณดูผลด้านบนแล้วตัดสินใจเองว่า")
print("         ควรผ่อนคลาย filters หรือเก็บไว้แบบเดิม")
