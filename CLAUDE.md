# Stock Analyzer — Claude Code Instructions

## ⛔ OUTPUT FORMAT (MANDATORY)

All scan results MUST use Markdown pipe-table format. The terminal CAN render tables.

✅ CORRECT — all candidates in ONE pipe-table:
| # | Symbol | Gap% | Yest% | Vol | 5d Mom | CPos | Sector | Catalyst | Score |
|---|--------|------|-------|-----|--------|------|--------|----------|-------|
| 1 | SNX | +0.9% | +10.4% | 1.7x | +13.8% | 0.99 | Tech | Q1 beat + upgrades | 5/6 ✅ |
| 2 | WDC | +0.4% | +10.1% | 1.5x | +0.5% | 0.70 | Tech | — | 3/6 |
| 3 | KGC | +0.7% | +4.9% | 1.1x | +10.3% | 0.69 | Gold | Gold rally | 3/6 |

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

**Prompt file มี data + WR tables — CLAUDE.md มี Score + TP/SL**
**ใช้ร่วมกัน: prompt file = strategy data | CLAUDE.md = scan code + Score + output format**

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
sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())

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
        # NOTE: ก่อนตลาดเปิด dailyBar = yesterday, prevDailyBar = day before yesterday
        # yesterday close = dailyBar.c (ปิดเมื่อวาน)
        yest_close = db.get('c',0)
        if yest_close < 3: continue

        # yesterday intraday return
        yest_ret = (db.get('c',0)/db.get('o',1)-1)*100

        d0 = days[0]; mom5d = (yest_close/d0[3]-1)*100 if len(days) >= 5 else yest_ret
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',yest_close), db.get('l',yest_close)
        rng = hi - lo; cp = (yest_close-lo)/rng if rng > 0 else 0.5
        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr = np.mean(trs[-4:])/yest_close*100 if trs else 0
        sec = sectors.get(sym, '') if 'sectors' in dir() else ''

        # PM gap: ดูจาก latestTrade vs yesterday close (ถ้ามี)
        # snapshot ตอน PM ยังไม่ update — ใช้ได้แค่ yesterday data
        # AI ต้อง re-scan ที่ 09:25 เพื่อเห็น PM gap จริง
        pm_gap = 0  # จะคำนวณได้จริงตอน market open
        has_pm = False

        if abs(yest_ret) >= 2 or abs(pm_gap) >= 1.5 or abs(mom5d) >= 5:
            results.append((sym, now, pm_gap, yest_ret, mom5d, vr, cp, atr, sec, has_pm))
    except: pass

# Sort: PM active first, then by PM gap
results.sort(key=lambda x: (x[9], abs(x[2])), reverse=True)
pm_count = sum(1 for r in results if r[9])
print(f"{len(results)} ORB candidates ({pm_count} มี PM activity)")
print(f"{'Sym':5s} {'Now':>7s} {'PMGap':>6s} {'Yest':>6s} {'5dM':>6s} {'Vol':>4s} {'CPos':>5s} {'ATR':>4s} {'Sec':>8s} {'PM'}")
for s,p,pg,yr,m,vr,cp,atr,sec,pm in results[:20]:
    print(f"{s:5s} {p:>7.2f} {pg:+5.1f}% {yr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {atr:>3.1f}% {sec[:8]:>8s} {'✅' if pm else '—'}")
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
        # VWAP: price above = bullish, below = bearish
        vwap = db.get('vw',0)
        vs_vwap = (now/vwap-1)*100 if vwap > 0 else 0

        if drop <= -2 and now > lo:
            dn_results.append((sym, opn, now, chg, drop, (now/lo-1)*100, vr, cp, last_green, daily_chg, sec))
        if chg > 1.5 or daily_chg > 3:  # intraday up OR daily gap up
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, vr, cp, last_green, pullback, daily_chg, sec))
    except: pass

dn_results.sort(key=lambda x: x[4])
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE (drop 2%+ from open)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,dr,bn,vr,cp,lg,dc,sec in dn_results[:12]:
    f = '  '
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")

up_results.sort(key=lambda x: (x[8], x[3]), reverse=True)
print(f"\n🔺 {len(up_results)} UP movers (check: gap+vol 2x = WR 57% momentum entry | PB=pullback from high)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'PB':>4s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,hi,vr,cp,lg,pb,dc,sec in up_results[:12]:
    f = '  '
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
        if chg >= 3 or daily_chg >= 5:  # intraday up OR daily gap up
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, vr, cp, last_green, pullback, daily_chg, sec))
    except: pass

dn_results.sort(key=lambda x: x[4])
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE (drop 2%+ from open)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,dr,bn,vr,cp,lg,dc,sec in dn_results[:12]:
    f = '  '
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {dc:+4.1f}% {sec[:8]:>8s} {'🟢' if lg else '🔴'}")

up_results.sort(key=lambda x: (x[8], x[3]), reverse=True)
print(f"\n🔺 {len(up_results)} UP movers (check: gap+vol 2x = WR 57% momentum entry | PB=pullback from high)")
print(f"{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'PB':>4s} {'Vol':>4s} {'DChg':>5s} {'Sec':>8s}")
for s,o,n,c,hi,vr,cp,lg,pb,dc,sec in up_results[:12]:
    f = '  '
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

-- Beta + MCap
-- Beta<1.5 = WR 52.3% | Beta>1.5 = WR 50.8% | MCap>30B = WR 52.6%
SELECT f.symbol, f.beta, f.market_cap, f.pe_forward, f.sector, f.industry
FROM stock_fundamentals f
WHERE f.symbol IN ('XXX','YYY','ZZZ');

-- Market Breadth (ดูความแข็งแรงของตลาดรวม)
SELECT date, pct_above_20d_ma, ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1;

-- Earnings: มี earnings ใกล้มั้ย (uncertainty สูง)
SELECT symbol, next_earnings_date FROM earnings_calendar
WHERE symbol IN ('XXX','YYY','ZZZ') AND next_earnings_date BETWEEN date('now') AND date('now','+3 days');
"
```

### ขั้นตอน 4: Score + ตัดสิน

**Score /9 — เรียงหุ้น ตัดสินเร็ว:**

| Factor | เงื่อนไข | Score | WR Impact (backtest) |
|--------|---------|-------|---------------------|
| SPY daily | green | +2 | +20pp (47→67%, N=7.6K) |
| AD ratio | ≥2 | +2 | +15pp (42→57%, N=106K) |
| Setup | Drop ≥3% หรือ Gap+Vol 2x | +1 | มี edge |
| Beta | <1.5 | +1 | +1.5pp (N=94K) |
| Sector | แข็งวันนี้ | +1 | rotation |
| Vol | ≥2x | +1 | +4pp |
| Catalyst | news/upgrade/insider/SI | +1 | attention |

Score 6+ → BUY NOW | 4-5 → พิจารณา | <4 → ไม่แสดง
เรียง: Score สูงสุด → Vol สูง → Beta ต่ำ

**GATE: AD < 1 → WR 43% ทุกช่วง (N=149K) — edge ติดลบ**

**SPY direction = ดูจาก DAILY** (prev close → now) ไม่ใช่ intraday
- SPY +2.4% daily แต่ intraday -0.2% = **วันเขียว**

**2 Play Types:**
- **Bounce**: Drop ≥3% + AD≥2 + SPY green → WR 57-68%
- **Momentum UP**: Gap 2-8% + Vol 2x at open → WR 57-58%

**TP/SL ตามช่วง (full data verified):**

| ช่วง | Long TP | Long SL | EV | Short condition | Short WR |
|------|---------|---------|-----|----------------|---------|
| ORB 09:30 | +2% | -0.5% | +0.42% | SPY red+VIX≥22+Gap dn+Vol 2x | 72% |
| 09:30-10:30 | +1.5% | -0.5% | +0.43% | SPY red+VIX≥22+Gap dn+Vol 2x | 75% |
| 10:30-11:30 | +1.0% | -0.5% | +0.10% | same | — |
| 11:30-15:00 | EOD exit | -0.5% | varies | SPY red+Drop 3%+ | 55% |
| 15:00+ | +0.65% | -0.5% | ~0% | VIX 38+ | 65% |

**11:30-15:00 specific (full data 236K signals):**
- Raw bounce = WR 50% (no edge without filter)
- AD≥3: WR 61-68% per hour (11:30=65%, 12:00=68%, 13:00=62%)
- AD<1: WR 43-45% (negative edge)
- Momentum 8%+ by 11:30 → WR 54% continuation
- EOD exit > TP/SL (backtest confirmed — TP caps winners)

**SHORT = highest edge setup:**
- SPY red + Gap down 2%+ + Vol 2x → WR 72% EV +0.94%
- VIX 38+ short → WR 65%
- SPY green short → WR 42% (negative)

### ขั้นตอน 5: แสดงผล

**เลือก 1-3 ตัวที่ดีที่สุด BUY NOW พร้อม Entry/SL/TP**
- ถ้าไม่มีตัวดี → "ไม่มี BUY NOW" + เวลา re-scan

**ตัวอย่าง output — มีตัวดี:**

---

## Scan — 12:30 ET Wed | SPY +2.4% 🟢 | AD 2.3 | VIX 21

### 🟢 BUY NOW

| # | Symbol | Now | SL | TP | R:R | Score | เหตุผล |
|---|--------|-----|-----|-----|-----|-------|--------|
| 1 | INTU | $405 | $403 (-0.5%) | EOD | — | 7/9 | Drop -5% + Beta 1.21 + MCap $114B + AD 2.3 |
| 2 | NBIS | $125 | $124 (-0.5%) | EOD | — | 6/9 | SI 19.6% + Beta 1.06 + Vol 2x |

**INTU**: deep drop + large cap + SPY green + AD≥2
**NBIS**: SI squeeze + low beta + momentum

Re-check: 13:00

---

**ตัวอย่าง output — ไม่มีตัวดี:**

---

## Scan — 09:42 ET Tue | SPY -0.5% 🔴 | AD 0.8 | VIX 24.2

ไม่มี BUY NOW — AD < 1 (WR 43%)

Re-check: 10:00

---

### Position Status (ถ้ามี)

| หุ้น | Entry | Now | P&L | Action |
|------|-------|-----|-----|--------|
| AA 10 | $64.87 | $70.49 | +8.7% (+$56) | trail SL $69 |

---

## เลือก scan type ตามเวลา ET

| เวลา ET | Prompt | ทำอะไร |
|---------|--------|--------|
| **00:00-03:59** | **ORB** | ORB prep: ดู yesterday movers + PM gaps |
| **04:00-09:29** | **ORB** | PM gaps vs prev close + vol + catalyst |
| **09:30-10:00** | **Intraday** | Opening Bell: First bar + OR breakout + Vol Surge |
| **10:00-10:30** | **Intraday** | Kill Zone + 10:00 confirmation + Down Bounce |
| **10:30-11:30** | **Intraday** | Late Morning: Consolidation breakout 47.6% / Noon vol surge |
| **11:30-12:30** | **Top Movers** | Lunch: Down Bounce + deep drop |
| **12:30-13:30** | **Top Movers** | Late Lunch: Down Bounce + context |
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
    f = '  '
    print(f"{f}{s:5s} {cl:>7.2f} {tr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {sec[:6]:>6s} {sc}/5")
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
    f = '  '
    print(f"{f}{s:5s} {cl:>7.2f} {fr:+5.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {su:>10s} {sc}/5 SL${slp:.2f}({slpct:+.0f}%)")
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
