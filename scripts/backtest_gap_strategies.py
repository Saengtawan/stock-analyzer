#!/usr/bin/env python3
"""
GAP OPEN BACKTEST v2.0 — Multi-Strategy Comparison
====================================================
Compares multiple Gap and Go variants to find the best WinRate / Sharpe config.

Strategies tested:
  A. EOD close  — baseline, buy open sell close (current system)
  B. TP+SL      — fixed take-profit + stop-loss from open
  C. Up-First   — only trade when intraday bullish (high_gain > low_drop proxy)
  D. Combo      — Up-First filter + best TP/SL

Proxy limitations (daily OHLCV):
  - gap_pct     = (today_open - prev_close) / prev_close  (not true pre-market gap)
  - volume_ratio = full-day volume / 20d avg              (not pre-market volume)
  - TP/SL order  = when both H/L triggered: assume SL first if abs(low_drop) > high_gain

Usage:
  python3 scripts/backtest_gap_strategies.py
  python3 scripts/backtest_gap_strategies.py --years 2 --top 500 --gap 8
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
from loguru import logger

# ─── Config ───────────────────────────────────────────────────────────────────
SLIPPAGE_PCT   = 0.10   # 0.1% each side
COMMISSION_PCT = 0.05   # 0.05% each side
BATCH_SIZE     = 50
MIN_GAP_SCREEN = 5.0    # pre-screen filter

# TP/SL test grid
TP_LEVELS = [2.0, 3.0, 5.0, 8.0, 10.0]   # % from entry
SL_LEVELS = [1.0, 2.0, 3.0, 5.0]          # % from entry (positive number = drop)

# Gap × Volume grid for summary
GAP_THRESHOLDS = [5.0, 8.0, 10.0, 12.0, 15.0]
VOL_THRESHOLDS = [0.0, 0.3, 1.0]
# ──────────────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int,   default=2)
    p.add_argument('--top',   type=int,   default=500)
    p.add_argument('--gap',   type=float, default=8.0,  help='Analysis gap threshold (default: 8.0)')
    p.add_argument('--vol',   type=float, default=0.3,  help='Analysis vol threshold (default: 0.3)')
    p.add_argument('--output',type=str,   default='data/backtest_gap_strategies.csv')
    return p.parse_args()


def load_universe(top_n: int) -> list:
    try:
        from database.repositories.universe_repository import UniverseRepository
        stocks = UniverseRepository().get_all()
        symbols = list(stocks.keys())
        logger.info(f"Universe: {len(symbols)} symbols")
        return symbols[:top_n]
    except Exception as e:
        logger.error(f"Universe load failed: {e}")
        return []


def download_batch(symbols: list, period: str):
    try:
        return yf.download(
            symbols, period=period, interval='1d',
            group_by='ticker', auto_adjust=True,
            progress=False, threads=True,
        )
    except Exception as e:
        logger.warning(f"Download error: {e}")
        return None


def extract_symbol(df_all, symbol: str, n_symbols: int):
    try:
        if n_symbols == 1:
            return df_all
        if symbol in df_all.columns.get_level_values(0):
            return df_all[symbol]
        return None
    except Exception:
        return None


def simulate_exit(high_pct: float, low_pct: float, eod_return: float,
                  tp_pct: float, sl_pct: float) -> tuple:
    """
    Simulate TP/SL exit given intraday high/low pct from entry.
    high_pct: (high - entry) / entry * 100  (positive)
    low_pct:  (low  - entry) / entry * 100  (negative)
    Returns: (net_return_pct, exit_type)
    Conservative assumption: when both TP+SL triggered, SL if abs(low) > high.
    """
    tp_hit = high_pct >= tp_pct
    sl_hit = (-low_pct) >= sl_pct   # low_pct is negative

    if tp_hit and sl_hit:
        # Ambiguous — use intraday action proxy
        if (-low_pct) > high_pct:   # went down harder → SL first
            return -sl_pct - 2 * COMMISSION_PCT, 'SL'
        else:
            return tp_pct - 2 * COMMISSION_PCT, 'TP'
    elif tp_hit:
        return tp_pct - 2 * COMMISSION_PCT, 'TP'
    elif sl_hit:
        return -sl_pct - 2 * COMMISSION_PCT, 'SL'
    else:
        return eod_return, 'EOD'


def process_symbol(df_sym, symbol: str) -> list:
    if df_sym is None or len(df_sym) < 25:
        return []
    try:
        df = df_sym[['Open', 'Close', 'High', 'Low', 'Volume']].copy()
        df = df.dropna(subset=['Open', 'Close', 'Volume'])
        df = df[df['Volume'] > 0]
        if len(df) < 25:
            return []

        df['prev_close']   = df['Close'].shift(1)
        df['open_gap_pct'] = (df['Open'] - df['prev_close']) / df['prev_close'] * 100
        df['avg_vol_20d']  = df['Volume'].rolling(20).mean().shift(1)
        df['volume_ratio'] = df['Volume'] / df['avg_vol_20d']

        entry = df['Open']  * (1 + SLIPPAGE_PCT / 100)
        exit_ = df['Close'] * (1 - SLIPPAGE_PCT / 100)

        df['eod_return']   = (exit_ - entry) / entry * 100 - 2 * COMMISSION_PCT
        df['high_pct']     = (df['High'] - entry) / entry * 100   # max gain intraday
        df['low_pct']      = (df['Low']  - entry) / entry * 100   # max loss intraday (negative)

        df = df.dropna(subset=['open_gap_pct', 'volume_ratio', 'eod_return'])
        df = df[df['open_gap_pct'] >= MIN_GAP_SCREEN]
        if df.empty:
            return []

        records = []
        for idx, row in df.iterrows():
            records.append({
                'date':         str(idx)[:10],
                'symbol':       symbol,
                'open_gap_pct': round(float(row['open_gap_pct']), 2),
                'volume_ratio': round(float(row['volume_ratio']), 2),
                'eod_return':   round(float(row['eod_return']),   2),
                'high_pct':     round(float(row['high_pct']),     2),
                'low_pct':      round(float(row['low_pct']),      2),
                # Up-First proxy: intraday went up more than down → bullish gap day
                'up_first':     float(row['high_pct']) > abs(float(row['low_pct'])),
            })
        return records
    except Exception as e:
        logger.debug(f"{symbol}: {e}")
        return []


def stats(returns: pd.Series) -> dict:
    n   = len(returns)
    if n == 0:
        return {}
    wr  = (returns > 0).mean() * 100
    avg = returns.mean()
    med = returns.median()
    std = returns.std()
    sh  = (avg / std * np.sqrt(252)) if std > 0 else 0
    return {
        'n': n, 'win_rate': round(wr, 1),
        'avg': round(avg, 2), 'median': round(med, 2),
        'sharpe': round(sh, 2),
        'max_gain': round(returns.max(), 2),
        'max_loss': round(returns.min(), 2),
        'pct_gt3': round((returns > 3).mean() * 100, 1),
        'pct_ltm3': round((returns < -3).mean() * 100, 1),
    }


# ─── Section A: EOD baseline grid ─────────────────────────────────────────────
def section_eod_grid(df: pd.DataFrame):
    print(f"\n{'='*72}")
    print("  SECTION A — EOD Baseline (buy open, sell close) by gap × volume")
    print('='*72)

    rows = []
    for g in GAP_THRESHOLDS:
        for v in VOL_THRESHOLDS:
            sub = df[(df['open_gap_pct'] >= g) & (df['volume_ratio'] >= v)]
            s   = stats(sub['eod_return'])
            if not s or s['n'] < 10:
                continue
            rows.append({'gap_min': g, 'vol_min': v, **s,
                         'current': g == 8.0 and v == 0.3})

    out = pd.DataFrame(rows)
    print(out[['gap_min','vol_min','n','win_rate','avg','median','sharpe',
               'max_gain','max_loss','pct_gt3','pct_ltm3']].to_string(index=False))

    curr = out[out['current']]
    if not curr.empty:
        r = curr.iloc[0]
        print(f"\n  ★ CURRENT (gap≥8%, vol≥0.3x): n={r['n']} WR={r['win_rate']}% avg={r['avg']:+.2f}% sharpe={r['sharpe']:.2f}")


# ─── Section B: TP+SL grid ────────────────────────────────────────────────────
def section_tp_sl_grid(df: pd.DataFrame, gap_min: float, vol_min: float):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()
    n_total = len(sub)

    print(f"\n{'='*72}")
    print(f"  SECTION B — TP+SL Grid  (gap≥{gap_min}%, vol≥{vol_min}x, n={n_total:,})")
    print(f"  Cells: avg return | win% | sharpe  (SL-first when ambiguous)")
    print('='*72)

    # Header
    tp_labels = [f'TP{int(t)}' for t in TP_LEVELS] + ['EOD']
    hdr = 'SL\\TP'
    print(f"  {hdr:>6}  " + '  '.join(f'{l:>18}' for l in tp_labels))

    rows_all = []
    for sl in SL_LEVELS:
        cells = []
        for tp in TP_LEVELS:
            returns = sub.apply(
                lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, sl)[0],
                axis=1
            )
            s = stats(returns)
            cells.append(s)
            rows_all.append({'tp': tp, 'sl': sl, 'filter': 'none', **s})

        # EOD column (no SL/TP)
        s_eod = stats(sub['eod_return'])
        cells.append(s_eod)

        # Print row
        cell_strs = []
        for s in cells:
            if not s:
                cell_strs.append(f"{'n/a':>18}")
            else:
                cell_strs.append(f"avg={s['avg']:+.1f}% WR={s['win_rate']:.0f}% sh={s['sharpe']:.1f}")
        print(f"  SL{sl:.0f}%  " + '  '.join(cell_strs))

    return rows_all


# ─── Section C: Up-First filter ───────────────────────────────────────────────
def section_up_first(df: pd.DataFrame, gap_min: float, vol_min: float):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()

    print(f"\n{'='*72}")
    print(f"  SECTION C — 'Up-First' Filter  (gap≥{gap_min}%, vol≥{vol_min}x)")
    print(f"  Proxy: intraday_high > abs(intraday_low) = bullish gap day")
    print('='*72)

    up   = sub[sub['up_first'] == True]
    down = sub[sub['up_first'] == False]

    s_all  = stats(sub['eod_return'])
    s_up   = stats(up['eod_return'])
    s_down = stats(down['eod_return'])

    print(f"\n  {'Filter':<16} {'n':>5} {'WR%':>6} {'avg':>7} {'median':>8} {'sharpe':>8} {'max_gain':>9} {'max_loss':>9}")
    print(f"  {'-'*70}")
    for label, s in [('All', s_all), ('Up-First only', s_up), ('Down-First skip', s_down)]:
        if s:
            print(f"  {label:<16} {s['n']:>5} {s['win_rate']:>6.1f} {s['avg']:>+7.2f} "
                  f"{s['median']:>+8.2f} {s['sharpe']:>8.2f} {s['max_gain']:>+9.2f} {s['max_loss']:>+9.2f}")

    # Up-First + TP/SL best
    print(f"\n  Up-First + TP/SL combinations (top by sharpe, n≥20):")
    print(f"  {'TP':>5} {'SL':>5} {'n':>5} {'WR%':>6} {'avg':>7} {'sharpe':>8}")
    best_rows = []
    for tp in TP_LEVELS:
        for sl in SL_LEVELS:
            returns = up.apply(
                lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, sl)[0],
                axis=1
            )
            s = stats(returns)
            if s and s['n'] >= 20:
                best_rows.append({'tp': tp, 'sl': sl, **s})

    best_rows.sort(key=lambda x: x['sharpe'], reverse=True)
    for r in best_rows[:8]:
        print(f"  {r['tp']:>4.0f}% {r['sl']:>4.0f}%  {r['n']:>5} {r['win_rate']:>6.1f} {r['avg']:>+7.2f} {r['sharpe']:>8.2f}")

    return up, down


# ─── Section D: Exit type breakdown ───────────────────────────────────────────
def section_exit_types(df: pd.DataFrame, gap_min: float, vol_min: float,
                       tp: float, sl: float, up_first_only: bool = True):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()
    if up_first_only:
        sub = sub[sub['up_first'] == True]

    label = f"gap≥{gap_min}%, vol≥{vol_min}x, TP={tp}%, SL={sl}%"
    if up_first_only:
        label += ", Up-First"

    results = sub.apply(
        lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, sl),
        axis=1
    )
    sub['ret']  = results.map(lambda x: x[0])
    sub['exit'] = results.map(lambda x: x[1])

    print(f"\n{'='*72}")
    print(f"  SECTION D — Exit Type Breakdown  ({label})")
    print('='*72)
    for exit_type in ['TP', 'SL', 'EOD']:
        mask = sub['exit'] == exit_type
        s = stats(sub.loc[mask, 'ret'])
        if s:
            print(f"  {exit_type:<4}  n={s['n']:>4}  WR={s['win_rate']:>5.1f}%  avg={s['avg']:>+6.2f}%  "
                  f"pct_of_trades={mask.mean()*100:.1f}%")

    total_s = stats(sub['ret'])
    if total_s:
        print(f"\n  TOTAL n={total_s['n']}  WR={total_s['win_rate']}%  avg={total_s['avg']:+.2f}%  "
              f"median={total_s['median']:+.2f}%  sharpe={total_s['sharpe']:.2f}")


# ─── Section E: Best configurations summary ───────────────────────────────────
def section_best_configs(df: pd.DataFrame, gap_min: float, vol_min: float):
    print(f"\n{'='*72}")
    print(f"  SECTION E — Top 15 Configurations by Sharpe  (n≥20)")
    print('='*72)

    combos = []
    base = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()

    for up_first in [False, True]:
        sub = base[base['up_first'] == True] if up_first else base
        for tp in TP_LEVELS + [None]:
            for sl in SL_LEVELS + [None]:
                if tp is None and sl is None:
                    returns = sub['eod_return']
                    name = 'EOD-only'
                elif tp is None:
                    returns = sub.apply(
                        lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], 999, sl)[0],
                        axis=1
                    )
                    name = f'SL{sl}%'
                elif sl is None:
                    returns = sub.apply(
                        lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, 999)[0],
                        axis=1
                    )
                    name = f'TP{tp}%'
                else:
                    returns = sub.apply(
                        lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, sl)[0],
                        axis=1
                    )
                    name = f'TP{tp}%+SL{sl}%'

                s = stats(returns)
                if s and s['n'] >= 20:
                    combos.append({
                        'config': name,
                        'up_first_filter': up_first,
                        **s
                    })

    combos.sort(key=lambda x: x['sharpe'], reverse=True)
    top = combos[:15]

    print(f"\n  {'Config':<18} {'UF':>3} {'n':>5} {'WR%':>6} {'avg':>7} {'med':>7} {'sharpe':>8} {'max_gain':>9} {'max_loss':>9}")
    print(f"  {'-'*78}")
    for r in top:
        uf = '✓' if r['up_first_filter'] else ' '
        print(f"  {r['config']:<18} {uf:>3} {r['n']:>5} {r['win_rate']:>6.1f} "
              f"{r['avg']:>+7.2f} {r['median']:>+7.2f} {r['sharpe']:>8.2f} "
              f"{r['max_gain']:>+9.2f} {r['max_loss']:>+9.2f}")

    return top


# ─── Section F: Return distribution ───────────────────────────────────────────
def section_distribution(df: pd.DataFrame, gap_min: float, vol_min: float,
                         tp: float, sl: float, up_first_only: bool):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()
    if up_first_only:
        sub = sub[sub['up_first'] == True]

    returns = sub.apply(
        lambda r: simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'], tp, sl)[0],
        axis=1
    )

    label = f"gap≥{gap_min}%, vol≥{vol_min}x, TP={tp}%, SL={sl}%"
    if up_first_only:
        label += ", Up-First filter"

    print(f"\n{'='*72}")
    print(f"  SECTION F — Return Distribution  ({label})")
    print('='*72)
    cuts   = [-100, -10, -5, -3, -2, -1, 0, 1, 2, 3, 5, 10, 100]
    labels = ['<-10%','-10to-5','-5to-3','-3to-2','-2to-1','-1to0',
              '0to+1','+1to+2','+2to+3','+3to+5','+5to+10','>+10%']
    buckets = pd.cut(returns, bins=cuts, labels=labels, right=False)
    dist = buckets.value_counts().reindex(labels).fillna(0).astype(int)
    for lbl, count in dist.items():
        bar = '█' * min(int(count / max(dist.max(), 1) * 40), 40)
        pct = count / len(returns) * 100 if len(returns) > 0 else 0
        print(f"  {lbl:>10}  {bar:<40}  {count:>5} ({pct:4.1f}%)")


def main():
    args = parse_args()
    period = f'{args.years}y'
    GAP_MIN = args.gap
    VOL_MIN = args.vol

    print(f"\n{'='*72}")
    print(f"  GAP STRATEGY BACKTEST v2.0  |  {args.years}y  |  top {args.top} stocks")
    print(f"  Slippage: {SLIPPAGE_PCT}% each side  |  Commission: {COMMISSION_PCT}% each side")
    print(f"  Analysis focus: gap≥{GAP_MIN}%, vol≥{VOL_MIN}x")
    print('='*72)

    symbols = load_universe(args.top)
    if not symbols:
        logger.error("No symbols"); return

    # ── Download & process ─────────────────────────────────────────────────
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
            all_records.extend(process_symbol(df_sym, sym))

    print(f"\n  Total gap events (≥{MIN_GAP_SCREEN}%): {len(all_records):,}")
    if not all_records:
        logger.error("No events found"); return

    df = pd.DataFrame(all_records)
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"  Raw data: {args.output}")

    # ── Run all sections ───────────────────────────────────────────────────
    section_eod_grid(df)
    section_tp_sl_grid(df, GAP_MIN, VOL_MIN)
    up_df, _ = section_up_first(df, GAP_MIN, VOL_MIN)

    # Best TP/SL from section B (pick by sharpe from full grid)
    top = section_best_configs(df, GAP_MIN, VOL_MIN)

    # Pick best config for breakdown + distribution
    best = top[0] if top else None
    if best:
        cfg = best['config']  # e.g. 'TP5%+SL2%'
        # Parse config string
        tp_val, sl_val, uf = 5.0, 2.0, best['up_first_filter']
        if 'TP' in cfg and 'SL' in cfg:
            tp_val = float(cfg.split('TP')[1].split('%')[0])
            sl_val = float(cfg.split('SL')[1].split('%')[0])
        elif 'TP' in cfg:
            tp_val = float(cfg.split('TP')[1].split('%')[0])
            sl_val = 999.0
        elif 'SL' in cfg:
            sl_val = float(cfg.split('SL')[1].split('%')[0])
            tp_val = 999.0

        section_exit_types(df, GAP_MIN, VOL_MIN, tp_val, sl_val, uf)
        section_distribution(df, GAP_MIN, VOL_MIN, tp_val, sl_val, uf)

    # ── Recommendation ─────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  RECOMMENDATION")
    print('='*72)
    if top:
        b = top[0]
        uf_str = ' + Up-First filter' if b['up_first_filter'] else ''
        print(f"\n  Best config: {b['config']}{uf_str}")
        print(f"  n={b['n']}  WR={b['win_rate']}%  avg={b['avg']:+.2f}%  "
              f"median={b['median']:+.2f}%  sharpe={b['sharpe']:.2f}")
        print(f"\n  Note: Up-First filter = proxy only (daily data).")
        print(f"  In live trading: wait 5-15min, skip if price < open × 0.99")
    print('='*72)


if __name__ == '__main__':
    main()
