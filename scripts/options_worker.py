"""Options backfill worker — 1 key, N symbols."""
import requests, time, sqlite3, sys
from datetime import datetime
from collections import defaultdict

API_KEY = sys.argv[1]
SYMBOLS = sys.argv[2].split(',')
WORKER = sys.argv[3]
DB = 'data/trade_history.db'

def api(url):
    r = requests.get(f"{url}&apiKey={API_KEY}" if '?' in url else f"{url}?apiKey={API_KEY}", timeout=30)
    if r.status_code == 429:
        print(f"W{WORKER} rate limit, sleep 30s", flush=True)
        time.sleep(30)
        return api(url)
    time.sleep(12)
    return r

conn = sqlite3.connect(DB)
conn.execute("""CREATE TABLE IF NOT EXISTS options_polygon_history (
    symbol TEXT NOT NULL, date TEXT NOT NULL,
    call_volume INTEGER DEFAULT 0, put_volume INTEGER DEFAULT 0,
    put_call_ratio REAL, call_oi INTEGER DEFAULT 0, put_oi INTEGER DEFAULT 0,
    n_contracts INTEGER DEFAULT 0, PRIMARY KEY (symbol, date))""")

for si, sym in enumerate(SYMBOLS):
    existing = conn.execute("SELECT COUNT(*) FROM options_polygon_history WHERE symbol=?", (sym,)).fetchone()[0]
    if existing > 10:
        print(f"W{WORKER} [{si+1}/{len(SYMBOLS)}] {sym}: skip ({existing} exists)", flush=True)
        continue
    daily = defaultdict(lambda: {'cv':0,'pv':0,'n':0})
    for ctype in ['call','put']:
        for exp in ['2025-01-01','2025-07-01','2026-01-01']:
            r = api(f"https://api.polygon.io/v3/reference/options/contracts?underlying_ticker={sym}&contract_type={ctype}&expired=true&expiration_date.gte={exp}&limit=20")
            for c in r.json().get('results',[])[:7]:
                bars = api(f"https://api.polygon.io/v2/aggs/ticker/{c['ticker']}/range/1/day/2024-04-01/2026-04-16?limit=50000").json().get('results',[])
                for bar in bars:
                    d = datetime.fromtimestamp(bar['t']/1000).strftime('%Y-%m-%d')
                    if ctype=='call': daily[d]['cv']+=bar.get('v',0)
                    else: daily[d]['pv']+=bar.get('v',0)
                    daily[d]['n']+=1
    for date, data in daily.items():
        cv=data['cv'];pv=data['pv']
        conn.execute('INSERT OR REPLACE INTO options_polygon_history VALUES (?,?,?,?,?,0,0,?)',
                     (sym,date,cv,pv,round(pv/cv,4) if cv>0 else 0,data['n']))
    conn.commit()
    print(f"W{WORKER} [{si+1}/{len(SYMBOLS)}] {sym}: {len(daily)} days", flush=True)
conn.close()
print(f"W{WORKER} DONE", flush=True)
