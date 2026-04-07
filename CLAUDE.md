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
from datetime import datetime; import pytz
et = datetime.now(pytz.timezone('US/Eastern'))
print(f'ET: {et.strftime("%Y-%m-%d %H:%M %A")}')
h, m = et.hour, et.minute
if h < 4: print('OVERNIGHT')
elif h < 9 or (h == 9 and m < 30): print(f'PRE-MARKET — {(9*60+30)-(h*60+m)}min to open')
elif h < 16: print(f'MARKET OPEN — {(h-9)*60+m-30}min since open')
else: print('CLOSED')
import yfinance as yf
spy = yf.Ticker('SPY').history(period='5d')
vix = yf.Ticker('^VIX').history(period='5d')
es = yf.Ticker('ES=F').history(period='5d')
gc = yf.Ticker('GC=F').history(period='5d')
prev = spy.iloc[-2]['Close']; now = spy.iloc[-1]['Close']
print(f'SPY ${now:.2f} ({(now/prev-1)*100:+.1f}%) | VIX {vix.iloc[-1]["Close"]:.1f} | ES {es.iloc[-1]["Close"]:.0f} | Gold ${gc.iloc[-1]["Close"]:.0f}')
# VIX zones: <20 NORMAL | 20-24 SKIP (ระวัง) | 24-38 HIGH | >38 EXTREME
PYEOF
```

### ขั้นตอน 2: Scan 200 + hot inject — ปรับตามเวลา

**ถ้า OVERNIGHT / PRE-MARKET / CLOSED → ใช้ daily + PM quotes:**
```bash
python3 << 'PYEOF'
import yfinance as yf, sqlite3, numpy as np

conn = sqlite3.connect("data/trade_history.db")
# Top 200 by dollar volume
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
# Hot inject: yesterday's big movers NOT in top 200 (catches mid-cap catalysts)
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.03
    AND d.volume * d.close >= 5000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers outside top 200: {', '.join(hot[:10])}")
syms = list(set(syms + hot))
conn.close()

d5 = yf.download(syms, period="6d", progress=False, threads=True)

results = []
for sym in syms:
    try:
        c = d5['Close'][sym].dropna()
        v = d5['Volume'][sym].dropna()
        h = d5['High'][sym].dropna()
        lo = d5['Low'][sym].dropna()
        if len(c) < 3: continue

        last_close = float(c.iloc[-1])
        prev_close = float(c.iloc[-2])
        last_ret = (last_close/prev_close-1)*100

        # 5d momentum (สำคัญมาก — mom5d>5% = 41.8% hit +3%)
        mom5d = (float(c.iloc[-1])/float(c.iloc[0])-1)*100 if len(c) >= 5 else last_ret

        # Volume ratio
        avg_vol = float(v.iloc[:-1].mean()) if len(v) > 1 else 1
        last_vr = float(v.iloc[-1])/avg_vol if avg_vol > 0 else 0

        # Close position (0=low, 1=high)
        hi_val = float(h.iloc[-1]); lo_val = float(lo.iloc[-1])
        rng = hi_val - lo_val
        cp = (last_close - lo_val)/rng if rng > 0 else 0.5

        # ATR
        trs = [max(float(h.iloc[i])-float(lo.iloc[i]), abs(float(h.iloc[i])-float(c.iloc[i-1])), abs(float(lo.iloc[i])-float(c.iloc[i-1]))) for i in range(1, min(len(c),5))]
        atr = np.mean(trs)/last_close*100 if trs else 0

        # Pre-market gap (ถ้ามี)
        try:
            hpm = yf.Ticker(sym).history(period="1d", interval="1m", prepost=True)
            pm = float(hpm.iloc[-1]['Close']) if len(hpm) > 0 else last_close
            gap = (pm/last_close-1)*100
        except:
            pm = last_close; gap = 0

        # Filter: yest move needs vol 1.5x+ (82% of yest+3% with low vol = noise)
        # gap and mom5d can pass without vol (PM gap = fresh, mom = trend)
        yest_pass = last_ret >= 3 and last_vr >= 1.5
        gap_pass = gap >= 2
        mom_pass = mom5d >= 10
        if last_close >= 5 and atr >= 2 and (yest_pass or gap_pass or mom_pass):
            results.append((sym, last_close, pm, gap, last_ret, mom5d, last_vr, cp, atr))
    except: pass

# Sort: PM gap first (today's setup), then yest_ret as tiebreaker
results.sort(key=lambda x: (x[3], x[4]), reverse=True)  # gap DESC, yest DESC
print(f"{len(results)} ORB candidates (sorted by PM gap)")
print(f"{'':1s}{'Sym':5s} {'Close':>7s} {'PM':>7s} {'Gap':>5s} {'Yest':>5s} {'5dM':>6s} {'Vol':>4s} {'CPos':>5s} {'ATR':>4s}")
for s,cl,pm,g,yr,m,vr,cp,atr in results[:20]:
    mode = '⛽' if g >= 2 and m < 0 else ('🔥' if m >= 10 and yr >= 3 and vr >= 1.5 else '✅')
    print(f"{mode}{s:5s} {cl:>7.2f} {pm:>7.2f} {g:+4.1f}% {yr:+4.1f}% {m:+5.1f}% {vr:>3.1f}x {cp:>4.2f} {atr:>3.1f}%")
PYEOF
```

**ถ้า MARKET OPEN (09:30-11:30) → Intraday scan (UP movers + DOWN bounce):**
```bash
python3 << 'PYEOF'
import yfinance as yf, sqlite3

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
conn.close()

d = yf.download(syms + ['SPY'], period="1d", interval="5m", progress=False)

# SPY direction (CRITICAL gate — SPY red kills bounce WR to 34%)
try:
    spy_o = float(d['Open']['SPY'].dropna().iloc[0])
    spy_n = float(d['Close']['SPY'].dropna().iloc[-1])
    spy_chg = (spy_n/spy_o-1)*100
    print(f"📊 SPY {spy_chg:+.1f}% intraday {'🟢' if spy_chg > 0 else '🔴'}")
    if spy_chg < -1: print("⚠️ SPY < -1% → bounce WR drops to 34% (ต่ำกว่า random มาก)")
except: spy_chg = 0

up_results = []  # Stocks up (momentum)
dn_results = []  # Stocks down (bounce candidates — BEST setup WR 54-68%)

for sym in syms:
    try:
        c = d['Close'][sym].dropna()
        o = d['Open'][sym].dropna()
        h = d['High'][sym].dropna()
        lo = d['Low'][sym].dropna()
        v = d['Volume'][sym].dropna()
        if len(c) < 5: continue

        opn = float(o.iloc[0]); now = float(c.iloc[-1])
        hi = float(h.max()); low = float(lo.min())
        chg = (now/opn-1)*100
        drop_from_open = (low/opn-1)*100  # max drop from open
        vol = int(v.sum())

        h20 = yf.Ticker(sym).history(period='20d')
        avg_vol = int(h20['Volume'].mean()) if len(h20) > 0 else 1
        mins = len(c)*5
        vr = (vol*390/max(mins,1))/avg_vol if avg_vol > 0 else 0

        # Green bar count (last 3 bars) — need 2+ for real bounce signal
        recent = min(3, len(c))
        green_ct = sum(1 for i in range(-recent, 0) if float(c.iloc[i]) > float(o.iloc[i]))
        last_green = float(c.iloc[-1]) > float(o.iloc[-1])
        fb = (float(c.iloc[0])/opn-1)*100

        if now < 5: continue

        # DOWN BOUNCE: dropped 2%+ from open (BEST setup — deeper drop = higher WR)
        # WR by drop: 2-3%=53%, 3-5%=57%, 5-8%=68%, 8%+=93%
        if drop_from_open <= -2 and now > low:
            bounce_pct = (now/low-1)*100
            dn_results.append((sym, opn, now, chg, drop_from_open, bounce_pct, vr, green_ct, last_green))

        # UP MOVERS: up 1.5%+ with volume
        if chg > 1.5 and vr > 1.0:
            rng = hi - low
            nh = ((now-low)/rng*100) if rng > 0 else 50
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, fb, vr, nh, last_green))
    except: pass

# Down Bounce candidates (BEST setup — deeper drop = higher WR)
dn_results.sort(key=lambda x: x[4])  # deepest drop first (most oversold)
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE candidates (dropped 2%+ from open)")
print(f"  Drop 5%+ = WR 68% | Drop 3-5% = WR 57% | Drop 2-3% = WR 53%")
print(f"{'':1s}{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'Grn':>3s} {'LG':>2s}")
for s,o,n,c,dr,bn,vr,gc,lg in dn_results[:10]:
    f = '🔥' if dr <= -5 else ('✅' if dr <= -3 else '⚠️')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {gc}/3 {'🟢' if lg else '🔴'}")

# Up movers (momentum continuation)
up_results.sort(key=lambda x: x[3], reverse=True)
print(f"\n🔺 {len(up_results)} UP movers (+1.5%+ from open)")
print(f"{'':1s}{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'1st':>5s} {'Vol':>4s} {'NrH':>4s} {'LG':>2s}")
for s,o,n,c,hi,fb,vr,nh,lg in up_results[:10]:
    f = '🔥' if c > 3 and vr > 2 and nh > 80 else ('✅' if c > 2 else '  ')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {hi:+4.1f}% {fb:+4.1f}% {vr:>3.1f}x {nh:>3.0f}% {'🟢' if lg else '🔴'}")
PYEOF
```

**ถ้า MARKET OPEN (11:30-15:30) → Top Movers scan:**
```bash
python3 << 'PYEOF'
import yfinance as yf, sqlite3

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
conn.close()

d = yf.download(syms + ['SPY'], period="1d", interval="5m", progress=False)

# SPY gate (CRITICAL: SPY<-1% → bounce WR=34%, SPY>0% → bounce WR=58-62%)
try:
    spy_o = float(d['Open']['SPY'].dropna().iloc[0])
    spy_n = float(d['Close']['SPY'].dropna().iloc[-1])
    spy_chg = (spy_n/spy_o-1)*100
    print(f"📊 SPY {spy_chg:+.1f}% {'🟢 bounce OK' if spy_chg > 0 else '🔴 bounce RISKY'}")
    if spy_chg < -1: print("⚠️ SPY < -1% → bounce WR = 34% (ต่ำกว่า random มาก)")
except: spy_chg = 0

dn_results = []  # Down bounce (best setup IF SPY green)
up_results = []  # Momentum continuation (up 5%+)

for sym in syms:
    try:
        c = d['Close'][sym].dropna()
        o = d['Open'][sym].dropna()
        h = d['High'][sym].dropna()
        lo = d['Low'][sym].dropna()
        v = d['Volume'][sym].dropna()
        if len(c) < 5: continue

        opn = float(o.iloc[0]); now = float(c.iloc[-1])
        hi = float(h.max()); low = float(lo.min())
        chg = (now/opn-1)*100
        drop_from_open = (low/opn-1)*100
        vol = int(v.sum())

        h20 = yf.Ticker(sym).history(period='20d')
        avg_vol = int(h20['Volume'].mean()) if len(h20) > 0 else 1
        mins = len(c)*5
        vr = (vol*390/max(mins,1))/avg_vol if avg_vol > 0 else 0

        # Green bar fraction (last 6 bars = 30 min) — 50%+ = WR 69%, <30% = WR 13%
        recent = min(6, len(c))
        green_frac = sum(1 for i in range(-recent, 0) if float(c.iloc[i]) > float(o.iloc[i])) / recent
        last_green = float(c.iloc[-1]) > float(o.iloc[-1])

        if now < 1: continue  # allow penny $1+

        # DOWN BOUNCE: dropped 2%+ from open + recovering
        if drop_from_open <= -2 and now > low:
            bounce_pct = (now/low-1)*100
            dn_results.append((sym, opn, now, chg, drop_from_open, bounce_pct, vr, green_frac, last_green))

        # UP MOMENTUM: up 5%+ today (continuation WR 52-56%)
        if chg >= 5 and vr > 1.0:
            rng = hi - low
            nh = ((now-low)/rng*100) if rng > 0 else 50
            up_results.append((sym, opn, now, chg, (hi/opn-1)*100, vr, nh, green_frac, last_green))
    except: pass

# Down bounce — need SPY green + green bar fraction 50%+
dn_results.sort(key=lambda x: (-x[7], x[4]))  # green frac DESC, deeper drop
print(f"\n🔻 {len(dn_results)} DOWN BOUNCE (need SPY green + green bars ≥50%)")
print(f"  GreenFrac 50%+ = WR 69% | GreenFrac <30% = WR 13%")
print(f"{'':1s}{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Drop':>5s} {'Bnc':>5s} {'Vol':>4s} {'GF':>4s} {'LG':>2s}")
for s,o,n,c,dr,bn,vr,gf,lg in dn_results[:10]:
    ok = '🔥' if gf >= 0.5 and spy_chg > 0 else ('✅' if gf >= 0.33 else '⚠️')
    print(f"{ok}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {dr:+4.1f}% +{bn:3.1f}% {vr:>3.1f}x {gf:>3.0%} {'🟢' if lg else '🔴'}")

# Momentum continuation (weaker — WR 52-56%)
up_results.sort(key=lambda x: x[3], reverse=True)
print(f"\n🔺 {len(up_results)} MOMENTUM continuation (up 5%+, WR 52-56%)")
print(f"{'':1s}{'Sym':5s} {'Open':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'Vol':>4s} {'NrH':>4s} {'GF':>4s} {'LG':>2s}")
for s,o,n,c,hi,vr,nh,gf,lg in up_results[:10]:
    f = '🔥' if c > 7 and vr > 2 else ('✅' if c > 5 else '  ')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {hi:+4.1f}% {vr:>3.1f}x {nh:>3.0f}% {gf:>3.0%} {'🟢' if lg else '🔴'}")
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
- **SPY direction = #1 gate**: SPY green → bounce WR 58-62% | SPY<-1% → WR 34% (skip bounce!)
- **Drop depth = #1 predictor**: 2-3% drop = WR 53% | 3-5% = 57% | 5%+ = 68%
- **Green bar fraction**: 50%+ green bars (last 30min) = WR 69% | <30% = WR 13%
- **Single green bar**: 1 green then red = WR 37% | 4+ consecutive = WR 61%
- **Beta**: <1.5 = WR 54% (good) | >1.5 = WR 50% (bad) — from stock_fundamentals
- **MCap**: >30B = WR 55% (best) | <10B = WR 51% (worse)
- SI สูง = short squeeze → bounce แรงกว่า
- มีข่าว (ไม่ว่า pos/neg) = มี attention + volume → ดีกว่าไม่มีข่าว
- Sector Tech/HC/Financial = bounce ดีกว่า Consumer Defensive/Real Estate
- มี insider buy = executives เชื่อมั่น
- Earnings ใกล้ = uncertainty สูง → อาจดีหรือแย่ ระวัง
- **Gap Down + Vol 2x** = WR 42% (ต่ำกว่า random)
- **Wednesday movers D+1** = WR 36% (strong mean reversion)

**TP/SL data (backtest 126K setups):**
- เช้า avg winner +2.3-3.6% / avg loser -2.3-3.8% (amplitude สูง)
- บ่าย avg winner +1.0-1.8% / avg loser -1.1-1.8% (amplitude ต่ำ)
- 14:00+ avg winner +0.6-0.9% / avg loser -0.6-1.0%
- หลัง hit +2%: เช้า 64% วิ่งต่อ +3% | บ่าย 43% | 14:00+ 32%
- Retrace risk: เช้า 32% retrace <+1% | บ่าย 19%

**Entry characteristics:**
- Bounce เช้า: median 14-18 bars (70-90 min) ค่อยๆ ขึ้น มีเวลาเข้า
- Bounce บ่าย: median 17-18 bars ช้า + consolidation ชัด เหมาะ limit
- 14:00+: median 6 bars (30 min) เร็ว เพราะใกล้ปิด
- เพียง 24-30% peak ใน ≤3 bars → ส่วนใหญ่ไม่ต้องรีบ
- WR ≈ 50% สำหรับ green bar เดียว — edge มาจาก context (SPY, drop depth, sector, beta) ไม่ใช่ signal เดียว

**AI ดู data ทั้งหมดแล้ว weigh เอง — แต่ละวันต่างกัน context ต่างกัน**
**ไม่มี fixed score — AI judge จาก totality of evidence**

### ขั้นตอน 5: แสดงผล — เฉพาะ BUY เท่านั้น

**แสดงเฉพาะหุ้นที่ AI ตัดสินว่า BUY ได้เลย**
- ❌ ไม่แสดง SKIP / HOLD / WAIT — user ไม่ต้องกรองเอง
- ❌ ไม่แสดง candidates ที่ไม่ผ่าน
- ✅ แสดงเฉพาะ BUY + Entry/SL/TP พร้อมซื้อ
- ถ้าไม่มีตัวที่ดีพอ → บอก "ไม่มี BUY signal วันนี้" (ดีกว่าฝืนแนะนำ)

**ตัวอย่าง output:**

---

## Scan — 10:15 ET | SPY $655 (+0.5%) | VIX 24.5

### 🟢 BUY

| # | Symbol | Setup | Entry | SL | TP | เหตุผล |
|---|--------|-------|-------|-----|-----|--------|
| 1 | CRWD | Down Bounce $18→$17 | $17.20 | $16.80 | $17.80 (+3.5%) | SI 18% squeeze + Tech sector + green bar |

**CRWD**: ลง -5% จาก open → green bar bounce ที่ $17.20
- SI 18% (short squeeze potential สูง)
- มีข่าว upgrade จาก Morgan Stanley เมื่อวาน
- VIX 24.5 = bounce amplitude ดี
- SL tight ที่ day low $16.80 (-2.3%)

---

**(จบ — ไม่มี SKIP list, ไม่มี HOLD, ไม่มี candidates ที่ไม่ผ่าน)**

### Position Status (ถ้ามี)

| หุ้น | Entry | Now | Total P&L | Today | NrHi | Action |
|------|-------|-----|-----------|-------|------|--------|
| AA 10 | $64.87 | $70.49 | +8.7% (+$56) | +4.3% | 95% | ถือ, trail SL $69 |

### Action Plan

```
08:30 → re-check PM gap + vol สำหรับ SNX
09:30 → first bar: ขึ้น 1%+ = GO / เฉยๆ = WAIT
10:00 → ยังขึ้น 2%+ = 61% ปิด +3% → HOLD / ลง = EXIT
10:30 → higher high = ถือ / หลุด open = ออก
12:00 → ยืน +2% = ถือ / ≤1% = ขาย
14:00 → ยืน +3% = ถือถึงปิด / ≤2% = ขาย
```

---

**(จบตัวอย่าง — ใช้ format นี้ทุกครั้ง ห้ามแสดงเป็น block แยกต่อตัว)**

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
import yfinance as yf, sqlite3, numpy as np
from datetime import datetime
import pytz

et = datetime.now(pytz.timezone('US/Eastern'))
day_name = et.strftime('%A')

conn = sqlite3.connect("data/trade_history.db")
# Top 200 + hot inject
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

# Sector map
sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks WHERE symbol IN ({})".format(','.join('?'*len(syms))), syms).fetchall())

# Earnings tomorrow (Hard Skip)
earnings_tomorrow = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now','+1 day')").fetchall())
conn.close()

d6 = yf.download(syms, period="6d", progress=False, threads=True)

results = []
for sym in syms:
    try:
        c = d6['Close'][sym].dropna()
        v = d6['Volume'][sym].dropna()
        h = d6['High'][sym].dropna()
        lo = d6['Low'][sym].dropna()
        if len(c) < 3: continue

        last_close = float(c.iloc[-1]); prev_close = float(c.iloc[-2])
        today_ret = (last_close/prev_close - 1)*100
        mom5d = (float(c.iloc[-1])/float(c.iloc[0]) - 1)*100 if len(c) >= 5 else today_ret

        avg_vol = float(v.iloc[:-1].mean()) if len(v) > 1 else 1
        vr = float(v.iloc[-1])/avg_vol if avg_vol > 0 else 0

        hi_val = float(h.iloc[-1]); lo_val = float(lo.iloc[-1])
        rng = hi_val - lo_val
        cp = (last_close - lo_val)/rng if rng > 0 else 0.5

        sector = sectors.get(sym, 'Unknown')
        good_sector = sector in ('Technology','Consumer Cyclical','Communication Services','Communication','Basic Materials')
        good_day = day_name in ('Tuesday','Wednesday')

        # Score 6 checklist
        score = 0
        checks = []
        if mom5d >= 5: score += 1; checks.append(f'☑5dM {mom5d:+.1f}%')
        else: checks.append(f'☐5dM {mom5d:+.1f}%')
        if today_ret >= 2: score += 1; checks.append(f'☑Ret {today_ret:+.1f}%')
        else: checks.append(f'☐Ret {today_ret:+.1f}%')
        if vr >= 2: score += 1; checks.append(f'☑Vol {vr:.1f}x')
        else: checks.append(f'☐Vol {vr:.1f}x')
        if cp > 0.5: score += 1; checks.append(f'☑CP {cp:.2f}')
        else: checks.append(f'☐CP {cp:.2f}')
        if good_sector: score += 1; checks.append(f'☑{sector[:4]}')
        else: checks.append(f'☐{sector[:4]}')
        if good_day: score += 1; checks.append(f'☑{day_name[:3]}')
        else: checks.append(f'☐{day_name[:3]}')

        # Hard skip
        if sym in earnings_tomorrow: continue  # earnings BMO tomorrow
        if vr >= 3 and mom5d < 0: continue  # spike + no momentum = 8.3% risk
        if last_close < 5: continue
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
import yfinance as yf, sqlite3, numpy as np
from datetime import datetime
import pytz

et = datetime.now(pytz.timezone('US/Eastern'))
if et.strftime('%A') != 'Friday':
    print(f"⚠️ วันนี้ {et.strftime('%A')} — Fri-Mon scan ใช้วันศุกร์เท่านั้น!")

conn = sqlite3.connect("data/trade_history.db")
# Top 200 + hot inject
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

sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks WHERE symbol IN ({})".format(','.join('?'*len(syms))), syms).fetchall())
# Earnings Monday BMO (Hard Skip)
earnings_mon = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date BETWEEN date('now','+2 day') AND date('now','+3 day')").fetchall())
# VIX
vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
vix_now = float(vix_row[0]) if vix_row else 20.0
conn.close()

d6 = yf.download(syms, period="6d", progress=False, threads=True)

results = []
for sym in syms:
    try:
        c = d6['Close'][sym].dropna()
        v = d6['Volume'][sym].dropna()
        h = d6['High'][sym].dropna()
        lo = d6['Low'][sym].dropna()
        o = d6['Open'][sym].dropna()
        if len(c) < 5: continue

        last_close = float(c.iloc[-1]); last_open = float(o.iloc[-1])
        fri_ret = (last_close/last_open - 1)*100
        mom5d = (float(c.iloc[-1])/float(c.iloc[0]) - 1)*100

        avg_vol = float(v.iloc[:-1].mean()) if len(v) > 1 else 1
        vr = float(v.iloc[-1])/avg_vol if avg_vol > 0 else 0

        hi_val = float(h.iloc[-1]); lo_val = float(lo.iloc[-1])
        rng = hi_val - lo_val
        cp = (last_close - lo_val)/rng if rng > 0 else 0.5

        sector = sectors.get(sym, 'Unknown')
        good_sector = sector in ('Technology','Energy','Basic Materials','Communication Services','Communication')

        # Detect setup type
        setup = ''
        if fri_ret >= 3: setup = 'FRI_RALLY'
        elif mom5d <= -5 and fri_ret >= 2: setup = 'BAD_WEEK_BOUNCE'
        elif fri_ret <= -3 and vr >= 2: setup = 'FRI_DUMP_VOL'
        else: continue  # ศุกร์ปกติ = skip (baseline 24% ไม่คุ้ม)

        # Score 6 checklist
        score = 0; checks = []
        if setup: score += 1; checks.append(f'☑{setup}')
        if cp > 0.5: score += 1; checks.append(f'☑CP {cp:.2f}')
        else: checks.append(f'☐CP {cp:.2f}')
        if vr >= 1.5: score += 1; checks.append(f'☑Vol {vr:.1f}x')
        else: checks.append(f'☐Vol {vr:.1f}x')
        if good_sector: score += 1; checks.append(f'☑{sector[:4]}')
        else: checks.append(f'☐{sector[:4]}')
        checks.append('☑NoNews' if sym not in earnings_mon else '☐EarnMon')
        if sym not in earnings_mon: score += 1
        if vix_now < 30: score += 1; checks.append(f'☑VIX {vix_now:.0f}')
        else: checks.append(f'☐VIX {vix_now:.0f}')

        if last_close < 5: continue
        if sym in earnings_mon: continue  # Hard skip earnings Monday BMO
        if score < 3: continue

        # ATR for SL calc
        trs = [max(float(h.iloc[i])-float(lo.iloc[i]), abs(float(h.iloc[i])-float(c.iloc[i-1])), abs(float(lo.iloc[i])-float(c.iloc[i-1]))) for i in range(1, min(len(c),5))]
        atr = np.mean(trs) if trs else last_close * 0.03
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
