#!/usr/bin/env python3
"""
collect_institutional_holdings.py — v7.8
==========================================
Collect institutional and insider ownership data from yfinance (free).
Source: SEC 13F filings, parsed and served via Yahoo Finance.

Tables filled:
  institutional_holdings  — top 10 institutions per symbol (quarterly)
  major_holders_summary   — insider%, institution%, float institution%

Analysis enabled:
  - "High institution_pct (>70%) → stable support → DIP safer to buy?"
  - "Vanguard/Blackrock increased position recently → institutional accumulation?"
  - "Low insider_pct → insiders already sold → weaker conviction signal"
  - "pct_change > 0 (institution buying more) → confirms DIP entry"
  - "Very low institution_count (<50) → illiquid, avoid DIP strategy"

Note: 13F data has 45-day lag (reported 45 days after quarter end).
Data reflects Q4 2025 filings (reported by Feb 14, 2026).

Cron (TZ=America/New_York):
  0 9 * * 0  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_institutional_holdings.py >> logs/collect_institutional_holdings.log 2>&1
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import os
import time
import argparse
from datetime import datetime

import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

DELAY_EVERY = 20
DELAY_SECS = 0.4
DEFAULT_TOP_N = 500


def fetch_holdings(sym: str) -> dict:
    """Fetch institutional_holders and major_holders from yfinance."""
    result = {'holders': [], 'major': None}
    try:
        t = yf.Ticker(sym)

        # --- Institutional holders (top 10) ---
        ih = t.institutional_holders
        if ih is not None and not ih.empty:
            for _, row in ih.iterrows():
                try:
                    report_date = None
                    rd = row.get('Date Reported') or row.get('dateReported')
                    if rd is not None:
                        report_date = pd.Timestamp(rd).strftime('%Y-%m-%d')

                    holder = str(row.get('Holder', '') or '')
                    if not holder:
                        continue

                    result['holders'].append({
                        'report_date': report_date,
                        'institution': holder[:200],
                        'pct_held':    _safe_float(row.get('pctHeld') or row.get('% Out')),
                        'shares':      _safe_int(row.get('Shares')),
                        'value':       _safe_int(row.get('Value')),
                        'pct_change':  _safe_float(row.get('pctChange') or row.get('% Change')),
                    })
                except Exception:
                    continue

        # --- Major holders summary ---
        mh = t.major_holders
        if mh is not None and not mh.empty:
            major = {}
            # yfinance returns a DataFrame with index = label, value column
            mh_dict = {}
            for idx, row in mh.iterrows():
                key = str(idx).strip().lower()
                # Try to get value from 'Value' column or first column
                val = None
                for col in row.index:
                    try:
                        val = float(row[col])
                        break
                    except Exception:
                        continue
                mh_dict[key] = val

            # Keys vary by yfinance version — try multiple
            major = {
                'insider_pct':           mh_dict.get('insiderspercentheld') or
                                         mh_dict.get('% of shares held by all insider'),
                'institution_pct':       mh_dict.get('institutionspercentheld') or
                                         mh_dict.get('% of shares held by institutions'),
                'float_institution_pct': mh_dict.get('institutionsfloatpercentheld') or
                                         mh_dict.get('% of float held by institutions'),
                'institution_count':     _safe_int(mh_dict.get('institutionscount') or
                                                   mh_dict.get('number of institutions holding shares')),
            }
            # Multiply pct fields (yfinance returns 0.69 = 69%)
            for key in ('insider_pct', 'institution_pct', 'float_institution_pct'):
                v = major.get(key)
                if v is not None and v <= 1.0:
                    major[key] = round(v * 100, 2)
                elif v is not None:
                    major[key] = round(v, 2)
            result['major'] = major

    except Exception:
        pass
    return result


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return round(f, 4) if f == f else None
    except Exception:
        return None


def _safe_int(v) -> int | None:
    try:
        return int(float(v))
    except Exception:
        return None


def save_holdings(conn: object, sym: str, data: dict):
    """Persist holdings to DB."""
    # --- institutional_holdings ---
    for h in data['holders']:
        if not h['institution']:
            continue
        # Use today as fallback if report_date missing
        report_date = h['report_date'] or datetime.now().strftime('%Y-%m-%d')
        try:
            conn.execute("""
                INSERT OR IGNORE INTO institutional_holdings
                    (symbol, report_date, institution, pct_held, shares, value, pct_change)
                VALUES (?,?,?,?,?,?,?)
            """, (sym, report_date, h['institution'],
                  h['pct_held'], h['shares'], h['value'], h['pct_change']))
        except Exception:
            pass

    # --- major_holders_summary ---
    major = data.get('major')
    if major:
        conn.execute("""
            INSERT INTO major_holders_summary
                (symbol, insider_pct, institution_pct,
                 float_institution_pct, institution_count)
            VALUES (?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                insider_pct           = COALESCE(excluded.insider_pct, insider_pct),
                institution_pct       = COALESCE(excluded.institution_pct, institution_pct),
                float_institution_pct = COALESCE(excluded.float_institution_pct, float_institution_pct),
                institution_count     = COALESCE(excluded.institution_count, institution_count),
                updated_at            = datetime('now')
        """, (sym,
              major.get('insider_pct'), major.get('institution_pct'),
              major.get('float_institution_pct'), major.get('institution_count')))


def main():
    parser = argparse.ArgumentParser(description='Collect institutional holdings data')
    parser.add_argument('--top', type=int, default=DEFAULT_TOP_N,
                        help=f'Top N symbols by dollar volume (default: {DEFAULT_TOP_N})')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch all (ignore 7-day freshness)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_institutional_holdings "
          f"top={args.top} force={args.force}")

    # conn via get_session()

    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = [r[0] for r in conn.execute(
            "SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC LIMIT ?",
            (args.top,)
        ).fetchall()]

        if not args.force:
            fresh = set(r[0] for r in conn.execute("""
                SELECT symbol FROM major_holders_summary
                WHERE updated_at >= datetime('now', '-7 days')
            """).fetchall())
            symbols = [s for s in symbols if s not in fresh]
            print(f"  {len(symbols)} stale symbols (skipping {len(fresh)} fresh)")
        else:
            print(f"  {len(symbols)} symbols (force mode)")

    if not symbols:
        print("  All fresh — done.")
        return

    ok = fail = 0
    for i, sym in enumerate(symbols):
        data = fetch_holdings(sym)
        if data['holders'] or data['major']:
            save_holdings(conn, sym, data)
            ok += 1
        else:
            fail += 1

        if (i + 1) % 100 == 0:
            pct = round((i + 1) / len(symbols) * 100)
            print(f"  [{i+1}/{len(symbols)} {pct}%] ok={ok} fail={fail}")

        if (i + 1) % DELAY_EVERY == 0:
            time.sleep(DELAY_SECS)
    print(f"\n  Done. ok={ok} fail={fail}")


if __name__ == '__main__':
    main()
