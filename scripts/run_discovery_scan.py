#!/usr/bin/env python3
"""Run Discovery scan from terminal — same code path as webapp.

Usage:
  python3 scripts/run_discovery_scan.py                  # evening scan
  python3 scripts/run_discovery_scan.py --mode premarket  # PM scan
  python3 scripts/run_discovery_scan.py --mode intraday   # intraday signals
  python3 scripts/run_discovery_scan.py --show             # show current picks (no scan)
"""
import argparse
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def show_picks():
    """Show current active picks from DB."""
    import sqlite3
    db = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_history.db')
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    picks = conn.execute('''
        SELECT symbol, scan_date, layer2_score, current_price, scan_price,
               sl_pct, tp1_pct, sector, council_json
        FROM discovery_picks WHERE status='active'
        ORDER BY layer2_score DESC
    ''').fetchall()

    print(f'\n=== Discovery Picks ({len(picks)}) — scan {picks[0]["scan_date"] if picks else "?"} ===\n')

    for p in picks:
        c = json.loads(p['council_json']) if p['council_json'] else {}
        strat = c.get('strategy', {}).get('strategy', '?')
        gt = c.get('strategy', {}).get('gap_type', '')
        gt_tag = f' [{gt}]' if gt else ''
        pct = ((p['current_price'] / p['scan_price']) - 1) * 100 if p['scan_price'] > 0 else 0
        print(f'  {strat:8s}{gt_tag:16s} {p["symbol"]:6s} E[R]={p["layer2_score"]:+.1f}  '
              f'${p["current_price"]:.2f} ({pct:+.1f}%)  SL={p["sl_pct"]}% TP={p["tp1_pct"]}%  {p["sector"]}')

    conn.close()


def run_evening():
    """Run evening scan via engine.py — same as webapp."""
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    picks = engine.run_scan()
    print(f'\nEvening scan done: {len(picks)} picks')
    show_picks()


def run_premarket():
    """Run PM scan via gap_scanner inside engine."""
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    macro = engine._load_macro()
    scan_date = engine._last_scan or ''
    gap_picks = engine._gap_scanner.scan(macro, scan_date, premarket_confirm=True)
    print(f'\nPM scan: {len(gap_picks)} picks')
    for p in gap_picks:
        pm = p.get('_pm_gap', 0)
        print(f'  {p["symbol"]:6s} PM gap={pm:+.1f}%  {p.get("_gap_type","")}  {p.get("_gap_reasons",[])}')
    if not gap_picks:
        print('  → 0 picks (no PM gap ≥1% or market closed)')


def run_intraday():
    """Run intraday scan via gap_scanner inside engine."""
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    signals = engine._gap_scanner.scan_intraday()
    print(f'\nIntraday signals: {len(signals)}')
    for s in signals:
        emoji = '🔴' if s['action'] == 'SHORT' else '🟢'
        print(f'  {emoji} {s["strategy"]:18s} {s["action"]:5s} {s["symbol"]:6s} '
              f'gap={s.get("gap_pct",0):+.1f}%  WR={s["backtest_wr"]}%')
        print(f'     {s["reason"]}')
    if not signals:
        print('  → 0 signals')


def main():
    parser = argparse.ArgumentParser(description='Discovery scan — same as webapp')
    parser.add_argument('--mode', choices=['evening', 'premarket', 'intraday'], default='evening')
    parser.add_argument('--show', action='store_true', help='Show current picks only (no scan)')
    args = parser.parse_args()

    if args.show:
        show_picks()
    elif args.mode == 'evening':
        run_evening()
    elif args.mode == 'premarket':
        run_premarket()
    elif args.mode == 'intraday':
        run_intraday()


if __name__ == '__main__':
    main()
