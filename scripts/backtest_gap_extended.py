#!/usr/bin/env python3
"""
GAP EXTENDED BACKTEST
======================
ต่อยอดจาก rigorous analysis เพิ่ม 5 การวิเคราะห์:

  1. VIX Regime Filter       — ทดสอบว่า VIX tier ช่วย AUC ได้จริงมั้ย
  2. ATR-based TP/SL         — dynamic exit แทน fixed % (grid ATR multipliers)
  3. Time-based Exit         — 1h, 2h, 3h, 4h, EOD ด้วย hourly data จริง
  4. Gap Quality Score       — composite score รวม vol + vix + gap tier
  5. Pre-market Vol Accel    — vol ใน 30min สุดท้ายก่อน open vs ก่อนหน้า

Data source: reuse existing CSV + download VIX + hourly bars

Usage:
  python3 scripts/backtest_gap_extended.py
  python3 scripts/backtest_gap_extended.py --refresh --years 3    # re-download 3y
  python3 scripts/backtest_gap_extended.py --timing_symbols 80   # more hourly data
"""

import sys, os, argparse, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import spearmanr, binomtest
from loguru import logger
import pytz

SLIPPAGE_PCT   = 0.10
COMMISSION_PCT = 0.05
ET = pytz.timezone('US/Eastern')


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--csv',             default='data/backtest_gap_correlations.csv')
    p.add_argument('--refresh',         action='store_true', help='Re-download daily data')
    p.add_argument('--years',           type=int, default=2)
    p.add_argument('--top',             type=int, default=500)
    p.add_argument('--timing_symbols',  type=int, default=60,  help='Max symbols for hourly timing')
    p.add_argument('--n_boot',          type=int, default=2000)
    return p.parse_args()


def sig(p):
    if p < 0.001: return '***'
    if p < 0.01:  return '**'
    if p < 0.05:  return '*'
    if p < 0.10:  return '.'
    return 'ns'


def binom_p(wins, n):
    if n < 1: return 1.0
    return binomtest(int(wins), int(n), 0.5, alternative='greater').pvalue


def bootstrap_wr(arr, n_boot=2000):
    arr = np.array(arr)
    n = len(arr)
    if n < 5: return np.nan, np.nan, np.nan
    boots = [arr[np.random.randint(0, n, n)].mean() for _ in range(n_boot)]
    return arr.mean()*100, np.percentile(boots,2.5)*100, np.percentile(boots,97.5)*100


def simulate_exit_daily(high_pct, low_pct, eod_ret, tp_pct, sl_pct):
    """Same H/L proxy as before"""
    tp_hit = high_pct >= tp_pct
    sl_hit = (-low_pct) >= sl_pct
    if tp_hit and sl_hit:
        if (-low_pct) > high_pct:
            return -sl_pct - 2*COMMISSION_PCT, 'SL'
        else:
            return tp_pct - 2*COMMISSION_PCT, 'TP'
    elif tp_hit:
        return tp_pct - 2*COMMISSION_PCT, 'TP'
    elif sl_hit:
        return -sl_pct - 2*COMMISSION_PCT, 'SL'
    return eod_ret, 'EOD'


# ─── Download helpers ──────────────────────────────────────────────────────────

def download_vix(period='2y'):
    try:
        df = yf.download('^VIX', period=period, interval='1d',
                         progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index).normalize()
        df.index = df.index.tz_localize(None) if df.index.tz else df.index
        df['vix'] = df['Close']
        return df[['vix']]
    except Exception as e:
        logger.warning(f"VIX download: {e}"); return None


def download_hourly(symbol, period='2y'):
    try:
        df = yf.download(symbol, period=period, interval='1h',
                         auto_adjust=True, progress=False, prepost=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty: return None
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(ET)
        else:
            df.index = df.index.tz_convert(ET)
        return df
    except Exception as e:
        logger.debug(f"{symbol} hourly: {e}"); return None


def download_hourly_prepost(symbol, period='2y'):
    """Pre-market volume acceleration"""
    try:
        df = yf.download(symbol, period=period, interval='1h',
                         auto_adjust=True, progress=False, prepost=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty: return None
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(ET)
        else:
            df.index = df.index.tz_convert(ET)
        return df
    except Exception as e:
        logger.debug(f"{symbol} prepost: {e}"); return None


# ─── SECTION 1: VIX Regime Filter ─────────────────────────────────────────────

def section_vix_regime(df, vix_df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 1 — VIX Regime Filter")
    print(f"  H0: WR ไม่ขึ้นกับ VIX tier | ทดสอบด้วย bootstrap CI + binomial p")
    print('='*72)

    # Merge VIX
    df = df.copy()
    df['date_norm'] = pd.to_datetime(df['date']).dt.normalize()
    df['date_norm'] = df['date_norm'].dt.tz_localize(None) if df['date_norm'].dt.tz else df['date_norm']
    vix_reset = vix_df.reset_index()
    vix_reset.columns = ['date_norm', 'vix']
    vix_reset['date_norm'] = pd.to_datetime(vix_reset['date_norm']).dt.normalize()
    vix_reset['date_norm'] = vix_reset['date_norm'].dt.tz_localize(None) if vix_reset['date_norm'].dt.tz else vix_reset['date_norm']
    merged = df.merge(vix_reset, on='date_norm', how='left')

    n_with_vix = merged['vix'].notna().sum()
    print(f"\n  Events with VIX data: {n_with_vix}/{len(merged)}")

    vix_bins   = [0,  15,  20,  25,  30,  100]
    vix_labels = ['<15','15-20','20-25','25-30','>30']
    merged['vix_tier'] = pd.cut(merged['vix'], bins=vix_bins,
                                labels=vix_labels, right=False)

    print(f"\n  {'VIX tier':<12} {'n':>5} {'WR%':>6} {'95% CI':>18} {'avg':>7} {'sig'}")
    print(f"  {'-'*60}")

    regime_results = {}
    for tier in vix_labels:
        sub = merged[merged['vix_tier'] == tier]
        if len(sub) < 5:
            print(f"  {tier:<12} {len(sub):>5}  (too few)")
            continue
        wr, lo, hi = bootstrap_wr(sub['eod_positive'].values, n_boot)
        avg = sub['eod_return'].mean()
        p   = binom_p(sub['eod_positive'].sum(), len(sub))
        above = '✓' if lo > 50 else ' '
        print(f"  {tier:<12} {len(sub):>5} {wr:>6.1f} [{lo:>5.1f}%-{hi:>5.1f}%] {above} {avg:>+7.2f} {sig(p)}")
        regime_results[tier] = {'n':len(sub),'wr':wr,'lo':lo,'hi':hi,'avg':avg,'p':p}

    # Interaction: VIX × volume_ratio
    print(f"\n  VIX × vol_ratio≥2x (ตัวกรองที่ robust ที่สุด):")
    print(f"  {'VIX tier':<12} {'n':>5} {'WR%':>6} {'CI lo':>7} {'avg':>7}")
    for tier in vix_labels:
        sub = merged[(merged['vix_tier'] == tier) & (merged['volume_ratio'] >= 2.0)]
        if len(sub) < 5:
            continue
        wr, lo, hi = bootstrap_wr(sub['eod_positive'].values, n_boot)
        avg = sub['eod_return'].mean()
        print(f"  {tier:<12} {len(sub):>5} {wr:>6.1f} {lo:>+7.1f}%   {avg:>+7.2f}")

    # Spearman IC between VIX and eod_return
    vix_sub = merged.dropna(subset=['vix','eod_return'])
    r, p_r = spearmanr(vix_sub['vix'], vix_sub['eod_return'])
    print(f"\n  Spearman IC (VIX vs eod_return): r={r:.4f} p={p_r:.4f} {sig(p_r)}")
    print(f"  {'negative r = higher VIX → worse return' if r < 0 else 'positive r = higher VIX → better return'}")

    return merged


# ─── SECTION 2: ATR-based TP/SL ───────────────────────────────────────────────

def section_atr_exit(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 2 — ATR-based TP/SL vs Fixed % (vol≥2x filter)")
    print(f"  TP = entry + ATR×tp_mult  |  SL = entry - ATR×sl_mult")
    print('='*72)

    sub = df[(df['volume_ratio'] >= 2.0) & df['atr_pct'].notna()].copy()
    print(f"\n  n (vol≥2x with ATR): {len(sub)}")

    TP_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
    SL_MULTS = [0.3, 0.5, 0.75, 1.0]

    # Baseline fixed TP5+SL2 (best from v2.0)
    fixed_rets = sub.apply(
        lambda r: simulate_exit_daily(r['high_pct'], r['low_pct'], r['eod_return'], 5.0, 2.0)[0],
        axis=1
    )
    fixed_wr = (fixed_rets > 0).mean() * 100
    fixed_avg = fixed_rets.mean()
    print(f"\n  Baseline (fixed TP5%+SL2%): WR={fixed_wr:.1f}% avg={fixed_avg:+.2f}%")

    # ATR-based grid
    results = []
    for tp_m in TP_MULTS:
        for sl_m in SL_MULTS:
            def calc(row, tp_m=tp_m, sl_m=sl_m):
                tp_pct = row['atr_pct'] * tp_m
                sl_pct = row['atr_pct'] * sl_m
                return simulate_exit_daily(row['high_pct'], row['low_pct'],
                                           row['eod_return'], tp_pct, sl_pct)[0]
            rets = sub.apply(calc, axis=1)
            wr   = (rets > 0).mean() * 100
            avg  = rets.mean()
            med  = rets.median()
            std  = rets.std()
            sh   = (avg / std * np.sqrt(252)) if std > 0 else 0
            _, lo, hi = bootstrap_wr((rets > 0).values, n_boot)
            p    = binom_p((rets > 0).sum(), len(rets))
            results.append({
                'tp_mult': tp_m, 'sl_mult': sl_m,
                'wr': round(wr, 1), 'avg': round(avg, 2),
                'median': round(med, 2), 'sharpe': round(sh, 2),
                'ci_lo': round(lo, 1), 'ci_hi': round(hi, 1), 'p': p,
                'above_baseline_wr': wr > fixed_wr,
            })

    results.sort(key=lambda x: -x['sharpe'])

    print(f"\n  ATR-based grid (sorted by Sharpe):")
    print(f"  {'TP_mult':>7} {'SL_mult':>7} {'WR%':>6} {'95% CI':>16} {'avg':>7} {'sharpe':>8} {'sig':>5}")
    print(f"  {'-'*68}")
    for r in results:
        above = '↑' if r['above_baseline_wr'] else ' '
        print(f"  {r['tp_mult']:>7.1f}x {r['sl_mult']:>7.2f}x {r['wr']:>6.1f} "
              f"[{r['ci_lo']:>5.1f}-{r['ci_hi']:>5.1f}%] {r['avg']:>+7.2f} "
              f"{r['sharpe']:>8.2f} {sig(r['p']):>5} {above}")

    best = results[0]
    print(f"\n  Best ATR config: TP={best['tp_mult']}x ATR, SL={best['sl_mult']}x ATR")
    print(f"  vs Fixed TP5%+SL2%: Δsharpe = {best['sharpe'] - (fixed_avg/fixed_rets.std()*16.0):.2f}")

    # ATR distribution of gap events
    print(f"\n  ATR distribution (vol≥2x gap events):")
    print(f"  mean ATR={sub['atr_pct'].mean():.2f}%  median={sub['atr_pct'].median():.2f}%  "
          f"p25={sub['atr_pct'].quantile(0.25):.2f}%  p75={sub['atr_pct'].quantile(0.75):.2f}%")
    print(f"  → At TP=1.5x ATR, median stock: TP={sub['atr_pct'].median()*1.5:.2f}%  SL={sub['atr_pct'].median()*0.5:.2f}%")

    return results


# ─── SECTION 3: Time-based Exit (hourly) ──────────────────────────────────────

def section_time_exit(df, n_symbols, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 3 — Time-based Exit Analysis (hourly bars, T+1h/2h/3h/4h/EOD)")
    print(f"  Filter: vol≥2x (the only robust feature)")
    print('='*72)

    filtered = df[df['volume_ratio'] >= 2.0].copy()
    filtered['date_str'] = filtered['date'].astype(str).str[:10]

    sym_counts = filtered['symbol'].value_counts()
    top_syms   = sym_counts.head(n_symbols).index.tolist()
    print(f"\n  Gap events (vol≥2x): {len(filtered)} | Symbols: {filtered['symbol'].nunique()}")
    print(f"  Downloading hourly bars for {len(top_syms)} symbols...")

    all_timing = []
    for i, sym in enumerate(top_syms):
        df_h = download_hourly(sym)
        if df_h is None:
            continue
        sym_events = filtered[filtered['symbol'] == sym]

        for _, evt in sym_events.iterrows():
            try:
                evt_date = pd.to_datetime(evt['date_str']).date()
                day_bars = df_h[df_h.index.date == evt_date]
                if len(day_bars) < 3:
                    continue

                open_bar = day_bars[day_bars.index.hour == 9]
                if open_bar.empty:
                    continue
                open_price = float(open_bar.iloc[0]['Open'])
                eod_close  = float(day_bars.iloc[-1]['Close'])
                if open_price <= 0:
                    continue

                rec = {
                    'symbol': sym, 'date': evt['date_str'],
                    'open_gap_pct': evt['open_gap_pct'],
                    'volume_ratio': evt['volume_ratio'],
                    'atr_pct': evt.get('atr_pct', np.nan),
                    'eod_ret_baseline': round(
                        (eod_close * (1-SLIPPAGE_PCT/100) - open_price * (1+SLIPPAGE_PCT/100))
                        / (open_price * (1+SLIPPAGE_PCT/100)) * 100 - 2*COMMISSION_PCT, 2),
                }

                # Time stops: exit at each hour bar close
                entry_price = open_price * (1 + SLIPPAGE_PCT/100)
                for h, label in [(9,'T+0h'),(10,'T+1h'),(11,'T+2h'),(12,'T+3h'),(13,'T+4h')]:
                    bar = day_bars[day_bars.index.hour == h]
                    if bar.empty:
                        rec[f'ret_{label}'] = np.nan
                        rec[f'hold_{label}'] = np.nan
                        continue
                    bar_close = float(bar.iloc[0]['Close'])
                    exit_p = bar_close * (1 - SLIPPAGE_PCT/100)
                    ret = (exit_p - entry_price) / entry_price * 100 - 2*COMMISSION_PCT
                    # gap hold: price still ≥ open × 0.99
                    rec[f'ret_{label}']  = round(ret, 2)
                    rec[f'hold_{label}'] = int(bar_close >= open_price * 0.99)

                # Time stop: exit at first bar where price < open × (1 - SL%)
                # with SL = atr × 0.5 or fixed 2%
                sl_pct = evt.get('atr_pct', 4.0) * 0.5  # ATR-based SL
                sl_price = open_price * (1 - sl_pct/100)
                time_stopped = False
                for bar_ts, bar_row in day_bars.iterrows():
                    if float(bar_row['Low']) <= sl_price:
                        exit_p_ts = sl_price * (1 - SLIPPAGE_PCT/100)
                        rec['ret_timestop'] = round(
                            (exit_p_ts - entry_price) / entry_price * 100 - 2*COMMISSION_PCT, 2)
                        time_stopped = True
                        break
                if not time_stopped:
                    rec['ret_timestop'] = rec['eod_ret_baseline']

                all_timing.append(rec)
            except Exception:
                continue

        if (i+1) % 10 == 0:
            print(f"    {i+1}/{len(top_syms)} symbols, {len(all_timing)} events", end='\r')

    print(f"\n  Total timing records: {len(all_timing)}")
    if not all_timing:
        print("  No hourly data — skip timing analysis"); return pd.DataFrame()

    tdf = pd.DataFrame(all_timing)

    print(f"\n  {'Exit Time':<14} {'n':>5} {'WR%':>6} {'95% CI':>18} {'avg':>8}  description")
    print(f"  {'-'*70}")

    for label, desc in [
        ('T+0h',     'Sell at 10:00 bar close (first 1h holds)'),
        ('T+1h',     'Sell at 11:00 bar close (hold 2h)'),
        ('T+2h',     'Sell at 12:00 bar close (hold 3h)'),
        ('T+3h',     'Sell at 13:00 bar close (hold 4h)'),
        ('T+4h',     'Sell at 14:00 bar close (hold 5h)'),
        ('eod_ret_baseline', 'Sell at EOD close (baseline)'),
        ('ret_timestop', f'ATR time-stop (SL=0.5×ATR)'),
    ]:
        col = label if label.startswith('ret_') or label == 'eod_ret_baseline' else f'ret_{label}'
        if col not in tdf.columns:
            continue
        sub = tdf.dropna(subset=[col])
        if len(sub) < 5:
            continue
        wins = (sub[col] > 0).astype(int)
        wr, lo, hi = bootstrap_wr(wins.values, n_boot)
        avg = sub[col].mean()
        p   = binom_p(wins.sum(), len(sub))
        above = '✓' if lo > 50 else ' '
        print(f"  {label:<14} {len(sub):>5} {wr:>6.1f} [{lo:>5.1f}%-{hi:>5.1f}%] {above} {avg:>+8.2f}  {desc}")

    # Gap-hold filter at each time point
    print(f"\n  + Gap-hold filter (ราคา ≥ open×0.99 ณ เวลานั้น):")
    print(f"  {'Exit Time':<14} {'n_filtered':>10} {'WR%':>6} {'avg':>8}  Δ vs no-filter")
    for label in ['T+0h','T+1h','T+2h']:
        col_ret  = f'ret_{label}'
        col_hold = f'hold_{label}'
        if col_ret not in tdf.columns or col_hold not in tdf.columns:
            continue
        sub_all  = tdf.dropna(subset=[col_ret])
        sub_held = sub_all[sub_all[col_hold] == 1]
        if len(sub_held) < 5:
            continue
        wr_all  = (sub_all[col_ret]  > 0).mean() * 100
        wr_held = (sub_held[col_ret] > 0).mean() * 100
        avg_held = sub_held[col_ret].mean()
        pct_kept = len(sub_held)/len(sub_all)*100
        print(f"  {label:<14} {len(sub_held):>5}/{len(sub_all):<5} ({pct_kept:.0f}%) "
              f"{wr_held:>6.1f} {avg_held:>+8.2f}  Δ={wr_held-wr_all:+.1f}pp")

    return tdf


# ─── SECTION 4: Gap Quality Composite Score ───────────────────────────────────

def section_gap_quality(df, vix_merged, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 4 — Gap Quality Composite Score")
    print(f"  รวม features → score แล้ว backtest แต่ละ threshold")
    print('='*72)

    df2 = vix_merged.copy() if 'vix' in vix_merged.columns else df.copy()

    # Normalize each component to [0, 1]
    # volume_ratio: 0=0x, 1=≥4x
    df2['vol_score']  = np.clip(df2['volume_ratio'] / 4.0, 0, 1)

    # gap_size: 0=8%, 0.5=15%, 1.0=20%
    df2['gap_score']  = np.clip((df2['open_gap_pct'] - 8) / 12, 0, 1)

    # VIX: 1=<15, 0=≥30 (lower VIX = better)
    if 'vix' in df2.columns:
        df2['vix_score'] = np.clip(1 - (df2['vix'] - 15) / 15, 0, 1)
    else:
        df2['vix_score'] = 0.5  # neutral

    # prev_1d: 1=down day, 0=up ≥5%
    df2['prev_score'] = np.clip(1 - (df2['prev_1d_return'] + 5) / 10, 0, 1)

    # Composite (weights based on statistical significance from Section B)
    # vol=0.60 (only significant IC), gap=0.20 (OOS evidence), vix=0.15, prev=0.05
    df2['gap_quality'] = (
        df2['vol_score']  * 0.60 +
        df2['gap_score']  * 0.20 +
        df2['vix_score']  * 0.15 +
        df2['prev_score'] * 0.05
    ).round(3)

    print(f"\n  Score distribution:")
    for bucket in [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)]:
        sub = df2[(df2['gap_quality'] >= bucket[0]) & (df2['gap_quality'] < bucket[1])]
        if len(sub) < 3:
            continue
        wr, lo, hi = bootstrap_wr(sub['eod_positive'].values, n_boot)
        avg = sub['eod_return'].mean()
        p   = binom_p(sub['eod_positive'].sum(), len(sub))
        above = '✓' if lo > 50 else ' '
        print(f"  score {bucket[0]:.1f}-{bucket[1]:.1f}:  n={len(sub):>4}  "
              f"WR={wr:.1f}% [{lo:.1f}-{hi:.1f}%] {above}  avg={avg:+.2f}%  {sig(p)}")

    # Decile analysis on composite score
    df2['score_decile'] = pd.qcut(df2['gap_quality'], 10, labels=False, duplicates='drop')
    d = df2.groupby('score_decile').agg(
        n=('eod_positive','count'),
        wr=('eod_positive', lambda x: x.mean()*100),
        avg=('eod_return','mean')
    ).round(2)
    r_mono, p_mono = spearmanr(d.index, d['wr'])
    print(f"\n  Decile monotonicity of composite score: r={r_mono:.3f} p={p_mono:.4f} {sig(p_mono)}")
    print(f"  Bottom decile WR={d['wr'].iloc[0]:.1f}%  Top decile WR={d['wr'].iloc[-1]:.1f}%")
    print(f"  Spread = {d['wr'].iloc[-1] - d['wr'].iloc[0]:.1f} pp  "
          f"(larger = score ทำงาน)")


# ─── SECTION 5: Pre-market Volume Acceleration ────────────────────────────────

def section_vol_acceleration(df, n_symbols, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 5 — Pre-market Volume Acceleration")
    print(f"  vol_accel = pre-market vol ใน 30min ก่อน open / 60min ก่อนหน้า")
    print(f"  H0: vol_accel ไม่สัมพันธ์กับ eod_return")
    print('='*72)

    filtered = df[df['volume_ratio'] >= 2.0].copy()
    filtered['date_str'] = filtered['date'].astype(str).str[:10]

    sym_counts = filtered['symbol'].value_counts()
    top_syms   = sym_counts.head(n_symbols).index.tolist()
    print(f"\n  Downloading pre-market hourly (prepost=True) for {len(top_syms)} symbols...")

    accel_records = []
    for i, sym in enumerate(top_syms):
        df_h = download_hourly_prepost(sym)
        if df_h is None:
            continue
        sym_events = filtered[filtered['symbol'] == sym]

        for _, evt in sym_events.iterrows():
            try:
                evt_date = pd.to_datetime(evt['date_str']).date()
                day_bars = df_h[df_h.index.date == evt_date]
                if len(day_bars) < 3:
                    continue

                # Pre-market bars: before 9:30 ET (hour 4-8)
                pm_bars = day_bars[day_bars.index.hour < 9]
                if len(pm_bars) < 2:
                    continue

                # Last 1 bar before open (8:00-9:00 ET, roughly 30-60min)
                last_bar_vol  = float(pm_bars.iloc[-1]['Volume']) if len(pm_bars) >= 1 else 0
                # Earlier bars (everything before last bar)
                early_vol_sum = float(pm_bars.iloc[:-1]['Volume'].sum()) if len(pm_bars) > 1 else 0
                n_early = len(pm_bars) - 1

                if early_vol_sum <= 0 or n_early == 0:
                    continue

                # Acceleration = last bar vol vs avg of earlier bars
                avg_early_vol = early_vol_sum / n_early
                vol_accel = last_bar_vol / avg_early_vol if avg_early_vol > 0 else np.nan

                accel_records.append({
                    'symbol':       sym,
                    'date':         evt['date_str'],
                    'open_gap_pct': evt['open_gap_pct'],
                    'volume_ratio': evt['volume_ratio'],
                    'eod_return':   evt['eod_return'],
                    'eod_positive': evt['eod_positive'],
                    'vol_accel':    round(vol_accel, 3) if not np.isnan(vol_accel) else np.nan,
                    'last_bar_vol': last_bar_vol,
                    'avg_early_vol':avg_early_vol,
                })
            except Exception:
                continue

        if (i+1) % 10 == 0:
            print(f"    {i+1}/{len(top_syms)} symbols, {len(accel_records)} records", end='\r')

    print(f"\n  Records with vol_accel data: {len(accel_records)}")
    if not accel_records:
        print("  No pre-market data available"); return

    adf = pd.DataFrame(accel_records).dropna(subset=['vol_accel'])
    adf = adf[adf['vol_accel'].between(0.01, 100)]  # remove outliers

    # IC test
    r, p_r = spearmanr(adf['vol_accel'], adf['eod_return'])
    print(f"\n  Spearman IC (vol_accel vs eod_return): r={r:.4f} p={p_r:.4f} {sig(p_r)}")

    # Decile breakdown
    try:
        adf['accel_decile'] = pd.qcut(adf['vol_accel'], 5, labels=False, duplicates='drop')
        d = adf.groupby('accel_decile').agg(
            n=('eod_positive','count'),
            wr=('eod_positive', lambda x: x.mean()*100),
            avg=('eod_return','mean'),
            accel_mean=('vol_accel','mean'),
        ).round(2)
        r_mono, p_mono = spearmanr(d.index, d['wr'])
        print(f"  Decile monotonicity: r={r_mono:.3f} p={p_mono:.4f} {sig(p_mono)}")
        print(f"\n  {'Quintile':>9} {'n':>5} {'WR%':>6} {'avg':>8} {'accel_mean':>11}")
        for idx, row in d.iterrows():
            print(f"  {idx:>9} {int(row['n']):>5} {row['wr']:>6.1f} {row['avg']:>+8.2f} {row['accel_mean']:>11.2f}x")
    except Exception as e:
        print(f"  Decile analysis error: {e}")

    accel_bins   = [0, 0.5, 1.0, 1.5, 2.0, 100]
    accel_labels = ['<0.5x','0.5-1x','1-1.5x','1.5-2x','>2x']
    adf['accel_bucket'] = pd.cut(adf['vol_accel'], bins=accel_bins,
                                 labels=accel_labels, right=False)
    print(f"\n  By vol_accel bucket:")
    print(f"  {'Bucket':>8} {'n':>5} {'WR%':>6} {'avg':>8}")
    for b in accel_labels:
        s = adf[adf['accel_bucket'] == b]
        if len(s) < 3:
            continue
        print(f"  {b:>8} {len(s):>5} {s['eod_positive'].mean()*100:>6.1f} "
              f"{s['eod_return'].mean():>+8.2f}")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print(f"\n{'='*72}")
    print(f"  GAP EXTENDED BACKTEST")
    print(f"  VIX regime | ATR exit | Time stop | Quality score | Vol accel")
    print('='*72)

    # Load data
    df = pd.read_csv(args.csv, parse_dates=['date'])
    df = df[df['open_gap_pct'] >= 8.0].copy()
    df = df.dropna(subset=['open_gap_pct','volume_ratio','eod_return','eod_positive'])
    print(f"\n  Loaded: {len(df)} gap events from {args.csv}")

    # Download VIX
    print("  Downloading VIX...")
    period = f'{args.years}y'
    vix_df = download_vix(period)
    if vix_df is not None:
        print(f"  VIX data: {len(vix_df)} days")
    else:
        print("  VIX not available")

    # Run sections
    vix_merged = section_vix_regime(df, vix_df if vix_df is not None else pd.DataFrame(), args.n_boot)
    section_atr_exit(df, args.n_boot)
    section_time_exit(df, args.timing_symbols, args.n_boot)
    section_gap_quality(df, vix_merged, args.n_boot)
    section_vol_acceleration(df, args.timing_symbols // 2, args.n_boot)

    print(f"\n{'='*72}")
    print(f"  SYNTHESIS — สรุปทั้ง 5 การวิเคราะห์")
    print('='*72)
    print(f"""
  Feature ranking (จากทุก test รวมกัน):
  ══════════════════════════════════════════════════════════
  TIER 1 — มีหลักฐานแน่นทุก test:
    volume_ratio ≥ 2x    IC***, decile r=0.924***, MW***

  TIER 2 — มีหลักฐานบางส่วน (OOS n เล็ก):
    VIX < 20             ถ้า VIX IC significant → ใช้ได้
    gap 15-20%           OOS WR=72% แต่ n=29
    ATR-based TP/SL      ถ้า sharpe ดีกว่า fixed → เปลี่ยน

  TIER 3 — ยังไม่พิสูจน์ได้:
    vol_acceleration     ถ้า IC significant → เพิ่ม feature
    prev_1d / prev_5d    ไม่ significant ใน MW/IC
    day of week          ไม่ significant หลัง correction

  Live strategy recommendation:
    ✓ เพิ่ม volume_ratio ≥ 2x (จาก 0.3x) — มีหลักฐานชัด
    ✓ เพิ่ม VIX tier logic ถ้า Section 1 significant
    ✓ เปลี่ยน TP/SL เป็น ATR-based ถ้า sharpe ดีกว่า
    ✓ Time stop: ออกถ้าราคา < open×(1-0.5×ATR) ภายใน day
""")


if __name__ == '__main__':
    main()
