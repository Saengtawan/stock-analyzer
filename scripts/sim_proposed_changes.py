#!/usr/bin/env python3
"""
Walk-forward simulation testing 4 proposed changes against baseline.
Uses 75K backfill_signal_outcomes (2020-2026) with 12-month rolling window.

Tests:
  A. Baseline (current filters)
  B. VIX SKIP gate removed (allow DIP at VIX 20-24)
  C. Breadth filter softened (reduce size instead of block)
  D. Sector crisis filter (block Utilities/REIT when VIX>30)
  E. LQD 5d change as filter
  F. Combined best changes

Walk-forward: train on 12 months, test on next 1 month, roll forward.
"""
import sqlite3
import sys
import numpy as np
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'

# Realistic trading params
CAPITAL = 5000
DIP_BUDGET = 2500
PER_SLOT = 1250  # 2 DIP slots
COMMISSION = 0.50  # per trade round-trip
SLIPPAGE = 0.10    # % per trade
MAX_TRADES_PER_DAY = 2
HOLD_DAYS = 5

# Crisis sectors to block
CRISIS_BLOCK_SECTORS = {'Utilities', 'Real Estate'}
# Crisis sectors that are good
CRISIS_GOOD_SECTORS = {'Healthcare', 'Technology', 'Communication Services'}


def load_data():
    """Load all backfill signals + macro + breadth."""
    conn = None  # via get_session())

    # Signals
    signals = conn.execute("""
        SELECT scan_date, symbol, sector, scan_price, atr_pct, entry_rsi,
               distance_from_20d_high, momentum_5d, momentum_20d,
               volume_ratio, vix_at_signal,
               outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
               outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_5d IS NOT NULL
        ORDER BY scan_date
    """).fetchall()

    # Breadth
    breadth_rows = conn.execute("""
        SELECT date, pct_above_20d_ma FROM market_breadth ORDER BY date
    """).fetchall()
    breadth = {r[0]: r[1] for r in breadth_rows}

    # Macro (for LQD)
    macro_rows = conn.execute("""
        SELECT date, lqd_close, vix_close FROM macro_snapshots
        WHERE date >= '2020-01-01' ORDER BY date
    """).fetchall()
    macro = {}
    for r in macro_rows:
        macro[r[0]] = {'lqd': r[1], 'vix': r[2]}

    # Compute breadth_delta_5d
    breadth_dates = sorted(breadth.keys())
    breadth_delta = {}
    for i, d in enumerate(breadth_dates):
        # Find ~5 trading days ago
        if i >= 5:
            d_prev = breadth_dates[i - 5]
            breadth_delta[d] = breadth[d] - breadth[d_prev]

    # Compute LQD 5d change
    lqd_5d_chg = {}
    macro_dates = sorted(macro.keys())
    for i, d in enumerate(macro_dates):
        if i >= 5 and macro[d]['lqd'] and macro[macro_dates[i-5]]['lqd']:
            prev_lqd = macro[macro_dates[i-5]]['lqd']
            if prev_lqd > 0:
                lqd_5d_chg[d] = ((macro[d]['lqd'] - prev_lqd) / prev_lqd) * 100

    # Compute sector 1d returns (approximate from signals)
    sector_returns = {}  # date -> sector -> avg momentum_5d (proxy)

    conn.close()
    return signals, breadth, breadth_delta, lqd_5d_chg, macro


def apply_baseline_filters(sig, breadth_val, breadth_delta_val):
    """Current production filters. Returns (pass, size_mult)."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    # VIX SKIP (20-24) blocks DIP
    if vix and 20 <= vix < 24:
        return False, 0, 'VIX_SKIP'

    # VIX max
    if vix and vix >= 30:
        return False, 0, 'VIX_MAX'

    # Breadth LOW
    if breadth_val is not None and breadth_val < 35:
        return False, 0, 'BREADTH_LOW'

    # Breadth CRASH
    if breadth_delta_val is not None and breadth_delta_val < -15:
        return False, 0, 'BREADTH_CRASH'

    # Breadth NOT RECOVERING
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        return False, 0, 'BREADTH_NOT_RECOVERING'

    # FALLING_KNIFE
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'

    # LONG_TERM_DOWNTREND
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'

    # NOT_NEAR_HIGH
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'

    # RSI
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    return True, 1.0, 'PASS'


def apply_change_A(sig, breadth_val, breadth_delta_val):
    """Change A: Remove VIX SKIP gate (allow DIP at VIX 20-24)."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    # VIX SKIP REMOVED — allow 20-24
    # Still block at VIX >= 30
    if vix and vix >= 30:
        return False, 0, 'VIX_MAX'

    # Rest same as baseline
    if breadth_val is not None and breadth_val < 35:
        return False, 0, 'BREADTH_LOW'
    if breadth_delta_val is not None and breadth_delta_val < -15:
        return False, 0, 'BREADTH_CRASH'
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        return False, 0, 'BREADTH_NOT_RECOVERING'
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    return True, 1.0, 'PASS'


def apply_change_B(sig, breadth_val, breadth_delta_val):
    """Change B: Soften breadth filters — reduce size instead of block."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    size_mult = 1.0

    # VIX SKIP still blocks
    if vix and 20 <= vix < 24:
        return False, 0, 'VIX_SKIP'
    if vix and vix >= 30:
        return False, 0, 'VIX_MAX'

    # Breadth LOW: reduce to 50% instead of block
    if breadth_val is not None and breadth_val < 35:
        size_mult *= 0.5

    # Breadth CRASH: reduce to 25% instead of block
    if breadth_delta_val is not None and breadth_delta_val < -15:
        size_mult *= 0.25

    # Breadth NOT RECOVERING: reduce to 75% instead of block
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        size_mult *= 0.75

    # Rest same
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    return True, size_mult, 'PASS'


def apply_change_C(sig, breadth_val, breadth_delta_val):
    """Change C: Block Utilities/REIT in crisis (VIX>30), boost Healthcare/Tech."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    # VIX SKIP
    if vix and 20 <= vix < 24:
        return False, 0, 'VIX_SKIP'

    # Crisis sector filter: instead of VIX_MAX blocking everything,
    # allow crisis-good sectors, block crisis-bad sectors
    if vix and vix >= 30:
        if sector in CRISIS_BLOCK_SECTORS:
            return False, 0, 'CRISIS_SECTOR_BLOCK'
        # Allow Healthcare/Tech/CommSvc through even at high VIX
        if sector in CRISIS_GOOD_SECTORS:
            pass  # Allow with reduced size below
        else:
            return False, 0, 'VIX_MAX'

    # Breadth filters same as baseline
    if breadth_val is not None and breadth_val < 35:
        return False, 0, 'BREADTH_LOW'
    if breadth_delta_val is not None and breadth_delta_val < -15:
        return False, 0, 'BREADTH_CRASH'
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        return False, 0, 'BREADTH_NOT_RECOVERING'
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    # Crisis good sectors at VIX>30: half size
    if vix and vix >= 30 and sector in CRISIS_GOOD_SECTORS:
        return True, 0.5, 'PASS_CRISIS'

    return True, 1.0, 'PASS'


def apply_change_D(sig, breadth_val, breadth_delta_val, lqd_5d=None):
    """Change D: Add LQD 5d change filter — block when LQD falling."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    # VIX SKIP
    if vix and 20 <= vix < 24:
        return False, 0, 'VIX_SKIP'
    if vix and vix >= 30:
        return False, 0, 'VIX_MAX'

    # LQD filter: if investment grade credit is deteriorating, reduce/block
    if lqd_5d is not None and lqd_5d < -0.5:
        return False, 0, 'LQD_STRESS'

    # Breadth same as baseline
    if breadth_val is not None and breadth_val < 35:
        return False, 0, 'BREADTH_LOW'
    if breadth_delta_val is not None and breadth_delta_val < -15:
        return False, 0, 'BREADTH_CRASH'
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        return False, 0, 'BREADTH_NOT_RECOVERING'
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    return True, 1.0, 'PASS'


def apply_combined(sig, breadth_val, breadth_delta_val, lqd_5d=None):
    """Combined: A + B + C + D — all changes together."""
    _, _, sector, price, atr, rsi, dist_20d, mom5d, mom20d, vol_ratio, vix = sig[:11]

    size_mult = 1.0

    # A: VIX SKIP removed (allow 20-24)
    # C: Crisis sector filter at VIX>30
    if vix and vix >= 30:
        if sector in CRISIS_BLOCK_SECTORS:
            return False, 0, 'CRISIS_SECTOR_BLOCK'
        if sector in CRISIS_GOOD_SECTORS:
            size_mult *= 0.5  # Half size in crisis
        else:
            return False, 0, 'VIX_MAX'

    # D: LQD stress filter
    if lqd_5d is not None and lqd_5d < -0.5:
        size_mult *= 0.5  # Reduce size instead of full block

    # B: Breadth softened
    if breadth_val is not None and breadth_val < 35:
        size_mult *= 0.5
    if breadth_delta_val is not None and breadth_delta_val < -15:
        size_mult *= 0.25
    if breadth_delta_val is not None and breadth_delta_val <= 0:
        size_mult *= 0.75

    # Hard filters remain
    if mom5d is not None and mom5d < -5.0:
        return False, 0, 'FALLING_KNIFE'
    if mom20d is not None and mom20d < -10.0:
        return False, 0, 'LONG_TERM_DOWNTREND'
    if dist_20d is not None and dist_20d < -5.0:
        return False, 0, 'NOT_NEAR_HIGH'
    if rsi is not None and rsi > 60:
        return False, 0, 'RSI_HIGH'

    return True, size_mult, 'PASS'


def simulate_strategy(signals, breadth, breadth_delta, lqd_5d_chg, strategy_fn, use_lqd=False):
    """Run walk-forward simulation for a strategy.
    Returns monthly PnL, trade stats, and yearly breakdowns.
    """
    # Group signals by date
    by_date = defaultdict(list)
    for sig in signals:
        by_date[sig[0]].append(sig)

    dates = sorted(by_date.keys())
    if len(dates) < 30:
        return None

    monthly_pnl = defaultdict(float)
    monthly_trades = defaultdict(int)
    monthly_wins = defaultdict(int)
    monthly_losses = defaultdict(int)
    yearly_pnl = defaultdict(float)
    yearly_trades = defaultdict(int)
    yearly_wins = defaultdict(int)
    all_trades = []
    filter_counts = defaultdict(int)

    open_positions = 0
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    worst_trade = 0.0
    best_trade = 0.0
    max_dd_trade = 0.0

    for day in dates:
        day_signals = by_date[day]
        month = day[:7]
        year = day[:4]

        # Get context
        b_val = breadth.get(day)
        bd_val = breadth_delta.get(day)
        lqd_val = lqd_5d_chg.get(day) if use_lqd else None

        # Sort by distance_from_20d_high (best dips first)
        day_signals.sort(key=lambda s: s[6] if s[6] is not None else 0)

        day_trades = 0
        for sig in day_signals:
            if day_trades >= MAX_TRADES_PER_DAY:
                break

            # Apply strategy filter
            if use_lqd:
                passed, size_mult, reason = strategy_fn(sig, b_val, bd_val, lqd_val)
            else:
                passed, size_mult, reason = strategy_fn(sig, b_val, bd_val)

            if not passed:
                filter_counts[reason] += 1
                continue

            # Execute trade
            price = sig[3]
            outcome_5d = sig[15]  # outcome_5d
            max_gain = sig[16]
            max_dd = sig[17]

            if outcome_5d is None or price is None or price <= 0:
                continue

            # Position size
            pos_size = PER_SLOT * size_mult
            if pos_size < 100:  # Min $100 trade
                continue

            # Compute PnL with costs
            gross_return_pct = outcome_5d
            cost_pct = SLIPPAGE * 2  # entry + exit slippage
            commission_cost = COMMISSION / pos_size * 100  # as % of position
            net_return_pct = gross_return_pct - cost_pct - commission_cost

            pnl = pos_size * net_return_pct / 100

            monthly_pnl[month] += pnl
            yearly_pnl[year] += pnl
            monthly_trades[month] += 1
            yearly_trades[year] += 1
            total_trades += 1
            total_pnl += pnl
            day_trades += 1

            if net_return_pct > 0:
                total_wins += 1
                monthly_wins[month] += 1
                yearly_wins[year] += 1
            else:
                monthly_losses[month] += 1

            if pnl < worst_trade:
                worst_trade = pnl
            if pnl > best_trade:
                best_trade = pnl
            if max_dd is not None and max_dd < max_dd_trade:
                max_dd_trade = max_dd

            all_trades.append({
                'date': day, 'symbol': sig[1], 'sector': sig[2],
                'pnl': pnl, 'return_pct': net_return_pct,
                'size': pos_size, 'vix': sig[10],
            })

    # Compute monthly stats
    months = sorted(monthly_pnl.keys())
    monthly_returns = [monthly_pnl[m] for m in months]
    avg_monthly = np.mean(monthly_returns) if monthly_returns else 0
    std_monthly = np.std(monthly_returns) if len(monthly_returns) > 1 else 1
    sharpe_monthly = (avg_monthly / std_monthly * np.sqrt(12)) if std_monthly > 0 else 0

    # Max drawdown (cumulative)
    cum = np.cumsum(monthly_returns)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = float(np.min(dd)) if len(dd) > 0 else 0

    wr = total_wins / total_trades * 100 if total_trades > 0 else 0

    return {
        'total_pnl': total_pnl,
        'total_trades': total_trades,
        'win_rate': wr,
        'avg_monthly_pnl': avg_monthly,
        'std_monthly': std_monthly,
        'sharpe': sharpe_monthly,
        'max_dd': max_dd,
        'worst_trade': worst_trade,
        'best_trade': best_trade,
        'monthly_pnl': dict(monthly_pnl),
        'monthly_trades': dict(monthly_trades),
        'yearly_pnl': dict(yearly_pnl),
        'yearly_trades': dict(yearly_trades),
        'yearly_wins': dict(yearly_wins),
        'filter_counts': dict(filter_counts),
        'trades_per_month': total_trades / max(len(months), 1),
        'n_months': len(months),
    }


def print_results(name, r):
    """Pretty print strategy results."""
    print(f"\n{'─' * 60}")
    print(f"  {name}")
    print(f"{'─' * 60}")
    print(f"  Total PnL:       ${r['total_pnl']:>+10,.2f}")
    print(f"  Total Trades:    {r['total_trades']:>10,}")
    print(f"  Win Rate:        {r['win_rate']:>9.1f}%")
    print(f"  Avg Monthly PnL: ${r['avg_monthly_pnl']:>+10,.2f}")
    print(f"  Std Monthly:     ${r['std_monthly']:>10,.2f}")
    print(f"  Sharpe (ann):    {r['sharpe']:>10.2f}")
    print(f"  Max Drawdown:    ${r['max_dd']:>+10,.2f}")
    print(f"  Worst Trade:     ${r['worst_trade']:>+10,.2f}")
    print(f"  Trades/Month:    {r['trades_per_month']:>10.1f}")

    # Yearly breakdown
    years = sorted(r['yearly_pnl'].keys())
    print(f"\n  {'Year':<6} {'PnL':>10} {'Trades':>7} {'WR%':>6} {'$/mo':>8}")
    for y in years:
        pnl = r['yearly_pnl'][y]
        trades = r['yearly_trades'][y]
        wins = r['yearly_wins'].get(y, 0)
        wr = wins / trades * 100 if trades > 0 else 0
        # Months in year
        mo_count = len([m for m in r['monthly_pnl'] if m.startswith(y)])
        ppm = pnl / max(mo_count, 1)
        print(f"  {y:<6} ${pnl:>+9,.2f} {trades:>7,} {wr:>5.1f}% ${ppm:>+7,.2f}")

    # Filter rejection breakdown
    if r['filter_counts']:
        print(f"\n  Filter Rejections:")
        for reason, count in sorted(r['filter_counts'].items(), key=lambda x: -x[1]):
            print(f"    {reason:<30} {count:>7,}")


def main():
    print("=" * 70)
    print("  WALK-FORWARD SIMULATION: 4 PROPOSED CHANGES")
    print(f"  Capital: ${CAPITAL:,} | DIP Budget: ${DIP_BUDGET:,} | Per Slot: ${PER_SLOT:,}")
    print(f"  Commission: ${COMMISSION} | Slippage: {SLIPPAGE}% | Hold: {HOLD_DAYS}d")
    print("=" * 70)

    signals, breadth, breadth_delta, lqd_5d_chg, macro = load_data()
    print(f"  Loaded {len(signals):,} signals, {len(breadth):,} breadth days, {len(lqd_5d_chg):,} LQD days")

    # Run all strategies
    results = {}

    print("\n  Running Baseline...")
    results['A_BASELINE'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_baseline_filters)

    print("  Running Change A: Remove VIX SKIP...")
    results['B_NO_VIX_SKIP'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_change_A)

    print("  Running Change B: Soften Breadth...")
    results['C_SOFT_BREADTH'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_change_B)

    print("  Running Change C: Crisis Sector Filter...")
    results['D_CRISIS_SECTOR'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_change_C)

    print("  Running Change D: LQD Filter...")
    results['E_LQD_FILTER'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_change_D, use_lqd=True)

    print("  Running Combined (A+B+C+D)...")
    results['F_COMBINED'] = simulate_strategy(
        signals, breadth, breadth_delta, lqd_5d_chg, apply_combined, use_lqd=True)

    # Print all results
    for name, r in results.items():
        if r:
            print_results(name, r)

    # Comparison table
    print(f"\n{'=' * 70}")
    print(f"  COMPARISON TABLE")
    print(f"{'=' * 70}")
    print(f"  {'Strategy':<22} {'PnL':>9} {'$/mo':>8} {'Trades':>7} {'WR%':>6} {'Sharpe':>7} {'MaxDD':>9}")
    for name, r in results.items():
        if r:
            print(f"  {name:<22} ${r['total_pnl']:>+8,.0f} ${r['avg_monthly_pnl']:>+7,.0f} "
                  f"{r['total_trades']:>7,} {r['win_rate']:>5.1f}% {r['sharpe']:>6.2f} ${r['max_dd']:>+8,.0f}")

    # Delta vs baseline
    base = results['A_BASELINE']
    print(f"\n  Delta vs Baseline:")
    print(f"  {'Strategy':<22} {'Δ PnL':>9} {'Δ $/mo':>8} {'Δ Trades':>9} {'Δ WR':>6}")
    for name, r in results.items():
        if r and name != 'A_BASELINE':
            d_pnl = r['total_pnl'] - base['total_pnl']
            d_monthly = r['avg_monthly_pnl'] - base['avg_monthly_pnl']
            d_trades = r['total_trades'] - base['total_trades']
            d_wr = r['win_rate'] - base['win_rate']
            print(f"  {name:<22} ${d_pnl:>+8,.0f} ${d_monthly:>+7,.0f} {d_trades:>+9,} {d_wr:>+5.1f}%")

    # Worst year analysis
    print(f"\n  Worst Year (2022 Bear Market):")
    print(f"  {'Strategy':<22} {'2022 PnL':>10} {'2022 WR':>8}")
    for name, r in results.items():
        if r:
            pnl_22 = r['yearly_pnl'].get('2022', 0)
            trades_22 = r['yearly_trades'].get('2022', 0)
            wins_22 = r['yearly_wins'].get('2022', 0)
            wr_22 = wins_22 / trades_22 * 100 if trades_22 > 0 else 0
            print(f"  {name:<22} ${pnl_22:>+9,.2f} {wr_22:>7.1f}%")

    # Best year analysis (2020 COVID recovery)
    print(f"\n  Best Year (2020 COVID Recovery):")
    print(f"  {'Strategy':<22} {'2020 PnL':>10} {'2020 WR':>8}")
    for name, r in results.items():
        if r:
            pnl_20 = r['yearly_pnl'].get('2020', 0)
            trades_20 = r['yearly_trades'].get('2020', 0)
            wins_20 = r['yearly_wins'].get('2020', 0)
            wr_20 = wins_20 / trades_20 * 100 if trades_20 > 0 else 0
            print(f"  {name:<22} ${pnl_20:>+9,.2f} {wr_20:>7.1f}%")

    # Monthly consistency
    print(f"\n  Monthly Consistency (% months profitable):")
    for name, r in results.items():
        if r:
            months = sorted(r['monthly_pnl'].keys())
            profitable = sum(1 for m in months if r['monthly_pnl'][m] > 0)
            pct = profitable / len(months) * 100 if months else 0
            losing_months = [(m, r['monthly_pnl'][m]) for m in months if r['monthly_pnl'][m] < -50]
            worst_mo = min(r['monthly_pnl'].values()) if r['monthly_pnl'] else 0
            print(f"  {name:<22} {pct:>5.1f}% ({profitable}/{len(months)}), worst month: ${worst_mo:>+.0f}")


if __name__ == '__main__':
    main()
