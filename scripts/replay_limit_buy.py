#!/usr/bin/env python3
"""
Replay Discovery v5.0 Production — full historical simulation.

Matches production config exactly:
- MacroKernel v5.0: 8 features (bw=0.4) — +crude_close, +vix_term_spread
- StockKernel v5.0: 13 features (8 macro + 5 stock, bw=1.0)
- Dynamic ATR-based SL: BULL=2×ATR, STRESS=1.5×ATR, CRISIS=1×ATR (floor=1.5%, cap=5%)
- Limit-buy: ATR<3.5%, pullback 0.3×ATR, SL=2.5%, TP=2.0%, hold 2d

Methodology:
1. Walk-forward kernel scoring (expanding window)
2. Download D+1 through D+5 OHLC for each pick
3. Simulate two strategies side-by-side:
   A) BASELINE: buy at open D+1, dynamic ATR SL, hold up to 5 days
   B) LIMIT-BUY: for ATR<3.5%, limit = open - 0.3×ATR
4. Compare: WR, SL rate, TP rate, expectancy, per-regime
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

# === v5.0 config ===
MACRO_BW = 0.4
STOCK_BW = 1.0
BULL_ER = 0.5
STRESS_ER = -0.5
MIN_TRAIN_DAYS = 20

# Baseline SL/TP
BASE_TP_PCT = 3.0
BASE_TP2_PCT = 6.0

# Dynamic ATR-based SL (v4.5 production)
DYN_SL_MULT = {'BULL': 2.0, 'STRESS': 1.5, 'CRISIS': 1.0}
DYN_SL_FLOOR = 1.5
DYN_SL_CAP = 5.0

# Limit-buy config (v4.6)
LB_PULLBACK_MULT = 0.3   # limit = open - 0.3 × ATR
LB_MAX_ATR = 3.5          # only limit-buy for ATR < 3.5%
LB_SL_PCT = 2.5
LB_TP_PCT = 2.0
LB_TP2_PCT = 4.0          # TP2 = 2.0 × 2.0
LB_MAX_HOLD = 2           # exit at close D+2

# "Through" filter: require price to trade THROUGH level, not just touch
# Prevents optimistic fill assumptions in backtest
THROUGH_PCT = 0.05        # 0.05% margin (~$0.05 on $100 stock)

DEFENSIVE_SECTORS = frozenset({
    'Utilities', 'Healthcare', 'Basic Materials', 'Real Estate', 'Energy',
})
CRISIS_DEFENSIVE = frozenset({
    'Utilities', 'Real Estate', 'Energy',
})

# v5.0: 8 macro features (+crude_close, +vix_term_spread)
MACRO_FEATURES = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                  'new_52w_highs', 'yield_10y', 'spy_close',
                  'crude_close', 'vix_term_spread']
# v5.0: 13 features (8 macro + 5 stock)
STOCK_FEATURES = ['new_52w_lows', 'crude_change_5d', 'pct_above_20d_ma',
                  'new_52w_highs', 'yield_10y', 'spy_close',
                  'crude_close', 'vix_term_spread',
                  'atr_pct', 'momentum_5d', 'volume_ratio',
                  'distance_from_20d_high', 'sector_1d_change']


class GaussianKernel:
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
        vals = []
        for i, f in enumerate(self.features):
            v = row.get(f)
            if v is None:
                v = self.mu[i]
            vals.append(v)
        x = (np.array(vals, dtype=float) - self.mu) / self.sigma
        dists = np.sqrt(np.sum((self.X - x) ** 2, axis=1))
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum()
        if total_w < 1e-10:
            return 0.0, 0.0
        er = float(np.sum(weights * self.y) / total_w)
        n_eff = float(total_w ** 2 / np.sum(weights ** 2))
        return er, n_eff


def load_data():
    conn = None  # via get_session())
    conn.row_factory = dict

    live_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs,
               ser.pct_change as sector_1d_change,
               m.vix_close, m.vix3m_close
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
        LEFT JOIN sector_etf_daily_returns ser
            ON ser.sector = s.sector
            AND ser.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL AND s.atr_pct IS NOT NULL
          AND s.signal_source = 'dip_bounce'
    """).fetchall()

    backfill_rows = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.distance_from_20d_high,
               s.momentum_5d, s.volume_ratio, s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d,
               m.crude_close, m.yield_10y, m.spy_close,
               b.pct_above_20d_ma, b.new_52w_lows, b.new_52w_highs,
               ser.pct_change as sector_1d_change,
               m.vix_close, m.vix3m_close
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
        LEFT JOIN sector_etf_daily_returns ser
            ON ser.sector = s.sector
            AND ser.date = CASE
                WHEN strftime('%w', s.scan_date) = '6' THEN date(s.scan_date, '-1 day')
                WHEN strftime('%w', s.scan_date) = '0' THEN date(s.scan_date, '-2 days')
                ELSE s.scan_date END
        WHERE s.outcome_5d IS NOT NULL
    """).fetchall()

    crude_series = conn.execute("""
        SELECT date, crude_close FROM macro_snapshots
        WHERE crude_close IS NOT NULL ORDER BY date
    """).fetchall()
    conn.close()

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
        # v5.0: vix_term_spread = vix - vix3m
        vix = row.get('vix_close')
        vix3m = row.get('vix3m_close')
        row['vix_term_spread'] = (vix - vix3m) if vix and vix3m else None

    print(f"Dataset: {len(combined)} rows, {len(set(r['scan_date'] for r in combined))} dates")
    return combined


def download_ohlc(picks):
    """Download D+1 through D+5 OHLC for all picks."""
    import yfinance as yf

    by_symbol = defaultdict(list)
    for p in picks:
        by_symbol[p['symbol']].append(p)

    symbols = list(by_symbol.keys())
    print(f"Downloading OHLC for {len(symbols)} symbols...")

    all_dates = [_dt.date.fromisoformat(p['date']) for p in picks]
    min_date = min(all_dates) - _dt.timedelta(days=2)
    max_date = max(all_dates) + _dt.timedelta(days=10)

    # Cache: (symbol, date_str) -> {open, high, low, close}
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
                        opens = data['Open']
                        highs = data['High']
                        lows = data['Low']
                        closes = data['Close']
                    else:
                        if sym not in data.columns.get_level_values(1):
                            continue
                        opens = data['Open'][sym]
                        highs = data['High'][sym]
                        lows = data['Low'][sym]
                        closes = data['Close'][sym]

                    for idx in opens.dropna().index:
                        ds = idx.strftime('%Y-%m-%d')
                        o = opens.get(idx)
                        h = highs.get(idx)
                        l = lows.get(idx)
                        c = closes.get(idx)
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
            continue

        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        if batch_num % 5 == 0 or batch_num == total_batches:
            print(f"  batch {batch_num}/{total_batches}")

    # Attach OHLC for D+1 through D+5
    def _find_trading_days(sym, scan_date, n_days=5):
        """Find next N trading days after scan_date."""
        days = []
        d = scan_date
        for _ in range(n_days * 2):  # search up to 2x for weekends
            d += _dt.timedelta(days=1)
            if (sym, d.isoformat()) in ohlc_cache:
                days.append(d.isoformat())
                if len(days) >= n_days:
                    break
        return days

    filled = 0
    for p in picks:
        scan_date = _dt.date.fromisoformat(p['date'])
        sym = p['symbol']
        trading_days = _find_trading_days(sym, scan_date, 5)

        if trading_days:
            p['ohlc'] = []
            for td in trading_days:
                p['ohlc'].append(ohlc_cache.get((sym, td)))
            filled += 1
        else:
            p['ohlc'] = []

    print(f"OHLC data: {filled}/{len(picks)} picks ({filled/len(picks)*100:.0f}%)")
    return picks


def run_walkforward(data):
    """Walk-forward v4.4b → scored picks."""
    dates = sorted(set(r['scan_date'] for r in data))
    all_picks = []
    regime_days = defaultdict(int)
    skipped = 0

    for test_date in dates:
        train = [r for r in data if r['scan_date'] < test_date]
        test = [r for r in data if r['scan_date'] == test_date]
        if not test:
            continue
        if len(set(r['scan_date'] for r in train)) < MIN_TRAIN_DAYS:
            skipped += 1
            continue

        macro_k = GaussianKernel(MACRO_BW, MACRO_FEATURES)
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

        stock_k = GaussianKernel(STOCK_BW, STOCK_FEATURES)
        stock_k.fit(train)

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
                sector = row.get('sector') or ''
                if mom5 >= 0: continue
                bonus = 0
                if (row.get('atr_pct') or 99) < 2.5: bonus += 1
                if mom5 < -2: bonus += 1
                if (row.get('volume_ratio') or 0) > 1.5: bonus += 1
                if sector in CRISIS_DEFENSIVE: bonus += 1
                if bonus < 3: continue
                stock_er += bonus * 0.5

            if stock_er < 0: continue
            scored.append((stock_er, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        for stock_er, row in scored[:max_picks]:
            # Dynamic ATR-based SL (v4.5 production)
            atr_val = row.get('atr_pct') or 0
            if atr_val > 0:
                dyn_sl = max(DYN_SL_FLOOR, min(DYN_SL_CAP, DYN_SL_MULT[regime] * atr_val))
                dyn_sl = round(dyn_sl, 1)
            else:
                dyn_sl = sl_pct
            all_picks.append({
                'date': test_date,
                'symbol': row['symbol'],
                'regime': regime,
                'stock_er': stock_er,
                'scan_price': row.get('scan_price'),
                'atr_pct': row.get('atr_pct'),
                'sector': row.get('sector'),
                'sl_pct': dyn_sl,
                # Keep raw outcomes for baseline comparison
                'outcome_5d': row['outcome_5d'],
                'outcome_max_gain_5d': row.get('outcome_max_gain_5d'),
                'outcome_max_dd_5d': row.get('outcome_max_dd_5d'),
                'ohlc': [],  # filled later
            })

    print(f"Walk-forward: {len(all_picks)} picks, "
          f"{len(set(p['date'] for p in all_picks))} days, skipped {skipped}")
    print(f"Regime days: {dict(regime_days)}")
    return all_picks


def simulate_baseline(pick):
    """Simulate baseline: buy at open D+1, regime SL/TP, hold up to 5 days."""
    ohlc = pick.get('ohlc', [])
    if not ohlc or not ohlc[0]:
        return None

    entry = ohlc[0]['open']
    if entry <= 0:
        return None

    sl_pct = pick['sl_pct']
    tp_pct = BASE_TP_PCT
    sl_price = entry * (1 - sl_pct / 100)
    tp_price = entry * (1 + tp_pct / 100)

    # Walk through each day (with "through" filter for honest backtest)
    sl_through = sl_price * (1 - THROUGH_PCT / 100)
    tp_through = tp_price * (1 + THROUGH_PCT / 100)
    for i, bar in enumerate(ohlc):
        if bar is None:
            continue
        # Check SL hit — price must trade THROUGH SL, not just touch
        if bar['low'] <= sl_through:
            return {
                'entry': entry, 'exit': sl_price,
                'return_pct': -sl_pct,
                'exit_type': 'SL', 'exit_day': i + 1,
            }
        # Check TP hit — price must trade THROUGH TP
        if bar['high'] >= tp_through:
            return {
                'entry': entry, 'exit': tp_price,
                'return_pct': tp_pct,
                'exit_type': 'TP1', 'exit_day': i + 1,
            }

    # Exit at last available close
    last_bar = None
    for bar in reversed(ohlc):
        if bar is not None:
            last_bar = bar
            break
    if last_bar is None:
        return None

    ret = (last_bar['close'] / entry - 1) * 100
    return {
        'entry': entry, 'exit': last_bar['close'],
        'return_pct': ret,
        'exit_type': 'EXPIRE', 'exit_day': len(ohlc),
    }


def simulate_limit_buy(pick):
    """Simulate limit-buy: for ATR<3.5%, limit at open-0.3×ATR. Otherwise same as baseline."""
    ohlc = pick.get('ohlc', [])
    if not ohlc or not ohlc[0]:
        return None

    atr_pct = pick.get('atr_pct') or 99
    open_d1 = ohlc[0]['open']
    if open_d1 <= 0:
        return None

    # ATR >= threshold → same as baseline (buy at open)
    if atr_pct >= LB_MAX_ATR:
        return simulate_baseline(pick)

    # Compute limit price
    pullback_pct = LB_PULLBACK_MULT * atr_pct
    limit_price = open_d1 * (1 - pullback_pct / 100)

    # Check fill across D+1 and D+2 ("through" filter: low must go BELOW limit)
    limit_through = limit_price * (1 - THROUGH_PCT / 100)
    entry_price = None
    fill_day = None
    for i in range(min(LB_MAX_HOLD, len(ohlc))):
        bar = ohlc[i]
        if bar is None:
            continue
        if bar['low'] <= limit_through:
            entry_price = limit_price
            fill_day = i
            break

    if entry_price is None:
        return {'entry': None, 'exit': None, 'return_pct': 0,
                'exit_type': 'MISSED', 'exit_day': 0}

    # Filled — apply limit-buy SL/TP
    sl_price = entry_price * (1 - LB_SL_PCT / 100)
    tp_price = entry_price * (1 + LB_TP_PCT / 100)

    # Check SL/TP from fill day onward, up to max_hold days from D+1
    sl_through = sl_price * (1 - THROUGH_PCT / 100)
    tp_through = tp_price * (1 + THROUGH_PCT / 100)
    max_exit_day = min(LB_MAX_HOLD, len(ohlc))
    for i in range(fill_day, max_exit_day):
        bar = ohlc[i]
        if bar is None:
            continue

        check_low = bar['low']
        check_high = bar['high']

        if check_low <= sl_through:
            return {
                'entry': entry_price, 'exit': sl_price,
                'return_pct': -LB_SL_PCT,
                'exit_type': 'SL', 'exit_day': i + 1,
                'limit_fill': True,
            }
        if check_high >= tp_through:
            return {
                'entry': entry_price, 'exit': tp_price,
                'return_pct': LB_TP_PCT,
                'exit_type': 'TP1', 'exit_day': i + 1,
                'limit_fill': True,
            }

    # Exit at close of last hold day
    exit_idx = min(max_exit_day - 1, len(ohlc) - 1)
    exit_bar = ohlc[exit_idx] if exit_idx >= 0 else None
    if exit_bar is None:
        return None

    ret = (exit_bar['close'] / entry_price - 1) * 100
    return {
        'entry': entry_price, 'exit': exit_bar['close'],
        'return_pct': ret,
        'exit_type': 'EXPIRE_D2', 'exit_day': exit_idx + 1,
        'limit_fill': True,
    }


def compute_metrics(results, label):
    """Compute metrics from simulation results."""
    # Filter out None and MISSED
    traded = [r for r in results if r is not None and r['exit_type'] != 'MISSED']
    missed = [r for r in results if r is not None and r['exit_type'] == 'MISSED']

    if not traded:
        return None

    n = len(traded)
    returns = [r['return_pct'] for r in traded]
    wins = sum(1 for r in returns if r > 0)
    wr = wins / n * 100
    total_pnl = sum(returns)
    avg_ret = np.mean(returns)

    tp1_hits = sum(1 for r in traded if r['exit_type'] == 'TP1')
    sl_hits = sum(1 for r in traded if r['exit_type'] == 'SL')
    expire = sum(1 for r in traded if r['exit_type'].startswith('EXPIRE'))

    win_rets = [r for r in returns if r > 0]
    loss_rets = [r for r in returns if r <= 0]
    avg_win = np.mean(win_rets) if win_rets else 0
    avg_loss = np.mean(loss_rets) if loss_rets else 0
    expectancy = avg_win * (wins / n) + avg_loss * ((n - wins) / n)

    # Limit-buy specific
    limit_fills = sum(1 for r in traded if r.get('limit_fill'))

    return {
        'label': label,
        'n_total': len(results),
        'n_traded': n,
        'n_missed': len(missed),
        'total_pnl': total_pnl,
        'avg_ret': avg_ret,
        'win_rate': wr,
        'tp1_rate': tp1_hits / n * 100,
        'sl_rate': sl_hits / n * 100,
        'expire_rate': expire / n * 100,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'limit_fills': limit_fills,
        'results': traded,
    }


def print_comparison(baseline, limit_buy, picks):
    """Print side-by-side comparison."""
    b, lb = baseline, limit_buy

    print(f"\n{'=' * 80}")
    print(f"  DISCOVERY v5.0 PRODUCTION REPLAY (8M+13S kernel + dynamic SL + limit-buy)")
    print(f"  MacroKernel: 8 feat, bw={MACRO_BW} | StockKernel: 13 feat, bw={STOCK_BW}")
    print(f"  DynSL: BULL={DYN_SL_MULT['BULL']}x STRESS={DYN_SL_MULT['STRESS']}x "
          f"CRISIS={DYN_SL_MULT['CRISIS']}x [floor={DYN_SL_FLOOR}%, cap={DYN_SL_CAP}%]")
    print(f"  Limit-Buy: pullback={LB_PULLBACK_MULT}×ATR, max_atr={LB_MAX_ATR}%, "
          f"SL={LB_SL_PCT}%, TP={LB_TP_PCT}%, hold={LB_MAX_HOLD}d")
    print(f"{'=' * 80}")

    print(f"\n  {'Metric':<30} {'Baseline':>18} {'Limit-Buy':>18} {'Delta':>12}")
    print(f"  {'─' * 72}")

    rows = [
        ('Total Picks', 'n_total', 'd', ''),
        ('Traded', 'n_traded', 'd', ''),
        ('Missed (unfilled)', 'n_missed', 'd', ''),
        ('Win Rate (%)', 'win_rate', '.1f', '%'),
        ('Avg Return (%)', 'avg_ret', '.3f', '%'),
        ('Total PnL (%)', 'total_pnl', '.1f', '%'),
        ('TP1 Hit Rate (%)', 'tp1_rate', '.1f', '%'),
        ('SL Hit Rate (%)', 'sl_rate', '.1f', '%'),
        ('Expire Rate (%)', 'expire_rate', '.1f', '%'),
        ('Avg Win (%)', 'avg_win', '.2f', '%'),
        ('Avg Loss (%)', 'avg_loss', '.2f', '%'),
        ('Expectancy (%)', 'expectancy', '.3f', '%'),
    ]

    for label, key, fmt, suffix in rows:
        bv = b[key]
        lv = lb[key] if lb else 0
        delta = lv - bv if lb else 0
        delta_str = f"{delta:+.1f}" if abs(delta) > 0.05 else "—"
        b_str = format(bv, fmt) + suffix
        l_str = (format(lv, fmt) + suffix) if lb else '—'
        print(f"  {label:<30} {b_str:>18} {l_str:>18} {delta_str:>12}")

    # ATR breakdown
    print(f"\n  {'─' * 72}")
    print(f"  ATR BREAKDOWN (Limit-Buy Strategy)")
    print(f"  {'─' * 72}")
    print(f"  {'ATR Range':<20} {'N':>5} {'Traded':>7} {'Missed':>7} "
          f"{'WR':>7} {'SL%':>7} {'TP%':>7} {'Avg':>8} {'PnL':>8}")
    print(f"  {'─' * 72}")

    atr_buckets = [
        ('< 2.0%', 0, 2.0),
        ('2.0-2.5%', 2.0, 2.5),
        ('2.5-3.0%', 2.5, 3.0),
        ('3.0-3.5%', 3.0, 3.5),
        ('>= 3.5% (open)', 3.5, 999),
    ]

    lb_results = list(zip(picks, [simulate_limit_buy(p) for p in picks]))
    for bkt_label, lo, hi in atr_buckets:
        bp = [(p, r) for p, r in lb_results
              if r is not None and lo <= (p.get('atr_pct') or 0) < hi]
        if not bp:
            continue
        traded = [(p, r) for p, r in bp if r['exit_type'] != 'MISSED']
        missed = [(p, r) for p, r in bp if r['exit_type'] == 'MISSED']
        if traded:
            rets = [r['return_pct'] for _, r in traded]
            w = sum(1 for ret in rets if ret > 0)
            sl = sum(1 for _, r in traded if r['exit_type'] == 'SL')
            tp = sum(1 for _, r in traded if r['exit_type'] == 'TP1')
            nt = len(traded)
            print(f"  {bkt_label:<20} {len(bp):>5} {nt:>7} {len(missed):>7} "
                  f"{w/nt*100:>6.1f}% {sl/nt*100:>6.1f}% {tp/nt*100:>6.1f}% "
                  f"{np.mean(rets):>+7.2f}% {sum(rets):>+7.1f}%")
        else:
            print(f"  {bkt_label:<20} {len(bp):>5} {'0':>7} {len(missed):>7} "
                  f"{'—':>7} {'—':>7} {'—':>7} {'—':>8} {'—':>8}")

    # Per-regime
    print(f"\n  {'─' * 72}")
    print(f"  PER REGIME")
    print(f"  {'─' * 72}")
    print(f"  {'Regime':<10} {'Strategy':<14} {'N':>5} {'WR':>7} {'SL%':>7} "
          f"{'TP%':>7} {'Avg':>8} {'PnL':>8}")
    print(f"  {'─' * 72}")

    for regime in ['BULL', 'STRESS', 'CRISIS']:
        for strat_label, results_list in [('Baseline', b['results']),
                                           ('Limit-Buy', lb['results'] if lb else [])]:
            rp = [r for i, r in enumerate(results_list)
                  if picks[i]['regime'] == regime] if len(results_list) == len(picks) else []
            # Need to match by index — use the picks list
            # Actually, let's redo this properly
            pass

    # Simpler per-regime
    for regime in ['BULL', 'STRESS', 'CRISIS']:
        b_regime = [r for r, p in zip(b['results'], picks)
                    if p['regime'] == regime and r is not None]
        if not b_regime:
            continue

        b_rets = [r['return_pct'] for r in b_regime]
        b_w = sum(1 for r in b_rets if r > 0)
        b_sl = sum(1 for r in b_regime if r['exit_type'] == 'SL')
        b_tp = sum(1 for r in b_regime if r['exit_type'] == 'TP1')

        print(f"  {regime:<10} {'Baseline':<14} {len(b_regime):>5} "
              f"{b_w/len(b_regime)*100:>6.1f}% {b_sl/len(b_regime)*100:>6.1f}% "
              f"{b_tp/len(b_regime)*100:>6.1f}% {np.mean(b_rets):>+7.2f}% "
              f"{sum(b_rets):>+7.1f}%")

        if lb:
            lb_regime_all = [(r, p) for r, p in zip(
                [simulate_limit_buy(p) for p in picks], picks)
                if p['regime'] == regime and r is not None
                and r['exit_type'] != 'MISSED']
            if lb_regime_all:
                lb_rets = [r['return_pct'] for r, _ in lb_regime_all]
                lb_w = sum(1 for r in lb_rets if r > 0)
                lb_sl = sum(1 for r, _ in lb_regime_all if r['exit_type'] == 'SL')
                lb_tp = sum(1 for r, _ in lb_regime_all if r['exit_type'] == 'TP1')
                print(f"  {'':<10} {'Limit-Buy':<14} {len(lb_regime_all):>5} "
                      f"{lb_w/len(lb_regime_all)*100:>6.1f}% "
                      f"{lb_sl/len(lb_regime_all)*100:>6.1f}% "
                      f"{lb_tp/len(lb_regime_all)*100:>6.1f}% "
                      f"{np.mean(lb_rets):>+7.2f}% {sum(lb_rets):>+7.1f}%")

    # Exit day distribution (limit-buy only)
    if lb:
        print(f"\n  {'─' * 72}")
        print(f"  EXIT DAY DISTRIBUTION (Limit-Buy, traded only)")
        print(f"  {'─' * 72}")
        exit_days = defaultdict(list)
        for r in lb['results']:
            exit_days[r['exit_day']].append(r['return_pct'])
        for day in sorted(exit_days.keys()):
            rets = exit_days[day]
            w = sum(1 for r in rets if r > 0)
            print(f"  D+{day}: {len(rets):>4} trades, WR={w/len(rets)*100:.0f}%, "
                  f"avg={np.mean(rets):+.2f}%, PnL={sum(rets):+.1f}%")

    print(f"\n{'=' * 80}")


def main():
    data = load_data()

    print("\n--- Step 1: Walk-forward v4.4b scoring ---")
    picks = run_walkforward(data)

    print("\n--- Step 2: Downloading OHLC data ---")
    picks = download_ohlc(picks)

    # Filter to picks with OHLC data
    picks_with_data = [p for p in picks if p.get('ohlc') and len(p['ohlc']) >= 1 and p['ohlc'][0]]
    print(f"\nPicks with OHLC: {len(picks_with_data)}/{len(picks)}")

    print("\n--- Step 3: Simulating strategies ---")
    baseline_results = [simulate_baseline(p) for p in picks_with_data]
    limit_results = [simulate_limit_buy(p) for p in picks_with_data]

    # Filter valid results
    baseline_valid = [(p, r) for p, r in zip(picks_with_data, baseline_results) if r is not None]
    limit_valid = [(p, r) for p, r in zip(picks_with_data, limit_results) if r is not None]

    print(f"Baseline: {len(baseline_valid)} valid simulations")
    print(f"Limit-Buy: {len(limit_valid)} valid simulations")

    baseline_metrics = compute_metrics([r for _, r in baseline_valid], 'Baseline v4.4b')
    limit_metrics = compute_metrics([r for _, r in limit_valid], 'Limit-Buy v4.6')

    print_comparison(baseline_metrics, limit_metrics, picks_with_data)


if __name__ == '__main__':
    main()
