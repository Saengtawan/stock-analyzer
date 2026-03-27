#!/usr/bin/env python3
"""
PEM Backtest — Post-Earnings Momentum
======================================
Hypotheses:
  P1: gap size vs outcome_1d  (sweet spot? overreaction?)
  P2: BMO vs AMC timing
  P3: EPS surprise vs gap / outcome

Universe: top 250 liquid stocks from universe_stocks (by dollar_vol)
          excluding permanently blocked sectors
Period:   last 8 quarters from yfinance earnings_dates

Run: python3 scripts/backtest_pem.py [--top N] [--min-gap PCT]
"""

import sys, os, time, argparse
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')

BLOCKED_SECTORS = {
    'Consumer Cyclical', 'Consumer Defensive', 'Consumer_Travel',
    'Consumer_Auto', 'Consumer_Retail', 'Consumer_Food', 'Consumer_Staples',
    'Communication Services', 'Finance_Banks', 'Unknown',
}

def load_universe(top_n: int) -> list[str]:
    conn = None  # via get_session()
    rows = conn.execute("""
        SELECT symbol, sector, dollar_vol FROM universe_stocks
        WHERE sector NOT IN ({})
        ORDER BY dollar_vol DESC LIMIT ?
    """.format(','.join('?' * len(BLOCKED_SECTORS))),
        list(BLOCKED_SECTORS) + [top_n]
    ).fetchall()
    conn.close()
    syms = [r[0] for r in rows]
    print(f"Universe: {len(syms)} stocks (top {top_n} by dollar_vol, blocked sectors excluded)")
    return syms


def fetch_earnings(symbol: str, quarters: int = 10) -> pd.DataFrame:
    """Fetch historical earnings dates + EPS surprise from yfinance."""
    try:
        t = yf.Ticker(symbol)
        ed = t.get_earnings_dates(limit=quarters * 2)
        if ed is None or ed.empty:
            return pd.DataFrame()
        # Drop future (NaN Reported EPS)
        ed = ed.dropna(subset=['Reported EPS'])
        ed.index = pd.to_datetime(ed.index).tz_localize(None)
        ed = ed.sort_index(ascending=False).head(quarters)
        return ed
    except Exception:
        return pd.DataFrame()


def fetch_daily(symbol: str) -> pd.DataFrame:
    """Fetch 2yr daily bars."""
    try:
        df = yf.download(symbol, period='2y', interval='1d',
                         auto_adjust=True, progress=False)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


def analyze_earnings_event(symbol: str, earnings_dt: datetime,
                            eps_surprise_pct: float,
                            daily: pd.DataFrame,
                            min_gap_pct: float) -> dict | None:
    """
    For one earnings event, compute:
      - gap_pct: open_D0 / close_D-1 - 1
      - timing: BMO (before 12:00) vs AMC (after 12:00)
      - outcome_1d: close_D0 / open_D0 - 1  (intraday, like PEM same-day)
      - outcome_next: close_D1 / open_D0 - 1 (next day)
      - volume_ratio: volume_D0 / avg_vol_20d
    """
    if daily.empty:
        return None

    dates = daily.index.normalize()
    earn_date = pd.Timestamp(earnings_dt).normalize()

    # Determine D0 (trading day of/after earnings)
    timing = 'BMO' if earnings_dt.hour < 12 else 'AMC'
    if timing == 'AMC':
        # Earnings after close → gap shows next trading day
        future = dates[dates > earn_date]
        if future.empty:
            return None
        d0 = future[0]
    else:
        # BMO → gap shows same day
        future = dates[dates >= earn_date]
        if future.empty:
            return None
        d0 = future[0]

    d0_idx = daily.index.get_loc(d0)
    if d0_idx < 20:
        return None  # Not enough history

    d0_row  = daily.iloc[d0_idx]
    dm1_row = daily.iloc[d0_idx - 1]  # day before

    open_d0   = float(d0_row['Open'].iloc[0]) if hasattr(d0_row['Open'], 'iloc') else float(d0_row['Open'])
    low_d0    = float(d0_row['Low'].iloc[0])  if hasattr(d0_row['Low'],  'iloc') else float(d0_row['Low'])
    close_dm1 = float(dm1_row['Close'].iloc[0]) if hasattr(dm1_row['Close'], 'iloc') else float(dm1_row['Close'])
    close_d0  = float(d0_row['Close'].iloc[0])  if hasattr(d0_row['Close'],  'iloc') else float(d0_row['Close'])

    if close_dm1 <= 0 or open_d0 <= 0:
        return None

    gap_pct = (open_d0 / close_dm1 - 1) * 100
    if gap_pct < min_gap_pct:
        return None

    # open→low fade: how far did price drop from open intraday?
    open_to_low_pct = (low_d0 / open_d0 - 1) * 100  # always ≤ 0

    # Intraday outcome (open → close same day) — like PEM same-day exit
    outcome_intraday = (close_d0 / open_d0 - 1) * 100
    # Full day outcome (prev_close → close D0)
    outcome_1d = (close_d0 / close_dm1 - 1) * 100

    # Next day outcome
    outcome_next = None
    if d0_idx + 1 < len(daily):
        close_d1 = float(daily.iloc[d0_idx + 1]['Close'])
        outcome_next = (close_d1 / open_d0 - 1) * 100

    # Volume ratio
    vol_d0 = float(d0_row['Volume'])
    avg_vol = float(daily['Volume'].iloc[d0_idx - 20:d0_idx].mean())
    vol_ratio = vol_d0 / avg_vol if avg_vol > 0 else None

    # Pre-market proxy: not available from daily bars
    # Use open vs prev_close as gap (same as PEM screener)

    return {
        'symbol':           symbol,
        'earn_date':        earnings_dt.strftime('%Y-%m-%d'),
        'd0':               d0.strftime('%Y-%m-%d'),
        'timing':           timing,
        'gap_pct':          round(gap_pct, 2),
        'open_to_low_pct':  round(open_to_low_pct, 2),
        'faded':            1 if open_to_low_pct < -1.0 else 0,
        'eps_surprise_pct': round(eps_surprise_pct, 2) if not pd.isna(eps_surprise_pct) else None,
        'open_d0':          round(open_d0, 2),
        'close_dm1':        round(close_dm1, 2),
        'outcome_intraday': round(outcome_intraday, 2),  # PEM-style (open→close)
        'outcome_1d':       round(outcome_1d, 2),        # prev_close→close
        'outcome_next':     round(outcome_next, 2) if outcome_next else None,
        'vol_ratio':        round(vol_ratio, 2) if vol_ratio else None,
        'win_intraday':     1 if outcome_intraday > 0 else 0,
        'win_1d':           1 if outcome_1d > 0 else 0,
    }


def print_analysis(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print(f"PEM BACKTEST RESULTS  (n={len(df)} events)")
    print(f"{'='*60}")

    # ── P1: Gap size buckets vs outcome_intraday ──────────────
    print("\n── P1: Gap Size vs Intraday Outcome (open→close, PEM-style) ──")
    bins   = [8, 10, 15, 20, 30, 50, 200]
    labels = ['8-10%','10-15%','15-20%','20-30%','30-50%','≥50%']
    df['gap_bucket'] = pd.cut(df['gap_pct'], bins=bins, labels=labels, right=False)
    g1 = df.groupby('gap_bucket', observed=True).agg(
        n=('outcome_intraday','count'),
        wr=('win_intraday','mean'),
        avg=('outcome_intraday','mean'),
        med=('outcome_intraday','median'),
    ).reset_index()
    g1['wr'] = (g1['wr']*100).round(1)
    g1['avg'] = g1['avg'].round(2)
    g1['med'] = g1['med'].round(2)
    print(g1.to_string(index=False))

    # ── P2: BMO vs AMC ──────────────────────────────────────
    print("\n── P2: BMO vs AMC Timing ──")
    g2 = df.groupby('timing').agg(
        n=('outcome_intraday','count'),
        wr_intraday=('win_intraday','mean'),
        avg_intraday=('outcome_intraday','mean'),
        wr_1d=('win_1d','mean'),
        avg_1d=('outcome_1d','mean'),
    ).reset_index()
    g2['wr_intraday'] = (g2['wr_intraday']*100).round(1)
    g2['avg_intraday'] = g2['avg_intraday'].round(2)
    g2['wr_1d'] = (g2['wr_1d']*100).round(1)
    g2['avg_1d'] = g2['avg_1d'].round(2)
    print(g2.to_string(index=False))

    # ── P3: EPS Surprise vs gap / outcome ────────────────────
    print("\n── P3: EPS Surprise Buckets vs Intraday Outcome ──")
    df_s = df.dropna(subset=['eps_surprise_pct'])
    surp_bins   = [-999, 0, 5, 15, 30, 999]
    surp_labels = ['Miss','0-5%','5-15%','15-30%','≥30%']
    df_s = df_s.copy()
    df_s['surp_bucket'] = pd.cut(df_s['eps_surprise_pct'],
                                  bins=surp_bins, labels=surp_labels, right=False)
    g3 = df_s.groupby('surp_bucket', observed=True).agg(
        n=('outcome_intraday','count'),
        wr=('win_intraday','mean'),
        avg_intraday=('outcome_intraday','mean'),
        avg_gap=('gap_pct','mean'),
    ).reset_index()
    g3['wr'] = (g3['wr']*100).round(1)
    g3['avg_intraday'] = g3['avg_intraday'].round(2)
    g3['avg_gap'] = g3['avg_gap'].round(2)
    print(g3.to_string(index=False))

    # ── P4: Gap threshold sensitivity ────────────────────────
    print("\n── P4: Threshold Sensitivity (WR if we require gap ≥ X%) ──")
    for thresh in [8, 10, 12, 15, 20, 25]:
        sub = df[df['gap_pct'] >= thresh]
        if len(sub) == 0:
            continue
        wr  = sub['win_intraday'].mean() * 100
        avg = sub['outcome_intraday'].mean()
        print(f"  gap ≥{thresh:3d}%: n={len(sub):4d}  WR={wr:.1f}%  avg={avg:+.2f}%")

    # ── P6: Fade filter — gap ≥15% fade vs no-fade ───────────
    print("\n── P6: Gap ≥15% — Fade (open→low < -1%) vs No-Fade ──")
    big = df[df['gap_pct'] >= 15].copy()
    if not big.empty and 'faded' in big.columns:
        g6 = big.groupby('faded').agg(
            n=('outcome_intraday','count'),
            wr=('win_intraday','mean'),
            avg=('outcome_intraday','mean'),
            med=('outcome_intraday','median'),
            avg_fade=('open_to_low_pct','mean'),
        ).reset_index()
        g6['faded'] = g6['faded'].map({0: 'No-Fade', 1: 'Faded(>1%)'})
        g6['wr']  = (g6['wr']*100).round(1)
        g6['avg'] = g6['avg'].round(2)
        g6['med'] = g6['med'].round(2)
        g6['avg_fade'] = g6['avg_fade'].round(2)
        print(g6.to_string(index=False))

        # Also: fade by timing for gap ≥15%
        print("\n── P6b: Gap ≥15% — Fade × Timing ──")
        g6b = big.groupby(['timing','faded']).agg(
            n=('outcome_intraday','count'),
            wr=('win_intraday','mean'),
            avg=('outcome_intraday','mean'),
        ).reset_index()
        g6b['faded'] = g6b['faded'].map({0: 'No-Fade', 1: 'Faded'})
        g6b['wr']  = (g6b['wr']*100).round(1)
        g6b['avg'] = g6b['avg'].round(2)
        print(g6b.to_string(index=False))
    else:
        print("  (no data or faded column missing)")

    # ── P5: BMO gap size interaction ─────────────────────────
    print("\n── P5: BMO gap size vs intraday (open→close) ──")
    bmo = df[df['timing'] == 'BMO'].copy()
    bmo['gap_bucket'] = pd.cut(bmo['gap_pct'], bins=bins, labels=labels, right=False)
    g5 = bmo.groupby('gap_bucket', observed=True).agg(
        n=('outcome_intraday','count'),
        wr=('win_intraday','mean'),
        avg=('outcome_intraday','mean'),
    ).reset_index()
    g5['wr'] = (g5['wr']*100).round(1)
    g5['avg'] = g5['avg'].round(2)
    print(g5.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top',     type=int,   default=250, help='Top N stocks by dollar_vol')
    parser.add_argument('--min-gap', type=float, default=8.0, help='Min gap pct to include')
    parser.add_argument('--quarters',type=int,   default=8,   help='Quarters of earnings history')
    args = parser.parse_args()

    symbols = load_universe(args.top)
    results = []
    errors  = 0

    for i, sym in enumerate(symbols):
        if i % 25 == 0:
            print(f"  [{i}/{len(symbols)}] fetching...")

        earnings = fetch_earnings(sym, args.quarters)
        if earnings.empty:
            errors += 1
            continue

        daily = fetch_daily(sym)
        if daily.empty:
            errors += 1
            continue

        for earn_dt, row in earnings.iterrows():
            event = analyze_earnings_event(
                sym, earn_dt,
                row.get('Surprise(%)', float('nan')),
                daily,
                args.min_gap,
            )
            if event:
                results.append(event)

        time.sleep(0.1)  # rate limit

    if not results:
        print("No gap events found.")
        return

    df = pd.DataFrame(results)
    print(f"\nTotal gap events ≥{args.min_gap}%: {len(df)}  ({errors} symbols failed)")

    # Save CSV
    out = os.path.join(os.path.dirname(__file__), '..', 'data', 'pem_backtest.csv')
    df.to_csv(out, index=False)
    print(f"Saved: {out}")

    print_analysis(df)


if __name__ == '__main__':
    main()
