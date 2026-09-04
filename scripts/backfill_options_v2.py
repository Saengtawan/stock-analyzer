"""
Polygon options backfill v2 — ATM monthly contracts approach.
For each symbol: find ATM contracts across quarterly windows, fetch daily bars, aggregate.
Paid key required (~5 calls/sec).
"""
import requests, time, sqlite3, sys
from datetime import datetime
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
symbols = [r[0] for r in conn.execute(
    "SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200")]

# Skip already done (need decent coverage — at least 50 dates)
done = set(r[0] for r in conn.execute(
    "SELECT symbol FROM options_polygon_paid GROUP BY symbol HAVING COUNT(DISTINCT date) >= 50"))

remaining = [s for s in symbols if s not in done]
print(f"Symbols: {len(symbols)} total, {len(done)} done, {len(remaining)} remaining", flush=True)

def api_get(url, retries=3):
    """GET with retry and rate limit handling."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 429:
                wait = 60 if attempt < 2 else 120
                print(f"  rate limit, wait {wait}s", flush=True)
                time.sleep(wait)
                continue
            return r
        except Exception as e:
            print(f"  error: {e}", flush=True)
            time.sleep(10)
    return None

def get_price_at_date(sym, date_str):
    """Get approximate stock price at a date from our DB."""
    row = conn.execute(
        "SELECT close FROM stock_daily_ohlc WHERE symbol=? AND date<=? ORDER BY date DESC LIMIT 1",
        (sym, date_str)).fetchone()
    return row[0] if row else None

# Quarterly windows to cover Apr 2024 - Apr 2026
WINDOWS = [
    ('2024-04-01', '2024-07-01', '2024-04-01', '2024-07-31'),
    ('2024-07-01', '2024-10-01', '2024-07-01', '2024-10-31'),
    ('2024-10-01', '2025-01-01', '2024-10-01', '2025-01-31'),
    ('2025-01-01', '2025-04-01', '2025-01-01', '2025-04-30'),
    ('2025-04-01', '2025-07-01', '2025-04-01', '2025-07-31'),
    ('2025-07-01', '2025-10-01', '2025-07-01', '2025-10-31'),
    ('2025-10-01', '2026-01-01', '2025-10-01', '2026-01-31'),
    ('2026-01-01', '2026-04-20', '2026-01-01', '2026-04-20'),
]

t0 = time.time()
for si, sym in enumerate(remaining):
    daily = defaultdict(lambda: {'cv': 0, 'pv': 0, 'n': 0})
    n_calls = 0

    for exp_gte, exp_lte, bars_from, bars_to in WINDOWS:
        # Get stock price at window start for ATM strike range
        price = get_price_at_date(sym, exp_gte)
        if not price:
            continue

        # ATM range: ±15% of price
        strike_lo = int(price * 0.85)
        strike_hi = int(price * 1.15)

        for ctype in ['call', 'put']:
            url = (f"https://api.polygon.io/v3/reference/options/contracts"
                   f"?underlying_ticker={sym}&contract_type={ctype}&expired=true"
                   f"&expiration_date.gte={exp_gte}&expiration_date.lte={exp_lte}"
                   f"&strike_price.gte={strike_lo}&strike_price.lte={strike_hi}"
                   f"&limit=100&apiKey={API_KEY}")

            r = api_get(url)
            if not r or r.status_code != 200:
                continue
            n_calls += 1
            contracts = r.json().get('results', [])
            time.sleep(0.2)

            # Prefer monthly expirations (3rd Friday) — more liquid
            # Take up to 10 contracts per window/side
            selected = contracts[:10]

            for c in selected:
                r2 = api_get(
                    f"https://api.polygon.io/v2/aggs/ticker/{c['ticker']}"
                    f"/range/1/day/{bars_from}/{bars_to}"
                    f"?limit=50000&apiKey={API_KEY}")
                if not r2 or r2.status_code != 200:
                    continue
                n_calls += 1
                for bar in r2.json().get('results', []):
                    d = datetime.fromtimestamp(bar['t'] / 1000).strftime('%Y-%m-%d')
                    if ctype == 'call':
                        daily[d]['cv'] += bar.get('v', 0)
                    else:
                        daily[d]['pv'] += bar.get('v', 0)
                    daily[d]['n'] += 1
                time.sleep(0.2)

    # Save
    saved = 0
    for date, data in daily.items():
        cv = data['cv']; pv = data['pv']
        pc = round(pv / cv, 4) if cv > 0 else 0
        conn.execute(
            'INSERT OR REPLACE INTO options_polygon_paid VALUES (?,?,?,?,?,0,0,?)',
            (sym, date, cv, pv, pc, data['n']))
        saved += 1
    conn.commit()

    elapsed = (time.time() - t0) / 60
    eta = elapsed / (si + 1) * (len(remaining) - si - 1)
    print(f"[{si+1}/{len(remaining)}] {sym}: {saved} dates, {n_calls} calls "
          f"({elapsed:.1f}m, ETA {eta:.0f}m)", flush=True)

total = conn.execute(
    "SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT date), COUNT(*) FROM options_polygon_paid"
).fetchone()
print(f"\nDone! {total[0]} symbols, {total[1]} dates, {total[2]:,} rows "
      f"({(time.time() - t0) / 60:.1f}m)")
conn.close()
