#!/usr/bin/env python3
"""
Collect CBOE delayed options data for universe stocks.
Computes and stores: P/C volume ratio, IV skew, unusual activity flags.
Run daily via cron. No authentication needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import time
import requests
from datetime import date
from database.orm.base import get_session
from sqlalchemy import text


def ensure_table():
    with get_session() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS options_daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                collected_date TEXT NOT NULL,
                total_call_volume INTEGER,
                total_put_volume INTEGER,
                pc_volume_ratio REAL,
                total_call_oi INTEGER,
                total_put_oi INTEGER,
                pc_oi_ratio REAL,
                avg_call_iv REAL,
                avg_put_iv REAL,
                iv_skew REAL,
                unusual_call_count INTEGER,
                unusual_put_count INTEGER,
                max_call_volume INTEGER,
                max_put_volume INTEGER,
                n_contracts INTEGER,
                UNIQUE(symbol, collected_date)
            )
        """))


def fetch_cboe_options(symbol):
    """Fetch options data from CBOE delayed API."""
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
    try:
        resp = requests.get(url, timeout=15,
                            headers={'User-Agent': 'Mozilla/5.0 StockAnalyzer/1.0'})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get('data', {}).get('options', [])
    except Exception:
        return None


def compute_summary(options):
    """Compute summary metrics from raw options data."""
    if not options:
        return None

    call_vol, put_vol = 0, 0
    call_oi, put_oi = 0, 0
    call_ivs, put_ivs = [], []
    unusual_calls, unusual_puts = 0, 0
    max_call_vol, max_put_vol = 0, 0

    for opt in options:
        otype = opt.get('option', '')
        v = opt.get('volume', 0) or 0
        oi = opt.get('open_interest', 0) or 0
        iv = opt.get('iv', 0) or 0

        is_call = 'C' in otype.upper() or opt.get('option_type', '').upper() == 'CALL'
        is_put = 'P' in otype.upper() or opt.get('option_type', '').upper() == 'PUT'

        if not is_call and not is_put:
            parts = otype.split()
            if parts:
                sym_part = parts[0] if len(parts) == 1 else otype
                for ch in reversed(sym_part):
                    if ch == 'C':
                        is_call = True; break
                    elif ch == 'P':
                        is_put = True; break
                    elif ch.isdigit():
                        continue
                    else:
                        break

        if is_call:
            call_vol += v
            call_oi += oi
            if iv > 0:
                call_ivs.append(iv)
            if v > 0 and oi > 0 and v > oi * 2:
                unusual_calls += 1
            max_call_vol = max(max_call_vol, v)
        elif is_put:
            put_vol += v
            put_oi += oi
            if iv > 0:
                put_ivs.append(iv)
            if v > 0 and oi > 0 and v > oi * 2:
                unusual_puts += 1
            max_put_vol = max(max_put_vol, v)

    total_vol = call_vol + put_vol
    if total_vol == 0:
        return None

    pc_vol = put_vol / call_vol if call_vol > 0 else 999
    pc_oi = put_oi / call_oi if call_oi > 0 else 999
    avg_call_iv = sum(call_ivs) / len(call_ivs) if call_ivs else 0
    avg_put_iv = sum(put_ivs) / len(put_ivs) if put_ivs else 0
    iv_skew = avg_put_iv - avg_call_iv

    return {
        'call_vol': call_vol, 'put_vol': put_vol, 'pc_vol': round(pc_vol, 3),
        'call_oi': call_oi, 'put_oi': put_oi, 'pc_oi': round(pc_oi, 3),
        'avg_call_iv': round(avg_call_iv, 4), 'avg_put_iv': round(avg_put_iv, 4),
        'iv_skew': round(iv_skew, 4),
        'unusual_calls': unusual_calls, 'unusual_puts': unusual_puts,
        'max_call_vol': max_call_vol, 'max_put_vol': max_put_vol,
        'n_contracts': len(options),
    }


def main():
    ensure_table()
    today = date.today().isoformat()

    with get_session() as session:
        existing = session.execute(
            text("SELECT COUNT(*) FROM options_daily_summary WHERE collected_date = :d"), {'d': today}
        ).scalar()
        if existing > 50:
            print(f"Already collected {existing} stocks today.")
            return

        symbols = [r[0] for r in session.execute(
            text("SELECT symbol FROM stock_fundamentals WHERE market_cap >= 30e9 ORDER BY market_cap DESC")
        ).fetchall()]

    print(f"Collecting CBOE options for {len(symbols)} stocks (mcap>=30B)...")
    total = 0
    errors = 0
    batch = []

    for i, sym in enumerate(symbols):
        options = fetch_cboe_options(sym)
        if options is None:
            errors += 1
        else:
            summary = compute_summary(options)
            if summary:
                batch.append((sym, today, summary['call_vol'], summary['put_vol'],
                              summary['pc_vol'], summary['call_oi'], summary['put_oi'],
                              summary['pc_oi'], summary['avg_call_iv'], summary['avg_put_iv'],
                              summary['iv_skew'], summary['unusual_calls'], summary['unusual_puts'],
                              summary['max_call_vol'], summary['max_put_vol'], summary['n_contracts']))
                total += 1

        if (i + 1) % 50 == 0:
            if batch:
                with get_session() as session:
                    for row in batch:
                        session.execute(text("""
                            INSERT OR REPLACE INTO options_daily_summary
                            (symbol, collected_date, total_call_volume, total_put_volume,
                             pc_volume_ratio, total_call_oi, total_put_oi, pc_oi_ratio,
                             avg_call_iv, avg_put_iv, iv_skew,
                             unusual_call_count, unusual_put_count,
                             max_call_volume, max_put_volume, n_contracts)
                            VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15)
                        """), {f'p{j}': v for j, v in enumerate(row)})
                batch = []
            print(f"  [{i+1}/{len(symbols)}] +{total:,} collected, {errors} errors")

        time.sleep(0.5)

    if batch:
        with get_session() as session:
            for row in batch:
                session.execute(text("""
                    INSERT OR REPLACE INTO options_daily_summary
                    (symbol, collected_date, total_call_volume, total_put_volume,
                     pc_volume_ratio, total_call_oi, total_put_oi, pc_oi_ratio,
                     avg_call_iv, avg_put_iv, iv_skew,
                     unusual_call_count, unusual_put_count,
                     max_call_volume, max_put_volume, n_contracts)
                    VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15)
                """), {f'p{j}': v for j, v in enumerate(row)})

    print(f"\nDone: {total:,} stocks collected, {errors} errors")

    with get_session() as session:
        print("\nSample P/C ratios:")
        for r in session.execute(text("""
            SELECT symbol, pc_volume_ratio, iv_skew, unusual_call_count, unusual_put_count
            FROM options_daily_summary WHERE collected_date = :d
            ORDER BY pc_volume_ratio DESC LIMIT 10
        """), {'d': today}).fetchall():
            print(f"  {r[0]}: P/C={r[1]:.2f}, IV_skew={r[2]:+.4f}, unusual_C={r[3]}, unusual_P={r[4]}")


if __name__ == '__main__':
    main()
