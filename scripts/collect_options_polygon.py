"""
Daily options data collector using Polygon.io snapshot endpoint.
Collects total call/put volume + OI for all universe symbols.
Run once per day after market close. ~2 min for 200 symbols.

Usage: python3 scripts/collect_options_polygon.py [API_KEY]
Cron:  35 4 * * 2-6 cd /path && python3 scripts/collect_options_polygon.py
"""
import requests, time, sqlite3, sys
from datetime import datetime

API_KEY = sys.argv[1] if len(sys.argv) > 1 else 'AmAlwvIxff90cBG1yHUT8DFBE6m5d4Nj'
DB = 'data/trade_history.db'

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS options_polygon_daily (
    symbol TEXT NOT NULL, date TEXT NOT NULL,
    call_volume INTEGER DEFAULT 0, put_volume INTEGER DEFAULT 0,
    put_call_ratio REAL, call_oi INTEGER DEFAULT 0, put_oi INTEGER DEFAULT 0,
    n_contracts INTEGER DEFAULT 0,
    avg_call_iv REAL, avg_put_iv REAL,
    PRIMARY KEY (symbol, date))""")
conn.commit()

today = datetime.now().strftime('%Y-%m-%d')

# Check if already collected today
existing = conn.execute(
    "SELECT COUNT(*) FROM options_polygon_daily WHERE date=?", (today,)
).fetchone()[0]
if existing > 50:
    print(f"Already collected {existing} symbols for {today}, skipping")
    conn.close()
    sys.exit(0)

# Get universe
symbols = [r[0] for r in conn.execute(
    "SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200")]
print(f"Collecting options snapshots for {len(symbols)} symbols ({today})", flush=True)

t0 = time.time()
saved = 0
errors = 0

for si, sym in enumerate(symbols):
    try:
        r = requests.get(
            f"https://api.polygon.io/v3/snapshot/options/{sym}"
            f"?limit=250&apiKey={API_KEY}", timeout=15)

        if r.status_code == 429:
            print(f"  rate limit at {sym}, wait 60s", flush=True)
            time.sleep(60)
            r = requests.get(
                f"https://api.polygon.io/v3/snapshot/options/{sym}"
                f"?limit=250&apiKey={API_KEY}", timeout=15)

        if r.status_code != 200:
            errors += 1
            time.sleep(0.2)
            continue

        results = r.json().get('results', [])

        # Aggregate across all contracts (first 250 — covers most volume)
        call_vol = 0; put_vol = 0
        call_oi = 0; put_oi = 0
        n = len(results)

        for opt in results:
            details = opt.get('details', {})
            day = opt.get('day', {})
            oi = opt.get('open_interest', 0) or 0
            vol = day.get('volume', 0) or 0

            if details.get('contract_type') == 'call':
                call_vol += vol
                call_oi += oi
            elif details.get('contract_type') == 'put':
                put_vol += vol
                put_oi += oi

        pc = round(put_vol / call_vol, 4) if call_vol > 0 else None

        conn.execute(
            "INSERT OR REPLACE INTO options_polygon_daily VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sym, today, call_vol, put_vol, pc, call_oi, put_oi, n, None, None))
        saved += 1
        time.sleep(0.2)

        if (si + 1) % 25 == 0:
            conn.commit()
            elapsed = time.time() - t0
            print(f"  [{si+1}/{len(symbols)}] {saved} saved, {errors} errors "
                  f"({elapsed:.0f}s)", flush=True)

    except Exception as e:
        print(f"  error {sym}: {e}", flush=True)
        errors += 1
        time.sleep(1)

conn.commit()
total = conn.execute(
    "SELECT COUNT(*) FROM options_polygon_daily WHERE date=?", (today,)
).fetchone()[0]
elapsed = time.time() - t0
print(f"\nDone! {total} symbols saved for {today} "
      f"({errors} errors, {elapsed:.0f}s)", flush=True)

# Sample
for r in conn.execute("""
    SELECT symbol, call_volume, put_volume, put_call_ratio, call_oi, put_oi
    FROM options_polygon_daily WHERE date=? ORDER BY call_volume DESC LIMIT 5
""", (today,)):
    print(f"  {r[0]}: call={r[1]:,} put={r[2]:,} PC={r[3]:.3f} OI(c/p)={r[4]:,}/{r[5]:,}")

conn.close()
