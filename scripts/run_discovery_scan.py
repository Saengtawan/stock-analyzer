#!/usr/bin/env python3
"""Run Discovery scan from terminal — same code path as webapp."""
import argparse, sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def show_picks():
    from database.orm.base import get_session
    from sqlalchemy import text
    with get_session() as session:
        picks = session.execute(text("""
            SELECT symbol, scan_date, layer2_score, current_price, scan_price,
                   sl_pct, tp1_pct, sector, council_json
            FROM discovery_picks WHERE status='active' ORDER BY layer2_score DESC
        """)).mappings().fetchall()
    print(f'\n=== Discovery Picks ({len(picks)}) ===\n')
    for p in picks:
        c = json.loads(p['council_json']) if p['council_json'] else {}
        strat = c.get('strategy', {}).get('strategy', '?')
        print(f'  {strat:8s} {p["symbol"]:6s} E[R]={p["layer2_score"]:+.1f}  {p["sector"] or ""}')

def run_evening():
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    picks = engine.run_scan()
    print(f'\nEvening scan done: {len(picks)} picks')
    show_picks()

def run_premarket():
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    macro = engine._load_macro()
    scan_date = engine._last_scan or ''
    gap_picks = engine._gap_scanner.scan(macro, scan_date, premarket_confirm=True)
    print(f'\nPM scan: {len(gap_picks)} picks')
    for p in gap_picks:
        print(f'  {p["symbol"]:6s} PM gap={p.get("_pm_gap",0):+.1f}%')

def run_intraday():
    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()
    signals = engine._gap_scanner.scan_intraday()
    print(f'\nIntraday signals: {len(signals)}')
    for s in signals:
        emoji = '🔴' if s['action'] == 'SHORT' else '🟢'
        print(f'  {emoji} {s["strategy"]:18s} {s["symbol"]:6s} WR={s["backtest_wr"]}%')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['evening', 'premarket', 'intraday'], default='evening')
    parser.add_argument('--show', action='store_true')
    args = parser.parse_args()
    if args.show: show_picks()
    elif args.mode == 'evening': run_evening()
    elif args.mode == 'premarket': run_premarket()
    elif args.mode == 'intraday': run_intraday()
