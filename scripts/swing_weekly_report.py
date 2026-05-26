"""
swing_weekly_report — Weekly performance summary for swing_filter.

Pulls swing picks + outcomes, computes live WR vs backtest, flags drift.

Usage:
  python3 scripts/swing_weekly_report.py           # last 7 days
  python3 scripts/swing_weekly_report.py --days=30 # last 30 days
"""
import sqlite3
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta

DB_JOURNAL = Path('/home/saengtawan/work/project/cc/stock-analyzer/data/scan_journal.db')

# Backtest expectations (v2.0)
EXPECTED_WR_F1 = 0.93
EXPECTED_EV_F1 = 1.78
EXPECTED_WR_F3 = 1.00
EXPECTED_EV_F3 = 1.99


def report(days=7):
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    con = sqlite3.connect(str(DB_JOURNAL))

    # All swing picks in period (use existing pick_outcomes schema)
    picks = pd.read_sql(f"""
        SELECT p.id, p.scan_date, p.symbol, p.entry, p.tp_price, p.ml_prob,
               o.exit_ts as exit_date, o.exit_price, o.pnl_pct, o.exit_reason,
               o.max_gain_pct, o.max_drawdown_pct
        FROM scan_picks p
        LEFT JOIN pick_outcomes o ON o.pick_id = p.id
        WHERE p.strategy = 'swing_filter'
          AND p.scan_date >= '{cutoff}'
        ORDER BY p.scan_date DESC, p.ml_prob DESC
    """, con)
    # Compute days_held from scan_date + exit_date
    if 'exit_date' in picks.columns:
        picks['days_held'] = (pd.to_datetime(picks['exit_date'], errors='coerce')
                              - pd.to_datetime(picks['scan_date'])).dt.days
    con.close()

    print(f"\n{'='*70}")
    print(f"SWING FILTER WEEKLY REPORT — last {days} days (since {cutoff})")
    print('='*70)

    if len(picks) == 0:
        print(f"\n  No swing picks in last {days} days.\n")
        return

    print(f"\nTotal picks: {len(picks)}")
    print(f"Unique symbols: {picks['symbol'].nunique()}")
    print(f"With outcome: {picks['pnl_pct'].notna().sum()}")
    print(f"Still open: {picks['pnl_pct'].isna().sum()}")

    completed = picks[picks['pnl_pct'].notna()]
    if len(completed) > 0:
        wins = (completed['pnl_pct'] > 0).sum()
        wr = wins / len(completed)
        avg = completed['pnl_pct'].mean()
        worst = completed['pnl_pct'].min()
        best = completed['pnl_pct'].max()
        avg_days = completed['days_held'].mean()

        print(f"\nCompleted trades:")
        print(f"  N:              {len(completed)}")
        print(f"  WR:             {wr*100:.1f}% (expected 93% F1 / 100% F3 OOS)")
        print(f"  Avg PnL:        {avg:+.2f}% (expected +1.78% F1 / +1.99% F3)")
        print(f"  Worst PnL:      {worst:+.2f}% (expected -2.27% F1)")
        print(f"  Best PnL:       {best:+.2f}%")
        print(f"  Avg days held:  {avg_days:.1f} days")

        # Exit reason breakdown
        reasons = completed['exit_reason'].value_counts()
        print(f"\nExit reasons:")
        for r, n in reasons.items():
            print(f"  {r:10s}: {n} ({n/len(completed)*100:.0f}%)")

        # Drift check
        wr_diff = wr - EXPECTED_WR_F1
        ev_diff = avg - EXPECTED_EV_F1
        print(f"\nDrift check (vs F1 expectations):")
        print(f"  WR drift:  {wr_diff*100:+.1f}pp {'⚠️' if abs(wr_diff) > 0.10 else '✅'}")
        print(f"  EV drift:  {ev_diff:+.2f}pp {'⚠️' if abs(ev_diff) > 1.0 else '✅'}")

    print(f"\nRecent picks (top 20 by date):")
    cols = ['scan_date', 'symbol', 'entry', 'ml_prob', 'pnl_pct', 'exit_reason', 'days_held']
    print(picks[cols].head(20).to_string(index=False))


if __name__ == '__main__':
    days = 7
    for arg in sys.argv[1:]:
        if arg.startswith('--days='):
            days = int(arg.split('=')[1])
    report(days)
