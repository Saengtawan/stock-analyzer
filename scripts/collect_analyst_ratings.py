#!/usr/bin/env python3
"""
collect_analyst_ratings.py — v7.8
=====================================
Collect analyst upgrades/downgrades, consensus ratings, and price targets.
All data sourced from yfinance — completely free.

Tables filled:
  analyst_ratings    — every upgrade/downgrade event per symbol
  analyst_consensus  — current buy/hold/sell counts + price target stats

Analysis enabled:
  - "Did analyst upgrade within 5 days before DIP entry → better outcome?"
  - "Stocks with bull_score > 1.5 (mostly Buy/Strong Buy) → higher win rate?"
  - "Stock at 30% below analyst mean target → better DIP bounce candidate?"
  - "Multiple downgrades in last 30 days → avoid DIP (falling knife)"
  - "Initiation of coverage (action=init) as catalyst confirmation"

Coverage:
  Daily: today's signal_outcomes + screener_rejections (candidates evaluated today)
  Weekly (Sunday): full universe top 500 for consensus refresh

Cron (TZ=America/New_York):
  45 16 * * 1-5  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_analyst_ratings.py >> logs/collect_analyst_ratings.log 2>&1
  30 8 * * 0     cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/collect_analyst_ratings.py --full >> logs/collect_analyst_ratings.log 2>&1
"""
import os
import sqlite3
import time
import argparse
from datetime import datetime, date, timedelta

import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
ET = ZoneInfo('America/New_York')

DELAY_EVERY = 20
DELAY_SECS = 0.4
UPGRADE_LOOKBACK_DAYS = 90  # store last 90 days of upgrades/downgrades


def get_target_symbols(conn: sqlite3.Connection, today: str, full: bool) -> list[str]:
    """Get symbols to collect for."""
    if full:
        return [r[0] for r in conn.execute(
            "SELECT symbol FROM universe_stocks WHERE status='active' ORDER BY dollar_vol DESC LIMIT 500"
        ).fetchall()]

    syms = set()
    # Today's signal_outcomes
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM signal_outcomes WHERE scan_date = ?", (today,)
    ).fetchall()
    syms.update(r[0] for r in rows)
    # Today's screener_rejections
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM screener_rejections WHERE scan_date = ?", (today,)
    ).fetchall()
    syms.update(r[0] for r in rows)
    # Last 10 days BOUGHT (for open position context)
    cutoff = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=10)).strftime('%Y-%m-%d')
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM signal_outcomes WHERE scan_date >= ? AND action_taken='BOUGHT'",
        (cutoff,)
    ).fetchall()
    syms.update(r[0] for r in rows)
    return sorted(syms)


def fetch_analyst_data(sym: str) -> dict:
    """Fetch upgrades/downgrades, consensus, and price targets from yfinance."""
    result = {'ratings': [], 'consensus': None, 'targets': None, 'last_price': None}
    try:
        t = yf.Ticker(sym)

        # --- Upgrades/Downgrades ---
        ud = t.upgrades_downgrades
        if ud is not None and not ud.empty:
            cutoff_dt = datetime.now() - timedelta(days=UPGRADE_LOOKBACK_DAYS)
            for idx, row in ud.iterrows():
                try:
                    grade_dt = pd.Timestamp(idx)
                    if grade_dt.tzinfo:
                        grade_dt = grade_dt.tz_localize(None)
                    if grade_dt < cutoff_dt:
                        continue
                    result['ratings'].append({
                        'date':          grade_dt.strftime('%Y-%m-%d'),
                        'firm':          str(row.get('Firm', '') or ''),
                        'to_grade':      str(row.get('ToGrade', '') or ''),
                        'from_grade':    str(row.get('FromGrade', '') or ''),
                        'action':        str(row.get('Action', '') or '').lower(),
                        'price_target':  _safe_float(row.get('currentPriceTarget')),
                        'prior_target':  _safe_float(row.get('priorPriceTarget')),
                    })
                except Exception:
                    continue

        # --- Recommendations summary (current month) ---
        rec = t.recommendations_summary
        if rec is not None and not rec.empty:
            cur = rec[rec['period'] == '0m']
            if not cur.empty:
                r = cur.iloc[0]
                sb   = int(r.get('strongBuy', 0) or 0)
                b    = int(r.get('buy', 0) or 0)
                h    = int(r.get('hold', 0) or 0)
                s    = int(r.get('sell', 0) or 0)
                ss   = int(r.get('strongSell', 0) or 0)
                total = sb + b + h + s + ss
                bull_score = round((sb * 2 + b) / total, 3) if total > 0 else None
                result['consensus'] = {
                    'strong_buy': sb, 'buy': b, 'hold': h,
                    'sell': s, 'strong_sell': ss,
                    'total_analysts': total,
                    'bull_score': bull_score,
                }

        # --- Price targets ---
        pt = t.analyst_price_targets
        if pt and isinstance(pt, dict):
            result['targets'] = {
                'mean':   _safe_float(pt.get('mean')),
                'high':   _safe_float(pt.get('high')),
                'low':    _safe_float(pt.get('low')),
                'median': _safe_float(pt.get('median')),
            }
            # Last price for upside calc
            info = t.fast_info
            result['last_price'] = _safe_float(getattr(info, 'last_price', None))

    except Exception:
        pass
    return result


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return round(f, 4) if f == f else None  # NaN check
    except Exception:
        return None


def save_analyst_data(conn: sqlite3.Connection, sym: str, data: dict, today: str):
    """Persist analyst data to DB."""
    # --- analyst_ratings ---
    for r in data['ratings']:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO analyst_ratings
                    (symbol, date, firm, to_grade, from_grade, action, price_target, prior_target)
                VALUES (?,?,?,?,?,?,?,?)
            """, (sym, r['date'], r['firm'][:100], r['to_grade'][:50],
                  r['from_grade'][:50], r['action'][:20],
                  r['price_target'], r['prior_target']))
        except Exception:
            pass

    # --- analyst_consensus ---
    cons = data['consensus']
    targets = data['targets']
    if cons or targets:
        upside_pct = None
        if targets and targets.get('mean') and data.get('last_price') and data['last_price'] > 0:
            upside_pct = round((targets['mean'] / data['last_price'] - 1) * 100, 2)

        conn.execute("""
            INSERT INTO analyst_consensus
                (symbol, updated_at,
                 strong_buy, buy, hold, sell, strong_sell, total_analysts, bull_score,
                 target_mean, target_high, target_low, target_median, upside_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                updated_at     = excluded.updated_at,
                strong_buy     = COALESCE(excluded.strong_buy, strong_buy),
                buy            = COALESCE(excluded.buy, buy),
                hold           = COALESCE(excluded.hold, hold),
                sell           = COALESCE(excluded.sell, sell),
                strong_sell    = COALESCE(excluded.strong_sell, strong_sell),
                total_analysts = COALESCE(excluded.total_analysts, total_analysts),
                bull_score     = COALESCE(excluded.bull_score, bull_score),
                target_mean    = COALESCE(excluded.target_mean, target_mean),
                target_high    = COALESCE(excluded.target_high, target_high),
                target_low     = COALESCE(excluded.target_low, target_low),
                target_median  = COALESCE(excluded.target_median, target_median),
                upside_pct     = COALESCE(excluded.upside_pct, upside_pct)
        """, (sym, today,
              cons.get('strong_buy') if cons else None,
              cons.get('buy') if cons else None,
              cons.get('hold') if cons else None,
              cons.get('sell') if cons else None,
              cons.get('strong_sell') if cons else None,
              cons.get('total_analysts') if cons else None,
              cons.get('bull_score') if cons else None,
              targets.get('mean') if targets else None,
              targets.get('high') if targets else None,
              targets.get('low') if targets else None,
              targets.get('median') if targets else None,
              upside_pct))


def main():
    parser = argparse.ArgumentParser(description='Collect analyst ratings and consensus')
    parser.add_argument('--date', default=None, help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--full', action='store_true',
                        help='Full universe top-500 refresh (weekly Sunday run)')
    parser.add_argument('--symbol', default=None, help='Single symbol (for testing)')
    args = parser.parse_args()

    today = args.date or datetime.now(ET).date().strftime('%Y-%m-%d')
    mode = 'full' if args.full else 'daily'
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] collect_analyst_ratings "
          f"date={today} mode={mode}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = get_target_symbols(conn, today, args.full)

    print(f"  {len(symbols)} symbols")

    ok = fail = 0
    for i, sym in enumerate(symbols):
        data = fetch_analyst_data(sym)
        if data['ratings'] or data['consensus'] or data['targets']:
            save_analyst_data(conn, sym, data, today)
            ok += 1
        else:
            fail += 1

        if (i + 1) % 100 == 0:
            conn.commit()
            pct = round((i + 1) / len(symbols) * 100)
            print(f"  [{i+1}/{len(symbols)} {pct}%] ok={ok} fail={fail}")

        if (i + 1) % DELAY_EVERY == 0:
            time.sleep(DELAY_SECS)

    conn.commit()
    conn.close()
    print(f"\n  Done. ok={ok} fail={fail}")


if __name__ == '__main__':
    main()
