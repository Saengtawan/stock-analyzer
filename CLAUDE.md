# Stock Analyzer — Claude Code Instructions

## ⛔ OUTPUT FORMAT (MANDATORY)

All scan results MUST use Markdown pipe-table format. The terminal CAN render tables.

✅ CORRECT — all candidates in ONE pipe-table:
| # | Symbol | Gap% | Yest% | Vol | 5d Mom | CPos | Sector | Catalyst | Score |
|---|--------|------|-------|-----|--------|------|--------|----------|-------|
| 1 | SNX | +0.9% | +10.4% | 1.7x | +13.8% | 0.99 | Tech | Q1 beat + upgrades | 5/6 ✅ |
| 2 | WDC | +0.4% | +10.1% | 1.5x | +0.5% | 0.70 | Tech | — | 3/6 ⚠️ |
| 3 | KGC | +0.7% | +4.9% | 1.1x | +10.3% | 0.69 | Gold | Gold rally | 3/6 ⚠️ |

Then add details per stock below the table.

❌ WRONG — never list stocks as separate blocks with `#: 1\nSymbol: SNX\n────────`
The terminal CAN render wide pipe-tables. Always use one table for all candidates.

---

## เมื่อ user ขอ scan หุ้น (ORB / intraday / OVN / หาหุ้น)

**⛔ ก่อนทำอะไร → อ่าน prompt file ที่ตรงกับ scan type:**

| Scan | อ่านไฟล์ | เวลา ET |
|------|---------|---------|
| ORB / หาหุ้น / scan | `prompts/orb_breakout_prompt.md` | 06:00-09:30 |
| Intraday / 3%+ | `prompts/intraday_3pct_prompt.md` | 09:30-11:30 |
| **Top Movers / หุ้นวิ่งแรง** | **`prompts/top_movers_prompt.md`** | **11:30-15:30** |
| OVN / overnight | `prompts/ovn_gap_prompt.md` | 15:30-15:55 |
| Friday / ศุกร์-จันทร์ | `prompts/friday_monday_prompt.md` | ศุกร์ 15:00 |

**ไม่ overlap**: ORB→Intraday handoff ที่ 09:30 | Top Movers→OVN handoff ที่ 15:30

**Prompt file มี rules + stats ครบ (Bounce Mode, Sector, HOLD vs FADE)**
**CLAUDE.md มี scan code + output format — ใช้ร่วมกัน**

จากนั้น **ทำ 5 ขั้นตอนนี้ทุกครั้ง ห้ามข้าม:**

---

### ขั้นตอน 1: เช็คเวลา + ตลาด
```bash
python3 << 'PYEOF'
from datetime import datetime; import pytz; import requests, os, sqlite3
from dotenv import load_dotenv; load_dotenv()
et = datetime.now(pytz.timezone('US/Eastern'))
print(f'ET: {et.strftime("%Y-%m-%d %H:%M %A")}')
h, m = et.hour, et.minute
if h < 4: print('OVERNIGHT')
elif h < 9 or (h == 9 and m < 30): print(f'PRE-MARKET — {(9*60+30)-(h*60+m)}min to open')
elif h < 16: print(f'MARKET OPEN — {(h-9)*60+m-30}min since open')
else: print('CLOSED')
# Alpaca snapshot for SPY + macro from DB
hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
r = requests.get('https://data.alpaca.markets/v2/stocks/snapshots?symbols=SPY', headers=hdr)
if r.status_code == 200:
    s = r.json().get('SPY',{})
    db, pb = s.get('dailyBar',{}), s.get('prevDailyBar',{})
    spy_now = db.get('c',0); spy_prev = pb.get('c',1)
    spy_daily = (spy_now/spy_prev-1)*100
    spy_intra = (db.get('c',0)/db.get('o',1)-1)*100
    print(f'SPY ${spy_now:.2f} daily {spy_daily:+.1f}% {"🟢" if spy_daily > 0 else "🔴"} | intraday {spy_intra:+.1f}%')
conn = sqlite3.connect("data/trade_history.db")
vix_r = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
print(f'VIX {vix_r[0]:.1f}' if vix_r else 'VIX N/A')
conn.close()
PYEOF
```

### ขั้นตอน 2: Scan 200 + hot inject — ปรับตามเวลา

**ถ้า OVERNIGHT / PRE-MARKET / CLOSED → Alpaca snapshots + DB history:**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from dotenv import load_dotenv; load_dotenv()

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03 AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")
syms = list(set(syms + hot))

# 5d history from DB
hist = {}
for r in conn.execute("""
    SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
    WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
    ORDER BY symbol, date
"""):
    hist.setdefault(r[0], []).append(r[1:])
conn.close()

# Alpaca snapshots (2 batches × 100, ~2 seconds total)
snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())
print(f"Loaded {len(snaps)} snapshots")

results = []
for sym in syms:
    try:
        snap = snaps.get(sym)
        days = hist.get(sym, [])
        if not snap or len(days) < 3: continue
        db = snap.get('dailyBar',{}); pb = snap.get('prevDailyBar',{})
        now = db.get('c',0); prev = pb.get('c',0)
        if now < 3 or prev < 1: continue

        last_ret = (now/prev-1)*100
        d0 = days[0]; mom5d = (now/d0[3]-1)*100 if len(days) >= 5 else last_ret
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',now), db.get('l',now)
        rng = hi - lo; cp = (now-lo)/rng if rng > 0 else 0.5
        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr = np.mean(trs[-4:])/now*100 if trs else 0

        if abs(last_ret) >= 2 or abs(mom5d) >= 5:
            results.append((sym, now, last_ret, mom5d, vr, cp, atr))
    except: pass

results.sort(key=lambda x: abs(x[2]), reverse=True)
print(f"{len(results)} ORB candidates")
print(f"{'Sym':5s} {'Price':>7s} {'Yest':>6s} {'5dM':>6s} {'Vol':>4s} {'CPos':>5s} {'ATR':>4s}")
for s,p,yr,m,vr,cp,atr in results[:20]:
    print(f"{s:5s} {p:>7.2f} {yr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {atr:>3.1f}%")
PYEOF
```

**ถ้า MARKET OPEN (09:30-11:30) → Alpaca Intraday scan:**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from dotenv import load_dotenv; load_dotenv()

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03 AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")
syms = list(set(syms + hot))
conn.close()

# Alpaca snapshots — 2 seconds for 200 symbols
snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

# SPY — BOTH daily and intraday
spy = snaps.get('SPY',{})
spy_db, spy_pb = spy.get('dailyBar',{}), spy.get('prevDailyBar',{})
spy_daily = (spy_db.get('c',0)/spy_pb.get('c',1)-1)*100 if spy_pb.get('c') else 0
spy_intra = (spy_db.get('c',0)/spy_db.get('o',1)-1)*100
print(f"📊 SPY daily {spy_daily:+.1f}% {'🟢' if spy_daily > 0 else '🔴'} | intraday {spy_intra:+.1f}%")

# Sector momentum — ดู sector ที่แข็งแรงวันนี้
conn2 = sqlite3.connect("data/trade_history.db")
sectors = dict(conn2.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
conn2.close()
sector_chg = {}
for sym in syms:
    s = snaps.get(sym)
    if not s: continue
    db, pb = s.get('dailyBar',{}), s.get('prevDailyBar',{})
    if pb.get('c',0) > 0:
        sec = sectors.get(sym,'')
        if sec:
            sector_chg.setdefault(sec, []).append((db.get('c',0)/pb['c']-1)*100)
sector_avg = {s: np.mean(v) for s,v in sector_chg.items() if len(v)>=5}
print(f"\n📊 Sector momentum วันนี้:")
for s,v in sorted(sector_avg.items(), key=lambda x: x[1], reverse=True):
    print(f"  {v:+5.1f}% {s}")

up_results = []; dn_results = []
for sym in syms:
    try:
        s = snaps.get(sym)
        if not s: continue
        db = s.get('dailyBar',{}); pb = s.get('prevDailyBar',{})
        mb = s.get('minuteBar',{})
        now = db.get('c',0); opn = db.get('o',0); hi = db.get('h',0); lo = db.get('l',0)
        prev_c = pb.get('c',0); vol = db.get('v',0); prev_vol = pb.get('v',1)
        if now < 3 or opn < 1 or prev_c < 1: continue
        chg = (now/opn-1)*100; daily_chg = (now/prev_c-1)*100
        drop = (lo/opn-1)*100; vr = vol/prev_vol if prev_vol > 0 else 0
        rng = hi-lo; cp = (now-lo)/rng if rng > 0 else 0.5
        last_green = mb.get('c',0) > mb.get('o',0) if mb else False
        pullback = (hi/now-1)*100 if now < hi else 0
        sec = sectors.get(sym,'')

        if drop <= -2 and now > lo:
            dn_results.append((sym, opn, now, chg, drop, (now/lo-1)*100, vr, cp, last_green, daily_chg, sec))
        if chg > 1.5:
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, vr, cp, last_green, pullback, daily_chg, sec))
    except: pass

dn_results.sort(key=lambda x: x[4])
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE (drop 2%+ from open)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,dr,bn,vr,cp,lg,dc,sec in dn_results[:12]:
    f = '🔥' if dr <= -5 else ('✅' if dr <= -3 else '  ')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")

up_results.sort(key=lambda x: (x[8], x[3]), reverse=True)
print(f"\n🔺 {len(up_results)} UP movers (+1.5%+ | PB=pullback from high)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'PB':>4s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,hi,vr,cp,lg,pb,dc,sec in up_results[:12]:
    f = '📐' if pb >= 1.5 else ('🔥' if c > 3 and vr > 2 else '✅')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {hi:+4.1f}% {pb:>3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")
PYEOF
```

**ถ้า MARKET OPEN (11:30-15:30) → Alpaca Top Movers scan:**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from dotenv import load_dotenv; load_dotenv()

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03 AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")
syms = list(set(syms + hot))
conn.close()

# Alpaca snapshots — ~2 seconds
snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

# SPY — BOTH daily and intraday
spy = snaps.get('SPY',{})
spy_db, spy_pb = spy.get('dailyBar',{}), spy.get('prevDailyBar',{})
spy_daily = (spy_db.get('c',0)/spy_pb.get('c',1)-1)*100 if spy_pb.get('c') else 0
spy_intra = (spy_db.get('c',0)/spy_db.get('o',1)-1)*100
print(f"📊 SPY daily {spy_daily:+.1f}% {'🟢' if spy_daily > 0 else '🔴'} | intraday {spy_intra:+.1f}%")

# Sector momentum — ดู sector ที่แข็งแรงวันนี้
conn2 = sqlite3.connect("data/trade_history.db")
sectors = dict(conn2.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
conn2.close()
sector_chg = {}
for sym in syms:
    s = snaps.get(sym)
    if not s: continue
    db, pb = s.get('dailyBar',{}), s.get('prevDailyBar',{})
    if pb.get('c',0) > 0:
        sec = sectors.get(sym,'')
        if sec:
            sector_chg.setdefault(sec, []).append((db.get('c',0)/pb['c']-1)*100)
sector_avg = {s: np.mean(v) for s,v in sector_chg.items() if len(v)>=5}
print(f"\n📊 Sector momentum วันนี้:")
for s,v in sorted(sector_avg.items(), key=lambda x: x[1], reverse=True):
    print(f"  {v:+5.1f}% {s}")

dn_results = []; up_results = []
for sym in syms:
    try:
        s = snaps.get(sym)
        if not s: continue
        db = s.get('dailyBar',{}); pb = s.get('prevDailyBar',{}); mb = s.get('minuteBar',{})
        now = db.get('c',0); opn = db.get('o',0); hi = db.get('h',0); lo = db.get('l',0)
        prev_c = pb.get('c',0); vol = db.get('v',0); prev_vol = pb.get('v',1)
        if now < 1 or opn < 1 or prev_c < 1: continue
        chg = (now/opn-1)*100; daily_chg = (now/prev_c-1)*100
        drop = (lo/opn-1)*100; vr = vol/prev_vol if prev_vol > 0 else 0
        rng = hi-lo; cp = (now-lo)/rng if rng > 0 else 0.5
        last_green = mb.get('c',0) > mb.get('o',0) if mb else False
        pullback = (hi/now-1)*100 if now < hi else 0
        sec = sectors.get(sym,'')

        if drop <= -2 and now > lo:
            dn_results.append((sym, opn, now, chg, drop, (now/lo-1)*100, vr, cp, last_green, daily_chg, sec))
        if chg >= 3:
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, vr, cp, last_green, pullback, daily_chg, sec))
    except: pass

dn_results.sort(key=lambda x: x[4])
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE (drop 2%+ from open)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,dr,bn,vr,cp,lg,dc,sec in dn_results[:12]:
    f = '🔥' if dr <= -5 else ('✅' if dr <= -3 else '  ')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")

up_results.sort(key=lambda x: (x[8], x[3]), reverse=True)
print(f"\n🔺 {len(up_results)} UP movers (+3%+ | PB=pullback from high)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'PB':>4s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,hi,vr,cp,lg,pb,dc,sec in up_results[:12]:
    f = '📐' if pb >= 1.5 else ('🔥' if c > 5 and vr > 2 else '✅')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {hi:+4.1f}% {pb:>3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")
PYEOF
```

### ขั้นตอน 3: ดึง context data ให้ครบ (สำหรับ top 5-8 ตัว)

**ดึง data ทั้งหมดนี้ แล้ว AI ตัดสินเอง — ไม่ hardcode score:**
```bash
# แทน XXX,YYY,ZZZ ด้วย symbols จาก Step 2
sqlite3 data/trade_history.db "
-- News: มีข่าวมั้ย ข่าวอะไร (มีข่าว = attention = ดี ไม่ว่า pos/neg)
SELECT n.symbol, n.sentiment_label, substr(n.headline,1,60), n.published_at
FROM news_events n
WHERE n.symbol IN ('XXX','YYY','ZZZ') AND n.published_at >= date('now','-3 days')
ORDER BY n.published_at DESC LIMIT 15;

-- Short Interest: SI สูง = short squeeze potential ช่วย bounce
-- SI ต่ำ = ไม่มีแรง squeeze → bounce อ่อนกว่า
SELECT s.symbol, s.short_pct_float, s.short_change_pct, u.sector
FROM short_interest s
JOIN universe_stocks u ON s.symbol = u.symbol
WHERE s.symbol IN ('XXX','YYY','ZZZ') AND s.date = (SELECT MAX(date) FROM short_interest);

-- Analyst: consensus ดีมั้ย target เท่าไหร่
SELECT symbol, target_mean, upside_pct, bull_score FROM analyst_consensus
WHERE symbol IN ('XXX','YYY','ZZZ');

-- Earnings: มี earnings ใกล้มั้ย (uncertainty สูง)
SELECT symbol, next_earnings_date FROM earnings_calendar
WHERE symbol IN ('XXX','YYY','ZZZ') AND next_earnings_date BETWEEN date('now') AND date('now','+3 days');

-- Insider: มี insider buy ล่าสุดมั้ย (confidence signal)
SELECT symbol, insider_name, total_value, transaction_date FROM insider_transactions
WHERE symbol IN ('XXX','YYY','ZZZ') AND transaction_date >= date('now','-30 days')
ORDER BY total_value DESC LIMIT 5;

-- Options: put/call ratio สูงมั้ย (hedging = fear)
SELECT symbol, pc_volume_ratio, unusual_call_count, unusual_put_count
FROM options_daily_summary
WHERE symbol IN ('XXX','YYY','ZZZ') AND collected_date = (SELECT MAX(collected_date) FROM options_daily_summary);

-- Beta + MCap (for Winner/Loser profile判断)
-- Beta>1.5 = WR 50% (bad) | Beta<1.0 = WR 54% (good) | MCap>30B = WR 55% (best)
SELECT f.symbol, f.beta, f.market_cap, f.pe_forward, f.sector, f.industry
FROM stock_fundamentals f
WHERE f.symbol IN ('XXX','YYY','ZZZ');
"
```

### ขั้นตอน 4: AI วิเคราะห์ + ตัดสิน

**ใช้ data จาก Step 3 + หลักการจาก prompt file ที่อ่าน → AI ตัดสินเอง:**

หลักการ (จาก backtest 97K+ signals — validated):
- **SPY direction = ดูจาก DAILY (prev close → now) ไม่ใช่ intraday (today open → now)**
  - SPY daily green → bounce WR 58-62% (แม้ intraday จะแดงเล็กน้อยจาก gap up)
  - SPY daily < -1% → WR 34%
  - ตัวอย่าง: SPY +2.4% daily แต่ intraday -0.2% = **วันเขียว** ไม่ใช่วันแดง
- **Drop depth = #1 predictor**: 2-3% drop = WR 53% | 3-5% = 57% | 5%+ = 68%
- **Green bar fraction**: 50%+ green bars (last 30min) = WR 69% | <30% = WR 13%
- **Single green bar**: 1 green then red = WR 37% | 4+ consecutive = WR 61%
- **Beta**: <1.5 = WR 54% (good) | >1.5 = WR 50% (bad) — from stock_fundamentals
- **MCap**: >30B = WR 55% (best) | <10B = WR 51% (worse)
- SI สูง = short squeeze → bounce แรงกว่า
- มีข่าว (ไม่ว่า pos/neg) = มี attention + volume → ดีกว่าไม่มีข่าว
- Sector: ดู sector ที่แข็งแรงวันนั้น (rotation เปลี่ยนทุกวัน — บางวัน Energy นำ บางวัน Tech นำ)
- มี insider buy = executives เชื่อมั่น
- Earnings ใกล้ = uncertainty สูง → อาจดีหรือแย่ ระวัง
- **Gap Down + Vol 2x** = WR 42% (ต่ำกว่า random)
- **Wednesday movers ถือข้ามคืน D+1** = WR 36% (mean reversion — เฉพาะ OVN hold ไม่ใช่ intraday วันนั้น)

**TP/SL data (backtest 126K setups):**
- เช้า avg winner +2.3-3.6% / avg loser -2.3-3.8% (amplitude สูง)
- บ่าย avg winner +1.0-1.8% / avg loser -1.1-1.8% (amplitude ต่ำ)
- 14:00+ avg winner +0.6-0.9% / avg loser -0.6-1.0%
- หลัง hit +2%: เช้า 64% วิ่งต่อ +3% | บ่าย 43% | 14:00+ 32%
- Retrace risk: เช้า 32% retrace <+1% | บ่าย 19%

**Entry characteristics:**
- Bounce เช้า: median 14-18 bars (70-90 min) ค่อยๆ ขึ้น
- Bounce บ่าย: median 17-18 bars ช้า + consolidation ชัด
- 14:00+: median 6 bars (30 min) เร็ว
- **26-30% ของ setups peak ใน ≤3 bars → บางตัววิ่งตรงขึ้นไม่ pullback เลย**
- Limit fill ยาก: ขอบล่างสุดอาจไม่ถึง | กลาง range (70-80%) fill ง่ายกว่า

**เมื่อไหร่ BUY NOW (market) vs WATCH (limit):**
- Winner profile แข็งมาก (Beta<1.5 + MCap>30B + GF≥67% + Drop≥3% + SPY daily green) → **BUY NOW ได้เลย** ที่ราคาปัจจุบัน ไม่ต้องรอ pullback
- Profile ปานกลาง หรือ SPY แดง → WATCH รอ pullback/consolidation
- ถ้ารอ pullback แล้วราคาวิ่งขึ้นเรื่อยๆ → **ไม่ chase** แต่ถ้า profile แข็งพอตั้งแต่แรก ควร BUY NOW ไม่ใช่ WATCH

**AI ดู data ทั้งหมดแล้ว weigh เอง — แต่ละวันต่างกัน context ต่างกัน**
**ไม่มี fixed score — AI judge จาก totality of evidence**

### ขั้นตอน 5: แสดงผล

**แสดงเฉพาะ BUY NOW — ตัวที่ AI มั่นใจแล้วเท่านั้น**
- **BUY NOW** = winner profile แข็ง + entry ได้เลย + AI มั่นใจ → แสดง 1-2 ตัวที่ดีที่สุด
- ตัวที่ไม่ดีพอ / ยังไม่มั่นใจ → **ไม่แสดง** (ไม่แสดง WATCH, ⚠️, ❌, "ไม่แนะนำ")
- ถ้าไม่มีตัวที่ดีพอ → "ไม่มี BUY NOW" + **เวลา re-scan ครั้งถัดไป**
- ถ้ายังก่อนตลาดเปิด / ยังไม่มี data จริง → บอก re-scan เวลาไหน (ไม่ WATCH)

**ตัวอย่าง output — SPY daily green + candidates ดี:**

---

## Scan — 12:30 ET Wed | SPY daily +2.4% 🟢 | intraday -0.1% | VIX 21

### 🟢 BUY NOW

| # | Symbol | Now | SL | TP | R:R | เหตุผล |
|---|--------|-----|-----|-----|-----|--------|
| 1 | INTU | $405 | $392 (-3.2%) | $418 (+3.2%) | 1:1 | Drop -5% + Beta 1.21 + MCap $114B + GF 67% + SPY daily 🟢 |
| 2 | NBIS | $125 | $119 (-4.8%) | $131 (+4.8%) | 1:1 | Drop -5.8% + Beta 1.06 + SI 19.6% + GF 83% |

**INTU**: Winner profile ครบ + SPY daily +2.4% = entry now
**NBIS**: SI 19.6% squeeze + low beta + deep drop

---

**ตัวอย่าง output — ยังไม่มี BUY NOW:**

---

## Scan — 09:42 ET Tue | SPY daily -0.5% 🔴 | VIX 24.2

ไม่มี BUY NOW — SPY daily แดง

Re-check: 10:00 ดู SPY direction | 10:15 ดู green bar fraction

---

### Position Status (ถ้ามี)

| หุ้น | Entry | Now | P&L | Action |
|------|-------|-----|-----|--------|
| AA 10 | $64.87 | $70.49 | +8.7% (+$56) | trail SL $69 |

---

**(ใช้ format นี้ทุกครั้ง — กระชับ ตารางแคบ รายละเอียด 2 บรรทัดต่อตัว)**

---

## เลือก scan type ตามเวลา ET

| เวลา ET | Prompt | ทำอะไร |
|---------|--------|--------|
| **00:00-03:59** | **ORB** | ORB prep: ดู yesterday movers + PM gaps |
| **04:00-09:29** | **ORB** | PM gaps vs prev close + vol + catalyst |
| **09:30-10:00** | **Intraday** | Opening Bell: First bar + OR breakout + Vol Surge |
| **10:00-10:30** | **Intraday** | Kill Zone + 10:00 confirmation + Down Bounce |
| **10:30-11:30** | **Intraday** | Late Morning: Consolidation breakout 47.6% / Noon vol surge |
| **11:30-12:30** | **Top Movers** | Lunch: Down Bounce (SPY green + green bars 50%+) |
| **12:30-13:30** | **Top Movers** | Late Lunch: Down Bounce / Green bar fraction 50%+ |
| **13:30-15:00** | **Top Movers** | Afternoon: Down Bounce (SPY gate) / momentum 5%+ |
| **15:00-15:30** | **Top Movers** | Power Hour: Down Bounce only / hold-exit confirm |
| **15:30-15:55** | **OVN** | 5d mom ≥5% + today green + vol ≥2x + close near high |
| **ศุกร์ 15:00** | **Fri-Mon** | ศุกร์ rally 3%+ / bad week bounce / dump vol 2x |

### ⚠️ Cross-Scan Conflict Rules (ศุกร์ 15:00-15:55)
ศุกร์บ่ายอาจมีหุ้นผ่านทั้ง OVN + Fri-Mon → ใช้กฎนี้:
1. **Fri-Mon ชนะ OVN เสมอวันศุกร์** — Fri-Mon baseline +0.37% ดีกว่า OVN +0.14% (Mon close > Tue open)
2. **ถ้าหุ้นผ่าน Fri-Mon checklist 5/6+ → ใช้ Fri-Mon** (ซื้อศุกร์ ขาย Mon close)
3. **ถ้าหุ้นผ่าน Fri-Mon แค่ 3/6 แต่ OVN 5/6+ → ใช้ OVN** (ซื้อศุกร์ ขาย Mon open)
4. **ไม่ควรเข้าทั้ง 2 scan บนหุ้นเดียวกัน** — เลือกอันที่ดีกว่า


---

## OVN Scan Code (15:30-15:55 ET)
**Checklist + stats → อ่านจาก `prompts/ovn_gap_prompt.md`**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from datetime import datetime
import pytz
from dotenv import load_dotenv; load_dotenv()

et = datetime.now(pytz.timezone('US/Eastern'))
day_name = et.strftime('%A')

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03
    AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")
syms = list(set(syms + hot))

sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
earnings_tomorrow = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now','+1 day')").fetchall())

# 5d history from DB
hist = {}
for r in conn.execute("""
    SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
    WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
    ORDER BY symbol, date
"""):
    hist.setdefault(r[0], []).append(r[1:])
conn.close()

# Alpaca snapshots
snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

results = []
for sym in syms:
    try:
        snap = snaps.get(sym); days = hist.get(sym, [])
        if not snap or len(days) < 3: continue
        db = snap.get('dailyBar',{}); pb = snap.get('prevDailyBar',{})
        last_close = db.get('c',0); prev_close = pb.get('c',0)
        if last_close < 5 or prev_close < 1: continue

        today_ret = (last_close/prev_close-1)*100
        d0 = days[0]; mom5d = (last_close/d0[3]-1)*100 if len(days) >= 5 else today_ret
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',last_close), db.get('l',last_close)
        rng = hi - lo; cp = (last_close-lo)/rng if rng > 0 else 0.5

        sector = sectors.get(sym, 'Unknown')
        good_day = day_name in ('Tuesday','Wednesday')

        score = 0; checks = []
        if mom5d >= 5: score += 1; checks.append(f'☑5dM {mom5d:+.1f}%')
        else: checks.append(f'☐5dM {mom5d:+.1f}%')
        if today_ret >= 2: score += 1; checks.append(f'☑Ret {today_ret:+.1f}%')
        else: checks.append(f'☐Ret {today_ret:+.1f}%')
        if vr >= 2: score += 1; checks.append(f'☑Vol {vr:.1f}x')
        else: checks.append(f'☐Vol {vr:.1f}x')
        if cp > 0.5: score += 1; checks.append(f'☑CP {cp:.2f}')
        else: checks.append(f'☐CP {cp:.2f}')
        checks.append(f'☐{sector[:4]}')  # AI judges sector — no hardcode
        if good_day: score += 1; checks.append(f'☑{day_name[:3]}')
        else: checks.append(f'☐{day_name[:3]}')

        if sym in earnings_tomorrow: continue
        if vr >= 3 and mom5d < 0: continue
        if score < 3: continue

        results.append((sym, last_close, today_ret, mom5d, vr, cp, sector, score, ' | '.join(checks)))
    except: pass

results.sort(key=lambda x: (-x[7], -x[3]))
print(f"\n{len(results)} OVN candidates (Score ≥ 3/6)")
print(f"{'':1s}{'Sym':5s} {'Close':>7s} {'Today':>6s} {'5dM':>6s} {'Vol':>4s} {'CP':>5s} {'Sec':>6s} {'Sc':>2s}")
for s,cl,tr,m,vr,cp,sec,sc,ch in results[:12]:
    f = '🔥' if sc >= 5 else ('✅' if sc >= 4 else '⚠️')
    print(f"{f}{s:5s} {cl:>7.2f} {tr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {sec[:6]:>6s} {sc}/6")
    print(f"  {ch}")
PYEOF
```

---

## Friday→Monday Scan Code (ศุกร์ 15:00-15:55 ET)
**Stats + setups + checklist → อ่านจาก `prompts/friday_monday_prompt.md`**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from datetime import datetime
import pytz
from dotenv import load_dotenv; load_dotenv()

et = datetime.now(pytz.timezone('US/Eastern'))
if et.strftime('%A') != 'Friday':
    print(f"⚠️ วันนี้ {et.strftime('%A')} — Fri-Mon scan ใช้วันศุกร์เท่านั้น!")

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03
    AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")
syms = list(set(syms + hot))

sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
earnings_mon = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date BETWEEN date('now','+2 day') AND date('now','+3 day')").fetchall())
vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
vix_now = float(vix_row[0]) if vix_row else 20.0

# 5d history from DB
hist = {}
for r in conn.execute("""
    SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
    WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
    ORDER BY symbol, date
"""):
    hist.setdefault(r[0], []).append(r[1:])
conn.close()

# Alpaca snapshots
snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

results = []
for sym in syms:
    try:
        snap = snaps.get(sym); days = hist.get(sym, [])
        if not snap or len(days) < 5: continue
        db = snap.get('dailyBar',{})
        last_close = db.get('c',0); last_open = db.get('o',0)
        if last_close < 5 or last_open < 1: continue

        fri_ret = (last_close/last_open - 1)*100
        d0 = days[0]; mom5d = (last_close/d0[3]-1)*100
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',last_close), db.get('l',last_close)
        rng = hi - lo; cp = (last_close-lo)/rng if rng > 0 else 0.5

        sector = sectors.get(sym, 'Unknown')

        setup = ''
        if fri_ret >= 3: setup = 'FRI_RALLY'
        elif mom5d <= -5 and fri_ret >= 2: setup = 'BAD_WEEK_BOUNCE'
        elif fri_ret <= -3 and vr >= 2: setup = 'FRI_DUMP_VOL'
        else: continue

        score = 0; checks = []
        if setup: score += 1; checks.append(f'☑{setup}')
        if cp > 0.5: score += 1; checks.append(f'☑CP {cp:.2f}')
        else: checks.append(f'☐CP {cp:.2f}')
        if vr >= 1.5: score += 1; checks.append(f'☑Vol {vr:.1f}x')
        else: checks.append(f'☐Vol {vr:.1f}x')
        checks.append(f'☐{sector[:4]}')  # AI judges sector
        checks.append('☑NoNews' if sym not in earnings_mon else '☐EarnMon')
        if sym not in earnings_mon: score += 1
        if vix_now < 30: score += 1; checks.append(f'☑VIX {vix_now:.0f}')
        else: checks.append(f'☐VIX {vix_now:.0f}')

        if sym in earnings_mon: continue
        if score < 3: continue

        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr = np.mean(trs[-4:]) if trs else last_close * 0.03
        sl_price = last_close - 2*atr
        sl_pct = (sl_price/last_close - 1)*100

        results.append((sym, last_close, fri_ret, mom5d, vr, cp, sector, setup, score, ' | '.join(checks), sl_price, sl_pct))
    except: pass

results.sort(key=lambda x: (-x[8], -abs(x[2])))
print(f"\n{len(results)} Fri-Mon candidates (Score ≥ 3/6) | VIX {vix_now:.1f}")
print(f"{'':1s}{'Sym':5s} {'Close':>7s} {'FriR':>6s} {'5dM':>6s} {'Vol':>4s} {'CP':>5s} {'Setup':>10s} {'Sc':>2s} {'SL':>7s}")
for s,cl,fr,m,vr,cp,sec,su,sc,ch,slp,slpct in results[:12]:
    f = '🔥' if sc >= 5 else ('✅' if sc >= 4 else '⚠️')
    print(f"{f}{s:5s} {cl:>7.2f} {fr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {su:>10s} {sc}/6 SL${slp:.2f}({slpct:+.0f}%)")
    print(f"  {ch}")
PYEOF
```

---

## Quick Commands อื่นๆ

### "ข่าววันนี้" / "news"
Query `news_events` + `macro_snapshots` ล่าสุด → สรุป risk-on/risk-off

### "ตรวจระบบ" / "system check"
Check: services, DB freshness, cron logs, active positions

### "run discovery"
`PYTHONPATH=src:. python3 scripts/discovery_scan.py`

---

## Project Info
- `src/auto_trading_engine.py` — main engine
- `src/discovery/engine.py` — Discovery scanner
- `src/web/app.py` — webapp
- `config/trading.yaml` / `config/discovery.yaml`
- `prompts/` — detailed trading prompts (ORB, intraday, OVN, friday-monday)
- `data/trade_history.db` — SQLite DB

### DB Tables
- `universe_stocks` — symbol, dollar_vol, sector (1000 ตัว → scan top 200 by dollar_vol)
- `stock_daily_ohlc` — symbol, date, open, high, low, close, volume
- `macro_snapshots` — date, vix_close, spy_close, crude_close, gold_close, yield_10y
- `market_breadth` — date, pct_above_20d_ma, ad_ratio
- `news_events` — published_at, headline, sentiment_label, symbol
- `short_interest` — symbol, date, short_pct_float, short_change_pct
- `insider_transactions` — symbol, insider_name, total_value, transaction_date
- `analyst_consensus` — symbol, target_mean, upside_pct, bull_score
- `earnings_calendar` — symbol, next_earnings_date
- `discovery_outcomes` — symbol, scan_date, actual_return_d3, max_gain, vix_close
- `trading_signals` — symbol, signal_price, score, reasons, signal_time
- `gap_pm_cache` — date, data_json

### Services
- `systemctl --user restart/stop auto-trading.service`
- `systemctl --user restart/stop stock-webapp.service`
- **NEVER pkill** — always use systemctl

### Account
- Alpaca Paper ($5K start, dynamic budget)
- Regime: MacroDayGate ML (16 features, AUC 0.60)
