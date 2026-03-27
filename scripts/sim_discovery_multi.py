#!/usr/bin/env python3
"""
Discovery Multi-Strategy Simulator v15.2
=========================================
Walk-forward backtest: 5 strategies on 75K backfill_signal_outcomes.
Tests: which strategy works best? What's the optimal ranking?
Max 2 picks per strategy, sorted by best E[R] / WR / Sharpe.

Strategies:
  DIP:        momentum_5d between -3% and -15%, beta < 1.5
  OVERSOLD:   momentum_5d < -5%, d20h < -10%
  MOMENTUM:   momentum_5d > +2%, momentum_20d > 0%, d20h > -10%
  VALUE:      PE 3-15, beta < 1.5, mcap > 5B (simulated via atr < 3%)
  CONTRARIAN: worst sector, best stock in sector

Ranking tests:
  A: E[R] descending (kernel expected return)
  B: ATR-weighted E[R] (higher ATR = higher return potential)
  C: Strategy-priority (OVERSOLD > DIP > VALUE > CONTRARIAN > MOMENTUM)
  D: Composite (E[R] × WR prediction × ATR blend)
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

PER_TRADE = 500  # $500 per pick (Discovery is display/research, not DIP engine)
COMMISSION = 0.50
SLIPPAGE = 0.10  # %
MAX_PER_STRATEGY = 2
MAX_TOTAL = 8
HOLD_DAYS = 5


def load_data():
    conn = None  # via get_session())

    # Load signals with outcomes + macro
    signals = conn.execute("""
        SELECT s.scan_date, s.symbol, s.sector, s.scan_price,
               s.atr_pct, s.entry_rsi, s.distance_from_20d_high,
               s.momentum_5d, s.momentum_20d, s.volume_ratio,
               s.vix_at_signal,
               s.outcome_1d, s.outcome_2d, s.outcome_3d, s.outcome_4d, s.outcome_5d,
               s.outcome_max_gain_5d, s.outcome_max_dd_5d
        FROM backfill_signal_outcomes s
        WHERE s.outcome_5d IS NOT NULL
        ORDER BY s.scan_date
    """).fetchall()

    # Load fundamentals for PE/mcap simulation
    funds = {}
    for r in conn.execute("SELECT symbol, beta, pe_forward, market_cap FROM stock_fundamentals"):
        funds[r[0]] = {'beta': r[1] or 1, 'pe': r[2], 'mcap': r[3] or 1e9}

    # Breadth for condition detection
    breadth = dict(conn.execute("SELECT date, pct_above_20d_ma FROM market_breadth").fetchall())

    conn.close()
    return signals, funds, breadth


def detect_condition(vix, breadth):
    vix = vix or 20
    breadth = breadth or 50
    if vix > 25 and breadth < 35:
        return 'STRESS'
    if vix < 18 and breadth > 55:
        return 'BULL'
    return 'NORMAL'


def classify_strategy(sig, funds):
    """Classify which strategies a signal qualifies for."""
    _, sym, sector, price, atr, rsi, d20h, mom5, mom20, vol, vix = sig[:11]
    mom5 = mom5 or 0
    mom20 = mom20 or 0
    d20h = d20h or 0
    vol = vol or 1
    beta = funds.get(sym, {}).get('beta', 1) or 1
    pe = funds.get(sym, {}).get('pe')
    mcap = funds.get(sym, {}).get('mcap', 1e9) or 1e9

    strategies = []

    # DIP: -3% to -15%, beta < 1.5, vol > 0.3
    if -15 < mom5 < -3 and beta < 1.5 and vol > 0.3:
        strategies.append('DIP')

    # OVERSOLD: mom < -5%, d20h < -10%
    if mom5 < -5 and d20h < -10 and beta < 2.0:
        strategies.append('OVERSOLD')

    # MOMENTUM: mom > 2%, mom20 > 0%, d20h > -10%
    if mom5 > 2 and mom20 > 0 and d20h > -10 and beta < 1.5:
        strategies.append('MOMENTUM')

    # VALUE: PE 3-15, beta < 1.5, mcap > 5B
    if pe and 3 < pe < 15 and beta < 1.5 and mcap > 5e9 and mom5 > -10:
        strategies.append('VALUE')

    return strategies


def simulate(signals, funds, breadth, rank_fn, label):
    """Run walk-forward simulation with given ranking function."""
    by_date = defaultdict(list)
    for sig in signals:
        by_date[sig[0]].append(sig)

    monthly_pnl = defaultdict(float)
    yearly_pnl = defaultdict(float)
    yearly_trades = defaultdict(int)
    yearly_wins = defaultdict(int)
    strat_stats = defaultdict(lambda: {'pnl': 0, 'n': 0, 'w': 0})
    total_trades = 0
    total_wins = 0

    for day in sorted(by_date.keys()):
        day_signals = by_date[day]
        month = day[:7]
        year = day[:4]
        vix = day_signals[0][10] if day_signals else 20
        b = breadth.get(day)

        # Classify each signal into strategies
        candidates = []
        for sig in day_signals:
            strats = classify_strategy(sig, funds)
            if not strats:
                continue
            for strat in strats:
                candidates.append((strat, sig))

        if not candidates:
            continue

        # Apply ranking
        ranked = rank_fn(candidates, vix, b)

        # Enforce max 2 per strategy, max 8 total
        strat_count = defaultdict(int)
        selected = []
        for strat, sig in ranked:
            if strat_count[strat] >= MAX_PER_STRATEGY:
                continue
            if len(selected) >= MAX_TOTAL:
                break
            strat_count[strat] += 1
            selected.append((strat, sig))

        # Execute trades
        for strat, sig in selected:
            outcome_5d = sig[15]
            if outcome_5d is None:
                continue

            cost_pct = SLIPPAGE * 2 + COMMISSION / PER_TRADE * 100
            net_ret = outcome_5d - cost_pct
            pnl = PER_TRADE * net_ret / 100

            monthly_pnl[month] += pnl
            yearly_pnl[year] += pnl
            yearly_trades[year] += 1
            total_trades += 1
            strat_stats[strat]['pnl'] += pnl
            strat_stats[strat]['n'] += 1

            if net_ret > 0:
                total_wins += 1
                yearly_wins[year] += 1
                strat_stats[strat]['w'] += 1

    months = sorted(monthly_pnl.keys())
    mr = [monthly_pnl[m] for m in months]
    avg = np.mean(mr) if mr else 0
    std = np.std(mr) if len(mr) > 1 else 1
    sharpe = avg / std * np.sqrt(12) if std > 0 else 0
    cum = np.cumsum(mr)
    peak = np.maximum.accumulate(cum)
    mdd = float(np.min(cum - peak)) if len(cum) else 0
    wr = total_wins / total_trades * 100 if total_trades else 0
    prof = sum(1 for m in months if monthly_pnl[m] > 0) / len(months) * 100 if months else 0

    return {
        'label': label, 'pnl': sum(mr), 'trades': total_trades, 'wr': wr,
        'mo': avg, 'sharpe': sharpe, 'mdd': mdd, 'prof': prof,
        'strat_stats': dict(strat_stats),
        'yp': dict(yearly_pnl), 'yt': dict(yearly_trades), 'yw': dict(yearly_wins),
    }


# === Ranking Functions ===

def rank_by_er(candidates, vix, b):
    """A: Sort by E[R] (outcome proxy: distance_from_20d_high as IC=0.52 predictor)."""
    # Use distance_from_20d_high as E[R] proxy (IC=0.52 strongest predictor)
    return sorted(candidates, key=lambda x: -(x[1][6] or 0))  # d20h: more negative = better dip


def rank_by_atr_weighted(candidates, vix, b):
    """B: ATR-weighted — higher ATR × deeper dip = higher priority."""
    def score(x):
        atr = x[1][4] or 2
        d20h = abs(x[1][6] or 0)
        return atr * d20h / 10
    return sorted(candidates, key=lambda x: -score(x))


def rank_by_strategy_priority(candidates, vix, b):
    """C: Strategy priority — OVERSOLD first, then DIP, VALUE, CONTRARIAN, MOMENTUM."""
    priority = {'OVERSOLD': 0, 'DIP': 1, 'VALUE': 2, 'CONTRARIAN': 3, 'MOMENTUM': 4}
    return sorted(candidates, key=lambda x: (priority.get(x[0], 5), -(x[1][6] or 0)))


def rank_by_composite(candidates, vix, b):
    """D: Composite — blend of dip depth + ATR + strategy priority."""
    priority_score = {'OVERSOLD': 1.2, 'DIP': 1.0, 'VALUE': 0.9, 'CONTRARIAN': 0.8, 'MOMENTUM': 0.7}
    def score(x):
        strat, sig = x
        d20h = abs(sig[6] or 0)  # deeper = better
        atr = sig[4] or 2
        vol = sig[9] or 1
        sp = priority_score.get(strat, 0.5)
        return sp * (d20h * 0.5 + atr * 0.3 + min(vol, 2) * 0.2)
    return sorted(candidates, key=lambda x: -score(x))


def rank_by_vix_regime(candidates, vix, b):
    """E: Regime-aware — adjust priority by VIX/breadth."""
    condition = detect_condition(vix, b)
    if condition == 'STRESS':
        priority = {'OVERSOLD': 1.5, 'DIP': 1.2, 'CONTRARIAN': 1.0, 'VALUE': 0.8, 'MOMENTUM': 0.3}
    elif condition == 'BULL':
        priority = {'MOMENTUM': 1.5, 'VALUE': 1.0, 'DIP': 0.8, 'CONTRARIAN': 0.7, 'OVERSOLD': 0.5}
    else:
        priority = {'DIP': 1.2, 'VALUE': 1.0, 'OVERSOLD': 1.0, 'CONTRARIAN': 0.8, 'MOMENTUM': 0.7}

    def score(x):
        strat, sig = x
        d20h = abs(sig[6] or 0)
        sp = priority.get(strat, 0.5)
        return sp * d20h
    return sorted(candidates, key=lambda x: -score(x))


def rank_by_mom_regime(candidates, vix, b):
    """F: Momentum-regime — STRESS favors deep dips, BULL favors momentum."""
    condition = detect_condition(vix, b)
    def score(x):
        strat, sig = x
        mom5 = sig[7] or 0
        d20h = abs(sig[6] or 0)
        atr = sig[4] or 2
        if condition == 'STRESS':
            # Favor deep dips with high ATR (mean reversion)
            return d20h * atr * 0.1
        elif condition == 'BULL':
            # Favor momentum with near-high
            return max(mom5, 0) * (10 - min(d20h, 10)) * 0.1
        else:
            # Balanced
            return d20h * 0.5 + atr * 0.3
    return sorted(candidates, key=lambda x: -score(x))


def main():
    signals, funds, breadth = load_data()
    print(f"Loaded {len(signals):,} signals, {len(funds):,} fundamentals\n")

    # Test all ranking methods
    rankings = [
        (rank_by_er, "A: E[R] (dip depth)"),
        (rank_by_atr_weighted, "B: ATR × dip depth"),
        (rank_by_strategy_priority, "C: Strategy priority"),
        (rank_by_composite, "D: Composite blend"),
        (rank_by_vix_regime, "E: VIX regime-aware"),
        (rank_by_mom_regime, "F: Momentum-regime"),
    ]

    results = []
    for fn, label in rankings:
        r = simulate(signals, funds, breadth, fn, label)
        results.append(r)

    # Also test: no multi-strategy (DIP only, like old system)
    def rank_dip_only(candidates, vix, b):
        dip = [(s, sig) for s, sig in candidates if s == 'DIP']
        return sorted(dip, key=lambda x: -(x[1][6] or 0))
    results.append(simulate(signals, funds, breadth, rank_dip_only, "X: DIP only (baseline)"))

    # Print comparison
    print(f"{'Ranking':<30} {'PnL':>9} {'$/mo':>7} {'N':>7} {'WR%':>6} {'Shrp':>6} {'MDD':>9} {'%Prof':>6}")
    print("─" * 90)
    for r in results:
        print(f"  {r['label']:<30} ${r['pnl']:>+7,.0f} ${r['mo']:>+5,.0f} {r['trades']:>6,} "
              f"{r['wr']:>5.1f}% {r['sharpe']:>5.2f} ${r['mdd']:>+8,.0f} {r['prof']:>5.1f}%")

    # Best ranking detail
    best = max(results, key=lambda r: r['sharpe'])
    print(f"\n{'='*70}")
    print(f"  BEST: {best['label']} (Sharpe={best['sharpe']:.2f})")
    print(f"{'='*70}")

    # Strategy breakdown for best
    print(f"\n  Per-Strategy Breakdown:")
    print(f"  {'Strategy':<15} {'N':>6} {'PnL':>9} {'WR%':>6} {'$/trade':>8}")
    for strat in ['DIP', 'OVERSOLD', 'MOMENTUM', 'VALUE', 'CONTRARIAN']:
        st = best['strat_stats'].get(strat, {'n': 0, 'pnl': 0, 'w': 0})
        if st['n'] > 0:
            wr = st['w'] / st['n'] * 100
            pt = st['pnl'] / st['n']
            print(f"  {strat:<15} {st['n']:>6,} ${st['pnl']:>+8,.0f} {wr:>5.1f}% ${pt:>+7.2f}")

    # Yearly for best
    print(f"\n  Yearly:")
    for y in sorted(best['yp'].keys()):
        t = best['yt'][y]
        w = best['yw'].get(y, 0)
        wr = w / t * 100 if t else 0
        print(f"  {y}: PnL=${best['yp'][y]:>+,.0f} trades={t} WR={wr:.1f}%")

    # Yearly for ALL rankings (comparison)
    print(f"\n  Year-by-Year Comparison:")
    print(f"  {'Year':<6}", end='')
    for r in results:
        label = r['label'][:12]
        print(f" {label:>13}", end='')
    print()
    for y in sorted(results[0]['yp'].keys()):
        print(f"  {y:<6}", end='')
        for r in results:
            pnl = r['yp'].get(y, 0)
            print(f" ${pnl:>+11,.0f}", end='')
        print()

    # Strategy contribution by ranking
    print(f"\n  Strategy Contribution ($/mo) by Ranking:")
    print(f"  {'Strategy':<15}", end='')
    for r in results:
        label = r['label'][:12]
        print(f" {label:>13}", end='')
    print()
    for strat in ['DIP', 'OVERSOLD', 'MOMENTUM', 'VALUE', 'CONTRARIAN']:
        print(f"  {strat:<15}", end='')
        for r in results:
            st = r['strat_stats'].get(strat, {'pnl': 0, 'n': 0})
            n_months = len(set(sig[0][:7] for sig in signals))
            ppm = st['pnl'] / max(n_months / 12, 1) if st['n'] > 0 else 0
            print(f" ${ppm:>+12,.0f}", end='')
        print()

    # Final recommendation
    print(f"\n{'='*70}")
    print(f"  RECOMMENDATION")
    print(f"{'='*70}")
    sorted_results = sorted(results, key=lambda r: r['sharpe'], reverse=True)
    for i, r in enumerate(sorted_results[:3]):
        print(f"  #{i+1} {r['label']:<30} Sharpe={r['sharpe']:.2f} $/mo=${r['mo']:>+,.0f}")


if __name__ == '__main__':
    main()
