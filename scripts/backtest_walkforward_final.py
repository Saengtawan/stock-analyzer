#!/usr/bin/env python3
"""
FINAL Walk-Forward Backtest: 10 strategies x ML filter x 856 symbols x 55M bars
Vectorized pandas for features, date-by-date SQL for intraday.
"""
import sys, os, warnings, time, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(line_buffering=True)

import numpy as np
import pandas as pd
from collections import defaultdict
from database.orm.base import get_session
from sqlalchemy import text
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

MIN_TRAIN_MONTHS = 6
STRATEGY_NAMES = [
    'FIRST_BAR_CONFIRM', 'HOD_BREAK', 'HAMMER', 'GAP_NOT_FILLED',
    'OPENING_DRIVE', 'RECLAIM_OPEN', 'NARROW_3BAR', 'VOLUME_SPIKE_GREEN',
    'HIGHER_HIGH_HIGHER_LOW', 'FIRST_RED_REVERSAL'
]
FEATURE_COLS = ['gap_pct', 'volume_ratio', 'mom_5d', 'mom_20d', 'atr_pct',
                'rsi_approx', 'dist_from_20d_high', 'market_cap_log', 'beta',
                'vix_close', 'breadth']

# ─── Step 1: Load reference data ──────────────────────────────────
print("=" * 80)
print("STEP 1: Loading reference data...")
t0 = time.time()

with get_session() as sess:
    macro_rows = sess.execute(text("SELECT date, vix_close FROM macro_snapshots")).fetchall()
    macro_dict = {r[0]: r[1] for r in macro_rows}

    breadth_rows = sess.execute(text("SELECT date, pct_above_20d_ma FROM market_breadth")).fetchall()
    breadth_dict = {r[0]: r[1] for r in breadth_rows}

    fund_rows = sess.execute(text("SELECT symbol, beta, market_cap FROM stock_fundamentals")).fetchall()
    fund_dict = {r[0]: (r[1], r[2]) for r in fund_rows}

    dates_rows = sess.execute(text("SELECT DISTINCT date FROM intraday_bars_5m ORDER BY date")).fetchall()
    all_intraday_dates = [r[0] for r in dates_rows]

print(f"  Macro: {len(macro_dict)}, Breadth: {len(breadth_dict)}, Fund: {len(fund_dict)}, Dates: {len(all_intraday_dates)}")
print(f"  {time.time()-t0:.1f}s")

# ─── Step 2: Vectorized daily features ────────────────────────────
print("\nSTEP 2: Computing daily features (vectorized pandas)...")
t0 = time.time()

with get_session() as sess:
    daily_df = pd.read_sql("SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc ORDER BY symbol, date", sess.connection())

print(f"  Loaded {len(daily_df):,} daily rows in {time.time()-t0:.1f}s")

# Vectorized features per symbol group
daily_df = daily_df.sort_values(['symbol', 'date']).reset_index(drop=True)

# Prev close
daily_df['prev_close'] = daily_df.groupby('symbol')['close'].shift(1)

# Momentum
daily_df['mom_5d'] = daily_df.groupby('symbol')['close'].pct_change(5) * 100
daily_df['mom_20d'] = daily_df.groupby('symbol')['close'].pct_change(20) * 100

# ATR (simplified: use rolling high-low as proxy, much faster)
daily_df['tr'] = daily_df['high'] - daily_df['low']
# True range needs prev_close
daily_df['tr2'] = (daily_df['high'] - daily_df['prev_close']).abs()
daily_df['tr3'] = (daily_df['low'] - daily_df['prev_close']).abs()
daily_df['true_range'] = daily_df[['tr', 'tr2', 'tr3']].max(axis=1)
daily_df['atr_14'] = daily_df.groupby('symbol')['true_range'].transform(lambda x: x.rolling(14, min_periods=1).mean())
daily_df['atr_pct'] = daily_df['atr_14'] / daily_df['prev_close'] * 100

# RSI 14
delta = daily_df.groupby('symbol')['close'].diff()
gain = delta.clip(lower=0)
loss = (-delta.clip(upper=0))
avg_gain = gain.groupby(daily_df['symbol']).transform(lambda x: x.rolling(14, min_periods=1).mean())
avg_loss = loss.groupby(daily_df['symbol']).transform(lambda x: x.rolling(14, min_periods=1).mean())
rs = avg_gain / avg_loss.replace(0, 0.001)
daily_df['rsi_approx'] = 100 - (100 / (1 + rs))

# Distance from 20d high
daily_df['high_20d'] = daily_df.groupby('symbol')['high'].transform(lambda x: x.rolling(20, min_periods=1).max())
daily_df['dist_from_20d_high'] = (daily_df['prev_close'] / daily_df['high_20d'].shift(1) - 1) * 100

# Average volume 20d
daily_df['avg_vol_20d'] = daily_df.groupby('symbol')['volume'].transform(lambda x: x.rolling(20, min_periods=1).mean())

# Add fundamentals
daily_df['beta'] = daily_df['symbol'].map(lambda s: (fund_dict.get(s, (1.0, 0))[0]) or 1.0)
daily_df['market_cap_log'] = daily_df['symbol'].map(lambda s: np.log10(max(fund_dict.get(s, (0, 1))[1] or 1, 1)))

# Drop early rows
daily_df = daily_df.dropna(subset=['prev_close', 'mom_5d']).copy()

# Create lookup dict: (symbol, date) -> features
print(f"  Building feature lookup ({len(daily_df):,} rows)...")
feat_cols = ['prev_close', 'mom_5d', 'mom_20d', 'atr_pct', 'rsi_approx',
             'dist_from_20d_high', 'market_cap_log', 'beta', 'avg_vol_20d',
             'open', 'close']
daily_features = {}
for row in daily_df[['symbol', 'date'] + feat_cols].itertuples(index=False):
    daily_features[(row[0], row[1])] = {
        'prev_close': row[2], 'mom_5d': row[3], 'mom_20d': row[4],
        'atr_pct': row[5], 'rsi_approx': row[6], 'dist_from_20d_high': row[7],
        'market_cap_log': row[8], 'beta': row[9], 'avg_vol_20d': row[10],
        'day_open': row[11], 'day_close': row[12],
    }

print(f"  Features: {len(daily_features):,} entries in {time.time()-t0:.1f}s")
del daily_df, delta, gain, loss, avg_gain, avg_loss, rs
gc.collect()

# ─── Step 3: Scan intraday bars ───────────────────────────────────
print("\nSTEP 3: Scanning intraday bars for 10 strategies...")
t0 = time.time()
all_signals = []
n_dates = len(all_intraday_dates)

for di, scan_date in enumerate(all_intraday_dates):
    if di % 50 == 0:
        elapsed = time.time() - t0
        rate = (di + 1) / max(elapsed, 0.01)
        eta = (n_dates - di) / rate / 60
        print(f"  [{di+1}/{n_dates}] {scan_date} | {elapsed:.0f}s | ETA {eta:.1f}min | signals: {len(all_signals):,}")

    with get_session() as sess:
        rows = sess.execute(text(
            "SELECT symbol, time_et, open, high, low, close, volume "
            "FROM intraday_bars_5m "
            "WHERE date = :d AND time_et >= '09:30' AND time_et <= '16:00' "
            "ORDER BY symbol, time_et"
        ), {'d': scan_date}).fetchall()

    if not rows:
        continue

    vix_val = macro_dict.get(scan_date, 20) or 20
    breadth_val = breadth_dict.get(scan_date, 50) or 50

    # Group by symbol (rows are sorted by symbol, time)
    sym_bars = defaultdict(list)
    for r in rows:
        sym_bars[r[0]].append(r[1:])  # time,o,h,l,c,v

    for sym, bars_raw in sym_bars.items():
        feat = daily_features.get((sym, scan_date))
        if feat is None or len(bars_raw) < 5:
            continue

        prev_close = feat['prev_close']
        if not prev_close or prev_close <= 0:
            continue

        day_open = bars_raw[0][1]  # open of first bar
        gap_pct = (day_open / prev_close - 1) * 100
        if gap_pct < 1.0:
            continue

        day_close_price = bars_raw[-1][4]  # close of last bar
        day_ended_green = 1 if day_close_price > day_open else 0

        # Volume ratio
        first_30min_vol = sum(b[5] for b in bars_raw[:6])
        avg_daily = feat['avg_vol_20d'] or 1
        vol_ratio = min(first_30min_vol / max(avg_daily / 13, 1), 10)

        base = {
            'gap_pct': gap_pct, 'volume_ratio': vol_ratio,
            'mom_5d': feat['mom_5d'] or 0, 'mom_20d': feat['mom_20d'] or 0,
            'atr_pct': feat['atr_pct'] or 0, 'rsi_approx': feat['rsi_approx'] or 50,
            'dist_from_20d_high': feat['dist_from_20d_high'] or 0,
            'market_cap_log': feat['market_cap_log'] or 10,
            'beta': feat['beta'] or 1, 'vix_close': vix_val, 'breadth': breadth_val,
        }

        # Build bar metadata
        n_bars = len(bars_raw)
        times = [b[0] for b in bars_raw]
        opens = [b[1] for b in bars_raw]
        highs = [b[2] for b in bars_raw]
        lows = [b[3] for b in bars_raw]
        closes = [b[4] for b in bars_raw]
        vols = [b[5] for b in bars_raw]

        # Running high/low
        rhi = np.maximum.accumulate(highs)
        rlo = np.minimum.accumulate(lows)
        bodies = [abs(closes[i] - opens[i]) for i in range(n_bars)]
        ranges_ = [highs[i] - lows[i] for i in range(n_bars)]
        is_green = [closes[i] > opens[i] for i in range(n_bars)]
        lower_wicks = [min(opens[i], closes[i]) - lows[i] for i in range(n_bars)]
        ret_from_open = [(closes[i] / day_open - 1) * 100 if day_open > 0 else 0 for i in range(n_bars)]
        gap_filled = [lows[i] <= prev_close for i in range(n_bars)]
        any_gap_filled = False  # running tracker

        found = set()

        def add_sig(strat, bi):
            if strat in found:
                return
            ep = closes[bi]
            if ep <= 0:
                return
            found.add(strat)
            all_signals.append({
                'strategy': strat, 'symbol': sym, 'date': scan_date,
                'month': scan_date[:7],
                'entry_price': ep, 'exit_price': day_close_price,
                'return_pct': (day_close_price / ep - 1) * 100,
                'label': day_ended_green,
                **base
            })

        for bi in range(n_bars):
            t = times[bi]
            if gap_filled[bi]:
                any_gap_filled = True

            # 1. FIRST_BAR_CONFIRM
            if '09:40' <= t <= '10:30' and ret_from_open[bi] > 0.8 and not any_gap_filled:
                add_sig('FIRST_BAR_CONFIRM', bi)

            # 2. HOD_BREAK
            if t > '10:00' and bi >= 2:
                prev_hi = max(highs[:bi])
                if closes[bi] >= prev_hi * 0.998 and prev_hi > day_open:
                    add_sig('HOD_BREAK', bi)

            # 3. HAMMER
            if '09:45' <= t <= '13:00' and is_green[bi] and not any_gap_filled:
                if bodies[bi] > 0 and lower_wicks[bi] >= 2 * bodies[bi]:
                    if lows[bi] <= rlo[bi] * 1.01:
                        add_sig('HAMMER', bi)

            # 4. GAP_NOT_FILLED
            if gap_pct >= 2.0 and '10:00' <= t <= '11:00' and not any_gap_filled and closes[bi] > day_open:
                add_sig('GAP_NOT_FILLED', bi)

            # 5. OPENING_DRIVE
            if bi == 3:
                if (is_green[1] and is_green[2] and is_green[3] and
                    closes[2] > closes[1] and closes[3] > closes[2] and
                    vols[2] > vols[1] and vols[3] > vols[2]):
                    add_sig('OPENING_DRIVE', bi)

            # 6. RECLAIM_OPEN
            if '10:00' <= t <= '12:00' and bi >= 2:
                dipped = any(lows[j] < day_open for j in range(bi))
                if dipped and closes[bi] > day_open and is_green[bi]:
                    add_sig('RECLAIM_OPEN', bi)

            # 7. NARROW_3BAR
            if '10:00' <= t <= '14:00' and bi >= 4:
                pr = closes[bi-3] if closes[bi-3] > 0 else 1
                if (ranges_[bi-3]/pr*100 < 0.3 and ranges_[bi-2]/pr*100 < 0.3 and
                    ranges_[bi-1]/pr*100 < 0.3 and ranges_[bi]/pr*100 > 0.5 and is_green[bi]):
                    ch = max(highs[bi-3], highs[bi-2], highs[bi-1])
                    if closes[bi] > ch:
                        add_sig('NARROW_3BAR', bi)

            # 8. VOLUME_SPIKE_GREEN
            if '09:45' <= t <= '13:00' and bi >= 4:
                avg_bv = np.mean(vols[max(0,bi-10):bi]) if bi > 0 else 1
                if avg_bv > 0 and vols[bi] > 3 * avg_bv and is_green[bi]:
                    p3h = max(highs[max(0,bi-3):bi])
                    if closes[bi] > p3h:
                        add_sig('VOLUME_SPIKE_GREEN', bi)

            # 9. HIGHER_HIGH_HIGHER_LOW
            if '10:00' <= t <= '12:00' and bi >= 3:
                if (highs[bi-1] > highs[bi-2] and lows[bi-1] > lows[bi-2] and
                    highs[bi] > highs[bi-1] and lows[bi] > lows[bi-1]):
                    add_sig('HIGHER_HIGH_HIGHER_LOW', bi)

            # 10. FIRST_RED_REVERSAL
            if '09:45' <= t <= '10:30' and bi >= 2:
                if not is_green[0] and is_green[bi] and closes[bi] > opens[0]:
                    add_sig('FIRST_RED_REVERSAL', bi)

            if len(found) == 10:
                break

    del rows
    if di % 100 == 0:
        gc.collect()

elapsed = time.time() - t0
print(f"\n  Total signals: {len(all_signals):,} in {elapsed:.0f}s")

# ─── Step 4: Walk-Forward ML ──────────────────────────────────────
print("\nSTEP 4: Walk-Forward ML...")
sig_df = pd.DataFrame(all_signals)
print(f"  Shape: {sig_df.shape}")
for strat in STRATEGY_NAMES:
    print(f"    {strat}: {(sig_df['strategy']==strat).sum():,}")

months_sorted = sorted(sig_df['month'].unique())
print(f"  Months: {months_sorted}")

sig_df['lr_prob'] = np.nan
sig_df['gb_prob'] = np.nan
sig_df['in_test'] = False

all_gb_imp = []
all_lr_coef = []

for test_idx in range(MIN_TRAIN_MONTHS, len(months_sorted)):
    test_month = months_sorted[test_idx]
    train_months = set(months_sorted[:test_idx])

    train_mask = sig_df['month'].isin(train_months)
    test_mask = sig_df['month'] == test_month

    X_train = np.nan_to_num(sig_df.loc[train_mask, FEATURE_COLS].values.astype(float), nan=0)
    y_train = sig_df.loc[train_mask, 'label'].values.astype(int)
    X_test = np.nan_to_num(sig_df.loc[test_mask, FEATURE_COLS].values.astype(float), nan=0)

    if len(X_train) < 50 or len(X_test) == 0:
        continue

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_te_s = scaler.transform(X_test)

    lr = LogisticRegression(max_iter=1000, C=1.0)
    lr.fit(X_tr_s, y_train)

    gb = GradientBoostingClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                                     subsample=0.8, random_state=42)
    gb.fit(X_train, y_train)

    sig_df.loc[test_mask, 'lr_prob'] = lr.predict_proba(X_te_s)[:, 1]
    sig_df.loc[test_mask, 'gb_prob'] = gb.predict_proba(X_test)[:, 1]
    sig_df.loc[test_mask, 'in_test'] = True

    all_gb_imp.append(gb.feature_importances_)
    all_lr_coef.append(lr.coef_[0])

    wr = sig_df.loc[test_mask, 'label'].mean() * 100
    print(f"  train={test_idx}mo test={test_month} | N_tr={len(X_train)} N_te={test_mask.sum()} | RawWR={wr:.1f}%")

test_df = sig_df[sig_df['in_test']].copy()

# ═══════════════════════════════════════════════════════════════════
# OUTPUTS
# ═══════════════════════════════════════════════════════════════════

# TABLE 1: Walk-Forward Monthly WR for 4 Current Strategies
print("\n" + "=" * 80)
print("TABLE 1: WALK-FORWARD MONTHLY WIN RATE — 4 Current Strategies")
print("=" * 80)

current_strats = ['FIRST_BAR_CONFIRM', 'HOD_BREAK', 'HAMMER', 'GAP_NOT_FILLED']
months_test = sorted(test_df['month'].unique())

for tier_name, cond in [
    ('RAW', pd.Series(True, index=test_df.index)),
    ('CONFIRMED', (test_df['lr_prob'] > 0.7) & (test_df['gb_prob'] > 0.7)),
    ('HIGH', test_df['gb_prob'] > 0.95)
]:
    tdf = test_df[cond]
    print(f"\n--- {tier_name} ---")
    print(f"{'Month':<10} | {'FIRST_BAR':>14} | {'HOD_BREAK':>14} | {'HAMMER':>14} | {'GAP_NOT_FIL':>14}")
    print("-" * 80)

    strat_mwr = {s: {} for s in current_strats}
    for m in months_test:
        parts = [f"{m:<10}"]
        for strat in current_strats:
            sub = tdf[(tdf['strategy'] == strat) & (tdf['month'] == m)]
            if len(sub) > 0:
                wr = sub['label'].mean() * 100
                strat_mwr[strat][m] = wr
                parts.append(f"{wr:5.1f}% ({len(sub):3d})")
            else:
                parts.append("   —        ")
        print(" | ".join(parts))

    print("-" * 80)
    parts = ["OVERALL   "]
    for strat in current_strats:
        sub = tdf[tdf['strategy'] == strat]
        if len(sub) > 0:
            parts.append(f"{sub['label'].mean()*100:5.1f}% ({len(sub):3d})")
        else:
            parts.append("   —        ")
    print(" | ".join(parts))

    print(f"\n  Detail ({tier_name}):")
    for strat in current_strats:
        sub = tdf[tdf['strategy'] == strat]
        if len(sub) == 0:
            print(f"    {strat}: NO SIGNALS"); continue
        wr = sub['label'].mean() * 100
        ar = sub['return_pct'].mean()
        mw = list(strat_mwr[strat].values())
        std = np.std(mw) if len(mw) > 1 else 0
        worst = min(mw) if mw else 0
        w = sub[sub['return_pct'] > 0]
        l = sub[sub['return_pct'] <= 0]
        pf = abs(w['return_pct'].sum() / l['return_pct'].sum()) if len(l) > 0 and l['return_pct'].sum() != 0 else 999
        print(f"    {strat}: N={len(sub)}, WR={wr:.1f}%, AvgRet={ar:+.2f}%, PF={pf:.2f}, Std={std:.1f}%, Worst={worst:.0f}%, N/mo={len(sub)/max(len(months_test),1):.1f}, Consistent={'YES' if std<10 else 'NO'}")

# TABLE 2: All 10 Strategies
print("\n" + "=" * 80)
print("TABLE 2: ALL 10 STRATEGIES COMPARISON")
print("=" * 80)
print(f"{'Strategy':<22} | {'N':>5} | {'RAW WR':>7} | {'AvgRet':>7} | {'PF':>5} | {'CONF_N':>6} | {'CONF_WR':>7} | {'HI_N':>5} | {'HI_WR':>7} | {'StdWR':>6} | {'Worst':>6} | {'OK':>3}")
print("-" * 120)

for strat in STRATEGY_NAMES:
    sr = test_df[test_df['strategy'] == strat]
    sc = test_df[(test_df['strategy'] == strat) & (test_df['lr_prob'] > 0.7) & (test_df['gb_prob'] > 0.7)]
    sh = test_df[(test_df['strategy'] == strat) & (test_df['gb_prob'] > 0.95)]
    if len(sr) == 0:
        print(f"{strat:<22} | {'—':>5} | {'—':>7} | {'—':>7} | {'—':>5} | {'—':>6} | {'—':>7} | {'—':>5} | {'—':>7} | {'—':>6} | {'—':>6} | {'—':>3}")
        continue
    rwr = sr['label'].mean()*100
    ar = sr['return_pct'].mean()
    w = sr[sr['return_pct']>0]; l = sr[sr['return_pct']<=0]
    pf = abs(w['return_pct'].sum()/l['return_pct'].sum()) if len(l)>0 and l['return_pct'].sum()!=0 else 999
    mwrs = sr.groupby('month')['label'].mean()*100
    std = mwrs.std() if len(mwrs)>1 else 0
    wst = mwrs.min()
    cwr = sc['label'].mean()*100 if len(sc)>0 else 0
    hwr = sh['label'].mean()*100 if len(sh)>0 else 0
    ok = 'YES' if std < 10 else 'NO'
    print(f"{strat:<22} | {len(sr):5d} | {rwr:6.1f}% | {ar:+6.2f}% | {pf:5.2f} | {len(sc):6d} | {cwr:6.1f}% | {len(sh):5d} | {hwr:6.1f}% | {std:5.1f}% | {wst:5.0f}% | {ok:>3}")

# TABLE 3: Feature Importance
print("\n" + "=" * 80)
print("TABLE 3: FEATURE IMPORTANCE ANALYSIS")
print("=" * 80)

if all_gb_imp:
    avg_imp = np.mean(all_gb_imp, axis=0)
    imp_order = np.argsort(-avg_imp)
    print("\nGradientBoosting Feature Importance (avg across folds):")
    print(f"{'Rank':>4} | {'Feature':<22} | {'Importance':>10}")
    print("-" * 42)
    for rank, i in enumerate(imp_order):
        print(f"{rank+1:4d} | {FEATURE_COLS[i]:<22} | {avg_imp[i]:10.4f}")

if all_lr_coef:
    avg_c = np.mean(all_lr_coef, axis=0)
    c_order = np.argsort(-avg_c)
    print("\nLogistic Regression Coefficients (standardized):")
    print(f"{'Rank':>4} | {'Feature':<22} | {'Coefficient':>12}")
    print("-" * 44)
    for rank, i in enumerate(c_order):
        print(f"{rank+1:4d} | {FEATURE_COLS[i]:<22} | {avg_c[i]:+12.4f}")

# Non-linear analyses
tc = test_df.copy()
for label, col, bins, names in [
    ('Gap %', 'gap_pct', [1,2,3,4,6,10,100], ['1-2%','2-3%','3-4%','4-6%','6-10%','10%+']),
    ('VIX', 'vix_close', [0,15,20,25,30,100], ['<15','15-20','20-25','25-30','30+']),
    ('Vol Ratio', 'volume_ratio', [0,0.5,1,2,4,100], ['<0.5x','0.5-1x','1-2x','2-4x','4x+']),
    ('RSI', 'rsi_approx', [0,30,40,50,60,70,100], ['<30','30-40','40-50','50-60','60-70','70+']),
    ('Mkt Cap', 'market_cap_log', [0,9,10,11,12,20], ['<1B','1-10B','10-100B','100B-1T','1T+']),
    ('Momentum 5d', 'mom_5d', [-100,-5,-2,0,2,5,100], ['<-5%','-5 to -2%','-2 to 0%','0-2%','2-5%','5%+']),
    ('Beta', 'beta', [0,0.5,1,1.5,2,10], ['<0.5','0.5-1','1-1.5','1.5-2','2+']),
]:
    tc['_bucket'] = pd.cut(tc[col], bins=bins, labels=names)
    ga = tc.groupby('_bucket', observed=True).agg(N=('label','count'), WR=('label','mean'), AvgRet=('return_pct','mean'))
    print(f"\nWin Rate by {label}:")
    print(f"{'Bucket':<12} | {'N':>6} | {'WR':>7} | {'AvgRet':>8}")
    print("-" * 40)
    for idx, r in ga.iterrows():
        print(f"{str(idx):<12} | {r['N']:6.0f} | {r['WR']*100:6.1f}% | {r['AvgRet']:+7.2f}%")

# High vs Low WR months
print("\nFeature Means: HIGH WR months (>65%) vs LOW WR months (<45%)")
ms = test_df.groupby('month').agg(WR=('label','mean'), **{f: (f,'mean') for f in FEATURE_COLS})
hm, lm = ms[ms['WR'] > 0.65], ms[ms['WR'] < 0.45]
if len(hm) > 0 and len(lm) > 0:
    print(f"  High WR months: {list(hm.index)}")
    print(f"  Low WR months: {list(lm.index)}")
    print(f"{'Feature':<22} | {'HighWR':>10} | {'LowWR':>10} | {'Diff':>8}")
    print("-" * 56)
    for f in FEATURE_COLS:
        print(f"{f:<22} | {hm[f].mean():10.3f} | {lm[f].mean():10.3f} | {hm[f].mean()-lm[f].mean():+8.3f}")

# FINAL SUMMARY
print("\n" + "=" * 80)
print("FINAL SUMMARY & RECOMMENDATIONS")
print("=" * 80)
for tier_name, cond, min_n in [
    ('CONFIRMED', (test_df['lr_prob']>0.7) & (test_df['gb_prob']>0.7), 20),
    ('HIGH', test_df['gb_prob']>0.95, 10)
]:
    print(f"\nTop by {tier_name} (min N={min_n}):")
    res = []
    for strat in STRATEGY_NAMES:
        sub = test_df[cond & (test_df['strategy']==strat)]
        if len(sub) >= min_n:
            res.append((strat, len(sub), sub['label'].mean()*100, sub['return_pct'].mean()))
    for s, n, wr, ar in sorted(res, key=lambda x: -x[2]):
        v = "STRONG" if wr >= 60 and n >= 50 else "MODERATE" if wr >= 55 else "WEAK"
        print(f"  {s:<22}: WR={wr:.1f}%, N={n}, AvgRet={ar:+.2f}%, {v}")

print("\n" + "=" * 80)
print("BACKTEST COMPLETE")
print("=" * 80)
