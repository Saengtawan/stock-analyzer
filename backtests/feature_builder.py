"""
Feature builder: Build training pkl from scratch for ANY date range.

Usage:
    python3 backtests/feature_builder.py --start 2021-01-01 --end 2026-04-22 --output /tmp/bt_features_v16.pkl

Produces pkl with:
- 63 base features (same as v13)
- 17 cross-asset features (ETF intraday + spreads)
- 1 anomaly score
- Labels: decay_pnl, fixed3_pnl, label_tp1, label_profit, label_big

This script is the FOUNDATION for all retraining.
"""
import argparse
import os
import sqlite3
import sys
import time as _time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

DB_PATH = '/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db'

# Top 200 stocks + sector ETFs
SECTOR_ETFS = ['XLE','XLK','XLV','XLP','XLU','XLF','XLI','XLY','XLC','XLB','XLRE']
CROSS_ETFS = ['SPY','QQQ','IWM','USO','VXX','GLD','HYG','IGV','DBC','UUP','EEM','LQD','TLT','IEF','SMH']
ALL_ETFS = list(set(SECTOR_ETFS + CROSS_ETFS))

# Anomaly baseline (from 2021-2026 historical)
ETF_BASELINES = {
    'USO': (-0.02, 0.61), 'VXX': (0.04, 1.74), 'IWM': (-0.01, 0.59),
    'SPY': (-0.19, 0.52), 'XLE': (0.04, 0.85), 'XLK': (0.01, 0.58),
    'GLD': (-0.01, 0.32), 'TLT': (-0.00, 0.31),
}


def mfo_to_time(mfo):
    h = 9 + (30 + mfo) // 60
    m = (30 + mfo) % 60
    return f"{h:02d}:{m:02d}"


def compute_path_features(past_bars, day_open):
    """Compute 20 path features from bars up to entry."""
    n = len(past_bars)
    if n < 4 or day_open <= 0:
        return {k: 0.0 for k in [
            'path_r_squared','path_peak_diff','path_low_diff','path_consol_range',
            'path_max_drawdown','path_choppiness','path_speed_late','path_speed_accel',
            'path_momentum_accel','path_speed_early','path_up_vol_ratio','path_support_touches',
            'path_bar_size_trend','path_wick_ratio','path_lower_wick_ratio','path_gap_ratio',
            'path_time_at_high','path_vol_at_peaks','path_vwap_slope','path_ret_skewness']}

    gains_c = [(b[4]/day_open - 1) * 100 for b in past_bars]  # close
    gains_h = [(b[2]/day_open - 1) * 100 for b in past_bars]  # high
    gains_l = [(b[3]/day_open - 1) * 100 for b in past_bars]  # low

    # R-squared
    x = np.arange(len(gains_c))
    corr = np.corrcoef(x, gains_c)[0, 1]
    r_sq = corr ** 2 if not np.isnan(corr) else 0

    # Peaks/lows
    peaks = [gains_h[i] for i in range(1, len(gains_h)-1) if gains_h[i] > gains_h[i-1] and gains_h[i] > gains_h[i+1]]
    lows = [gains_l[i] for i in range(1, len(gains_l)-1) if gains_l[i] < gains_l[i-1] and gains_l[i] < gains_l[i+1]]
    peak_diff = (peaks[-1] - peaks[-2]) if len(peaks) >= 2 else 0
    low_diff = (lows[-1] - lows[-2]) if len(lows) >= 2 else 0

    # Consolidation
    last4 = past_bars[-min(4, n):]
    consol = (max(b[2] for b in last4) - min(b[3] for b in last4)) / day_open * 100

    # Max drawdown
    running_max = gains_c[0]
    max_dd = 0
    for g in gains_c:
        if g > running_max: running_max = g
        dd = g - running_max
        if dd < max_dd: max_dd = dd

    # Choppiness
    changes = sum(1 for i in range(2, n) if (gains_c[i]-gains_c[i-1])*(gains_c[i-1]-gains_c[i-2]) < 0)
    chop = changes / n if n > 0 else 0

    # Speed features
    third = max(1, n // 3)
    early_speed = (gains_c[third] - gains_c[0]) / (third * 5) if third > 0 else 0
    late_speed = (gains_c[-1] - gains_c[-third]) / (third * 5) if third > 0 else 0
    speed_accel = late_speed - early_speed

    rets = [gains_c[i] - gains_c[i-1] for i in range(1, n)]
    mid = len(rets) // 2
    mom_accel = np.mean(rets[mid:]) - np.mean(rets[:mid]) if mid > 0 and rets else 0

    # Volume
    up_vol = sum(b[5] for i, b in enumerate(past_bars) if i > 0 and gains_c[i] > gains_c[i-1])
    dn_vol = sum(b[5] for i, b in enumerate(past_bars) if i > 0 and gains_c[i] <= gains_c[i-1])
    up_vol_ratio = np.log1p(up_vol) - np.log1p(dn_vol)

    # Support touches
    running_low = gains_c[0]
    touches = 0
    for g in gains_c:
        if g <= running_low * 1.001: touches += 1
        if g < running_low: running_low = g
    support_touches = touches / n

    # Bar size trend
    ranges = [(b[2]-b[3])/day_open*100 for b in past_bars if b[2] and b[3]]
    bar_size_trend = np.corrcoef(np.arange(len(ranges)), ranges)[0, 1] if len(ranges) > 3 else 0
    if np.isnan(bar_size_trend): bar_size_trend = 0

    # Wick ratios
    wick_ratios, lower_wicks = [], []
    for b in past_bars:
        t, o, h, l, c, v = b[0], b[1], b[2], b[3], b[4], b[5]
        rng = h - l
        if rng > 0:
            wick_ratios.append((h - max(o, c)) / rng)
            lower_wicks.append((min(o, c) - l) / rng)
    wick_ratio = np.mean(wick_ratios) if wick_ratios else 0
    lower_wick = np.mean(lower_wicks) if lower_wicks else 0

    # Gaps between bars
    gaps = [(past_bars[i][1]/past_bars[i-1][4] - 1) * 100
            for i in range(1, n) if past_bars[i-1][4] > 0]
    gap_ratio = np.mean(gaps) if gaps else 0

    # Time at high
    if gains_c:
        g_max, g_min = max(gains_c), min(gains_c)
        g_range = g_max - g_min
        time_at_high = sum(1 for g in gains_c if g >= g_max - 0.25*g_range) / n if g_range > 0 else 0.5
    else:
        time_at_high = 0.5

    # Volume at peaks
    if n > 2:
        med_gain = np.median(gains_c)
        peak_vol = np.mean([b[5] for i, b in enumerate(past_bars) if gains_c[i] >= med_gain]) or 1
        dip_vol = np.mean([b[5] for i, b in enumerate(past_bars) if gains_c[i] < med_gain]) or 1
        vol_at_peaks = np.log(peak_vol) - np.log(dip_vol)
    else:
        vol_at_peaks = 0

    # VWAP slope
    cum_pv = 0; cum_v = 0; vwap_diffs = []
    for b in past_bars:
        v = b[5] or 0; cum_v += v; cum_pv += b[4] * v
        vwap = cum_pv / cum_v if cum_v > 0 else b[4]
        vwap_diffs.append((b[4]/vwap - 1) * 100)
    vwap_slope = np.corrcoef(np.arange(len(vwap_diffs)), vwap_diffs)[0, 1] if len(vwap_diffs) > 3 else 0
    if np.isnan(vwap_slope): vwap_slope = 0

    # Return skewness
    try:
        from scipy.stats import skew as scipy_skew
        ret_skew = float(scipy_skew(rets)) if len(rets) > 3 else 0
    except Exception:
        ret_skew = 0
    if np.isnan(ret_skew): ret_skew = 0

    return {
        'path_r_squared': r_sq, 'path_peak_diff': peak_diff, 'path_low_diff': low_diff,
        'path_consol_range': consol, 'path_max_drawdown': max_dd, 'path_choppiness': chop,
        'path_speed_late': late_speed, 'path_speed_accel': speed_accel,
        'path_momentum_accel': mom_accel, 'path_speed_early': early_speed,
        'path_up_vol_ratio': up_vol_ratio, 'path_support_touches': support_touches,
        'path_bar_size_trend': bar_size_trend, 'path_wick_ratio': wick_ratio,
        'path_lower_wick_ratio': lower_wick, 'path_gap_ratio': gap_ratio,
        'path_time_at_high': time_at_high, 'path_vol_at_peaks': vol_at_peaks,
        'path_vwap_slope': vwap_slope, 'path_ret_skewness': ret_skew,
    }


def simulate_trail(future_bars, entry_price, trail_mode='fixed3'):
    """Simulate trail stop exit from entry.
    Modes: 'fixed3' (3% constant) or 'decay' (3% → 2% at 10:00 → 1% at 10:30)
    Returns: exit_pnl_pct
    """
    peak = entry_price
    for b in future_bars:
        t = b[0]
        if trail_mode == 'decay':
            trail_pct = 0.03 if t < '10:00' else (0.02 if t < '10:30' else 0.01)
        else:
            trail_pct = 0.03
        if b[2] > peak: peak = b[2]
        trail_price = peak * (1 - trail_pct)
        if b[3] <= trail_price:
            return (trail_price / entry_price - 1) * 100
    if future_bars:
        return (future_bars[-1][4] / entry_price - 1) * 100
    return 0


def build_features(start_date, end_date, output_path, limit_symbols=200):
    """Main builder: produce pkl with all features + labels for date range."""
    t_start = _time.time()
    print(f"Feature builder: {start_date} → {end_date}")
    print(f"Output: {output_path}")

    conn = sqlite3.connect(DB_PATH)

    # 1. Load universe (top N by volume)
    print(f"\n[{_time.time()-t_start:.0f}s] Loading universe...")
    syms = [r[0] for r in conn.execute(
        f"SELECT symbol FROM universe_stocks ORDER BY dollar_vol DESC LIMIT {limit_symbols}"
    ).fetchall()]
    sectors_map = dict(conn.execute("SELECT symbol, sector FROM universe_stocks WHERE sector IS NOT NULL").fetchall())
    betas = dict(conn.execute("SELECT symbol, beta FROM stock_fundamentals WHERE beta IS NOT NULL").fetchall())
    mcaps = dict(conn.execute("SELECT symbol, market_cap FROM stock_fundamentals WHERE market_cap IS NOT NULL").fetchall())
    print(f"  {len(syms)} symbols, {len(sectors_map)} sector maps")

    # 2. Load macro snapshots
    print(f"[{_time.time()-t_start:.0f}s] Loading macro data...")
    macro = pd.read_sql_query(f"""
        SELECT date, spy_close, vix_close, vix3m_close, btc_close, usdjpy_close,
               skew_close, vvix_close
        FROM macro_snapshots
        WHERE date >= '{start_date}' AND date <= '{end_date}'
        ORDER BY date
    """, conn)
    # Forward-fill macro for weekends/holidays
    macro = macro.set_index('date').ffill().reset_index()
    # Compute derived
    macro['spy_daily'] = (macro['spy_close'] / macro['spy_close'].shift(1) - 1) * 100
    macro['vix_5d_chg'] = macro['vix_close'] - macro['vix_close'].shift(5)
    macro['btc_5d_chg'] = (macro['btc_close'] / macro['btc_close'].shift(5) - 1) * 100
    macro['jpy_5d_chg'] = (macro['usdjpy_close'] / macro['usdjpy_close'].shift(5) - 1) * 100
    macro['vix_term_spread'] = macro['vix3m_close'] - macro['vix_close']
    macro_dict = {r['date']: r for _, r in macro.iterrows()}

    # 3. Load breadth
    breadth = dict(conn.execute(
        f"SELECT date, ad_ratio FROM market_breadth WHERE date >= '{start_date}' AND date <= '{end_date}'"
    ).fetchall())

    # 4. Load stock daily OHLC for momentum/52w + daily volume for vol_ratio baseline
    print(f"[{_time.time()-t_start:.0f}s] Loading daily OHLC...")
    daily = pd.read_sql_query(f"""
        SELECT symbol, date, close, high, low, volume FROM stock_daily_ohlc
        WHERE date >= date('{start_date}', '-300 days') AND date <= '{end_date}'
        AND symbol IN ({','.join(['?']*len(syms))})
        ORDER BY symbol, date
    """, conn, params=syms)
    print(f"  {len(daily):,} daily bars")

    # Build per-symbol daily lookup
    daily_by_sym = defaultdict(list)
    for _, r in daily.iterrows():
        daily_by_sym[r['symbol']].append((r['date'], r['close'], r['high'], r['low'], r['volume']))

    # 5. Load ETF 09:30 opens + changes at each 5-min for each date
    print(f"[{_time.time()-t_start:.0f}s] Loading ETF data...")
    etf_bars = pd.read_sql_query(f"""
        SELECT symbol, date, time_et, open, close FROM intraday_bars_5m
        WHERE symbol IN ({','.join(['?']*len(ALL_ETFS))})
        AND date >= '{start_date}' AND date <= '{end_date}'
        AND time_et >= '09:30' AND time_et <= '13:00'
    """, conn, params=ALL_ETFS)

    # ETF 09:30 open: {(sym, date): open}
    etf_opens = etf_bars[etf_bars.time_et == '09:30'].set_index(['symbol','date'])['open'].to_dict()

    # ETF change at (sym, date, time): {(sym, date, time): pct_from_open}
    etf_change_lookup = {}
    for _, r in etf_bars.iterrows():
        opn = etf_opens.get((r['symbol'], r['date']))
        if opn and opn > 0:
            etf_change_lookup[(r['symbol'], r['date'], r['time_et'])] = (r['close']/opn - 1) * 100

    # 6. Load stock bars (process date by date)
    print(f"[{_time.time()-t_start:.0f}s] Processing stocks...")

    all_dates = sorted([d for d in macro_dict.keys() if start_date <= d <= end_date])
    print(f"  {len(all_dates)} trading dates")

    rows = []
    processed_dates = 0

    for date in all_dates:
        processed_dates += 1
        if processed_dates % 50 == 0:
            elapsed = _time.time() - t_start
            print(f"  [{elapsed:.0f}s] Date {processed_dates}/{len(all_dates)} ({date}), rows so far: {len(rows):,}", flush=True)

        # Load all stocks' bars for this date
        bars_today = pd.read_sql_query(f"""
            SELECT symbol, time_et, open, high, low, close, volume
            FROM intraday_bars_5m
            WHERE date = ? AND time_et >= '09:30' AND time_et <= '16:00'
            AND symbol IN ({','.join(['?']*len(syms))})
            ORDER BY symbol, time_et
        """, conn, params=[date] + syms)

        if bars_today.empty: continue

        # Macro for this date
        m = macro_dict.get(date, {})
        spy_daily_chg = m.get('spy_daily', 0) or 0
        vix = float(m.get('vix_close', 20) or 20)
        vix_5d = float(m.get('vix_5d_chg', 0) or 0)
        btc_5d = float(m.get('btc_5d_chg', 0) or 0)
        jpy_5d = float(m.get('jpy_5d_chg', 0) or 0)
        vvix = float(m.get('vvix_close', 100) or 100)
        skew = float(m.get('skew_close', 145) or 145)
        vix_term = float(m.get('vix_term_spread', 1.5) or 1.5)
        ad = float(breadth.get(date, 1.0) or 1.0)

        # SPY intraday at each 5-min bar
        spy_open = etf_opens.get(('SPY', date), 0)

        # Day of week
        from datetime import datetime
        dow = datetime.strptime(date, '%Y-%m-%d').weekday()

        # Anomaly score for this date
        z_scores = []
        for etf_sym, (mean, std) in ETF_BASELINES.items():
            # Use 09:30→10:00 change for anomaly
            chg = etf_change_lookup.get((etf_sym, date, '10:00'))
            if chg is None: continue
            z = abs((chg - mean) / (std + 0.01))
            z_scores.append(z)
        anomaly_score = np.sqrt(sum(z**2 for z in z_scores)) / np.sqrt(len(z_scores)) if z_scores else 0

        # Process each symbol
        for sym, sym_bars_df in bars_today.groupby('symbol'):
            sym_bars = [(r['time_et'], r['open'], r['high'], r['low'], r['close'], r['volume'] or 0)
                        for _, r in sym_bars_df.iterrows()]
            if len(sym_bars) < 6: continue

            # Day open from 09:30 bar
            bar_0930 = [b for b in sym_bars if b[0] == '09:30']
            if not bar_0930: continue
            day_open = bar_0930[0][1]
            if day_open < 1: continue

            # Previous day close + 10-day range + 30-day vol baseline (canonical).
            sym_daily = daily_by_sym.get(sym, [])
            prev_close = None
            closes_21d = []
            ranges_10d = []
            vols_30d = []
            for row in sym_daily:
                # Tuple is (date, close, high, low, volume) — handle older 4-tuple too.
                dd = row[0]
                c = row[1]; h = row[2]; l = row[3]
                v = row[4] if len(row) >= 5 else 0
                if dd < date:
                    prev_close = c
                    closes_21d.append((dd, c))
                    if c and c > 0:
                        ranges_10d.append((dd, (h - l) / c * 100))
                    if v and v > 0:
                        vols_30d.append((dd, v))
            if prev_close is None or prev_close < 1: continue
            ranges_10d = sorted(ranges_10d)[-10:]
            rng10 = float(np.mean([r for _, r in ranges_10d])) if ranges_10d else 3.0
            if rng10 <= 0: rng10 = 3.0
            vols_30d = sorted(vols_30d)[-30:]
            avg_daily_vol = float(np.mean([v for _, v in vols_30d])) if vols_30d else 0.0

            # Momentum features
            closes_21d = sorted(closes_21d)[-21:]
            if len(closes_21d) < 21: continue
            closes = [c for _, c in closes_21d]
            mom5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0
            mom20 = (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0
            sma20 = np.mean(closes[-20:])

            # 52w (need more history)
            closes_full = [t[1] for t in sorted(sym_daily) if t[0] < date][-250:]
            if len(closes_full) < 100: continue
            h52w = max(closes_full)
            l52w = min(closes_full)

            # Sector
            sec = sectors_map.get(sym, '')
            beta = betas.get(sym, 1.5)
            mcap = mcaps.get(sym, 0) or 0
            mcap_bucket = 4 if mcap >= 100e9 else (3 if mcap >= 20e9 else (2 if mcap >= 5e9 else (1 if mcap >= 500e6 else 0)))

            # Iterate through mfo (0 to 180, every 5 min)
            for mfo in range(0, 181, 5):
                time_et = mfo_to_time(mfo)
                # Find bar at this time
                past_bars = [b for b in sym_bars if b[0] <= time_et]
                if len(past_bars) < 1: continue
                entry_bar = past_bars[-1]
                if entry_bar[0] != time_et: continue

                # Current close
                cur_close = entry_bar[4]
                cur_high = max(b[2] for b in past_bars)
                cur_low = min(b[3] for b in past_bars)
                gain = (cur_close / day_open - 1) * 100  # from today's open
                total_gain = (cur_close / prev_close - 1) * 100  # from prev close (chased filter)

                # v19: Filter on TOTAL move from prev close (catches overnight gap chasers)
                # Old (v16): filter on gain_from_open only — could pick +8% gap stocks
                if total_gain < 2 or total_gain >= 5: continue

                # Base features
                range_pct = (cur_high - cur_low) / day_open * 100
                from_peak_pct = (cur_close / cur_high - 1) * 100 if cur_high > 0 else 0
                vwap_num = sum(b[4] * (b[5] or 0) for b in past_bars)
                vwap_den = sum((b[5] or 0) for b in past_bars)
                vwap = vwap_num / vwap_den if vwap_den > 0 else cur_close
                vs_vwap = (cur_close / vwap - 1) * 100 if vwap > 0 else 0

                # vol_ratio — canonical: today_so_far vs expected (30d-avg-daily * fraction-elapsed).
                # No lookahead. Captures "today running heavier than typical day at this point".
                total_vol = sum((b[5] or 0) for b in past_bars)
                # 390 minutes in a regular session; mfo=0 → 5 min elapsed (first bar)
                minutes_elapsed = max(5, mfo + 5)
                expected_so_far = avg_daily_vol * (minutes_elapsed / 390.0) if avg_daily_vol > 0 else 0
                if expected_so_far > 0:
                    vol_ratio = min(20.0, total_vol / expected_so_far)
                else:
                    vol_ratio = 1.0

                # vol_accel — last 3 bars vs prior 3 (canonical, matches live).
                if len(past_bars) >= 6:
                    recent_vol = sum((b[5] or 0) for b in past_bars[-3:])
                    prior_vol = sum((b[5] or 0) for b in past_bars[-6:-3])
                    vol_accel = min(20.0, recent_vol / prior_vol) if prior_vol > 0 else 1.0
                else:
                    vol_accel = 1.0

                # bars_since_hi — first-occurrence (canonical).
                peak_idx = 0
                peak_h = -float('inf')
                for i, b in enumerate(past_bars):
                    if b[2] > peak_h:
                        peak_h = b[2]
                        peak_idx = i
                bars_since_hi = len(past_bars) - 1 - peak_idx

                # hh_count — cumulative all-bar new highs (canonical).
                hh_count = 0
                prev_hi = -float('inf')
                for b in past_bars:
                    if b[2] > prev_hi:
                        hh_count += 1
                        prev_hi = b[2]

                # Consolidation — last 5 bars range as % of day_open (canonical, matches live).
                last5 = past_bars[-min(5, len(past_bars)):]
                consol = (max(b[2] for b in last5) - min(b[3] for b in last5)) / day_open * 100

                # Range expansion — today's range vs 10-day rolling avg (canonical).
                range_exp = range_pct / rng10 if rng10 > 0 else 1.0

                # Gap
                gap_from_prev = (day_open / prev_close - 1) * 100

                # Momentum features
                dist_sma20 = (cur_close / sma20 - 1) * 100 if sma20 > 0 else 0
                pct_52w_hi = (cur_close / h52w - 1) * 100 if h52w > 0 else 0
                pct_52w_lo = (cur_close / l52w - 1) * 100 if l52w > 0 else 0

                # SPY intra at this time
                spy_chg = etf_change_lookup.get(('SPY', date, time_et), 0)

                # Cross-asset at this time
                cross = {}
                for etf in ALL_ETFS:
                    cross[f'{etf.lower()}_intra'] = etf_change_lookup.get((etf, date, time_et), 0)

                # Sector ETF for this stock's sector
                sector_etf_map = {
                    'Technology': 'XLK', 'Healthcare': 'XLV', 'Health Care': 'XLV',
                    'Financial Services': 'XLF', 'Financials': 'XLF',
                    'Consumer Cyclical': 'XLY', 'Communication Services': 'XLC',
                    'Industrials': 'XLI', 'Consumer Defensive': 'XLP',
                    'Energy': 'XLE', 'Basic Materials': 'XLB',
                    'Real Estate': 'XLRE', 'Utilities': 'XLU',
                }
                sec_etf = sector_etf_map.get(sec)

                # sec3d: sector 3-day performance (simplified: skip for now = 0)
                sec3d = 0

                # Path features
                path_feats = compute_path_features(past_bars, day_open)

                # Labels: simulate exit from this entry
                # Entry price = OPEN of entry bar (matches precompute_labels.py v91)
                # Trail starts from entry bar itself (includes its high/low)
                entry_open = entry_bar[1]  # open of entry bar
                entry_idx_in_bars = sym_bars.index(entry_bar) if entry_bar in sym_bars else None
                if entry_idx_in_bars is not None:
                    trail_bars = sym_bars[entry_idx_in_bars:]
                else:
                    trail_bars = [b for b in sym_bars if b[0] >= time_et]
                # Decay trail PnL (3→2→1 based on time)
                label_decay = simulate_trail(trail_bars, entry_open, trail_mode='decay')
                # Fixed 3% trail PnL
                label_fixed3 = simulate_trail(trail_bars, entry_open, trail_mode='fixed3')

                # Binary labels
                label_tp1 = 1 if label_decay >= 1.0 else 0
                label_profit_trail3 = 1 if label_fixed3 > 0 else 0
                label_big_trail3 = 1 if label_fixed3 >= 2.0 else 0

                row = {
                    'sym': sym, 'date': date, 'time': time_et,
                    'mins_from_open': mfo, 'gain_from_open': gain,
                    'range_pct': range_pct, 'from_peak_pct': from_peak_pct,
                    'vs_vwap': vs_vwap, 'vol_ratio': vol_ratio, 'vol_accel': vol_accel,
                    'bars_since_hi': bars_since_hi, 'hh_count': hh_count, 'consol': consol,
                    'range_exp': range_exp, 'gap_from_prev': gap_from_prev,
                    'beta': beta, 'mcap_bucket': mcap_bucket,
                    'spy_green': 1 if spy_daily_chg > 0 else 0, 'spy_intra': spy_chg,
                    'vix': vix, 'vix_5d_chg': vix_5d, 'ad_ratio': ad, 'sec3d': sec3d,
                    'mom5d': mom5, 'mom20d': mom20, 'dist_sma20': dist_sma20,
                    'pct_52w_hi': pct_52w_hi, 'pct_52w_lo': pct_52w_lo, 'dow': dow,
                    # v3 features (zeros for now — need separate backfill)
                    'insider_net_30d': 0, 'news_sentiment': 0, 'earnings_days': 60,
                    'pm_vol_ratio': 0, 'short_pct': 0,
                    # v6 macro
                    'btc_5d_chg': btc_5d, 'jpy_5d_chg': jpy_5d, 'skew': skew, 'vvix': vvix,
                    'vix_term_spread': vix_term,
                    'sec_rel_strength': max(-20, min(20, gain - sec3d)),
                    # Path features
                    **path_feats,
                    # Cross-asset
                    **cross,
                    # Derived cross-asset
                    'iwm_spy_spread': cross.get('iwm_intra', 0) - spy_chg,
                    'xlk_spy_spread': cross.get('xlk_intra', 0) - spy_chg,
                    'xle_spy_spread': cross.get('xle_intra', 0) - spy_chg,
                    'smh_xlk_spread': cross.get('smh_intra', 0) - cross.get('xlk_intra', 0),
                    'hyg_spy_spread': cross.get('hyg_intra', 0) - spy_chg,
                    'qqq_spy_spread': cross.get('qqq_intra', 0) - spy_chg,
                    'uso_iwm_combo': cross.get('uso_intra', 0) * (1.0 if (cross.get('iwm_intra', 0) - spy_chg) < -0.3 else 0.0),
                    'vxx_spy_combo': cross.get('vxx_intra', 0) * (1.0 if spy_chg < 0 else 0.0),
                    'tlt_gld_avg': (cross.get('tlt_intra', 0) + cross.get('gld_intra', 0)) / 2,
                    'anomaly_score': anomaly_score,
                    # Labels
                    'fwd_ret': label_fixed3,
                    'trail3_pnl': label_fixed3,
                    'label_decay': label_decay,
                    'label_fixed3': label_fixed3,
                    'label_tp1': label_tp1,
                    'label_profit_trail3': label_profit_trail3,
                    'label_big_trail3': label_big_trail3,
                }
                rows.append(row)

    conn.close()

    print(f"\n[{_time.time()-t_start:.0f}s] Total rows: {len(rows):,}")

    # Build DataFrame
    df = pd.DataFrame(rows)
    print(f"  Columns: {len(df.columns)}")
    print(f"  Date range: {df.date.min()} → {df.date.max()}")

    # Save
    df.to_pickle(output_path)
    print(f"\n[{_time.time()-t_start:.0f}s] Saved: {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2021-01-01')
    parser.add_argument('--end', default='2026-04-22')
    parser.add_argument('--output', default='/tmp/bt_features_v16.pkl')
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()

    build_features(args.start, args.end, args.output, args.limit)
