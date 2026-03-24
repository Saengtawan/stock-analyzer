#!/usr/bin/env python3
"""
Validate D+E+VIX_SMART strategy:
1. Bootstrap confidence intervals
2. Monthly breakdown comparison
3. Regime-level analysis (does it work in ALL regimes?)
4. Per-sector breakdown
5. Sensitivity to thresholds (robustness)
6. Trade count impact
"""
import sqlite3
import numpy as np
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

PER_SLOT = 1250
COMMISSION = 0.50
SLIPPAGE = 0.10
MAX_TRADES_PER_DAY = 2

CRISIS_BLOCK = {'Utilities', 'Real Estate'}
CRISIS_GOOD = {'Healthcare', 'Technology', 'Communication Services'}


def load_data():
    conn = sqlite3.connect(str(DB_PATH))
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
    bd = sorted(breadth.keys())
    breadth_delta = {}
    for i, d in enumerate(bd):
        if i >= 5: breadth_delta[d] = breadth[d] - breadth[bd[i-5]]

    macro_rows = conn.execute("SELECT date, lqd_close FROM macro_snapshots WHERE date >= '2020-01-01' ORDER BY date").fetchall()
    macro = {r[0]: r[1] for r in macro_rows}
    md = sorted(macro.keys())
    lqd_5d = {}
    for i, d in enumerate(md):
        if i >= 5 and macro[d] and macro[md[i-5]]:
            prev = macro[md[i-5]]
            if prev > 0: lqd_5d[d] = ((macro[d] - prev) / prev) * 100

    conn.close()
    return signals, breadth, breadth_delta, lqd_5d


def base_filters(sig):
    _, _, _, _, _, rsi, dist_20d, mom5d, mom20d, _, _ = sig[:11]
    if mom5d is not None and mom5d < -5.0: return False
    if mom20d is not None and mom20d < -10.0: return False
    if dist_20d is not None and dist_20d < -5.0: return False
    if rsi is not None and rsi > 60: return False
    return True


def baseline_fn(sig, b, bd, lqd):
    vix = sig[10]
    if vix and 20 <= vix < 24: return False, 0
    if vix and vix >= 30: return False, 0
    if b is not None and b < 35: return False, 0
    if bd is not None and bd < -15: return False, 0
    if bd is not None and bd <= 0: return False, 0
    return base_filters(sig), 1.0


def winner_fn(sig, b, bd, lqd):
    """D+E+VIX_SMART"""
    vix, sector = sig[10], sig[2]
    # Smart VIX: allow good sectors through SKIP zone at reduced size
    if vix and 20 <= vix < 24:
        if sector in CRISIS_BLOCK: return False, 0
        if sector in CRISIS_GOOD: pass  # allow through
        else: return False, 0
    if vix and vix >= 30:
        if sector in CRISIS_BLOCK: return False, 0
        if sector in CRISIS_GOOD: pass
        else: return False, 0
    # LQD stress filter
    if lqd is not None and lqd < -0.5: return False, 0
    # Breadth
    if b is not None and b < 35: return False, 0
    if bd is not None and bd < -15: return False, 0
    if bd is not None and bd <= 0: return False, 0
    if not base_filters(sig): return False, 0
    size = 1.0
    if vix and vix >= 24 and sector in CRISIS_GOOD: size = 0.5
    elif vix and 20 <= vix < 24 and sector in CRISIS_GOOD: size = 0.75
    return True, size


def run_trades(signals, breadth, breadth_delta, lqd_5d, strategy_fn):
    """Returns list of individual trades with metadata."""
    by_date = defaultdict(list)
    for sig in signals:
        by_date[sig[0]].append(sig)

    trades = []
    for day in sorted(by_date.keys()):
        sigs = sorted(by_date[day], key=lambda s: s[6] if s[6] is not None else 0)
        b = breadth.get(day)
        bd = breadth_delta.get(day)
        lqd = lqd_5d.get(day)
        day_n = 0

        for sig in sigs:
            if day_n >= MAX_TRADES_PER_DAY: break
            passed, size = strategy_fn(sig, b, bd, lqd)
            if not passed: continue

            price = sig[3]
            outcome = sig[15]
            if outcome is None or not price or price <= 0: continue

            pos = PER_SLOT * size
            if pos < 100: continue

            cost = SLIPPAGE * 2 + COMMISSION / pos * 100
            net = outcome - cost
            pnl = pos * net / 100

            trades.append({
                'date': day, 'month': day[:7], 'year': day[:4],
                'symbol': sig[1], 'sector': sig[2],
                'vix': sig[10], 'breadth': b,
                'pnl': pnl, 'return_pct': net, 'size': pos,
                'outcome_5d': outcome,
                'lqd': lqd,
            })
            day_n += 1

    return trades


def main():
    signals, breadth, breadth_delta, lqd_5d = load_data()

    base_trades = run_trades(signals, breadth, breadth_delta, lqd_5d, baseline_fn)
    win_trades = run_trades(signals, breadth, breadth_delta, lqd_5d, winner_fn)

    print("=" * 70)
    print("  VALIDATION: D+E+VIX_SMART vs BASELINE")
    print("=" * 70)

    # ── 1. Bootstrap Confidence Intervals ──
    print("\n1. BOOTSTRAP CONFIDENCE INTERVALS (10,000 resamples)")
    np.random.seed(42)
    n_boot = 10000

    for name, trades in [('BASELINE', base_trades), ('D+E+VIX_SMART', win_trades)]:
        monthly = defaultdict(float)
        for t in trades:
            monthly[t['month']] += t['pnl']
        m_returns = list(monthly.values())

        boot_means = []
        for _ in range(n_boot):
            sample = np.random.choice(m_returns, size=len(m_returns), replace=True)
            boot_means.append(np.mean(sample))

        ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])
        mean = np.mean(m_returns)
        print(f"   {name:<22} mean=${mean:>+.0f}/mo  95% CI: [${ci_lo:>+.0f}, ${ci_hi:>+.0f}]")

    # Difference bootstrap
    base_monthly = defaultdict(float)
    win_monthly = defaultdict(float)
    for t in base_trades: base_monthly[t['month']] += t['pnl']
    for t in win_trades: win_monthly[t['month']] += t['pnl']

    all_months = sorted(set(base_monthly.keys()) | set(win_monthly.keys()))
    diffs = [win_monthly.get(m, 0) - base_monthly.get(m, 0) for m in all_months]

    boot_diffs = []
    for _ in range(n_boot):
        sample = np.random.choice(diffs, size=len(diffs), replace=True)
        boot_diffs.append(np.mean(sample))

    ci_lo, ci_hi = np.percentile(boot_diffs, [2.5, 97.5])
    pct_positive = sum(1 for d in boot_diffs if d > 0) / n_boot * 100
    print(f"   DIFFERENCE              mean=${np.mean(diffs):>+.0f}/mo  95% CI: [${ci_lo:>+.0f}, ${ci_hi:>+.0f}]")
    print(f"   P(improvement > 0):     {pct_positive:.1f}%")

    # ── 2. Monthly Comparison ──
    print(f"\n2. MONTHLY PNL COMPARISON")
    print(f"   {'Month':<10} {'Base':>8} {'Winner':>8} {'Delta':>8} {'Winner?':>8}")
    months_improved = 0
    for m in sorted(all_months):
        b_pnl = base_monthly.get(m, 0)
        w_pnl = win_monthly.get(m, 0)
        d = w_pnl - b_pnl
        better = "✓" if w_pnl > b_pnl else ""
        if w_pnl > b_pnl: months_improved += 1
        # Only show extreme months
        if abs(d) > 50 or m >= '2025-01':
            print(f"   {m:<10} ${b_pnl:>+7,.0f} ${w_pnl:>+7,.0f} ${d:>+7,.0f} {better:>8}")
    print(f"   Winner better in {months_improved}/{len(all_months)} months ({months_improved/len(all_months)*100:.0f}%)")

    # ── 3. VIX Regime Analysis ──
    print(f"\n3. VIX REGIME BREAKDOWN")
    for name, trades in [('BASELINE', base_trades), ('WINNER', win_trades)]:
        regime_stats = defaultdict(lambda: {'pnl': 0, 'n': 0, 'wins': 0})
        for t in trades:
            vix = t['vix'] or 0
            if vix < 20: r = 'NORMAL(<20)'
            elif vix < 24: r = 'SKIP(20-24)'
            elif vix < 30: r = 'HIGH(24-30)'
            elif vix < 38: r = 'ELEVATED(30-38)'
            else: r = 'EXTREME(38+)'
            regime_stats[r]['pnl'] += t['pnl']
            regime_stats[r]['n'] += 1
            if t['pnl'] > 0: regime_stats[r]['wins'] += 1

        print(f"\n   {name}:")
        print(f"   {'Regime':<18} {'N':>6} {'PnL':>9} {'WR%':>6} {'$/trade':>8}")
        for r in ['NORMAL(<20)', 'SKIP(20-24)', 'HIGH(24-30)', 'ELEVATED(30-38)', 'EXTREME(38+)']:
            s = regime_stats[r]
            if s['n'] > 0:
                wr = s['wins']/s['n']*100
                pt = s['pnl']/s['n']
                print(f"   {r:<18} {s['n']:>6} ${s['pnl']:>+8,.0f} {wr:>5.1f}% ${pt:>+7.2f}")

    # ── 4. Sector Breakdown (Winner only) ──
    print(f"\n4. SECTOR BREAKDOWN (D+E+VIX_SMART)")
    sector_stats = defaultdict(lambda: {'pnl': 0, 'n': 0, 'wins': 0})
    for t in win_trades:
        s = t['sector'] or 'Unknown'
        sector_stats[s]['pnl'] += t['pnl']
        sector_stats[s]['n'] += 1
        if t['pnl'] > 0: sector_stats[s]['wins'] += 1

    print(f"   {'Sector':<25} {'N':>5} {'PnL':>9} {'WR%':>6} {'$/trade':>8}")
    for s in sorted(sector_stats.keys(), key=lambda x: sector_stats[x]['pnl'], reverse=True):
        st = sector_stats[s]
        if st['n'] >= 10:
            wr = st['wins']/st['n']*100
            pt = st['pnl']/st['n']
            print(f"   {s:<25} {st['n']:>5} ${st['pnl']:>+8,.0f} {wr:>5.1f}% ${pt:>+7.2f}")

    # ── 5. Sensitivity: What if we change LQD threshold? ──
    print(f"\n5. LQD THRESHOLD SENSITIVITY")
    for thresh in [-0.2, -0.3, -0.4, -0.5, -0.6, -0.7, -0.8, -1.0]:
        def make_fn(t):
            def fn(sig, b, bd, lqd):
                vix, sector = sig[10], sig[2]
                if vix and 20 <= vix < 24:
                    if sector in CRISIS_BLOCK: return False, 0
                    if sector in CRISIS_GOOD: pass
                    else: return False, 0
                if vix and vix >= 30:
                    if sector in CRISIS_BLOCK: return False, 0
                    if sector in CRISIS_GOOD: pass
                    else: return False, 0
                if lqd is not None and lqd < t: return False, 0
                if b is not None and b < 35: return False, 0
                if bd is not None and bd < -15: return False, 0
                if bd is not None and bd <= 0: return False, 0
                if not base_filters(sig): return False, 0
                size = 1.0
                if vix and vix >= 24 and sector in CRISIS_GOOD: size = 0.5
                elif vix and 20 <= vix < 24 and sector in CRISIS_GOOD: size = 0.75
                return True, size
            return fn

        t_trades = run_trades(signals, breadth, breadth_delta, lqd_5d, make_fn(thresh))
        pnl = sum(t['pnl'] for t in t_trades)
        n = len(t_trades)
        wins = sum(1 for t in t_trades if t['pnl'] > 0)
        wr = wins/n*100 if n else 0
        monthly = defaultdict(float)
        for t in t_trades: monthly[t['month']] += t['pnl']
        avg_mo = np.mean(list(monthly.values())) if monthly else 0
        marker = " ◄ CURRENT" if thresh == -0.5 else ""
        print(f"   LQD < {thresh:>+.1f}: PnL=${pnl:>+,.0f}, {n} trades, WR={wr:.1f}%, $/mo=${avg_mo:>+,.0f}{marker}")

    # ── 6. What trades does Winner ADD vs Baseline? ──
    print(f"\n6. TRADES ADDED BY WINNER (not in Baseline)")
    base_set = set((t['date'], t['symbol']) for t in base_trades)
    added = [t for t in win_trades if (t['date'], t['symbol']) not in base_set]
    removed = [t for t in base_trades if (t['date'], t['symbol']) not in
               set((t['date'], t['symbol']) for t in win_trades)]

    if added:
        added_pnl = sum(t['pnl'] for t in added)
        added_wins = sum(1 for t in added if t['pnl'] > 0)
        added_wr = added_wins/len(added)*100

        # By VIX zone
        by_vix = defaultdict(list)
        for t in added:
            vix = t['vix'] or 0
            if vix < 20: by_vix['NORMAL'].append(t)
            elif vix < 24: by_vix['SKIP(20-24)'].append(t)
            elif vix < 30: by_vix['HIGH(24-30)'].append(t)
            else: by_vix['VIX30+'].append(t)

        print(f"   Added trades: {len(added)}, PnL=${added_pnl:>+,.0f}, WR={added_wr:.1f}%")
        for zone, trades_z in sorted(by_vix.items()):
            z_pnl = sum(t['pnl'] for t in trades_z)
            z_wr = sum(1 for t in trades_z if t['pnl']>0)/len(trades_z)*100
            print(f"     {zone:<15}: {len(trades_z)} trades, PnL=${z_pnl:>+,.0f}, WR={z_wr:.1f}%")

        # By sector (added trades)
        by_sect = defaultdict(list)
        for t in added:
            by_sect[t['sector']].append(t)
        print(f"   By sector:")
        for s in sorted(by_sect.keys(), key=lambda x: sum(t['pnl'] for t in by_sect[x]), reverse=True):
            ts = by_sect[s]
            if len(ts) >= 3:
                s_pnl = sum(t['pnl'] for t in ts)
                s_wr = sum(1 for t in ts if t['pnl']>0)/len(ts)*100
                print(f"     {s:<25}: {len(ts)} trades, PnL=${s_pnl:>+,.0f}, WR={s_wr:.1f}%")

    if removed:
        removed_pnl = sum(t['pnl'] for t in removed)
        removed_wr = sum(1 for t in removed if t['pnl']>0)/len(removed)*100
        print(f"\n   Removed trades (LQD filter): {len(removed)}, PnL=${removed_pnl:>+,.0f}, WR={removed_wr:.1f}%")

    # ── 7. Summary verdict ──
    base_pnl = sum(t['pnl'] for t in base_trades)
    win_pnl = sum(t['pnl'] for t in win_trades)
    print(f"\n{'=' * 70}")
    print(f"  VERDICT")
    print(f"{'=' * 70}")
    print(f"  Baseline: ${base_pnl:>+,.0f} ({len(base_trades)} trades)")
    print(f"  Winner:   ${win_pnl:>+,.0f} ({len(win_trades)} trades)")
    print(f"  Delta:    ${win_pnl-base_pnl:>+,.0f} ({len(win_trades)-len(base_trades):>+d} trades)")


if __name__ == '__main__':
    main()
