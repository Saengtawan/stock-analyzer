#!/usr/bin/env python3
"""Fill outcome data for Discovery picks.

For each pick where outcome columns are NULL and enough trading days have passed,
download price data and compute:
- outcome_1d..5d: % change from scan_price to close on D+1..D+5
- outcome_max_gain_5d: max intraday gain within 5 days
- outcome_max_dd_5d: max intraday drawdown within 5 days

Cron: 0 6 * * 2-6 (06:00 ET Tue-Sat, after market data settles)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import sys
import os
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/fill_discovery_outcomes.log'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger('fill_discovery_outcomes')

DB_PATH = 'data/trade_history.db'


def get_trading_days_after(scan_date: str, n: int) -> list[str]:
    """Get n trading days after scan_date (approximate: skip weekends)."""
    from datetime import date
    d = datetime.strptime(scan_date, '%Y-%m-%d').date()
    days = []
    current = d
    while len(days) < n:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            days.append(current)
    return days


def fill_outcomes():
    """Fill outcome columns for picks with enough elapsed trading days."""
    import yfinance as yf
    import pandas as pd

    # conn via get_session()

    # Find picks needing outcomes (outcome_5d IS NULL and scan_date old enough)
    today = datetime.now().date()
    rows = conn.execute("""
        SELECT id, symbol, scan_date, scan_price
        FROM discovery_picks
        WHERE outcome_1d IS NULL
        ORDER BY scan_date ASC
    """).fetchall()

    if not rows:
        logger.info("No picks need outcome filling")
        return

    logger.info(f"Found {len(rows)} picks needing outcomes")

    # Group by symbol for batch download
    symbols = list(set(r['symbol'] for r in rows))
    min_date = min(r['scan_date'] for r in rows)
    start_date = (datetime.strptime(min_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    logger.info(f"Downloading data for {len(symbols)} symbols from {start_date}")
    data = yf.download(' '.join(symbols), start=start_date, interval='1d',
                        auto_adjust=True, progress=False, threads=False)

    if data.empty:
        logger.error("No data downloaded")
        return

    filled = 0
    for row in rows:
        sym = row['symbol']
        scan_date = row['scan_date']
        scan_price = row['scan_price']
        pick_id = row['id']

        try:
            # Extract this symbol's data
            if len(symbols) == 1:
                df = data
            else:
                if sym not in data.columns.get_level_values(1):
                    continue
                df = data.xs(sym, axis=1, level=1)

            if df is None or df.empty:
                continue

            # Get closes after scan_date
            scan_dt = datetime.strptime(scan_date, '%Y-%m-%d')
            future = df[df.index > pd.Timestamp(scan_dt)]

            if len(future) < 1:
                continue  # Not enough data yet

            # Compute outcomes for available days
            outcomes = {}
            for day_n in [1, 2, 3, 5]:
                if len(future) >= day_n:
                    close_n = float(future['Close'].iloc[day_n - 1])
                    outcomes[f'outcome_{day_n}d'] = round((close_n / scan_price - 1) * 100, 4)

            # Max gain and DD within 5 days (using highs/lows)
            if len(future) >= 1:
                n_days = min(5, len(future))
                future_slice = future.iloc[:n_days]

                # Max gain from any intraday high
                max_high = float(future_slice['High'].max())
                outcomes['outcome_max_gain_5d'] = round((max_high / scan_price - 1) * 100, 4)

                # Max drawdown from any intraday low
                min_low = float(future_slice['Low'].min())
                outcomes['outcome_max_dd_5d'] = round((min_low / scan_price - 1) * 100, 4)

            if not outcomes:
                continue

            # Build UPDATE query
            set_parts = []
            values = []
            for col, val in outcomes.items():
                set_parts.append(f'{col} = ?')
                values.append(val)
            values.append(pick_id)

            conn.execute(f"""
                UPDATE discovery_picks SET {', '.join(set_parts)}, updated_at = datetime('now')
                WHERE id = ?
            """, values)
            filled += 1

            if filled % 10 == 0:
                print(f'  Filled {filled}...')

        except Exception as e:
            logger.error(f"Error filling {sym} {scan_date}: {e}")
            continue
    logger.info(f"Filled outcomes for {filled}/{len(rows)} picks")


def fill_benchmarks():
    """Fill benchmark returns (XLU, XLE, SPY) for each scan_date — answers 'is L2 better than sector beta?'"""
    import yfinance as yf
    import pandas as pd

    # conn via get_session()

    # Ensure benchmark columns exist
    for col in ['benchmark_xlu_5d', 'benchmark_xle_5d', 'benchmark_spy_5d']:
        try:
            conn.execute(f"ALTER TABLE discovery_picks ADD COLUMN {col} REAL")
        except:
            pass

    # Find scan_dates needing benchmarks
    dates = conn.execute("""
        SELECT DISTINCT scan_date FROM discovery_picks
        WHERE benchmark_spy_5d IS NULL AND outcome_5d IS NOT NULL
    """).fetchall()

    if not dates:
        logger.info("No scan dates need benchmark filling")
        return

    scan_dates = [d['scan_date'] for d in dates]
    min_date = min(scan_dates)
    start = (datetime.strptime(min_date, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    logger.info(f"Downloading benchmark data from {start}")
    data = yf.download('XLU XLE SPY', start=start, interval='1d',
                        auto_adjust=True, progress=False, threads=False)
    if data.empty:
        return

    filled = 0
    for sd in scan_dates:
        scan_dt = datetime.strptime(sd, '%Y-%m-%d')
        for etf, col in [('XLU', 'benchmark_xlu_5d'), ('XLE', 'benchmark_xle_5d'), ('SPY', 'benchmark_spy_5d')]:
            try:
                close = data['Close'][etf]
                future = close[close.index > pd.Timestamp(scan_dt)]
                if len(future) >= 5:
                    scan_close = float(close[close.index <= pd.Timestamp(scan_dt)].iloc[-1])
                    day5_close = float(future.iloc[4])
                    ret = round((day5_close / scan_close - 1) * 100, 4)
                    conn.execute(f"UPDATE discovery_picks SET {col}=? WHERE scan_date=?", (ret, sd))
            except Exception as e:
                logger.debug(f"Benchmark {etf} for {sd}: {e}")

        filled += 1
    logger.info(f"Filled benchmarks for {filled} scan dates")


if __name__ == '__main__':
    fill_outcomes()
    fill_benchmarks()
