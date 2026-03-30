#!/usr/bin/env python3
"""
Backtest Sanity Check — automated validation layer.

Run BEFORE reporting any backtest results. Catches:
- Tautology (filter = win condition)
- Date clustering (>50% from few dates)
- Year concentration (single year dominates)
- Walk-forward instability
- Suspicious PF (>10 = investigate)
- Insufficient N

Usage:
    from scripts.backtest_sanity_check import sanity_check, SanityResult

    result = sanity_check(
        trades=trades_list,  # list of dicts with: date, symbol, entry, exit, win
        filter_description="gap down + close > open",
        win_description="close > open",
    )

    if not result.passed:
        print(f"BLOCKED: {result.failures}")
    else:
        print(f"PASSED: WR={result.wr:.1f}%, PF={result.pf:.2f}")
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from collections import Counter
import math


@dataclass
class SanityResult:
    passed: bool
    wr: float
    pf: float
    n: int
    checks: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, str] = field(default_factory=dict)


def sanity_check(
    trades: List[dict],
    filter_description: str = "",
    win_description: str = "",
    min_n: int = 100,
    min_years: int = 3,
    max_single_day_pct: float = 10.0,
    max_single_year_pct: float = 50.0,
    max_pf: float = 10.0,
    max_walk_forward_gap: float = 15.0,
) -> SanityResult:
    """
    Run all sanity checks on backtest results.

    trades: list of dicts with keys:
        - date: str (YYYY-MM-DD)
        - symbol: str
        - entry: float (entry price)
        - exit: float (exit price)
        - win: bool (exit > entry)

    Returns SanityResult with passed/failed status.
    """
    result = SanityResult(passed=True, wr=0, pf=0, n=len(trades))

    if not trades:
        result.passed = False
        result.failures.append("NO_TRADES: 0 trades")
        return result

    # Basic stats
    n = len(trades)
    wins = sum(1 for t in trades if t.get('win', False))
    losses = n - wins
    wr = wins / n * 100

    win_sum = sum(t['exit'] / t['entry'] - 1 for t in trades if t.get('win') and t['entry'] > 0)
    loss_sum = sum(abs(t['exit'] / t['entry'] - 1) for t in trades if not t.get('win') and t['entry'] > 0)
    pf = win_sum / loss_sum if loss_sum > 0 else float('inf')

    result.wr = wr
    result.pf = pf
    result.n = n

    # ── CHECK 1: Tautology ──
    filter_norm = filter_description.lower().strip()
    win_norm = win_description.lower().strip()
    is_tautology = False

    if filter_norm and win_norm:
        # Check if filter contains win condition
        if win_norm in filter_norm or filter_norm in win_norm:
            is_tautology = True
        # Common tautology patterns
        tautology_pairs = [
            ("close > open", "close > open"),
            ("green bar", "close > open"),
            ("close > open", "green"),
        ]
        for f, w in tautology_pairs:
            if f in filter_norm and w in win_norm:
                is_tautology = True
            if w in filter_norm and f in win_norm:
                is_tautology = True

    # Also detect by WR = 100%
    if wr >= 99.5 and n >= 10:
        is_tautology = True

    result.checks['no_tautology'] = not is_tautology
    if is_tautology:
        result.passed = False
        result.failures.append(
            f"TAUTOLOGY: filter='{filter_description}' overlaps with win='{win_description}'. "
            f"WR={wr:.1f}% (suspiciously high)"
        )

    # ── CHECK 2: N sufficient ──
    result.checks['n_sufficient'] = n >= min_n
    if n < min_n:
        result.passed = False
        result.failures.append(f"N_LOW: {n} < {min_n} minimum")

    # ── CHECK 3: Date clustering ──
    date_counts = Counter(t['date'] for t in trades)
    if date_counts:
        max_date, max_count = date_counts.most_common(1)[0]
        max_date_pct = max_count / n * 100
        top3_pct = sum(c for _, c in date_counts.most_common(3)) / n * 100

        result.checks['date_not_clustered'] = max_date_pct <= max_single_day_pct
        result.details['worst_date'] = f"{max_date}: {max_count} trades ({max_date_pct:.1f}%)"
        result.details['top3_dates_pct'] = f"{top3_pct:.1f}%"

        if max_date_pct > max_single_day_pct:
            result.passed = False
            result.failures.append(
                f"DATE_CLUSTER: {max_date} has {max_count}/{n} trades ({max_date_pct:.1f}% > {max_single_day_pct}%)"
            )
        if top3_pct > 50:
            result.warnings.append(f"TOP3_DATES: {top3_pct:.1f}% of trades from 3 dates")

    # ── CHECK 4: Year spread ──
    year_counts = Counter(t['date'][:4] for t in trades)
    years_with_enough = sum(1 for y, c in year_counts.items() if c >= 10)

    result.checks['year_spread'] = years_with_enough >= min_years
    result.details['years'] = str(dict(year_counts.most_common()))

    if years_with_enough < min_years:
        result.passed = False
        result.failures.append(
            f"YEAR_SPREAD: only {years_with_enough} years with N≥10 (need {min_years}). "
            f"Distribution: {dict(year_counts)}"
        )

    # Check single year dominance
    if year_counts:
        max_year, max_year_n = year_counts.most_common(1)[0]
        max_year_pct = max_year_n / n * 100
        result.checks['no_year_dominance'] = max_year_pct <= max_single_year_pct

        if max_year_pct > max_single_year_pct:
            result.warnings.append(
                f"YEAR_DOMINANCE: {max_year} has {max_year_pct:.1f}% of trades"
            )

    # ── CHECK 5: Walk-forward stability ──
    sorted_trades = sorted(trades, key=lambda t: t['date'])
    mid = len(sorted_trades) // 2
    first_half = sorted_trades[:mid]
    second_half = sorted_trades[mid:]

    if len(first_half) >= 20 and len(second_half) >= 20:
        wr_first = sum(1 for t in first_half if t.get('win')) / len(first_half) * 100
        wr_second = sum(1 for t in second_half if t.get('win')) / len(second_half) * 100
        gap = abs(wr_first - wr_second)

        result.checks['walk_forward_stable'] = gap <= max_walk_forward_gap
        result.details['walk_forward'] = f"H1={wr_first:.1f}% H2={wr_second:.1f}% gap={gap:.1f}%"

        if gap > max_walk_forward_gap:
            result.warnings.append(
                f"WALK_FORWARD: H1 WR={wr_first:.1f}% vs H2 WR={wr_second:.1f}% (gap={gap:.1f}% > {max_walk_forward_gap}%)"
            )
    else:
        result.checks['walk_forward_stable'] = False
        result.warnings.append("WALK_FORWARD: insufficient data for split")

    # ── CHECK 6: PF not suspicious ──
    result.checks['pf_not_suspicious'] = pf <= max_pf
    if pf > max_pf:
        result.passed = False
        result.failures.append(
            f"PF_SUSPICIOUS: PF={pf:.2f} > {max_pf} — investigate for leakage"
        )

    # ── CHECK 7: Per-year WR consistency ──
    year_wr = {}
    for year, count in year_counts.items():
        year_wins = sum(1 for t in trades if t['date'][:4] == year and t.get('win'))
        year_wr[year] = year_wins / count * 100 if count > 0 else 0

    result.details['year_wr'] = str({y: f"{w:.1f}%" for y, w in sorted(year_wr.items())})

    # Check if any year has WR < 40% with N >= 10
    bad_years = {y: w for y, w in year_wr.items() if w < 40 and year_counts[y] >= 10}
    if bad_years:
        result.warnings.append(f"BAD_YEAR: {bad_years} — WR < 40%")

    return result


def print_result(result: SanityResult):
    """Pretty print sanity check results."""
    status = "✅ PASSED" if result.passed else "❌ BLOCKED"
    print(f"\n{'='*60}")
    print(f"SANITY CHECK: {status}")
    print(f"{'='*60}")
    print(f"N={result.n}, WR={result.wr:.1f}%, PF={result.pf:.2f}")
    print()

    print("Checks:")
    for check, passed in result.checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check}")

    if result.failures:
        print(f"\n❌ FAILURES ({len(result.failures)}):")
        for f in result.failures:
            print(f"  - {f}")

    if result.warnings:
        print(f"\n⚠️ WARNINGS ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"  - {w}")

    if result.details:
        print(f"\nDetails:")
        for k, v in result.details.items():
            print(f"  {k}: {v}")

    print()


if __name__ == '__main__':
    # Example usage
    example_trades = [
        {'date': '2024-01-08', 'symbol': 'AAPL', 'entry': 180, 'exit': 183, 'win': True},
        {'date': '2024-01-08', 'symbol': 'MSFT', 'entry': 370, 'exit': 365, 'win': False},
        {'date': '2024-02-05', 'symbol': 'AAPL', 'entry': 185, 'exit': 188, 'win': True},
    ]

    result = sanity_check(
        trades=example_trades,
        filter_description="gap down + first bar green",
        win_description="exit > entry",
        min_n=3,  # low for example
    )
    print_result(result)
