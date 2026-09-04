"""Extend wf_1min_bars from its latest date to yesterday (Alpaca IEX 1-min = live-faithful source).
Auto-detects the gap. Run before building the faithful feature pkl so it stays current.
Usage: python scripts/extend_wf1min.py [--end YYYY-MM-DD]"""
import os, sys, requests, sqlite3, time, argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; ET = ZoneInfo('America/New_York')
for ln in (ROOT/'.env').read_text().splitlines():
    ln = ln.strip()
    if ln and not ln.startswith('#') and '=' in ln:
        k, v = ln.split('=', 1); os.environ.setdefault(k.strip(), v.strip().strip('"\''))
HDR = {'APCA-API-KEY-ID': os.getenv('ALPACA_API_KEY') or os.getenv('APCA_API_KEY_ID'),
       'APCA-API-SECRET-KEY': os.getenv('ALPACA_SECRET_KEY') or os.getenv('APCA_API_SECRET_KEY')}

def etmin(t):
    d = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(ET); return d.hour*60 + d.minute

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--end', default=None); a = ap.parse_args()
    th = sqlite3.connect(str(ROOT/'data/trade_history.db'))
    syms = [r[0] for r in th.execute("SELECT symbol FROM universe_stocks WHERE sector!='ETF' ORDER BY dollar_vol DESC LIMIT 500")]
    w = sqlite3.connect(str(ROOT/'cache/wf_1min_bars.db'))
    last = w.execute("SELECT MAX(date) FROM bars").fetchone()[0]
    end = a.end or (datetime.now(ET) - timedelta(days=1)).strftime('%Y-%m-%d')
    days = [r[0] for r in th.execute("SELECT DISTINCT date FROM intraday_bars_5m WHERE date>? AND date<=? ORDER BY date", (last, end))]
    th.close()
    print(f"extend wf_1min: last={last} -> {end} | {len(days)} new trading days, {len(syms)} syms", flush=True)
    total = 0
    for di, date in enumerate(days):
        rows = []
        for i in range(0, len(syms), 100):
            p = {'feed': 'iex', 'symbols': ','.join(syms[i:i+100]), 'timeframe': '1Min',
                 'start': f'{date}T13:30:00Z', 'end': f'{date}T20:05:00Z', 'limit': 10000}
            r = None
            for _ in range(3):
                try:
                    r = requests.get('https://data.alpaca.markets/v2/stocks/bars', headers=HDR, params=p, timeout=30)
                    if r.status_code == 200: break
                    time.sleep(2)
                except Exception: time.sleep(2)
            if not r or r.status_code != 200: continue
            for sym, bars in r.json().get('bars', {}).items():
                for x in bars:
                    em = etmin(x['t'])
                    if 570 <= em <= 959: rows.append((sym, date, em, x['o'], x['h'], x['l'], x['c']))
        w.executemany("INSERT OR IGNORE INTO bars(sym,date,em,o,h,l,c) VALUES(?,?,?,?,?,?,?)", rows)
        w.commit(); total += len(rows)
        print(f"  [{di+1}/{len(days)}] {date}: +{len(rows)} (total {total})", flush=True)
    print(f"DONE: +{total} bars, latest={w.execute('SELECT MAX(date) FROM bars').fetchone()[0]}", flush=True)
    w.close()

if __name__ == '__main__': main()
