#!/usr/bin/env python3
"""
Simulate sector concentration caps on Discovery Engine backtest data.
Reads from backfill_signal_outcomes, applies TP/SL capping, compares sector cap scenarios.
"""

import sqlite3
import statistics
from collections import defaultdict

DB_PATH = "/home/saengtawan/work/project/cc/stock-analyzer/data/trade_history.db"

# TP/SL parameters (approximate average)
TP = 3.0   # take profit %
SL = 2.5   # stop loss %


def cap_return(outcome_5d):
    """Apply TP/SL capping to a raw 5-day outcome."""
    if outcome_5d >= TP:
        return TP
    elif outcome_5d <= -SL:
        return -SL
    else:
        return outcome_5d


def load_data():
    """Load all discovery picks with outcomes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT scan_date, symbol, sector, outcome_5d, outcome_max_gain_5d, outcome_max_dd_5d
        FROM backfill_signal_outcomes
        WHERE outcome_5d IS NOT NULL
        ORDER BY scan_date, outcome_5d DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows


def group_by_date(rows):
    """Group rows by scan_date."""
    by_date = defaultdict(list)
    for r in rows:
        by_date[r['scan_date']].append(dict(r))
    return by_date


def apply_sector_cap(day_picks, max_per_sector):
    """
    Apply sector cap: keep at most max_per_sector picks per sector.
    Picks are already sorted by outcome_5d DESC (best first).
    Since we're simulating what we'd pick BEFORE knowing outcome,
    we need a selection rule. We'll test two approaches:
    1) Random within sector (average of all permutations ~ take first N alphabetically)
    2) Best outcome (upper bound -- oracle)

    For fairness, we use random selection (alphabetical by symbol as proxy).
    """
    sector_count = defaultdict(int)
    kept = []

    # Sort by sector then symbol (alphabetical) for deterministic "random" selection
    # This avoids look-ahead bias
    day_sorted = sorted(day_picks, key=lambda x: (x['sector'] or '', x['symbol']))

    for pick in day_sorted:
        sector = pick['sector'] or 'Unknown'
        if max_per_sector is None or sector_count[sector] < max_per_sector:
            sector_count[sector] += 1
            kept.append(pick)

    return kept


def apply_sector_cap_oracle(day_picks, max_per_sector):
    """Oracle version: keep the BEST outcome picks per sector (upper bound)."""
    sector_count = defaultdict(int)
    kept = []

    # Already sorted by outcome_5d DESC
    for pick in day_picks:
        sector = pick['sector'] or 'Unknown'
        if max_per_sector is None or sector_count[sector] < max_per_sector:
            sector_count[sector] += 1
            kept.append(pick)

    return kept


def apply_sector_cap_worst(day_picks, max_per_sector):
    """Worst-case version: keep the WORST outcome picks per sector (lower bound)."""
    sector_count = defaultdict(int)
    kept = []

    # Sort by outcome ASC (worst first)
    day_sorted = sorted(day_picks, key=lambda x: x['outcome_5d'])

    for pick in day_sorted:
        sector = pick['sector'] or 'Unknown'
        if max_per_sector is None or sector_count[sector] < max_per_sector:
            sector_count[sector] += 1
            kept.append(pick)

    return kept


def compute_metrics(picks_by_date, max_per_sector, selection='alpha'):
    """Compute PnL metrics for a given sector cap."""
    total_trades = 0
    total_capped_return = 0.0
    total_raw_return = 0.0
    wins = 0
    losses = 0
    daily_returns = []
    daily_trade_counts = []
    sector_concentration_days = 0  # days where any sector had > max_per_sector before cap
    all_capped_returns = []

    # Track same-sector pair correlation
    sector_pair_outcomes = []  # list of (outcome_a, outcome_b) for same-sector pairs on same day

    for date, day_picks in sorted(picks_by_date.items()):
        # Check concentration before cap
        sector_counts_before = defaultdict(int)
        for p in day_picks:
            sector_counts_before[p['sector'] or 'Unknown'] += 1
        if max_per_sector and any(c > max_per_sector for c in sector_counts_before.values()):
            sector_concentration_days += 1

        # Apply cap
        if selection == 'alpha':
            kept = apply_sector_cap(day_picks, max_per_sector)
        elif selection == 'oracle':
            kept = apply_sector_cap_oracle(day_picks, max_per_sector)
        else:
            kept = apply_sector_cap_worst(day_picks, max_per_sector)

        day_capped_sum = 0.0
        day_raw_sum = 0.0
        day_count = 0

        for pick in kept:
            raw = pick['outcome_5d']
            capped = cap_return(raw)
            total_capped_return += capped
            total_raw_return += raw
            all_capped_returns.append(capped)
            day_capped_sum += capped
            day_raw_sum += raw
            day_count += 1
            total_trades += 1

            if capped > 0:
                wins += 1
            elif capped < 0:
                losses += 1

        daily_returns.append(day_capped_sum / day_count if day_count > 0 else 0)
        daily_trade_counts.append(day_count)

        # Compute same-sector pair correlations
        sector_groups = defaultdict(list)
        for pick in kept:
            sector_groups[pick['sector'] or 'Unknown'].append(pick['outcome_5d'])
        for sector, outcomes in sector_groups.items():
            if len(outcomes) >= 2:
                for i in range(len(outcomes)):
                    for j in range(i + 1, len(outcomes)):
                        sector_pair_outcomes.append((outcomes[i], outcomes[j]))

    n_days = len(picks_by_date)
    wr = wins / total_trades * 100 if total_trades > 0 else 0
    avg_capped = total_capped_return / total_trades if total_trades > 0 else 0
    avg_raw = total_raw_return / total_trades if total_trades > 0 else 0

    # Compute correlation of same-sector pairs
    if len(sector_pair_outcomes) >= 2:
        xs = [p[0] for p in sector_pair_outcomes]
        ys = [p[1] for p in sector_pair_outcomes]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / n
        std_x = (sum((x - mean_x) ** 2 for x in xs) / n) ** 0.5
        std_y = (sum((y - mean_y) ** 2 for y in ys) / n) ** 0.5
        corr = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0
    else:
        corr = None

    # Compute Sharpe-like ratio (daily mean / daily std)
    if len(daily_returns) > 1:
        daily_mean = statistics.mean(daily_returns)
        daily_std = statistics.stdev(daily_returns)
        sharpe_like = daily_mean / daily_std if daily_std > 0 else 0
    else:
        sharpe_like = 0

    # Win/loss distribution
    big_wins = sum(1 for r in all_capped_returns if r >= TP)
    big_losses = sum(1 for r in all_capped_returns if r <= -SL)
    small_wins = sum(1 for r in all_capped_returns if 0 < r < TP)
    small_losses = sum(1 for r in all_capped_returns if -SL < r < 0)
    flat = sum(1 for r in all_capped_returns if r == 0)

    return {
        'total_trades': total_trades,
        'n_days': n_days,
        'trades_per_day': total_trades / n_days if n_days > 0 else 0,
        'total_capped_pnl': total_capped_return,
        'total_raw_pnl': total_raw_return,
        'avg_capped_return': avg_capped,
        'avg_raw_return': avg_raw,
        'win_rate': wr,
        'wins': wins,
        'losses': losses,
        'big_wins_tp': big_wins,
        'big_losses_sl': big_losses,
        'small_wins': small_wins,
        'small_losses': small_losses,
        'flat': flat,
        'concentration_days': sector_concentration_days,
        'same_sector_corr': corr,
        'n_sector_pairs': len(sector_pair_outcomes),
        'sharpe_like': sharpe_like,
        'daily_mean': statistics.mean(daily_returns) if daily_returns else 0,
        'daily_std': statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0,
    }


def print_metrics(label, m):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Total trades:        {m['total_trades']:,}")
    print(f"  Days:                {m['n_days']}")
    print(f"  Trades/day:          {m['trades_per_day']:.1f}")
    print(f"  Total capped PnL:    {m['total_capped_pnl']:+.2f}%")
    print(f"  Total raw PnL:       {m['total_raw_pnl']:+.2f}%")
    print(f"  Avg capped return:   {m['avg_capped_return']:+.4f}%")
    print(f"  Avg raw return:      {m['avg_raw_return']:+.4f}%")
    print(f"  Win rate:            {m['win_rate']:.1f}%")
    print(f"  Wins / Losses:       {m['wins']} / {m['losses']}")
    print(f"  Hit TP (>={TP}%):     {m['big_wins_tp']} ({m['big_wins_tp']/m['total_trades']*100:.1f}%)")
    print(f"  Hit SL (<=-{SL}%):    {m['big_losses_sl']} ({m['big_losses_sl']/m['total_trades']*100:.1f}%)")
    print(f"  Small wins:          {m['small_wins']} ({m['small_wins']/m['total_trades']*100:.1f}%)")
    print(f"  Small losses:        {m['small_losses']} ({m['small_losses']/m['total_trades']*100:.1f}%)")
    print(f"  Flat (0.0):          {m['flat']}")
    print(f"  Days with excess:    {m['concentration_days']} / {m['n_days']}")
    if m['same_sector_corr'] is not None:
        print(f"  Same-sector corr:    {m['same_sector_corr']:.3f} (n_pairs={m['n_sector_pairs']:,})")
    else:
        print(f"  Same-sector corr:    N/A (no pairs)")
    print(f"  Daily mean return:   {m['daily_mean']:+.4f}%")
    print(f"  Daily std return:    {m['daily_std']:.4f}%")
    print(f"  Sharpe-like ratio:   {m['sharpe_like']:.3f}")


def sector_detail_analysis(picks_by_date):
    """Show per-sector outcome stats."""
    sector_outcomes = defaultdict(list)
    for date, day_picks in picks_by_date.items():
        for pick in day_picks:
            sector = pick['sector'] or 'Unknown'
            sector_outcomes[sector].append(cap_return(pick['outcome_5d']))

    print(f"\n{'='*60}")
    print(f"  PER-SECTOR OUTCOME STATS (capped)")
    print(f"{'='*60}")
    print(f"  {'Sector':<25} {'N':>5} {'Avg':>7} {'WR':>6} {'TP%':>5} {'SL%':>5}")
    print(f"  {'-'*55}")

    for sector in sorted(sector_outcomes.keys(), key=lambda s: -len(sector_outcomes[s])):
        outcomes = sector_outcomes[sector]
        n = len(outcomes)
        avg = sum(outcomes) / n
        wr = sum(1 for o in outcomes if o > 0) / n * 100
        tp_pct = sum(1 for o in outcomes if o >= TP) / n * 100
        sl_pct = sum(1 for o in outcomes if o <= -SL) / n * 100
        print(f"  {sector:<25} {n:>5} {avg:>+7.3f} {wr:>5.1f}% {tp_pct:>4.1f}% {sl_pct:>4.1f}%")


def concentration_detail(picks_by_date):
    """Show how many days have N+ picks from same sector."""
    print(f"\n{'='*60}")
    print(f"  SECTOR CONCENTRATION DISTRIBUTION")
    print(f"{'='*60}")

    max_counts = []
    for date, day_picks in sorted(picks_by_date.items()):
        sector_counts = defaultdict(int)
        for p in day_picks:
            sector_counts[p['sector'] or 'Unknown'] += 1
        max_count = max(sector_counts.values())
        max_counts.append((date, max_count, max(sector_counts, key=sector_counts.get)))

    # Distribution
    from collections import Counter
    dist = Counter(mc[1] for mc in max_counts)
    print(f"\n  Max picks from single sector per day:")
    for k in sorted(dist.keys()):
        print(f"    {k:>2} picks: {dist[k]:>3} days ({dist[k]/len(max_counts)*100:.1f}%)")

    # Top 10 most concentrated days
    print(f"\n  Top 10 most concentrated days:")
    max_counts.sort(key=lambda x: -x[1])
    for date, cnt, sector in max_counts[:10]:
        print(f"    {date}: {cnt} picks in {sector}")

    # Average number of distinct sectors per day
    sectors_per_day = []
    for date, day_picks in picks_by_date.items():
        sectors_per_day.append(len(set(p['sector'] for p in day_picks)))
    print(f"\n  Avg distinct sectors/day: {statistics.mean(sectors_per_day):.1f}")
    print(f"  Min distinct sectors/day: {min(sectors_per_day)}")
    print(f"  Max distinct sectors/day: {max(sectors_per_day)}")


def dropped_picks_analysis(picks_by_date, max_per_sector):
    """Analyze what gets dropped by sector cap."""
    dropped_outcomes = []
    kept_outcomes = []

    for date, day_picks in sorted(picks_by_date.items()):
        # Alphabetical selection (same as apply_sector_cap)
        sector_count = defaultdict(int)
        day_sorted = sorted(day_picks, key=lambda x: (x['sector'] or '', x['symbol']))

        for pick in day_sorted:
            sector = pick['sector'] or 'Unknown'
            capped = cap_return(pick['outcome_5d'])
            if sector_count[sector] < max_per_sector:
                sector_count[sector] += 1
                kept_outcomes.append(capped)
            else:
                dropped_outcomes.append(capped)

    if dropped_outcomes:
        print(f"\n  Dropped picks analysis (cap={max_per_sector}):")
        print(f"    N dropped:     {len(dropped_outcomes)}")
        print(f"    Avg outcome:   {sum(dropped_outcomes)/len(dropped_outcomes):+.4f}%")
        print(f"    WR dropped:    {sum(1 for o in dropped_outcomes if o > 0)/len(dropped_outcomes)*100:.1f}%")
        print(f"    Kept avg:      {sum(kept_outcomes)/len(kept_outcomes):+.4f}%")
        print(f"    Kept WR:       {sum(1 for o in kept_outcomes if o > 0)/len(kept_outcomes)*100:.1f}%")


def main():
    print("Loading data...")
    rows = load_data()
    picks_by_date = group_by_date(rows)
    print(f"Loaded {len(rows)} picks across {len(picks_by_date)} days")
    print(f"TP={TP}%, SL={SL}%")

    # Sector detail analysis
    sector_detail_analysis(picks_by_date)

    # Concentration detail
    concentration_detail(picks_by_date)

    # ===== SCENARIO COMPARISONS =====
    print(f"\n\n{'#'*60}")
    print(f"  SCENARIO COMPARISON (Alphabetical selection = no look-ahead)")
    print(f"{'#'*60}")

    scenarios = [
        ("NO CAP (current, all 50/day)", None),
        ("MAX 5 PER SECTOR", 5),
        ("MAX 4 PER SECTOR", 4),
        ("MAX 3 PER SECTOR", 3),
        ("MAX 2 PER SECTOR", 2),
        ("MAX 1 PER SECTOR", 1),
    ]

    results = {}
    for label, cap in scenarios:
        m = compute_metrics(picks_by_date, cap, selection='alpha')
        print_metrics(label, m)
        results[label] = m

    # ===== ORACLE COMPARISON (upper bound) =====
    print(f"\n\n{'#'*60}")
    print(f"  ORACLE COMPARISON (best outcome selection = upper bound)")
    print(f"{'#'*60}")

    for cap in [2, 1]:
        m = compute_metrics(picks_by_date, cap, selection='oracle')
        print_metrics(f"MAX {cap} PER SECTOR (ORACLE)", m)

    # ===== WORST CASE COMPARISON (lower bound) =====
    print(f"\n\n{'#'*60}")
    print(f"  WORST-CASE COMPARISON (worst outcome selection = lower bound)")
    print(f"{'#'*60}")

    for cap in [2, 1]:
        m = compute_metrics(picks_by_date, cap, selection='worst')
        print_metrics(f"MAX {cap} PER SECTOR (WORST)", m)

    # ===== DROPPED PICKS ANALYSIS =====
    print(f"\n\n{'#'*60}")
    print(f"  DROPPED PICKS ANALYSIS")
    print(f"{'#'*60}")

    for cap in [5, 3, 2, 1]:
        dropped_picks_analysis(picks_by_date, cap)

    # ===== SUMMARY TABLE =====
    print(f"\n\n{'#'*60}")
    print(f"  SUMMARY COMPARISON TABLE")
    print(f"{'#'*60}")
    print(f"\n  {'Scenario':<35} {'Trades':>7} {'AvgRet':>8} {'WR':>6} {'TotPnL':>9} {'Sharpe':>7}")
    print(f"  {'-'*72}")
    for label, cap in scenarios:
        m = results[label]
        short_label = label[:35]
        print(f"  {short_label:<35} {m['total_trades']:>7} {m['avg_capped_return']:>+8.4f} {m['win_rate']:>5.1f}% {m['total_capped_pnl']:>+9.2f} {m['sharpe_like']:>7.3f}")


if __name__ == '__main__':
    main()
