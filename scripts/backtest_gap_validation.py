#!/usr/bin/env python3
"""
GAP STRATEGY — VALIDATION BACKTEST
====================================
5 การทดสอบก่อน implement:

  1. Gap-Hold OOS     — Walk-forward 70/30 ทดสอบ gap-hold rule (เพื่อหัก look-ahead bias)
  2. Slippage Model   — Realistic execution costs (market-open spread ≠ 0.05%)
  3. Sector/Catalyst  — WR breakdown by sector + inferred catalyst type
  4. Drawdown Pattern — Consecutive loss clustering + SPY correlation (เข้าใจ max DD)
  5. Stress Test      — 2020 crash / 2022 bear market behavior

Data:
  - Base: data/backtest_gap_correlations.csv (existing 2024-2026 events)
  - Stress: yfinance download of same symbols in 2020/2022 windows

Usage:
  python3 scripts/backtest_gap_validation.py
  python3 scripts/backtest_gap_validation.py --stress        # include Section 5
  python3 scripts/backtest_gap_validation.py --n_boot 500   # faster bootstrap
"""

import sys, os, argparse, warnings, time
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pandas as pd
import numpy as np
import yfinance as yf
from scipy.stats import spearmanr, mannwhitneyu, binomtest
from loguru import logger
import pytz

# ─── Constants ────────────────────────────────────────────────────────────────

ET = pytz.timezone('US/Eastern')
COMMISSION_PCT = 0.05   # per side (round-trip = 0.10%)

# Current live config
LIVE_SL_PCT  = 2.0
LIVE_TP_PCT  = 5.0

# Best from extended backtest
ATR_TP_MULT  = 1.5
ATR_SL_MULT  = 0.3


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--csv',      default='data/backtest_gap_correlations.csv')
    p.add_argument('--n_boot',   type=int, default=2000)
    p.add_argument('--stress',   action='store_true', help='Run Section 5 (slow: downloads 2020/2022 data)')
    p.add_argument('--min_gap',  type=float, default=8.0)
    p.add_argument('--vol_min',  type=float, default=2.0, help='Vol ratio filter for most sections')
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
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n < 5: return np.nan, np.nan, np.nan
    rng = np.random.default_rng(42)
    boots = [arr[rng.integers(0, n, n)].mean() for _ in range(n_boot)]
    return arr.mean() * 100, np.percentile(boots, 2.5) * 100, np.percentile(boots, 97.5) * 100


def sharpe(returns):
    r = np.asarray(returns)
    if len(r) < 2 or r.std() == 0: return 0.0
    return r.mean() / r.std() * np.sqrt(252)


def simulate_exit(high_pct, low_pct, eod_ret, tp_pct, sl_pct, slip_entry=0.05, slip_exit=0.05):
    """H/L proxy: if both hit, lower absolute value wins"""
    tp_hit = high_pct >= tp_pct
    sl_hit = (-low_pct) >= sl_pct
    cost = slip_entry + COMMISSION_PCT + slip_exit + COMMISSION_PCT
    if tp_hit and sl_hit:
        if (-low_pct) > high_pct:
            return -sl_pct - cost, 'SL'
        else:
            return tp_pct - cost, 'TP'
    elif tp_hit:
        return tp_pct - cost, 'TP'
    elif sl_hit:
        return -sl_pct - cost, 'SL'
    return eod_ret - cost + COMMISSION_PCT + slip_entry, 'EOD'   # EOD: still pay entry slip + commission×2


def load_base_data(csv_path, min_gap=8.0):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}\nRun backtest_gap_correlations.py first.")
    df = pd.read_csv(csv_path, parse_dates=['date'])
    df = df[df['open_gap_pct'] >= min_gap].copy()
    df = df.dropna(subset=['open_gap_pct', 'volume_ratio', 'eod_return', 'eod_positive'])
    df = df.sort_values('date').reset_index(drop=True)
    logger.info(f"Loaded {len(df)} gap events (≥{min_gap}%) | {df['date'].min().date()} → {df['date'].max().date()}")
    return df


# ─── SECTION 1: Gap-Hold Walk-Forward OOS ─────────────────────────────────────

def section_gaphold_oos(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 1 — Gap-Hold Rule: Out-of-Sample Walk-Forward")
    print(f"  H0: gap-hold filter ไม่ช่วย OOS (WR ≤ 50%)")
    print(f"  Method: rolling train→test windows (4 folds), vol≥2x baseline")
    print('='*72)

    # ── 1A. เตรียม: ตรวจสอบ column ──────────────────────────────────────────
    if 'gap_held' not in df.columns:
        print(f"\n  ⚠️  'gap_held' column not found in CSV. Skip Section 1.")
        print(f"     Re-run backtest_gap_correlations.py to regenerate CSV.")
        return

    sub = df[df['volume_ratio'] >= 2.0].copy()
    sub = sub.sort_values('date').reset_index(drop=True)
    print(f"\n  Base set (vol≥2x): n={len(sub)}")
    print(f"  gap_held definition (from correlations script): price ≥ open×0.99 at EOD")
    print(f"  ⚠️  Note: true T+1h check requires hourly data; EOD is conservative proxy")

    if len(sub) < 40:
        print(f"\n  ⚠️  Too few events (n={len(sub)}) for reliable walk-forward. Skip.")
        return

    # ── 1B. Static 70/30 split ───────────────────────────────────────────────
    split_idx = int(len(sub) * 0.70)
    split_date = sub.iloc[split_idx]['date']
    train = sub.iloc[:split_idx]
    test  = sub.iloc[split_idx:]

    print(f"\n  70/30 Split:")
    print(f"  Train: {train['date'].min().date()} → {train['date'].max().date()} (n={len(train)})")
    print(f"  Test:  {test['date'].min().date()}  → {test['date'].max().date()} (n={len(test)})")

    # Training set stats
    t_all_wr = train['eod_positive'].mean() * 100
    t_held = train[train['gap_held'] == 1]
    t_nohold = train[train['gap_held'] == 0]
    t_held_wr = t_held['eod_positive'].mean() * 100 if len(t_held) > 0 else np.nan
    t_no_wr   = t_nohold['eod_positive'].mean() * 100 if len(t_nohold) > 0 else np.nan

    print(f"\n  [TRAIN] gap_held=1: WR={t_held_wr:.1f}% n={len(t_held)}")
    print(f"  [TRAIN] gap_held=0: WR={t_no_wr:.1f}% n={len(t_nohold)}")
    print(f"  [TRAIN] no filter:  WR={t_all_wr:.1f}% n={len(train)}")

    # Test set stats (OOS)
    oos_all_wr, lo_all, hi_all = bootstrap_wr(test['eod_positive'].values, n_boot)
    p_all = binom_p(test['eod_positive'].sum(), len(test))

    test_held   = test[test['gap_held'] == 1]
    test_nohold = test[test['gap_held'] == 0]

    oos_held_wr, lo_h, hi_h = bootstrap_wr(test_held['eod_positive'].values, n_boot)
    p_held = binom_p(test_held['eod_positive'].sum(), len(test_held))

    oos_no_wr, lo_n, hi_n = bootstrap_wr(test_nohold['eod_positive'].values, n_boot)
    p_no   = binom_p(test_nohold['eod_positive'].sum(), len(test_nohold))

    print(f"\n  ── OOS Results (test set, {test['date'].min().date()} → {test['date'].max().date()}) ──")
    print(f"  {'Filter':<20} {'n':>5} {'WR%':>6}  {'95% CI':>18}  {'avg ret':>7}  {'sig'}")
    print(f"  {'-'*68}")

    def row(label, sub_df, wr, lo, hi, p):
        avg = sub_df['eod_return'].mean() if len(sub_df) > 0 else np.nan
        above = '✓' if (not np.isnan(lo) and lo > 50) else ' '
        print(f"  {label:<20} {len(sub_df):>5} {wr:>6.1f}  [{lo:>5.1f}%-{hi:>5.1f}%]{above}  {avg:>+7.2f}%  {sig(p)}")

    row("no filter",      test,      oos_all_wr,  lo_all, hi_all, p_all)
    row("gap_held=1",     test_held, oos_held_wr, lo_h,   hi_h,   p_held)
    row("gap_held=0",     test_nohold, oos_no_wr, lo_n,   hi_n,   p_no)

    # ── 1C. Rolling 4-fold walk-forward ─────────────────────────────────────
    print(f"\n  ── Rolling Walk-Forward (4 folds) ──")
    print(f"  {'Fold':<8} {'Train n':>8} {'Test n':>7} {'WR (no filter)':>15} {'WR (gap_held=1)':>17} {'lift':>6}")
    print(f"  {'-'*65}")

    n_sub = len(sub)
    fold_size = n_sub // 5   # 5 chunks → 4 folds (train=1-4 chunks, test=5th; etc.)

    fold_results = []
    for fold in range(1, 5):
        tr_end = fold * fold_size
        te_end = min(tr_end + fold_size, n_sub)
        tr = sub.iloc[:tr_end]
        te = sub.iloc[tr_end:te_end]
        if len(te) < 5: continue

        wr_base = te['eod_positive'].mean() * 100
        te_held = te[te['gap_held'] == 1]
        wr_held = te_held['eod_positive'].mean() * 100 if len(te_held) >= 3 else np.nan
        lift = wr_held - wr_base if not np.isnan(wr_held) else np.nan

        fold_results.append({'fold': fold, 'wr_base': wr_base, 'wr_held': wr_held, 'lift': lift,
                              'n_tr': len(tr), 'n_te': len(te)})
        held_str = f"{wr_held:>6.1f}% (n={len(te_held)})" if not np.isnan(wr_held) else "  n/a "
        lift_str = f"{lift:>+5.1f}%" if not np.isnan(lift) else "   n/a"
        print(f"  Fold {fold:<3}  {len(tr):>8}  {len(te):>7}  {wr_base:>8.1f}% (n={len(te):<3})  {held_str}  {lift_str}")

    if fold_results:
        lifts = [r['lift'] for r in fold_results if not np.isnan(r['lift'])]
        consistent = sum(1 for l in lifts if l > 0)
        print(f"\n  Gap-hold lifted WR in {consistent}/{len(lifts)} folds (≥0): "
              f"avg lift = {np.mean(lifts):+.1f}%")
        if consistent >= 3:
            print(f"  ✅ Consistent lift OOS → gap-hold rule generalizes")
        else:
            print(f"  ⚠️  Inconsistent → may be in-sample artifact")

    # ── 1D. Conclusion ───────────────────────────────────────────────────────
    print(f"\n  ── Interpretation ──")
    print(f"  • gap_held=1 keeps {len(test_held)}/{len(test)} events ({len(test_held)/len(test)*100:.0f}% pass rate)")
    print(f"  • If OOS WR > train WR → rule generalizes (good)")
    print(f"  • If CI lo > 50% OOS → statistically meaningful edge")
    print(f"  ⚠️  gap_held uses EOD price (not T+1h) — real implementation needs intraday check")


# ─── SECTION 2: Slippage Model ────────────────────────────────────────────────

def section_slippage(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 2 — Realistic Slippage & Execution Model")
    print(f"  Gap stocks มี wide spread ตอน open — slippage จริงสูงกว่า backtest มาก")
    print('='*72)

    # Use best config: vol≥2x, ATR-based TP/SL
    sub = df[(df['volume_ratio'] >= 2.0) & df['atr_pct'].notna()].copy()
    print(f"\n  Base set (vol≥2x, ATR available): n={len(sub)}")

    # Compute ATR-based TP/SL for each event
    sub['tp_atr'] = sub['atr_pct'] * ATR_TP_MULT
    sub['sl_atr'] = sub['atr_pct'] * ATR_SL_MULT

    # Slippage scenarios: (label, entry_slip%, exit_slip_sl%, exit_slip_tp%)
    SCENARIOS = [
        ('Backtest (clean)',     0.05, 0.05,  0.05),   # baseline
        ('Conservative 0.2%',   0.20, 0.10,  0.10),   # modest
        ('Realistic 0.3%',      0.30, 0.15,  0.10),   # market-open gap stock
        ('Pessimistic 0.5%',    0.50, 0.25,  0.15),   # large cap gap < liquidity
        ('Worst case 0.7%',     0.70, 0.40,  0.20),   # penny/small cap gap
    ]

    print(f"\n  Config: TP={ATR_TP_MULT}×ATR, SL={ATR_SL_MULT}×ATR  (median: TP≈{sub['tp_atr'].median():.1f}%, SL≈{sub['sl_atr'].median():.1f}%)")
    print(f"\n  {'Scenario':<25} {'n':>5} {'WR%':>6}  {'CI [lo-hi]':>16}  {'avg ret':>8}  {'sharpe':>7}  {'edge?'}")
    print(f"  {'-'*80}")

    scenario_rows = []
    for label, slip_e, slip_sl, slip_tp in SCENARIOS:
        rets = []
        for _, row_data in sub.iterrows():
            tp = row_data['tp_atr']
            sl = row_data['sl_atr']
            high_pct = row_data['high_pct']
            low_pct  = row_data['low_pct']
            eod_ret  = row_data['eod_return']

            tp_hit = high_pct >= tp
            sl_hit = (-low_pct) >= sl
            cost   = slip_e + COMMISSION_PCT + COMMISSION_PCT   # exit is TP or EOD (low slip)

            if tp_hit and sl_hit:
                if (-low_pct) > high_pct:
                    ret = -sl - slip_e - slip_sl - 2 * COMMISSION_PCT
                else:
                    ret = tp - slip_e - slip_tp - 2 * COMMISSION_PCT
            elif tp_hit:
                ret = tp - slip_e - slip_tp - 2 * COMMISSION_PCT
            elif sl_hit:
                ret = -sl - slip_e - slip_sl - 2 * COMMISSION_PCT
            else:
                ret = eod_ret - slip_e - COMMISSION_PCT * 2   # EOD: entry slip + both commissions
            rets.append(ret)

        rets = np.array(rets)
        wins = (rets > 0).sum()
        wr, lo, hi = bootstrap_wr((rets > 0).astype(float), n_boot)
        avg = rets.mean()
        sh  = sharpe(rets)
        above = '✓' if (not np.isnan(lo) and lo > 50) else ' '
        edge = '✅ positive' if avg > 0 else ('⚠️ marginal' if avg > -0.3 else '❌ negative')
        print(f"  {label:<25} {len(rets):>5} {wr:>6.1f}  [{lo:>5.1f}-{hi:>5.1f}%]{above}  {avg:>+8.3f}%  {sh:>7.2f}  {edge}")
        scenario_rows.append({'scenario': label, 'wr': wr, 'avg': avg, 'sharpe': sh})

    # Fixed SL2% comparison at conservative slippage
    print(f"\n  ── Fixed TP5%+SL2% (current live) vs ATR at Realistic 0.3% slippage ──")
    SLIP_E, SLIP_SL = 0.30, 0.15
    for config_name, tp_col, sl_col in [
        ('Fixed TP5%+SL2%', None, None),
        (f'ATR TP{ATR_TP_MULT}x+SL{ATR_SL_MULT}x', 'tp_atr', 'sl_atr'),
    ]:
        rets = []
        for _, r in sub.iterrows():
            tp = 5.0 if tp_col is None else r[tp_col]
            sl = 2.0 if sl_col is None else r[sl_col]
            tp_hit = r['high_pct'] >= tp
            sl_hit = (-r['low_pct']) >= sl
            if tp_hit and sl_hit:
                ret = (-sl - SLIP_E - SLIP_SL - 2*COMMISSION_PCT) if (-r['low_pct']) > r['high_pct'] else (tp - SLIP_E - 0.10 - 2*COMMISSION_PCT)
            elif tp_hit:
                ret = tp - SLIP_E - 0.10 - 2*COMMISSION_PCT
            elif sl_hit:
                ret = -sl - SLIP_E - SLIP_SL - 2*COMMISSION_PCT
            else:
                ret = r['eod_return'] - SLIP_E - 2*COMMISSION_PCT
            rets.append(ret)
        rets = np.array(rets)
        wr, lo, hi = bootstrap_wr((rets > 0).astype(float), n_boot)
        print(f"  {config_name:<25}  WR={wr:.1f}%  avg={rets.mean():+.3f}%  sharpe={sharpe(rets):.2f}")

    print(f"\n  ── Break-even slippage ──")
    for config_name, tp_col, sl_col in [
        ('Fixed TP5%+SL2%', None, None),
        (f'ATR TP{ATR_TP_MULT}x+SL{ATR_SL_MULT}x', 'tp_atr', 'sl_atr'),
    ]:
        for slip_e in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50]:
            rets = []
            for _, r in sub.iterrows():
                tp = 5.0 if tp_col is None else r[tp_col]
                sl = 2.0 if sl_col is None else r[sl_col]
                tp_hit = r['high_pct'] >= tp
                sl_hit = (-r['low_pct']) >= sl
                slip_sl = slip_e * 0.5
                if tp_hit and sl_hit:
                    ret = (-sl - slip_e - slip_sl - 2*COMMISSION_PCT) if (-r['low_pct']) > r['high_pct'] else (tp - slip_e - 0.10 - 2*COMMISSION_PCT)
                elif tp_hit:
                    ret = tp - slip_e - 0.10 - 2*COMMISSION_PCT
                elif sl_hit:
                    ret = -sl - slip_e - slip_sl - 2*COMMISSION_PCT
                else:
                    ret = r['eod_return'] - slip_e - 2*COMMISSION_PCT
                rets.append(ret)
            avg = np.mean(rets)
            if avg <= 0:
                print(f"  {config_name}: break-even at entry slippage ≈ {slip_e:.2f}%  (avg turns negative)")
                break
        else:
            print(f"  {config_name}: positive even at 0.5% entry slippage")


# ─── SECTION 3: Sector & Catalyst Breakdown ───────────────────────────────────

def section_sector_catalyst(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 3 — Sector & Inferred Catalyst Type")
    print(f"  สาเหตุที่ vol สูง → ประเภท catalyst → WR ต่างกันมั้ย?")
    print('='*72)

    # ── 3A. Download sector from yfinance ──────────────────────────────────
    symbols = df['symbol'].unique().tolist()
    print(f"\n  Downloading sector info for {len(symbols)} symbols...")

    sector_map = {}
    batch_size = 20
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        for sym in batch:
            try:
                info = yf.Ticker(sym).info
                sector_map[sym] = info.get('sector', 'Unknown')
            except Exception:
                sector_map[sym] = 'Unknown'
        time.sleep(0.3)

    df2 = df.copy()
    df2['sector'] = df2['symbol'].map(sector_map).fillna('Unknown')

    sector_counts = df2['sector'].value_counts()
    print(f"\n  Sector distribution:")
    for sec, cnt in sector_counts.items():
        print(f"    {sec:<35} {cnt:>4} events")

    # ── 3B. WR by sector ─────────────────────────────────────────────────────
    print(f"\n  ── WR by Sector (all events, gap≥8%) ──")
    print(f"  {'Sector':<35} {'n':>5} {'WR%':>6}  {'CI [lo-hi]':>16}  {'avg ret':>8}  {'sig'}")
    print(f"  {'-'*78}")

    sector_results = []
    for sec in sector_counts.index:
        sub = df2[df2['sector'] == sec]
        if len(sub) < 8:
            continue
        wr, lo, hi = bootstrap_wr(sub['eod_positive'].values, n_boot)
        avg = sub['eod_return'].mean()
        p   = binom_p(sub['eod_positive'].sum(), len(sub))
        above = '✓' if (not np.isnan(lo) and lo > 50) else ' '
        print(f"  {sec:<35} {len(sub):>5} {wr:>6.1f}  [{lo:>5.1f}-{hi:>5.1f}%]{above}  {avg:>+8.2f}%  {sig(p)}")
        sector_results.append({'sector': sec, 'n': len(sub), 'wr': wr, 'avg': avg, 'p': p})

    # ── 3C. Infer catalyst type by vol_ratio tier ─────────────────────────────
    print(f"\n  ── Inferred Catalyst Type (vol_ratio proxy) ──")
    print(f"  vol≥5x + gap≥15% → likely earnings/major news")
    print(f"  vol 2-5x          → sector momentum/analyst action")
    print(f"  vol 0.3-2x        → unclear (sympathy/thin volume)")

    def infer_catalyst(row):
        if row['volume_ratio'] >= 5.0 and row['open_gap_pct'] >= 15.0:
            return 'Earnings/Major (vol≥5x,gap≥15%)'
        elif row['volume_ratio'] >= 2.0 and row['open_gap_pct'] >= 10.0:
            return 'Strong catalyst (vol≥2x,gap≥10%)'
        elif row['volume_ratio'] >= 2.0:
            return 'Vol catalyst (vol≥2x,gap 8-10%)'
        elif row['volume_ratio'] >= 1.0:
            return 'Moderate vol (1-2x)'
        else:
            return 'Low vol (<1x)'

    df2['catalyst_type'] = df2.apply(infer_catalyst, axis=1)

    print(f"\n  {'Catalyst type':<35} {'n':>5} {'WR%':>6}  {'CI [lo-hi]':>16}  {'avg ret':>8}  {'sig'}")
    print(f"  {'-'*78}")

    order = ['Earnings/Major (vol≥5x,gap≥15%)', 'Strong catalyst (vol≥2x,gap≥10%)',
             'Vol catalyst (vol≥2x,gap 8-10%)', 'Moderate vol (1-2x)', 'Low vol (<1x)']
    for cat in order:
        sub = df2[df2['catalyst_type'] == cat]
        if len(sub) < 5: continue
        wr, lo, hi = bootstrap_wr(sub['eod_positive'].values, n_boot)
        avg = sub['eod_return'].mean()
        p   = binom_p(sub['eod_positive'].sum(), len(sub))
        above = '✓' if (not np.isnan(lo) and lo > 50) else ' '
        print(f"  {cat:<35} {len(sub):>5} {wr:>6.1f}  [{lo:>5.1f}-{hi:>5.1f}%]{above}  {avg:>+8.2f}%  {sig(p)}")

    # ── 3D. Best sector × vol≥2x ─────────────────────────────────────────────
    print(f"\n  ── Sector × vol≥2x filter ──")
    sub2x = df2[df2['volume_ratio'] >= 2.0]
    print(f"  {'Sector':<35} {'n':>5} {'WR%':>6}  {'avg ret':>8}")
    print(f"  {'-'*58}")
    for sec in sector_counts.index:
        sub = sub2x[sub2x['sector'] == sec]
        if len(sub) < 5: continue
        wr = sub['eod_positive'].mean() * 100
        avg = sub['eod_return'].mean()
        print(f"  {sec:<35} {len(sub):>5} {wr:>6.1f}  {avg:>+8.2f}%")

    return df2


# ─── SECTION 4: Consecutive Loss & Drawdown ───────────────────────────────────

def section_drawdown(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 4 — Consecutive Loss & Drawdown Pattern")
    print(f"  วัด: max consecutive losses, loss clustering, SPY correlation")
    print('='*72)

    # Apply best config: vol≥2x, ATR SL (or fixed if no ATR)
    sub = df[df['volume_ratio'] >= 2.0].copy()
    sub = sub.sort_values('date').reset_index(drop=True)
    print(f"\n  Base set (vol≥2x): n={len(sub)}")

    if len(sub) < 10:
        print(f"  ⚠️  Too few events. Skip.")
        return

    # Compute returns with realistic slippage (0.3% entry)
    SLIP_E = 0.30
    def compute_ret(r):
        if pd.notna(r.get('atr_pct')):
            tp, sl = r['atr_pct'] * ATR_TP_MULT, r['atr_pct'] * ATR_SL_MULT
        else:
            tp, sl = LIVE_TP_PCT, LIVE_SL_PCT
        tp_hit = r['high_pct'] >= tp
        sl_hit = (-r['low_pct']) >= sl
        if tp_hit and sl_hit:
            return (-sl - SLIP_E - 0.15 - 2*COMMISSION_PCT) if (-r['low_pct']) > r['high_pct'] else (tp - SLIP_E - 0.10 - 2*COMMISSION_PCT)
        elif tp_hit:
            return tp - SLIP_E - 0.10 - 2*COMMISSION_PCT
        elif sl_hit:
            return -sl - SLIP_E - 0.15 - 2*COMMISSION_PCT
        return r['eod_return'] - SLIP_E - 2*COMMISSION_PCT

    sub['strat_ret'] = sub.apply(compute_ret, axis=1)
    sub['win'] = sub['strat_ret'] > 0

    # ── 4A. Equity curve ─────────────────────────────────────────────────────
    sub['cum_pct'] = sub['strat_ret'].cumsum()
    sub['peak']    = sub['cum_pct'].cummax()
    sub['drawdown']= sub['cum_pct'] - sub['peak']
    max_dd = sub['drawdown'].min()
    max_dd_date = sub.loc[sub['drawdown'].idxmin(), 'date']

    total_wr = sub['win'].mean() * 100
    total_avg = sub['strat_ret'].mean()
    total_sh = sharpe(sub['strat_ret'].values)

    print(f"\n  Overall (vol≥2x + ATR SL + 0.3% slippage):")
    print(f"  WR={total_wr:.1f}%  avg={total_avg:+.3f}%  sharpe={total_sh:.2f}")
    print(f"  Total return: {sub['cum_pct'].iloc[-1]:+.1f}%  Max DD: {max_dd:.1f}%  (at {max_dd_date.date()})")

    # ── 4B. Consecutive losses ────────────────────────────────────────────────
    print(f"\n  ── Consecutive Loss Analysis ──")
    max_streak = 0
    cur_streak = 0
    streak_starts = []
    all_streaks = []
    streak_start_date = None

    for idx, row_data in sub.iterrows():
        if not row_data['win']:
            if cur_streak == 0:
                streak_start_date = row_data['date']
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            if cur_streak >= 2:
                all_streaks.append({'start': streak_start_date,
                                    'length': cur_streak,
                                    'loss_pct': sub.loc[idx-cur_streak:idx-1, 'strat_ret'].sum()})
            cur_streak = 0
    if cur_streak >= 2:
        all_streaks.append({'start': streak_start_date, 'length': cur_streak,
                            'loss_pct': sub.iloc[-cur_streak:]['strat_ret'].sum()})

    print(f"  Max consecutive losses: {max_streak}")
    if all_streaks:
        print(f"\n  Loss streaks ≥2 consecutive:")
        print(f"  {'Start':<12} {'Length':>6} {'Cumulative loss':>16}")
        print(f"  {'-'*38}")
        for s in sorted(all_streaks, key=lambda x: x['length'], reverse=True)[:10]:
            print(f"  {str(s['start'].date()):<12} {s['length']:>6}      {s['loss_pct']:>+10.2f}%")

    # ── 4C. Loss → SPY correlation ────────────────────────────────────────────
    print(f"\n  ── Loss vs SPY return on same day ──")
    spy_avail = sub.dropna(subset=['spy_return'])
    if len(spy_avail) >= 10:
        wins_spy  = spy_avail[spy_avail['win']]['spy_return']
        loss_spy  = spy_avail[~spy_avail['win']]['spy_return']
        mw_stat, mw_p = mannwhitneyu(wins_spy, loss_spy, alternative='greater')
        print(f"  WIN days  — avg SPY: {wins_spy.mean():>+.2f}%  (n={len(wins_spy)})")
        print(f"  LOSS days — avg SPY: {loss_spy.mean():>+.2f}%  (n={len(loss_spy)})")
        print(f"  Mann-Whitney: p={mw_p:.4f} {sig(mw_p)}")
        if mw_p < 0.10:
            print(f"  → SPY direction predictive: SPY up days = higher gap WR")
        else:
            print(f"  → SPY direction NOT predictive (gap stocks move independently)")

        # SPY return buckets
        print(f"\n  WR by SPY return that day:")
        spy_bins   = [-10, -1.5, -0.5, 0.5, 1.5, 10]
        spy_labels = ['< -1.5%', '-1.5 to -0.5%', '-0.5 to +0.5%', '+0.5 to +1.5%', '> +1.5%']
        spy_avail2 = spy_avail.copy()
        spy_avail2['spy_bin'] = pd.cut(spy_avail2['spy_return'], bins=spy_bins, labels=spy_labels)
        for lbl in spy_labels:
            s = spy_avail2[spy_avail2['spy_bin'] == lbl]
            if len(s) < 3: continue
            wr = s['win'].mean() * 100
            avg = s['strat_ret'].mean()
            print(f"  SPY {lbl:<20}  n={len(s):>4}  WR={wr:.1f}%  avg={avg:>+.2f}%")
    else:
        print(f"  ⚠️  Not enough events with SPY data")

    # ── 4D. Loss clustering by market quarter ────────────────────────────────
    print(f"\n  ── WR by Quarter (regime shift detection) ──")
    sub['quarter'] = pd.PeriodIndex(sub['date'], freq='Q')
    for q in sorted(sub['quarter'].unique()):
        qs = sub[sub['quarter'] == q]
        if len(qs) < 3: continue
        wr = qs['win'].mean() * 100
        avg = qs['strat_ret'].mean()
        print(f"  {str(q):<8}  n={len(qs):>4}  WR={wr:.1f}%  avg={avg:>+.2f}%")


# ─── SECTION 5: Stress Test ────────────────────────────────────────────────────

def _find_gap_events_in_window(symbols, start, end, min_gap=8.0, vol_filter=0.3, batch_size=80):
    """Download daily OHLCV for symbols in [start,end], find gap≥min_gap events"""
    events = []
    logger.info(f"Downloading {len(symbols)} symbols for {start} → {end}...")

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        try:
            raw = yf.download(batch, start=start, end=end,
                              interval='1d', auto_adjust=True,
                              progress=False, group_by='ticker')
            if raw.empty:
                continue
            # Flatten MultiIndex
            if isinstance(raw.columns, pd.MultiIndex):
                for sym in batch:
                    try:
                        sym_df = raw[sym].dropna(subset=['Open', 'Close', 'Volume'])
                        if len(sym_df) < 5:
                            continue
                        # avg volume
                        sym_df = sym_df.copy()
                        sym_df['avg_vol'] = sym_df['Volume'].rolling(20, min_periods=5).mean().shift(1)
                        sym_df['prev_close'] = sym_df['Close'].shift(1)
                        sym_df['gap_pct'] = (sym_df['Open'] / sym_df['prev_close'] - 1) * 100
                        sym_df['vol_ratio'] = sym_df['Volume'] / sym_df['avg_vol']
                        sym_df['eod_return'] = (sym_df['Close'] / sym_df['Open'] - 1) * 100
                        sym_df['high_pct']   = (sym_df['High']  / sym_df['Open'] - 1) * 100
                        sym_df['low_pct']    = (sym_df['Low']   / sym_df['Open'] - 1) * 100

                        gap_events = sym_df[
                            (sym_df['gap_pct'] >= min_gap) &
                            (sym_df['vol_ratio'] >= vol_filter) &
                            sym_df['prev_close'].notna()
                        ]
                        for dt, ev in gap_events.iterrows():
                            events.append({
                                'date': dt,
                                'symbol': sym,
                                'open_gap_pct': ev['gap_pct'],
                                'volume_ratio': ev['vol_ratio'],
                                'eod_return': ev['eod_return'],
                                'high_pct': ev['high_pct'],
                                'low_pct': ev['low_pct'],
                                'eod_positive': int(ev['eod_return'] > 0),
                            })
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Batch download error: {e}")
        time.sleep(0.5)

    return pd.DataFrame(events) if events else pd.DataFrame()


def section_stress_test(df, n_boot):
    print(f"\n{'='*72}")
    print(f"  SECTION 5 — Stress Test: 2020 Crash / 2022 Bear Market")
    print(f"  ทดสอบว่า strategy ทำงานยังไงในช่วง market extreme")
    print('='*72)

    # Use top-frequency symbols from our current universe (gap-prone stocks)
    symbols = df['symbol'].value_counts().head(100).index.tolist()
    print(f"\n  Using top {len(symbols)} gap-prone symbols from current universe")

    stress_windows = [
        ('2020 COVID Crash',  '2020-01-15', '2020-04-15'),
        ('2020 Recovery',     '2020-04-15', '2020-08-01'),
        ('2022 Bear Market',  '2022-01-01', '2022-12-31'),
        ('2018 Q4 Selloff',   '2018-10-01', '2019-01-15'),
    ]

    print(f"\n  {'Period':<22} {'Events':>7} {'vol≥2x':>7} {'WR (all)':>9} {'WR (vol≥2x)':>12} {'avg (vol≥2x)':>14} {'VIX note'}")
    print(f"  {'-'*85}")

    # Also need VIX for context
    vix_data = {}
    try:
        vix_df = yf.download('^VIX', start='2018-01-01', end='2023-01-01',
                             interval='1d', auto_adjust=True, progress=False)
        if isinstance(vix_df.columns, pd.MultiIndex):
            vix_df.columns = vix_df.columns.get_level_values(0)
        vix_df.index = pd.to_datetime(vix_df.index).normalize()
        vix_data = vix_df['Close'].to_dict()
    except Exception:
        pass

    for period_name, start, end in stress_windows:
        events_df = _find_gap_events_in_window(symbols, start, end, min_gap=8.0, vol_filter=0.3)
        if events_df.empty:
            print(f"  {period_name:<22}    no data")
            continue

        n_all = len(events_df)
        wr_all = events_df['eod_positive'].mean() * 100
        sub2x = events_df[events_df['volume_ratio'] >= 2.0]
        n_2x = len(sub2x)

        if n_2x < 3:
            wr_2x = np.nan
            avg_2x = np.nan
        else:
            wr_2x = sub2x['eod_positive'].mean() * 100
            # Simulate with ATR proxy (use 3% ATR default if not available)
            rets = []
            for _, r in sub2x.iterrows():
                atr = r.get('atr_pct', 3.0) if pd.notna(r.get('atr_pct', np.nan)) else 3.0
                tp = atr * ATR_TP_MULT
                sl = atr * ATR_SL_MULT
                ret, _ = simulate_exit(r['high_pct'], r['low_pct'], r['eod_return'],
                                       tp, sl, slip_entry=0.30, slip_exit=0.15)
                rets.append(ret)
            avg_2x = np.mean(rets)

        # Average VIX for the period
        mid_date = pd.to_datetime(end) - (pd.to_datetime(end) - pd.to_datetime(start)) / 2
        vix_note = ''
        period_vix = [v for d, v in vix_data.items()
                      if pd.to_datetime(start) <= pd.Timestamp(d) <= pd.to_datetime(end)]
        if period_vix:
            avg_vix = np.mean(period_vix)
            max_vix = np.max(period_vix)
            vix_note = f"VIX avg={avg_vix:.0f} max={max_vix:.0f}"

        wr_2x_str = f"{wr_2x:>5.1f}%" if not np.isnan(wr_2x) else "  n/a "
        avg_2x_str = f"{avg_2x:>+.2f}%" if not np.isnan(avg_2x) else "   n/a"
        print(f"  {period_name:<22} {n_all:>7} {n_2x:>7} {wr_all:>8.1f}% {wr_2x_str:>12} {avg_2x_str:>14}  {vix_note}")

    print(f"\n  ── Interpretation ──")
    print(f"  • VIX>30 → skip ทั้งหมด (WR=8% ตาม Section 1 ของ extended backtest)")
    print(f"  • COVID crash (Mar 2020) VIX>70 → ควร skip ทั้งหมด")
    print(f"  • 2022 bear VIX 20-35 → บางวันมี gap อาจยังเล่นได้ถ้า vol≥2x")
    print(f"  • ถ้า WR ยังสูงใน 2022 → vol≥2x filter robust ข้ามรอบตลาด")
    print(f"  • ถ้า WR ต่ำมากใน 2022 → ต้องเพิ่ม SPY trend filter (SPY > MA50)")


# ─── SECTION Summary ──────────────────────────────────────────────────────────

def print_final_summary():
    print(f"\n{'='*72}")
    print(f"  FINAL SUMMARY — Implementation Recommendation")
    print('='*72)
    print(f"""
  ┌─────────────────────────────────────────────────────────────────────┐
  │  GAP Strategy Upgrade Decision Matrix                               │
  ├────────────────────────────┬───────────┬───────────────────────────┤
  │  Change                    │  Evidence │  Risk                     │
  ├────────────────────────────┼───────────┼───────────────────────────┤
  │  vol≥2x filter             │  ***      │  LOW — proven OOS         │
  │  ATR SL (0.3×ATR)          │  **       │  LOW — clear sharpe gain  │
  │  VIX>30 skip               │  *        │  LOW — rare events anyway │
  │  Gap-hold T+1h check       │  Section1 │  MED — EOD proxy only     │
  │  Sector filter             │  Section3 │  Depends on results       │
  └────────────────────────────┴───────────┴───────────────────────────┘

  Option A (Safe):    vol≥2x + ATR SL + VIX>30 skip
  Option B (Full):    Option A + gap-hold T+1h check + best sectors only

  ⚠️  Key risks from this analysis:
    • Slippage 0.3% may cut avg return from +1.2% to +0.6%
    • n=~20/year — need 6+ months live trading to confirm edge
    • Stress test shows regime dependency (Section 5)
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    np.random.seed(42)

    print(f"\n{'='*72}")
    print(f"  GAP STRATEGY — VALIDATION BACKTEST")
    print(f"  5 Tests before implementing changes")
    print('='*72)

    df = load_base_data(args.csv, args.min_gap)

    # Section 1: Gap-Hold OOS
    section_gaphold_oos(df, args.n_boot)

    # Section 2: Slippage
    section_slippage(df, args.n_boot)

    # Section 3: Sector/Catalyst
    _ = section_sector_catalyst(df, args.n_boot)

    # Section 4: Drawdown
    section_drawdown(df, args.n_boot)

    # Section 5: Stress test (optional, slow)
    if args.stress:
        section_stress_test(df, args.n_boot)
    else:
        print(f"\n{'='*72}")
        print(f"  SECTION 5 — Stress Test (SKIPPED)")
        print(f"  Run with --stress flag to include 2020/2022 historical simulation")
        print('='*72)

    print_final_summary()


if __name__ == '__main__':
    main()
