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

# === HARD GATE: AD ratio < 1 → no edge, exit early ===
br = conn.execute("SELECT date, ad_ratio, pct_above_20d_ma FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
ad_ratio = float(br[1]) if br else 1.0
if ad_ratio < 1.0:
    print(f"❌ AD ratio {ad_ratio:.2f} < 1 — no edge (WR 43%). Skip scan.")
    print(f"Re-check market_breadth update next cron cycle.")
    conn.close(); raise SystemExit

syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05 AND d.volume * d.close >= 20000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)} movers: {', '.join(hot[:10])}")

# === Step 1.5: News inject — catch overnight catalysts before snapshot reflects them ===
news_inject = [r[0] for r in conn.execute("""
    SELECT DISTINCT n.symbol FROM news_events n
    JOIN universe_stocks u ON n.symbol = u.symbol
    WHERE n.published_at >= datetime('now','-12 hours')
    AND n.sentiment_label IN ('positive','very_positive')
    AND n.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
""").fetchall()]
if news_inject: print(f"📰 News inject: {len(news_inject)} positive 12h: {', '.join(news_inject[:10])}")

syms = list(set(syms + hot + news_inject))
sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
earnings_today = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now')").fetchall())
earnings_tomorrow = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now','+1 day')").fetchall())

# Symbols with positive news (for catalyst score component)
news_set = set(r[0] for r in conn.execute("""
    SELECT DISTINCT symbol FROM news_events
    WHERE published_at >= datetime('now','-24 hours')
    AND sentiment_label IN ('positive','very_positive')
""").fetchall())
# Symbols with insider buys 30d
insider_set = set(r[0] for r in conn.execute("""
    SELECT DISTINCT symbol FROM insider_transactions
    WHERE transaction_date >= date('now','-30 days') AND total_value >= 100000
""").fetchall())
# Symbols with high SI
si_set = set(r[0] for r in conn.execute("""
    SELECT symbol FROM short_interest
    WHERE date = (SELECT MAX(date) FROM short_interest) AND short_pct_float >= 10
""").fetchall())

# === 3-day sector trend (vs single day = noise) ===
sector_3d = {}
for r in conn.execute("""
    SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0) as avg_chg
    FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
    AND u.sector IS NOT NULL
    GROUP BY u.sector
"""):
    sector_3d[r[0]] = r[1] or 0

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
print(f"Loaded {len(snaps)} snapshots | AD {ad_ratio:.2f} ✅")

# SPY daily green check (for Score) — use macro_snapshots (snapshot stale during PM)
conn2 = sqlite3.connect("data/trade_history.db")
spy_rows = conn2.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
conn2.close()
spy_daily = (spy_rows[0][0]/spy_rows[1][0]-1)*100 if len(spy_rows) >= 2 else 0
spy_green = spy_daily > 0
print(f"SPY daily {spy_daily:+.2f}% {'🟢 GREEN' if spy_green else '🔴 RED'} (from macro_snapshots)")

results = []
for sym in syms:
    try:
        snap = snaps.get(sym)
        days = hist.get(sym, [])
        if not snap or len(days) < 3: continue
        if sym in earnings_today or sym in earnings_tomorrow: continue  # skip earnings
        db = snap.get('dailyBar',{}); pb = snap.get('prevDailyBar',{})
        lt = snap.get('latestTrade', {})
        yest_close = db.get('c',0)
        pm_price = lt.get('p', yest_close) if lt else yest_close
        if yest_close < 3: continue

        yest_ret = (yest_close/db.get('o',1)-1)*100
        pm_gap = (pm_price/yest_close - 1)*100 if pm_price != yest_close else 0
        d0 = days[0]; mom5d = (yest_close/d0[3]-1)*100 if len(days) >= 5 else yest_ret
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        # ATR % for adaptive SL
        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr_pct = np.mean(trs[-4:])/yest_close*100 if trs else 3.0
        sec = sectors.get(sym, '')
        sec_3d_avg = sector_3d.get(sec, 0)  # 3-day trend (less noisy)
        beta = betas.get(sym, 1.5)  # default 1.5 if unknown
        has_catalyst = sym in news_set or sym in insider_set or sym in si_set

        # Mode (sector gate using 3d trend)
        if pm_gap >= 2 and mom5d >= 0: mode = 'PM_MOM'
        elif yest_ret >= 3 and mom5d >= 0: mode = 'MomUP'
        elif mom5d <= -5 and sec_3d_avg >= 0: mode = 'Bounce'
        elif mom5d <= -5: mode = 'KNIFE'  # falling knife — sector down trend
        else: mode = 'Watch'

        # Adaptive SL: ATR-based per mode (avoid noise stops)
        if mode in ('MomUP','PM_MOM'):
            sl_pct = -max(0.5, 0.2 * atr_pct)  # min -0.5%, 0.2×ATR for high-vol stocks
            tp_pct = max(2.0, 0.5 * atr_pct)   # TP at least +2%, scale with vol
        elif mode == 'Bounce':
            sl_pct = -max(1.5, 0.5 * atr_pct)  # min -1.5%, wider for volatile bounces
            tp_pct = max(3.0, 0.8 * atr_pct)   # bigger targets
        else:
            sl_pct = -max(1.0, 0.3 * atr_pct); tp_pct = max(1.5, 0.4 * atr_pct)

        # === SCORE /9 (computed in code, not in head) ===
        score = 0; reasons = []
        if spy_green: score += 2; reasons.append('SPY+')
        if ad_ratio >= 2: score += 2; reasons.append(f'AD{ad_ratio:.1f}')
        if abs(yest_ret) >= 3 or abs(pm_gap) >= 2: score += 1; reasons.append('Setup')
        if beta < 1.5: score += 1; reasons.append(f'β{beta:.1f}')
        if sec_3d_avg >= 0.5: score += 1; reasons.append(f'Sec+{sec_3d_avg:.1f}%')
        if vr >= 2.0: score += 1; reasons.append(f'V{vr:.1f}x')
        if has_catalyst: score += 1
        if has_catalyst:
            cat_tags = []
            if sym in news_set: cat_tags.append('news')
            if sym in insider_set: cat_tags.append('insider')
            if sym in si_set: cat_tags.append('SI')
            reasons.append('+'.join(cat_tags))

        # Filter: skip Knife and skip score <4
        if mode == 'KNIFE': continue
        if abs(yest_ret) < 2 and abs(mom5d) < 5 and abs(pm_gap) < 1.5: continue
        # No min score — always return top N. Score = confidence, not gate

        sl_price = pm_price * (1 + sl_pct/100)
        tp_price = pm_price * (1 + tp_pct/100)
        results.append((sym, pm_price, pm_gap, yest_ret, mom5d, vr, sec, sec_3d_avg, beta, mode, score, atr_pct, sl_pct, tp_pct, sl_price, tp_price, ' '.join(reasons)))
    except: pass

# Sort by score DESC, then mode priority
mode_order = {'PM_MOM':0,'MomUP':1,'Bounce':2,'Watch':3}
results.sort(key=lambda x: (-x[10], mode_order.get(x[9],9)))

# Diversify (max 2/sector, 4 if sec_3d >= 0.5%)
sec_counts = {}; diversified = []
for r in results:
    sec = r[6]; sec_3d = r[7]
    max_picks = 4 if sec_3d >= 0.5 else 2
    if sec_counts.get(sec, 0) >= max_picks: continue
    sec_counts[sec] = sec_counts.get(sec, 0) + 1
    diversified.append(r)

# === ALWAYS return top 3 (user rule: scan must yield 1-3 picks) ===
top_picks = diversified[:3]

mom_n = sum(1 for r in results if r[9] in ('PM_MOM','MomUP'))
bnc_n = sum(1 for r in results if r[9] == 'Bounce')
print(f"\n{len(results)} candidates ({mom_n} mom, {bnc_n} bounce) → TOP 3")
print(f"{'#':>2s} {'Sym':6s} {'Px':>7s} {'Yest':>6s} {'5dM':>6s} {'β':>4s} {'ATR':>5s} {'Sec':>10s} {'Mode':>7s} {'Sc':>3s} {'Tier':>5s} {'SL':>9s} {'TP':>9s}")
for i,(s,p,pg,yr,m,vr,sec,sa,b,mode,sc,atr,slp,tpp,slpr,tppr,rsn) in enumerate(top_picks, 1):
    tier = 'HIGH' if sc >= 7 else ('MED' if sc >= 5 else 'LOW')
    print(f"{i:>2d} {s:6s} {p:>7.2f} {yr:+5.1f}% {m:+5.1f}% {b:>4.1f} {atr:>4.1f}% {sec[:10]:>10s} {mode:>7s} {sc}/9 {tier:>5s} ${slpr:.2f}({slp:+.1f}%) ${tppr:.2f}(+{tpp:.1f}%)")
    print(f"   {rsn}")
PYEOF
```

**ถ้า MARKET OPEN (09:30-11:30) → Alpaca Intraday scan:**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from datetime import datetime
import pytz
from dotenv import load_dotenv; load_dotenv()

# Time-of-day expected volume curve (cumulative % of daily volume by ET hour)
ET_VOL_CURVE = {
    9:  0.05, 10: 0.18, 11: 0.30, 12: 0.42,
    13: 0.52, 14: 0.62, 15: 0.78, 16: 1.00
}
def expected_vol_pct():
    et = datetime.now(pytz.timezone('US/Eastern'))
    h, m = et.hour, et.minute
    if h < 9 or (h == 9 and m < 30): return 0
    if h >= 16: return 1.0
    base = ET_VOL_CURVE.get(h, 0.5)
    next_h = ET_VOL_CURVE.get(h+1, base + 0.1)
    return base + (next_h - base) * (m / 60)
expected_pct = expected_vol_pct()

# Time-decay penalty per backtest continuation rate (60% → 32%)
def time_decay_score():
    et = datetime.now(pytz.timezone('US/Eastern'))
    h, m = et.hour, et.minute
    minutes_from_open = (h - 9) * 60 + (m - 30) if h >= 9 else 0
    if minutes_from_open < 60: return 0    # 09:30-10:30 = full edge
    if minutes_from_open < 120: return 0   # 10:30-11:30 = ok
    if minutes_from_open < 270: return -1  # 11:30-14:00 = weak (lunch hour drag)
    return -2                              # 14:00+ = peak distribution time
td_penalty = time_decay_score()
print(f"📊 Expected vol pct: {expected_pct*100:.0f}% | Time decay: {td_penalty}")

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")

# === HARD GATE: AD ratio < 1 → no edge ===
br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
ad_ratio = float(br[0]) if br else 1.0
if ad_ratio < 1.0:
    print(f"❌ AD ratio {ad_ratio:.2f} < 1 — WR 43% no edge. Skip scan.")
    conn.close(); raise SystemExit

syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05 AND d.volume * d.close >= 20000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)}")

news_inject = [r[0] for r in conn.execute("""
    SELECT DISTINCT n.symbol FROM news_events n
    JOIN universe_stocks u ON n.symbol = u.symbol
    WHERE n.published_at >= datetime('now','-12 hours')
    AND n.sentiment_label IN ('positive','very_positive')
    AND n.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
""").fetchall()]
if news_inject: print(f"📰 News inject: {len(news_inject)}")

syms = list(set(syms + hot + news_inject))
betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
earnings_today = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now')").fetchall())
news_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM news_events WHERE published_at >= datetime('now','-24 hours') AND sentiment_label IN ('positive','very_positive')").fetchall())
insider_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM insider_transactions WHERE transaction_date >= date('now','-30 days') AND total_value >= 100000").fetchall())
si_set = set(r[0] for r in conn.execute("SELECT symbol FROM short_interest WHERE date = (SELECT MAX(date) FROM short_interest) AND short_pct_float >= 10").fetchall())
sector_3d = {}
for r in conn.execute("""
    SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0)
    FROM stock_daily_ohlc d JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
    AND u.sector IS NOT NULL GROUP BY u.sector
"""): sector_3d[r[0]] = r[1] or 0
spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
spy_daily = (spy_rows[0][0]/spy_rows[1][0]-1)*100 if len(spy_rows) >= 2 else 0
spy_green = spy_daily > 0
vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
vix_now = float(vix_row[0]) if vix_row else 20.0
et_hour = datetime.now(pytz.timezone('US/Eastern')).hour
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

results = []
for sym in syms:
    try:
        if sym in earnings_today: continue
        s = snaps.get(sym)
        if not s: continue
        db = s.get('dailyBar',{}); pb = s.get('prevDailyBar',{}); mb = s.get('minuteBar',{})
        now = db.get('c',0); opn = db.get('o',0); hi = db.get('h',0); lo = db.get('l',0)
        prev_c = pb.get('c',0); vol = db.get('v',0); prev_vol = pb.get('v',1)
        if now < 3 or opn < 1 or prev_c < 1: continue
        chg = (now/opn-1)*100; daily_chg = (now/prev_c-1)*100
        drop = (lo/opn-1)*100; vr = vol/prev_vol if prev_vol > 0 else 0
        atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0  # intraday range as ATR
        last_green = mb.get('c',0) > mb.get('o',0) if mb else False
        sec = sectors.get(sym,'')
        sec_3d_avg = sector_3d.get(sec, 0)
        sec_today_avg = sector_avg.get(sec, 0) if 'sector_avg' in dir() else sec_3d_avg
        sec_effective = min(sec_3d_avg, sec_today_avg)
        beta = betas.get(sym, 1.5)
        has_catalyst = sym in news_set or sym in insider_set or sym in si_set
        vol_pace = vr / expected_pct if expected_pct > 0 else 0
        from_peak_pct = (now/hi - 1) * 100 if hi > 0 else 0
        is_stale = from_peak_pct < -1.5
        # Top 3 sectors today (backtest: +19pp edge)
        top3_secs = set(s for s,_ in sorted(sector_avg.items(), key=lambda x: -x[1])[:3]) if 'sector_avg' in dir() else set()
        in_top3_sec = sec in top3_secs

        if chg >= 1.5 and daily_chg >= 0: mode = 'MomUP'
        else: mode = 'Watch'  # Backtest: intraday bounces have no edge — removed

        # Adaptive SL/TP (backtest: trail 1% from peak > fixed TP/SL)
        if mode == 'MomUP':
            sl_pct = -max(1.5, 0.5 * atr_pct)  # wider per backtest (-0.5% = 28% WR)
            tp_pct = max(3.0, 1.0 * atr_pct)  # wider TP, exit via trail 1% in practice
        else:
            sl_pct = -max(1.5, 0.5 * atr_pct); tp_pct = max(2.0, 0.6 * atr_pct)

        # === Score v2 (backtest-driven) ===
        score = 0
        if spy_green: score += 2  # critical after 10:00 (11:00 SPY red = 37% WR)
        if ad_ratio >= 2: score += 2
        if abs(chg) >= 2: score += 1
        if 1.0 <= beta < 2.0: score += 1  # sweet spot (not <1.5)
        if sec_effective >= 0.5: score += 2  # HEAVIER weight (biggest factor)
        if in_top3_sec: score += 2  # NEW: top 3 sector = +19pp
        if 1.5 <= vol_pace < 2.5: score += 1  # refined sweet spot
        if vix_now > 25: score += 1  # NEW: vol = edge
        # Penalties
        score += td_penalty
        if has_catalyst: score -= 1  # NEW: catalyst HURTS momentum
        if vol_pace < 0.5: score -= 1
        if is_stale: score -= 1

        # Hard filters (backtest-validated)
        if mode == 'Watch': continue  # no edge for bounces or indecisive
        if sec_today_avg < -0.5 and chg < 0: continue
        if not spy_green and et_hour >= 11: continue  # SPY red + late = 37% WR
        if chg > 8: continue  # gap too big = losing (WR 38%)
        if vol_pace < 0.3: continue
        if abs(chg) < 1.5: continue

        sl_price = now * (1 + sl_pct/100); tp_price = now * (1 + tp_pct/100)
        results.append((sym, opn, now, chg, drop, vol_pace, daily_chg, sec, sec_effective, beta, last_green, mode, score, atr_pct, sl_pct, tp_pct, sl_price, tp_price, from_peak_pct, is_stale))
    except: pass

mode_order = {'MomUP':0,'Bounce':1,'Watch':2}
results.sort(key=lambda x: (-x[12], mode_order.get(x[11],9)))
sec_counts = {}; diversified = []
for r in results:
    sec = r[7]; sec_3d = r[8]
    max_picks = 4 if sec_3d >= 0.5 else 2
    if sec_counts.get(sec, 0) >= max_picks: continue
    sec_counts[sec] = sec_counts.get(sec, 0) + 1
    diversified.append(r)

top_picks = diversified[:3]
print(f"\n📊 {len(results)} candidates → TOP 3 (TimeDecay {td_penalty})")
print(f"{'#':>2s} {'Sym':6s} {'Now':>7s} {'Chg':>6s} {'VPace':>6s} {'Peak':>7s} {'β':>4s} {'Sec':>10s} {'Mode':>7s} {'Sc':>3s} {'Tier':>5s} {'SL':>9s} {'TP':>9s}")
for i,(s,o,n,c,dr,vp,dc,sec,sa,b,lg,mode,sc,atr,slp,tpp,slpr,tppr,fp,stale) in enumerate(top_picks, 1):
    tier = 'HIGH' if sc >= 7 else ('MED' if sc >= 5 else 'LOW')
    vp_flag = '🟢' if vp >= 1.0 else ('🟡' if vp >= 0.5 else '🔴')
    stale_flag = '🔴STALE' if stale else f'{fp:+.1f}%'
    print(f"{i:>2d} {s:6s} {n:>7.2f} {c:+5.1f}% {vp_flag}{vp:>4.1f}x {stale_flag:>7s} {b:>4.1f} {sec[:10]:>10s} {mode:>7s} {sc}/9 {tier:>5s} ${slpr:.2f}({slp:+.1f}%) ${tppr:.2f}(+{tpp:.1f}%)")
PYEOF
```

**ถ้า MARKET OPEN (11:30-15:30) → Alpaca Top Movers scan:**
```bash
python3 << 'PYEOF'
import requests, os, sqlite3, numpy as np
from datetime import datetime
import pytz
from dotenv import load_dotenv; load_dotenv()

ET_VOL_CURVE = {9: 0.05, 10: 0.18, 11: 0.30, 12: 0.42, 13: 0.52, 14: 0.62, 15: 0.78, 16: 1.00}
def expected_vol_pct():
    et = datetime.now(pytz.timezone('US/Eastern'))
    h, m = et.hour, et.minute
    if h < 9 or (h == 9 and m < 30): return 0
    if h >= 16: return 1.0
    base = ET_VOL_CURVE.get(h, 0.5)
    next_h = ET_VOL_CURVE.get(h+1, base + 0.1)
    return base + (next_h - base) * (m / 60)
expected_pct = expected_vol_pct()
def time_decay_score():
    et = datetime.now(pytz.timezone('US/Eastern'))
    h, m = et.hour, et.minute
    minutes_from_open = (h - 9) * 60 + (m - 30) if h >= 9 else 0
    if minutes_from_open < 60: return 0
    if minutes_from_open < 120: return 0
    if minutes_from_open < 270: return -1
    return -2
td_penalty = time_decay_score()
print(f"📊 Expected vol pct: {expected_pct*100:.0f}% | Time decay: {td_penalty}")

hdr = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY'), 'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY')}
conn = sqlite3.connect("data/trade_history.db")

# === HARD GATE: AD ratio < 1 ===
br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
ad_ratio = float(br[0]) if br else 1.0
if ad_ratio < 1.0:
    print(f"❌ AD ratio {ad_ratio:.2f} < 1 — WR 43% no edge. Skip.")
    conn.close(); raise SystemExit

syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05 AND d.volume * d.close >= 20000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)}")

news_inject = [r[0] for r in conn.execute("""
    SELECT DISTINCT n.symbol FROM news_events n
    JOIN universe_stocks u ON n.symbol = u.symbol
    WHERE n.published_at >= datetime('now','-12 hours')
    AND n.sentiment_label IN ('positive','very_positive')
    AND n.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
""").fetchall()]
if news_inject: print(f"📰 News inject: {len(news_inject)}")

syms = list(set(syms + hot + news_inject))
betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
earnings_today = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now')").fetchall())
news_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM news_events WHERE published_at >= datetime('now','-24 hours') AND sentiment_label IN ('positive','very_positive')").fetchall())
insider_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM insider_transactions WHERE transaction_date >= date('now','-30 days') AND total_value >= 100000").fetchall())
si_set = set(r[0] for r in conn.execute("SELECT symbol FROM short_interest WHERE date = (SELECT MAX(date) FROM short_interest) AND short_pct_float >= 10").fetchall())
sector_3d = {}
for r in conn.execute("""
    SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0)
    FROM stock_daily_ohlc d JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
    AND u.sector IS NOT NULL GROUP BY u.sector
"""): sector_3d[r[0]] = r[1] or 0
spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
spy_daily = (spy_rows[0][0]/spy_rows[1][0]-1)*100 if len(spy_rows) >= 2 else 0
spy_green = spy_daily > 0
vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
vix_now = float(vix_row[0]) if vix_row else 20.0
et_hour = datetime.now(pytz.timezone('US/Eastern')).hour
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

results = []
for sym in syms:
    try:
        if sym in earnings_today: continue
        s = snaps.get(sym)
        if not s: continue
        db = s.get('dailyBar',{}); pb = s.get('prevDailyBar',{}); mb = s.get('minuteBar',{})
        now = db.get('c',0); opn = db.get('o',0); hi = db.get('h',0); lo = db.get('l',0)
        prev_c = pb.get('c',0); vol = db.get('v',0); prev_vol = pb.get('v',1)
        if now < 1 or opn < 1 or prev_c < 1: continue
        chg = (now/opn-1)*100; daily_chg = (now/prev_c-1)*100
        drop = (lo/opn-1)*100; vr = vol/prev_vol if prev_vol > 0 else 0
        atr_pct = (hi - lo) / now * 100 if now > 0 else 3.0
        last_green = mb.get('c',0) > mb.get('o',0) if mb else False
        sec = sectors.get(sym,'')
        sec_3d_avg = sector_3d.get(sec, 0)
        sec_today_avg = sector_avg.get(sec, 0) if 'sector_avg' in dir() else sec_3d_avg
        sec_effective = min(sec_3d_avg, sec_today_avg)
        beta = betas.get(sym, 1.5)
        has_catalyst = sym in news_set or sym in insider_set or sym in si_set
        vol_pace = vr / expected_pct if expected_pct > 0 else 0
        from_peak_pct = (now/hi - 1) * 100 if hi > 0 else 0
        is_stale = from_peak_pct < -1.5
        top3_secs = set(s for s,_ in sorted(sector_avg.items(), key=lambda x: -x[1])[:3])
        in_top3_sec = sec in top3_secs

        if daily_chg >= 3 and chg >= 0: mode = 'MomCont'
        else: mode = 'Watch'  # Backtest: no edge for intraday bounces

        # Adaptive SL/TP (backtest: trail 1% from peak > fixed TP/SL)
        if mode == 'MomCont':
            sl_pct = -max(1.5, 0.5 * atr_pct)  # wider per backtest
            tp_pct = max(3.0, 1.0 * atr_pct)   # EOD + trail 1%
        else:
            sl_pct = -max(1.5, 0.5 * atr_pct); tp_pct = max(2.0, 0.6 * atr_pct)

        # === Score v2 (backtest-driven) ===
        score = 0
        if spy_green: score += 2
        if ad_ratio >= 2: score += 2
        if abs(daily_chg) >= 3: score += 1
        if 1.0 <= beta < 2.0: score += 1  # sweet spot
        if sec_effective >= 0.5: score += 2  # biggest factor
        if in_top3_sec: score += 2  # top 3 sector = +19pp
        if 1.5 <= vol_pace < 2.5: score += 1
        if vix_now > 25: score += 1
        score += td_penalty
        if has_catalyst: score -= 1  # catalyst HURTS momentum
        if vol_pace < 0.5: score -= 1
        if is_stale: score -= 1

        if vol_pace < 0.5: score -= 1
        if is_stale: score -= 1

        if mode == 'Watch': continue  # no edge (bounces debunked)
        if sec_today_avg < -0.5 and chg < 0: continue
        if not spy_green and et_hour >= 11: continue  # SPY red + late = dead
        if daily_chg > 8: continue  # gap too big = losing
        if vol_pace < 0.3: continue
        if abs(daily_chg) < 3: continue

        sl_price = now * (1 + sl_pct/100); tp_price = now * (1 + tp_pct/100)
        results.append((sym, opn, now, chg, drop, vol_pace, daily_chg, sec, sec_effective, beta, last_green, mode, score, atr_pct, sl_pct, tp_pct, sl_price, tp_price, from_peak_pct, is_stale))
    except: pass

mode_order = {'MomCont':0,'Bounce':1,'Watch':2}
results.sort(key=lambda x: (-x[12], mode_order.get(x[11],9)))
sec_counts = {}; diversified = []
for r in results:
    sec = r[7]; sec_3d = r[8]
    max_picks = 4 if sec_3d >= 0.5 else 2
    if sec_counts.get(sec, 0) >= max_picks: continue
    sec_counts[sec] = sec_counts.get(sec, 0) + 1
    diversified.append(r)

top_picks = diversified[:3]
print(f"\n📊 {len(results)} candidates → TOP 3 (TimeDecay {td_penalty})")
print(f"{'#':>2s} {'Sym':6s} {'Now':>7s} {'DChg':>6s} {'VPace':>6s} {'Peak':>7s} {'β':>4s} {'Sec':>10s} {'Mode':>7s} {'Sc':>3s} {'Tier':>5s} {'SL':>9s} {'TP':>9s}")
for i,(s,o,n,c,dr,vp,dc,sec,sa,b,lg,mode,sc,atr,slp,tpp,slpr,tppr,fp,stale) in enumerate(top_picks, 1):
    tier = 'HIGH' if sc >= 7 else ('MED' if sc >= 5 else 'LOW')
    vp_flag = '🟢' if vp >= 1.0 else ('🟡' if vp >= 0.5 else '🔴')
    stale_flag = '🔴STALE' if stale else f'{fp:+.1f}%'
    print(f"{i:>2d} {s:6s} {n:>7.2f} {dc:+5.1f}% {vp_flag}{vp:>4.1f}x {stale_flag:>7s} {b:>4.1f} {sec[:10]:>10s} {mode:>7s} {sc}/9 {tier:>5s} ${slpr:.2f}({slp:+.1f}%) ${tppr:.2f}(+{tpp:.1f}%)")
PYEOF
```

### ขั้นตอน 3: ดึง context data ให้ครบ (สำหรับ top 5-8 ตัว)

**ใช้ symbols จริงจาก Step 2 — ไม่ต้อง replace มือ:**
```bash
# ใส่ top 5-8 symbols จาก Step 2 ตรงนี้
SYMS="'SYM1','SYM2','SYM3','SYM4','SYM5'"
sqlite3 data/trade_history.db "
-- News (มีข่าว = attention = ดี ไม่ว่า pos/neg)
SELECT n.symbol, n.sentiment_label, substr(n.headline,1,60), n.published_at
FROM news_events n WHERE n.symbol IN ($SYMS) AND n.published_at >= date('now','-3 days')
ORDER BY n.published_at DESC LIMIT 15;

-- Short Interest (SI สูง = squeeze potential)
SELECT s.symbol, s.short_pct_float, s.short_change_pct, u.sector
FROM short_interest s JOIN universe_stocks u ON s.symbol = u.symbol
WHERE s.symbol IN ($SYMS) AND s.date = (SELECT MAX(date) FROM short_interest);

-- Analyst consensus
SELECT symbol, target_mean, upside_pct, bull_score FROM analyst_consensus WHERE symbol IN ($SYMS);

-- Earnings within 3 days (uncertainty risk)
SELECT symbol, next_earnings_date FROM earnings_calendar
WHERE symbol IN ($SYMS) AND next_earnings_date BETWEEN date('now') AND date('now','+3 days');

-- Insider buys (confidence signal)
SELECT symbol, insider_name, total_value, transaction_date FROM insider_transactions
WHERE symbol IN ($SYMS) AND transaction_date >= date('now','-30 days') ORDER BY total_value DESC LIMIT 5;

-- Options flow (put/call ratio)
SELECT symbol, pc_volume_ratio, unusual_call_count, unusual_put_count FROM options_daily_summary
WHERE symbol IN ($SYMS) AND collected_date = (SELECT MAX(collected_date) FROM options_daily_summary);

-- Beta + MCap (Beta<1.5 = WR 52.3% | MCap>30B = WR 52.6%)
SELECT f.symbol, f.beta, f.market_cap, f.pe_forward, f.sector, f.industry
FROM stock_fundamentals f WHERE f.symbol IN ($SYMS);

-- Market Breadth
SELECT date, pct_above_20d_ma, ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1;
"
```

### ขั้นตอน 4: Score + ตัดสิน

**Score v2 (backtest-driven, 20M bars, 2025+)**:

| Factor | เงื่อนไข | Score | WR Impact |
|--------|---------|-------|-----------|
| SPY daily | green | +2 | +8pp @ 10:00, **+19pp @ 11:00** |
| AD ratio | ≥2 | +2 | +15pp (N=106K) |
| **Sec3d** | ≥ 0.5% | **+2** | **71.6% WR** (biggest factor) |
| **Top 3 sector today** | in top 3 | **+2** | +19pp vs rest |
| Setup | gain 3-8% or drop 3-5% | +1 | sweet spot |
| **Beta** | 1.0-2.0 | +1 | **sweet spot** (not <1.5) |
| Vol pace | 1.5-2.5x | +1 | refined sweet spot |
| **VIX** | > 25 | **+1** | NEW (vol = edge) |
| **Catalyst** | any news/insider/SI | **-1** | **NEGATIVE** — hurts momentum |
| Time decay | ≥11:30 | **-1 to -2** | WR drops post-11:00 |
| Stale | >1.5% below peak | -1 | peak passed |

**Max realistic: 12 points** (SPY+2, AD+2, Sec3d+2, Top3+2, Setup+1, Beta+1, Vol+1, VIX+1)
**Display as /9 for consistency** (cap at 9)

Score 6+ → BUY NOW | 4-5 → พิจารณา | <4 → ไม่แสดง
เรียง: Score สูงสุด → Vol สูง → Beta ต่ำ

**GATE: AD < 1 → WR 43% ทุกช่วง (N=149K) — edge ติดลบ**

**SPY direction = ดูจาก DAILY** (prev close → now) ไม่ใช่ intraday
- SPY +2.4% daily แต่ intraday -0.2% = **วันเขียว**

**2 Play Types:**
- **Bounce**: Drop ≥3% + AD≥2 + SPY green → WR 57-68%
- **Momentum UP**: Gap 2-8% + Vol 2x at open → WR 57-58%

**TP/SL — backtest-verified (20M 5-min bars, 274K symbol-days)**

### CRITICAL backtest findings (2025+ data)
- **SL -0.5% tight = 28% WR** (noise stops) 🔴
- **SL -3% wider = 54% WR** ✅
- **Trail 1% from peak** = **best EV +0.93%** ⭐ (beats fixed TP/SL)
- **Fixed TP +2% / SL -0.5%** = EV +0.43% (worse than trail)
- **EOD hold** = 57% WR +0.88% (2nd best)

### Recommended SL/TP per entry

| Strategy | Entry | SL | TP | Exit |
|---|---|---|---|---|
| **Momentum UP (09:50-10:30)** | 3-8% gain from open | -max(1.5%, 0.5×ATR) | n/a | **Trail 1% from peak OR EOD** |
| **Momentum (10:30-11:30)** | Same | -1.5% | n/a | Trail 1% |
| **Afternoon (13:00 strict)** | fresh + vol + SPY green | -2% | n/a | Trail 1% OR EOD |
| **Gap Down bounce at open** | Gap -3 to -5% | -2% | +1% | EOD |

### What the backtest DEBUNKED

| Old rule | Backtest verdict |
|---|---|
| "Gap UP + Vol 2x = WR 51-65%" | **FALSE for buy-open hold-close** (WR 39-43%) |
| "Tight SL -0.5% saves capital" | **FALSE** — noise stops, WR drops to 28% |
| "Intraday bounce edge" | **FALSE** — all drop depths 42-52% WR |
| "Beta <1.5 best" | **FALSE** — Beta 1.0-2.0 is sweet spot |
| "Catalyst helps" | **FALSE** — no catalyst = 58% WR, news = 50% |

### Short Entries (unchanged — separate backtest not yet run)
| ช่วง | Condition | Short WR |
|------|-----------|----------|
| ORB 09:30 | SPY red+VIX≥22+Gap dn+Vol 2x | 72%* |
| 09:30-10:30 | same | 75%* |

*From old backtest — not re-validated in v2 suite

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

**⛔ HARD RULE: scan output = fresh recommendation จากข้อมูลปัจจุบัน เท่านั้น**

ห้าม assume ว่า user ถือ position ใดๆ จาก scan ก่อนหน้า:
- ❌ "ถ้าซื้อ X ไปแล้ว..."
- ❌ "trail SL ขึ้นมา..."
- ❌ "lock profit ตอนนี้"
- ❌ "exit ตอน..."
- ❌ "Position update" / "P&L"

✅ อนุญาต:
- TOP 3 picks ปัจจุบัน + ราคา/SL/TP คำนวณจากตอน scan นี้
- เปรียบเทียบกับ scan ก่อนเพื่อ persistence ranking ("NBIS อยู่ใน 5 scans ติด")
- Sector trend / market state

**Position management = command แยก** — ถ้า user อยากเช็ค P&L ต้องบอก "เช็ค X" / "position status" ไม่ใช่ส่วนของ "scan หุ้น"

**เลือก 1-3 ตัวที่ดีที่สุด พร้อม Entry/SL/TP** (always 1-3 picks per scan, no "ไม่มี BUY NOW" except AD<1)

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

### Position Status (เฉพาะตอน user ขอ "position status" / "เช็ค X")

ห้ามแสดงใน scan ปกติ — แยก command

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

# === HARD GATE: AD ratio < 1 ===
br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
ad_ratio = float(br[0]) if br else 1.0
if ad_ratio < 1.0:
    print(f"❌ AD ratio {ad_ratio:.2f} < 1 — WR 43% no edge. Skip OVN.")
    conn.close(); raise SystemExit

syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05
    AND d.volume * d.close >= 20000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)}")

news_inject = [r[0] for r in conn.execute("""
    SELECT DISTINCT n.symbol FROM news_events n
    JOIN universe_stocks u ON n.symbol = u.symbol
    WHERE n.published_at >= datetime('now','-12 hours')
    AND n.sentiment_label IN ('positive','very_positive')
    AND n.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
""").fetchall()]
if news_inject: print(f"📰 News inject: {len(news_inject)}")

syms = list(set(syms + hot + news_inject))
sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
earnings_tomorrow = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date = date('now','+1 day')").fetchall())
news_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM news_events WHERE published_at >= datetime('now','-24 hours') AND sentiment_label IN ('positive','very_positive')").fetchall())
insider_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM insider_transactions WHERE transaction_date >= date('now','-30 days') AND total_value >= 100000").fetchall())
si_set = set(r[0] for r in conn.execute("SELECT symbol FROM short_interest WHERE date = (SELECT MAX(date) FROM short_interest) AND short_pct_float >= 10").fetchall())

# 3-day sector trend
sector_3d = {}
for r in conn.execute("""
    SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0)
    FROM stock_daily_ohlc d JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
    AND u.sector IS NOT NULL GROUP BY u.sector
"""): sector_3d[r[0]] = r[1] or 0

# 5d history
hist = {}
for r in conn.execute("""
    SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
    WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
    ORDER BY symbol, date
"""): hist.setdefault(r[0], []).append(r[1:])

# SPY direction from macro_snapshots
spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
spy_daily = (spy_rows[0][0]/spy_rows[1][0]-1)*100 if len(spy_rows) >= 2 else 0
spy_green = spy_daily > 0
conn.close()

snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

print(f"AD {ad_ratio:.2f} ✅ | SPY {spy_daily:+.2f}% {'🟢' if spy_green else '🔴'}")

results = []
for sym in syms:
    try:
        snap = snaps.get(sym); days = hist.get(sym, [])
        if not snap or len(days) < 3: continue
        if sym in earnings_tomorrow: continue
        db = snap.get('dailyBar',{}); pb = snap.get('prevDailyBar',{})
        last_close = db.get('c',0); prev_close = pb.get('c',0)
        if last_close < 5 or prev_close < 1: continue

        today_ret = (last_close/prev_close-1)*100
        d0 = days[0]; mom5d = (last_close/d0[3]-1)*100 if len(days) >= 5 else today_ret
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',last_close), db.get('l',last_close)
        rng = hi - lo; cp = (last_close-lo)/rng if rng > 0 else 0.5
        # 4-day ATR
        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr_pct = np.mean(trs[-4:])/last_close*100 if trs else 3.0

        sec = sectors.get(sym, 'Unknown')
        sec_3d_avg = sector_3d.get(sec, 0)
        beta = betas.get(sym, 1.5)
        has_catalyst = sym in news_set or sym in insider_set or sym in si_set
        good_day = day_name in ('Tuesday','Wednesday')

        ovn_setup = mom5d >= 5 and today_ret >= 2

        score = 0; reasons = []
        if spy_green: score += 2; reasons.append('SPY+')
        if ad_ratio >= 2: score += 2; reasons.append(f'AD{ad_ratio:.1f}')
        if ovn_setup: score += 1; reasons.append(f'5d{mom5d:+.0f}%/T{today_ret:+.0f}%')
        if beta < 1.5: score += 1; reasons.append(f'β{beta:.1f}')
        if sec_3d_avg >= 0.5: score += 1; reasons.append(f'Sec+{sec_3d_avg:.1f}%')
        if vr >= 2.0: score += 1; reasons.append(f'V{vr:.1f}x')
        if has_catalyst:
            score += 1
            cat = []
            if sym in news_set: cat.append('news')
            if sym in insider_set: cat.append('insider')
            if sym in si_set: cat.append('SI')
            reasons.append('+'.join(cat))

        if cp < 0.5: continue
        if vr >= 3 and mom5d < 0: continue
        if not (mom5d >= 5 or today_ret >= 2): continue
        if sec_3d_avg < 0: continue
        # No min score — return top 3 always

        # OVN SL/TP — wider since holding overnight (gap risk both ways)
        sl_pct = -max(2.0, 0.7 * atr_pct)  # wider for overnight
        tp_pct = max(3.0, 1.0 * atr_pct)
        sl_price = last_close * (1 + sl_pct/100)
        tp_price = last_close * (1 + tp_pct/100)

        results.append((sym, last_close, today_ret, mom5d, vr, cp, sec, sec_3d_avg, beta, score, atr_pct, sl_pct, tp_pct, sl_price, tp_price, ' '.join(reasons)))
    except: pass

results.sort(key=lambda x: (-x[9], -x[3]))

sec_counts = {}; diversified = []
for r in results:
    sec = r[6]; sec_3d = r[7]
    max_picks = 4 if sec_3d >= 0.5 else 2
    if sec_counts.get(sec, 0) >= max_picks: continue
    sec_counts[sec] = sec_counts.get(sec, 0) + 1
    diversified.append(r)

top_picks = diversified[:3]
print(f"\n{len(results)} OVN candidates → TOP 3 | {day_name}")
print(f"{'#':>2s} {'Sym':6s} {'Close':>7s} {'Today':>6s} {'5dM':>6s} {'β':>4s} {'ATR':>5s} {'Sec':>10s} {'Sc':>3s} {'Tier':>5s} {'SL':>9s} {'TP':>9s}")
for i,(s,cl,tr,m,vr,cp,sec,sa,b,sc,atr,slp,tpp,slpr,tppr,rsn) in enumerate(top_picks, 1):
    tier = 'HIGH' if sc >= 7 else ('MED' if sc >= 5 else 'LOW')
    print(f"{i:>2d} {s:6s} {cl:>7.2f} {tr:+5.1f}% {m:+5.1f}% {b:>4.1f} {atr:>4.1f}% {sec[:10]:>10s} {sc}/9 {tier:>5s} ${slpr:.2f}({slp:+.1f}%) ${tppr:.2f}(+{tpp:.1f}%)")
    print(f"   {rsn}")
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

# === HARD GATE: AD ratio < 1 ===
br = conn.execute("SELECT ad_ratio FROM market_breadth ORDER BY date DESC LIMIT 1").fetchone()
ad_ratio = float(br[0]) if br else 1.0
if ad_ratio < 1.0:
    print(f"❌ AD ratio {ad_ratio:.2f} < 1 — WR 43% no edge. Skip Fri-Mon.")
    conn.close(); raise SystemExit

syms = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200").fetchall()]
hot = [r[0] for r in conn.execute("""
    SELECT DISTINCT d.symbol FROM stock_daily_ohlc d
    JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date = (SELECT MAX(date) FROM stock_daily_ohlc)
    AND d.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
    AND ABS(d.close - d.open) * 1.0 / d.open >= 0.05
    AND d.volume * d.close >= 20000000
""").fetchall()]
if hot: print(f"🔥 Hot inject: {len(hot)}")

news_inject = [r[0] for r in conn.execute("""
    SELECT DISTINCT n.symbol FROM news_events n
    JOIN universe_stocks u ON n.symbol = u.symbol
    WHERE n.published_at >= datetime('now','-12 hours')
    AND n.sentiment_label IN ('positive','very_positive')
    AND n.symbol NOT IN (SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200)
""").fetchall()]
if news_inject: print(f"📰 News inject: {len(news_inject)}")

syms = list(set(syms + hot + news_inject))
sectors = dict(conn.execute("SELECT symbol, sector FROM universe_stocks").fetchall())
betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
earnings_mon = set(r[0] for r in conn.execute("SELECT symbol FROM earnings_calendar WHERE next_earnings_date BETWEEN date('now','+2 day') AND date('now','+3 day')").fetchall())
news_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM news_events WHERE published_at >= datetime('now','-24 hours') AND sentiment_label IN ('positive','very_positive')").fetchall())
insider_set = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM insider_transactions WHERE transaction_date >= date('now','-30 days') AND total_value >= 100000").fetchall())
si_set = set(r[0] for r in conn.execute("SELECT symbol FROM short_interest WHERE date = (SELECT MAX(date) FROM short_interest) AND short_pct_float >= 10").fetchall())

# 3-day sector trend
sector_3d = {}
for r in conn.execute("""
    SELECT u.sector, AVG((d.close - d.open) / d.open * 100.0)
    FROM stock_daily_ohlc d JOIN universe_stocks u ON d.symbol = u.symbol
    WHERE d.date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-3 days')
    AND u.sector IS NOT NULL GROUP BY u.sector
"""): sector_3d[r[0]] = r[1] or 0

vix_row = conn.execute("SELECT vix_close FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
vix_now = float(vix_row[0]) if vix_row else 20.0
spy_rows = conn.execute("SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 2").fetchall()
spy_daily = (spy_rows[0][0]/spy_rows[1][0]-1)*100 if len(spy_rows) >= 2 else 0
spy_green = spy_daily > 0

hist = {}
for r in conn.execute("""
    SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc
    WHERE date >= date((SELECT MAX(date) FROM stock_daily_ohlc), '-7 days')
    ORDER BY symbol, date
"""): hist.setdefault(r[0], []).append(r[1:])
conn.close()

snaps = {}
for i in range(0, len(syms), 100):
    batch = ','.join(syms[i:i+100])
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/snapshots?symbols={batch}', headers=hdr)
    if r.status_code == 200: snaps.update(r.json())

print(f"AD {ad_ratio:.2f} ✅ | SPY {spy_daily:+.2f}% {'🟢' if spy_green else '🔴'} | VIX {vix_now:.1f}")

results = []
for sym in syms:
    try:
        snap = snaps.get(sym); days = hist.get(sym, [])
        if not snap or len(days) < 5: continue
        if sym in earnings_mon: continue
        db = snap.get('dailyBar',{})
        last_close = db.get('c',0); last_open = db.get('o',0)
        if last_close < 5 or last_open < 1: continue

        fri_ret = (last_close/last_open - 1)*100
        d0 = days[0]; mom5d = (last_close/d0[3]-1)*100
        avg_vol = np.mean([d[5] for d in days[:-1]]) if len(days) > 1 else 1
        vr = db.get('v',0)/avg_vol if avg_vol > 0 else 0
        hi, lo = db.get('h',last_close), db.get('l',last_close)
        rng = hi - lo; cp = (last_close-lo)/rng if rng > 0 else 0.5

        sec = sectors.get(sym, 'Unknown')
        sec_3d_avg = sector_3d.get(sec, 0)
        beta = betas.get(sym, 1.5)
        has_catalyst = sym in news_set or sym in insider_set or sym in si_set

        # Setup classification (sector gate applied to dump)
        setup = ''
        if fri_ret >= 3: setup = 'FRI_RALLY'
        elif mom5d <= -5 and fri_ret >= 2 and sec_3d_avg >= 0: setup = 'BAD_WEEK_BOUNCE'
        elif fri_ret <= -3 and vr >= 2 and sec_3d_avg >= 0: setup = 'FRI_DUMP_VOL'
        else: continue  # no setup or sector falling = skip

        # === Score /9 ===
        score = 0; reasons = [setup]
        if spy_green: score += 2; reasons.append('SPY+')
        if ad_ratio >= 2: score += 2; reasons.append(f'AD{ad_ratio:.1f}')
        score += 1; reasons.append(f'Fri{fri_ret:+.0f}%')  # setup itself
        if beta < 1.5: score += 1; reasons.append(f'β{beta:.1f}')
        if sec_3d_avg >= 0.5: score += 1; reasons.append(f'Sec+{sec_3d_avg:.1f}%')
        if vr >= 2.0: score += 1; reasons.append(f'V{vr:.1f}x')
        if has_catalyst:
            score += 1
            cat = []
            if sym in news_set: cat.append('news')
            if sym in insider_set: cat.append('insider')
            if sym in si_set: cat.append('SI')
            reasons.append('+'.join(cat))

        if cp < 0.5: continue
        if vix_now >= 30: continue
        # No min score — return top 3 always

        trs = [max(d[2]-d[3], abs(d[2]-days[i-1][4]), abs(d[3]-days[i-1][4])) for i,d in enumerate(days[1:],1)]
        atr_pct = np.mean(trs[-4:])/last_close*100 if trs else 3.0
        # Weekend hold = wider SL (gap risk both ways)
        sl_pct = -max(2.5, 0.8 * atr_pct)  # widest of all scans
        tp_pct = max(3.0, 1.0 * atr_pct)
        sl_price = last_close * (1 + sl_pct/100)
        tp_price = last_close * (1 + tp_pct/100)

        results.append((sym, last_close, fri_ret, mom5d, vr, cp, sec, sec_3d_avg, beta, setup, score, atr_pct, sl_pct, tp_pct, sl_price, tp_price, ' '.join(reasons)))
    except: pass

results.sort(key=lambda x: (-x[10], -abs(x[2])))

sec_counts = {}; diversified = []
for r in results:
    sec = r[6]; sec_3d = r[7]
    max_picks = 4 if sec_3d >= 0.5 else 2
    if sec_counts.get(sec, 0) >= max_picks: continue
    sec_counts[sec] = sec_counts.get(sec, 0) + 1
    diversified.append(r)

top_picks = diversified[:3]
print(f"\n{len(results)} Fri-Mon candidates → TOP 3 | VIX {vix_now:.1f}")
print(f"{'#':>2s} {'Sym':6s} {'Close':>7s} {'FriR':>6s} {'5dM':>6s} {'β':>4s} {'ATR':>5s} {'Sec':>10s} {'Setup':>15s} {'Sc':>3s} {'Tier':>5s} {'SL':>9s} {'TP':>9s}")
for i,(s,cl,fr,m,vr,cp,sec,sa,b,su,sc,atr,slp,tpp,slpr,tppr,rsn) in enumerate(top_picks, 1):
    tier = 'HIGH' if sc >= 7 else ('MED' if sc >= 5 else 'LOW')
    print(f"{i:>2d} {s:6s} {cl:>7.2f} {fr:+5.1f}% {m:+5.1f}% {b:>4.1f} {atr:>4.1f}% {sec[:10]:>10s} {su:>15s} {sc}/9 {tier:>5s} ${slpr:.2f}({slp:+.1f}%) ${tppr:.2f}(+{tpp:.1f}%)")
    print(f"   {rsn}")
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
