#!/usr/bin/env python3
"""
Check why MU passed the screener even though it already ran +10%
"""

import yfinance as yf
import pandas as pd

def check_mu_momentum():
    print("\n" + "="*70)
    print("🔍 ทำไม MU ถึงผ่าน Filter ทั้งที่ขึ้นมา +10% แล้ว?")
    print("="*70)

    ticker = yf.Ticker('MU')
    hist = ticker.history(period='1mo')

    current_price = hist['Close'].iloc[-1]

    # Check various momentum periods
    print(f"\n📊 MU @ ${current_price:.2f}")
    print("="*70)

    lookback_periods = [
        (3, '3 วัน'),
        (5, '5 วัน'),
        (7, '7 วัน'),
        (10, '10 วัน'),
        (14, '14 วัน'),
        (20, '20 วัน')
    ]

    print(f"\n{'Period':<15} {'Old Price':<12} {'Return':<12} {'Status':<20}")
    print("-" * 70)

    for days, label in lookback_periods:
        if len(hist) > days:
            old_price = hist['Close'].iloc[-days-1]
            return_pct = ((current_price - old_price) / old_price) * 100

            # Determine status
            if return_pct > 15:
                status = "🔥 Already extended!"
            elif return_pct > 10:
                status = "⚠️  Strong move - late"
            elif return_pct > 5:
                status = "✅ Good - catchable"
            elif return_pct > 0:
                status = "✅ Early - ideal"
            else:
                status = "❌ Declining"

            print(f"{label:<15} ${old_price:<11.2f} {return_pct:>+7.2f}%   {status:<20}")

    # Check the "already extended" logic in screener
    print("\n" + "="*70)
    print("🔧 Screener Logic Check")
    print("="*70)

    # From code: line 882
    # recent_move = 10 days ago
    if len(hist) >= 10:
        price_10d_ago = hist['Close'].iloc[-10]
        recent_move = ((current_price - price_10d_ago) / price_10d_ago) * 100

        print(f"\n📍 Screener checks 10-day momentum:")
        print(f"   10 วันที่แล้ว: ${price_10d_ago:.2f}")
        print(f"   ตอนนี้: ${current_price:.2f}")
        print(f"   Recent Move: {recent_move:+.1f}%")

        print(f"\n🔍 Filter Logic:")
        if recent_move > 15:
            print(f"   ❌ recent_move ({recent_move:.1f}%) > 15%")
            print(f"   → Should PENALIZE -10 catalyst score")
            print(f"   → BUT does NOT exclude the stock!")
        else:
            print(f"   ✅ recent_move ({recent_move:.1f}%) <= 15%")
            print(f"   → Stock is NOT considered 'already extended'")
            print(f"   → PASSES this check!")

    # Real problem
    print("\n" + "="*70)
    print("⚠️  ปัญหาที่แท้จริง")
    print("="*70)

    print(f"\n1. ระบบตรวจ 'already extended' ที่ **10 วัน**")
    print(f"   MU 10-day return: {recent_move:+.1f}%")

    # Check 7-day
    price_7d_ago = hist['Close'].iloc[-7]
    return_7d = ((current_price - price_7d_ago) / price_7d_ago) * 100

    print(f"\n2. แต่ MU ขึ้นส่วนใหญ่ใน **7 วัน**")
    print(f"   7-day return: {return_7d:+.1f}%")
    print(f"   → ระบบไม่จับ!")

    print(f"\n3. ระบบไม่ได้ EXCLUDE หุ้นที่ 'already extended'")
    print(f"   → แค่ลด catalyst score -10 points")
    print(f"   → MU ยังผ่าน filters อื่นๆ ได้")

    print("\n" + "="*70)
    print("💡 แนวทางแก้ไข")
    print("="*70)

    print(f"\n📌 ควรเพิ่ม 'Momentum Filter' ที่:")
    print(f"   1. ตรวจ 7-day momentum (ใกล้กับ user มากกว่า)")
    print(f"   2. ถ้า > 10% → EXCLUDE (too late)")
    print(f"   3. ถ้า 3-8% → ยังจับได้ (early enough)")
    print(f"   4. ถ้า < 3% → ideal (setup phase)")

    print(f"\n📌 หรือเพิ่ม 'Consolidation Check':")
    print(f"   1. หุ้นต้องอยู่ใกล้ breakout zone")
    print(f"   2. ไม่ใช่ขึ้นไปเยอะแล้ว")
    print(f"   3. มี volume confirmation")

    print(f"\n✅ เป้าหมาย:")
    print(f"   → จับหุ้นที่กำลัง 'setup'")
    print(f"   → ไม่ใช่หุ้นที่ 'already ran'")
    print(f"   → ซื้อได้ในราคาดี ไม่ต้องไล่")

if __name__ == "__main__":
    check_mu_momentum()
