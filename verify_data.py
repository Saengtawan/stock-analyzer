#!/usr/bin/env python3
"""
ตรวจสอบความถูกต้องของข้อมูล AFRM
"""
import requests
import yfinance as yf

# 1. ดึงราคาจริงจาก Yahoo Finance
print("="*70)
print("📊 ข้อมูลจริงจาก Yahoo Finance")
print("="*70)

ticker = yf.Ticker("AFRM")
info = ticker.info
hist = ticker.history(period="5d")

current_price = hist['Close'].iloc[-1]
print(f"\n💵 ราคาปัจจุบัน (จริง): ${current_price:.2f}")

# Support/Resistance โดยประมาณจาก 20 days
hist_20d = ticker.history(period="20d")
support_20d = hist_20d['Low'].min()
resistance_20d = hist_20d['High'].max()

print(f"📉 Support (20d low): ${support_20d:.2f}")
print(f"📈 Resistance (20d high): ${resistance_20d:.2f}")

# 2. ดึงข้อมูลจาก API
print(f"\n{'='*70}")
print("🤖 ข้อมูลจาก API ของเรา")
print("="*70)

url = "http://127.0.0.1:5002/api/analyze"
data = {"symbol": "AFRM", "time_horizon": "short", "account_value": 100000}

response = requests.post(url, json=data, timeout=120)
result = response.json()

# Technical Analysis
tech = result.get('technical_analysis', {})
unified = result.get('unified_recommendation', {})

api_current_price = tech.get('last_price', 0)
api_support = tech.get('support_1', 0)
api_resistance = tech.get('resistance_1', 0)
api_entry = unified.get('entry_point', 0)
api_tp = unified.get('target_price', 0)
api_sl = unified.get('stop_loss', 0)

print(f"\n💵 ราคาปัจจุบัน (API): ${api_current_price:.2f}")
print(f"📉 Support (API): ${api_support:.2f}")
print(f"📈 Resistance (API): ${api_resistance:.2f}")
print(f"\n🎯 Entry Point (API): ${api_entry:.2f}")
print(f"🎯 Target Price (API): ${api_tp:.2f}")
print(f"🛑 Stop Loss (API): ${api_sl:.2f}")

# 3. ดึงข้อมูลจาก Enhanced Features
ef = result.get('enhanced_features', {})
features = ef.get('features', {})
pnl = features.get('pnl_tracker', {})

entry_data = pnl.get('entry', {})
targets = pnl.get('targets', {})
risk = pnl.get('risk', {})

ef_entry = entry_data.get('price', 0)
ef_tp1 = targets.get('tp1', {}).get('price', 0)
ef_tp2 = targets.get('tp2', {}).get('price', 0)
ef_sl = risk.get('stop_loss', 0)

print(f"\n{'='*70}")
print("💰 Enhanced Features (P&L Tracker)")
print("="*70)
print(f"\n🎯 Entry Price: ${ef_entry:.2f}")
print(f"   Method: {entry_data.get('method', 'N/A')}")
print(f"   Source: {entry_data.get('source', 'N/A')}")

print(f"\n🎯 Target 1 (TP1): ${ef_tp1:.2f}")
print(f"   Progress: {targets.get('tp1', {}).get('progress_pct', 0):.1f}%")

print(f"\n🎯 Target 2 (TP2): ${ef_tp2:.2f}")
print(f"   Progress: {targets.get('tp2', {}).get('progress_pct', 0):.1f}%")

print(f"\n🛑 Stop Loss: ${ef_sl:.2f}")

# 4. เปรียบเทียบ
print(f"\n{'='*70}")
print("🔍 การเปรียบเทียบ")
print("="*70)

print(f"\n💵 ราคาปัจจุบัน:")
print(f"   Yahoo: ${current_price:.2f}")
print(f"   API: ${api_current_price:.2f}")
price_diff_pct = abs(current_price - api_current_price) / current_price * 100
print(f"   ✅ ความแตกต่าง: {price_diff_pct:.2f}%")

print(f"\n📉 Support:")
print(f"   Yahoo (20d low): ${support_20d:.2f}")
print(f"   API: ${api_support:.2f}")

print(f"\n📈 Resistance:")
print(f"   Yahoo (20d high): ${resistance_20d:.2f}")
print(f"   API: ${api_resistance:.2f}")

print(f"\n🎯 Entry vs Support:")
print(f"   Entry: ${ef_entry:.2f}")
print(f"   Support: ${api_support:.2f}")
entry_vs_support = ((ef_entry - api_support) / api_support) * 100
print(f"   Entry อยู่เหนือ Support: {entry_vs_support:+.1f}%")

print(f"\n🎯 TP1 vs Resistance:")
print(f"   TP1: ${ef_tp1:.2f}")
print(f"   Resistance: ${api_resistance:.2f}")
tp1_vs_resistance = ((ef_tp1 - api_resistance) / api_resistance) * 100
print(f"   TP1 อยู่เหนือ Resistance: {tp1_vs_resistance:+.1f}%")

# 5. คำนวณ Risk/Reward
print(f"\n{'='*70}")
print("⚖️ Risk/Reward Ratio")
print("="*70)

current_to_tp1 = ef_tp1 - current_price
current_to_sl = current_price - ef_sl
rr_ratio = current_to_tp1 / current_to_sl if current_to_sl > 0 else 0

print(f"\nจากราคาปัจจุบัน (${current_price:.2f}):")
print(f"   📈 Upside to TP1: ${current_to_tp1:.2f} (+{(current_to_tp1/current_price)*100:.1f}%)")
print(f"   📉 Downside to SL: ${current_to_sl:.2f} (-{(current_to_sl/current_price)*100:.1f}%)")
print(f"   ⚖️ R/R Ratio: {rr_ratio:.2f}:1")

if rr_ratio < 1.5:
    print(f"   ⚠️ R/R ต่ำกว่า 1.5:1 (ไม่คุ้มค่า)")
else:
    print(f"   ✅ R/R สูงกว่า 1.5:1 (คุ้มค่า)")

print(f"\n{'='*70}")
print("สรุป: ข้อมูลถูกต้องหรือไม่?")
print("="*70)

if price_diff_pct < 1:
    print("✅ ราคาปัจจุบัน ตรงกับ Yahoo Finance")
else:
    print("⚠️ ราคาปัจจุบัน แตกต่างจาก Yahoo Finance")

if api_support < current_price < api_resistance:
    print("✅ ราคาอยู่ระหว่าง Support และ Resistance (สมเหตุสมผล)")
else:
    print("⚠️ ราคาอยู่นอกช่วง Support-Resistance")

if ef_entry < current_price:
    print(f"✅ Entry Price (${ef_entry:.2f}) ต่ำกว่าราคาปัจจุบัน (กำไร {((current_price-ef_entry)/ef_entry)*100:.2f}%)")
else:
    print(f"⚠️ Entry Price สูงกว่าราคาปัจจุบัน (ผิดปกติ)")

if ef_tp1 > current_price:
    print(f"✅ TP1 (${ef_tp1:.2f}) สูงกว่าราคาปัจจุบัน (มี upside)")
else:
    print(f"⚠️ TP1 ต่ำกว่าราคาปัจจุบัน (ผิดปกติ)")
