#!/usr/bin/env python3
"""
วิเคราะห์ว่า Filter ใหม่กรองหุ้นอะไรออกไป
และหุ้นที่ถูกกรองออกนั้นจริงๆ เป็น winner หรือ loser
"""

import json

# โหลดผลลัพธ์ทั้งสอง
with open('standard_backtest_20260201_171257.json', 'r') as f:
    original = json.load(f)

with open('standard_backtest_20260201_172824.json', 'r') as f:
    new_filter = json.load(f)

original_trades = original['trades']
new_trades = new_filter['trades']

# สร้าง set ของหุ้นที่ trade ในแต่ละ version
original_symbols = set((t['symbol'], t['entry_date']) for t in original_trades)
new_symbols = set((t['symbol'], t['entry_date']) for t in new_trades)

# หาหุ้นที่ถูกกรองออก
filtered_out = original_symbols - new_symbols
new_only = new_symbols - original_symbols

print("=" * 70)
print("วิเคราะห์ผลกระทบของ Filter ใหม่")
print("=" * 70)

print(f"\nOriginal: {len(original_trades)} trades")
print(f"New Filter: {len(new_trades)} trades")
print(f"Filtered Out: {len(filtered_out)} trades")
print(f"New Only: {len(new_only)} trades")

# วิเคราะห์หุ้นที่ถูกกรองออก
filtered_trades = [t for t in original_trades
                   if (t['symbol'], t['entry_date']) in filtered_out]

print("\n" + "=" * 70)
print("หุ้นที่ถูก FILTER ออก (จาก Original)")
print("=" * 70)

winners_filtered = [t for t in filtered_trades if t['pnl_pct'] > 0]
losers_filtered = [t for t in filtered_trades if t['pnl_pct'] <= 0]

print(f"\n  Winners ที่ถูกกรองออก: {len(winners_filtered)}")
print(f"  Losers ที่ถูกกรองออก: {len(losers_filtered)}")

total_profit_lost = sum(t['pnl_pct'] for t in winners_filtered)
total_loss_avoided = sum(t['pnl_pct'] for t in losers_filtered)

print(f"\n  กำไรที่เสียไป: {total_profit_lost:+.2f}%")
print(f"  ขาดทุนที่หลีกเลี่ยงได้: {total_loss_avoided:+.2f}%")
print(f"  Net: {total_profit_lost + total_loss_avoided:+.2f}%")

# แสดงรายละเอียด Winners ที่ถูกกรองออก
print("\n" + "-" * 70)
print("WINNERS ที่ถูกกรองออก (เสียโอกาส!):")
print("-" * 70)

for t in sorted(winners_filtered, key=lambda x: -x['pnl_pct']):
    print(f"  {t['entry_date']} {t['symbol']:6} +{t['pnl_pct']:.2f}% (Score={t['score']}, RSI={t.get('rsi', 'N/A')})")

# แสดงรายละเอียด Losers ที่ถูกกรองออก
print("\n" + "-" * 70)
print("LOSERS ที่ถูกกรองออก (หลีกเลี่ยงได้!):")
print("-" * 70)

for t in sorted(losers_filtered, key=lambda x: x['pnl_pct']):
    print(f"  {t['entry_date']} {t['symbol']:6} {t['pnl_pct']:.2f}% (Score={t['score']}, RSI={t.get('rsi', 'N/A')})")

# วิเคราะห์ว่า Filter ไหนกรองอะไรออก
print("\n" + "=" * 70)
print("วิเคราะห์ว่า Filter ไหนกรองหุ้นดีออกไป")
print("=" * 70)

# ดูว่า winners ที่ถูกกรองมี RSI เท่าไหร่
print("\n### RSI ของ Winners ที่ถูกกรองออก ###")
rsi_values = [t.get('rsi', 0) for t in winners_filtered if t.get('rsi')]
if rsi_values:
    print(f"  Min RSI: {min(rsi_values):.1f}")
    print(f"  Max RSI: {max(rsi_values):.1f}")
    print(f"  Avg RSI: {sum(rsi_values)/len(rsi_values):.1f}")

    below_40 = sum(1 for r in rsi_values if r < 40)
    print(f"  RSI < 40: {below_40}/{len(rsi_values)} ({below_40/len(rsi_values)*100:.0f}%)")

# แนะนำ
print("\n" + "=" * 70)
print("ข้อเสนอแนะ")
print("=" * 70)

print("""
ปัญหา: Filter RSI > 40 กรอง Winners ออกไปเยอะ

เหตุผล: หุ้นที่ RSI ต่ำ (oversold) บางตัวก็ bounce กลับได้ดี
        เช่น KRYS, OKTA, SOUN ที่มี RSI < 40 แต่กำไร 3-8%

แนวทางแก้ไข:
1. ใช้ RSI > 30 แทน RSI > 40 (ผ่อนปรนขึ้น)
2. หรือ ใช้ RSI + SMA20 ร่วมกัน:
   - ถ้า Price > SMA20 → ยอมรับ RSI ต่ำได้
   - ถ้า Price < SMA20 → ต้อง RSI > 50

3. หรือ ใช้เฉพาะ filter ที่สำคัญที่สุด:
   - Price > SMA20 (จำเป็น - 92% ของ losers อยู่ใต้)
   - Gap Down > -2% (ไม่ใช่ -1%)
   - ไม่ใช้ RSI filter
""")

# สรุปสุดท้าย
print("\n" + "=" * 70)
print("สรุป: ทำไมกำไรลดลง")
print("=" * 70)

print(f"""
Filter ใหม่กรองออก {len(filtered_trades)} trades:
  - Winners: {len(winners_filtered)} (เสียกำไร {total_profit_lost:+.2f}%)
  - Losers: {len(losers_filtered)} (หลีกเลี่ยง {abs(total_loss_avoided):.2f}%)

Net Impact: {total_profit_lost + total_loss_avoided:+.2f}%

ถ้า Net เป็นลบ = Filter เข้มเกินไป กรอง winners มากกว่า losers
ถ้า Net เป็นบวก = Filter พอดี กรอง losers ได้มากกว่า
""")
