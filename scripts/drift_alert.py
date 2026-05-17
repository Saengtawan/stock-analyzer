"""Drift alert: compare live scan outcomes vs WF baseline expectations.

Runs daily after market close. Alerts via log if:
  - 7-day rolling WR < baseline - 10pp
  - Worst trade pnl < -5% (tail breach)
  - Z4 picks > 60% of total (zone imbalance)
  - 0 picks in 5 consecutive trading days (engine issue)

Baseline (Step 25 WF Nov 2025-Apr 2026):
  Z1: WR 89%, avg +2.96%
  Z2: WR 84%, avg +1.81%
  Z3: WR 72%, avg +1.23%
  Z4: WR 81%, avg +1.43%
  Combined: WR 81%, avg +1.73%, worst -4.75%

Usage:
  python3 scripts/drift_alert.py           # report last 7 days
  python3 scripts/drift_alert.py --days=30 # last 30 days
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Step 25 WF baseline
BASELINE = {
    'Z1': {'wr': 89, 'avg': 2.96, 'mfo_range': (0, 9)},
    'Z2': {'wr': 84, 'avg': 1.81, 'mfo_range': (10, 29)},
    'Z3': {'wr': 72, 'avg': 1.23, 'mfo_range': (30, 44)},
    'Z4': {'wr': 81, 'avg': 1.43, 'mfo_range': (45, 75)},
    'combined': {'wr': 81, 'avg': 1.73, 'worst': -4.75},
}

WR_DROP_THRESHOLD = 10  # alert if WR drops > 10pp from baseline
WORST_TAIL_THRESHOLD = -5.0  # alert if any trade < -5%
Z4_IMBALANCE_PCT = 60.0  # alert if Z4 > 60% of picks
ZERO_PICK_DAYS = 5  # alert if 5 consecutive trading days with 0 picks


def bucket_to_zone(bucket: str, mfo: int = None) -> str:
    """Map bucket string or mfo to zone."""
    if mfo is not None:
        for zone, info in BASELINE.items():
            if zone == 'combined': continue
            lo, hi = info['mfo_range']
            if lo <= mfo <= hi:
                return zone
    # fallback by bucket string
    if '09:30-10:00' in bucket: return 'Z1' if mfo and mfo < 10 else 'Z2'
    if '10:00-10:45' in bucket: return 'Z3'
    if '11:30' in bucket or '11:00' in bucket: return 'Z4'
    return 'unknown'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--db', default='data/scan_journal.db')
    parser.add_argument('--alert-log', default='logs/drift_alerts.log')
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    db_path = repo_root / args.db
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        sys.exit(1)

    con = sqlite3.connect(str(db_path))
    cutoff = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    rows = con.execute("""
        SELECT p.id, p.scan_ts, p.scan_date, p.bucket, p.symbol, p.ml_prob,
               p.entry, p.features_json, o.pnl_pct, o.exit_reason
        FROM scan_picks p
        LEFT JOIN pick_outcomes o ON p.id = o.pick_id
        WHERE p.strategy = 'ml_filter' AND p.scan_date >= ?
        ORDER BY p.scan_ts
    """, (cutoff,)).fetchall()

    if not rows:
        print(f"⚠️  NO ML_FILTER PICKS in last {args.days} days — check engine")
        return

    # Parse mfo from features_json
    import json
    parsed = []
    for r in rows:
        pid, scan_ts, date, bucket, sym, prob, entry, fjson, pnl, exit_r = r
        mfo = None
        try:
            f = json.loads(fjson) if fjson else {}
            mfo = f.get('mins_from_open')
        except: pass
        zone = bucket_to_zone(bucket, mfo) if mfo else bucket_to_zone(bucket)
        parsed.append({
            'pid': pid, 'date': date, 'sym': sym, 'zone': zone, 'mfo': mfo,
            'prob': prob, 'pnl': pnl, 'exit': exit_r,
        })

    # Per-zone stats (only with outcome)
    by_zone = {z: [] for z in ['Z1','Z2','Z3','Z4','unknown']}
    for p in parsed:
        if p['pnl'] is not None:
            by_zone[p['zone']].append(p['pnl'])

    total_with_outcome = sum(len(v) for v in by_zone.values())
    total_picks = len(parsed)

    print(f"\n{'='*78}")
    print(f"Drift report — last {args.days} days ({cutoff} → today)")
    print('='*78)
    print(f"  Total picks: {total_picks}  |  With outcome: {total_with_outcome}")

    alerts = []

    # Zero-pick check
    days_with_pick = set(p['date'] for p in parsed)
    weekdays = []
    for i in range(args.days):
        d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        if datetime.strptime(d, '%Y-%m-%d').weekday() < 5:
            weekdays.append(d)
    missing_days = [d for d in weekdays if d not in days_with_pick]
    if len(missing_days) >= ZERO_PICK_DAYS:
        alerts.append(f"⚠️  {len(missing_days)} weekdays with 0 picks: {missing_days[:5]}...")

    # Z4 imbalance
    z4_count = len([p for p in parsed if p['zone'] == 'Z4'])
    if total_picks > 20:
        z4_pct = z4_count / total_picks * 100
        if z4_pct > Z4_IMBALANCE_PCT:
            alerts.append(f"⚠️  Z4 imbalance: {z4_pct:.0f}% of picks (baseline 44%)")

    # Tail breach
    all_pnls = [p['pnl'] for p in parsed if p['pnl'] is not None]
    worst = min(all_pnls) if all_pnls else 0
    if worst < WORST_TAIL_THRESHOLD:
        worst_pick = min((p for p in parsed if p['pnl'] is not None), key=lambda x: x['pnl'])
        alerts.append(f"⚠️  Tail breach: worst trade {worst:+.2f}% ({worst_pick['sym']} {worst_pick['date']} {worst_pick['zone']}) < {WORST_TAIL_THRESHOLD}%")

    # Per-zone WR drift
    print(f"\n  {'Zone':<6}{'N':>5}{'WR':>7}{'avg':>9}{'baseline WR':>14}{'drift':>10}{'status':>10}")
    print(f"  {'-'*60}")
    for z in ['Z1','Z2','Z3','Z4']:
        pnls = by_zone[z]
        if not pnls:
            print(f"  {z:<6}{0:>5}{'--':>7}{'--':>9}{BASELINE[z]['wr']:>13}%{'':>10}{'no data':>10}")
            continue
        wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
        avg = sum(pnls) / len(pnls)
        baseline_wr = BASELINE[z]['wr']
        drift = wr - baseline_wr
        status = "OK"
        if drift < -WR_DROP_THRESHOLD:
            status = "⚠ DRIFT"
            alerts.append(f"⚠️  {z} WR drift: {wr:.0f}% vs baseline {baseline_wr}% ({drift:+.0f}pp)")
        print(f"  {z:<6}{len(pnls):>5}{wr:>6.0f}%{avg:>+8.2f}%{baseline_wr:>13}%{drift:>+9.0f}pp{status:>10}")

    # Combined
    if all_pnls:
        combined_wr = sum(1 for p in all_pnls if p > 0) / len(all_pnls) * 100
        combined_avg = sum(all_pnls) / len(all_pnls)
        baseline_combined_wr = BASELINE['combined']['wr']
        drift = combined_wr - baseline_combined_wr
        print(f"  {'-'*60}")
        print(f"  {'TOTAL':<6}{len(all_pnls):>5}{combined_wr:>6.0f}%{combined_avg:>+8.2f}%{baseline_combined_wr:>13}%{drift:>+9.0f}pp")
        if drift < -WR_DROP_THRESHOLD:
            alerts.append(f"⚠️  Combined WR drift: {combined_wr:.0f}% vs baseline {baseline_combined_wr}%")

    print(f"\n  Recent picks (last 5):")
    for p in parsed[-5:]:
        pnl_str = f"{p['pnl']:+.2f}%" if p['pnl'] is not None else "pending"
        print(f"    {p['date']} {p['sym']:<6} {p['zone']} prob={p['prob']:.2f}  pnl={pnl_str}")

    # Alerts summary
    print(f"\n{'='*78}")
    if alerts:
        print(f"🔴 ALERTS ({len(alerts)}):")
        for a in alerts:
            print(f"  {a}")
        # Log to file
        log_path = repo_root / args.alert_log
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a') as f:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"\n=== {ts} (last {args.days}d) ===\n")
            for a in alerts:
                f.write(f"  {a}\n")
        print(f"\n  Alerts written to {log_path}")
        sys.exit(2)  # non-zero exit for cron to detect
    else:
        print("🟢 No drift detected — system within baseline expectations")


if __name__ == '__main__':
    main()
