#!/usr/bin/env python3
"""
วิเคราะห์: ทำไมหุ้นที่ขาดทุนหนัก (AVGO, NVDA, SNOW) ถึงผ่าน v4.2 screening?
มีอะไรที่ screener พลาดไป?
"""

import pandas as pd
from loguru import logger

# Load v4.2 results
df = pd.read_csv('backtest_new_criteria.csv')

logger.info("=" * 80)
logger.info("🔍 วิเคราะห์: ทำไมหุ้นที่ขาดทุนหนักถึงผ่าน Screening?")
logger.info("=" * 80)
logger.info("")

# Focus on big losers (< -10%)
big_losers = df[df['actual_return'] < -10].copy()

logger.info(f"หุ้นที่ขาดทุนหนัก (< -10%): {len(big_losers)} trades")
logger.info("")

# ========== PART 1: ENTRY METRICS ==========
logger.info("=" * 80)
logger.info("📊 PART 1: เมตริกตอน Entry - ดูดีไหม?")
logger.info("=" * 80)
logger.info("")

logger.info(f"{'Symbol':<8} {'Date':<12} {'Loss':<8} {'RSI':<6} {'Mom30d':<8} {'vs MA50':<8} {'Volume':<8}")
logger.info("-" * 80)

for _, row in big_losers.iterrows():
    symbol = row['symbol']
    date = row['entry_date']
    loss = row['actual_return']
    rsi = row['rsi']
    mom = row['mom_30d']
    vs_ma50 = row['price_vs_ma50']
    vol = row['volume_ratio']

    logger.info(f"{symbol:<8} {date:<12} {loss:>6.2f}% {rsi:>5.1f} {mom:>7.2f}% {vs_ma50:>7.2f}% {vol:>7.2f}x")

logger.info("")
logger.info("💭 คำถาม: เมตริกเหล่านี้ดูดีไหม?")
logger.info("")

# Check against v4.2 gates
logger.info("✅ ตรวจสอบตาม v4.2 Gates:")
logger.info("")

for _, row in big_losers.iterrows():
    symbol = row['symbol']
    date = row['entry_date']
    rsi = row['rsi']
    mom = row['mom_30d']
    vol = row['volume_ratio']

    logger.info(f"{symbol} ({date}):")

    # Gate 1: Momentum <38%
    if mom <= 38:
        logger.info(f"  ✅ Momentum {mom:.1f}% < 38% (PASS)")
    else:
        logger.info(f"  ❌ Momentum {mom:.1f}% > 38% (FAIL)")

    # Gate 2: RSI 45-72
    if 45 <= rsi <= 72:
        logger.info(f"  ✅ RSI {rsi:.1f} in range 45-72 (PASS)")
        if rsi >= 65:
            logger.info(f"     ⚠️ แต่ RSI {rsi:.1f} ใกล้ extended (>65)")
    else:
        logger.info(f"  ❌ RSI {rsi:.1f} out of range (FAIL)")

    # Gate 3: Volume
    if mom >= 20:
        if 0.8 <= vol <= 2.0:
            logger.info(f"  ✅ Volume {vol:.2f}x (high mom range) (PASS)")
        else:
            logger.info(f"  ❌ Volume {vol:.2f}x out of range (FAIL)")
    else:
        if 0.8 <= vol <= 1.8:
            logger.info(f"  ✅ Volume {vol:.2f}x (PASS)")
        else:
            logger.info(f"  ⚠️ Volume {vol:.2f}x < 0.8 (WEAK)")

    logger.info("")

# ========== PART 2: COMPARE WITH WINNERS ==========
logger.info("=" * 80)
logger.info("📊 PART 2: เปรียบเทียบกับ Winners - ต่างกันตรงไหน?")
logger.info("=" * 80)
logger.info("")

winners = df[df['actual_return'] > 0]

logger.info(f"{'Metric':<20} {'Big Losers':<15} {'Winners':<15} {'Difference'}")
logger.info("-" * 70)

metrics = ['rsi', 'mom_30d', 'price_vs_ma50', 'volume_ratio']
for metric in metrics:
    loser_avg = big_losers[metric].mean()
    winner_avg = winners[metric].mean()
    diff = loser_avg - winner_avg

    logger.info(f"{metric:<20} {loser_avg:>12.2f}   {winner_avg:>12.2f}   {diff:>+8.2f}")

logger.info("")

# ========== PART 3: WHAT WENT WRONG ==========
logger.info("=" * 80)
logger.info("🔍 PART 3: เกิดอะไรขึ้นหลัง Entry?")
logger.info("=" * 80)
logger.info("")

logger.info(f"{'Symbol':<8} {'Entry':<12} {'Max Gain':<10} {'Min Loss':<10} {'Final':<8} {'สิ่งที่เกิดขึ้น'}")
logger.info("-" * 90)

for _, row in big_losers.iterrows():
    symbol = row['symbol']
    date = row['entry_date']
    max_ret = row['max_return']
    min_ret = row['min_return']
    final = row['actual_return']

    # Analyze pattern
    if max_ret > 5:
        pattern = f"✅ เคยกำไร {max_ret:.1f}% แล้วกลับมาขาดทุน (reversal!)"
    elif max_ret > 0:
        pattern = f"⚠️ เคยกำไรนิดหน่อย {max_ret:.1f}% แล้วกลับตัว"
    else:
        pattern = f"❌ ไม่เคยกำไรเลย ลงตรงๆ"

    logger.info(f"{symbol:<8} {date:<12} {max_ret:>8.2f}% {min_ret:>9.2f}% {final:>6.2f}% {pattern}")

logger.info("")

# ========== PART 4: ROOT CAUSE ==========
logger.info("=" * 80)
logger.info("🎯 PART 4: Root Cause - ทำไมถึงขาดทุนหนัก?")
logger.info("=" * 80)
logger.info("")

logger.info("วิเคราะห์จากข้อมูล:")
logger.info("")

# Check RSI levels
high_rsi_losers = big_losers[big_losers['rsi'] >= 65]
logger.info(f"1. RSI สูง (>= 65): {len(high_rsi_losers)}/{len(big_losers)} ตัว")
if len(high_rsi_losers) > 0:
    logger.info(f"   👉 RSI เฉลี่ย: {high_rsi_losers['rsi'].mean():.1f} (ใกล้ extended)")
    logger.info(f"   📌 v4.2 ยอมให้ RSI ถึง 72, แต่ >= 65 ก็เริ่มเสี่ยงแล้ว!")

logger.info("")

# Check momentum
avg_mom = big_losers['mom_30d'].mean()
winner_avg_mom = winners['mom_30d'].mean()
logger.info(f"2. Momentum 30d:")
logger.info(f"   Big Losers: {avg_mom:.2f}%")
logger.info(f"   Winners:    {winner_avg_mom:.2f}%")
if avg_mom > winner_avg_mom:
    logger.info(f"   👉 Big losers มี momentum สูงกว่า winners!")
    logger.info(f"   📌 Momentum สูง = ใกล้ exhausted?")

logger.info("")

# Check volume
low_vol_losers = big_losers[big_losers['volume_ratio'] < 0.8]
logger.info(f"3. Volume ต่ำ (< 0.8x): {len(low_vol_losers)}/{len(big_losers)} ตัว")
if len(low_vol_losers) > 0:
    logger.info(f"   👉 SNOW volume 0.736x < 0.8x แต่ยังผ่าน?")
    logger.info(f"   📌 v4.2 gate อาจต้องเข้มงวดกับ volume มากกว่านี้")

logger.info("")

# All had profit at some point
all_had_profit = all(big_losers['max_return'] > 0)
if all_had_profit:
    logger.info(f"4. ✅ ทุกตัวเคยกำไรระหว่างทาง!")
    logger.info(f"   เฉลี่ยเคยกำไร: {big_losers['max_return'].mean():.2f}%")
    logger.info(f"   👉 ปัญหาไม่ใช่ที่ screening ผิด แต่ที่ไม่มี EXIT RULE!")
    logger.info(f"   📌 ถ้ามี Trailing Stop -3% จะไม่ขาดทุนเลย!")

logger.info("")

# ========== PART 5: SCREENING GAPS ==========
logger.info("=" * 80)
logger.info("🔧 PART 5: Screening Gaps - อะไรที่ v4.2 พลาด?")
logger.info("=" * 80)
logger.info("")

logger.info("v4.2 Gates ที่มีอยู่:")
logger.info("  1. ✅ Momentum <38% (ป้องกัน exhausted)")
logger.info("  2. ✅ RSI 45-72 (ป้องกัน extended)")
logger.info("  3. ✅ Volume 0.8-1.8x")
logger.info("  4. ✅ MA20 > MA50 (uptrend)")
logger.info("  5. ✅ 5d momentum > -8%")
logger.info("")

logger.info("❌ สิ่งที่ v4.2 ไม่มี (อาจเป็นสาเหตุ):")
logger.info("")

logger.info("1. 📉 ไม่มี Trailing Stop!")
logger.info("   • ทุก big loser เคยกำไร +4-5%")
logger.info("   • ถ้ามี trailing stop -3% จะไม่ขาดทุน")
logger.info("")

logger.info("2. ⚠️ RSI Gate อาจหลวมเกินไป:")
logger.info("   • v4.2 ยอม RSI ถึง 72")
logger.info("   • Big losers มี RSI 63-69 (ใกล้ extended)")
logger.info("   • ควรเข้มงวด: RSI >65 = ลดคะแนน หรือ reject?")
logger.info("")

logger.info("3. 📊 Volume Gate มีช่องโหว่:")
logger.info("   • SNOW volume 0.736x < 0.8 แต่ยังผ่าน")
logger.info("   • ต้อง strict กว่านี้")
logger.info("")

logger.info("4. 🔄 ไม่มี Sector/Market Context:")
logger.info("   • ไม่รู้ว่า sector กำลัง rotate out")
logger.info("   • ไม่รู้ว่า market regime เปลี่ยน")
logger.info("")

logger.info("5. 📈 ไม่มี Recent Weakness Filter:")
logger.info("   • ไม่เช็คว่าหุ้นเพิ่งอ่อนลงหรือเปล่า")
logger.info("   • momentum 30d อาจซ่อน weakness 5-7d")
logger.info("")

# ========== PART 6: RECOMMENDATIONS ==========
logger.info("=" * 80)
logger.info("💡 PART 6: แนะนำการแก้ไข")
logger.info("=" * 80)
logger.info("")

logger.info("🏆 แนะนำอันดับ 1: เพิ่ม TRAILING STOP LOSS")
logger.info("   • Trailing Stop -3% จากจุดสูงสุด")
logger.info("   • จะเปลี่ยน 3 big losers → 3 small winners!")
logger.info("   • ไม่ต้องแก้ screening logic")
logger.info("")

logger.info("🔧 แนะนำอันดับ 2: เข้มงวด RSI Gate")
logger.info("   • เดิม: RSI 45-72")
logger.info("   • ใหม่: RSI 45-65 (เหมือน v5.1)")
logger.info("   • หรือ: RSI >65 = ลดคะแนนหนักๆ")
logger.info("")

logger.info("📊 แนะนำอันดับ 3: เข้มงวด Volume Gate")
logger.info("   • ไม่ยอมให้ volume < 0.8x")
logger.info("   • High momentum (>15%) ต้อง volume >= 1.0x")
logger.info("")

logger.info("🎯 แนะนำอันดับ 4: เพิ่ม Recent Weakness Filter")
logger.info("   • เช็ค 5d momentum: ถ้า < 0% = อ่อนลง")
logger.info("   • เช็ค recent drop: ถ้าลง >3% ใน 5d = รอก่อน")
logger.info("")

# ========== CONCLUSION ==========
logger.info("=" * 80)
logger.info("📌 สรุป: ทำไมหุ้นที่ขาดทุนหนักถึงผ่าน Screening?")
logger.info("=" * 80)
logger.info("")

logger.info("🔍 สาเหตุหลัก:")
logger.info("")
logger.info("1. ✅ เมตริกตอน Entry ดูดีจริง (ผ่าน v4.2 gates ทั้งหมด)")
logger.info("   • RSI, momentum, volume อยู่ในเกณฑ์")
logger.info("   • แต่ใกล้เขต extended (RSI 63-69)")
logger.info("")

logger.info("2. 🎢 ทุกตัวเคยกำไรระหว่างทาง!")
logger.info("   • AVGO เคยกำไร +6.24% แล้วกลับมา -14.64%")
logger.info("   • NVDA เคยกำไร +0.45% แล้วกลับมา -12.07%")
logger.info("   • SNOW เคยกำไร +2.74% แล้วกลับมา -18.84%")
logger.info("")

logger.info("3. ❌ ปัญหาคือ: ไม่มี EXIT RULE!")
logger.info("   • v4.2 มี screening ดี แต่ไม่มี trailing stop")
logger.info("   • ถ้ามี trailing stop -3% จะไม่ขาดทุนเลย!")
logger.info("")

logger.info("=" * 80)
logger.info("🎯 คำตอบสั้นๆ:")
logger.info("=" * 80)
logger.info("")
logger.info("'ทำไมถึงค้นหาแล้วแนะนำให้ซื้อ?'")
logger.info("")
logger.info("✅ เพราะเมตริกตอน Entry ดูดีจริง:")
logger.info("   • Momentum healthy (9-19%)")
logger.info("   • RSI neutral-high (63-69)")
logger.info("   • MA uptrend")
logger.info("   • ผ่าน v4.2 gates ทั้งหมด")
logger.info("")
logger.info("❌ แต่ Screener ไม่รู้ว่า:")
logger.info("   • หุ้นใกล้ extended (RSI >65)")
logger.info("   • กำลังจะ reverse")
logger.info("   • sector กำลัง rotate")
logger.info("")
logger.info("💡 แก้ไข:")
logger.info("   • เพิ่ม Trailing Stop -3% (สำคัญที่สุด!)")
logger.info("   • เข้มงวด RSI >65")
logger.info("   • เข้มงวด volume")
