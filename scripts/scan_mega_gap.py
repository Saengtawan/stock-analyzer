#!/usr/bin/env python3
"""
Mega Gap Scanner — หาหุ้นที่ gap up 20%+ ใน Pre-Market
ใช้ตอน 06:00-09:30 ET

Strategy (from backtest 2,652 events):
  - Gap 30-50%: ขึ้นต่อจาก open avg +12% แต่ 58% fade → ขายเร็ว
  - Gap 50%+:   ขึ้นต่อจาก open avg +14% แต่ 61% fade → ขายเร็ว
  - Buy at open → sell within 15-30 min for +5-10%

Usage: python3 scripts/scan_mega_gap.py
"""
import yfinance as yf
import sqlite3
import time
import sys
from datetime import datetime
import pytz

et = datetime.now(pytz.timezone('US/Eastern'))
print(f"🕐 {et.strftime('%Y-%m-%d %H:%M ET %A')}")
print(f"{'='*70}")
print(f"MEGA GAP SCANNER — หุ้น Gap Up 20%+ จาก prev close")
print(f"Strategy: ซื้อ open → ขาย 15-30 นาที (avg +12-14% from open ก่อน fade)")
print(f"{'='*70}\n")

# Build broad universe
conn = sqlite3.connect("data/trade_history.db")
# Top 300 liquid + all universe
syms = [r[0] for r in conn.execute(
    "SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 500"
).fetchall()]
conn.close()

# Add micro-cap / volatile / China AI names
extras = [
    'AIXI','BAOS','TAOP','HOLO','JG','SOS','GFAI','CNET','KXIN','YXT',
    'SMIT','TOP','SOPA','EDTK','CLPS','FAMI',
    'GME','AMC','SOUN','RGTI','QUBT','IONQ','BBAI',
    'HIMS','CVNA','MARA','WULF','CIFR','IREN','AAOI','AXTI',
    'BTBT','CLOV','SNDL','TLRY','BKSY','DRUG','WEST',
    'SMCI','HOOD','SOFI','GRAB','LCID','RIVN',
    'NVAX','MRNA','BNTX','VKTX','SMMT',
]
syms = list(set(syms + extras))
print(f"Scanning {len(syms)} symbols...\n")

results = []
batch_size = 80

for i in range(0, len(syms), batch_size):
    batch = syms[i:i+batch_size]
    if i > 0:
        time.sleep(2)
    try:
        d = yf.download(batch, period="2d", progress=False, threads=True)
        if len(d) == 0:
            continue
        for sym in batch:
            try:
                if hasattr(d['Close'], 'columns'):
                    c = d['Close'][sym].dropna()
                    v = d['Volume'][sym].dropna()
                else:
                    c = d['Close'].dropna()
                    v = d['Volume'].dropna()
                if len(c) < 2:
                    continue

                prev_close = float(c.iloc[-2])
                today_close = float(c.iloc[-1])
                if prev_close < 0.05:
                    continue

                # Get PM/AH quote
                t = yf.Ticker(sym)
                try:
                    fi = t.fast_info
                    pm_price = fi.last_price
                except:
                    pm_price = today_close

                if not pm_price or pm_price <= 0:
                    pm_price = today_close

                # Gap from prev close to current PM price
                gap_pct = (pm_price / prev_close - 1) * 100
                day_chg = (today_close / prev_close - 1) * 100

                if gap_pct >= 20:
                    # Get more info
                    try:
                        info = t.info
                        mcap = info.get('marketCap', 0) or 0
                        flt = info.get('floatShares', 0) or 0
                        name = info.get('shortName', '?')[:25]
                        si = (info.get('shortPercentOfFloat', 0) or 0) * 100
                    except:
                        mcap = 0; flt = 0; name = '?'; si = 0

                    results.append((
                        sym, name, prev_close, today_close, day_chg,
                        pm_price, gap_pct, mcap, flt, si
                    ))
            except:
                pass
    except:
        pass

# Sort by gap size
results.sort(key=lambda x: x[6], reverse=True)

if results:
    print(f"🚀 {len(results)} stocks with Gap ≥20% from prev close!\n")
    print(f"{'':2s}{'Sym':6s} {'Name':25s} {'PrevCl':>7s} {'PM/AH':>7s} {'Gap%':>7s} {'MCap':>8s} {'Float':>8s} {'SI%':>5s}")
    print("-" * 85)

    for s, n, pc, tc, dc, pm, gap, mc, fl, si in results:
        mc_str = f"${mc/1e6:.0f}M" if mc > 0 else "?"
        fl_str = f"{fl/1e6:.1f}M" if fl > 0 else "?"

        if gap >= 50:
            flag = '🚀🚀'
            note = "Buy open → sell 15min (avg +14% before fade, WR 39%)"
        elif gap >= 30:
            flag = '🚀  '
            note = "Buy open → sell 30min (avg +12% before fade, WR 42%)"
        else:
            flag = '📈  '
            note = "Buy open → sell 30min (avg +8% before fade, WR 45%)"

        print(f"{flag}{s:5s} {n:25s} {pc:>7.2f} {pm:>7.2f} {gap:>+6.1f}% {mc_str:>8s} {fl_str:>8s} {si:>4.1f}%")
        print(f"      → {note}")

    print(f"\n{'='*70}")
    print(f"⚠️  RULES:")
    print(f"  1. ซื้อตอน OPEN (09:30) — ไม่ซื้อ PM เพราะ spread กว้าง")
    print(f"  2. ขายใน 15-30 นาที — ห้ามถือ! 58-61% จะ fade กลับ")
    print(f"  3. Target +5-10% จาก open — ไม่โลภ")
    print(f"  4. SL -5% จาก open — ถ้าไม่วิ่งขึ้นทันที = ออก")
    print(f"  5. Size เล็ก — max 2-3% ของพอร์ต")
    print(f"{'='*70}")
else:
    print("❌ ไม่มีหุ้น Gap ≥20% ตอนนี้")
    print("")
    print("ปกติ gap ใหญ่จะเกิดจาก:")
    print("  • Earnings AH/BMO (16:00-09:00 ET)")
    print("  • FDA decisions (overnight)")
    print("  • M&A announcements")
    print("  • Viral social media / short squeeze")
    print("")
    print("💡 Re-run ตอน 06:00-09:00 ET พรุ่งนี้เพื่อจับ PM movers")
