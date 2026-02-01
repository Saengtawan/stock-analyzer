#!/usr/bin/env python3
"""
วิเคราะห์ v4.2 Losers: ขาดทุนเท่าไร? ถ้ารอนานกว่าจะกลับมาไหม?
"""

import pandas as pd
from loguru import logger

# Load v4.2 results
df = pd.read_csv('backtest_new_criteria.csv')

logger.info("=" * 80)
logger.info("📊 v4.2 LOSERS ANALYSIS - ตอนแพ้ขาดทุนเท่าไร?")
logger.info("=" * 80)
logger.info("")

# Separate winners and losers
winners = df[df['actual_return'] > 0]
losers = df[df['actual_return'] <= 0]

logger.info(f"✅ Winners: {len(winners)} trades ({len(winners)/len(df)*100:.1f}%)")
logger.info(f"❌ Losers:  {len(losers)} trades ({len(losers)/len(df)*100:.1f}%)")
logger.info("")

# ========== PART 1: LOSS STATISTICS ==========
logger.info("=" * 80)
logger.info("📉 PART 1: สถิติการขาดทุน")
logger.info("=" * 80)
logger.info("")

logger.info(f"Losers ขาดทุนเฉลี่ย: {losers['actual_return'].mean():.2f}%")
logger.info(f"Losers ขาดทุน median: {losers['actual_return'].median():.2f}%")
logger.info(f"Losers ขาดทุนมากสุด: {losers['actual_return'].min():.2f}%")
logger.info(f"Losers ขาดทุนน้อยสุด: {losers['actual_return'].max():.2f}%")
logger.info("")

# Count by loss severity
loss_mild = losers[losers['actual_return'] > -5]
loss_moderate = losers[(losers['actual_return'] <= -5) & (losers['actual_return'] > -10)]
loss_severe = losers[losers['actual_return'] <= -10]

logger.info("การแบ่งตามความรุนแรง:")
logger.info(f"  ขาดทุนน้อย (0% ถึง -5%):    {len(loss_mild):2d} trades ({len(loss_mild)/len(losers)*100:5.1f}%)")
logger.info(f"  ขาดทุนปานกลาง (-5% ถึง -10%): {len(loss_moderate):2d} trades ({len(loss_moderate)/len(losers)*100:5.1f}%)")
logger.info(f"  ขาดทุนหนัก (-10% ขึ้นไป):    {len(loss_severe):2d} trades ({len(loss_severe)/len(losers)*100:5.1f}%)")
logger.info("")

# ========== PART 2: COULD HAVE BEEN WINNERS ==========
logger.info("=" * 80)
logger.info("🔄 PART 2: หุ้นที่แพ้ แต่เคยกำไรระหว่างทาง!")
logger.info("=" * 80)
logger.info("")

# Losers that had positive max_return (were profitable at some point)
losers_had_profit = losers[losers['max_return'] > 0]

logger.info(f"จำนวน losers ที่เคยกำไรระหว่างทาง: {len(losers_had_profit)}/{len(losers)} ({len(losers_had_profit)/len(losers)*100:.1f}%)")
logger.info("")
logger.info("👉 แสดงว่า: ถ้าขายตอนกำไร จะไม่ต้องขาดทุน!")
logger.info("")

# Show details
logger.info("รายละเอียด:")
logger.info(f"{'Symbol':<8} {'Entry':<12} {'Final':<8} {'Max Gain':<10} {'Lost':<10}")
logger.info("-" * 60)

for _, row in losers_had_profit.iterrows():
    symbol = row['symbol']
    entry_date = row['entry_date']
    final_return = row['actual_return']
    max_return = row['max_return']
    lost_profit = max_return - final_return

    logger.info(f"{symbol:<8} {entry_date:<12} {final_return:>6.2f}%  {max_return:>6.2f}%     -{lost_profit:>6.2f}%")

logger.info("")
logger.info(f"💡 เฉลี่ย: หุ้นที่แพ้เคยกำไร {losers_had_profit['max_return'].mean():.2f}% ระหว่างทาง")
logger.info(f"   แต่สุดท้ายขาดทุน {losers_had_profit['actual_return'].mean():.2f}%")
logger.info(f"   🔴 Lost profit: {(losers_had_profit['max_return'] - losers_had_profit['actual_return']).mean():.2f}%")
logger.info("")

# ========== PART 3: WORST LOSERS DETAIL ==========
logger.info("=" * 80)
logger.info("💀 PART 3: Losers ที่ขาดทุนหนัก (< -10%)")
logger.info("=" * 80)
logger.info("")

logger.info(f"{'Symbol':<8} {'Entry':<12} {'Loss':<8} {'Max':<8} {'Min':<8} {'Days':<6} {'Note'}")
logger.info("-" * 85)

for _, row in loss_severe.iterrows():
    symbol = row['symbol']
    entry_date = row['entry_date']
    loss = row['actual_return']
    max_ret = row['max_return']
    min_ret = row['min_return']
    days = row['days_held']

    # Check if it was ever profitable
    if max_ret > 0:
        note = f"⚠️ เคยกำไร +{max_ret:.1f}%!"
    else:
        note = "❌ ไม่เคยกำไรเลย"

    logger.info(f"{symbol:<8} {entry_date:<12} {loss:>6.2f}% {max_ret:>6.2f}% {min_ret:>6.2f}% {days:<6} {note}")

logger.info("")

# ========== PART 4: RECOVERY POTENTIAL ==========
logger.info("=" * 80)
logger.info("🔮 PART 4: ถ้ารอนานกว่า 30 วัน จะกลับมาไหม?")
logger.info("=" * 80)
logger.info("")

logger.info("⚠️ ข้อจำกัด: Backtest ใช้ 30-day holding period เท่านั้น")
logger.info("   ไม่มีข้อมูลว่าหลัง 30 วันราคาจะเป็นยังไง")
logger.info("")
logger.info("แต่ดูจาก pattern ที่มี:")
logger.info("")

# Check losers that were close to breakeven at max
close_to_breakeven = losers[(losers['max_return'] >= -2) & (losers['max_return'] <= 2)]
logger.info(f"1. Losers ที่เคยใกล้ breakeven (-2% ถึง +2%): {len(close_to_breakeven)}/{len(losers)}")
logger.info(f"   👉 มีโอกาสกลับมา break even ถ้ารอนานกว่า")
logger.info("")

# Check losers with strong uptrend at some point
strong_uptrend = losers[losers['max_return'] > 5]
logger.info(f"2. Losers ที่เคยกำไร >5%: {len(strong_uptrend)}/{len(losers)}")
logger.info(f"   👉 มี momentum ดีอยู่ ถ้าไม่ขายอาจกลับมาได้")
logger.info("")

# Check losers that never recovered
never_recovered = losers[losers['max_return'] < 0]
logger.info(f"3. Losers ที่ไม่เคยกำไรเลยตลอด 30 วัน: {len(never_recovered)}/{len(losers)}")
logger.info(f"   👉 Hold นานกว่าก็อาจไม่กลับมา (downtrend)")
logger.info("")

# ========== PART 5: CONCLUSION ==========
logger.info("=" * 80)
logger.info("📌 PART 5: สรุปและข้อเสนอแนะ")
logger.info("=" * 80)
logger.info("")

avg_loss = losers['actual_return'].mean()
median_loss = losers['actual_return'].median()
pct_had_profit = len(losers_had_profit) / len(losers) * 100
avg_max_gain_of_losers = losers_had_profit['max_return'].mean()

logger.info(f"✅ ข่าวดี:")
logger.info(f"   • Losers ขาดทุนเฉลี่ย {avg_loss:.2f}% (ไม่รุนแรงมาก)")
logger.info(f"   • Losers median {median_loss:.2f}% (ขาดทุนปานกลาง)")
logger.info(f"   • {pct_had_profit:.1f}% ของ losers เคยกำไรระหว่างทาง")
logger.info(f"   • เฉลี่ยเคยกำไร {avg_max_gain_of_losers:.2f}% ก่อนกลับมาขาดทุน")
logger.info("")

logger.info(f"⚠️ ความเสี่ยง:")
logger.info(f"   • มี {len(loss_severe)} trades ขาดทุนหนัก (< -10%)")
logger.info(f"   • Worst loss: {losers['actual_return'].min():.2f}%")
logger.info(f"   • {len(never_recovered)} trades ไม่เคยกำไรเลยตลอด 30 วัน")
logger.info("")

logger.info("💡 ข้อเสนอแนะ:")
logger.info("")
logger.info("1. ใช้ Trailing Stop Loss แทน Hard Stop:")
logger.info(f"   • {pct_had_profit:.1f}% ของ losers เคยกำไรถึง {avg_max_gain_of_losers:.2f}%")
logger.info("   • ถ้าใช้ trailing stop -3% จากจุดสูงสุด จะขายตอนยังกำไร")
logger.info("")

logger.info("2. Hold Longer Strategy (ถ้าไม่ใช้ stop loss):")
logger.info("   ✅ ข้อดี: หุ้นที่ดีอาจกลับมากำไรถ้ารอนานกว่า 30 วัน")
logger.info(f"   ❌ ข้อเสีย: เสี่ยงขาดทุนหนักขึ้น (worst: {losers['actual_return'].min():.2f}%)")
logger.info("   ⚠️ ต้องมี capital มากพอ + จิตวิทยาแข็งแรง")
logger.info("")

logger.info("3. Hybrid Approach (แนะนำ!):")
logger.info("   • ใช้ Hard Stop -6% (ป้องกันขาดทุนหนัก)")
logger.info("   • ใช้ Trailing Stop -3% (ล็อคกำไร)")
logger.info("   • ถ้าขาดทุน -3% ถึง -6% = รอดูอีก (อาจกลับมา)")
logger.info("")

logger.info("=" * 80)
logger.info("🎯 ตอบคำถาม: 'ถ้ารอสักระยะจะกลับมาราคาเดิมได้มั้ย?'")
logger.info("=" * 80)
logger.info("")
logger.info(f"✅ มีโอกาส {pct_had_profit:.1f}%: เคยกำไรระหว่างทาง แสดงว่ามี momentum")
logger.info(f"   ถ้ารอนานกว่า 30 วัน อาจกลับมาได้")
logger.info("")
logger.info(f"❌ มีโอกาส {len(never_recovered)/len(losers)*100:.1f}%: ไม่เคยกำไรเลย แสดงว่า downtrend")
logger.info("   รอนานแค่ไหนก็อาจไม่กลับมา")
logger.info("")
logger.info("💡 ข้อเสนอ: ใช้ Trailing Stop จะดีกว่า Hold นิ่งๆ")
logger.info(f"   เพราะ {pct_had_profit:.1f}% เคยกำไร ถ้าขายตอนนั้นจะไม่ต้องขาดทุน")
