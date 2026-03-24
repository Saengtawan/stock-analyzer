#!/usr/bin/env python3
"""
Discovery Pipeline Sim v2 — Diagnostic Variants
=================================================
Tests multiple exit methods to find what actually works:
  A: D0-D3 dynamic TP/SL (v15.3 current)
  B: D1 entry, D1/D3 SL/TP check, D5 close (v10-style)
  C: Raw outcome_3d (no SL/TP — pure stock selection quality)
  D: Raw outcome_5d (no SL/TP — 5-day hold)

Also tests kernel filtering vs no-kernel to isolate pipeline alpha.
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict
from scipy.spatial.distance import cdist

DB = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

PER_TRADE = 500
COMMISSION = 0.50
SLIPPAGE = 0.10
MAX_PER_STRATEGY = 2
MAX_TOTAL = 8
MIN_MCAP_B = 30
MAX_VOL_RATIO = 3.0


def load_all():
    conn = sqlite3.connect(str(DB))
    signals = conn.execute("""
        SELECT b.scan_date, b.symbol, b.sector, b.scan_price,
               b.atr_pct, b.momentum_5d, b.momentum_20d,
               b.distance_from_20d_high, b.volume_ratio, b.vix_at_signal,
               b.outcome_5d, b.outcome_1d, b.outcome_3d,
               COALESCE(m.vix_close, 20), m.spy_close, m.crude_close,
               COALESCE(m.vix3m_close, 22), m.yield_10y,
               mb.pct_above_20d_ma, mb.new_52w_lows, mb.new_52w_highs,
               d0.open, d0.high, d0.low, d0.close,
               d1.open, d1.high, d1.low, d1.close,
               d2.open, d2.high, d2.low, d2.close,
               d3.open, d3.high, d3.low, d3.close,
               COALESCE(ser.pct_change, 0),
               d5.open, d5.high, d5.low, d5.close
        FROM backfill_signal_outcomes b
        LEFT JOIN macro_snapshots m
            ON m.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        LEFT JOIN market_breadth mb
            ON mb.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        JOIN signal_daily_bars d0 ON b.scan_date=d0.scan_date AND b.symbol=d0.symbol AND d0.day_offset=0
        JOIN signal_daily_bars d1 ON b.scan_date=d1.scan_date AND b.symbol=d1.symbol AND d1.day_offset=1
        JOIN signal_daily_bars d2 ON b.scan_date=d2.scan_date AND b.symbol=d2.symbol AND d2.day_offset=2
        JOIN signal_daily_bars d3 ON b.scan_date=d3.scan_date AND b.symbol=d3.symbol AND d3.day_offset=3
        JOIN signal_daily_bars d5 ON b.scan_date=d5.scan_date AND b.symbol=d5.symbol AND d5.day_offset=5
        LEFT JOIN sector_etf_daily_returns ser
            ON ser.sector = b.sector
            AND ser.date = CASE
                WHEN strftime('%%w', b.scan_date) = '6' THEN date(b.scan_date, '-1 day')
                WHEN strftime('%%w', b.scan_date) = '0' THEN date(b.scan_date, '-2 days')
                ELSE b.scan_date END
        WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0 AND d0.open > 0 AND d1.open > 0
        ORDER BY b.scan_date
    """).fetchall()

    funds = {}
    for r in conn.execute("SELECT symbol, beta, pe_forward, market_cap FROM stock_fundamentals"):
        funds[r[0]] = {'beta': r[1] or 1, 'pe': r[2], 'mcap': r[3] or 1e9}

    crude_lag = {}
    for r in conn.execute("""
        SELECT date, crude_close,
               LAG(crude_close, 5) OVER (ORDER BY date) as crude_5d_ago
        FROM macro_snapshots WHERE crude_close IS NOT NULL
    """):
        if r[2] and r[2] > 0:
            crude_lag[r[0]] = (r[1] / r[2] - 1) * 100
    conn.close()
    return signals, funds, crude_lag


# Column indices (same as v1 + D5 bars at 38-41)
I_DATE, I_SYM, I_SEC, I_PRICE = 0, 1, 2, 3
I_ATR, I_MOM5, I_MOM20, I_D20H, I_VOL, I_VIX_SIG = 4, 5, 6, 7, 8, 9
I_OUT5, I_OUT1, I_OUT3 = 10, 11, 12
I_VIX, I_SPY, I_CRUDE, I_VIX3M, I_Y10 = 13, 14, 15, 16, 17
I_BREADTH, I_LOWS, I_HIGHS = 18, 19, 20
I_D0O, I_D0H, I_D0L, I_D0C = 21, 22, 23, 24
I_D1O, I_D1H, I_D1L, I_D1C = 25, 26, 27, 28
I_D2O, I_D2H, I_D2L, I_D2C = 29, 30, 31, 32
I_D3O, I_D3H, I_D3L, I_D3C = 33, 34, 35, 36
I_SEC1D = 37
I_D5O, I_D5H, I_D5L, I_D5C = 38, 39, 40, 41


class GaussianKernel:
    def __init__(self, bandwidth):
        self.bw = bandwidth
        self.X = self.y = self.means = self.stds = None

    def fit(self, features, returns):
        X = np.array(features[-40000:], dtype=np.float64)
        y = np.array(returns[-40000:], dtype=np.float64)
        self.means = X.mean(axis=0)
        self.stds = X.std(axis=0)
        self.stds[self.stds == 0] = 1.0
        self.X = (X - self.means) / self.stds
        self.y = y

    def estimate_batch(self, X_new_raw):
        if self.X is None or len(self.X) == 0:
            return np.zeros(len(X_new_raw))
        X_new = (np.array(X_new_raw, dtype=np.float64) - self.means) / self.stds
        dists = cdist(X_new, self.X)
        weights = np.exp(-0.5 * (dists / self.bw) ** 2)
        total_w = weights.sum(axis=1)
        total_w[total_w < 1e-10] = 1e-10
        return (weights @ self.y) / total_w


def build_macro_vec(sig, crude_lag):
    date = sig[I_DATE]
    vix, spy, crude, vix3m, y10 = sig[I_VIX], sig[I_SPY], sig[I_CRUDE], sig[I_VIX3M], sig[I_Y10]
    breadth, lows, highs = sig[I_BREADTH], sig[I_LOWS], sig[I_HIGHS]
    if any(v is None for v in [spy, crude, y10, breadth, lows, highs]):
        return None
    return [lows, crude_lag.get(date, 0), breadth, highs, y10, spy, crude,
            (vix or 20) - (vix3m or 22)]


def build_stock_vec(sig, mv):
    atr, mom5, d20h, vol, sec1d = sig[I_ATR], sig[I_MOM5], sig[I_D20H], sig[I_VOL], sig[I_SEC1D]
    if any(v is None for v in [atr, mom5, d20h, vol]):
        return None
    return mv + [atr, mom5 or 0, d20h or 0, vol or 1, sec1d or 0]


def classify_strategies(sig, funds, worst_sector=None):
    sym, mom5, mom20, d20h, vol = sig[I_SYM], sig[I_MOM5] or 0, sig[I_MOM20] or 0, sig[I_D20H] or 0, sig[I_VOL] or 1
    f = funds.get(sym, {})
    beta, pe, mcap = f.get('beta', 1) or 1, f.get('pe'), f.get('mcap', 1e9) or 1e9
    strats = []
    if -15 < mom5 < -3 and beta < 1.5 and vol > 0.3:
        strats.append('DIP')
    if mom5 < -5 and d20h < -10 and beta < 2.0:
        strats.append('OVERSOLD')
    if pe and 3 < pe < 15 and beta < 1.5 and mcap > 5e9 and mom5 > -10:
        strats.append('VALUE')
    if worst_sector and sig[I_SEC] == worst_sector and beta < 1.5 and mom5 > -15:
        strats.append('CONTRARIAN')
    return strats


# === EXIT METHODS ===

def exit_A_d0d3_dynamic(sig, atr):
    """A: D0 entry, D0-D3 dynamic TP/SL (v15.3 current)."""
    entry = sig[I_D0O]
    if entry <= 0: return 0.0
    sl = max(1.5, min(3.5, 0.8 * atr))
    tps = [max(1.0, 0.55*atr), max(1.0, 0.55*atr), max(1.5, 0.85*atr), max(1.5, 1.09*atr)]
    bars = [(sig[I_D0H], sig[I_D0L]), (sig[I_D1H], sig[I_D1L]),
            (sig[I_D2H], sig[I_D2L]), (sig[I_D3H], sig[I_D3L])]
    for (h, l), tp in zip(bars, tps):
        if (l/entry-1)*100 <= -sl: return -sl
        if (h/entry-1)*100 >= tp: return tp
    return (sig[I_D3C]/entry-1)*100


def exit_B_d1_entry_d5(sig, atr):
    """B: D1 entry, D1/D3 SL/TP check, D5 close (v10-style)."""
    entry = sig[I_D1O]
    if entry <= 0: return 0.0
    sl = max(1.5, min(5.0, 1.5 * atr))
    tp = max(1.0, 1.2 * atr)
    for h, l in [(sig[I_D1H], sig[I_D1L]), (sig[I_D3H], sig[I_D3L])]:
        if (l/entry-1)*100 <= -sl: return -sl
        if (h/entry-1)*100 >= tp: return tp
    return (sig[I_D5C]/entry-1)*100


def exit_C_outcome3d(sig, atr):
    """C: Raw outcome_3d (no SL/TP — pure stock selection test)."""
    return sig[I_OUT3] if sig[I_OUT3] is not None else 0.0


def exit_D_outcome5d(sig, atr):
    """D: Raw outcome_5d (no SL/TP — 5-day hold)."""
    return sig[I_OUT5] if sig[I_OUT5] is not None else 0.0


def exit_E_d0d3_wider_sl(sig, atr):
    """E: D0 entry, wider SL (1.5×ATR), TP=max(1.0×ATR, 5%) (relaxed)."""
    entry = sig[I_D0O]
    if entry <= 0: return 0.0
    sl = max(2.0, min(5.0, 1.5 * atr))
    tp = max(3.0, 1.0 * atr)  # uniform TP, no per-day dynamic
    bars = [(sig[I_D0H], sig[I_D0L]), (sig[I_D1H], sig[I_D1L]),
            (sig[I_D2H], sig[I_D2L]), (sig[I_D3H], sig[I_D3L])]
    for h, l in bars:
        if (l/entry-1)*100 <= -sl: return -sl
        if (h/entry-1)*100 >= tp: return tp
    return (sig[I_D3C]/entry-1)*100


EXIT_METHODS = {
    'A: D0-D3 dyn TP/SL': exit_A_d0d3_dynamic,
    'B: D1→D5 wide SL':   exit_B_d1_entry_d5,
    'C: outcome_3d raw':   exit_C_outcome3d,
    'D: outcome_5d raw':   exit_D_outcome5d,
    'E: D0-D3 wider SL':  exit_E_d0d3_wider_sl,
}


def run_sim(signals, funds, crude_lag, exit_fn, use_kernel=True, use_strategy=True):
    """Run one variant of the sim. Returns dict of results."""
    by_month = defaultdict(list)
    for sig in signals:
        by_month[sig[I_DATE][:7]].append(sig)
    months = sorted(by_month.keys())

    train_macro, train_macro_r = [], []
    train_stock, train_stock_r = [], []
    rng = np.random.RandomState(42)

    monthly_pnl = []
    tot = {'t': 0, 'w': 0, 'p': 0.0}
    strat_stats = defaultdict(lambda: {'t': 0, 'w': 0, 'p': 0.0})

    def accumulate(month_sigs):
        for sig in month_sigs:
            mv = build_macro_vec(sig, crude_lag)
            if mv and sig[I_OUT5] is not None:
                train_macro.append(mv)
                train_macro_r.append(sig[I_OUT5])
                sv = build_stock_vec(sig, mv)
                if sv:
                    train_stock.append(sv)
                    train_stock_r.append(sig[I_OUT5])

    for mi, month in enumerate(months):
        if mi < 12:
            accumulate(by_month[month])
            continue

        # Fit kernels (if using)
        stock_kernel = None
        if use_kernel and len(train_stock) >= 500:
            stock_kernel = GaussianKernel(bandwidth=1.0)
            stock_kernel.fit(train_stock, train_stock_r)

        test_sigs = by_month[month]
        by_day = defaultdict(list)
        for sig in test_sigs:
            by_day[sig[I_DATE]].append(sig)

        mo_pnl = 0.0
        for day, day_sigs in sorted(by_day.items()):
            if not day_sigs:
                continue
            s0 = day_sigs[0]
            mv = build_macro_vec(s0, crude_lag)
            if mv is None:
                continue

            # Find worst sector
            sector_moms = defaultdict(list)
            for sig in day_sigs:
                if sig[I_SEC]:
                    sector_moms[sig[I_SEC]].append(sig[I_MOM5] or 0)
            sector_avg = {s: np.mean(ms) for s, ms in sector_moms.items() if len(ms) >= 3}
            worst_sector = min(sector_avg, key=sector_avg.get) if sector_avg else None

            # Filter eligible stocks
            eligible = []
            stock_vecs = []
            for sig in day_sigs:
                sym = sig[I_SYM]
                mcap_b = (funds.get(sym, {}).get('mcap', 1e9) or 1e9) / 1e9
                vol = sig[I_VOL] or 1
                if mcap_b < MIN_MCAP_B or vol > MAX_VOL_RATIO:
                    continue
                sv = build_stock_vec(sig, mv)
                if sv is None:
                    continue
                eligible.append(sig)
                stock_vecs.append(sv)

            if not eligible:
                continue

            # Score with kernel (if using)
            if stock_kernel and stock_vecs:
                stock_ers = stock_kernel.estimate_batch(stock_vecs)
            else:
                stock_ers = np.zeros(len(eligible))

            # Build candidate list
            if use_strategy:
                scored = []
                for i, sig in enumerate(eligible):
                    ser = float(stock_ers[i])
                    # NO negative E[R] filter (proven to hurt in v1)
                    strats = classify_strategies(sig, funds, worst_sector)
                    if not strats:
                        continue
                    scored.append((ser, sig, strats))

                # Rank by volume_ratio desc
                scored.sort(key=lambda x: -(x[1][I_VOL] or 0))

                # Pick: max 2/strat, max 8
                strat_count = defaultdict(int)
                selected = []
                for er, sig, strats in scored:
                    if len(selected) >= MAX_TOTAL:
                        break
                    for strat in strats:
                        if strat_count[strat] < MAX_PER_STRATEGY:
                            strat_count[strat] += 1
                            selected.append((strat, sig))
                            break
            else:
                # No strategy: just top 8 by volume_ratio
                top_vol = sorted(eligible, key=lambda s: -(s[I_VOL] or 0))[:MAX_TOTAL]
                selected = [('NONE', sig) for sig in top_vol]

            # Execute
            cost_pct = SLIPPAGE * 2 + COMMISSION / PER_TRADE * 100
            for strat, sig in selected:
                atr = sig[I_ATR] or 2
                ret = exit_fn(sig, atr)
                net = ret - cost_pct
                pnl = PER_TRADE * net / 100
                mo_pnl += pnl
                tot['t'] += 1; tot['p'] += pnl
                if net > 0: tot['w'] += 1
                strat_stats[strat]['t'] += 1; strat_stats[strat]['p'] += pnl
                if net > 0: strat_stats[strat]['w'] += 1

        monthly_pnl.append(mo_pnl)
        accumulate(by_month[month])

    # Compute summary
    if not monthly_pnl or not tot['t']:
        return None
    avg = np.mean(monthly_pnl)
    std = max(np.std(monthly_pnl), 0.01)
    return {
        'monthly': monthly_pnl,
        'trades': tot['t'],
        'wr': tot['w'] / tot['t'] * 100,
        'er': tot['p'] / tot['t'],
        'mo_avg': avg,
        'sharpe': avg / std * np.sqrt(12),
        'win_mo': sum(1 for m in monthly_pnl if m > 0),
        'n_mo': len(monthly_pnl),
        'worst': min(monthly_pnl),
        'best': max(monthly_pnl),
        'total': sum(monthly_pnl),
        'strats': dict(strat_stats),
    }


def main():
    signals, funds, crude_lag = load_all()
    print(f"Loaded {len(signals):,} signals\n")

    # Run all variants
    variants = []

    for exit_name, exit_fn in EXIT_METHODS.items():
        # Full pipeline (kernel + strategy)
        r = run_sim(signals, funds, crude_lag, exit_fn, use_kernel=True, use_strategy=True)
        if r:
            r['label'] = f"PIPE | {exit_name}"
            variants.append(r)

        # No kernel, but with strategy
        r = run_sim(signals, funds, crude_lag, exit_fn, use_kernel=False, use_strategy=True)
        if r:
            r['label'] = f"STRT | {exit_name}"
            variants.append(r)

        # No strategy, no kernel (top volume only)
        r = run_sim(signals, funds, crude_lag, exit_fn, use_kernel=False, use_strategy=False)
        if r:
            r['label'] = f"TVOL | {exit_name}"
            variants.append(r)

    # Print comparison
    print(f"{'Variant':<35s} {'N':>6s} {'WR%':>6s} {'$/trd':>7s} {'$/mo':>7s} {'Sharpe':>7s} "
          f"{'WinMo':>6s} {'Worst':>8s} {'Best':>8s} {'Total':>9s}")
    print("─" * 110)

    for r in variants:
        print(f"  {r['label']:<33s} {r['trades']:>5,} {r['wr']:>5.1f}% ${r['er']:>+5.2f} "
              f"${r['mo_avg']:>+6.0f} {r['sharpe']:>+6.2f} "
              f"{r['win_mo']:>2d}/{r['n_mo']:<2d} ${r['worst']:>+7.0f} ${r['best']:>+7.0f} "
              f"${r['total']:>+8.0f}")

    # Group by exit method for cleaner comparison
    print(f"\n{'='*80}")
    print("  SUMMARY BY EXIT METHOD (Pipeline vs Strategy-only vs Top-Volume)")
    print(f"{'='*80}")

    for exit_name in EXIT_METHODS:
        pipe = next((r for r in variants if r['label'] == f"PIPE | {exit_name}"), None)
        strt = next((r for r in variants if r['label'] == f"STRT | {exit_name}"), None)
        tvol = next((r for r in variants if r['label'] == f"TVOL | {exit_name}"), None)

        print(f"\n  {exit_name}")
        for label, r in [("Pipeline(K+S)", pipe), ("Strategy-only", strt), ("TopVol-only", tvol)]:
            if r:
                print(f"    {label:<16s} WR={r['wr']:5.1f}%  $/mo=${r['mo_avg']:>+6.0f}  "
                      f"Sharpe={r['sharpe']:>+5.2f}  N={r['trades']:>5,}")

    # Per-strategy breakdown for best exit method
    print(f"\n{'='*80}")
    print("  PER-STRATEGY BREAKDOWN (best exit per method)")
    print(f"{'='*80}")

    for exit_name in EXIT_METHODS:
        pipe = next((r for r in variants if r['label'] == f"PIPE | {exit_name}"), None)
        if not pipe:
            continue
        print(f"\n  {exit_name} — Pipeline")
        print(f"  {'Strategy':<15s} {'N':>6s} {'WR%':>6s} {'$/trd':>8s} {'PnL':>8s}")
        for strat in ['DIP', 'OVERSOLD', 'VALUE', 'CONTRARIAN']:
            st = pipe['strats'].get(strat, {'t': 0, 'w': 0, 'p': 0})
            if st['t'] > 0:
                wr = st['w'] / st['t'] * 100
                pt = st['p'] / st['t']
                print(f"  {strat:<15s} {st['t']:>6,} {wr:>5.1f}% ${pt:>+7.2f} ${st['p']:>+7.0f}")

    # Key findings
    print(f"\n{'='*80}")
    print("  KEY FINDINGS")
    print(f"{'='*80}")

    # Find best variant
    best = max(variants, key=lambda r: r['sharpe'])
    worst = min(variants, key=lambda r: r['sharpe'])
    print(f"\n  Best:  {best['label']:<35s} Sharpe={best['sharpe']:+.2f} $/mo=${best['mo_avg']:+.0f}")
    print(f"  Worst: {worst['label']:<35s} Sharpe={worst['sharpe']:+.2f} $/mo=${worst['mo_avg']:+.0f}")

    # Kernel adds value?
    for exit_name in EXIT_METHODS:
        pipe = next((r for r in variants if r['label'] == f"PIPE | {exit_name}"), None)
        strt = next((r for r in variants if r['label'] == f"STRT | {exit_name}"), None)
        if pipe and strt:
            delta = pipe['mo_avg'] - strt['mo_avg']
            wr_delta = pipe['wr'] - strt['wr']
            print(f"\n  Kernel delta ({exit_name}):")
            print(f"    $/mo: {delta:>+.0f}  WR: {wr_delta:>+.1f}pp")


if __name__ == '__main__':
    main()
