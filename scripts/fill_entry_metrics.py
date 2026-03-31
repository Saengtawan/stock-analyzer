#!/usr/bin/env python3
"""
fill_entry_metrics.py — v7.6
==============================
Nightly fill of at-entry quality metrics for BOUGHT signals.

Fills (from yfinance 1m bars — reliable, not Alpaca snapshot which lags in paper):
  - signal_outcomes.bounce_pct_from_lod  = (entry_price - day_low) / day_low x 100
  - signal_outcomes.entry_vs_vwap_pct    = (entry_price - day_vwap) / day_vwap x 100
  - trades.bounce_pct_from_lod           = same, in trades table (v7.6: new column)

bounce_pct_from_lod answers: "how far above the day's LOW did we buy?"
  - 0% = bought exactly at LOD (perfect DIP entry)
  - 3% = bought 3% above LOD (stock already bounced before we bought)
  - negative = impossible (we can't buy below LOD)

Runs after market close (21:30 ET) so full day's 1m data is available.

Cron (TZ=America/New_York):
  30 21 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/fill_entry_metrics.py >> logs/fill_entry_metrics.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import sys
import argparse
from datetime import datetime, date, timedelta

import yfinance as yf
import pandas as pd
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def _get_1m_bars(symbol: str, target_date: str) -> pd.DataFrame | None:
    """Download 1m bars for a specific date. Returns None on failure."""
    try:
        # yfinance 'period=1d' gives today; for past dates use start/end
        start = target_date
        end_dt = datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=1)
        end = end_dt.strftime('%Y-%m-%d')

        df = yf.download(symbol, start=start, end=end, interval='1m',
                         auto_adjust=True, progress=False)
        if df is None or df.empty:
            return None
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


def _compute_metrics_from_bars(df: pd.DataFrame, entry_price: float) -> dict:
    """
    Compute bounce_pct_from_lod and entry_vs_vwap_pct from 1m bars.
    Returns dict with keys: bounce_pct_from_lod, entry_vs_vwap_pct (both may be None).
    """
    result = {'bounce_pct_from_lod': None, 'entry_vs_vwap_pct': None}
    if df is None or df.empty or entry_price is None or entry_price <= 0:
        return result

    try:
        day_low = float(df['Low'].min())
        if day_low > 0:
            result['bounce_pct_from_lod'] = round((entry_price / day_low - 1) * 100, 3)
    except Exception:
        pass

    try:
        typical = (df['High'] + df['Low'] + df['Close']) / 3
        vol = df['Volume']
        total_vol = vol.sum()
        if total_vol > 0:
            day_vwap = float((typical * vol).sum() / total_vol)
            if day_vwap > 0:
                result['entry_vs_vwap_pct'] = round((entry_price / day_vwap - 1) * 100, 3)
    except Exception:
        pass

    return result


def main():
    parser = argparse.ArgumentParser(description='Fill entry metrics from yfinance 1m data')
    parser.add_argument('--date', default=None,
                        help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1,
                        help='Number of past trading days to backfill (default: 1 = today only)')
    args = parser.parse_args()

    target_date = args.date or date.today().strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] fill_entry_metrics date={target_date} days={args.days}")

    with get_session() as session:
        # Build date range
        base_dt = datetime.strptime(target_date, '%Y-%m-%d')
        dates_to_fill = [
            (base_dt - timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range(args.days)
        ]

        total_so = 0
        total_tr = 0

        for fill_date in dates_to_fill:
            print(f"\n  --- {fill_date} ---")

            # === signal_outcomes: BOUGHT rows missing bounce_pct_from_lod ===
            so_rows = session.execute(text("""
                SELECT so.id, so.symbol, so.scan_date,
                       t.price AS entry_price, t.date AS trade_date
                FROM signal_outcomes so
                LEFT JOIN trades t ON t.symbol = so.symbol
                                   AND t.action = 'BUY'
                                   AND t.date >= date(so.scan_date, '-3 days')
                                   AND t.date <= so.scan_date
                WHERE so.scan_date = :p0
                  AND so.action_taken = 'BOUGHT'
                  AND (so.bounce_pct_from_lod IS NULL OR so.entry_vs_vwap_pct IS NULL)
                  AND so.scan_price > 0
            """), {"p0": fill_date}).fetchall()

            # === trades: BUY rows missing bounce_pct_from_lod ===
            tr_rows = session.execute(text("""
                SELECT id, symbol, date, price AS entry_price
                FROM trades
                WHERE action = 'BUY'
                  AND date = :p0
                  AND bounce_pct_from_lod IS NULL
                  AND price IS NOT NULL AND price > 0
            """), {"p0": fill_date}).fetchall()

            if not so_rows and not tr_rows:
                print(f"    Nothing to fill for {fill_date}")
                continue

            # Deduplicate (symbol, date) pairs — OVN entries use trade_date (day before scan_date)
            sym_date_pairs = set()
            for r in so_rows:
                td = r[4] if r[4] else fill_date
                sym_date_pairs.add((r[1], td))
            for r in tr_rows:
                sym_date_pairs.add((r[1], fill_date))

            print(f"    signal_outcomes BOUGHT: {len(so_rows)} | trades BUY: {len(tr_rows)} | "
                  f"unique sym/date pairs: {len(sym_date_pairs)}")

            # Fetch 1m bars keyed by (symbol, date)
            bars_cache: dict[tuple, pd.DataFrame | None] = {}
            for i, (sym, bar_date) in enumerate(sym_date_pairs):
                bars_cache[(sym, bar_date)] = _get_1m_bars(sym, bar_date)
                if (i + 1) % 10 == 0:
                    print(f"    [{i+1}/{len(sym_date_pairs)}] fetched...")

            fetched = sum(1 for v in bars_cache.values() if v is not None)
            print(f"    Fetched {fetched}/{len(sym_date_pairs)} sym/date pairs with 1m data")

            # Update signal_outcomes
            so_updated = 0
            for row in so_rows:
                sym = row[1]
                trade_date = row[4] if row[4] else fill_date
                df = bars_cache.get((sym, trade_date))
                entry_price = row[3]
                if df is None or entry_price is None:
                    continue
                metrics = _compute_metrics_from_bars(df, entry_price)
                bounce = metrics['bounce_pct_from_lod']
                vwap_pct = metrics['entry_vs_vwap_pct']
                if bounce is not None or vwap_pct is not None:
                    session.execute(text("""
                        UPDATE signal_outcomes
                        SET bounce_pct_from_lod = COALESCE(bounce_pct_from_lod, :p0),
                            entry_vs_vwap_pct   = COALESCE(entry_vs_vwap_pct, :p1)
                        WHERE id = :p2
                    """), {"p0": bounce, "p1": vwap_pct, "p2": row[0]})
                    so_updated += 1

            # Update trades
            tr_updated = 0
            for row in tr_rows:
                df = bars_cache.get((row[1], fill_date))
                if df is None:
                    continue
                metrics = _compute_metrics_from_bars(df, row[3])
                bounce = metrics['bounce_pct_from_lod']
                if bounce is not None:
                    session.execute(text("""
                        UPDATE trades SET bounce_pct_from_lod = :p0
                        WHERE id = :p1
                    """), {"p0": bounce, "p1": row[0]})
                    tr_updated += 1
            print(f"    Updated: signal_outcomes={so_updated} trades={tr_updated}")
            total_so += so_updated
            total_tr += tr_updated
    print(f"\n  Total updated: signal_outcomes={total_so} trades={total_tr}")
    print(f"  Done.")


if __name__ == '__main__':
    main()
