#!/usr/bin/env python3
"""
ตรวจสอบความถูกต้องของ Trailing Stop และ Short Interest
"""
import requests
import yfinance as yf

symbol = "AFRM"

print("="*70)
print(f"🔍 ตรวจสอบ Trailing Stop & Short Interest สำหรับ {symbol}")
print("="*70)

# 1. ดึงข้อมูลจาก API
url = "http://127.0.0.1:5002/api/analyze"
data = {"symbol": symbol, "time_horizon": "short", "account_value": 100000}
response = requests.post(url, json=data, timeout=120)
result = response.json()

ef = result.get('enhanced_features', {})
features = ef.get('features', {})

# =============================================================================
# ตรวจสอบ Trailing Stop Loss
# =============================================================================
print("\n" + "="*70)
print("🛑 TRAILING STOP LOSS MANAGER")
print("="*70)

trailing = features.get('trailing_stop', {})

if not trailing:
    print("❌ ไม่มีข้อมูล Trailing Stop")
else:
    should_move = trailing.get('should_move', False)
    original_sl = trailing.get('original_sl', 0)
    recommended_sl = trailing.get('recommended_sl', 0)
    locked_profit = trailing.get('locked_profit', {})
    locked_pct = locked_profit.get('percentage', 0)
    locked_dollars = locked_profit.get('dollars', 0)
    reason = trailing.get('reason', 'N/A')

    print(f"\n📊 ข้อมูลจาก API:")
    print(f"   Should Move: {should_move}")
    print(f"   Original SL: ${original_sl:.2f}")
    print(f"   Recommended SL: ${recommended_sl:.2f}")
    print(f"   Locked Profit: {locked_pct:.2f}% (${locked_dollars:.2f})")
    print(f"   Reason: {reason}")

    # ตรวจสอบตรรกะ
    print(f"\n🧠 ตรวจสอบตรรกะการคำนวณ:")

    # ดึงข้อมูลจริงมาเปรียบเทียบ
    pnl = features.get('pnl_tracker', {})
    entry_data = pnl.get('entry', {})
    current_data = pnl.get('current', {})

    entry_price = entry_data.get('price', 0)
    current_price = current_data.get('price', 0)
    current_profit_pct = current_data.get('profit_pct', 0)

    print(f"   Entry Price: ${entry_price:.2f}")
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Current Profit: {current_profit_pct:.2f}%")

    # ตรวจสอบ Stop Loss
    if original_sl > 0 and entry_price > 0:
        sl_from_entry_pct = ((original_sl - entry_price) / entry_price) * 100
        print(f"   Original SL vs Entry: {sl_from_entry_pct:+.2f}%")

    if recommended_sl > 0 and entry_price > 0:
        new_sl_from_entry_pct = ((recommended_sl - entry_price) / entry_price) * 100
        print(f"   Recommended SL vs Entry: {new_sl_from_entry_pct:+.2f}%")

        # คำนวณ locked profit ด้วยตัวเอง
        if entry_price > 0:
            manual_locked = ((recommended_sl - entry_price) / entry_price) * 100
            print(f"\n   ✅ Locked Profit (คำนวณเอง): {manual_locked:.2f}%")
            print(f"   ✅ Locked Profit (จาก API): {locked_pct:.2f}%")

            if abs(manual_locked - locked_pct) < 0.5:
                print(f"   ✅ ตรงกัน - คำนวณถูกต้อง!")
            else:
                print(f"   ⚠️ ไม่ตรงกัน - แตกต่าง {abs(manual_locked - locked_pct):.2f}%")

    # ตรวจสอบ logic ว่าควร move หรือไม่
    print(f"\n🎯 ตรวจสอบ Logic:")
    if current_profit_pct >= 5:
        print(f"   ✅ กำไรมากกว่า 5% ({current_profit_pct:.2f}%) → ควร move stop")
        if should_move:
            print(f"   ✅ API แนะนำให้ move - ถูกต้อง!")
        else:
            print(f"   ⚠️ API ไม่แนะนำให้ move - อาจผิดพลาด")
    elif current_profit_pct >= 3:
        print(f"   ⚠️ กำไร 3-5% ({current_profit_pct:.2f}%) → พิจารณา move")
    else:
        print(f"   ⏸️ กำไรน้อยกว่า 3% ({current_profit_pct:.2f}%) → ยังไม่ควร move")
        if not should_move:
            print(f"   ✅ API ไม่แนะนำให้ move - ถูกต้อง!")

# =============================================================================
# ตรวจสอบ Short Interest
# =============================================================================
print("\n" + "="*70)
print("📊 SHORT INTEREST ANALYSIS")
print("="*70)

short_data = features.get('short_interest', {})

if not short_data:
    print("❌ ไม่มีข้อมูล Short Interest")
else:
    short_interest = short_data.get('short_interest', {})
    short_pct = short_interest.get('short_pct_float', 0)
    days_to_cover = short_interest.get('days_to_cover', 0)
    squeeze_potential = short_data.get('squeeze_potential', 'Unknown')
    interpretation = short_data.get('interpretation', '')

    print(f"\n📊 ข้อมูลจาก API:")
    print(f"   Short % of Float: {short_pct:.2f}%")
    print(f"   Days to Cover: {days_to_cover:.2f}")
    print(f"   Squeeze Potential: {squeeze_potential}")
    print(f"   Interpretation: {interpretation}")

    # ดึงข้อมูลจริงจาก Yahoo Finance
    print(f"\n🔍 ตรวจสอบกับ Yahoo Finance:")
    ticker = yf.Ticker(symbol)
    info = ticker.info

    yf_short_pct = info.get('shortPercentOfFloat', 0) * 100 if info.get('shortPercentOfFloat') else 0
    yf_short_ratio = info.get('shortRatio', 0)  # Days to cover

    print(f"   Yahoo Short % of Float: {yf_short_pct:.2f}%")
    print(f"   Yahoo Days to Cover: {yf_short_ratio:.2f}")

    # เปรียบเทียบ
    if abs(short_pct - yf_short_pct) < 1:
        print(f"   ✅ Short % ตรงกัน - ถูกต้อง!")
    else:
        print(f"   ⚠️ Short % แตกต่าง {abs(short_pct - yf_short_pct):.2f}%")

    if abs(days_to_cover - yf_short_ratio) < 0.5:
        print(f"   ✅ Days to Cover ตรงกัน - ถูกต้อง!")
    else:
        print(f"   ⚠️ Days to Cover แตกต่าง {abs(days_to_cover - yf_short_ratio):.2f}")

    # ตรวจสอบ Squeeze Potential Logic
    print(f"\n🎯 ตรวจสอบ Squeeze Potential Logic:")

    if short_pct > 20 and days_to_cover > 5:
        expected = "High"
        print(f"   Short > 20% AND Days > 5 → ควรเป็น '{expected}'")
    elif short_pct > 10 or days_to_cover > 3:
        expected = "Medium"
        print(f"   Short > 10% OR Days > 3 → ควรเป็น '{expected}'")
    else:
        expected = "Low"
        print(f"   Short <= 10% AND Days <= 3 → ควรเป็น '{expected}'")

    if squeeze_potential == expected:
        print(f"   ✅ API คำนวณเป็น '{squeeze_potential}' - ถูกต้อง!")
    else:
        print(f"   ⚠️ API คำนวณเป็น '{squeeze_potential}' แต่ควรเป็น '{expected}'")

print("\n" + "="*70)
print("สรุป")
print("="*70)
