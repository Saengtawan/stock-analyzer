#!/usr/bin/env python3
"""
GAP CORRELATION ANALYSIS
=========================
ค้นหา indicator / ค่าที่สัมพันธ์กับ gap up (hold) vs gap down (fill)
บน daily OHLCV data

Features ที่ test:
  - open_gap_pct     : ขนาด gap
  - volume_ratio     : volume วันนั้น / 20d avg
  - prev_1d_return   : return วันก่อนหน้า (momentum short)
  - prev_5d_return   : return 5 วันก่อน (momentum medium)
  - intraday_range   : (high-low)/open — ความผันผวนภายในวัน
  - dow              : วันในสัปดาห์
  - month            : เดือน
  - spy_day_return   : SPY return วันเดียวกัน (market context)
  - gap_fill_ratio   : (close-open)/(open-prev_close) — fill=<0, extend=>1

Target:
  - eod_return       : continuous return EOD
  - gap_held         : 1 ถ้า close > prev_close (gap ยัง hold ≥ 50%)
  - eod_positive     : 1 ถ้า eod_return > 0

Usage:
  python3 scripts/backtest_gap_correlations.py
  python3 scripts/backtest_gap_correlations.py --years 3 --top 1000 --gap 8
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
from scipy import stats as scipy_stats
from loguru import logger

SLIPPAGE_PCT   = 0.10
COMMISSION_PCT = 0.05
BATCH_SIZE     = 50
MIN_GAP_SCREEN = 5.0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int,   default=2)
    p.add_argument('--top',   type=int,   default=500)
    p.add_argument('--gap',   type=float, default=8.0)
    p.add_argument('--vol',   type=float, default=0.3)
    p.add_argument('--output',type=str,   default='data/backtest_gap_correlations.csv')
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
        logger.warning(f"Download error: {e}"); return None


def extract_symbol(df_all, symbol, n_symbols):
    try:
        if n_symbols == 1: return df_all
        if symbol in df_all.columns.get_level_values(0):
            return df_all[symbol]
        return None
    except Exception:
        return None


def download_spy(period):
    """Download SPY for market context"""
    try:
        df = yf.download('SPY', period=period, interval='1d',
                         auto_adjust=True, progress=False)
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['spy_return'] = df['Close'].pct_change() * 100
        # Normalize index to date string for joining
        spy = df[['spy_return']].copy()
        spy.index = spy.index.tz_localize(None) if spy.index.tz else spy.index
        spy.index = pd.to_datetime(spy.index).normalize()
        return spy
    except Exception as e:
        logger.warning(f"SPY download failed: {e}")
        return None


def process_symbol(df_sym, symbol, spy_returns=None):
    if df_sym is None or len(df_sym) < 30:
        return []
    try:
        df = df_sym[['Open','Close','High','Low','Volume']].copy()
        df = df.dropna(subset=['Open','Close','Volume'])
        df = df[df['Volume'] > 0]
        if len(df) < 30:
            return []

        # ── Core gap metrics ──────────────────────────────────
        df['prev_close']    = df['Close'].shift(1)
        df['open_gap_pct']  = (df['Open'] - df['prev_close']) / df['prev_close'] * 100
        df['avg_vol_20d']   = df['Volume'].rolling(20).mean().shift(1)
        df['volume_ratio']  = df['Volume'] / df['avg_vol_20d']

        # Entry/exit with costs
        entry = df['Open']  * (1 + SLIPPAGE_PCT  / 100)
        exit_ = df['Close'] * (1 - SLIPPAGE_PCT  / 100)
        df['eod_return']    = (exit_ - entry) / entry * 100 - 2 * COMMISSION_PCT
        df['high_pct']      = (df['High']  - entry) / entry * 100
        df['low_pct']       = (df['Low']   - entry) / entry * 100  # negative

        # ── Additional features ───────────────────────────────
        # Momentum before gap day
        df['prev_1d_return']  = df['Close'].shift(1).pct_change()  * 100   # close[-2] → close[-1]
        df['prev_5d_return']  = df['Close'].shift(1).pct_change(5) * 100   # 5-day momentum
        df['prev_10d_return'] = df['Close'].shift(1).pct_change(10)* 100

        # Intraday range (proxy for uncertainty/volatility on gap day)
        df['intraday_range']  = (df['High'] - df['Low']) / df['Open'] * 100

        # Gap fill ratio: 0 = held exactly at open, 1 = extended full gap, negative = filled
        gap_size = df['Open'] - df['prev_close']
        df['gap_fill_ratio']  = np.where(
            gap_size.abs() > 0,
            (df['Close'] - df['Open']) / gap_size.abs(),
            np.nan
        )

        # Volume vs prev day
        df['vol_vs_prev']     = df['Volume'] / df['Volume'].shift(1)

        # ATR 14 (normalized volatility context)
        tr = pd.concat([
            df['High'] - df['Low'],
            (df['High'] - df['prev_close']).abs(),
            (df['Low']  - df['prev_close']).abs(),
        ], axis=1).max(axis=1)
        df['atr_pct']         = tr.rolling(14).mean().shift(1) / df['prev_close'] * 100

        # Date features
        df['dow']   = df.index.dayofweek  # 0=Mon
        df['month'] = df.index.month

        # Targets
        df['eod_positive']  = (df['eod_return'] > 0).astype(int)
        df['gap_held']      = (df['Close'] > df['prev_close']).astype(int)  # still above prev close
        df['gap_extended']  = (df['Close'] >= df['Open']).astype(int)       # close >= open
        df['up_first']      = (df['high_pct'] > df['low_pct'].abs()).astype(int)

        # Pre-screen
        df = df.dropna(subset=['open_gap_pct','volume_ratio','eod_return',
                                'prev_1d_return','prev_5d_return','atr_pct'])
        df = df[df['open_gap_pct'] >= MIN_GAP_SCREEN]
        if df.empty:
            return []

        # Merge SPY by date
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
                # Features
                'open_gap_pct':    round(float(row['open_gap_pct']),    2),
                'volume_ratio':    round(float(row['volume_ratio']),    2),
                'prev_1d_return':  round(float(row['prev_1d_return']),  2),
                'prev_5d_return':  round(float(row['prev_5d_return']),  2),
                'prev_10d_return': round(float(row['prev_10d_return']), 2),
                'intraday_range':  round(float(row['intraday_range']),  2),
                'gap_fill_ratio':  round(float(row['gap_fill_ratio']),  3) if pd.notna(row['gap_fill_ratio']) else np.nan,
                'vol_vs_prev':     round(float(row['vol_vs_prev']),     2) if pd.notna(row['vol_vs_prev']) else np.nan,
                'atr_pct':         round(float(row['atr_pct']),         2),
                'dow':             int(row['dow']),
                'month':           int(row['month']),
                'spy_return':      round(float(row['spy_return']), 2)  if pd.notna(row['spy_return']) else np.nan,
                # Intraday
                'high_pct':        round(float(row['high_pct']),       2),
                'low_pct':         round(float(row['low_pct']),        2),
                # Targets
                'eod_return':      round(float(row['eod_return']),     2),
                'eod_positive':    int(row['eod_positive']),
                'gap_held':        int(row['gap_held']),
                'gap_extended':    int(row['gap_extended']),
                'up_first':        int(row['up_first']),
            })
        return records
    except Exception as e:
        logger.debug(f"{symbol}: {e}")
        return []


def pearson_table(df, features, target_col):
    """Pearson correlation + p-value for continuous target"""
    rows = []
    for f in features:
        col = df[[f, target_col]].dropna()
        if len(col) < 20:
            continue
        r, p = scipy_stats.pearsonr(col[f], col[target_col])
        rows.append({'feature': f, 'pearson_r': round(r, 4), 'p_value': round(p, 4),
                     'abs_r': round(abs(r), 4), 'n': len(col)})
    return pd.DataFrame(rows).sort_values('abs_r', ascending=False)


def point_biserial_table(df, features, binary_target):
    """Point-biserial correlation for binary target"""
    rows = []
    for f in features:
        col = df[[f, binary_target]].dropna()
        if len(col) < 20:
            continue
        r, p = scipy_stats.pointbiserialr(col[binary_target], col[f])
        rows.append({'feature': f, 'pb_r': round(r, 4), 'p_value': round(p, 4),
                     'abs_r': round(abs(r), 4), 'n': len(col)})
    return pd.DataFrame(rows).sort_values('abs_r', ascending=False)


def group_stats(df, group_col, target):
    """Mean target by group value"""
    return df.groupby(group_col)[target].agg(['mean','count','std']).round(3)


def section_correlation(df, gap_min, vol_min):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()
    n = len(sub)

    FEATURES = [
        'open_gap_pct', 'volume_ratio', 'prev_1d_return', 'prev_5d_return',
        'prev_10d_return', 'intraday_range', 'atr_pct', 'vol_vs_prev',
        'spy_return',
    ]

    print(f"\n{'='*72}")
    print(f"  SECTION 1 — Pearson Correlation vs EOD Return  (gap≥{gap_min}%, vol≥{vol_min}x, n={n})")
    print(f"  (positive r = feature สูง → eod return สูง)")
    print('='*72)
    tbl = pearson_table(sub, FEATURES, 'eod_return')
    print(tbl[['feature','pearson_r','p_value','n']].to_string(index=False))

    print(f"\n{'='*72}")
    print(f"  SECTION 2 — Point-Biserial vs Gap Held (close > prev_close)  n={n}")
    print(f"  (positive r = feature สูง → แนวโน้ม gap hold ไม่ fill)")
    print('='*72)
    tbl2 = point_biserial_table(sub, FEATURES, 'gap_held')
    print(tbl2[['feature','pb_r','p_value','n']].to_string(index=False))

    print(f"\n{'='*72}")
    print(f"  SECTION 3 — Point-Biserial vs EOD Positive (eod > 0)  n={n}")
    print('='*72)
    tbl3 = point_biserial_table(sub, FEATURES, 'eod_positive')
    print(tbl3[['feature','pb_r','p_value','n']].to_string(index=False))

    return sub


def section_bucketed(df, gap_min, vol_min):
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()

    print(f"\n{'='*72}")
    print(f"  SECTION 4 — EOR Return by Feature Buckets  (gap≥{gap_min}%, vol≥{vol_min}x)")
    print('='*72)

    # Gap size
    gap_bins   = [8, 10, 12, 15, 20, 100]
    gap_labels = ['8-10%','10-12%','12-15%','15-20%','>20%']
    sub['gap_bucket'] = pd.cut(sub['open_gap_pct'], bins=gap_bins, labels=gap_labels, right=False)
    g = sub.groupby('gap_bucket', observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
        gap_held_pct=('gap_held', lambda x: round(x.mean()*100, 1)),
    )
    print(f"\n  By Gap Size:")
    print(g.to_string())

    # Volume ratio
    vol_bins   = [0, 0.3, 0.5, 1.0, 2.0, 100]
    vol_labels = ['<0.3x','0.3-0.5x','0.5-1x','1-2x','>2x']
    sub['vol_bucket'] = pd.cut(sub['volume_ratio'], bins=vol_bins, labels=vol_labels, right=False)
    g2 = sub.groupby('vol_bucket', observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
        gap_held_pct=('gap_held', lambda x: round(x.mean()*100, 1)),
    )
    print(f"\n  By Volume Ratio:")
    print(g2.to_string())

    # Previous day return
    sub['prev1d_bucket'] = pd.cut(sub['prev_1d_return'],
        bins=[-100,-5,-2,-1,0,1,2,5,100],
        labels=['<-5%','-5to-2%','-2to-1%','-1to0%','0to1%','1to2%','2to5%','>5%'], right=False)
    g3 = sub.groupby('prev1d_bucket', observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
    )
    print(f"\n  By Prev Day Return (momentum before gap):")
    print(g3.to_string())

    # 5-day momentum
    sub['prev5d_bucket'] = pd.cut(sub['prev_5d_return'],
        bins=[-100,-10,-5,0,5,10,20,100],
        labels=['<-10%','-10to-5%','-5to0%','0to5%','5to10%','10to20%','>20%'], right=False)
    g4 = sub.groupby('prev5d_bucket', observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
    )
    print(f"\n  By 5-Day Momentum (before gap day):")
    print(g4.to_string())

    # Day of week
    dow_map = {0:'Mon',1:'Tue',2:'Wed',3:'Thu',4:'Fri'}
    sub['dow_name'] = sub['dow'].map(dow_map)
    g5 = sub.groupby('dow_name').agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
    ).reindex(['Mon','Tue','Wed','Thu','Fri'])
    print(f"\n  By Day of Week:")
    print(g5.to_string())

    # SPY return on same day
    spy_sub = sub.dropna(subset=['spy_return'])
    if len(spy_sub) > 50:
        spy_sub['spy_bucket'] = pd.cut(spy_sub['spy_return'],
            bins=[-100,-2,-1,-0.5,0,0.5,1,2,100],
            labels=['<-2%','-2to-1%','-1to-0.5%','-0.5to0%','0to0.5%','0.5to1%','1to2%','>2%'],
            right=False)
        g6 = spy_sub.groupby('spy_bucket', observed=True).agg(
            n=('eod_return','count'),
            wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
            avg=('eod_return', lambda x: round(x.mean(), 2)),
        )
        print(f"\n  By SPY Return on Same Day (market context):")
        print(g6.to_string())

    # ATR context
    sub['atr_bucket'] = pd.cut(sub['atr_pct'],
        bins=[0, 2, 3, 4, 6, 100],
        labels=['<2%','2-3%','3-4%','4-6%','>6%'], right=False)
    g7 = sub.groupby('atr_bucket', observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100, 1)),
        avg=('eod_return', lambda x: round(x.mean(), 2)),
    )
    print(f"\n  By Stock ATR (volatility context before gap):")
    print(g7.to_string())

    return sub


def section_interaction(df, gap_min, vol_min):
    """Gap × Prev Return interaction — find sweet spot combinations"""
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()

    print(f"\n{'='*72}")
    print(f"  SECTION 5 — Interaction: Gap Size × Prev Day Return")
    print('='*72)

    sub['gap_grp']  = pd.cut(sub['open_gap_pct'],
        bins=[8,12,15,100], labels=['8-12%','12-15%','>15%'], right=False)
    sub['prev_grp'] = pd.cut(sub['prev_1d_return'],
        bins=[-100,-2,0,2,100], labels=['<-2%','-2to0%','0to2%','>2%'], right=False)

    g = sub.groupby(['gap_grp','prev_grp'], observed=True).agg(
        n=('eod_return','count'),
        wr=('eod_positive', lambda x: round(x.mean()*100,1)),
        avg=('eod_return', lambda x: round(x.mean(),2)),
    ).reset_index()
    g = g[g['n'] >= 5]
    print(g.to_string(index=False))

    print(f"\n{'='*72}")
    print(f"  SECTION 6 — Interaction: Gap Size × SPY Return")
    print('='*72)
    spy_sub = sub.dropna(subset=['spy_return'])
    if len(spy_sub) >= 50:
        spy_sub['spy_grp'] = pd.cut(spy_sub['spy_return'],
            bins=[-100,-0.5,0,0.5,100], labels=['Bear(<-0.5%)','Flat(-0.5-0%)','Flat(0-0.5%)','Bull(>0.5%)'],
            right=False)
        g2 = spy_sub.groupby(['gap_grp','spy_grp'], observed=True).agg(
            n=('eod_return','count'),
            wr=('eod_positive', lambda x: round(x.mean()*100,1)),
            avg=('eod_return', lambda x: round(x.mean(),2)),
        ).reset_index()
        g2 = g2[g2['n'] >= 5]
        print(g2.to_string(index=False))


def section_feature_ranking(df, gap_min, vol_min):
    """Simple logistic regression feature importance proxy"""
    sub = df[(df['open_gap_pct'] >= gap_min) & (df['volume_ratio'] >= vol_min)].copy()

    FEATURES = [
        'open_gap_pct', 'volume_ratio', 'prev_1d_return', 'prev_5d_return',
        'atr_pct', 'intraday_range', 'vol_vs_prev', 'spy_return',
        'dow', 'month'
    ]

    print(f"\n{'='*72}")
    print(f"  SECTION 7 — Feature Ranking Summary (|pearson r| vs eod_return)")
    print(f"  (combined correlation ranking for key features, gap≥{gap_min}%)")
    print('='*72)

    results = []
    for f in FEATURES:
        col = sub[[f, 'eod_return', 'eod_positive', 'gap_held']].dropna()
        if len(col) < 20:
            continue
        r_cont, p_cont    = scipy_stats.pearsonr(col[f], col['eod_return'])
        r_bin,  p_bin     = scipy_stats.pointbiserialr(col['eod_positive'], col[f])
        r_held, p_held    = scipy_stats.pointbiserialr(col['gap_held'], col[f])

        significance = '***' if p_cont < 0.001 else ('**' if p_cont < 0.01 else ('*' if p_cont < 0.05 else ''))
        results.append({
            'feature':        f,
            'r_vs_return':    round(r_cont, 4),
            'r_vs_wr':        round(r_bin,  4),
            'r_vs_gap_held':  round(r_held, 4),
            'p_value':        round(p_cont, 4),
            'sig':            significance,
            'n':              len(col),
        })

    results.sort(key=lambda x: abs(x['r_vs_return']), reverse=True)
    out = pd.DataFrame(results)
    print(out[['feature','r_vs_return','r_vs_wr','r_vs_gap_held','p_value','sig','n']].to_string(index=False))

    print(f"\n  Legend: sig * p<0.05  ** p<0.01  *** p<0.001")
    print(f"  r_vs_return: correlation vs eod_return (continuous)")
    print(f"  r_vs_wr:     correlation vs eod>0 (binary win rate)")
    print(f"  r_vs_gap_held: correlation vs close>prev_close (gap not filled)")


def main():
    args = parse_args()
    period = f'{args.years}y'

    print(f"\n{'='*72}")
    print(f"  GAP CORRELATION ANALYSIS  |  {args.years}y  |  top {args.top} stocks")
    print(f"  Focus: gap≥{args.gap}%, vol≥{args.vol}x")
    print('='*72)

    symbols = load_universe(args.top)
    if not symbols:
        logger.error("No symbols"); return

    print("  Downloading SPY for market context...")
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
            all_records.extend(process_symbol(df_sym, sym, spy))

    print(f"\n  Total gap events (≥{MIN_GAP_SCREEN}%): {len(all_records):,}")
    if not all_records:
        logger.error("No events"); return

    df = pd.DataFrame(all_records)
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else '.', exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"  Raw data: {args.output}")

    section_correlation(df, args.gap, args.vol)
    section_bucketed(df, args.gap, args.vol)
    section_interaction(df, args.gap, args.vol)
    section_feature_ranking(df, args.gap, args.vol)

    print(f"\n{'='*72}")
    print(f"  Done. Full data: {args.output}")
    print('='*72)


if __name__ == '__main__':
    main()
