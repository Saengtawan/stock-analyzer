#!/usr/bin/env python3
"""
sector_momentum_scan.py — v7.5
================================
Capture top movers per sector at 10:05 ET (after first 30 min of trading).

For each sector ETF moving >= 1.5% from prior close:
  -> Find top 10 individual stocks in that sector (by |pct_from_open| x volume)
  -> Save to sector_movers table for future Sector Catalyst Momentum strategy analysis

Also captures movers for ETFs that are DOWN >= 1.5% (for short-side analysis).

Cron (TZ=America/New_York):
  5 10 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/sector_momentum_scan.py >> logs/sector_momentum_scan.log 2>&1

Data flow:
  sector_movers -> analysis for Sector Catalyst Momentum strategy (future)
  Enables: "which sector stocks move most when ETF is up/down >= 1.5% at 10:00 ET?"
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import time
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

ET = ZoneInfo('America/New_York')

# Sector ETF -> yfinance sector name (matches sector_cache.sector)
SECTOR_ETF_MAP = {
    'XLK':  'Technology',
    'XLV':  'Healthcare',
    'XLI':  'Industrials',
    'XLE':  'Energy',
    'XLF':  'Financial Services',
    'XLB':  'Basic Materials',
    'XLRE': 'Real Estate',
    'XLU':  'Utilities',
    'XLP':  'Consumer Defensive',
    'XLY':  'Consumer Cyclical',
    'XLC':  'Communication Services',
}

HOT_SECTOR_THRESHOLD = 1.5   # % — sector ETF must move >= this to qualify
TOP_N_PER_SECTOR     = 10    # top N stocks to capture per hot sector
MIN_PRICE            = 5.0   # exclude penny stocks
MIN_AVG_VOLUME       = 200_000  # 20d avg volume filter


def _get_etf_pct_change(etf_symbols: list[str]) -> dict[str, dict]:
    """
    Download sector ETF 2-day daily bars -> compute today's % change from yesterday's close.
    Returns {etf: {pct_chg, today_price, prev_close}}
    """
    result = {}
    try:
        df = yf.download(etf_symbols, period='5d', interval='1d',
                         auto_adjust=True, progress=False)
        if df.empty:
            return result

        today = date.today()

        for etf in etf_symbols:
            try:
                if len(etf_symbols) == 1:
                    sym_df = df
                else:
                    sym_df = df[etf]

                sym_df = sym_df.dropna(how='all')
                if len(sym_df) < 2:
                    continue

                # Filter to today and prior trading day
                sym_df.index = pd.to_datetime(sym_df.index)
                today_rows = sym_df[sym_df.index.date == today]
                prior_rows = sym_df[sym_df.index.date < today]

                if today_rows.empty or prior_rows.empty:
                    continue

                today_close = float(today_rows['Close'].iloc[-1])
                prev_close  = float(prior_rows['Close'].iloc[-1])

                if prev_close <= 0:
                    continue

                pct_chg = round((today_close / prev_close - 1) * 100, 3)
                result[etf] = {
                    'pct_chg':    pct_chg,
                    'today_price': round(today_close, 4),
                    'prev_close': round(prev_close, 4),
                }
            except Exception:
                continue
    except Exception as e:
        print(f"  ETF download error: {e}")

    return result


def _get_sector_symbols(session, sector_name: str,
                        min_price: float = MIN_PRICE,
                        min_avg_vol: float = MIN_AVG_VOLUME) -> list[str]:
    """
    Get symbols for a sector from sector_cache (yfinance sector names).
    Filter by dollar_vol (proxy for avg volume x price).
    """
    rows = session.execute(text("""
        SELECT sc.symbol
        FROM sector_cache sc
        JOIN universe_stocks us ON sc.symbol = us.symbol
        WHERE sc.sector = :p0
          AND us.dollar_vol >= :p1
        ORDER BY us.dollar_vol DESC
        LIMIT 100
    """), {'p0': sector_name, 'p1': min_price * min_avg_vol}).fetchall()
    return [r[0] for r in rows]


def _fetch_movers(symbols: list[str]) -> dict[str, dict]:
    """
    Download today's 1-min bars for symbols -> compute pct_from_open + volume_ratio.
    Returns {symbol: {price, open_price, pct_from_open, volume, high, low}}
    """
    if not symbols:
        return {}

    result = {}
    # Batch in chunks of 50 to avoid yfinance limits
    for i in range(0, len(symbols), 50):
        chunk = symbols[i:i+50]
        try:
            df = yf.download(chunk, period='1d', interval='1m',
                             auto_adjust=True, progress=False, group_by='ticker')
            if df.empty:
                continue

            for sym in chunk:
                try:
                    if len(chunk) == 1:
                        sym_df = df
                    else:
                        sym_df = df[sym]

                    sym_df = sym_df.dropna(how='all')
                    if sym_df.empty:
                        continue

                    last  = sym_df.iloc[-1]
                    open_ = float(sym_df.iloc[0]['Open'])
                    close = float(last['Close'])
                    vol   = int(sym_df['Volume'].sum())
                    high  = float(sym_df['High'].max())
                    low   = float(sym_df['Low'].min())

                    if open_ <= 0 or close < MIN_PRICE:
                        continue

                    pct_from_open = round((close / open_ - 1) * 100, 3)

                    result[sym] = {
                        'price':        round(close, 4),
                        'open_price':   round(open_, 4),
                        'pct_from_open': pct_from_open,
                        'volume':       vol,
                        'high':         round(high, 4),
                        'low':          round(low, 4),
                    }
                except Exception:
                    continue

        except Exception as e:
            print(f"  Chunk {i//50+1} error: {e}")
        time.sleep(0.1)

    return result


def _get_avg_volumes(symbols: list[str]) -> dict[str, float]:
    """Get 20-day average volume from yfinance daily bars."""
    result = {}
    try:
        df = yf.download(symbols, period='25d', interval='1d',
                         auto_adjust=True, progress=False, group_by='ticker')
        if df.empty:
            return result

        for sym in symbols:
            try:
                if len(symbols) == 1:
                    sym_df = df
                else:
                    sym_df = df[sym]
                sym_df = sym_df.dropna(how='all')
                if sym_df.empty:
                    continue
                avg_vol = float(sym_df['Volume'].tail(20).mean())
                result[sym] = round(avg_vol, 0)
            except Exception:
                continue
    except Exception:
        pass
    return result


def main():
    now_et   = datetime.now(ET)
    today    = now_et.date().strftime('%Y-%m-%d')
    time_str = now_et.strftime('%H:%M')

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] sector_momentum_scan date={today} time_et={time_str}")

    with get_session() as session:

        etf_symbols = list(SECTOR_ETF_MAP.keys())

        # 1. Get sector ETF % change from yesterday's close
        print(f"  Fetching {len(etf_symbols)} sector ETFs...")
        etf_data = _get_etf_pct_change(etf_symbols)

        # 2. Identify hot sectors
        hot_sectors = {
            etf: data for etf, data in etf_data.items()
            if abs(data['pct_chg']) >= HOT_SECTOR_THRESHOLD
        }
        print(f"  Hot sectors (|pct| >= {HOT_SECTOR_THRESHOLD}%): {len(hot_sectors)}")

        # Always save ETF summary (even if no hot sectors — useful for "what was flat" analysis)
        for etf, data in etf_data.items():
            tag = '+' if etf in hot_sectors else ' '
            print(f"  {tag} {etf}: {data['pct_chg']:+.2f}%")

        if not hot_sectors:
            # Still save ETF-level rows with NULL symbol fields for the record
            for etf, data in etf_data.items():
                sector_name = SECTOR_ETF_MAP.get(etf, '')
                session.execute(text("""
                    INSERT OR IGNORE INTO sector_movers
                        (date, time_et, sector_etf, sector_name, etf_pct_chg, etf_price,
                         symbol, price, open_price, pct_from_open, pct_from_close,
                         volume, avg_volume_20d, volume_ratio, rank_in_sector)
                    VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14)
                """), {
                    'p0': today, 'p1': time_str, 'p2': etf, 'p3': sector_name,
                    'p4': data['pct_chg'], 'p5': data['today_price'],
                    'p6': None, 'p7': None, 'p8': None, 'p9': None, 'p10': None,
                    'p11': None, 'p12': None, 'p13': None, 'p14': 0,
                })
            print(f"  No hot sectors today — saved {len(etf_data)} ETF summary rows")
            return

        total_saved = 0

        for etf, etf_info in hot_sectors.items():
            sector_name = SECTOR_ETF_MAP[etf]
            pct_chg     = etf_info['pct_chg']

            # Get sector constituents from sector_cache
            syms = _get_sector_symbols(session, sector_name)
            if not syms:
                print(f"  {etf} ({sector_name}): no symbols in sector_cache")
                continue
            print(f"  {etf} ({sector_name}) {pct_chg:+.2f}%: scanning {len(syms)} stocks...")

            # Fetch intraday movers
            movers = _fetch_movers(syms)
            if not movers:
                print(f"    No price data returned")
                continue

            # Get 20d avg volumes for volume_ratio
            avg_vols = _get_avg_volumes(list(movers.keys()))

            # Rank by |pct_from_open| (momentum) weighted by whether direction matches ETF
            def mover_score(sym_data: dict) -> float:
                pct = sym_data['pct_from_open']
                # Boost if stock moving same direction as sector ETF
                direction_match = 1.2 if (pct > 0) == (pct_chg > 0) else 0.8
                return abs(pct) * direction_match

            ranked = sorted(movers.items(), key=lambda x: mover_score(x[1]), reverse=True)

            for rank, (sym, data) in enumerate(ranked[:TOP_N_PER_SECTOR], start=1):
                avg_vol = avg_vols.get(sym)
                vol_ratio = round(data['volume'] / avg_vol, 2) if avg_vol and avg_vol > 0 else None

                session.execute(text("""
                    INSERT OR IGNORE INTO sector_movers
                        (date, time_et, sector_etf, sector_name, etf_pct_chg, etf_price,
                         symbol, price, open_price, pct_from_open, pct_from_close,
                         volume, avg_volume_20d, volume_ratio, rank_in_sector)
                    VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14)
                """), {
                    'p0': today, 'p1': time_str,
                    'p2': etf, 'p3': sector_name, 'p4': pct_chg, 'p5': etf_info['today_price'],
                    'p6': sym, 'p7': data['price'], 'p8': data['open_price'], 'p9': data['pct_from_open'],
                    'p10': None,  # pct_from_close — would need prior daily bar; skip for speed
                    'p11': data['volume'], 'p12': avg_vol, 'p13': vol_ratio, 'p14': rank,
                })
            total_saved += min(len(ranked), TOP_N_PER_SECTOR)

            # Show top 5
            for rank, (sym, data) in enumerate(ranked[:5], start=1):
                print(f"    #{rank} {sym}: {data['pct_from_open']:+.2f}% open={data['open_price']:.2f} price={data['price']:.2f}")

        # Also save ETF-level summary for non-hot sectors (for full picture)
        for etf, data in etf_data.items():
            if etf in hot_sectors:
                continue
            sector_name = SECTOR_ETF_MAP.get(etf, '')
            session.execute(text("""
                INSERT OR IGNORE INTO sector_movers
                    (date, time_et, sector_etf, sector_name, etf_pct_chg, etf_price,
                     symbol, price, open_price, pct_from_open, pct_from_close,
                     volume, avg_volume_20d, volume_ratio, rank_in_sector)
                VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14)
            """), {
                'p0': today, 'p1': time_str, 'p2': etf, 'p3': sector_name,
                'p4': data['pct_chg'], 'p5': data['today_price'],
                'p6': None, 'p7': None, 'p8': None, 'p9': None, 'p10': None,
                'p11': None, 'p12': None, 'p13': None, 'p14': 0,
            })
        print(f"  Done. Saved {total_saved} stock movers across {len(hot_sectors)} hot sectors")


if __name__ == '__main__':
    main()
