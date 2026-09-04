"""Fast paid backfill: 10 most active contracts per side × 200 symbols. ~40 min."""
import requests, time, sqlite3, sys
from datetime import datetime
from collections import defaultdict

API_KEY = sys.argv[1] if len(sys.argv)>1 else 'AmAlwvIxff90cBG1yHUT8DFBE6m5d4Nj'
DB = 'data/trade_history.db'

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS options_polygon_paid (
    symbol TEXT NOT NULL, date TEXT NOT NULL,
    call_volume INTEGER DEFAULT 0, put_volume INTEGER DEFAULT 0,
    put_call_ratio REAL, call_oi INTEGER DEFAULT 0, put_oi INTEGER DEFAULT 0,
    n_contracts INTEGER DEFAULT 0, PRIMARY KEY (symbol, date))""")

symbols = [r[0] for r in conn.execute("SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT 200")]
# Skip already done
done = set(r[0] for r in conn.execute("SELECT DISTINCT symbol FROM options_polygon_paid WHERE n_contracts > 5"))

remaining = [s for s in symbols if s not in done]
print(f"Symbols: {len(symbols)} total, {len(done)} done, {len(remaining)} remaining", flush=True)

t0 = time.time()
for si, sym in enumerate(remaining):
    daily = defaultdict(lambda: {'cv':0,'pv':0,'n':0})
    n_calls = 0

    for ctype in ['call','put']:
        # Get 10 contracts per expiry range (covers 2 years)
        for exp in ['2025-01-01','2025-06-01','2025-12-01','2026-03-01']:
            r = requests.get(
                f"https://api.polygon.io/v3/reference/options/contracts"
                f"?underlying_ticker={sym}&contract_type={ctype}"
                f"&expired=true&expiration_date.gte={exp}&limit=10"
                f"&sort=open_interest&order=desc"
                f"&apiKey={API_KEY}", timeout=30)
            n_calls += 1
            contracts = r.json().get('results',[])
            time.sleep(0.3)

            for c in contracts[:5]:  # top 5 by OI per range
                r2 = requests.get(
                    f"https://api.polygon.io/v2/aggs/ticker/{c['ticker']}"
                    f"/range/1/day/2024-04-01/2026-04-16?limit=50000"
                    f"&apiKey={API_KEY}", timeout=30)
                n_calls += 1
                for bar in r2.json().get('results',[]):
                    d = datetime.fromtimestamp(bar['t']/1000).strftime('%Y-%m-%d')
                    if ctype=='call': daily[d]['cv']+=bar.get('v',0)
                    else: daily[d]['pv']+=bar.get('v',0)
                    daily[d]['n']+=1
                time.sleep(0.3)

    saved = 0
    for date, data in daily.items():
        cv=data['cv'];pv=data['pv']
        conn.execute('INSERT OR REPLACE INTO options_polygon_paid VALUES (?,?,?,?,?,0,0,?)',
                     (sym,date,cv,pv,round(pv/cv,4) if cv>0 else 0,data['n']))
        saved += 1
    conn.commit()

    elapsed=(time.time()-t0)/60
    eta=elapsed/(si+1)*(len(remaining)-si-1)
    print(f"[{si+1}/{len(remaining)}] {sym}: {saved} days, {n_calls} calls ({elapsed:.1f}m, ETA {eta:.0f}m)", flush=True)

total=conn.execute("SELECT COUNT(DISTINCT symbol), COUNT(DISTINCT date), COUNT(*) FROM options_polygon_paid").fetchone()
print(f"\nDone! {total[0]} symbols, {total[1]} dates, {total[2]:,} rows ({(time.time()-t0)/60:.1f}m)")
conn.close()
