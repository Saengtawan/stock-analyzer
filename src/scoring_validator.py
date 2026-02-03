#!/usr/bin/env python3
"""
Scoring Model Validator v1.0

Analyzes trading performance by score components to validate
that scoring weights are empirically justified.

Usage:
    python src/scoring_validator.py [--days 30]

Output:
    - Factor-by-factor win rate analysis
    - Score threshold vs win rate curve
    - Component correlation with P&L
"""

import os
import sys
import json
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger


def load_trade_history(days: int = 60) -> List[Dict]:
    """Load trade history from trade_logger JSON files."""
    trade_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_logs')

    if not os.path.exists(trade_dir):
        logger.warning(f"No trade_logs directory: {trade_dir}")
        return []

    all_trades = []
    cutoff = datetime.now() - timedelta(days=days)

    for fname in sorted(os.listdir(trade_dir)):
        if not fname.endswith('.json'):
            continue
        # File format: trades_YYYY-MM-DD.json
        try:
            date_str = fname.replace('trades_', '').replace('.json', '')
            file_date = datetime.strptime(date_str, '%Y-%m-%d')
            if file_date < cutoff:
                continue
        except ValueError:
            continue

        with open(os.path.join(trade_dir, fname), 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                all_trades.extend(data)

    logger.info(f"Loaded {len(all_trades)} trade log entries from {days} days")
    return all_trades


def analyze_score_vs_winrate(trades: List[Dict]):
    """Analyze win rate at different score thresholds."""
    sells = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl_pct') is not None]

    if not sells:
        print("No SELL trades with P&L data found.")
        return

    # Group by score bucket
    buckets = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_pnl': 0.0})

    for t in sells:
        score = t.get('signal_score', 0) or 0
        pnl = t.get('pnl_pct', 0) or 0

        # Find matching BUY for this symbol to get signal_score
        if score == 0:
            # Try to get from associated buy
            continue

        bucket = (score // 5) * 5  # Round to nearest 5
        if pnl > 0:
            buckets[bucket]['wins'] += 1
        else:
            buckets[bucket]['losses'] += 1
        buckets[bucket]['total_pnl'] += pnl

    if not buckets:
        print("No scored trades found. Make sure trades have signal_score field.")
        return

    print("\n" + "=" * 60)
    print("SCORE vs WIN RATE ANALYSIS")
    print("=" * 60)
    print(f"{'Score':>8} {'Trades':>8} {'Win%':>8} {'Avg P&L':>10}")
    print("-" * 40)

    for bucket in sorted(buckets.keys()):
        data = buckets[bucket]
        total = data['wins'] + data['losses']
        wr = (data['wins'] / total * 100) if total > 0 else 0
        avg_pnl = data['total_pnl'] / total if total > 0 else 0
        bar = '#' * int(wr / 5)
        print(f"{bucket:>5}-{bucket+4:<3} {total:>6}   {wr:>5.1f}%  {avg_pnl:>+8.2f}%  {bar}")


def analyze_factor_correlation(trades: List[Dict]):
    """Analyze individual factor correlations with outcome."""
    sells = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl_pct') is not None]

    if not sells:
        print("No SELL trades to analyze.")
        return

    # Factors to check
    factors = ['atr_pct', 'gap_pct', 'signal_score', 'return_5d', 'return_20d',
               'beta', 'volume_ratio', 'dist_from_52w_high']

    print("\n" + "=" * 60)
    print("FACTOR CORRELATION WITH P&L")
    print("=" * 60)
    print(f"{'Factor':>22} {'N':>6} {'Corr':>8} {'AvgWin':>10} {'AvgLoss':>10}")
    print("-" * 58)

    for factor in factors:
        values = []
        pnls = []
        wins = []
        losses = []

        for t in sells:
            val = t.get(factor)
            pnl = t.get('pnl_pct', 0)
            if val is not None and pnl is not None:
                values.append(float(val))
                pnls.append(float(pnl))
                if pnl > 0:
                    wins.append(float(val))
                else:
                    losses.append(float(val))

        if len(values) < 5:
            print(f"{factor:>22} {len(values):>6}   (insufficient data)")
            continue

        # Simple correlation
        n = len(values)
        mean_x = sum(values) / n
        mean_y = sum(pnls) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(values, pnls)) / n
        std_x = (sum((x - mean_x) ** 2 for x in values) / n) ** 0.5
        std_y = (sum((y - mean_y) ** 2 for y in pnls) / n) ** 0.5

        corr = cov / (std_x * std_y) if std_x > 0 and std_y > 0 else 0

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        print(f"{factor:>22} {n:>6}  {corr:>+7.3f}  {avg_win:>+9.2f}  {avg_loss:>+9.2f}")


def analyze_hold_duration(trades: List[Dict]):
    """Analyze hold duration vs outcome."""
    sells = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl_pct') is not None]

    if not sells:
        return

    print("\n" + "=" * 60)
    print("HOLD DURATION vs WIN RATE")
    print("=" * 60)

    by_day = defaultdict(lambda: {'wins': 0, 'losses': 0, 'total_pnl': 0.0})

    for t in sells:
        day = t.get('day_held', 0) or 0
        pnl = t.get('pnl_pct', 0) or 0
        if pnl > 0:
            by_day[day]['wins'] += 1
        else:
            by_day[day]['losses'] += 1
        by_day[day]['total_pnl'] += pnl

    print(f"{'Day':>6} {'Trades':>8} {'Win%':>8} {'Avg P&L':>10}")
    print("-" * 36)

    for day in sorted(by_day.keys()):
        data = by_day[day]
        total = data['wins'] + data['losses']
        wr = (data['wins'] / total * 100) if total > 0 else 0
        avg_pnl = data['total_pnl'] / total if total > 0 else 0
        print(f"{day:>6} {total:>6}   {wr:>5.1f}%  {avg_pnl:>+8.2f}%")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scoring Model Validator')
    parser.add_argument('--days', type=int, default=60, help='Days of history to analyze')
    args = parser.parse_args()

    print("=" * 60)
    print("  SCORING MODEL VALIDATOR v1.0")
    print(f"  Analyzing last {args.days} days of trades")
    print("=" * 60)

    trades = load_trade_history(days=args.days)

    if not trades:
        print("\nNo trade data found. Run the system first to generate trade logs.")
        return

    analyze_score_vs_winrate(trades)
    analyze_factor_correlation(trades)
    analyze_hold_duration(trades)

    print("\n" + "=" * 60)
    print("  RECOMMENDATIONS")
    print("=" * 60)
    print("  1. Factors with |corr| > 0.2 are worth keeping/increasing weight")
    print("  2. Factors with |corr| < 0.05 may be noise (consider removing)")
    print("  3. Score threshold should be set where Win% consistently > 50%")
    print("=" * 60)


if __name__ == '__main__':
    main()
