#!/usr/bin/env python3
"""
backfill_intraday_5m.py — Backfill 5-minute intraday bars from Alpaca API.

Usage:
  python3 scripts/backfill_intraday_5m.py              # full backfill
  python3 scripts/backfill_intraday_5m.py --recent 7    # last 7 days only
  python3 scripts/backfill_intraday_5m.py --symbol NVDA  # single symbol
"""
import argparse, os, sys, time, requests
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text

# Load Alpaca keys from .env
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


def ensure_table():
    with get_session() as session:
        session.execute(text('''CREATE TABLE IF NOT EXISTS intraday_bars_5m (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL,
            time_et TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume INTEGER, vwap REAL, n_trades INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, timestamp)
        )'''))
        session.execute(text('CREATE INDEX IF NOT EXISTS idx_intraday_5m_sym_date ON intraday_bars_5m(symbol, date)'))
        session.execute(text('CREATE INDEX IF NOT EXISTS idx_intraday_5m_date ON intraday_bars_5m(date)'))


def fetch_bars(symbol, start_date, end_date):
    """Fetch all 5-min bars for symbol between dates. Handles pagination."""
    all_bars = []
    page_token = None
    retries = 0

    while True:
        params = {
            'timeframe': '5Min',
            'start': f'{start_date}T09:30:00Z',
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
                print(f'    Rate limited — waiting 60s')
                time.sleep(60)
                retries += 1
                if retries > 3:
                    break
                continue
            if r.status_code != 200:
                break

            data = r.json()
            bars = data.get('bars', [])
            if not bars:
                break

            all_bars.extend(bars)
            page_token = data.get('next_page_token')
            if not page_token:
                break

            time.sleep(0.15)
            retries = 0

        except Exception as e:
            print(f'    {symbol} error: {e}')
            retries += 1
            if retries > 3:
                break
            time.sleep(5)

    return all_bars


def insert_bars(session, symbol, bars):
    """Insert bars into DB, skip duplicates."""
    n = 0
    for bar in bars:
        ts = bar['t']
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        et = dt - timedelta(hours=4)
        date_str = et.strftime('%Y-%m-%d')
        time_str = et.strftime('%H:%M')

        try:
            session.execute(text('''INSERT OR IGNORE INTO intraday_bars_5m
                (symbol, timestamp, date, time_et, open, high, low, close, volume, vwap, n_trades)
                VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10)'''),
                {'p0': symbol, 'p1': ts, 'p2': date_str, 'p3': time_str,
                 'p4': bar['o'], 'p5': bar['h'], 'p6': bar['l'], 'p7': bar['c'],
                 'p8': bar['v'], 'p9': bar.get('vw'), 'p10': bar.get('n')})
            n += 1
        except:
            pass
    return n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recent', type=int, default=0, help='Only last N days')
    parser.add_argument('--symbol', type=str, default='', help='Single symbol')
    parser.add_argument('--min-volume', type=int, default=500_000, help='Min avg volume')
    parser.add_argument('--min-mcap', type=float, default=1e9, help='Min market cap')
    args = parser.parse_args()

    ensure_table()

    # Determine symbols
    with get_session() as session:
        if args.symbol:
            symbols = [args.symbol.upper()]
        else:
            symbols = [r[0] for r in session.execute(text(
                'SELECT symbol FROM stock_fundamentals WHERE avg_volume > :v AND market_cap > :m ORDER BY avg_volume DESC'
            ), {'v': args.min_volume, 'm': args.min_mcap}).fetchall()]

    # Determine date range
    if args.recent > 0:
        start = (date.today() - timedelta(days=args.recent)).isoformat()
    else:
        start = '2023-06-01'
    end = date.today().isoformat()

    print(f'Backfill intraday 5m: {len(symbols)} symbols, {start} to {end}')

    total_bars = 0
    total_new = 0

    for si, sym in enumerate(symbols):
        # Check existing data
        with get_session() as session:
            existing = session.execute(text(
                'SELECT MAX(date) FROM intraday_bars_5m WHERE symbol=:s'
            ), {'s': sym}).fetchone()[0]

        sym_start = start
        if existing and not args.recent:
            if existing >= (date.today() - timedelta(days=3)).isoformat():
                continue
            sym_start = existing

        # Fetch month by month
        current = datetime.strptime(sym_start, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end, '%Y-%m-%d').date()
        sym_bars = 0

        while current < end_dt:
            month_end = min(current + timedelta(days=30), end_dt)
            bars = fetch_bars(sym, current.isoformat(), month_end.isoformat())
            if bars:
                with get_session() as session:
                    n = insert_bars(session, sym, bars)
                    sym_bars += n
            current = month_end

        if sym_bars > 0:
            total_bars += sym_bars
            total_new += 1

        if (si + 1) % 20 == 0 or si == len(symbols) - 1:
            with get_session() as session:
                db_total = session.execute(text('SELECT COUNT(*) FROM intraday_bars_5m')).fetchone()[0]
            print(f'  [{si+1}/{len(symbols)}] {sym:6s} +{sym_bars:>6,} bars | '
                  f'Total: {db_total:>10,} bars, {total_new} new symbols')

    # Final stats
    with get_session() as session:
        final = session.execute(text('''
            SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(date), MAX(date)
            FROM intraday_bars_5m
        ''')).fetchone()
    print(f'\n=== BACKFILL COMPLETE ===')
    print(f'Total bars: {final[0]:,}')
    print(f'Symbols: {final[1]}')
    print(f'Date range: {final[2]} to {final[3]}')


if __name__ == '__main__':
    main()
