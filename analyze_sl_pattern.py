#!/usr/bin/env python3
"""
วิเคราะห์ pattern ของ Stop Loss
- มี SL กี่ครั้ง
- มี double SL (2 ตัวโดนพร้อมกัน) กี่ครั้ง
- โดน SL วันเดียวกับ entry หรือไม่ (PDT concern)
"""

import json

# โหลดผลลัพธ์ล่าสุด
with open('standard_backtest_20260201_171257.json', 'r') as f:
    data = json.load(f)

trades = data['trades']

print("=" * 70)
print("วิเคราะห์ STOP LOSS Pattern")
print("=" * 70)

# แยก trades ตาม entry_date (week)
from collections import defaultdict
weeks = defaultdict(list)
for t in trades:
    weeks[t['entry_date']].append(t)

# วิเคราะห์แต่ละสัปดาห์
double_sl_weeks = []
single_sl_weeks = []
no_sl_weeks = []

print("\n### สัปดาห์ที่มี STOP LOSS ###\n")

for week_date, week_trades in sorted(weeks.items()):
    sl_trades = [t for t in week_trades if t['exit_reason'] == 'STOP_LOSS']

    if len(sl_trades) == 2:
        double_sl_weeks.append(week_date)
        total_loss = sum(t['pnl_pct'] for t in sl_trades)
        print(f"❌❌ {week_date}: DOUBLE SL!")
        for t in sl_trades:
            print(f"     {t['symbol']}: {t['pnl_pct']:+.2f}%")
        print(f"     รวมขาดทุน: {total_loss:.2f}%")
        print()
    elif len(sl_trades) == 1:
        single_sl_weeks.append(week_date)
        t = sl_trades[0]
        win_trade = [x for x in week_trades if x['exit_reason'] != 'STOP_LOSS'][0]
        net = t['pnl_pct'] + win_trade['pnl_pct']
        print(f"❌  {week_date}: {t['symbol']} {t['pnl_pct']:+.2f}%")
        print(f"     อีกตัว: {win_trade['symbol']} {win_trade['pnl_pct']:+.2f}%")
        print(f"     Net: {net:+.2f}%")
        print()
    else:
        no_sl_weeks.append(week_date)

# สรุป
print("=" * 70)
print("สรุป STOP LOSS Pattern")
print("=" * 70)

total_weeks = len(weeks)
print(f"\nจาก {total_weeks} สัปดาห์:")
print(f"  ❌❌ Double SL (2 ตัวพร้อมกัน): {len(double_sl_weeks)} สัปดาห์ ({len(double_sl_weeks)/total_weeks*100:.0f}%)")
print(f"  ❌  Single SL (1 ตัว):          {len(single_sl_weeks)} สัปดาห์ ({len(single_sl_weeks)/total_weeks*100:.0f}%)")
print(f"  ✅  No SL:                      {len(no_sl_weeks)} สัปดาห์ ({len(no_sl_weeks)/total_weeks*100:.0f}%)")

# วิเคราะห์ว่า SL โดนวันไหน
print("\n" + "=" * 70)
print("วิเคราะห์ SL โดนวันที่เท่าไหร่ (Day 1 = Entry day)")
print("=" * 70)

sl_trades = [t for t in trades if t['exit_reason'] == 'STOP_LOSS']

# ดู exit_date เทียบกับ entry_date
from datetime import datetime

day_distribution = defaultdict(int)
same_day_exits = []

for t in sl_trades:
    entry = datetime.strptime(t['entry_date'], '%Y-%m-%d')
    exit_d = datetime.strptime(t['exit_date'], '%Y-%m-%d')
    days = (exit_d - entry).days
    day_distribution[days] += 1

    if days == 0:
        same_day_exits.append(t)

print(f"\nSL โดนวันที่เท่าไหร่หลัง entry:")
for day in sorted(day_distribution.keys()):
    count = day_distribution[day]
    pct = count / len(sl_trades) * 100
    bar = "█" * int(pct / 5)
    day_label = "Entry day (PDT!)" if day == 0 else f"Day {day}"
    print(f"  {day_label}: {count} ครั้ง ({pct:.0f}%) {bar}")

if same_day_exits:
    print(f"\n⚠️  SL วันเดียวกับ entry (PDT concern): {len(same_day_exits)} ครั้ง")
    for t in same_day_exits:
        print(f"     {t['entry_date']} {t['symbol']}: {t['pnl_pct']:+.2f}%")
else:
    print(f"\n✅ ไม่มี SL วันเดียวกับ entry (ไม่ติด PDT)")

# สรุปความเสี่ยง
print("\n" + "=" * 70)
print("สรุปความเสี่ยงสำหรับทุนจำกัด")
print("=" * 70)

print("""
ปัญหาหลัก:
1. Double SL weeks (-7% ถึง -9% ในสัปดาห์เดียว)
2. ถ้าทุนน้อย อาจไม่มีเงินพอ recover

แนวทางแก้ไข:
1. ลดเป็น 1 position (ไม่ใช่ 2)
   - ลด risk แต่ก็ลด return ด้วย

2. ใช้ position size เล็กลง (เช่น 20% แทน 40%)
   - Max loss per trade = 20% × 4% = 0.8%

3. เพิ่ม filter เข้มงวดขึ้น
   - เลือกเฉพาะ Score >= 150
   - Skip NEUTRAL market
""")
