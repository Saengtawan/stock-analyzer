#!/usr/bin/env python3
"""
macro_snapshot_cron.py — v13.1
==============================
Daily macro snapshot: yield curve, VIX, SPY, DXY, commodities, credit, crypto,
FX carry, bond vol, tail risk. 18 instruments total.

v13.1: Added BTC, USD/JPY, SKEW, VVIX, Copper, TLT, LQD, EEM, IEF
       for crash prediction (BTC + JPY detected 5/6 worst months).

Cron (TZ=America/New_York — auto-handles EDT/EST DST):
  10 5 * * 2-6  cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/macro_snapshot_cron.py >> logs/macro_snapshot.log 2>&1

(5:10 AM ET Tue-Sat — runs after fill_outcomes_all.py at 05:00 ET, captures yesterday's close)
"""
import os
import sqlite3
from datetime import datetime, date, timedelta

import yfinance as yf

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# === Original macro symbols (v7.5) ===
YIELD_10Y = '^TNX'    # 10-year Treasury yield (%)
YIELD_3M  = '^IRX'    # 13-week T-bill yield (%)
VIX       = '^VIX'
VIX3M     = '^VIX3M'  # 3-month VIX (term structure analysis)
SPY       = 'SPY'
DXY       = 'DX-Y.NYB'  # US Dollar Index
GOLD      = 'GC=F'       # Gold futures (safe haven)
CRUDE     = 'CL=F'       # WTI Crude Oil futures (commodity shock)
HYG       = 'HYG'        # iShares High Yield Corporate Bond ETF (credit stress)

# === v13.1: New signals for crash prediction ===
BTC       = 'BTC-USD'    # Bitcoin — leads risk-off since 2020 (corr -0.046)
USDJPY    = 'USDJPY=X'   # USD/JPY — yen carry trade (corr -0.090)
SKEW      = '^SKEW'      # CBOE SKEW — tail risk pricing (corr +0.054)
VVIX      = '^VVIX'      # VIX of VIX — volatility regime change
COPPER    = 'HG=F'       # Copper futures — Dr. Copper, economic bellwether
TLT       = 'TLT'        # Treasury 20+ Year ETF — flight to safety
LQD       = 'LQD'        # Investment Grade Corp Bond — credit health (corr +0.040)
EEM       = 'EEM'        # Emerging Markets ETF — global risk appetite
IEF       = 'IEF'        # Treasury 7-10Y ETF — intermediate safe haven


def _get_last_close(symbol: str, as_of_date: date) -> float | None:
    """Fetch last available close on or before as_of_date."""
    try:
        start = (as_of_date - timedelta(days=5)).strftime('%Y-%m-%d')
        end   = (as_of_date + timedelta(days=1)).strftime('%Y-%m-%d')
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return None
        # Filter rows <= as_of_date
        df = df[df.index.date <= as_of_date]
        if df.empty:
            return None
        val = float(df['Close'].iloc[-1].iloc[0] if hasattr(df['Close'].iloc[-1], 'iloc') else df['Close'].iloc[-1])
        # TNX/IRX are quoted as yield × 10 in some feeds, check magnitude
        # yfinance returns them as actual % (e.g., 4.23 for 4.23%)
        return round(val, 4)
    except Exception as e:
        print(f"  {symbol}: {e}")
        return None


def _ensure_table(conn: sqlite3.Connection):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS macro_snapshots (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT NOT NULL UNIQUE,
            yield_10y      REAL,
            yield_3m       REAL,
            yield_spread   REAL,
            vix_close      REAL,
            spy_close      REAL,
            dxy_close      REAL,
            collected_at   TEXT
        )
    ''')
    conn.commit()
    # Add new columns (safe if already exist)
    new_cols = [
        'gold_close', 'crude_close', 'hyg_close',
        # v13.1: New signals
        'btc_close', 'usdjpy_close', 'skew_close', 'vvix_close',
        'copper_close', 'tlt_close', 'lqd_close', 'eem_close', 'ief_close',
    ]
    for col in new_cols:
        try:
            conn.execute(f"ALTER TABLE macro_snapshots ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass


def main():
    today = date.today()
    # Capture yesterday's close (market already closed)
    target = today - timedelta(days=1)
    # Skip weekends
    if target.weekday() >= 5:
        target -= timedelta(days=target.weekday() - 4)

    target_str = target.strftime('%Y-%m-%d')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] macro_snapshot date={target_str}")

    conn = sqlite3.connect(DB_PATH)
    _ensure_table(conn)

    # Skip if already collected
    existing = conn.execute(
        "SELECT id FROM macro_snapshots WHERE date = ?", (target_str,)
    ).fetchone()
    if existing:
        print(f"  Already collected for {target_str} — skip")
        conn.close()
        return

    # Fetch all macro values
    y10   = _get_last_close(YIELD_10Y, target)
    y3m   = _get_last_close(YIELD_3M, target)
    vix   = _get_last_close(VIX, target)
    vix3m = _get_last_close(VIX3M, target)
    spy   = _get_last_close(SPY, target)
    dxy   = _get_last_close(DXY, target)
    gold  = _get_last_close(GOLD, target)
    crude = _get_last_close(CRUDE, target)
    hyg   = _get_last_close(HYG, target)

    # v13.1: New signals
    btc    = _get_last_close(BTC, target)
    usdjpy = _get_last_close(USDJPY, target)
    skew   = _get_last_close(SKEW, target)
    vvix   = _get_last_close(VVIX, target)
    copper = _get_last_close(COPPER, target)
    tlt    = _get_last_close(TLT, target)
    lqd    = _get_last_close(LQD, target)
    eem    = _get_last_close(EEM, target)
    ief    = _get_last_close(IEF, target)

    spread = round(y10 - y3m, 4) if y10 is not None and y3m is not None else None

    # Compute dxy_change_pct from previous day's recorded dxy_close
    dxy_change_pct = None
    if dxy is not None:
        prev_row = conn.execute(
            "SELECT dxy_close, spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if prev_row and prev_row[0] and prev_row[0] > 0:
            dxy_change_pct = round((dxy / prev_row[0] - 1) * 100, 4)
        prev_spy = prev_row[1] if prev_row else None
    else:
        prev_row = conn.execute(
            "SELECT spy_close FROM macro_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        prev_spy = prev_row[0] if prev_row else None

    # Compute regime labels
    regime_label = None
    if vix is not None:
        if vix < 20:
            regime_label = 'NORMAL'
        elif vix < 24:
            regime_label = 'SKIP'
        elif vix < 38:
            regime_label = 'HIGH'
        else:
            regime_label = 'EXTREME'

    spy_regime = None
    if spy is not None and prev_spy is not None and prev_spy > 0:
        spy_regime = 'BULL' if spy > prev_spy else 'BEAR'

    conn.execute('''
        INSERT OR IGNORE INTO macro_snapshots
            (date, yield_10y, yield_3m, yield_spread, vix_close, vix3m_close,
             spy_close, dxy_close, dxy_change_pct,
             gold_close, crude_close, hyg_close,
             btc_close, usdjpy_close, skew_close, vvix_close,
             copper_close, tlt_close, lqd_close, eem_close, ief_close,
             regime_label, spy_regime, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ''', (target_str, y10, y3m, spread, vix, vix3m, spy, dxy, dxy_change_pct,
          gold, crude, hyg,
          btc, usdjpy, skew, vvix, copper, tlt, lqd, eem, ief,
          regime_label, spy_regime))
    conn.commit()
    conn.close()

    print(f"  ✅ Saved: VIX={vix}({regime_label}) SPY={spy} BTC={btc} JPY={usdjpy} SKEW={skew} VVIX={vvix} Copper={copper} TLT={tlt} LQD={lqd}")


if __name__ == '__main__':
    main()
