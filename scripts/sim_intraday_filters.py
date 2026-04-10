#!/usr/bin/env python3
"""
Comprehensive intraday strategy filter backtest.
Tests 40+ filter combinations on 3 strategies.

Matches exact strategy definitions from backtest_walkforward_final.py:
  FIRST_BAR_CONFIRM: gap>=1%, 09:40-10:30, ret_from_open>0.8%, gap not filled
  GAP_NOT_FILLED: gap>=2%, 10:00-11:00, gap not filled, price>open
  RECLAIM_OPEN: gap>=1%, 10:00-12:00, dipped below open, reclaimed, green bar

Walk through bars day-by-day per symbol. Entry = signal bar close, exit = day close.
"""
import sys, os, time, gc, warnings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
warnings.filterwarnings('ignore')
sys.stdout.reconfigure(line_buffering=True)

import numpy as np
import pandas as pd
from collections import defaultdict
from database.orm.base import get_session
from sqlalchemy import text

DB_PATH = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'

# ─── Step 1: Load reference data ────────────────────────────────
print("=" * 90)
print("INTRADAY STRATEGY FILTER BACKTEST — 3 strategies × 40+ filters")
print("=" * 90)
print("\nStep 1: Loading reference data...")
t0 = time.time()

with get_session() as sess:
    macro_rows = sess.execute(text("SELECT date, vix_close FROM macro_snapshots")).fetchall()
    macro_dict = {r[0]: r[1] for r in macro_rows}

    breadth_rows = sess.execute(text("SELECT date, pct_above_50d_ma, pct_above_20d_ma FROM market_breadth")).fetchall()
    breadth_dict = {r[0]: {'pct_above_50d': r[1], 'pct_above_20d': r[2]} for r in breadth_rows}

    fund_rows = sess.execute(text("SELECT symbol, beta, market_cap, sector FROM stock_fundamentals")).fetchall()
    fund_dict = {r[0]: {'beta': r[1], 'market_cap': r[2], 'sector': r[3]} for r in fund_rows}

    sector_rows = sess.execute(text("SELECT date, sector, pct_change FROM sector_etf_daily_returns")).fetchall()
    sector_ret_dict = {}
    spy_ret_dict = {}
    for r in sector_rows:
        sector_ret_dict[(r[0], r[1])] = r[2]
        if r[1] == 'S&P 500':
            spy_ret_dict[r[0]] = r[2]

    dates_rows = sess.execute(text(
        "SELECT DISTINCT date FROM intraday_bars_5m WHERE date >= '2024-01-01' ORDER BY date"
    )).fetchall()
    all_intraday_dates = [r[0] for r in dates_rows]

print(f"  Macro: {len(macro_dict)}, Breadth: {len(breadth_dict)}, Fund: {len(fund_dict)}")
print(f"  Sector returns: {len(sector_ret_dict)}, Dates: {len(all_intraday_dates)}")
print(f"  {time.time()-t0:.1f}s")

# Build sorted dates list for prev-date lookup
sorted_dates = sorted(macro_dict.keys())
date_to_idx = {d: i for i, d in enumerate(sorted_dates)}

def get_prev_trading_date(dt):
    idx = date_to_idx.get(dt)
    if idx and idx > 0:
        return sorted_dates[idx - 1]
    return None


# ─── Step 2: Vectorized daily features ──────────────────────────
print("\nStep 2: Computing daily features (vectorized pandas)...")
t0 = time.time()

with get_session() as sess:
    daily_df = pd.read_sql(
        "SELECT symbol, date, open, high, low, close, volume FROM stock_daily_ohlc "
        "WHERE date >= '2023-06-01' ORDER BY symbol, date",
        sess.connection()
    )

print(f"  Loaded {len(daily_df):,} daily rows in {time.time()-t0:.1f}s")

daily_df = daily_df.sort_values(['symbol', 'date']).reset_index(drop=True)

# IMPORTANT: ALL features must be known BEFORE market open on scan_date.
# This means we can only use data up to PREVIOUS day's close.
# Every feature must be shifted by 1 to avoid leakage.

daily_df['prev_close'] = daily_df.groupby('symbol')['close'].shift(1)
daily_df['prev_open'] = daily_df.groupby('symbol')['open'].shift(1)
daily_df['prev_green'] = (daily_df.groupby('symbol')['close'].shift(1) > daily_df.groupby('symbol')['open'].shift(1)).astype(int)

# Momentum: shift(1) means prev_close / close_6d_ago (no today leakage)
daily_df['mom_5d'] = (daily_df.groupby('symbol')['close'].shift(1) / daily_df.groupby('symbol')['close'].shift(6) - 1) * 100
daily_df['mom_20d'] = (daily_df.groupby('symbol')['close'].shift(1) / daily_df.groupby('symbol')['close'].shift(21) - 1) * 100

# ATR: use only prev day and before (shift everything by 1)
daily_df['tr'] = daily_df['high'] - daily_df['low']
daily_df['tr2'] = (daily_df['high'] - daily_df['prev_close']).abs()
daily_df['tr3'] = (daily_df['low'] - daily_df['prev_close']).abs()
daily_df['true_range'] = daily_df[['tr', 'tr2', 'tr3']].max(axis=1)
# ATR up to prev day (shift by 1)
daily_df['atr_14'] = daily_df.groupby('symbol')['true_range'].transform(
    lambda x: x.shift(1).rolling(14, min_periods=1).mean()
)
daily_df['atr_pct'] = daily_df['atr_14'] / daily_df['prev_close'] * 100

# Distance from 20d high (using highs up to prev day)
daily_df['high_20d'] = daily_df.groupby('symbol')['high'].transform(
    lambda x: x.shift(1).rolling(20, min_periods=1).max()
)
daily_df['dist_from_20d_high'] = (daily_df['prev_close'] / daily_df['high_20d'] - 1) * 100

# Distance from 52w high (using highs up to prev day)
daily_df['high_252d'] = daily_df.groupby('symbol')['high'].transform(
    lambda x: x.shift(1).rolling(252, min_periods=20).max()
)
daily_df['dist_from_52w_high'] = (daily_df['prev_close'] / daily_df['high_252d'] - 1) * 100

# Volume: prev day's volume / 20d avg (all shifted by 1 to exclude today)
daily_df['avg_vol_20d'] = daily_df.groupby('symbol')['volume'].transform(
    lambda x: x.shift(1).rolling(20, min_periods=1).mean()
)
# vol_ratio_daily = yesterday's volume / avg of days before yesterday
daily_df['prev_volume'] = daily_df.groupby('symbol')['volume'].shift(1)
daily_df['vol_ratio_daily'] = daily_df['prev_volume'] / daily_df['avg_vol_20d']

# Consecutive green days: streak AS OF prev day close (shift by 1)
daily_df['green'] = (daily_df['close'] > daily_df['open']).astype(int)
daily_df['green_streak_raw'] = 0
for sym, grp in daily_df.groupby('symbol'):
    streak = 0
    streaks = []
    for _, row in grp.iterrows():
        if row['green']:
            streak += 1
        else:
            streak = 0
        streaks.append(streak)
    daily_df.loc[grp.index, 'green_streak_raw'] = streaks
# Shift by 1: streak as of PREVIOUS day (known before market open)
daily_df['green_streak'] = daily_df.groupby('symbol')['green_streak_raw'].shift(1).fillna(0).astype(int)

# Day of week (this is today's date - no leakage, it's calendar info)
daily_df['day_of_week'] = pd.to_datetime(daily_df['date']).dt.dayofweek

daily_df = daily_df.dropna(subset=['prev_close', 'mom_5d']).copy()

# Build lookup
feat_cols = ['prev_close', 'prev_green', 'mom_5d', 'mom_20d', 'atr_pct',
             'dist_from_20d_high', 'dist_from_52w_high', 'avg_vol_20d',
             'vol_ratio_daily', 'green_streak', 'day_of_week',
             'open', 'close']
daily_features = {}
for row in daily_df[['symbol', 'date'] + feat_cols].itertuples(index=False):
    daily_features[(row[0], row[1])] = {
        'prev_close': row[2], 'prev_green': row[3], 'mom_5d': row[4], 'mom_20d': row[5],
        'atr_pct': row[6], 'dist_from_20d_high': row[7], 'dist_from_52w_high': row[8],
        'avg_vol_20d': row[9], 'vol_ratio_daily': row[10], 'green_streak': row[11],
        'day_of_week': row[12], 'day_open': row[13], 'day_close': row[14],
    }

print(f"  Features: {len(daily_features):,} entries in {time.time()-t0:.1f}s")
del daily_df
gc.collect()

# ─── Step 3: Scan intraday bars ─────────────────────────────────
print("\nStep 3: Scanning intraday bars for 3 strategies...")
t0 = time.time()
all_signals = []
n_dates = len(all_intraday_dates)

for di, scan_date in enumerate(all_intraday_dates):
    if di % 50 == 0:
        elapsed = time.time() - t0
        rate = (di + 1) / max(elapsed, 0.01)
        eta = (n_dates - di) / rate / 60
        print(f"  [{di+1}/{n_dates}] {scan_date} | {elapsed:.0f}s | ETA {eta:.1f}min | signals: {len(all_signals):,}")

    # Get prev trading date for macro/breadth (no leakage)
    prev_date = get_prev_trading_date(scan_date)

    vix_val = macro_dict.get(prev_date, 20) or 20 if prev_date else 20
    breadth_data = breadth_dict.get(prev_date, {'pct_above_50d': 50, 'pct_above_20d': 50}) if prev_date else {'pct_above_50d': 50, 'pct_above_20d': 50}
    breadth_50d = breadth_data.get('pct_above_50d') or 50
    breadth_20d = breadth_data.get('pct_above_20d') or 50
    spy_prev_ret = spy_ret_dict.get(prev_date, 0) if prev_date else 0

    with get_session() as sess:
        rows = sess.execute(text(
            "SELECT symbol, time_et, open, high, low, close, volume "
            "FROM intraday_bars_5m "
            "WHERE date = :d AND time_et >= '09:30' AND time_et <= '16:00' "
            "ORDER BY symbol, time_et"
        ), {'d': scan_date}).fetchall()

    if not rows:
        continue

    sym_bars = defaultdict(list)
    for r in rows:
        sym_bars[r[0]].append(r[1:])

    for sym, bars_raw in sym_bars.items():
        feat = daily_features.get((sym, scan_date))
        if feat is None or len(bars_raw) < 5:
            continue

        prev_close = feat['prev_close']
        if not prev_close or prev_close <= 0:
            continue

        f_info = fund_dict.get(sym, {})
        market_cap = f_info.get('market_cap') or 0
        sector = f_info.get('sector') or ''
        beta = f_info.get('beta') or 1.0

        day_open = bars_raw[0][1]  # open of first bar
        gap_pct = (day_open / prev_close - 1) * 100
        if gap_pct < 1.0:
            continue

        day_close_price = bars_raw[-1][4]  # close of last bar

        # Sector prev day return
        sector_prev_ret = sector_ret_dict.get((prev_date, sector), 0) if prev_date else 0

        n_bars = len(bars_raw)
        times = [b[0] for b in bars_raw]
        opens = [b[1] for b in bars_raw]
        highs = [b[2] for b in bars_raw]
        lows = [b[3] for b in bars_raw]
        closes = [b[4] for b in bars_raw]
        vols = [b[5] for b in bars_raw]
        is_green = [closes[i] > opens[i] for i in range(n_bars)]

        rlo = list(np.minimum.accumulate(lows))
        any_gap_filled = False
        found = set()

        # Common features for all signals from this symbol-day
        base_feat = {
            'symbol': sym,
            'date': scan_date,
            'gap_pct': gap_pct,
            'market_cap': market_cap,
            'sector': sector,
            'beta': beta,
            'prev_green': feat['prev_green'],
            'mom_5d': feat['mom_5d'] or 0,
            'mom_20d': feat['mom_20d'] or 0,
            'atr_pct': feat['atr_pct'] or 2.0,
            'dist_from_20d_high': feat['dist_from_20d_high'] or 0,
            'dist_from_52w_high': feat['dist_from_52w_high'] or 0,
            'vol_ratio_daily': feat['vol_ratio_daily'] or 1.0,
            'green_streak': feat['green_streak'] or 0,
            'day_of_week': feat['day_of_week'],
            'vix': vix_val,
            'breadth_50d': breadth_50d,
            'breadth_20d': breadth_20d,
            'sector_prev_ret': sector_prev_ret,
            'spy_prev_ret': spy_prev_ret,
        }

        for bi in range(n_bars):
            t = times[bi]
            if lows[bi] <= prev_close:
                any_gap_filled = True

            ret_from_open = (closes[bi] / day_open - 1) * 100 if day_open > 0 else 0
            first_bar_ret = (closes[bi] / opens[bi] - 1) * 100 if opens[bi] > 0 else 0

            # Volume ratio (cumulative 30-min vs daily avg)
            cum_vol = sum(vols[:bi+1])
            avg_daily = feat['avg_vol_20d'] or 1
            vol_ratio_intraday = cum_vol / max(avg_daily / 13, 1)

            entry_price = closes[bi]
            if entry_price <= 0:
                continue
            pnl_pct = (day_close_price / entry_price - 1) * 100
            win = 1 if day_close_price > entry_price else 0

            # ── S1: FIRST_BAR_CONFIRM ──
            if ('FBC' not in found
                    and '09:40' <= t <= '10:30'
                    and ret_from_open > 0.8
                    and not any_gap_filled):
                found.add('FBC')
                all_signals.append({
                    'strategy': 'FIRST_BAR_CONFIRM',
                    'entry_price': entry_price, 'exit_price': day_close_price,
                    'pnl_pct': pnl_pct, 'win': win,
                    'ret_from_open': ret_from_open,
                    'first_bar_ret': first_bar_ret,
                    'entry_bar': t,
                    'vol_ratio_intraday': vol_ratio_intraday,
                    **base_feat,
                })

            # ── S2: GAP_NOT_FILLED ──
            if ('GNF' not in found
                    and gap_pct >= 2.0
                    and '10:00' <= t <= '11:00'
                    and not any_gap_filled
                    and closes[bi] > day_open):
                found.add('GNF')
                all_signals.append({
                    'strategy': 'GAP_NOT_FILLED',
                    'entry_price': entry_price, 'exit_price': day_close_price,
                    'pnl_pct': pnl_pct, 'win': win,
                    'ret_from_open': ret_from_open,
                    'first_bar_ret': first_bar_ret,
                    'entry_bar': t,
                    'vol_ratio_intraday': vol_ratio_intraday,
                    **base_feat,
                })

            # ── S3: RECLAIM_OPEN ──
            if ('RO' not in found
                    and '10:00' <= t <= '12:00'
                    and bi >= 2):
                dipped = any(lows[j] < day_open for j in range(bi))
                if dipped and closes[bi] > day_open and is_green[bi] and not any_gap_filled:
                    found.add('RO')
                    all_signals.append({
                        'strategy': 'RECLAIM_OPEN',
                        'entry_price': entry_price, 'exit_price': day_close_price,
                        'pnl_pct': pnl_pct, 'win': win,
                        'ret_from_open': ret_from_open,
                        'first_bar_ret': first_bar_ret,
                        'entry_bar': t,
                        'vol_ratio_intraday': vol_ratio_intraday,
                        **base_feat,
                    })

            if len(found) == 3:
                break

    del rows
    if di % 100 == 0:
        gc.collect()

elapsed = time.time() - t0
print(f"\n  Total signals: {len(all_signals):,} in {elapsed:.0f}s")

# ─── Step 4: Build DataFrame and test filters ───────────────────
print("\nStep 4: Testing filter combinations...")

sig_df = pd.DataFrame(all_signals)
print(f"  Total signals: {len(sig_df):,}")

for strat in ['FIRST_BAR_CONFIRM', 'GAP_NOT_FILLED', 'RECLAIM_OPEN']:
    sub = sig_df[sig_df['strategy'] == strat]
    wr = sub['win'].mean() * 100 if len(sub) > 0 else 0
    print(f"  {strat}: N={len(sub):,}, Base WR={wr:.1f}%")


def compute_pf(df):
    if len(df) == 0:
        return 0
    w = df[df['pnl_pct'] > 0]['pnl_pct'].sum()
    l = abs(df[df['pnl_pct'] < 0]['pnl_pct'].sum())
    return w / l if l > 0 else 99.9


def test_filters(base_df, strategy_name, min_n=200):
    """Test all filter combinations on a strategy's base signal set."""
    results = []
    n = len(base_df)
    if n == 0:
        return results

    wr = base_df['win'].mean() * 100
    pf = compute_pf(base_df)
    avg = base_df['pnl_pct'].mean()
    results.append({'filter': 'BASELINE', 'n': n, 'wr': wr, 'pf': pf, 'avg': avg})

    # Define all filters as (name, mask) pairs
    filters = {}

    # Macro (prev day - already no leakage since we used prev_date)
    filters['vix<20'] = base_df['vix'] < 20
    filters['vix<18'] = base_df['vix'] < 18
    filters['vix<15'] = base_df['vix'] < 15
    filters['breadth50d>50'] = base_df['breadth_50d'] > 50
    filters['breadth50d>60'] = base_df['breadth_50d'] > 60
    filters['breadth50d>70'] = base_df['breadth_50d'] > 70
    filters['breadth20d>50'] = base_df['breadth_20d'] > 50
    filters['breadth20d>60'] = base_df['breadth_20d'] > 60

    # Stock quality
    filters['mcap>50B'] = base_df['market_cap'] > 50e9
    filters['mcap>100B'] = base_df['market_cap'] > 100e9
    filters['mcap>200B'] = base_df['market_cap'] > 200e9
    filters['prev_green'] = base_df['prev_green'] == 1
    filters['streak>=2'] = base_df['green_streak'] >= 2
    filters['streak>=3'] = base_df['green_streak'] >= 3
    filters['mom5d>0'] = base_df['mom_5d'] > 0
    filters['mom5d>3'] = base_df['mom_5d'] > 3
    filters['mom5d>5'] = base_df['mom_5d'] > 5
    filters['near_20d(<-3%)'] = base_df['dist_from_20d_high'] > -3
    filters['near_20d(<-5%)'] = base_df['dist_from_20d_high'] > -5
    filters['near_52w(<-5%)'] = base_df['dist_from_52w_high'] > -5
    filters['near_52w(<-10%)'] = base_df['dist_from_52w_high'] > -10
    filters['vol_prev>1.5x'] = base_df['vol_ratio_daily'] > 1.5

    # Gap quality
    filters['gap1-3'] = (base_df['gap_pct'] >= 1) & (base_df['gap_pct'] <= 3)
    filters['gap1-2'] = (base_df['gap_pct'] >= 1) & (base_df['gap_pct'] <= 2)
    filters['gap2-4'] = (base_df['gap_pct'] >= 2) & (base_df['gap_pct'] <= 4)
    filters['gap2-3'] = (base_df['gap_pct'] >= 2) & (base_df['gap_pct'] <= 3)
    filters['gap>3'] = base_df['gap_pct'] >= 3
    filters['gap>4'] = base_df['gap_pct'] >= 4

    # Sector/market
    filters['sector_up_prev'] = base_df['sector_prev_ret'] > 0
    filters['sector_up>0.5'] = base_df['sector_prev_ret'] > 0.5
    filters['spy_green_prev'] = base_df['spy_prev_ret'] > 0

    # Day of week
    filters['monday'] = base_df['day_of_week'] == 0
    filters['tuesday'] = base_df['day_of_week'] == 1
    filters['wednesday'] = base_df['day_of_week'] == 2
    filters['thursday'] = base_df['day_of_week'] == 3
    filters['friday'] = base_df['day_of_week'] == 4
    filters['mon_tue_thu'] = base_df['day_of_week'].isin([0, 1, 3])
    filters['not_friday'] = base_df['day_of_week'] != 4
    filters['not_monday'] = base_df['day_of_week'] != 0

    # Strategy-specific: ret_from_open thresholds
    filters['ret>1.0'] = base_df['ret_from_open'] > 1.0
    filters['ret>1.5'] = base_df['ret_from_open'] > 1.5
    filters['ret>2.0'] = base_df['ret_from_open'] > 2.0
    filters['ret>2.5'] = base_df['ret_from_open'] > 2.5
    filters['ret>3.0'] = base_df['ret_from_open'] > 3.0

    # First bar return
    filters['fb_ret>0.5'] = base_df['first_bar_ret'] > 0.5
    filters['fb_ret>1.0'] = base_df['first_bar_ret'] > 1.0

    # ATR filter
    filters['atr<3'] = base_df['atr_pct'] < 3
    filters['atr<2'] = base_df['atr_pct'] < 2

    # Beta filter
    filters['beta<1.5'] = base_df['beta'] < 1.5
    filters['beta<1.2'] = base_df['beta'] < 1.2

    # Test singles
    print(f"    Testing {len(filters)} individual filters...")
    single_results = {}
    for name, mask in filters.items():
        filtered = base_df[mask]
        nn = len(filtered)
        if nn >= 30:  # Track even small N for combination building
            w = filtered['win'].mean() * 100
            single_results[name] = {'wr': w, 'n': nn, 'mask': mask}
            if nn >= min_n:
                results.append({
                    'filter': name, 'n': nn,
                    'wr': w, 'pf': compute_pf(filtered),
                    'avg': filtered['pnl_pct'].mean(),
                })

    # Test pairs of top 20 by WR
    sorted_singles = sorted(single_results.items(), key=lambda x: x[1]['wr'], reverse=True)[:20]
    print(f"    Testing pairs of top {len(sorted_singles)} filters...")
    pair_results = {}
    for i, (n1, r1) in enumerate(sorted_singles):
        for j, (n2, r2) in enumerate(sorted_singles):
            if j <= i:
                continue
            mask = filters[n1] & filters[n2]
            filtered = base_df[mask]
            nn = len(filtered)
            if nn >= 30:
                w = filtered['win'].mean() * 100
                key = f"{n1} + {n2}"
                pair_results[key] = {'wr': w, 'n': nn, 'mask': mask}
                if nn >= min_n:
                    results.append({
                        'filter': key, 'n': nn,
                        'wr': w, 'pf': compute_pf(filtered),
                        'avg': filtered['pnl_pct'].mean(),
                    })

    # Test triples of top 12
    top12 = sorted_singles[:12]
    print(f"    Testing triples of top {len(top12)} filters...")
    for i, (n1, _) in enumerate(top12):
        for j, (n2, _) in enumerate(top12):
            if j <= i:
                continue
            for k, (n3, _) in enumerate(top12):
                if k <= j:
                    continue
                mask = filters[n1] & filters[n2] & filters[n3]
                filtered = base_df[mask]
                nn = len(filtered)
                if nn >= min_n:
                    w = filtered['win'].mean() * 100
                    results.append({
                        'filter': f"{n1} + {n2} + {n3}", 'n': nn,
                        'wr': w, 'pf': compute_pf(filtered),
                        'avg': filtered['pnl_pct'].mean(),
                    })

    # Also test top pairs × top singles (quad combinations from best pairs)
    sorted_pairs = sorted(pair_results.items(), key=lambda x: x[1]['wr'], reverse=True)[:10]
    for pair_name, pair_data in sorted_pairs:
        for single_name, single_data in sorted_singles[:10]:
            if single_name in pair_name:
                continue
            mask = pair_data['mask'] & filters[single_name]
            filtered = base_df[mask]
            nn = len(filtered)
            if nn >= min_n:
                w = filtered['win'].mean() * 100
                results.append({
                    'filter': f"{pair_name} + {single_name}", 'n': nn,
                    'wr': w, 'pf': compute_pf(filtered),
                    'avg': filtered['pnl_pct'].mean(),
                })

    return results


def print_results(results, strategy, top_n=25, min_n_display=200):
    res_df = pd.DataFrame(results)
    # Show results at different N thresholds
    for min_n in [200, 100, 50]:
        valid = res_df[res_df['n'] >= min_n].sort_values('wr', ascending=False)
        if len(valid) <= 1:
            continue

        print(f"\n{'='*100}")
        print(f"  {strategy} — Top filters (N >= {min_n})")
        print(f"{'='*100}")
        print(f"{'Rank':<5} {'Filter':<60} {'N':>6} {'WR%':>7} {'PF':>7} {'Avg%':>7}")
        print(f"{'-'*100}")

        shown = 0
        for _, row in valid.head(top_n).iterrows():
            shown += 1
            marker = " <-- 75%+" if row['wr'] >= 75 else (" <-- 70%+" if row['wr'] >= 70 else "")
            print(f"{shown:<5} {row['filter']:<60} {row['n']:>6} {row['wr']:>6.1f}% {row['pf']:>6.2f} {row['avg']:>6.2f}%{marker}")

        # Baseline
        baseline = res_df[res_df['filter'] == 'BASELINE']
        if len(baseline) > 0:
            b = baseline.iloc[0]
            print(f"\n  Baseline: N={b['n']:,}, WR={b['wr']:.1f}%, PF={b['pf']:.2f}, Avg={b['avg']:.2f}%")

    return res_df


# Run for each strategy
all_results = {}
for strat in ['FIRST_BAR_CONFIRM', 'GAP_NOT_FILLED', 'RECLAIM_OPEN']:
    print(f"\n{'#'*100}")
    print(f"  Processing: {strat}")
    print(f"{'#'*100}")

    base = sig_df[sig_df['strategy'] == strat].copy()
    if len(base) == 0:
        print("  No signals! Skipping.")
        continue

    results = test_filters(base, strat, min_n=200)
    res_df = print_results(results, strat)
    all_results[strat] = results

# ─── Final Summary ──────────────────────────────────────────────
print(f"\n{'='*100}")
print("  FINAL SUMMARY")
print(f"{'='*100}")

for strat, results in all_results.items():
    res_df = pd.DataFrame(results)
    print(f"\n  {strat}:")
    for min_n in [200, 100, 50]:
        valid = res_df[(res_df['n'] >= min_n) & (res_df['filter'] != 'BASELINE')]
        if len(valid) > 0:
            best = valid.sort_values('wr', ascending=False).iloc[0]
            baseline = res_df[res_df['filter'] == 'BASELINE'].iloc[0]
            lift = best['wr'] - baseline['wr']
            print(f"    N>={min_n:>3}: WR={best['wr']:.1f}% (+{lift:.1f}pp), N={best['n']}, PF={best['pf']:.2f} | {best['filter']}")

print(f"\n{'='*100}")
print("  DONE")
print(f"{'='*100}")
