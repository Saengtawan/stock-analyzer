#!/usr/bin/env python3
"""
POST-TRADE OUTCOME TRACKER v1.0 (v5.0)
=======================================
Batch job for tracking outcomes after trades and scanned signals.

Runs daily via cron or manual. Completely separate from trading engine.

Two functions:
1. track_sell_outcomes() — What happened after we sold? (7 fields per SELL)
2. track_signal_outcomes() — What happened to all scanned signals? (5 fields per signal)

Usage:
    python3 src/batch/outcome_tracker.py                  # Track both
    python3 src/batch/outcome_tracker.py --sells-only     # Track sell outcomes only
    python3 src/batch/outcome_tracker.py --signals-only   # Track signal outcomes only
    python3 src/batch/outcome_tracker.py --dry-run        # Preview without saving

Idempotent: re-running does not duplicate data (checks existing tracked IDs).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


def _get_trading_days_after(start_date: str, days_needed: int) -> List[str]:
    """Get N trading days after a date (approximation: skip weekends)."""
    from datetime import date as dt_date
    result = []
    d = datetime.strptime(start_date, '%Y-%m-%d').date()
    while len(result) < days_needed:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            result.append(d.strftime('%Y-%m-%d'))
    return result


def _fetch_price_history(symbol: str, start_date: str, end_date: str) -> Optional[Dict]:
    """Fetch OHLCV data from yfinance between dates. Returns dict with close/high/low arrays."""
    try:
        import yfinance as yf
        # Add 1 day buffer on each side
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=1)
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=2)

        df = yf.download(
            symbol,
            start=start_dt.strftime('%Y-%m-%d'),
            end=end_dt.strftime('%Y-%m-%d'),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return None

        # Handle MultiIndex columns from yf.download (single ticker)
        if hasattr(df.columns, 'levels'):
            # Find which level has 'Close' — that's the price level
            for lvl in range(df.columns.nlevels):
                if 'Close' in df.columns.get_level_values(lvl):
                    df.columns = df.columns.get_level_values(lvl)
                    break
            else:
                # Fallback: flatten to first level
                df.columns = df.columns.get_level_values(0)

        if 'Close' not in df.columns:
            return None

        return {
            'dates': [d.strftime('%Y-%m-%d') for d in df.index],
            'close': [float(x) for x in df['Close'].values],
            'high': [float(x) for x in df['High'].values],
            'low': [float(x) for x in df['Low'].values],
        }
    except Exception as e:
        print(f"  Warning: Failed to fetch {symbol}: {e}")
        return None


def _load_json_file(filepath: str) -> list:
    """Load JSON file, return empty list on error."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        return []


def _save_json_atomic(filepath: str, data):
    """Atomic write JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp = filepath + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, filepath)


# =========================================================================
# ITEM #4: Post-Sell Outcome Tracking
# =========================================================================

def track_sell_outcomes(dry_run: bool = False) -> int:
    """
    Track what happened after each SELL (did price continue up or down?).

    For each SELL entry aged 1-7 trading days:
    - Fetch daily bars for 5 trading days after sell
    - Calculate: close_1d, close_3d, close_5d, max_5d, min_5d, pnl_1d, pnl_5d

    Returns number of outcomes tracked.
    """
    print("\n=== Post-Sell Outcome Tracking ===")

    trade_log_dir = os.path.join(PROJECT_ROOT, 'trade_logs')
    outcomes_dir = os.path.join(PROJECT_ROOT, 'outcomes')
    os.makedirs(outcomes_dir, exist_ok=True)

    if not os.path.exists(trade_log_dir):
        print("  No trade_logs directory found")
        return 0

    # Load existing outcomes — only skip fully-tracked (close_5d not null)
    complete_ids = set()   # trade_ids with close_5d filled
    incomplete_ids = set() # trade_ids still missing close_5d
    for f in os.listdir(outcomes_dir):
        if f.startswith('sell_outcomes_') and f.endswith('.json'):
            for entry in _load_json_file(os.path.join(outcomes_dir, f)):
                tid = entry.get('trade_id', '')
                if entry.get('post_sell_close_5d') is not None:
                    complete_ids.add(tid)
                else:
                    incomplete_ids.add(tid)

    # Find SELL entries from last 10 days of trade logs
    sell_entries = []
    today = datetime.now()
    for days_ago in range(1, 11):
        log_date = (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        filepath = os.path.join(trade_log_dir, f'trade_log_{log_date}.json')
        if os.path.exists(filepath):
            logs = _load_json_file(filepath)
            for log in logs:
                if log.get('action') == 'SELL' and log.get('id') not in complete_ids:
                    sell_entries.append(log)

    if not sell_entries:
        print("  No untracked SELL entries found")
        return 0

    print(f"  Found {len(sell_entries)} untracked SELL entries")

    # Track outcomes
    outcomes = []
    for sell in sell_entries:
        trade_id = sell.get('id', '')
        symbol = sell.get('symbol', '')
        sell_price = sell.get('price', 0)
        sell_timestamp = sell.get('timestamp', '')

        if not symbol or not sell_price or not sell_timestamp:
            continue

        # Parse sell date
        try:
            sell_date = sell_timestamp[:10]  # YYYY-MM-DD
        except Exception:
            continue

        # Need at least 1 trading day after sell
        trading_days = _get_trading_days_after(sell_date, 5)
        if not trading_days:
            continue

        # Check if enough time has passed (at least 1 trading day)
        today_str = today.strftime('%Y-%m-%d')
        if trading_days[0] > today_str:
            continue  # Too recent

        print(f"  Tracking {symbol} (sold {sell_date} @ ${sell_price:.2f})...", end=" ")

        # Fetch price data
        history = _fetch_price_history(symbol, sell_date, trading_days[-1])
        if not history or not history['dates']:
            print("no data")
            continue

        # Use actual trading days from history (handles holidays correctly)
        post_sell_dates = [
            (d, i) for i, d in enumerate(history['dates']) if d > sell_date
        ]

        close_1d = None
        close_3d = None
        close_5d = None
        max_5d = None
        min_5d = None

        # Collect post-sell data points using real trading days
        post_sell_highs = []
        post_sell_lows = []

        for day_num, (d, idx) in enumerate(post_sell_dates[:5]):
            c = float(history['close'][idx])
            h = float(history['high'][idx])
            l = float(history['low'][idx])

            post_sell_highs.append(h)
            post_sell_lows.append(l)

            if day_num == 0:
                close_1d = c
            if day_num == 2:
                close_3d = c
            if day_num == 4:
                close_5d = c

        if post_sell_highs:
            max_5d = max(post_sell_highs)
        if post_sell_lows:
            min_5d = min(post_sell_lows)

        # Calculate P&L if we had held
        pnl_1d = round(((close_1d - sell_price) / sell_price) * 100, 2) if close_1d else None
        pnl_5d = round(((close_5d - sell_price) / sell_price) * 100, 2) if close_5d else None

        outcome = {
            "trade_id": trade_id,
            "symbol": symbol,
            "sell_date": sell_date,
            "sell_price": sell_price,
            "sell_reason": sell.get('reason', ''),
            "sell_pnl_pct": sell.get('pnl_pct'),
            "post_sell_close_1d": round(close_1d, 2) if close_1d else None,
            "post_sell_close_3d": round(close_3d, 2) if close_3d else None,
            "post_sell_close_5d": round(close_5d, 2) if close_5d else None,
            "post_sell_max_5d": round(max_5d, 2) if max_5d else None,
            "post_sell_min_5d": round(min_5d, 2) if min_5d else None,
            "post_sell_pnl_pct_1d": pnl_1d,
            "post_sell_pnl_pct_5d": pnl_5d,
            "tracked_at": datetime.now().isoformat(),
        }
        outcomes.append(outcome)

        direction = "up" if pnl_1d and pnl_1d > 0 else "down"
        print(f"1d: {pnl_1d:+.1f}% ({direction})" if pnl_1d else "partial")

    if outcomes and not dry_run:
        # Remove old incomplete entries for re-tracked trade_ids
        retracked_ids = {o['trade_id'] for o in outcomes if o['trade_id'] in incomplete_ids}
        if retracked_ids:
            for f in os.listdir(outcomes_dir):
                if f.startswith('sell_outcomes_') and f.endswith('.json'):
                    fpath = os.path.join(outcomes_dir, f)
                    entries = _load_json_file(fpath)
                    filtered = [e for e in entries if e.get('trade_id') not in retracked_ids]
                    if len(filtered) < len(entries):
                        if filtered:
                            _save_json_atomic(fpath, filtered)
                        else:
                            os.unlink(fpath)
                        print(f"  Removed {len(entries) - len(filtered)} old incomplete entries from {f}")

        outfile = os.path.join(outcomes_dir, f'sell_outcomes_{today.strftime("%Y-%m-%d")}.json')
        # Append to existing file
        existing = _load_json_file(outfile) if os.path.exists(outfile) else []
        existing.extend(outcomes)
        _save_json_atomic(outfile, existing)
        print(f"  Saved {len(outcomes)} sell outcomes to {outfile}")
    elif outcomes and dry_run:
        print(f"  [DRY RUN] Would save {len(outcomes)} sell outcomes")
        for o in outcomes[:3]:
            print(f"    {o['symbol']}: 1d={o['post_sell_pnl_pct_1d']}%, 5d={o['post_sell_pnl_pct_5d']}%")

    return len(outcomes)


# =========================================================================
# ITEM #5: Signal Outcome Tracking
# =========================================================================

def track_signal_outcomes(dry_run: bool = False) -> int:
    """
    Track what happened to all scanned signals (bought, queued, and skipped).

    For each signal aged 1-7 trading days:
    - Fetch daily bars for 5 trading days after scan
    - Calculate: outcome_1d, outcome_3d, outcome_5d, max_gain_5d, max_dd_5d

    Returns number of signal outcomes tracked.
    """
    print("\n=== Signal Outcome Tracking ===")

    scan_log_dir = os.path.join(PROJECT_ROOT, 'scan_logs')
    outcomes_dir = os.path.join(PROJECT_ROOT, 'outcomes')
    os.makedirs(outcomes_dir, exist_ok=True)

    if not os.path.exists(scan_log_dir):
        print("  No scan_logs directory found (Item #1 must run first)")
        return 0

    # Load existing signal outcomes — only skip fully-tracked (outcome_5d not null)
    complete_keys = set()
    incomplete_keys = set()
    for f in os.listdir(outcomes_dir):
        if f.startswith('signal_outcomes_') and f.endswith('.json'):
            for entry in _load_json_file(os.path.join(outcomes_dir, f)):
                key = f"{entry.get('scan_id')}_{entry.get('symbol')}_{entry.get('signal_rank', 0)}"
                if entry.get('outcome_5d') is not None:
                    complete_keys.add(key)
                else:
                    incomplete_keys.add(key)

    # Find signal entries from last 10 days of scan logs
    signals_to_track = []
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    for days_ago in range(1, 11):
        log_date = (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        filepath = os.path.join(scan_log_dir, f'scan_{log_date}.json')
        if os.path.exists(filepath):
            scans = _load_json_file(filepath)
            for scan in scans:
                scan_id = scan.get('scan_id', '')
                scan_date = scan.get('scan_timestamp', '')[:10]
                for sig in scan.get('signals', []):
                    symbol = sig.get('symbol', '')
                    sig_rank = sig.get('signal_rank', 0)
                    key = f"{scan_id}_{symbol}_{sig_rank}"
                    if key not in complete_keys and symbol:
                        signals_to_track.append({
                            'scan_id': scan_id,
                            'scan_date': scan_date,
                            'scan_type': scan.get('scan_type', ''),
                            'signal_rank': sig.get('signal_rank'),
                            'action_taken': sig.get('action_taken', ''),
                            'symbol': symbol,
                            'scan_price': sig.get('scan_price') or sig.get('price', 0),
                            'score': sig.get('score', 0),
                            'signal_source': sig.get('signal_source', ''),
                        })

    if not signals_to_track:
        print("  No untracked signals found")
        return 0

    print(f"  Found {len(signals_to_track)} untracked signals")

    # Group by symbol to minimize API calls
    symbols_data = {}
    for sig in signals_to_track:
        sym = sig['symbol']
        if sym not in symbols_data:
            symbols_data[sym] = []
        symbols_data[sym].append(sig)

    outcomes = []
    for symbol, sigs in symbols_data.items():
        # Find earliest scan date for this symbol
        earliest_date = min(s['scan_date'] for s in sigs)
        latest_date = max(s['scan_date'] for s in sigs)

        # Get trading days after earliest scan
        trading_days = _get_trading_days_after(earliest_date, 7)
        if not trading_days or trading_days[0] > today_str:
            continue

        print(f"  Fetching {symbol} ({len(sigs)} signals)...", end=" ")

        # Fetch history covering all scan dates + 5 trading days
        history = _fetch_price_history(symbol, earliest_date, trading_days[-1])
        if not history or not history['dates']:
            print("no data")
            continue

        for sig in sigs:
            scan_price = sig['scan_price']
            if not scan_price or scan_price <= 0:
                continue

            scan_date = sig['scan_date']

            # Use actual trading days from history (handles holidays correctly)
            post_scan_dates = [
                (d, i) for i, d in enumerate(history['dates']) if d > scan_date
            ]

            outcome_1d = None
            outcome_3d = None
            outcome_5d = None
            max_gain = None
            max_dd = None

            post_highs = []
            post_lows = []

            for day_num, (d, idx) in enumerate(post_scan_dates[:5]):
                c = float(history['close'][idx])
                h = float(history['high'][idx])
                l = float(history['low'][idx])

                pct = ((c - scan_price) / scan_price) * 100
                gain = ((h - scan_price) / scan_price) * 100
                dd = ((l - scan_price) / scan_price) * 100

                post_highs.append(gain)
                post_lows.append(dd)

                if day_num == 0:
                    outcome_1d = round(pct, 2)
                if day_num == 2:
                    outcome_3d = round(pct, 2)
                if day_num == 4:
                    outcome_5d = round(pct, 2)

            if post_highs:
                max_gain = round(max(post_highs), 2)
            if post_lows:
                max_dd = round(min(post_lows), 2)

            outcomes.append({
                "scan_id": sig['scan_id'],
                "scan_date": scan_date,
                "scan_type": sig['scan_type'],
                "signal_rank": sig['signal_rank'],
                "action_taken": sig['action_taken'],
                "symbol": symbol,
                "score": sig['score'],
                "signal_source": sig['signal_source'],
                "scan_price": scan_price,
                "outcome_1d": outcome_1d,
                "outcome_3d": outcome_3d,
                "outcome_5d": outcome_5d,
                "outcome_max_gain_5d": max_gain,
                "outcome_max_dd_5d": max_dd,
                "tracked_at": datetime.now().isoformat(),
            })

        print(f"tracked {len([s for s in sigs if any(o['symbol'] == symbol for o in outcomes)])} signals")

    if outcomes and not dry_run:
        # Remove old incomplete entries for re-tracked signals
        retracked_keys = set()
        for o in outcomes:
            key = f"{o['scan_id']}_{o['symbol']}_{o['signal_rank']}"
            if key in incomplete_keys:
                retracked_keys.add(key)
        if retracked_keys:
            for f in os.listdir(outcomes_dir):
                if f.startswith('signal_outcomes_') and f.endswith('.json'):
                    fpath = os.path.join(outcomes_dir, f)
                    entries = _load_json_file(fpath)
                    filtered = [e for e in entries
                                if f"{e.get('scan_id')}_{e.get('symbol')}_{e.get('signal_rank', 0)}" not in retracked_keys]
                    if len(filtered) < len(entries):
                        if filtered:
                            _save_json_atomic(fpath, filtered)
                        else:
                            os.unlink(fpath)
                        print(f"  Removed {len(entries) - len(filtered)} old incomplete signal entries from {f}")

        outfile = os.path.join(outcomes_dir, f'signal_outcomes_{today.strftime("%Y-%m-%d")}.json')
        existing = _load_json_file(outfile) if os.path.exists(outfile) else []
        existing.extend(outcomes)
        _save_json_atomic(outfile, existing)
        print(f"  Saved {len(outcomes)} signal outcomes to {outfile}")
    elif outcomes and dry_run:
        print(f"  [DRY RUN] Would save {len(outcomes)} signal outcomes")
        for o in outcomes[:3]:
            print(f"    {o['symbol']} ({o['action_taken']}): 1d={o['outcome_1d']}, 5d={o['outcome_5d']}")

    return len(outcomes)


# =========================================================================
# LOG ROTATION
# =========================================================================

def cleanup_old_files(max_age_days: int = 90):
    """Remove outcome and scan log files older than max_age_days."""
    dirs_to_clean = [
        os.path.join(PROJECT_ROOT, 'outcomes'),
        os.path.join(PROJECT_ROOT, 'scan_logs'),
    ]
    import time as _time
    cutoff = _time.time() - (max_age_days * 86400)
    removed = 0
    for d in dirs_to_clean:
        if not os.path.exists(d):
            continue
        for fname in os.listdir(d):
            if fname.endswith('.json'):
                fpath = os.path.join(d, fname)
                if os.path.getmtime(fpath) < cutoff:
                    os.unlink(fpath)
                    removed += 1
                    print(f"  Cleaned up: {os.path.join(os.path.basename(d), fname)}")
    if removed:
        print(f"  Removed {removed} files older than {max_age_days} days")
    else:
        print(f"  No files older than {max_age_days} days")


# =========================================================================
# CLI
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="Post-trade outcome tracker")
    parser.add_argument('--sells-only', action='store_true', help='Track sell outcomes only')
    parser.add_argument('--signals-only', action='store_true', help='Track signal outcomes only')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--cleanup', action='store_true', help='Remove files older than 90 days')
    parser.add_argument('--cleanup-days', type=int, default=90, help='Max age in days for cleanup')
    args = parser.parse_args()

    print("=" * 60)
    print(f"OUTCOME TRACKER v1.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if args.cleanup:
        cleanup_old_files(max_age_days=args.cleanup_days)
        return

    total = 0
    if not args.signals_only:
        total += track_sell_outcomes(dry_run=args.dry_run)
    if not args.sells_only:
        total += track_signal_outcomes(dry_run=args.dry_run)

    # Auto-cleanup after tracking
    print("\n=== Log Rotation ===")
    cleanup_old_files(max_age_days=90)

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Total outcomes tracked: {total}")
    print("=" * 60)


if __name__ == '__main__':
    main()
