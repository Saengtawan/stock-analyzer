#!/usr/bin/env python3
"""Exit ML manual check CLI.

Usage:
  python3 scripts/exit_check.py <SYMBOL> <ENTRY_PRICE> [ENTRY_TIME_ET]

Examples:
  python3 scripts/exit_check.py MKSI 301.75
  python3 scripts/exit_check.py MKSI 301.75 09:35
  python3 scripts/exit_check.py SMTC 136.57 10:05

Reads current bars via yfinance/Alpaca, runs Exit ML, prints recommendation.
USER decides — script just provides decision support. No actual orders placed.
"""
import sys, sqlite3, argparse
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

PROJ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJ))
sys.path.insert(0, str(PROJ / 'backtests'))


def fetch_today_bars(sym):
    """Fetch today's (US/Eastern) bars from intraday_bars_5m (Alpaca DB).
    Returns list of (em, o, h, l, c) ET.
    """
    db = PROJ / 'data' / 'trade_history.db'
    # Use US/Eastern date — server may be in different TZ
    try:
        import pytz
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
    except ImportError:
        today = datetime.today().strftime('%Y-%m-%d')
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT strftime('%H', timestamp) as h, strftime('%M', timestamp) as m, "
        "open, high, low, close FROM intraday_bars_5m "
        "WHERE symbol=? AND DATE(timestamp)=? ORDER BY timestamp",
        (sym, today)
    ).fetchall()
    # Fallback: if no rows today, use latest available date for this symbol
    if not rows:
        latest = con.execute(
            "SELECT MAX(DATE(timestamp)) FROM intraday_bars_5m WHERE symbol=?",
            (sym,)
        ).fetchone()
        if latest and latest[0]:
            print(f"  (no data for {today}, using latest: {latest[0]})", flush=True)
            rows = con.execute(
                "SELECT strftime('%H', timestamp) as h, strftime('%M', timestamp) as m, "
                "open, high, low, close FROM intraday_bars_5m "
                "WHERE symbol=? AND DATE(timestamp)=? ORDER BY timestamp",
                (sym, latest[0])
            ).fetchall()
    con.close()
    bars = []
    day_open = None
    for h_str, m_str, o, hi, lo, c in rows:
        # Bangkok server stores in DB as Bangkok time? or UTC? Need to convert.
        # intraday_bars_5m timestamp = US/Eastern actually (Alpaca returns ET)
        # But sqlite strftime treats stored value as-is. Trust the timestamp.
        em = int(h_str) * 60 + int(m_str)
        # Map server-stored time to ET: if 13:30 = 09:30 ET shift, but appears
        # we store in ET already. First bar should be em=570 (09:30 ET).
        if em < 570: continue
        if em > 960: break
        if o is None or c is None: continue
        bars.append((em, float(o), float(hi), float(lo), float(c)))
        if day_open is None and em == 570: day_open = float(o)
    if not day_open and bars:
        day_open = bars[0][1]
    return bars, day_open


def fetch_entry_features(sym, entry_em):
    """Build entry-time 72 pkl features from production scan_candidates or scan_picks."""
    # Try scan_candidates first (has full features_json sometimes)
    db = PROJ / 'data' / 'scan_journal.db'
    if not db.exists():
        return None
    con = sqlite3.connect(str(db))
    # Look for today's pick at this sym
    today = datetime.today().strftime('%Y-%m-%d')
    row = con.execute(
        "SELECT features_json FROM scan_candidates WHERE symbol=? AND scan_date=? AND mfo=? AND selected=1 LIMIT 1",
        (sym, today, entry_em - 570)
    ).fetchone()
    con.close()
    if not row or not row[0]:
        return None
    import json
    feats = json.loads(row[0])
    # If only summary (9 fields), can't recover full 72
    if len(feats) < 50:
        return None
    return feats


def fetch_recent_pkl_features(sym):
    """Fallback: use most recent pkl row for this sym (today's entry mfo)."""
    pkl_path = PROJ / 'cache' / 'bt_features' / 'features.pkl'
    if not pkl_path.exists():
        return None
    df = pd.read_pickle(str(pkl_path))
    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    sym_rows = df[df['sym'] == sym].sort_values('date', ascending=False).head(1)
    return sym_rows.iloc[0] if len(sym_rows) else None


def auto_lookup_entry(sym):
    """Look up today's entry for this symbol from scan_picks DB.
    Returns (entry_price, entry_em, win_p, pred_r) or None.
    """
    db = PROJ / 'data' / 'scan_journal.db'
    if not db.exists(): return None
    try:
        import pytz
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
    except ImportError:
        today = datetime.today().strftime('%Y-%m-%d')
    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT scan_ts, entry, ml_prob FROM scan_picks "
        "WHERE symbol=? AND scan_date=? ORDER BY scan_ts LIMIT 1",
        (sym, today)
    ).fetchone()
    # Fallback: latest entry for this symbol any date
    if not row:
        row = con.execute(
            "SELECT scan_ts, entry, ml_prob FROM scan_picks "
            "WHERE symbol=? ORDER BY scan_ts DESC LIMIT 1",
            (sym,)
        ).fetchone()
    con.close()
    if not row: return None
    scan_ts, entry, ml_prob = row
    # Parse scan_ts "2026-05-20 09:35:39" → ET HH:MM
    dt = datetime.strptime(scan_ts.split('.')[0], '%Y-%m-%d %H:%M:%S')
    entry_em = dt.hour * 60 + dt.minute
    return entry, entry_em, ml_prob, scan_ts


def main():
    ap = argparse.ArgumentParser(
        description='Manual Exit ML check. Both entry_price + entry_time are REQUIRED '
                    '(prevents wrong defaults if broker fill differs from scan_picks).')
    ap.add_argument('symbol', help='Stock symbol (e.g. MKSI)')
    ap.add_argument('entry_price', type=float,
                    help='Actual entry price (your fill, may differ from scan)')
    ap.add_argument('entry_time',
                    help='Entry time ET HH:MM (your actual fill time)')
    ap.add_argument('--win_p', type=float, default=None,
                    help='Entry win_p (auto-lookup from scan_picks if omitted)')
    ap.add_argument('--pred_r', type=float, default=0.99, help='Entry pred_r (default 0.99)')
    ap.add_argument('--atr', type=float, default=3.0, help='ATR pct (default 3.0)')
    args = ap.parse_args()

    sym = args.symbol.upper()
    entry_price = args.entry_price
    win_p_arg = args.win_p

    # Parse required time
    h, m = map(int, args.entry_time.split(':'))
    entry_em = h * 60 + m

    # Auto-lookup win_p from scan_picks (and show scan comparison)
    auto_result = auto_lookup_entry(sym)
    if auto_result:
        scan_price, scan_em, auto_winp, scan_ts = auto_result
        if win_p_arg is None: win_p_arg = auto_winp
        price_diff = abs(entry_price - scan_price)
        time_diff = abs(entry_em - scan_em)
        diff_notes = []
        if price_diff >= 0.005:  # half-cent tolerance
            diff_notes.append(f"price diff ${entry_price-scan_price:+.2f}")
        if time_diff > 0:
            diff_notes.append(f"time diff {entry_em-scan_em:+d}min")
        diff_str = f"  ({', '.join(diff_notes)})" if diff_notes else "  (matches scan_picks)"
        print(f"  User: ${entry_price:.2f} @ {entry_em//60:02d}:{entry_em%60:02d}  |  "
              f"scan: ${scan_price:.2f} @ {scan_em//60:02d}:{scan_em%60:02d} win_p={auto_winp:.3f}"
              f"{diff_str}")
    else:
        print(f"  User: ${entry_price:.2f} @ {entry_em//60:02d}:{entry_em%60:02d}  "
              f"(no scan_picks history, win_p default 0.7)")

    if win_p_arg is None: win_p_arg = 0.7

    if win_p_arg is None:
        win_p_arg = 0.7
    entry_mfo = entry_em - 570
    if entry_mfo < 0: entry_mfo = 5

    print(f"\n=== Exit ML Check ===")
    print(f"  Symbol:     {sym}")
    print(f"  Entry:      ${entry_price:.2f} at {entry_em//60:02d}:{entry_em%60:02d} ET (mfo={entry_mfo})")

    # Fetch bars
    print(f"  Fetching bars from intraday_bars_5m...", flush=True)
    bars, day_open = fetch_today_bars(sym)
    if not bars:
        print(f"  ❌ no bars (symbol not in DB or no recent trading)")
        sys.exit(1)
    print(f"  Got {len(bars)} bars, day_open=${day_open:.2f}")

    # Latest bar
    last_em, _, _, _, current_price = bars[-1]
    print(f"  Current:    ${current_price:.2f} at {last_em//60:02d}:{last_em%60:02d} ET")
    pnl = (current_price - entry_price) / entry_price * 100
    print(f"  PnL:        {pnl:+.2f}%")

    # Fetch entry features
    entry_pkl_feats = None
    feats_source = 'unknown'
    feats_dict = fetch_entry_features(sym, entry_em)
    if feats_dict and len(feats_dict) >= 50:
        # Build vector from dict (need feature ordering — use prod features_zone)
        prod_feats_file = PROJ / 'backtests' / 'models_prod_v22' / 'features_zone_z4.txt'
        prod_feats = [l.strip() for l in open(prod_feats_file) if l.strip()]
        entry_pkl_feats = np.array([feats_dict.get(f, 0.0) for f in prod_feats])
        feats_source = 'scan_candidates'
    else:
        # Fallback: use today's pkl row (post-entry)
        row = fetch_recent_pkl_features(sym)
        if row is not None:
            prod_feats_file = PROJ / 'backtests' / 'models_prod_v22' / 'features_zone_z4.txt'
            prod_feats = [l.strip() for l in open(prod_feats_file) if l.strip()]
            entry_pkl_feats = row[prod_feats].fillna(0).values
            feats_source = f'pkl ({row["date"]})'

    if entry_pkl_feats is None:
        print(f"  ⚠️ Cannot build entry pkl features — Exit ML inference skipped")
        print(f"  Suggestion: ensure scan_candidates has full features_json, or pkl up to date")
        sys.exit(1)

    print(f"  Features:   72 entry pkl features from {feats_source}")

    # Determine zone from entry mfo
    if entry_mfo <= 9: zone = 'Z1'
    elif entry_mfo <= 29: zone = 'Z2'
    elif entry_mfo <= 44: zone = 'Z3'
    else: zone = 'Z4'

    # Build position dict + predict
    from src.scan.ml_exit_scorer import ExitScorer
    scorer = ExitScorer()
    model_set = scorer.get_model_set_for_zone(zone)

    position = {
        'sym': sym,
        'entry_em': entry_em,
        'entry_price': entry_price,
        'entry_pkl_feats': entry_pkl_feats,
        'entry_win_p': win_p_arg,
        'entry_pred_r': args.pred_r,
        'entry_mfo': entry_mfo,
        'atr': args.atr,
    }
    print(f"  Zone: {zone} (mfo {entry_mfo}) → using {model_set} model")
    hold_prob = scorer.predict_hold_prob(zone, position, bars)
    threshold = scorer.config.get('exit_threshold', 0.35)
    min_hold = scorer.config.get('min_hold_minutes', 30)
    mins_since = last_em - entry_em

    # Peak tracking
    peak = entry_price
    for em, o, h, l, c in bars:
        if em <= entry_em: continue
        if h and h > peak: peak = h
    hwm_pnl = (peak - entry_price) / entry_price * 100
    drift = (current_price - peak) / peak * 100

    print(f"\n--- Position Context ---")
    print(f"  Mins since entry: {mins_since}")
    print(f"  Peak:             ${peak:.2f} ({hwm_pnl:+.2f}% from entry)")
    print(f"  Drift from peak:  {drift:+.2f}%")
    print(f"  Day open:         ${day_open:.2f} ({(current_price-day_open)/day_open*100:+.2f}%)")

    print(f"\n--- Exit ML Decision ---")
    print(f"  hold_prob:        {hold_prob:.4f}  (1.0 = always hold, 0.0 = always exit)")
    print(f"  threshold:        {threshold}")
    print(f"  min_hold:         {min_hold} min (current: {mins_since} min)")

    if mins_since < min_hold:
        print(f"  Decision:         🟡 HOLD (min_hold not met yet, wait {min_hold-mins_since} more min)")
    elif hold_prob < threshold:
        print(f"  Decision:         🔴 EXIT — Model says no upside expected")
        print(f"                       Suggested action: SELL @ ${current_price:.2f} (lock {pnl:+.2f}%)")
    else:
        print(f"  Decision:         🟢 HOLD — Model expects upside")
        cushion = (hold_prob - threshold) / (1 - threshold) * 100
        print(f"                       Confidence cushion: {cushion:.0f}% above threshold")

    print(f"\n  ⚠️  User decides — script only provides ML recommendation")
    print()


if __name__ == '__main__':
    main()
