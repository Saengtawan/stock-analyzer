"""Shadow Step 24 outcome simulator.

Step 24 vs Step 25 differ ONLY in Z4 exit (SL -3% vs pure hold).
At pick time both make identical picks. So "shadow" = re-evaluate Z4 picks
with hypothetical SL @ -3% to see if Step 24 would have done better/worse.

Daily report:
  - Z4 picks (real outcome vs hypothetical SL outcome)
  - Cumulative total: actual Step 25 vs shadow Step 24
  - Trade-by-trade where SL would have triggered

Usage:
  python3 scripts/shadow_step24.py              # last 7 days
  python3 scripts/shadow_step24.py --days=30    # last 30 days
"""
import argparse
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

Z4_SL_PCT = 0.03  # Step 24 SL %
SLIPPAGE = 0.001  # 0.1% per trade

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--journal', default='data/scan_journal.db')
    parser.add_argument('--main-db', default='data/trade_history.db')
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    journal = sqlite3.connect(str(repo_root / args.journal))
    main_db = sqlite3.connect(str(repo_root / args.main_db))

    cutoff = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    # Get Z4 picks with outcomes (mfo 45-75)
    rows = journal.execute("""
        SELECT p.id, p.scan_ts, p.scan_date, p.symbol, p.entry, p.bucket,
               p.ml_prob, p.features_json,
               o.pnl_pct, o.exit_reason, o.exit_ts
        FROM scan_picks p
        LEFT JOIN pick_outcomes o ON p.id = o.pick_id
        WHERE p.strategy = 'ml_filter' AND p.scan_date >= ?
        ORDER BY p.scan_ts
    """, (cutoff,)).fetchall()

    if not rows:
        print(f"No ml_filter picks in last {args.days} days")
        return

    print(f"\n{'='*100}")
    print(f"Shadow Step 24 outcomes — last {args.days} days (Step 25 actual vs Step 24 SL -3% hypothetical)")
    print('='*100)

    z4_actual_total = 0.0
    z4_shadow_total = 0.0
    z4_n = 0
    z4_sl_hits = 0
    all_actual_total = 0.0  # combined across all zones for ref
    rescued_trades = []  # SL saved money
    whipsaw_trades = []  # SL cost money

    print(f"\n{'Date':<11}{'Sym':<7}{'mfo':>4}{'Zone':>5}{'Entry':>9}{'Actual pnl':>12}{'SL pnl':>10}{'Diff':>9}{'SL hit?':>10}")
    print("-"*97)

    for r in rows:
        pid, ts, date, sym, entry, bucket, prob, fjson, actual_pnl, exit_r, exit_ts = r
        if actual_pnl is None: continue
        # Derive mfo from scan_ts (ET time = HH:MM)
        try:
            scan_dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
            mfo = (scan_dt.hour - 9) * 60 + (scan_dt.minute - 30)
        except: continue
        if mfo < 0 or mfo > 90: continue
        # Determine zone
        if mfo <= 9: zone = 'Z1'
        elif mfo <= 29: zone = 'Z2'
        elif mfo <= 44: zone = 'Z3'
        else: zone = 'Z4'

        all_actual_total += actual_pnl
        if zone != 'Z4': continue

        # Z4 only: check if SL -3% would have triggered
        # Get intraday bars after fill time, look at lows
        sl_price = entry * (1 - Z4_SL_PCT)
        # Use intraday_bars_5m
        fill_dt = datetime.fromisoformat(ts.replace(' ', 'T').replace('Z',''))
        # Get bars after fill_dt on the same date
        bars = main_db.execute("""
            SELECT timestamp, low FROM intraday_bars_5m
            WHERE symbol = ? AND DATE(timestamp) = ?
            AND time(timestamp) > '13:30:00' AND time(timestamp) <= '20:00:00'
            ORDER BY timestamp
        """, (sym, date)).fetchall()

        sl_hit = False
        for bar_ts, low in bars:
            try:
                bar_dt = datetime.fromisoformat(bar_ts.replace('Z',''))
                if bar_dt <= fill_dt: continue
                if low and low <= sl_price:
                    sl_hit = True
                    break
            except: pass

        if sl_hit:
            shadow_pnl = -Z4_SL_PCT * 100 - SLIPPAGE * 100  # -3.10%
            z4_sl_hits += 1
        else:
            shadow_pnl = actual_pnl

        z4_actual_total += actual_pnl
        z4_shadow_total += shadow_pnl
        z4_n += 1
        diff = actual_pnl - shadow_pnl

        if sl_hit:
            if actual_pnl > shadow_pnl:
                whipsaw_trades.append((date, sym, actual_pnl, shadow_pnl, diff))
                hit_str = "WHIPSAW"
            else:
                rescued_trades.append((date, sym, actual_pnl, shadow_pnl, diff))
                hit_str = "RESCUE"
        else:
            hit_str = "no"

        print(f"{date:<11}{sym:<7}{mfo:>4}{zone:>5}{entry:>8.2f} {actual_pnl:>+10.2f}% {shadow_pnl:>+8.2f}% {diff:>+7.2f}% {hit_str:>10}")

    print("-"*97)
    print(f"\nZ4 trades: {z4_n}, SL would trigger: {z4_sl_hits} ({z4_sl_hits/max(z4_n,1)*100:.0f}%)")
    print(f"  Whipsaw cost (Step 24 SL hit but actual recovered): {len(whipsaw_trades)} trades")
    print(f"  Rescue value  (Step 24 SL hit and saved money):     {len(rescued_trades)} trades")
    print(f"\nCumulative Z4 totals:")
    print(f"  Step 25 actual (pure hold):  {z4_actual_total:+.2f}%")
    print(f"  Step 24 shadow (SL -3%):     {z4_shadow_total:+.2f}%")
    print(f"  Difference (Step 25 - 24):   {z4_actual_total - z4_shadow_total:+.2f}%")

    if z4_actual_total - z4_shadow_total > 0:
        verdict = "Step 25 (no SL) WINNING"
    elif z4_actual_total - z4_shadow_total < 0:
        verdict = "Step 24 (with SL) winning"
    else:
        verdict = "tied"
    print(f"\n  Verdict ({args.days}d): {verdict}")

    if rescued_trades:
        print(f"\n  Rescue trades (SL was correct):")
        for d, s, a, sh, di in rescued_trades:
            print(f"    {d} {s} actual={a:+.2f}% SL={sh:+.2f}% diff={di:+.2f}%")
    if whipsaw_trades:
        print(f"\n  Whipsaw trades (no SL was correct):")
        for d, s, a, sh, di in whipsaw_trades:
            print(f"    {d} {s} actual={a:+.2f}% SL={sh:+.2f}% diff={di:+.2f}%")

    # Recommendation
    print(f"\n{'='*100}")
    if z4_n >= 20:
        if z4_actual_total - z4_shadow_total > 5:
            print(f"📊 RECOMMENDATION: Keep Step 25 (no Z4 SL). Cumulative gain over Step 24: {z4_actual_total-z4_shadow_total:+.2f}%")
        elif z4_actual_total - z4_shadow_total < -5:
            print(f"📊 RECOMMENDATION: Rollback to Step 24 (Z4 SL -3%). Cumulative loss: {z4_actual_total-z4_shadow_total:+.2f}%")
        else:
            print(f"📊 RECOMMENDATION: Need more data. Current diff: {z4_actual_total-z4_shadow_total:+.2f}% (n={z4_n})")
    else:
        print(f"📊 Need at least 20 Z4 trades for decision. Current: {z4_n}")


if __name__ == '__main__':
    main()
