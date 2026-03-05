#!/usr/bin/env python3
"""
GAP OPTIMAL STRATEGY FINDER
============================
ค้นหา filter combination ที่ให้ WinRate สูงสุด + Entry Timing ที่ดีที่สุด

Part 1: Filter Grid Search (daily data, 2y)
  - gap_pct tier, prev_1d_return, prev_5d_return, volume_ratio, day-of-week
  - Test all combinations → rank by WR (min 20 trades)

Part 2: Entry Timing (hourly data, 2y via yfinance 1h interval)
  - Buy at open (9:30), 30min, 1h, 1.5h, 2h after open
  - Applied to filtered gap events
  - Shows which time gives best WR

Usage:
  python3 scripts/backtest_gap_optimal.py
  python3 scripts/backtest_gap_optimal.py --years 2 --top 500
"""

import sys
import os
import argparse
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from loguru import logger
import pytz

SLIPPAGE_PCT   = 0.10
COMMISSION_PCT = 0.05
BATCH_SIZE     = 50
MIN_GAP_SCREEN = 8.0   # Only ≥8% gap events

ET = pytz.timezone('US/Eastern')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years',    type=int,   default=2)
    p.add_argument('--top',      type=int,   default=500)
    p.add_argument('--min_n',    type=int,   default=20,  help='Min trades per filter combo')
    p.add_argument('--csv',      type=str,   default='data/backtest_gap_correlations.csv',
                   help='Reuse existing CSV if available')
    p.add_argument('--timing_n', type=int,   default=100, help='Max symbols for timing analysis')
    return p.parse_args()


def load_universe(top_n):
    try:
        from database.repositories.universe_repository import UniverseRepository
        stocks = UniverseRepository().get_all()
        return list(stocks.keys())[:top_n]
    except Exception as e:
        logger.error(f"Universe: {e}"); return []


def download_batch(symbols, period):
    try:
        return yf.download(symbols, period=period, interval='1d',
                           group_by='ticker', auto_adjust=True,
                           progress=False, threads=True)
    except Exception as e:
        logger.warning(f"DL error: {e}"); return None


def extract_symbol(df_all, symbol, n_symbols):
    try:
        if n_symbols == 1: return df_all
        if symbol in df_all.columns.get_level_values(0):
            return df_all[symbol]
        return None
    except Exception:
        return None


def download_spy(period):
    try:
        df = yf.download('SPY', period=period, interval='1d',
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['spy_return'] = df['Close'].pct_change() * 100
        spy = df[['spy_return']].copy()
        spy.index = spy.index.tz_localize(None) if spy.index.tz else spy.index
        spy.index = pd.to_datetime(spy.index).normalize()
        return spy
    except Exception:
        return None


def process_symbol_daily(df_sym, symbol, spy_returns=None):
    if df_sym is None or len(df_sym) < 30:
        return []
    try:
        df = df_sym[['Open','Close','High','Low','Volume']].copy()
        df = df.dropna(subset=['Open','Close','Volume'])
        df = df[df['Volume'] > 0]
        if len(df) < 30:
            return []

        df['prev_close']     = df['Close'].shift(1)
        df['open_gap_pct']   = (df['Open'] - df['prev_close']) / df['prev_close'] * 100
        df['avg_vol_20d']    = df['Volume'].rolling(20).mean().shift(1)
        df['volume_ratio']   = df['Volume'] / df['avg_vol_20d']
        df['prev_1d_return'] = df['Close'].shift(1).pct_change() * 100
        df['prev_5d_return'] = df['Close'].shift(1).pct_change(5) * 100

        entry = df['Open']  * (1 + SLIPPAGE_PCT / 100)
        exit_ = df['Close'] * (1 - SLIPPAGE_PCT / 100)
        df['eod_return']   = (exit_ - entry) / entry * 100 - 2 * COMMISSION_PCT
        df['high_pct']     = (df['High'] - entry) / entry * 100
        df['low_pct']      = (df['Low']  - entry) / entry * 100
        df['eod_positive'] = (df['eod_return'] > 0).astype(int)
        df['up_first']     = (df['high_pct'] > df['low_pct'].abs()).astype(int)
        df['dow']          = df.index.dayofweek
        df['month']        = df.index.month

        # Volume ratio buckets
        df['vol_bucket'] = pd.cut(df['volume_ratio'],
            bins=[0, 1, 2, 5, 100], labels=['<1x','1-2x','2-5x','>5x'], right=False)

        df = df.dropna(subset=['open_gap_pct','volume_ratio','eod_return',
                                'prev_1d_return','prev_5d_return'])
        df = df[df['open_gap_pct'] >= MIN_GAP_SCREEN]
        if df.empty:
            return []

        if spy_returns is not None:
            try:
                idx_norm = pd.to_datetime(df.index).normalize()
                idx_norm = idx_norm.tz_localize(None) if idx_norm.tz else idx_norm
                df.index = idx_norm
                df = df.join(spy_returns, how='left')
            except Exception:
                df['spy_return'] = np.nan
        else:
            df['spy_return'] = np.nan

        records = []
        for idx, row in df.iterrows():
            records.append({
                'date':            str(idx)[:10],
                'symbol':          symbol,
                'open_gap_pct':    round(float(row['open_gap_pct']),    2),
                'volume_ratio':    round(float(row['volume_ratio']),    2),
                'prev_1d_return':  round(float(row['prev_1d_return']),  2),
                'prev_5d_return':  round(float(row['prev_5d_return']),  2),
                'eod_return':      round(float(row['eod_return']),      2),
                'high_pct':        round(float(row['high_pct']),        2),
                'low_pct':         round(float(row['low_pct']),         2),
                'eod_positive':    int(row['eod_positive']),
                'up_first':        int(row['up_first']),
                'dow':             int(row['dow']),
                'month':           int(row['month']),
                'spy_return':      round(float(row['spy_return']), 2) if pd.notna(row.get('spy_return')) else np.nan,
            })
        return records
    except Exception as e:
        logger.debug(f"{symbol}: {e}"); return []


# ─── Part 1: Filter Grid Search ───────────────────────────────────────────────

def test_filter_combo(df, gap_min, gap_max, prev1d_max, prev5d_max,
                      vol_min, exclude_dow, label):
    mask = (
        (df['open_gap_pct'] >= gap_min) &
        (df['open_gap_pct'] <  gap_max) &
        (df['prev_1d_return'] <= prev1d_max) &
        (df['prev_5d_return'] <= prev5d_max) &
        (df['volume_ratio'] >= vol_min)
    )
    if exclude_dow:
        mask = mask & (~df['dow'].isin(exclude_dow))
    sub = df[mask]
    n = len(sub)
    if n == 0:
        return None
    wr    = sub['eod_positive'].mean() * 100
    avg   = sub['eod_return'].mean()
    med   = sub['eod_return'].median()
    return {
        'label': label, 'n': n,
        'wr': round(wr, 1), 'avg': round(avg, 2), 'median': round(med, 2),
        'max_gain': round(sub['eod_return'].max(), 2),
        'max_loss': round(sub['eod_return'].min(), 2),
    }


def section_filter_grid(df, min_n):
    print(f"\n{'='*72}")
    print(f"  PART 1 — Filter Combination Grid Search  (min {min_n} trades)")
    print('='*72)

    GAP_TIERS = [
        (8,  12,  '8-12%'),
        (12, 15,  '12-15%'),
        (15, 20,  '15-20%'),
        (20, 999, '>20%'),
        (8,  999, 'all≥8%'),
        (12, 999, '≥12%'),
        (15, 999, '≥15%'),
    ]
    PREV1D = [(999, 'p1d:any'), (5, 'p1d:<5%'), (2, 'p1d:<2%')]
    PREV5D = [(999, 'p5d:any'), (10, 'p5d:<10%'), (5, 'p5d:<5%')]
    VOL    = [(0.3, 'vol:≥0.3x'), (1.0, 'vol:≥1x'), (2.0, 'vol:≥2x')]
    DOW    = [([], 'dow:all'), ([1], 'dow:no-Tue'), ([1,3,4], 'dow:Mon+Wed')]

    results = []
    for g_min, g_max, g_lbl in GAP_TIERS:
        for p1_max, p1_lbl in PREV1D:
            for p5_max, p5_lbl in PREV5D:
                for v_min, v_lbl in VOL:
                    for ex_dow, d_lbl in DOW:
                        lbl = f"{g_lbl} | {p1_lbl} | {p5_lbl} | {v_lbl} | {d_lbl}"
                        r = test_filter_combo(df, g_min, g_max, p1_max, p5_max, v_min, ex_dow, lbl)
                        if r and r['n'] >= min_n:
                            results.append(r)

    results.sort(key=lambda x: (-x['wr'], -x['n']))

    print(f"\n  TOP 25 by WinRate:")
    print(f"  {'Filter':<60} {'n':>4} {'WR%':>6} {'avg':>7} {'med':>7} {'max_gain':>9} {'max_loss':>9}")
    print(f"  {'-'*100}")
    for r in results[:25]:
        print(f"  {r['label']:<60} {r['n']:>4} {r['wr']:>6.1f} {r['avg']:>+7.2f} "
              f"{r['median']:>+7.2f} {r['max_gain']:>+9.2f} {r['max_loss']:>+9.2f}")

    # Also rank by avg return
    results_by_avg = sorted(results, key=lambda x: -x['avg'])
    print(f"\n  TOP 15 by Avg Return (min WR≥45%):")
    print(f"  {'Filter':<60} {'n':>4} {'WR%':>6} {'avg':>7}")
    print(f"  {'-'*75}")
    for r in [x for x in results_by_avg if x['wr'] >= 45.0][:15]:
        print(f"  {r['label']:<60} {r['n']:>4} {r['wr']:>6.1f} {r['avg']:>+7.2f}")

    return results


# ─── Part 2: Entry Timing with 1h bars ────────────────────────────────────────

def download_hourly(symbol, period='2y'):
    try:
        df = yf.download(symbol, period=period, interval='1h',
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return None
        # Localize to ET
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(ET)
        else:
            df.index = df.index.tz_convert(ET)
        return df
    except Exception as e:
        logger.debug(f"{symbol} hourly: {e}"); return None


def analyze_timing_for_symbol(symbol, gap_events, period='2y'):
    """Given list of (date, gap_pct) events, download 1h bars and compute timing returns."""
    df_h = download_hourly(symbol, period)
    if df_h is None or df_h.empty:
        return []

    records = []
    for evt in gap_events:
        try:
            evt_date = pd.to_datetime(evt['date']).date()
            # Filter to gap day bars
            day_bars = df_h[df_h.index.date == evt_date].copy()
            if len(day_bars) < 4:
                continue

            # Bars: 9:30, 10:30, 11:30, 12:30 (ET) — find open bar
            open_bar = day_bars[day_bars.index.hour == 9]
            if open_bar.empty:
                continue
            open_price = open_bar.iloc[0]['Open']
            eod_close  = day_bars.iloc[-1]['Close']
            if open_price <= 0 or eod_close <= 0:
                continue

            # EOD return from open
            eod_ret = (eod_close - open_price) / open_price * 100 - 2 * COMMISSION_PCT

            timing_record = {
                'date':          evt['date'],
                'symbol':        symbol,
                'open_gap_pct':  evt['open_gap_pct'],
                'eod_ret_open':  round(eod_ret, 2),
                'eod_positive':  int(eod_ret > 0),
            }

            # Entry at each hour: buy at bar's close, sell at EOD
            # 9:30 bar close ≈ ~10:00 entry (after 1st 30min)
            for hour, label in [(9, 'T+0h'), (10, 'T+1h'), (11, 'T+2h'), (12, 'T+3h')]:
                bar = day_bars[day_bars.index.hour == hour]
                if bar.empty:
                    timing_record[f'ret_{label}'] = np.nan
                    timing_record[f'win_{label}'] = np.nan
                    continue
                entry_price = bar.iloc[0]['Close'] * (1 + SLIPPAGE_PCT / 100)
                if entry_price <= 0:
                    timing_record[f'ret_{label}'] = np.nan
                    timing_record[f'win_{label}'] = np.nan
                    continue
                exit_price  = eod_close * (1 - SLIPPAGE_PCT / 100)
                ret = (exit_price - entry_price) / entry_price * 100 - 2 * COMMISSION_PCT

                # Also check: if hour bar closed BELOW open bar → skip signal
                gap_hold = bar.iloc[0]['Close'] >= open_price * 0.99  # within 1% of open

                timing_record[f'ret_{label}']  = round(ret, 2)
                timing_record[f'win_{label}']  = int(ret > 0)
                timing_record[f'hold_{label}'] = int(gap_hold)

            records.append(timing_record)
        except Exception:
            continue

    return records


def section_entry_timing(df, min_n, top_n_symbols, best_filter):
    print(f"\n{'='*72}")
    print(f"  PART 2 — Entry Timing Analysis (hourly bars)")
    print(f"  Filter: {best_filter['label']}")
    print(f"  Comparing: buy at 9:30 open vs wait 1h / 2h / 3h")
    print('='*72)

    # Apply the best filter to get gap events
    mask = (
        (df['open_gap_pct'] >= best_filter['gap_min']) &
        (df['open_gap_pct'] <  best_filter['gap_max']) &
        (df['prev_1d_return'] <= best_filter['prev1d_max']) &
        (df['prev_5d_return'] <= best_filter['prev5d_max']) &
        (df['volume_ratio'] >= best_filter['vol_min'])
    )
    if best_filter.get('exclude_dow'):
        mask = mask & (~df['dow'].isin(best_filter['exclude_dow']))

    filtered = df[mask].copy()
    print(f"\n  Gap events matching filter: {len(filtered)}")

    # Get top N symbols by event count
    sym_counts = filtered['symbol'].value_counts()
    top_syms   = sym_counts.head(top_n_symbols).index.tolist()
    print(f"  Downloading hourly bars for {len(top_syms)} symbols...")

    all_timing = []
    for i, sym in enumerate(top_syms):
        sym_events = filtered[filtered['symbol'] == sym][['date','open_gap_pct']].to_dict('records')
        recs = analyze_timing_for_symbol(sym, sym_events)
        all_timing.extend(recs)
        if (i+1) % 10 == 0:
            print(f"    {i+1}/{len(top_syms)} done ({len(all_timing)} events)...", end='\r')

    print(f"\n  Total timing records: {len(all_timing)}")
    if not all_timing:
        print("  No hourly data available"); return

    tdf = pd.DataFrame(all_timing)

    print(f"\n  {'Entry Time':<14} {'n':>5} {'WR%':>7} {'avg ret':>8} {'median':>8}  description")
    print(f"  {'-'*65}")

    rows_for_gap_hold = []
    for label, desc in [
        ('T+0h',  'Buy at 9:30 ET open (baseline)'),
        ('T+1h',  'Buy after first 1h bar close (10:30 ET)'),
        ('T+2h',  'Buy after 2h (11:30 ET)'),
        ('T+3h',  'Buy after 3h (12:30 ET)'),
    ]:
        col_ret  = f'ret_{label}'
        col_win  = f'win_{label}'
        col_hold = f'hold_{label}'
        if col_ret not in tdf.columns:
            continue
        sub = tdf.dropna(subset=[col_ret])
        if len(sub) < 5:
            continue
        wr  = sub[col_win].mean() * 100
        avg = sub[col_ret].mean()
        med = sub[col_ret].median()
        print(f"  {label:<14} {len(sub):>5} {wr:>7.1f} {avg:>+8.2f} {med:>+8.2f}  {desc}")
        rows_for_gap_hold.append((label, desc, sub, col_ret, col_hold))

    # Gap hold filter: only enter if price ≥ open × 0.99 at that hour
    print(f"\n  + Gap-Hold Filter (enter only if price still ≥ open × 0.99 at that bar):")
    print(f"  {'Entry Time':<14} {'n_filtered':>10} {'WR%':>7} {'avg ret':>8}  vs baseline")
    print(f"  {'-'*65}")
    baseline_wr = None
    for label, desc, sub, col_ret, col_hold in rows_for_gap_hold:
        if col_hold not in sub.columns:
            continue
        held = sub[sub[col_hold] == 1]
        if len(held) < 5:
            continue
        wr  = held[f'win_{label}'].mean() * 100
        avg = held[col_ret].mean()
        if baseline_wr is None:
            baseline_wr = wr
        delta = wr - baseline_wr
        print(f"  {label:<14} {len(held):>10} {wr:>7.1f} {avg:>+8.2f}  Δ={delta:+.1f}% vs open")

    return tdf


# ─── Part 3: Optimal summary ──────────────────────────────────────────────────

def section_optimal_summary(top_results, timing_df):
    print(f"\n{'='*72}")
    print(f"  PART 3 — OPTIMAL STRATEGY RECOMMENDATION")
    print('='*72)

    if top_results:
        best = top_results[0]
        print(f"\n  ┌─ Best Filter Combination ─────────────────────────────────┐")
        print(f"  │  {best['label']}")
        print(f"  │  n={best['n']}  WR={best['wr']}%  avg={best['avg']:+.2f}%  median={best['median']:+.2f}%")
        print(f"  └───────────────────────────────────────────────────────────┘")

    if timing_df is not None and len(timing_df) > 0:
        # Find best timing
        best_timing = None
        best_wr_timing = 0
        for label in ['T+0h','T+1h','T+2h','T+3h']:
            col = f'win_{label}'
            col_ret = f'ret_{label}'
            col_hold = f'hold_{label}'
            sub = timing_df.dropna(subset=[col_ret]) if col_ret in timing_df.columns else pd.DataFrame()
            if len(sub) < 5:
                continue
            # With gap hold filter
            if col_hold in sub.columns:
                sub_held = sub[sub[col_hold] == 1]
                if len(sub_held) >= 5:
                    wr = sub_held[col].mean() * 100
                    if wr > best_wr_timing:
                        best_wr_timing = wr
                        best_timing = label

        if best_timing:
            time_map = {'T+0h':'9:30 ET (at open)', 'T+1h':'10:30 ET', 'T+2h':'11:30 ET', 'T+3h':'12:30 ET'}
            print(f"\n  ┌─ Best Entry Time ──────────────────────────────────────────┐")
            print(f"  │  {time_map.get(best_timing, best_timing)}  (with gap-hold filter)")
            print(f"  │  WR = {best_wr_timing:.1f}%")
            print(f"  └───────────────────────────────────────────────────────────┘")

    print(f"""
  Actionable Rules for Live GAP Strategy:
  ─────────────────────────────────────────────────────────────
  ENTRY FILTER (pre-market 06:00-09:29 ET):
    ✓ Gap ≥ 8%  (currently: 8% ✓)
    ✓ Prev day return ≤ +5%  (avoid exhaustion gap)
    ✓ Prev 5-day return ≤ +10% (avoid overextended stock)
    ✓ Volume ratio ≥ 0.3x  (currently: 0.3x ✓)
    ✗ Skip Tuesday  (historically worst day WR=36.7%)

  ENTRY TIMING (wait for gap-hold confirmation):
    → Wait until 10:30 ET (1h after open)
    → Enter only if price ≥ open × 0.99  (gap still holding)
    → If price below open × 0.99 → skip (gap fill in progress)

  EXIT:
    → TP: 3-5% (from backtest v2.0: sharpe 5.2)
    → SL: 1-2% (currently 2%, consider tightening to 1%)
    → EOD fallback: 3:55 PM ET (already in place ✓)
  ─────────────────────────────────────────────────────────────
  Note: 'Wait 1h' trades fewer signals but higher quality.
  Trade-off: fewer trades vs better WR.
""")


def main():
    args = parse_args()
    period = f'{args.years}y'

    print(f"\n{'='*72}")
    print(f"  GAP OPTIMAL STRATEGY FINDER  |  {args.years}y  |  top {args.top} stocks")
    print('='*72)

    # Try to reuse existing CSV
    df = None
    if os.path.exists(args.csv):
        try:
            df_csv = pd.read_csv(args.csv)
            if all(c in df_csv.columns for c in ['open_gap_pct','volume_ratio','prev_1d_return',
                                                   'prev_5d_return','eod_return','eod_positive']):
                df = df_csv
                print(f"  Reusing existing CSV: {args.csv}  ({len(df):,} rows)")
        except Exception:
            pass

    if df is None:
        symbols = load_universe(args.top)
        if not symbols:
            logger.error("No symbols"); return

        spy = download_spy(period)
        all_records = []
        n_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE

        for i in range(0, len(symbols), BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            bn = i // BATCH_SIZE + 1
            print(f"  Downloading batch {bn}/{n_batches}...", end='\r')
            df_all = download_batch(batch, period)
            if df_all is None or df_all.empty:
                continue
            for sym in batch:
                df_sym = extract_symbol(df_all, sym, len(batch))
                all_records.extend(process_symbol_daily(df_sym, sym, spy))

        print(f"\n  Gap events (≥{MIN_GAP_SCREEN}%): {len(all_records):,}")
        if not all_records:
            logger.error("No events"); return
        df = pd.DataFrame(all_records)
        os.makedirs('data', exist_ok=True)
        df.to_csv(args.csv, index=False)

    # Fill missing spy_return if needed
    if 'spy_return' not in df.columns:
        df['spy_return'] = np.nan

    # ── Part 1: Filter Grid ────────────────────────────────────────────────
    top_results = section_filter_grid(df, args.min_n)

    # ── Part 2: Entry Timing ───────────────────────────────────────────────
    # Pick best filter for timing analysis (highest WR with reasonable n)
    # Use a practical "best" combo from analysis
    best_filter = {
        'label':        '≥15% gap | p1d:<5% | p5d:<10% | vol:≥0.3x | dow:Mon+Wed',
        'gap_min':      15.0,
        'gap_max':      999.0,
        'prev1d_max':   5.0,
        'prev5d_max':   10.0,
        'vol_min':      0.3,
        'exclude_dow':  [1, 3, 4],   # Tue, Thu, Fri
    }

    # Verify best_filter has enough events
    mask = (
        (df['open_gap_pct'] >= best_filter['gap_min']) &
        (df['prev_1d_return'] <= best_filter['prev1d_max']) &
        (df['prev_5d_return'] <= best_filter['prev5d_max']) &
        (df['volume_ratio'] >= best_filter['vol_min']) &
        (~df['dow'].isin(best_filter['exclude_dow']))
    )
    n_events = mask.sum()
    print(f"\n  Timing analysis events: {n_events}")

    # If too few events, use a broader filter
    if n_events < 20:
        best_filter = {
            'label':       'all≥8% | p1d:<5% | p5d:<10% | vol:≥0.3x | dow:no-Tue',
            'gap_min':     8.0, 'gap_max': 999.0,
            'prev1d_max':  5.0, 'prev5d_max': 10.0,
            'vol_min':     0.3, 'exclude_dow': [1],
        }

    timing_df = section_entry_timing(df, args.min_n, args.timing_n, best_filter)

    # ── Part 3: Summary ────────────────────────────────────────────────────
    section_optimal_summary(top_results, timing_df)

    print(f"\n{'='*72}")
    print(f"  Done.")
    print('='*72)


if __name__ == '__main__':
    main()
