"""
Fast options backfill with paid Polygon Starter key.
Uses snapshot endpoint for current + grouped daily for historical.
~30 min for 200 symbols × 2 years.
"""
import requests, time, sqlite3
import sys
from datetime import datetime, timedelta
from collections import defaultdict

API_KEY = sys.argv[1] if len(sys.argv) > 1 else 'AmAlwvIxff90cBG1yHUT8DFBE6m5d4Nj'
DB = 'data/trade_history.db'

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS options_polygon_paid (
    symbol TEXT NOT NULL, date TEXT NOT NULL,
    call_volume INTEGER DEFAULT 0, put_volume INTEGER DEFAULT 0,
    put_call_ratio REAL, call_oi INTEGER DEFAULT 0, put_oi INTEGER DEFAULT 0,
    n_contracts INTEGER DEFAULT 0, PRIMARY KEY (symbol, date))""")
conn.commit()

# Get universe
symbols = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200")]
print(f"Backfill {len(symbols)} symbols with paid key", flush=True)

# Strategy: use grouped daily endpoint (1 call = ALL options for ALL symbols for 1 date)
# Much faster than per-symbol approach!
t0 = time.time()

# Generate trading dates (weekdays) for last 2 years
from datetime import date
start = date(2024, 4, 1)
end = date(2026, 4, 16)
dates = []
d = start
while d <= end:
    if d.weekday() < 5:  # Mon-Fri
        dates.append(d.strftime('%Y-%m-%d'))
    d += timedelta(days=1)
print(f"Dates to fetch: {len(dates)} ({dates[0]} → {dates[-1]})", flush=True)

sym_set = set(symbols)
total_saved = 0
errors = 0

for di, date_str in enumerate(dates):
    try:
        r = requests.get(
            f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/options/{date_str}?apiKey={API_KEY}",
            timeout=30)

        if r.status_code != 200:
            if r.status_code == 429:
                print(f"  rate limit at {date_str}, sleep 60s", flush=True)
                time.sleep(60)
                continue
            errors += 1
            continue

        results = r.json().get('results', [])

        # Aggregate by underlying symbol
        daily = defaultdict(lambda: {'cv': 0, 'pv': 0, 'coi': 0, 'poi': 0, 'n': 0})

        for opt in results:
            ticker = opt.get('T', '')
            # Parse: O:SNDK260417C00900000 → underlying=SNDK, type=C(all)/P(ut)
            if not ticker.startswith('O:'): continue
            rest = ticker[2:]

            # Find underlying by matching against our universe
            underlying = None
            for sym in sym_set:
                if rest.startswith(sym):
                    remaining = rest[len(sym):]
                    if remaining and remaining[0].isdigit():
                        underlying = sym
                        # Determine call/put from the character after date (6 digits)
                        if len(remaining) > 6:
                            cp_char = remaining[6]
                        else:
                            cp_char = '?'
                        break

            if not underlying: continue

            vol = opt.get('v', 0) or 0
            # Note: grouped endpoint doesn't have OI

            if cp_char == 'C':
                daily[underlying]['cv'] += vol
            elif cp_char == 'P':
                daily[underlying]['pv'] += vol
            daily[underlying]['n'] += 1

        # Save
        saved = 0
        for sym, data in daily.items():
            cv = data['cv']; pv = data['pv']
            pc = pv / cv if cv > 0 else 0
            conn.execute(
                "INSERT OR REPLACE INTO options_polygon_paid VALUES (?,?,?,?,?,?,?,?)",
                (sym, date_str, cv, pv, round(pc, 4), data['coi'], data['poi'], data['n']))
            saved += 1
        conn.commit()
        total_saved += saved

        if (di + 1) % 20 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (di + 1) * (len(dates) - di - 1) / 60
            print(f"  [{di+1}/{len(dates)}] {date_str}: {saved} symbols, total={total_saved:,} ({elapsed/60:.1f}m, ETA {eta:.0f}m)", flush=True)

        time.sleep(0.5)  # gentle rate limit

    except Exception as e:
        print(f"  error {date_str}: {e}", flush=True)
        errors += 1
        time.sleep(5)

# Summary
total = conn.execute("SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT date), COUNT(*) FROM options_polygon_paid").fetchone()
print(f"\nDone! {total[0]} symbols, {total[1]} dates, {total[2]:,} rows")
print(f"Errors: {errors}")
print(f"Time: {(time.time()-t0)/60:.1f} min")

# Sample
print(f"\nSNDK sample:")
for r in conn.execute("SELECT date, call_volume, put_volume, put_call_ratio FROM options_polygon_paid WHERE symbol='SNDK' ORDER BY date DESC LIMIT 5"):
    print(f"  {r[0]}: call={r[1]:,} put={r[2]:,} PC={r[3]:.2f}")

conn.close()
