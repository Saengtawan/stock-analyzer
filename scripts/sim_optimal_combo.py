#!/usr/bin/env python3
"""
Fine-tune the winning changes (D: Crisis Sector + E: LQD filter).
Test optimal LQD threshold, sector lists, and combinations.
Also test D+E combined vs each alone.
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

CAPITAL = 5000
PER_SLOT = 1250
COMMISSION = 0.50
SLIPPAGE = 0.10
MAX_TRADES_PER_DAY = 2

CRISIS_BLOCK = {'Utilities', 'Real Estate'}
CRISIS_GOOD = {'Healthcare', 'Technology', 'Communication Services'}


def load_data():
    conn = None  # via get_session())
    signals = conn.execute("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d,
               volume_ratio, vix_at_signal,
               outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
               outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_5d IS NOT NULL ORDER BY scan_date
    """).fetchall()

    breadth = dict(conn.execute("SELECT date, pct_above_20d_ma FROM market_breadth").fetchall())

    breadth_dates = sorted(breadth.keys())
    breadth_delta = {}
    for i, d in enumerate(breadth_dates):
        if i >= 5:
            breadth_delta[d] = breadth[d] - breadth[breadth_dates[i-5]]

    macro_rows = conn.execute("""
        SELECT date, lqd_close, vix_close FROM macro_snapshots
        WHERE date >= '2020-01-01' ORDER BY date
    """).fetchall()
    macro = {r[0]: {'lqd': r[1], 'vix': r[2]} for r in macro_rows}

    macro_dates = sorted(macro.keys())
    lqd_5d = {}
    for i, d in enumerate(macro_dates):
        if i >= 5 and macro[d]['lqd'] and macro[macro_dates[i-5]]['lqd']:
            prev = macro[macro_dates[i-5]]['lqd']
            if prev > 0:
                lqd_5d[d] = ((macro[d]['lqd'] - prev) / prev) * 100

    conn.close()
    return signals, breadth, breadth_delta, lqd_5d


def base_filters(sig, b_val, bd_val):
    """Common baseline filters (non-VIX, non-breadth-block)."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]
    if mom5d is not None and mom5d < -5.0:
        return False, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 'RSI_HIGH'
    return True, 'PASS'


def sim(signals, breadth, breadth_delta, lqd_5d, strategy_fn):
    by_date = defaultdict(list)
    for sig in signals:
        by_date[sig[0]].append(sig)

    monthly_pnl = defaultdict(float)
    yearly_pnl = defaultdict(float)
    yearly_trades = defaultdict(int)
    yearly_wins = defaultdict(int)
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0

    for day in sorted(by_date.keys()):
        sigs = by_date[day]
        sigs.sort(key=lambda s: s[6] if s[6] is not None else 0)

        b_val = breadth.get(day)
        bd_val = breadth_delta.get(day)
        lqd_val = lqd_5d.get(day)
        month = day[:7]
        year = day[:4]

        day_trades = 0
        for sig in sigs:
            if day_trades >= MAX_TRADES_PER_DAY:
                break

            passed, size_mult = strategy_fn(sig, b_val, bd_val, lqd_val)
            if not passed:
                continue

            price = sig[3]
            outcome_5d = sig[15]
            if outcome_5d is None or not price or price <= 0:
                continue

            pos_size = PER_SLOT * size_mult
            if pos_size < 100:
                continue

            cost_pct = SLIPPAGE * 2 + COMMISSION / pos_size * 100
            net_ret = outcome_5d - cost_pct
            pnl = pos_size * net_ret / 100

            monthly_pnl[month] += pnl
            yearly_pnl[year] += pnl
            yearly_trades[year] += 1
            total_trades += 1
            total_pnl += pnl
            day_trades += 1

            if net_ret > 0:
                total_wins += 1
                yearly_wins[year] += 1

    months = sorted(monthly_pnl.keys())
    m_returns = [monthly_pnl[m] for m in months]
    avg_mo = np.mean(m_returns) if m_returns else 0
    std_mo = np.std(m_returns) if len(m_returns) > 1 else 1
    sharpe = avg_mo / std_mo * np.sqrt(12) if std_mo > 0 else 0

    cum = np.cumsum(m_returns)
    peak = np.maximum.accumulate(cum)
    max_dd = float(np.min(cum - peak)) if len(cum) > 0 else 0

    wr = total_wins / total_trades * 100 if total_trades else 0
    profitable_months = sum(1 for m in months if monthly_pnl[m] > 0)
    pct_profitable = profitable_months / len(months) * 100 if months else 0

    return {
        'pnl': total_pnl, 'trades': total_trades, 'wr': wr,
        'avg_mo': avg_mo, 'sharpe': sharpe, 'max_dd': max_dd,
        'pct_profitable': pct_profitable,
        'yearly_pnl': dict(yearly_pnl),
        'yearly_trades': dict(yearly_trades),
        'yearly_wins': dict(yearly_wins),
        'n_months': len(months),
    }


def print_row(name, r, base=None):
    delta = ''
    if base:
        d = r['avg_mo'] - base['avg_mo']
        delta = f" ({'+' if d>=0 else ''}{d:.0f})"
    y22 = r['yearly_pnl'].get('2022', 0)
    y20 = r['yearly_pnl'].get('2020', 0)
    print(f"  {name:<32} ${r['pnl']:>+8,.0f} ${r['avg_mo']:>+6,.0f}{delta:<8} "
          f"{r['trades']:>6,} {r['wr']:>5.1f}% {r['sharpe']:>5.2f} ${r['max_dd']:>+7,.0f} "
          f"{r['pct_profitable']:>5.1f}% ${y22:>+7,.0f} ${y20:>+7,.0f}")


def main():
    signals, breadth, breadth_delta, lqd_5d = load_data()
    print(f"Loaded {len(signals):,} signals\n")

    results = {}

    # ── BASELINE ──
    def baseline(sig, b, bd, lqd):
        vix = sig[10]
        if vix and 20 <= vix < 24: return False, 0
        if vix and vix >= 30: return False, 0
        if b is not None and b < 35: return False, 0
        if bd is not None and bd < -15: return False, 0
        if bd is not None and bd <= 0: return False, 0
        ok, _ = base_filters(sig, b, bd)
        return ok, 1.0

    results['BASELINE'] = sim(signals, breadth, breadth_delta, lqd_5d, baseline)

    # ── D: Crisis Sector only ──
    def crisis_sector(sig, b, bd, lqd):
        vix, sector = sig[10], sig[2]
        if vix and 20 <= vix < 24: return False, 0
        if vix and vix >= 30:
            if sector in CRISIS_BLOCK: return False, 0
            if sector in CRISIS_GOOD: pass  # allow
            else: return False, 0
        if b is not None and b < 35: return False, 0
        if bd is not None and bd < -15: return False, 0
        if bd is not None and bd <= 0: return False, 0
        ok, _ = base_filters(sig, b, bd)
        size = 0.5 if (vix and vix >= 30 and sector in CRISIS_GOOD) else 1.0
        return ok, size

    results['D_CRISIS_SECTOR'] = sim(signals, breadth, breadth_delta, lqd_5d, crisis_sector)

    # ── E: LQD filter — test multiple thresholds ──
    for thresh in [-0.3, -0.5, -0.7, -1.0, -1.5]:
        def make_lqd_fn(t):
            def fn(sig, b, bd, lqd):
                vix = sig[10]
                if vix and 20 <= vix < 24: return False, 0
                if vix and vix >= 30: return False, 0
                if lqd is not None and lqd < t: return False, 0
                if b is not None and b < 35: return False, 0
                if bd is not None and bd < -15: return False, 0
                if bd is not None and bd <= 0: return False, 0
                ok, _ = base_filters(sig, b, bd)
                return ok, 1.0
            return fn
        results[f'E_LQD<{thresh}'] = sim(signals, breadth, breadth_delta, lqd_5d, make_lqd_fn(thresh))

    # ── D+E Combined ──
    for thresh in [-0.3, -0.5, -0.7, -1.0]:
        def make_de_fn(t):
            def fn(sig, b, bd, lqd):
                vix, sector = sig[10], sig[2]
                if vix and 20 <= vix < 24: return False, 0
                if vix and vix >= 30:
                    if sector in CRISIS_BLOCK: return False, 0
                    if sector in CRISIS_GOOD: pass
                    else: return False, 0
                if lqd is not None and lqd < t: return False, 0
                if b is not None and b < 35: return False, 0
                if bd is not None and bd < -15: return False, 0
                if bd is not None and bd <= 0: return False, 0
                ok, _ = base_filters(sig, b, bd)
                size = 0.5 if (vix and vix >= 30 and sector in CRISIS_GOOD) else 1.0
                return ok, size
            return fn
        results[f'D+E_LQD<{t}' if False else f'D+E_LQD<{thresh}'] = sim(
            signals, breadth, breadth_delta, lqd_5d, make_de_fn(thresh))

    # ── E_soft: LQD reduce size instead of block ──
    for thresh in [-0.3, -0.5]:
        def make_lqd_soft(t):
            def fn(sig, b, bd, lqd):
                vix = sig[10]
                if vix and 20 <= vix < 24: return False, 0
                if vix and vix >= 30: return False, 0
                size = 1.0
                if lqd is not None and lqd < t: size *= 0.5
                if b is not None and b < 35: return False, 0
                if bd is not None and bd < -15: return False, 0
                if bd is not None and bd <= 0: return False, 0
                ok, _ = base_filters(sig, b, bd)
                return ok, size
            return fn
        results[f'E_SOFT_LQD<{thresh}'] = sim(signals, breadth, breadth_delta, lqd_5d, make_lqd_soft(thresh))

    # ── D+E_soft: Both with soft LQD ──
    def de_soft(sig, b, bd, lqd):
        vix, sector = sig[10], sig[2]
        if vix and 20 <= vix < 24: return False, 0
        if vix and vix >= 30:
            if sector in CRISIS_BLOCK: return False, 0
            if sector in CRISIS_GOOD: pass
            else: return False, 0
        size = 1.0
        if lqd is not None and lqd < -0.5: size *= 0.5
        if vix and vix >= 30 and sector in CRISIS_GOOD: size *= 0.5
        if b is not None and b < 35: return False, 0
        if bd is not None and bd < -15: return False, 0
        if bd is not None and bd <= 0: return False, 0
        ok, _ = base_filters(sig, b, bd)
        return ok, size
    results['D+E_SOFT'] = sim(signals, breadth, breadth_delta, lqd_5d, de_soft)

    # ── Additional: D+E + open VIX SKIP for good sectors ──
    def de_vix_smart(sig, b, bd, lqd):
        vix, sector = sig[10], sig[2]
        # Smart VIX: only block SKIP for bad sectors
        if vix and 20 <= vix < 24:
            if sector in CRISIS_BLOCK:
                return False, 0
            # Allow through for good sectors at half size
            elif sector in CRISIS_GOOD:
                pass
            else:
                return False, 0  # still block for neutral sectors
        if vix and vix >= 30:
            if sector in CRISIS_BLOCK: return False, 0
            if sector in CRISIS_GOOD: pass
            else: return False, 0
        if lqd is not None and lqd < -0.5: return False, 0
        if b is not None and b < 35: return False, 0
        if bd is not None and bd < -15: return False, 0
        if bd is not None and bd <= 0: return False, 0
        ok, _ = base_filters(sig, b, bd)
        size = 1.0
        if vix and vix >= 24 and sector in CRISIS_GOOD: size = 0.5
        elif vix and 20 <= vix < 24 and sector in CRISIS_GOOD: size = 0.75
        return ok, size
    results['D+E+VIX_SMART'] = sim(signals, breadth, breadth_delta, lqd_5d, de_vix_smart)

    # Print comparison
    print(f"{'Strategy':<32} {'PnL':>9} {'$/mo':>14} {'Trades':>7} {'WR%':>6} "
          f"{'Sharpe':>6} {'MaxDD':>8} {'%Prof':>6} {'2022':>8} {'2020':>8}")
    print("─" * 120)

    base = results['BASELINE']
    for name in ['BASELINE', 'D_CRISIS_SECTOR',
                 'E_LQD<-0.3', 'E_LQD<-0.5', 'E_LQD<-0.7', 'E_LQD<-1.0', 'E_LQD<-1.5',
                 'E_SOFT_LQD<-0.3', 'E_SOFT_LQD<-0.5',
                 'D+E_LQD<-0.3', 'D+E_LQD<-0.5', 'D+E_LQD<-0.7', 'D+E_LQD<-1.0',
                 'D+E_SOFT', 'D+E+VIX_SMART']:
        if name in results:
            print_row(name, results[name], None if name == 'BASELINE' else base)

    # Best strategies
    print(f"\n{'=' * 70}")
    print("  TOP 3 STRATEGIES (by $/mo improvement):")
    ranked = sorted(
        [(n, r) for n, r in results.items() if n != 'BASELINE'],
        key=lambda x: x[1]['avg_mo'], reverse=True
    )
    for i, (name, r) in enumerate(ranked[:5]):
        d_mo = r['avg_mo'] - base['avg_mo']
        y22 = r['yearly_pnl'].get('2022', 0)
        y20 = r['yearly_pnl'].get('2020', 0)
        print(f"  #{i+1} {name:<30} Δ$/mo={d_mo:>+.0f} PnL=${r['pnl']:>+,.0f} "
              f"Sharpe={r['sharpe']:.2f} 2022=${y22:>+,.0f} 2020=${y20:>+,.0f}")

    # Yearly detail for top 3
    for name, r in ranked[:3]:
        print(f"\n  {name} — Yearly Breakdown:")
        for y in sorted(r['yearly_pnl'].keys()):
            pnl = r['yearly_pnl'][y]
            t = r['yearly_trades'][y]
            w = r['yearly_wins'].get(y, 0)
            wr = w/t*100 if t else 0
            mo_count = max(1, len([m for m in range(1,13) if f"{y}-{m:02d}" in
                [f"{y}-{m:02d}" for m in range(1,13)]]))
            # approximate months
            ppm = pnl / max(1, t / 20)  # ~20 trades/mo
            print(f"    {y}: PnL=${pnl:>+,.0f}, {t} trades, WR={wr:.1f}%")


if __name__ == '__main__':
    main()
