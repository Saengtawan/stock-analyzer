#!/usr/bin/env python3
"""
Weekly Signal Count Report — v7.02

Logs unique signal counts per week from signal_outcomes.
Run every Monday or manually to track progress toward n>=300 calibration target.

Usage:
  python3 scripts/weekly_signal_report.py           # last 8 weeks
  python3 scripts/weekly_signal_report.py --weeks 12
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from database.orm.base import get_session
from sqlalchemy import text
import argparse
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'trade_history.db'
CALIBRATION_TARGET = 300


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def report(weeks: int = 8):
    with get_session() as session:

        today = date.today()
        start_monday = monday_of(today) - timedelta(weeks=weeks - 1)

        print(f"\n{'='*62}")
        print(f"  Weekly Signal Count Report  (target: n>={CALIBRATION_TARGET} QUEUE_FULL unique)")
        print(f"{'='*62}")
        print(f"{'Week':<12} {'Mon':>10}  {'QUEUE_FULL':>10}  {'All actions':>11}  {'Cumulative QF':>14}")
        print(f"{'-'*62}")

        cumulative_qf = 0
        total_qf = 0

        for w in range(weeks):
            mon = start_monday + timedelta(weeks=w)
            sun = mon + timedelta(days=6)

            # Unique (symbol, scan_date) per week — deduped
            rows = session.execute(text("""
                SELECT action_taken, COUNT(DISTINCT symbol || '|' || scan_date) as n
                FROM signal_outcomes
                WHERE scan_date BETWEEN :p0 AND :p1
                GROUP BY action_taken
            """), {'p0': mon.isoformat(), 'p1': sun.isoformat()}).fetchall()

            qf_count = 0
            all_count = 0
            for r in rows:
                all_count += r[1]
                if r[0] == 'QUEUE_FULL':
                    qf_count = r[1]

            cumulative_qf += qf_count
            total_qf += qf_count

            marker = ' [OK]' if cumulative_qf >= CALIBRATION_TARGET else ''
            week_label = f"wk{mon.strftime('%V')}"
            print(f"{week_label:<12} {mon.isoformat():>10}  {qf_count:>10}  {all_count:>11}  {cumulative_qf:>14}{marker}")

        print(f"{'-'*62}")
        print(f"{'TOTAL':<12} {'':>10}  {total_qf:>10}")

        remaining = max(0, CALIBRATION_TARGET - total_qf)
        if remaining > 0:
            # Estimate weeks remaining based on recent avg (last 4 weeks)
            recent_mon = monday_of(today) - timedelta(weeks=3)
            recent_row = session.execute(text("""
                SELECT COUNT(DISTINCT symbol || '|' || scan_date) as n
                FROM signal_outcomes
                WHERE action_taken = 'QUEUE_FULL'
                  AND scan_date BETWEEN :p0 AND :p1
            """), {'p0': recent_mon.isoformat(), 'p1': today.isoformat()}).fetchone()
            recent_avg = (recent_row[0] / 4) if recent_row[0] else 1
            eta_weeks = int(remaining / recent_avg) + 1 if recent_avg > 0 else '?'
            print(f"\n  Need {remaining} more QUEUE_FULL signals for calibration")
            print(f"  Recent avg: ~{recent_avg:.0f}/week -> ETA ~{eta_weeks} weeks")
        else:
            print(f"\n  Calibration target reached! Run weight calibration analysis.")

        # --- new_score quality breakdown (QUEUE_FULL only, all-time) ---
        score_rows = session.execute(text("""
            SELECT
                SUM(CASE WHEN new_score IS NULL           THEN 1 ELSE 0 END) as no_score,
                SUM(CASE WHEN new_score < 60              THEN 1 ELSE 0 END) as lt60,
                SUM(CASE WHEN new_score >= 60 AND new_score < 70 THEN 1 ELSE 0 END) as s60_70,
                SUM(CASE WHEN new_score >= 70 AND new_score < 75 THEN 1 ELSE 0 END) as s70_75,
                SUM(CASE WHEN new_score >= 75 AND new_score < 80 THEN 1 ELSE 0 END) as s75_80,
                SUM(CASE WHEN new_score >= 80                    THEN 1 ELSE 0 END) as ge80
            FROM signal_outcomes
            WHERE action_taken = 'QUEUE_FULL'
              AND scan_date BETWEEN :p0 AND :p1
        """), {'p0': start_monday.isoformat(), 'p1': today.isoformat()}).fetchone()

        if score_rows:
            print(f"\n  new_score distribution (QUEUE_FULL, last {weeks} wks):")
            print(f"    NULL={score_rows[0]}  <60={score_rows[1]}  "
                  f"60-70={score_rows[2]}  70-75={score_rows[3]}  "
                  f"75-80={score_rows[4]}  >=80={score_rows[5]}")
            scored_total = (score_rows[1] or 0) + (score_rows[2] or 0) + \
                           (score_rows[3] or 0) + (score_rows[4] or 0) + \
                           (score_rows[5] or 0)
            passing = (score_rows[3] or 0) + (score_rows[4] or 0) + (score_rows[5] or 0)
            if scored_total > 0:
                print(f"    Pass rate (>=70): {passing}/{scored_total} = {passing/scored_total*100:.0f}%")

        print(f"{'='*62}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Weekly signal count report')
    parser.add_argument('--weeks', type=int, default=8, help='Number of weeks to show (default: 8)')
    args = parser.parse_args()
    report(args.weeks)
