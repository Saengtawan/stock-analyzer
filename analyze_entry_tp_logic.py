#!/usr/bin/env python3
"""
วิเคราะห์ว่า Entry/TP1/TP2 คำนวณอย่างไร และมีความเป็นจริงแค่ไหน
"""
import requests
import yfinance as yf
import pandas as pd

symbol = "AFRM"

# 1. ดึงข้อมูลประวัติราคา
print("="*70)
print(f"📈 วิเคราะห์ความเป็นจริงของ Entry/TP สำหรับ {symbol}")
print("="*70)

ticker = yf.Ticker(symbol)
hist = ticker.history(period="60d")  # 60 วันย้อนหลัง

# 2. ดึงข้อมูลจาก API
url = "http://127.0.0.1:5002/api/analyze"
data = {"symbol": symbol, "time_horizon": "short", "account_value": 100000}
response = requests.post(url, json=data, timeout=120)
result = response.json()

# Extract data
ef = result.get('enhanced_features', {})
features = ef.get('features', {})
pnl = features.get('pnl_tracker', {})

entry = pnl.get('entry', {})
targets = pnl.get('targets', {})
current = pnl.get('current', {})

entry_price = entry.get('price', 0)
entry_method = entry.get('method', 'N/A')
entry_source = entry.get('source', 'N/A')

tp1_price = targets.get('tp1', {}).get('price', 0)
tp2_price = targets.get('tp2', {}).get('price', 0)
current_price = current.get('price', 0)

print(f"\n💰 ข้อมูลจาก API:")
print(f"   Current: ${current_price:.2f}")
print(f"   Entry: ${entry_price:.2f} ({entry_method}, {entry_source})")
print(f"   TP1: ${tp1_price:.2f}")
print(f"   TP2: ${tp2_price:.2f}")

# 3. วิเคราะห์ Entry Price
print(f"\n{'='*70}")
print("🎯 วิเคราะห์ Entry Price - มีโอกาสได้ซื้อราคานี้จริงหรือไม่?")
print("="*70)

# หาว่าในรอบ 60 วัน ราคาเคยลงมาต่ำกว่า entry หรือไม่
prices_below_entry = hist[hist['Close'] <= entry_price]
days_at_or_below = len(prices_below_entry)
total_days = len(hist)

print(f"\n📊 ในรอบ {total_days} วันที่ผ่านมา:")
print(f"   • ราคาต่ำกว่า/เท่ากับ Entry (${entry_price:.2f}): {days_at_or_below} วัน")
print(f"   • เปอร์เซ็นต์: {(days_at_or_below/total_days)*100:.1f}%")

if days_at_or_below > 0:
    last_time_at_entry = prices_below_entry.index[-1].strftime('%Y-%m-%d')
    days_ago = (pd.Timestamp.now(tz='UTC') - prices_below_entry.index[-1]).days
    print(f"   • ครั้งล่าสุดที่ราคาอยู่ที่ Entry: {last_time_at_entry} ({days_ago} วันที่แล้ว)")

    if days_ago <= 5:
        print(f"   ✅ Entry price สมเหตุสมผล - เคยมีราคานี้เมื่อเร็ว ๆ นี้")
    elif days_ago <= 20:
        print(f"   ⚠️ Entry price เป็นไปได้ - เคยมีราคานี้ใน 20 วันที่แล้ว")
    else:
        print(f"   ❌ Entry price ไม่สมจริง - ไม่มีราคานี้มานาน")
else:
    print(f"   ❌ ไม่เคยมีราคาต่ำกว่า ${entry_price:.2f} ในรอบ 60 วัน")
    print(f"   → Entry price สูงเกินไป!")

# เปรียบเทียบกับราคาปัจจุบัน
diff_from_current = ((current_price - entry_price) / entry_price) * 100
print(f"\n💡 Entry vs ราคาปัจจุบัน:")
print(f"   • Entry อยู่ต่ำกว่าราคาปัจจุบัน: {diff_from_current:.2f}%")
if diff_from_current > 10:
    print(f"   ⚠️ ห่างกันมาก - Entry อาจเป็นราคาที่ผ่านมาแล้ว ไม่ใช่จุดเข้าในอนาคต")
elif diff_from_current > 2:
    print(f"   ✅ สมเหตุสมผล - ถ้ามี signal เมื่อราคาที่ Entry")

# 4. วิเคราะห์ TP1/TP2
print(f"\n{'='*70}")
print("🎯 วิเคราะห์ TP1/TP2 - มีโอกาสถึงราคานี้จริงหรือไม่?")
print("="*70)

# หาว่าในรอบ 60 วัน ราคาเคยสูงกว่า TP1/TP2 หรือไม่
prices_above_tp1 = hist[hist['High'] >= tp1_price]
prices_above_tp2 = hist[hist['High'] >= tp2_price]

days_above_tp1 = len(prices_above_tp1)
days_above_tp2 = len(prices_above_tp2)

print(f"\n📊 ในรอบ {total_days} วันที่ผ่านมา:")
print(f"\nTP1 (${tp1_price:.2f}):")
print(f"   • ราคาสูงกว่า/เท่ากับ TP1: {days_above_tp1} วัน ({(days_above_tp1/total_days)*100:.1f}%)")

if days_above_tp1 > 0:
    last_time_above_tp1 = prices_above_tp1.index[-1].strftime('%Y-%m-%d')
    days_ago_tp1 = (pd.Timestamp.now(tz='UTC') - prices_above_tp1.index[-1]).days
    print(f"   • ครั้งล่าสุด: {last_time_above_tp1} ({days_ago_tp1} วันที่แล้ว)")

    if days_above_tp1 > total_days * 0.3:  # มากกว่า 30%
        print(f"   ✅ TP1 เป็นไปได้สูง - เคยมีราคานี้บ่อย")
    elif days_above_tp1 > total_days * 0.1:  # มากกว่า 10%
        print(f"   ⚠️ TP1 เป็นไปได้ - เคยมีราคานี้บ้าง")
    else:
        print(f"   ⚠️ TP1 เป็นไปได้ยาก - เคยมีราคานี้น้อยมาก")
else:
    print(f"   ❌ ไม่เคยถึง TP1 ในรอบ 60 วัน - TP1 สูงเกินไป!")

print(f"\nTP2 (${tp2_price:.2f}):")
print(f"   • ราคาสูงกว่า/เท่ากับ TP2: {days_above_tp2} วัน ({(days_above_tp2/total_days)*100:.1f}%)")

if days_above_tp2 > 0:
    last_time_above_tp2 = prices_above_tp2.index[-1].strftime('%Y-%m-%d')
    days_ago_tp2 = (pd.Timestamp.now(tz='UTC') - prices_above_tp2.index[-1]).days
    print(f"   • ครั้งล่าสุด: {last_time_above_tp2} ({days_ago_tp2} วันที่แล้ว)")

    if days_above_tp2 > total_days * 0.2:
        print(f"   ✅ TP2 เป็นไปได้ - เคยมีราคานี้บ่อย")
    elif days_above_tp2 > total_days * 0.05:
        print(f"   ⚠️ TP2 เป็นไปได้ยาก - เคยมีราคานี้น้อย")
    else:
        print(f"   ❌ TP2 เป็นไปได้ยากมาก - เคยมีราคานี้หายากมาก")
else:
    print(f"   ❌ ไม่เคยถึง TP2 ในรอบ 60 วัน - TP2 สูงเกินไป!")

# 5. คำนวณ % การเคลื่อนไหว
print(f"\n{'='*70}")
print("📊 การเคลื่อนไหวที่ต้องการ")
print("="*70)

move_to_tp1 = ((tp1_price - current_price) / current_price) * 100
move_to_tp2 = ((tp2_price - current_price) / current_price) * 100

print(f"\nจากราคาปัจจุบัน (${current_price:.2f}):")
print(f"   • ไป TP1: ต้องขึ้น +{move_to_tp1:.2f}%")
print(f"   • ไป TP2: ต้องขึ้น +{move_to_tp2:.2f}%")

# คำนวณ average daily move
daily_returns = hist['Close'].pct_change().dropna()
avg_daily_move = daily_returns.abs().mean() * 100
max_daily_move = daily_returns.abs().max() * 100
volatility = daily_returns.std() * 100

print(f"\n📈 ความผันผวนในรอบ 60 วัน:")
print(f"   • เคลื่อนไหวเฉลี่ย/วัน: ±{avg_daily_move:.2f}%")
print(f"   • เคลื่อนไหวสูงสุด/วัน: ±{max_daily_move:.2f}%")
print(f"   • Volatility (Std Dev): {volatility:.2f}%")

days_to_tp1 = abs(move_to_tp1 / avg_daily_move) if avg_daily_move > 0 else 999
days_to_tp2 = abs(move_to_tp2 / avg_daily_move) if avg_daily_move > 0 else 999

print(f"\n⏱️ เวลาโดยประมาณ (ถ้าเคลื่อนไหวเฉลี่ย):")
print(f"   • ถึง TP1: ~{days_to_tp1:.0f} วัน")
print(f"   • ถึง TP2: ~{days_to_tp2:.0f} วัน")

if days_to_tp1 <= 14:
    print(f"   ✅ TP1 เหมาะสำหรับ short-term (1-14 วัน)")
elif days_to_tp1 <= 60:
    print(f"   ⚠️ TP1 เหมาะสำหรับ medium-term (2-8 สัปดาห์)")
else:
    print(f"   ❌ TP1 ใช้เวลานานเกินไป")

# 6. สรุป
print(f"\n{'='*70}")
print("🎯 สรุปความสมเหตุสมผล")
print("="*70)

entry_reasonable = days_at_or_below > 0 and diff_from_current < 10
tp1_reasonable = days_above_tp1 > 0 and move_to_tp1 < 15
tp2_reasonable = days_above_tp2 > 0 or move_to_tp2 < 25

print(f"\n💰 Entry Price (${entry_price:.2f}): {'✅ สมเหตุสมผล' if entry_reasonable else '❌ ไม่สมจริง'}")
if entry_reasonable:
    print(f"   → เคยมีราคานี้ และไม่ห่างจากราคาปัจจุบันมาก")
else:
    print(f"   → อาจเป็นราคา calculated ไม่ใช่โอกาสจริง")

print(f"\n🎯 TP1 (${tp1_price:.2f}): {'✅ เป็นไปได้' if tp1_reasonable else '⚠️ ยาก'}")
if tp1_reasonable:
    print(f"   → เคยมีราคานี้ และเคลื่อนไหวไม่มากเกินไป")
else:
    print(f"   → ต้องขึ้นมาก อาจเป็นไปได้ยาก")

print(f"\n🎯 TP2 (${tp2_price:.2f}): {'✅ เป็นไปได้' if tp2_reasonable else '❌ ยากมาก'}")
if tp2_reasonable:
    print(f"   → มีโอกาสถึง แต่ต้องใช้เวลา")
else:
    print(f"   → ต้องขึ้นมาก มักเป็น 'stretch target'")

print(f"\n{'='*70}")
