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

| Scan | อ่านไฟล์ |
|------|---------|
| ORB / หาหุ้น / scan (ก่อนเปิด-10:30) | `prompts/orb_breakout_prompt.md` |
| Intraday / 3%+ (ตลาดเปิด) | `prompts/intraday_3pct_prompt.md` |
| OVN / overnight (15:30-15:55) | `prompts/ovn_gap_prompt.md` |
| Friday / ศุกร์-จันทร์ (ศุกร์ 15:00) | `prompts/friday_monday_prompt.md` |

**Prompt file มี rules + stats ครบ (Bounce Mode, Gap Down Reversal, Sector, HOLD vs FADE)**
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

        if last_close >= 5 and atr >= 2 and (last_ret >= 3 or gap >= 2 or mom5d >= 10):
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

**ถ้า MARKET OPEN → ใช้ intraday 5m data:**
```bash
python3 << 'PYEOF'
import yfinance as yf, sqlite3

conn = sqlite3.connect("data/trade_history.db")
# Top 200 by dollar volume
syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
# Hot inject: yesterday's big movers NOT in top 200
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

d = yf.download(syms, period="1d", interval="5m", progress=False)

results = []
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
        vol = int(v.sum())

        h20 = yf.Ticker(sym).history(period='20d')
        avg_vol = int(h20['Volume'].mean()) if len(h20) > 0 else 1
        mins = len(c)*5
        vr = (vol*390/max(mins,1))/avg_vol if avg_vol > 0 else 0

        rng = hi - low
        nh = ((now-low)/rng*100) if rng > 0 else 50
        recent_hi = float(h.iloc[-3:].max()) >= hi*0.998 if len(h) >= 3 else False
        up = float(c.iloc[-1]) > float(c.iloc[-3]) if len(c) >= 3 else True
        fb = (float(c.iloc[0])/opn-1)*100  # first 5min bar

        if now >= 5 and chg > 1.5 and vr > 1.0:
            results.append((sym, opn, now, chg, (hi/opn-1)*100, fb, vr, nh, recent_hi, up))
    except: pass

results.sort(key=lambda x: x[3], reverse=True)
print(f"{len(results)} stocks up >1.5% + vol >1x")
print(f"{'':1s}{'Sym':5s} {'O':>7s} {'Now':>7s} {'Chg':>5s} {'Hi':>5s} {'1st':>5s} {'Vol':>4s} {'NrH':>4s} {'New':>3s} {'Up':>2s}")
for s,o,n,c,hi,fb,vr,nh,rh,up in results[:15]:
    f = '🔥' if c > 3 and vr > 2 and nh > 80 else ('✅' if c > 2 else '  ')
    print(f"{f}{s:5s} {o:>7.2f} {n:>7.2f} {c:+4.1f}% {hi:+4.1f}% {fb:+4.1f}% {vr:>3.1f}x {nh:>3.0f}% {'Y' if rh else 'n'} {'↑' if up else '↓'}")
PYEOF
```

### ขั้นตอน 3: เช็ค catalyst + SI + sector (สำหรับ top 5-8 ตัว)
```bash
sqlite3 data/trade_history.db "
SELECT n.symbol, substr(n.headline,1,60), n.published_at
FROM news_events n
WHERE n.symbol IN ('XXX','YYY','ZZZ') AND n.published_at >= date('now','-3 days')
ORDER BY n.published_at DESC LIMIT 10;
"
sqlite3 data/trade_history.db "
SELECT s.symbol, s.short_pct_float, s.short_change_pct, u.sector
FROM short_interest s
JOIN universe_stocks u ON s.symbol = u.symbol
WHERE s.symbol IN ('XXX','YYY','ZZZ') AND s.date = (SELECT MAX(date) FROM short_interest);
"
sqlite3 data/trade_history.db "
SELECT symbol, target_mean, upside_pct, bull_score FROM analyst_consensus
WHERE symbol IN ('XXX','YYY','ZZZ');
"
sqlite3 data/trade_history.db "
SELECT symbol, next_earnings_date FROM earnings_calendar
WHERE symbol IN ('XXX','YYY','ZZZ') AND next_earnings_date >= date('now') AND next_earnings_date <= date('now','+1 day');
"
```

### ขั้นตอน 4: Score + Filter ตาม prompt file

ใช้ checklist, hard skip, play type (Momentum/Bounce/Gap Down Reversal) จาก prompt file ที่อ่านในขั้นตอนแรก

### ขั้นตอน 5: แสดงผล

**ตัวอย่าง output ที่ถูกต้อง:**

---

## ORB Scan — พฤหัสบดี 2 เม.ย. 03:12 ET (OVERNIGHT)

**SPY** $655.24 (+0.8%) | **VIX** 24.5 | **ES** 6531 | **Gold** $4,627

### Top ORB Candidates

| # | Symbol | Gap% | Yest% | Vol | 5d Mom | CPos | Sector | Catalyst | Score |
|---|--------|------|-------|-----|--------|------|--------|----------|-------|
| 1 | **SNX** | +0.9% | +10.4% | 1.7x | **+13.8%** | 0.99 | Tech | Earnings beat + upgrades | **5/6** ✅ |
| 2 | WDC | +0.4% | +10.1% | 1.5x | +0.5% | 0.70 | Tech | — | 3/6 ⚠️ |
| 3 | INTC | +0.3% | +8.8% | 1.5x | +1.8% | 0.80 | Tech | — | 3/6 ⚠️ |
| 4 | KGC | +0.7% | +4.9% | 1.1x | +10.3% | 0.69 | Gold | Gold rally | 3/6 ⚠️ |

### SNX $188.00 | Entry $188 | SL $182 | TP1 $194 (+3%) | TP2 $197 (+5%)

☑ Gap +10.4% | ☑ Vol 1.7x | ☑ Catalyst: Q1 beat $4.73 vs $3.31 + guidance raise | ☐ 1stBar: รอ 09:30 | ☑ Sector: Tech | ☑ 5d Mom +13.8%

Earnings momentum day 2, CPos 0.99 = ปิดแทบ AT high → continuation signal
⚠️ Day-2 post-gap fade risk + VIX 24.5 HIGH → ลด size, ขาย 50% ถ้าพุ่ง 3%+ ก่อน 10:00

**❌ SKIP:** STX, SNDK, LITE (Vol < 1.5x)

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
| **00:00-03:59** | **ORB** | ORB prep: ดู yesterday movers + PM gaps forming + watchlist |
| **04:00-09:25** | **ORB** | PM gaps vs prev close + vol building + catalyst |
| **09:30-09:45** | **ORB** | First bar + OR high/low → breakout entry |
| **09:45-10:00** | **ORB → Intraday** | OR breakout entry / 10:00 confirmation |
| **10:00** | **Intraday** | ขึ้น 2%+ → 61% / **Vol Surge 3x no gap → 47%** |
| **10:00-10:30** | **Intraday** | ⚠️ Kill Zone: ขาย 50% ถ้า +3% / 10:30 หลุด open → ออก |
| **10:30-12:00** | **Intraday** | Consolidation breakout 47.6% / Noon vol surge 38.1% |
| **12:00** | **Intraday** | ยืน +2% → 51% ถือ / ≤1% → ขาย |
| **13:00-14:00** | **Intraday** | AM high breakout + vol 3x → 13.5% +1% |
| **14:00** | **Intraday** | ยืน +3% → 80% ถือถึงปิด / ≤2% → ขาย |
| **15:30-15:55** | **OVN** | 5d mom ≥5% + today green + vol ≥2x + close near high |
| **ศุกร์ 15:00** | **Fri-Mon** | ศุกร์ rally 3%+ / bad week bounce / dump vol 2x |

### ⚠️ Cross-Scan Conflict Rules (ศุกร์ 15:00-15:55)
ศุกร์บ่ายอาจมีหุ้นผ่านทั้ง OVN + Fri-Mon → ใช้กฎนี้:
1. **Fri-Mon ชนะ OVN เสมอวันศุกร์** — Fri-Mon baseline +0.37% ดีกว่า OVN +0.14% (Mon close > Tue open)
2. **ถ้าหุ้นผ่าน Fri-Mon checklist 5/6+ → ใช้ Fri-Mon** (ซื้อศุกร์ ขาย Mon close)
3. **ถ้าหุ้นผ่าน Fri-Mon แค่ 3/6 แต่ OVN 5/6+ → ใช้ OVN** (ซื้อศุกร์ ขาย Mon open)
4. **ห้ามเข้าทั้ง 2 scan บนหุ้นเดียวกัน** — เลือกอันเดียว


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
