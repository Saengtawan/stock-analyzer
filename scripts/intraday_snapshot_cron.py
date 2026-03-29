#!/usr/bin/env python3
"""
intraday_snapshot_cron.py — v7.8
==================================
Every 5 minutes during US market hours, capture price snapshots for:
  1. Today's signal_outcomes candidates (all action_taken types)
  2. Today's screener_rejections (stocks rejected before engine — Dimension 3)
  3. Market universe: SPY, VIX (^VIX), 11 sector ETFs

Enables counterfactual analysis: "where was the SKIPPED_FILTER/SCREENER_REJECT stock 30/60/90 min after scan?"

New columns (v7.8):
  vs_spy_rs     = stock_pct_from_open - spy_pct_from_open  (relative strength vs market)
  sector_etf_pct = sector ETF % change from open at snapshot time

Cron (TZ=America/New_York in crontab — auto-handles EDT/EST DST):
  */5 9,10,11,12,13,14,15,16 * * 1-5  cd /path && python3 scripts/intraday_snapshot_cron.py >> logs/intraday_snapshot.log 2>&1

(Script exits immediately if outside US market hours 9:28-16:02 ET)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import sys
import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd

LOG_DIR  = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Market universe always captured
UNIVERSE_SYMBOLS = [
    'SPY', '^VIX',
    'XLK', 'XLV', 'XLI', 'XLE', 'XLF',
    'XLB', 'XLRE', 'XLU', 'XLP', 'XLY', 'XLC',
]

# Sector name → ETF ticker mapping
SECTOR_TO_ETF = {
    'technology':             'XLK',
    'healthcare':             'XLV',
    'industrials':            'XLI',
    'energy':                 'XLE',
    'financial services':     'XLF',
    'financials':             'XLF',
    'basic materials':        'XLB',
    'materials':              'XLB',
    'real estate':            'XLRE',
    'utilities':              'XLU',
    'consumer defensive':     'XLP',
    'consumer staples':       'XLP',
    'consumer cyclical':      'XLY',
    'consumer discretionary': 'XLY',
    'communication services': 'XLC',
}

ET_ZONE = ZoneInfo('America/New_York')


def get_et_now() -> datetime:
    return datetime.now(ET_ZONE)


def is_market_open(now_et: datetime) -> bool:
    """Return True if within regular US market hours (9:30–16:00 ET) on a weekday."""
    if now_et.weekday() >= 5:   # Saturday/Sunday
        return False
    t = now_et.time()
    return time(9, 28) <= t <= time(16, 2)


def get_sector_map(conn: object, symbols: list[str]) -> dict[str, str]:
    """Return {symbol: sector_lower} from sector_cache for given symbols."""
    if not symbols:
        return {}
    placeholders = ','.join(f':p{i}' for i in range(len(symbols)))
    params = {f'p{i}': s for i, s in enumerate(symbols)}
    rows = conn.execute(
        text(f"SELECT symbol, sector FROM sector_cache WHERE symbol IN ({placeholders})"),
        params
    ).fetchall()
    return {r[0]: (r[1] or '').lower() for r in rows}


def get_today_candidates(conn: object, today: str) -> list[dict]:
    """Fetch today's signal_outcomes rows (all action_taken types)."""
    rows = conn.execute(text("""
        SELECT symbol, signal_source, action_taken, scan_price
        FROM signal_outcomes
        WHERE scan_date = :today
          AND scan_price > 0
        GROUP BY symbol
    """), {'today': today}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_today_screener_rejections(conn: object, today: str) -> list[dict]:
    """
    v7.6: Fetch today's screener_rejections — stocks rejected BEFORE engine.
    Returns deduplicated list (one row per symbol, first occurrence by scan_time).
    action_taken = 'SCREENER_REJECT' to distinguish from signal_outcomes candidates.
    """
    rows = conn.execute(text("""
        SELECT symbol, screener AS signal_source, scan_price,
               MIN(scan_time) AS first_scan_time
        FROM screener_rejections
        WHERE scan_date = :today
          AND scan_price IS NOT NULL AND scan_price > 0
        GROUP BY symbol
    """), {'today': today}).fetchall()
    return [
        {
            'symbol':        r[0],
            'signal_source': r[1],
            'action_taken':  'SCREENER_REJECT',
            'scan_price':    r[2],
        }
        for r in rows
    ]


def fetch_prices(symbols: list[str]) -> dict[str, dict]:
    """
    Fetch latest 1-min bar for each symbol via yfinance.
    Returns {symbol: {price, volume, open, high, low, vwap}}
    """
    if not symbols:
        return {}

    # Deduplicate
    syms = list(set(symbols))
    result = {}

    try:
        # Batch download — last 5 minutes of 1m bars
        df = yf.download(syms, period='1d', interval='1m',
                         auto_adjust=True, progress=False,
                         group_by='ticker')

        if df.empty:
            return {}

        # Single symbol: columns are flat
        if len(syms) == 1:
            sym = syms[0]
            if df.empty:
                return {}
            last = df.iloc[-1]
            # Compute VWAP from today's bars (typical_price × volume / sum_volume)
            vwap = _compute_vwap(df)
            result[sym] = {
                'price':  round(float(last['Close']), 4),
                'volume': int(last['Volume']),
                'open':   round(float(df.iloc[0]['Open']), 4),
                'high':   round(float(df['High'].max()), 4),
                'low':    round(float(df['Low'].min()), 4),
                'vwap':   round(vwap, 4) if vwap else None,
            }
        else:
            for sym in syms:
                try:
                    sym_df = df[sym].dropna(how='all')
                    if sym_df.empty:
                        continue
                    last = sym_df.iloc[-1]
                    vwap = _compute_vwap(sym_df)
                    result[sym] = {
                        'price':  round(float(last['Close']), 4),
                        'volume': int(last['Volume']),
                        'open':   round(float(sym_df.iloc[0]['Open']), 4),
                        'high':   round(float(sym_df['High'].max()), 4),
                        'low':    round(float(sym_df['Low'].min()), 4),
                        'vwap':   round(vwap, 4) if vwap else None,
                    }
                except Exception:
                    continue
    except Exception as e:
        print(f"  fetch_prices error: {e}")

    return result


def _compute_vwap(df: pd.DataFrame) -> float | None:
    """Compute VWAP from a 1m OHLCV dataframe."""
    try:
        typical = (df['High'] + df['Low'] + df['Close']) / 3
        vol = df['Volume']
        total_vol = vol.sum()
        if total_vol <= 0:
            return None
        return float((typical * vol).sum() / total_vol)
    except Exception:
        return None


def insert_snapshots(conn: object, rows: list[dict]):
    """Bulk insert snapshot rows."""
    if not rows:
        return
    stmt = text("""
        INSERT INTO intraday_snapshots
            (date, time_et, symbol, price, volume, vwap, open_price, high, low,
             signal_source, action_taken, scan_price, pct_from_scan,
             spy_price, vix_at_time, unrealized_pnl_pct, pct_to_sl,
             vs_spy_rs, sector_etf_pct,
             created_at)
        VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15,:p16,:p17,:p18, datetime('now'))
    """)
    for r in rows:
        conn.execute(stmt, {
            'p0': r['date'], 'p1': r['time_et'], 'p2': r['symbol'],
            'p3': r['price'], 'p4': r['volume'], 'p5': r['vwap'],
            'p6': r['open'], 'p7': r['high'], 'p8': r['low'],
            'p9': r.get('signal_source'), 'p10': r.get('action_taken'),
            'p11': r.get('scan_price'), 'p12': r.get('pct_from_scan'),
            'p13': r.get('spy_price'), 'p14': r.get('vix_at_time'),
            'p15': r.get('unrealized_pnl_pct'), 'p16': r.get('pct_to_sl'),
            'p17': r.get('vs_spy_rs'), 'p18': r.get('sector_etf_pct'),
        })


def main():
    now_et = get_et_now()

    if not is_market_open(now_et):
        # Silent exit outside market hours — cron fires every 5 min, guard here
        sys.exit(0)

    today_et  = now_et.date().strftime('%Y-%m-%d')
    time_et   = now_et.strftime('%H:%M')

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] intraday_snapshot_cron ET={now_et.strftime('%H:%M')} date={today_et}")

    with get_session() as conn:

        # 1. Today's candidates from signal_outcomes + screener_rejections
        candidates  = get_today_candidates(conn, today_et)
        sr_rejects  = get_today_screener_rejections(conn, today_et)

        # Merge: signal_outcomes takes priority over screener_rejections for same symbol
        cand_meta_so = {c['symbol']: c for c in candidates}
        for r in sr_rejects:
            if r['symbol'] not in cand_meta_so:
                candidates.append(r)

        cand_syms = [c['symbol'] for c in candidates]

        # 2. Combined symbol list (candidates + universe)
        all_syms = list(set(cand_syms + UNIVERSE_SYMBOLS))

        # 3. Fetch prices
        prices = fetch_prices(all_syms)

        if not prices:
            print(f"  No price data returned — yfinance issue or pre-market?")
            return

        # 4. Build candidate lookup
        cand_meta: dict[str, dict] = {c['symbol']: c for c in candidates}

        # 4b. Extract SPY price and VIX for context columns
        spy_price_now = prices.get('SPY', {}).get('price')
        vix_now       = prices.get('^VIX', {}).get('price')
        spy_open_now  = prices.get('SPY', {}).get('open')

        # SPY % from open (for relative strength computation)
        spy_pct_from_open = None
        if spy_open_now and spy_open_now > 0 and spy_price_now:
            spy_pct_from_open = (spy_price_now / spy_open_now - 1) * 100

        # Precompute sector ETF % from open for all 11 ETFs
        etf_pct_from_open: dict[str, float] = {}
        for etf in ['XLK', 'XLV', 'XLI', 'XLE', 'XLF', 'XLB', 'XLRE', 'XLU', 'XLP', 'XLY', 'XLC']:
            px_etf = prices.get(etf, {})
            etf_open = px_etf.get('open')
            etf_price = px_etf.get('price')
            if etf_open and etf_open > 0 and etf_price:
                etf_pct_from_open[etf] = (etf_price / etf_open - 1) * 100

        # 4c. Load sector map for candidates (not universe ETFs)
        cand_syms_only = [s for s in cand_syms if s not in UNIVERSE_SYMBOLS]
        sector_map = get_sector_map(conn, cand_syms_only) if cand_syms_only else {}

        # 4d. Load active positions for unrealized_pnl + pct_to_sl
        active_pos: dict[str, dict] = {}
        try:
            rows_pos = conn.execute(
                text("SELECT symbol, entry_price, stop_loss FROM active_positions")
            ).fetchall()
            for p in rows_pos:
                active_pos[p[0]] = {'entry_price': p[1], 'stop_loss': p[2]}
        except Exception:
            pass

        # 5. Assemble rows
        rows_to_insert = []

        for sym, px in prices.items():
            scan_price = cand_meta.get(sym, {}).get('scan_price')
            pct_from_scan = None
            if scan_price and scan_price > 0 and px['price']:
                pct_from_scan = round((px['price'] / scan_price - 1) * 100, 3)

            # Unrealized P&L and distance to SL (only for held positions)
            unrealized_pnl_pct = None
            pct_to_sl = None
            if sym in active_pos and px['price']:
                ep = active_pos[sym]['entry_price']
                sl = active_pos[sym]['stop_loss']
                if ep and ep > 0:
                    unrealized_pnl_pct = round((px['price'] / ep - 1) * 100, 3)
                if sl and sl > 0 and px['price'] > 0:
                    pct_to_sl = round((px['price'] / sl - 1) * 100, 3)

            # vs_spy_rs: stock's % from open minus SPY's % from open
            vs_spy_rs = None
            sym_open = px.get('open')
            sym_price = px.get('price')
            if sym_open and sym_open > 0 and sym_price and spy_pct_from_open is not None:
                stock_pct = (sym_price / sym_open - 1) * 100
                vs_spy_rs = round(stock_pct - spy_pct_from_open, 3)

            # sector_etf_pct: sector ETF % from open at snapshot time
            sector_etf_pct = None
            sec_lower = sector_map.get(sym, '')
            if sec_lower:
                etf_ticker = SECTOR_TO_ETF.get(sec_lower)
                if etf_ticker:
                    sector_etf_pct = round(etf_pct_from_open.get(etf_ticker, None) or 0, 3) or None

            rows_to_insert.append({
                'date':               today_et,
                'time_et':            time_et,
                'symbol':             sym,
                'price':              sym_price,
                'volume':             px['volume'],
                'vwap':               px['vwap'],
                'open':               sym_open,
                'high':               px['high'],
                'low':                px['low'],
                'signal_source':      cand_meta.get(sym, {}).get('signal_source', 'UNIVERSE'),
                'action_taken':       cand_meta.get(sym, {}).get('action_taken', 'UNIVERSE'),
                'scan_price':         scan_price,
                'pct_from_scan':      pct_from_scan,
                'spy_price':          spy_price_now,
                'vix_at_time':        vix_now,
                'unrealized_pnl_pct': unrealized_pnl_pct,
                'pct_to_sl':          pct_to_sl,
                'vs_spy_rs':          vs_spy_rs,
                'sector_etf_pct':     sector_etf_pct,
            })

        insert_snapshots(conn, rows_to_insert)

        n_so = len([c for c in candidates if c.get('action_taken') != 'SCREENER_REJECT'])
        n_sr = len([c for c in candidates if c.get('action_taken') == 'SCREENER_REJECT'])
        print(f"  Inserted {len(rows_to_insert)} snapshots "
              f"({n_so} signal_outcomes + {n_sr} screener_rejects + {len(UNIVERSE_SYMBOLS)} universe)")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
