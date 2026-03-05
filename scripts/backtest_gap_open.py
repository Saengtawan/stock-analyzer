#!/usr/bin/env python3
"""
GAP OPEN BACKTEST v1.0
======================
Backtest: buy stock at open if overnight gap ≥ threshold, sell at EOD close.

Proxy note:
  - "Open gap" = (today_open - prev_close) / prev_close  (actual open price)
  - Volume ratio = full-day volume / 20d avg daily volume  (proxy for pre-market activity)
  - Real pre-market hourly volume is not available historically in yfinance

Current scanner filters (config/trading.yaml):
  MIN_GAP_PCT     = 8%
  MIN_VOLUME_RATIO = 0.3x
  MIN_CONFIDENCE  = 80%  (confidence = POSSIBLE_CATALYST if gap ≥ 8%)

Usage:
  cd /home/saengtawan/work/project/cc/stock-analyzer
  python3 scripts/backtest_gap_open.py
  python3 scripts/backtest_gap_open.py --years 1 --top 500
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
from datetime import datetime
from loguru import logger

# ─── Config ───────────────────────────────────────────────────────────────────
SLIPPAGE_PCT   = 0.10   # 0.1% each side (buy + sell)
COMMISSION_PCT = 0.05   # 0.05% each side
BATCH_SIZE     = 50     # symbols per yf.download call
MIN_GAP_SCREEN = 5.0    # pre-screen: only keep gap ≥ 5% events (saves memory)

# Current scanner thresholds (to highlight in output)
CURRENT_GAP_MIN = 8.0
CURRENT_VOL_MIN = 0.3

# Analysis grid
GAP_THRESHOLDS = [5.0, 6.0, 8.0, 10.0, 12.0, 15.0]
VOL_THRESHOLDS = [0.0, 0.3, 0.5, 1.0]
# ──────────────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(description='Backtest premarket gap strategy')
    p.add_argument('--years',  type=int,   default=2,    help='Lookback years (default: 2)')
    p.add_argument('--top',    type=int,   default=1000, help='Top N stocks by universe (default: 1000)')
    p.add_argument('--output', type=str,   default='data/backtest_gap_open.csv', help='Output CSV path')
    return p.parse_args()


def load_universe(top_n: int) -> list[str]:
    try:
        from database.repositories.universe_repository import UniverseRepository
        stocks = UniverseRepository().get_all()
        symbols = list(stocks.keys())
        logger.info(f"Universe: {len(symbols)} symbols loaded from DB")
        return symbols[:top_n]
    except Exception as e:
        logger.error(f"Could not load universe: {e}")
        return []


def download_batch(symbols: list[str], period: str) -> pd.DataFrame | None:
    try:
        df = yf.download(
            symbols,
            period=period,
            interval='1d',
            group_by='ticker',
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        return df
    except Exception as e:
        logger.warning(f"Batch download error: {e}")
        return None


def extract_symbol(df_all, symbol: str, n_symbols: int) -> pd.DataFrame | None:
    """Extract single symbol from multi/single ticker download result."""
    try:
        if n_symbols == 1:
            return df_all
        if symbol in df_all.columns.get_level_values(0):
            return df_all[symbol]
        return None
    except Exception:
        return None


def process_symbol(df_sym: pd.DataFrame, symbol: str) -> list[dict]:
    """Compute open-gap events for one symbol. Returns list of trade records."""
    if df_sym is None or len(df_sym) < 25:
        return []
    try:
        df = df_sym[['Open', 'Close', 'High', 'Low', 'Volume']].copy()
        df = df.dropna(subset=['Open', 'Close', 'Volume'])
        df = df[df['Volume'] > 0]
        if len(df) < 25:
            return []

        df['prev_close']    = df['Close'].shift(1)
        df['open_gap_pct']  = (df['Open'] - df['prev_close']) / df['prev_close'] * 100
        df['avg_vol_20d']   = df['Volume'].rolling(20).mean().shift(1)
        df['volume_ratio']  = df['Volume'] / df['avg_vol_20d']

        # Intraday return: buy open (+slippage), sell close (-slippage)
        entry = df['Open']  * (1 + SLIPPAGE_PCT  / 100)
        exit_ = df['Close'] * (1 - SLIPPAGE_PCT  / 100)
        df['net_return_pct'] = (exit_ - entry) / entry * 100 - 2 * COMMISSION_PCT

        # Intraday high/low for max gain / max drawdown
        df['intraday_high_pct'] = (df['High']  - entry) / entry * 100
        df['intraday_low_pct']  = (df['Low']   - entry) / entry * 100

        df = df.dropna(subset=['open_gap_pct', 'volume_ratio', 'net_return_pct'])
        df = df[df['open_gap_pct'] >= MIN_GAP_SCREEN]  # pre-screen
        if df.empty:
            return []

        records = []
        for idx, row in df.iterrows():
            records.append({
                'date':             str(idx)[:10],
                'symbol':           symbol,
                'open_gap_pct':     round(float(row['open_gap_pct']), 2),
                'volume_ratio':     round(float(row['volume_ratio']), 2),
                'open':             round(float(row['Open']), 2),
                'close':            round(float(row['Close']), 2),
                'prev_close':       round(float(row['prev_close']), 2),
                'net_return_pct':   round(float(row['net_return_pct']), 2),
                'intraday_high_pct':round(float(row['intraday_high_pct']), 2),
                'intraday_low_pct': round(float(row['intraday_low_pct']), 2),
                'win':              float(row['net_return_pct']) > 0,
            })
        return records
    except Exception as e:
        logger.debug(f"{symbol}: process error — {e}")
        return []


def analyze_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Build summary table for all gap × vol threshold combinations."""
    rows = []
    for gap_min in GAP_THRESHOLDS:
        for vol_min in VOL_THRESHOLDS:
            sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)]
            n = len(sub)
            if n < 5:
                continue
            ret = sub['net_return_pct']
            rows.append({
                'gap_min':      gap_min,
                'vol_min':      vol_min,
                'n_trades':     n,
                'win_rate':     round(sub['win'].mean() * 100, 1),
                'avg_return':   round(ret.mean(), 2),
                'median_return':round(ret.median(), 2),
                'avg_gain':     round(ret[ret > 0].mean(), 2) if (ret > 0).any() else 0,
                'avg_loss':     round(ret[ret <= 0].mean(), 2) if (ret <= 0).any() else 0,
                'max_gain':     round(ret.max(), 2),
                'max_loss':     round(ret.min(), 2),
                'pct_gt_2':     round((ret > 2).mean() * 100, 1),   # % trades > +2%
                'pct_lt_m2':    round((ret < -2).mean() * 100, 1),  # % trades < -2%
                'sharpe':       round((ret.mean() / ret.std()) * np.sqrt(252), 2) if ret.std() > 0 else 0,
                'is_current':   gap_min == CURRENT_GAP_MIN and vol_min == CURRENT_VOL_MIN,
            })
    return pd.DataFrame(rows)


def analyze_by_gap_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Break down by gap size bucket (regardless of volume)."""
    bins   = [5, 8, 10, 12, 15, 20, 30, 100]
    labels = ['5-8%', '8-10%', '10-12%', '12-15%', '15-20%', '20-30%', '>30%']
    df['gap_bucket'] = pd.cut(df['open_gap_pct'], bins=bins, labels=labels, right=False)
    grouped = df.groupby('gap_bucket', observed=True).agg(
        n_trades    =('net_return_pct', 'count'),
        win_rate    =('win', lambda x: round(x.mean() * 100, 1)),
        avg_return  =('net_return_pct', lambda x: round(x.mean(), 2)),
        median_ret  =('net_return_pct', lambda x: round(x.median(), 2)),
        avg_high    =('intraday_high_pct', lambda x: round(x.mean(), 2)),
        avg_low     =('intraday_low_pct',  lambda x: round(x.mean(), 2)),
    ).reset_index()
    return grouped


def analyze_by_vol_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Break down by volume ratio bucket (gap ≥ 8% only)."""
    sub = df[df['open_gap_pct'] >= 8.0].copy()
    bins   = [0, 0.3, 0.5, 0.6, 1.0, 2.0, 100]
    labels = ['<0.3x', '0.3-0.5x', '0.5-0.6x', '0.6-1x', '1-2x', '>2x']
    sub['vol_bucket'] = pd.cut(sub['volume_ratio'], bins=bins, labels=labels, right=False)
    grouped = sub.groupby('vol_bucket', observed=True).agg(
        n_trades    =('net_return_pct', 'count'),
        win_rate    =('win', lambda x: round(x.mean() * 100, 1)),
        avg_return  =('net_return_pct', lambda x: round(x.mean(), 2)),
        median_ret  =('net_return_pct', lambda x: round(x.median(), 2)),
    ).reset_index()
    return grouped


def analyze_by_day_of_week(df: pd.DataFrame) -> pd.DataFrame:
    """Monday-Friday breakdown for gap ≥ 8%, vol ≥ 0.3x."""
    sub = df[(df['open_gap_pct'] >= 8.0) & (df['volume_ratio'] >= 0.3)].copy()
    sub['dow'] = pd.to_datetime(sub['date']).dt.day_name()
    order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    grouped = sub.groupby('dow').agg(
        n_trades=('net_return_pct', 'count'),
        win_rate=('win', lambda x: round(x.mean() * 100, 1)),
        avg_return=('net_return_pct', lambda x: round(x.mean(), 2)),
    ).reindex(order).reset_index()
    return grouped


def print_table(title: str, df: pd.DataFrame, highlight_col: str = None):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)
    print(df.to_string(index=False))


def main():
    args = parse_args()
    period = f'{args.years}y'

    print(f"\n{'='*70}")
    print(f"  GAP OPEN BACKTEST  |  {args.years}y  |  top {args.top} stocks")
    print(f"  Slippage: {SLIPPAGE_PCT}% each side  |  Commission: {COMMISSION_PCT}% each side")
    print(f"  Current scanner: gap ≥ {CURRENT_GAP_MIN}%, vol ≥ {CURRENT_VOL_MIN}x")
    print('='*70)

    symbols = load_universe(args.top)
    if not symbols:
        logger.error("No symbols to backtest")
        sys.exit(1)

    # ── Download + process ──────────────────────────────────────────────────
    all_records = []
    n_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Downloading batch {batch_num}/{n_batches} ({len(batch)} symbols)...", end='\r')

        df_all = download_batch(batch, period)
        if df_all is None or df_all.empty:
            continue

        for sym in batch:
            df_sym = extract_symbol(df_all, sym, len(batch))
            records = process_symbol(df_sym, sym)
            all_records.extend(records)

    print(f"\n  Total gap events (≥{MIN_GAP_SCREEN}%): {len(all_records):,}")

    if not all_records:
        logger.error("No gap events found")
        sys.exit(1)

    df = pd.DataFrame(all_records)

    # ── Save raw CSV ────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"  Raw data saved → {args.output}")

    # ── Analysis ────────────────────────────────────────────────────────────

    # 1. Grid (gap × volume)
    grid = analyze_grid(df)
    print_table("GRID: gap_min × vol_min  (★ = current scanner setting)", grid)
    # Mark current setting
    for _, row in grid[grid['is_current']].iterrows():
        print(f"\n  ★ CURRENT SETTING (gap≥{CURRENT_GAP_MIN}%, vol≥{CURRENT_VOL_MIN}x):")
        print(f"    n={row['n_trades']:,}  WR={row['win_rate']}%  "
              f"avg={row['avg_return']:+.2f}%  median={row['median_return']:+.2f}%  "
              f"sharpe={row['sharpe']:.2f}")

    # 2. By gap bucket
    print_table("BY GAP SIZE BUCKET (all volume)", analyze_by_gap_bucket(df))

    # 3. By volume bucket (gap ≥ 8% only)
    print_table("BY VOLUME RATIO BUCKET (gap ≥ 8% only)", analyze_by_vol_bucket(df))

    # 4. Day of week
    print_table("DAY OF WEEK (gap ≥ 8%, vol ≥ 0.3x)", analyze_by_day_of_week(df))

    # 5. Best single threshold by avg_return (min 30 trades)
    best = grid[grid['n_trades'] >= 30].sort_values('avg_return', ascending=False).head(5)
    print_table("TOP 5 SETTINGS BY AVG RETURN (min 30 trades)", best[
        ['gap_min','vol_min','n_trades','win_rate','avg_return','median_return','sharpe']
    ])

    # 6. Distribution of returns for current setting
    current = df[(df['open_gap_pct'] >= CURRENT_GAP_MIN) & (df['volume_ratio'] >= CURRENT_VOL_MIN)]
    if not current.empty:
        print(f"\n{'='*70}")
        print(f"  RETURN DISTRIBUTION  (gap ≥ {CURRENT_GAP_MIN}%, vol ≥ {CURRENT_VOL_MIN}x, n={len(current):,})")
        print('='*70)
        cuts = [-100, -10, -5, -3, -2, -1, 0, 1, 2, 3, 5, 10, 100]
        labels = ['<-10%','-10to-5','-5to-3','-3to-2','-2to-1','-1to0',
                  '0to+1','+1to+2','+2to+3','+3to+5','+5to+10','>+10%']
        buckets = pd.cut(current['net_return_pct'], bins=cuts, labels=labels, right=False)
        dist = buckets.value_counts().reindex(labels).fillna(0).astype(int)
        for label, count in dist.items():
            bar = '█' * min(int(count / max(dist) * 40), 40)
            pct = count / len(current) * 100
            print(f"  {label:>10}  {bar:<40}  {count:>5} ({pct:4.1f}%)")

    print(f"\n{'='*70}")
    print(f"  Done. Full data: {args.output}")
    print('='*70)


if __name__ == '__main__':
    main()
