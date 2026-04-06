#!/usr/bin/env python3
"""
collect_intraday_5m_daily.py — Daily 5-min bar collection for universe stocks.

Runs after market close to collect today's 5-min bars into intraday_bars_5m.
Reuses Alpaca API logic from backfill_intraday_5m.py.

Cron (TZ=America/New_York):
  20 17 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_intraday_5m_daily.py >> logs/collect_intraday_5m_daily.log 2>&1
"""
import sys, os, time, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from database.orm.base import get_session
from sqlalchemy import text

ET = ZoneInfo('America/New_York')

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Load Alpaca keys
_DIR = os.path.dirname(os.path.abspath(__file__))
_env = {}
try:
    for line in open(os.path.join(_DIR, '..', '.env')):
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            _env[k.strip()] = v.strip()
except:
    pass

HEADERS = {
    'APCA-API-KEY-ID': _env.get('ALPACA_API_KEY', ''),
    'APCA-API-SECRET-KEY': _env.get('ALPACA_SECRET_KEY', ''),
}
BARS_URL = 'https://data.alpaca.markets/v2/stocks/{}/bars'


def fetch_bars(symbol, start_date, end_date):
    all_bars = []
    page_token = None
    retries = 0
    while True:
        params = {
            'timeframe': '5Min',
            'start': f'{start_date}T04:00:00Z',
            'end': f'{end_date}T21:00:00Z',
            'limit': 10000,
            'adjustment': 'all',
        }
        if page_token:
            params['page_token'] = page_token
        try:
            r = requests.get(BARS_URL.format(symbol), params=params,
                             headers=HEADERS, timeout=30)
            if r.status_code == 429:
                time.sleep(60)
                retries += 1
                if retries > 3: break
                continue
            if r.status_code != 200: break
            data = r.json()
            bars = data.get('bars', [])
            if not bars: break
            all_bars.extend(bars)
            page_token = data.get('next_page_token')
            if not page_token: break
            time.sleep(0.15)
            retries = 0
        except Exception as e:
            retries += 1
            if retries > 3: break
            time.sleep(5)
    return all_bars


def main():
    now = datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] collect_intraday_5m_daily")

    # Ensure table
    with get_session() as session:
        session.execute(text('''CREATE TABLE IF NOT EXISTS intraday_bars_5m (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, timestamp TEXT NOT NULL,
            date TEXT NOT NULL, time_et TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER, vwap REAL, n_trades INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, timestamp)
        )'''))

    # Get universe
    with get_session() as session:
        symbols = [r[0] for r in session.execute(
            text("SELECT symbol FROM universe_stocks")).fetchall()]

    print(f"  Universe: {len(symbols)} symbols")

    # Use ET date (not Bangkok) to avoid requesting future dates from Alpaca
    today_et = datetime.now(ET).date()
    end_date = today_et.strftime('%Y-%m-%d')
    start_date = (today_et - timedelta(days=2)).strftime('%Y-%m-%d')

    # Check what's already in DB for today (ET date)
    with get_session() as session:
        existing = session.execute(text(
            "SELECT DISTINCT symbol FROM intraday_bars_5m WHERE date = :d"
        ), {'d': end_date}).fetchall()
        existing_syms = {r[0] for r in existing}

    todo = [s for s in symbols if s not in existing_syms]
    print(f"  Already have: {len(existing_syms)}, need: {len(todo)}")

    if not todo:
        print("  All symbols collected — done.")
        return

    total_saved = 0
    for i, symbol in enumerate(todo):
        try:
            bars = fetch_bars(symbol, start_date, end_date)
            if not bars:
                continue

            with get_session() as session:
                saved = 0
                for b in bars:
                    ts = b.get('t', '')
                    if not ts: continue
                    # Convert to ET (handles EDT/EST automatically)
                    try:
                        utc_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        et_dt = utc_dt.astimezone(ET)
                        dt = et_dt.strftime('%Y-%m-%d')
                        time_et = et_dt.strftime('%H:%M')
                    except Exception:
                        dt = ts[:10]
                        time_et = ts[11:16]

                    session.execute(text('''
                        INSERT OR IGNORE INTO intraday_bars_5m
                        (symbol, timestamp, date, time_et, open, high, low, close, volume, vwap, n_trades)
                        VALUES (:sym, :ts, :dt, :te, :o, :h, :l, :c, :v, :vw, :n)
                    '''), {
                        'sym': symbol, 'ts': ts, 'dt': dt, 'te': time_et,
                        'o': b.get('o', 0), 'h': b.get('h', 0),
                        'l': b.get('l', 0), 'c': b.get('c', 0),
                        'v': b.get('v', 0), 'vw': b.get('vw', 0),
                        'n': b.get('n', 0),
                    })
                    saved += 1
                total_saved += saved

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{len(todo)}] +{total_saved} bars")

            time.sleep(0.15)

        except Exception as e:
            print(f"  Error {symbol}: {e}")
            continue

    print(f"  Done: {total_saved} bars for {start_date}→{end_date}")


if __name__ == '__main__':
    main()
