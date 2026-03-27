#!/usr/bin/env python3
"""
Replay: Test 4 improvements against baseline v4.4b + limit-buy.

Variants:
  A) BASELINE: current v4.4b (fixed SL, fixed bw, 10 features, NW estimator)
  B) DYNAMIC_SL: ATR-scaled SL per regime
  C) LOOCV_BW: Cross-validated bandwidth selection
  D) FEAT_OPT: Remove entry_rsi, add distance_from_20d_high + sector_1d_change
  E) LOCAL_LINEAR: Local linear regression instead of NW
  F) ALL_COMBINED: B+C+D+E together
"""
import datetime as _dt
import sqlite3
import sys
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# === Shared config ===
MACRO_BW = 0.6
STOCK_BW = 1.0
BULL_ER = 0.5
STRESS_ER = -0.5
MIN_TRAIN_DAYS = 20
BASE_TP_PCT = 3.0
THROUGH_PCT = 0.05

# Limit-buy
LB_PULLBACK_MULT = 0.3
LB_MAX_ATR = 3.5
LB_SL_PCT = 2.5
LB_TP_PCT = 2.0
LB_MAX_HOLD = 2

# Dynamic SL config
DYN_SL_MULT = {'BULL': 2.0, 'STRESS': 1.5, 'CRISIS': 1.0}
DYN_SL_FLOOR = 1.5
DYN_SL_CAP = 5.0

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

# Feature sets
MACRO_FEATURES = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                  'new_52w_highs', 'yield_10y', 'spy_close']

STOCK_FEATURES_BASELINE = MACRO_FEATURES + ['atr_pct', 'momentum_5d', 'volume_ratio', 'entry_rsi']
STOCK_FEATURES_OPTIMIZED = MACRO_FEATURES + ['atr_pct', 'momentum_5d', 'volume_ratio',
                                              'distance_from_20d_high', 'sector_1d_change']


# ====== Kernel implementations ======

class GaussianKernel:
    """Standard Nadaraya-Watson kernel regression."""
    def __init__(self, bandwidth, features):
        self.bw = bandwidth
        self.features = features
        self.X = np.array([])
        self.y = np.array([])
        self.mu = np.zeros(len(features))
        self.sigma = np.ones(len(features))

    def fit(self, data):
        rows, rets = [], []
        for r in data:
            vals = [r.get(f) for f in self.features]
            if any(v is None for v in vals):
                continue
            rows.append(vals)
            rets.append(r['outcome_5d'])
        if len(rows) < 10:
            self.X = np.array([])
            return
        self.X = np.array(rows, dtype=float)
        self.y = np.array(rets, dtype=float)
        self.mu = self.X.mean(axis=0)
        self.sigma = self.X.std(axis=0)
        self.sigma[self.sigma == 0] = 1.0
        self.X = (self.X - self.mu) / self.sigma

    def estimate(self, row):
        if len(self.X) == 0:
            return 0.0, 0.0
        x = self._normalize(row)
        dists = np.sqrt(np.sum((self.X - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0
        er = float(np.sum(weights * self.y) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff

    def _normalize(self, row):
        vals = []
        for i, f in enumerate(self.features):
            v = row.get(f)
            if v is None:
                v = self.mu[i]
            vals.append(v)
        return (np.array(vals, dtype=float) - self.mu) / self.sigma


class LOOCVKernel(GaussianKernel):
    """Kernel with LOOCV bandwidth — vectorized O(n×bw) instead of O(n²×bw)."""
    def __init__(self, features, bw_grid=None):
        super().__init__(1.0, features)
        self.bw_grid = bw_grid or [0.4, 0.6, 0.8, 1.0, 1.5]

    def fit(self, data):
        super().fit(data)
        if len(self.X) < 20:
            return
        n = len(self.X)
        # Precompute full distance matrix once: O(n²) — then reuse for all bw
        # For large n, subsample to keep fast
        max_cv = min(n, 500)
        idx = np.random.RandomState(42).choice(n, max_cv, replace=False) if n > max_cv else np.arange(n)
        # Distance matrix: (max_cv, n)
        dist_mat = np.sqrt(np.sum((self.X[idx, None, :] - self.X[None, :, :]) ** 2, axis=2))

        best_bw, best_mse = self.bw, float('inf')
        for bw in self.bw_grid:
            weight_mat = np.exp(-0.5 * (dist_mat / bw) ** 2)  # (max_cv, n)
            # Zero out self-weight for LOO
            for k, i in enumerate(idx):
                weight_mat[k, i] = 0.0
            total_w = weight_mat.sum(axis=1)  # (max_cv,)
            mask = total_w > 1e-10
            y_hat = np.zeros(max_cv)
            y_hat[mask] = (weight_mat[mask] @ self.y) / total_w[mask]
            residuals = self.y[idx] - y_hat
            residuals[~mask] = 0
            mse = np.mean(residuals[mask] ** 2) if mask.any() else float('inf')
            if mse < best_mse:
                best_mse = mse
                best_bw = bw
        self.bw = best_bw


class LocalLinearKernel(GaussianKernel):
    """Local linear regression — fixes boundary bias of NW estimator."""
    def estimate(self, row):
        if len(self.X) == 0:
            return 0.0, 0.0
        x = self._normalize(row)
        diffs = self.X - x  # (n, d)
        dists = np.sqrt(np.sum(diffs ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0

        # Weighted least squares: y = a + b'(X - x)
        # Solution: [a, b] = (X_aug' W X_aug)^{-1} X_aug' W y
        n, d = self.X.shape
        X_aug = np.column_stack([np.ones(n), diffs])  # (n, d+1)
        W = np.diag(weights)
        try:
            XtWX = X_aug.T @ W @ X_aug  # (d+1, d+1)
            XtWy = X_aug.T @ W @ self.y  # (d+1,)
            beta = np.linalg.solve(XtWX + 1e-8 * np.eye(d + 1), XtWy)
            er = float(beta[0])  # intercept = local estimate at x
        except np.linalg.LinAlgError:
            er = float(np.sum(weights * self.y) / total_w)

        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff


class CombinedKernel(LocalLinearKernel):
    """Local linear + LOOCV bandwidth — fast vectorized NW CV then local linear estimate."""
    def __init__(self, features, bw_grid=None):
        super().__init__(1.0, features)
        self.bw_grid = bw_grid or [0.4, 0.6, 0.8, 1.0, 1.5]

    def fit(self, data):
        GaussianKernel.fit(self, data)
        if len(self.X) < 20:
            return
        # Fast LOOCV using NW (not local linear) for bandwidth selection
        # Then use that bandwidth for local linear estimation
        n = len(self.X)
        max_cv = min(n, 500)
        idx = np.random.RandomState(42).choice(n, max_cv, replace=False) if n > max_cv else np.arange(n)
        dist_mat = np.sqrt(np.sum((self.X[idx, None, :] - self.X[None, :, :]) ** 2, axis=2))

        best_bw, best_mse = self.bw, float('inf')
        for bw in self.bw_grid:
            weight_mat = np.exp(-0.5 * (dist_mat / bw) ** 2)
            for k, i in enumerate(idx):
                weight_mat[k, i] = 0.0
            total_w = weight_mat.sum(axis=1)
            mask = total_w > 1e-10
            y_hat = np.zeros(max_cv)
            y_hat[mask] = (weight_mat[mask] @ self.y) / total_w[mask]
            residuals = self.y[idx] - y_hat
            mse = np.mean(residuals[mask] ** 2) if mask.any() else float('inf')
            if mse < best_mse:
                best_mse = mse
                best_bw = bw
        self.bw = best_bw


# ====== Data loading ======

def load_data():
    conn = None  # via get_session())
    conn.row_factory = dict

    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs
        FROM backfill_signal_outcomes s
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        LEFT JOIN market_breadth b
            ON b.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    # Also get sector_1d_change from sector_etf_daily_returns
    sector_returns = conn.execute("""
        SELECT date, sector, pct_change FROM sector_etf_daily_returns
    """).fetchall()

    crude_series = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()
    conn.close()

    # Build sector return lookup
    sector_ret_map = {}
    for r in sector_returns:
        sector_ret_map[(r['date'], r['sector'])] = r['pct_change']

    crude_by_date = {r['date']: r['crude_close'] for r in crude_series}
    crude_dates = sorted(crude_by_date.keys())
    crude_chg_by_date = {}
    for i, d in enumerate(crude_dates):
        if i >= 5:
            c5 = crude_by_date[crude_dates[i - 5]]
            if c5 and c5 > 0:
                crude_chg_by_date[d] = (crude_by_date[d] / c5 - 1) * 100

    combined = []
    for r in backfill_rows:
        d = dict(r); d['source'] = 'backfill'; combined.append(d)
    for r in live_rows:
        d = dict(r); d['source'] = 'live'; combined.append(d)

    seen = {}
    for row in combined:
        key = (row['scan_date'], row['symbol'])
        if key in seen:
            if row['source'] == 'live': seen[key] = row
        else:
            seen[key] = row
    combined = sorted(seen.values(), key=lambda r: r['scan_date'])

    for row in combined:
        sd = row['scan_date']
        d_obj = _dt.date.fromisoformat(sd)
        wd = d_obj.weekday()
        if wd == 5: macro_d = (d_obj - _dt.timedelta(days=1)).isoformat()
        elif wd == 6: macro_d = (d_obj - _dt.timedelta(days=2)).isoformat()
        else: macro_d = sd
        row['crude_change_5d'] = crude_chg_by_date.get(macro_d)
        # Add sector_1d_change
        sector = row.get('sector', '')
        row['sector_1d_change'] = sector_ret_map.get((macro_d, sector))

    print(f"Dataset: {len(combined)} rows, {len(set(r['scan_date'] for r in combined))} dates")
    return combined


def download_ohlc(picks):
    """Download D+1 through D+5 OHLC."""
    import yfinance as yf

    by_symbol = defaultdict(list)
    for p in picks:
        by_symbol[p['symbol']].append(p)

    symbols = list(by_symbol.keys())
    print(f"Downloading OHLC for {len(symbols)} symbols...")

    all_dates = [_dt.date.fromisoformat(p['date']) for p in picks]
    min_date = min(all_dates) - _dt.timedelta(days=2)
    max_date = max(all_dates) + _dt.timedelta(days=10)

    ohlc_cache = {}
    batch_size = 50

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_str = ' '.join(batch)
        try:
            data = yf.download(batch_str, start=min_date.isoformat(),
                               end=max_date.isoformat(),
                               interval='1d', auto_adjust=True,
                               progress=False, threads=False)
            if data.empty:
                continue
            for sym in batch:
                try:
                    if len(batch) == 1:
                        opens, highs, lows, closes = data['Open'], data['High'], data['Low'], data['Close']
                    else:
                        if sym not in data.columns.get_level_values(1):
                            continue
                        opens, highs, lows, closes = data['Open'][sym], data['High'][sym], data['Low'][sym], data['Close'][sym]
                    for idx in opens.dropna().index:
                        ds = idx.strftime('%Y-%m-%d')
                        o, h, l, c = opens.get(idx), highs.get(idx), lows.get(idx), closes.get(idx)
                        if o is not None and not np.isnan(o):
                            ohlc_cache[(sym, ds)] = {
                                'open': float(o),
                                'high': float(h) if h is not None and not np.isnan(h) else float(o),
                                'low': float(l) if l is not None and not np.isnan(l) else float(o),
                                'close': float(c) if c is not None and not np.isnan(c) else float(o),
                            }
                except Exception:
                    continue
        except Exception as e:
            print(f"  batch error: {e}")
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        if batch_num % 5 == 0 or batch_num == total_batches:
            print(f"  batch {batch_num}/{total_batches}")

    for p in picks:
        scan_date = _dt.date.fromisoformat(p['date'])
        sym = p['symbol']
        days = []
        d = scan_date
        for _ in range(10):
            d += _dt.timedelta(days=1)
            if (sym, d.isoformat()) in ohlc_cache:
                days.append(ohlc_cache[(sym, d.isoformat())])
                if len(days) >= 5:
                    break
        p['ohlc'] = days

    filled = sum(1 for p in picks if p['ohlc'])
    print(f"OHLC: {filled}/{len(picks)}")
    return picks


# ====== Walk-forward with configurable kernel ======

def run_walkforward(data, macro_kernel_cls, stock_kernel_cls,
                    macro_features, stock_features,
                    macro_bw=MACRO_BW, stock_bw=STOCK_BW,
                    dynamic_sl=False, label=''):
    """Walk-forward scoring with configurable kernels and features."""
    dates = sorted(set(r['scan_date'] for r in data))
    all_picks = []
    regime_days = defaultdict(int)
    skipped = 0
    bw_log = []

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test:
            continue
        if len(set(r['scan_date'] for r in train)) < MIN_TRAIN_DAYS:
            skipped += 1
            continue

        # Macro kernel
        if macro_kernel_cls == LOOCVKernel or macro_kernel_cls == CombinedKernel:
            macro_k = macro_kernel_cls(macro_features)
        else:
            macro_k = macro_kernel_cls(macro_bw, macro_features)
        macro_k.fit(train)
        macro_er, macro_neff = macro_k.estimate(test[0])
        if macro_neff < 3.0:
            skipped += 1
            continue

        if macro_er > BULL_ER:
            regime, max_picks, sl_pct = 'BULL', 5, 3.0
        elif macro_er > STRESS_ER:
            regime, max_picks, sl_pct = 'STRESS', 3, 2.0
        else:
            regime, max_picks, sl_pct = 'CRISIS', 2, 2.0
        regime_days[regime] += 1

        # Stock kernel
        if stock_kernel_cls == LOOCVKernel or stock_kernel_cls == CombinedKernel:
            stock_k = stock_kernel_cls(stock_features)
        else:
            stock_k = stock_kernel_cls(stock_bw, stock_features)
        stock_k.fit(train)
        bw_log.append((test_date, macro_k.bw, stock_k.bw))

        scored = []
        for row in test:
            stock_er, stock_neff = stock_k.estimate(row)
            if stock_neff < 3.0:
                stock_er = 0.0

            if regime == 'STRESS':
                atr = row.get('atr_pct') or 99
                mom5 = row.get('momentum_5d') or 0
                sector = row.get('sector') or ''
                bonus = 0
                if atr < 2.5: bonus += 1
                if mom5 < 0: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.2: bonus += 1
                if sector in DEFENSIVE_SECTORS: bonus += 1
                if bonus < 2: continue
                stock_er += bonus * 0.5
            elif regime == 'CRISIS':
                mom5 = row.get('momentum_5d') or 0
                if mom5 >= 0: continue
                bonus = 0
                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                if mom5 < -2: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                if (row.get('sector') or '') in CRISIS_DEFENSIVE: bonus += 1
                if bonus < 3: continue
                stock_er += bonus * 0.5

            if stock_er < 0: continue
            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        for stock_er, row in scored[:max_picks]:
            atr = row.get('atr_pct') or 3.0

            # Dynamic SL
            if dynamic_sl:
                pick_sl = max(DYN_SL_FLOOR, min(DYN_SL_CAP, DYN_SL_MULT[regime] * atr))
            else:
                pick_sl = sl_pct

            all_picks.append({
                'date': test_date, 'symbol': row['symbol'],
                'regime': regime, 'stock_er': stock_er,
                'scan_price': row.get('scan_price'),
                'atr_pct': atr, 'sector': row.get('sector'),
                'sl_pct': pick_sl,
                'outcome_5d': row['outcome_5d'],
                'outcome_max_gain_5d': row.get('outcome_max_gain_5d'),
                'outcome_max_dd_5d': row.get('outcome_max_dd_5d'),
                'ohlc': [],
            })

    # Log bandwidth stats if LOOCV
    if bw_log and (macro_kernel_cls in (LOOCVKernel, CombinedKernel)):
        macro_bws = [b[1] for b in bw_log]
        stock_bws = [b[2] for b in bw_log]
        print(f"  [{label}] LOOCV bw: macro={np.mean(macro_bws):.2f} "
              f"(min={min(macro_bws):.1f}, max={max(macro_bws):.1f}), "
              f"stock={np.mean(stock_bws):.2f} "
              f"(min={min(stock_bws):.1f}, max={max(stock_bws):.1f})")

    return all_picks, regime_days


# ====== Simulation ======

def simulate_limit_buy(pick):
    ohlc = pick.get('ohlc', [])
    if not ohlc or not ohlc[0]:
        return None

    atr_pct = pick.get('atr_pct') or 99
    open_d1 = ohlc[0]['open']
    if open_d1 <= 0:
        return None

    sl_pct = pick['sl_pct']

    if atr_pct >= LB_MAX_ATR:
        # Buy at open, use pick's SL (dynamic or fixed)
        tp_pct = BASE_TP_PCT
        entry = open_d1
        sl_price = entry * (1 - sl_pct / 100)
        tp_price = entry * (1 + tp_pct / 100)
        sl_through = sl_price * (1 - THROUGH_PCT / 100)
        tp_through = tp_price * (1 + THROUGH_PCT / 100)

        for i, bar in enumerate(ohlc):
            if bar is None: continue
            if bar['low'] <= sl_through:
                return {'return_pct': -sl_pct, 'exit_type': 'SL', 'exit_day': i+1}
            if bar['high'] >= tp_through:
                return {'return_pct': tp_pct, 'exit_type': 'TP1', 'exit_day': i+1}
        last = next((b for b in reversed(ohlc) if b), None)
        if not last: return None
        return {'return_pct': (last['close']/entry - 1)*100, 'exit_type': 'EXPIRE', 'exit_day': len(ohlc)}

    # Limit-buy path
    pullback_pct = LB_PULLBACK_MULT * atr_pct
    limit_price = open_d1 * (1 - pullback_pct / 100)
    limit_through = limit_price * (1 - THROUGH_PCT / 100)

    entry_price = None
    fill_day = None
    for i in range(min(LB_MAX_HOLD, len(ohlc))):
        bar = ohlc[i]
        if bar and bar['low'] <= limit_through:
            entry_price = limit_price
            fill_day = i
            break

    if entry_price is None:
        return {'return_pct': 0, 'exit_type': 'MISSED', 'exit_day': 0}

    lb_sl = LB_SL_PCT
    lb_tp = LB_TP_PCT
    sl_price = entry_price * (1 - lb_sl / 100)
    tp_price = entry_price * (1 + lb_tp / 100)
    sl_through = sl_price * (1 - THROUGH_PCT / 100)
    tp_through = tp_price * (1 + THROUGH_PCT / 100)

    max_exit = min(LB_MAX_HOLD, len(ohlc))
    for i in range(fill_day, max_exit):
        bar = ohlc[i]
        if bar is None: continue
        if bar['low'] <= sl_through:
            return {'return_pct': -lb_sl, 'exit_type': 'SL', 'exit_day': i+1, 'limit_fill': True}
        if bar['high'] >= tp_through:
            return {'return_pct': lb_tp, 'exit_type': 'TP1', 'exit_day': i+1, 'limit_fill': True}

    exit_bar = ohlc[min(max_exit-1, len(ohlc)-1)] if ohlc else None
    if not exit_bar: return None
    return {'return_pct': (exit_bar['close']/entry_price - 1)*100, 'exit_type': 'EXPIRE_D2',
            'exit_day': max_exit, 'limit_fill': True}


def compute_metrics(picks, results):
    traded = [(p, r) for p, r in zip(picks, results) if r and r['exit_type'] != 'MISSED']
    missed = [(p, r) for p, r in zip(picks, results) if r and r['exit_type'] == 'MISSED']
    if not traded:
        return None

    n = len(traded)
    rets = [r['return_pct'] for _, r in traded]
    wins = sum(1 for r in rets if r > 0)
    tp1 = sum(1 for _, r in traded if r['exit_type'] == 'TP1')
    sl = sum(1 for _, r in traded if r['exit_type'] == 'SL')

    win_rets = [r for r in rets if r > 0]
    loss_rets = [r for r in rets if r <= 0]

    # Per regime
    regime_data = {}
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        rp = [(p, r) for p, r in traded if p['regime'] == regime]
        if rp:
            rr = [r['return_pct'] for _, r in rp]
            rw = sum(1 for r in rr if r > 0)
            r_sl = sum(1 for _, r in rp if r['exit_type'] == 'SL')
            regime_data[regime] = {
                'n': len(rp), 'wr': rw/len(rp)*100,
                'pnl': sum(rr), 'sl_rate': r_sl/len(rp)*100,
            }
        else:
            regime_data[regime] = {'n': 0, 'wr': 0, 'pnl': 0, 'sl_rate': 0}

    return {
        'n_total': len(picks), 'n_traded': n, 'n_missed': len(missed),
        'wr': wins/n*100, 'pnl': sum(rets), 'avg': np.mean(rets),
        'tp1_rate': tp1/n*100, 'sl_rate': sl/n*100,
        'avg_win': np.mean(win_rets) if win_rets else 0,
        'avg_loss': np.mean(loss_rets) if loss_rets else 0,
        'exp': np.mean(rets),
        'regimes': regime_data,
    }


# ====== Main ======

def main():
    data = load_data()

    # Define variants
    variants = [
        {
            'label': 'A) BASELINE',
            'macro_cls': GaussianKernel, 'stock_cls': GaussianKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_BASELINE,
            'dynamic_sl': False,
        },
        {
            'label': 'B) DYNAMIC_SL',
            'macro_cls': GaussianKernel, 'stock_cls': GaussianKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_BASELINE,
            'dynamic_sl': True,
        },
        {
            'label': 'C) LOOCV_BW',
            'macro_cls': LOOCVKernel, 'stock_cls': LOOCVKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_BASELINE,
            'dynamic_sl': False,
        },
        {
            'label': 'D) FEAT_OPT',
            'macro_cls': GaussianKernel, 'stock_cls': GaussianKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_OPTIMIZED,
            'dynamic_sl': False,
        },
        {
            'label': 'E) LOCAL_LIN',
            'macro_cls': LocalLinearKernel, 'stock_cls': LocalLinearKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_BASELINE,
            'dynamic_sl': False,
        },
        {
            'label': 'F) ALL_COMBINED',
            'macro_cls': CombinedKernel, 'stock_cls': CombinedKernel,
            'macro_feat': MACRO_FEATURES, 'stock_feat': STOCK_FEATURES_OPTIMIZED,
            'dynamic_sl': True,
        },
    ]

    # Run walk-forward for each variant
    print("\n--- Step 1: Walk-forward scoring (6 variants) ---")
    variant_picks = {}
    for v in variants:
        print(f"\n  Running {v['label']}...")
        picks, regime_days = run_walkforward(
            data, v['macro_cls'], v['stock_cls'],
            v['macro_feat'], v['stock_feat'],
            dynamic_sl=v['dynamic_sl'], label=v['label'],
        )
        variant_picks[v['label']] = picks
        print(f"  {v['label']}: {len(picks)} picks, regimes={dict(regime_days)}")

    # Download OHLC once (use baseline picks — all variants have similar picks)
    # Actually all variants produce different picks, so we need to download for all unique symbols/dates
    all_picks_flat = []
    for label, picks in variant_picks.items():
        all_picks_flat.extend(picks)

    print("\n--- Step 2: Downloading OHLC ---")
    # Deduplicate by (symbol, date) for download
    seen_keys = set()
    unique_picks = []
    for p in all_picks_flat:
        key = (p['symbol'], p['date'])
        if key not in seen_keys:
            seen_keys.add(key)
            unique_picks.append(p)
    unique_picks = download_ohlc(unique_picks)

    # Build lookup
    ohlc_lookup = {(p['symbol'], p['date']): p['ohlc'] for p in unique_picks}

    # Attach OHLC to all variant picks
    for label, picks in variant_picks.items():
        for p in picks:
            p['ohlc'] = ohlc_lookup.get((p['symbol'], p['date']), [])

    # Simulate and compute metrics
    print("\n--- Step 3: Simulating ---")
    results = {}
    for v in variants:
        label = v['label']
        picks = variant_picks[label]
        picks_with_data = [p for p in picks if p.get('ohlc') and p['ohlc'] and p['ohlc'][0]]
        sim_results = [simulate_limit_buy(p) for p in picks_with_data]
        metrics = compute_metrics(picks_with_data, sim_results)
        results[label] = metrics

    # Print comparison
    print(f"\n{'='*100}")
    print(f"  DISCOVERY IMPROVEMENT COMPARISON — 6 Variants + Limit-Buy + Through Filter")
    print(f"{'='*100}")

    header = f"  {'Metric':<18}"
    for v in variants:
        header += f" {v['label'].split(') ')[1]:>12}"
    print(header)
    print(f"  {'─'*90}")

    rows = [
        ('Traded', 'n_traded', 'd'),
        ('Missed', 'n_missed', 'd'),
        ('WR (%)', 'wr', '.1f'),
        ('Avg Ret (%)', 'avg', '.3f'),
        ('Total PnL (%)', 'pnl', '.1f'),
        ('TP1 Rate (%)', 'tp1_rate', '.1f'),
        ('SL Rate (%)', 'sl_rate', '.1f'),
        ('Avg Win (%)', 'avg_win', '.2f'),
        ('Avg Loss (%)', 'avg_loss', '.2f'),
        ('Expectancy (%)', 'exp', '.3f'),
    ]

    for row_label, key, fmt in rows:
        line = f"  {row_label:<18}"
        baseline_val = results[variants[0]['label']][key] if results[variants[0]['label']] else 0
        for v in variants:
            m = results[v['label']]
            val = m[key] if m else 0
            val_str = format(val, fmt)
            # Color indicator
            if v['label'] != variants[0]['label'] and key in ('wr', 'exp', 'pnl', 'avg'):
                delta = val - baseline_val
                if abs(delta) > 0.1:
                    val_str += f"{'↑' if delta > 0 else '↓'}"
            line += f" {val_str:>12}"
        print(line)

    # Per-regime comparison
    print(f"\n  {'─'*90}")
    print(f"  PER REGIME (WR% / SL% / PnL)")
    print(f"  {'─'*90}")
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        line = f"  {regime:<18}"
        for v in variants:
            m = results[v['label']]
            if m:
                rd = m['regimes'][regime]
                if rd['n'] > 0:
                    line += f" {rd['wr']:.0f}/{rd['sl_rate']:.0f}/{rd['pnl']:+.0f}%"
                    line = line[:-1]  # Remove trailing
                    # Pad
                    last_part = line.split()[-1]
                    line = line + ' ' * max(0, 12 - len(last_part))
                else:
                    line += f" {'—':>12}"
            else:
                line += f" {'—':>12}"
        print(line)

    print(f"\n{'='*100}")
    print(f"\n  Legend:")
    print(f"  A) BASELINE: Current v4.4b (fixed SL, fixed bw=0.6/1.0, 10 features, NW)")
    print(f"  B) DYNAMIC_SL: ATR-scaled SL (BULL=2×ATR, STRESS=1.5×, CRISIS=1×, floor=1.5%)")
    print(f"  C) LOOCV_BW: Leave-One-Out CV bandwidth selection")
    print(f"  D) FEAT_OPT: -entry_rsi +distance_from_20d_high +sector_1d_change (9 feat)")
    print(f"  E) LOCAL_LIN: Local linear regression (boundary bias fix)")
    print(f"  F) ALL_COMBINED: B+C+D+E together")


if __name__ == '__main__':
    main()
