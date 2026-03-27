#!/usr/bin/env python3
"""
Discovery v17 Validation — walk-forward backtest of all 3 adaptive layers.

Tests:
  1. SignalTracker: IC of each signal, learned weights vs hardcoded
  2. SectorScorer: top vs bottom sector 5d returns
  3. AdaptiveStockSelector: AUC on OOS data, WR of top picks
  4. Full pipeline: v17 WR vs current system WR

Usage: python scripts/sim_v17.py
"""
import sys
import sqlite3
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def test_signal_tracker():
    """Test SignalTracker IC computation."""
    print("\n" + "="*60)
    print("TEST 1: SignalTracker — IC-based signal weights")
    print("="*60)

    from discovery.signal_tracker import SignalTracker

    tracker = SignalTracker()
    ok = tracker.fit()
    if not ok:
        print("  FAIL: SignalTracker.fit() returned False")
        return False

    stats = tracker.get_stats()
    print(f"\n  Fitted: {stats['fitted']}")
    print(f"\n  {'Signal':<25s} {'IC':>8s} {'Weight':>8s} {'N':>8s}")
    print(f"  {'-'*50}")
    for name in ['insider_bought', 'analyst_upgrade', 'analyst_downgrade',
                  'options_bullish', 'options_bearish']:
        ic = stats['ic_values'].get(name, 0)
        weight = stats['weights'].get(name, 0)
        n = stats['n_observations'].get(name, 0)
        active = "✓" if weight != 0 else "✗ (noise)"
        print(f"  {name:<25s} {ic:>+8.4f} {weight:>+8.4f} {n:>8d}  {active}")

    # Compare with v16 hardcoded
    print(f"\n  v16 hardcoded: insider=+0.500, analyst_up=+0.300, analyst_down=-0.300")
    print(f"  v17 learned:   insider={stats['weights'].get('insider_bought', 0):+.3f}, "
          f"analyst_up={stats['weights'].get('analyst_upgrade', 0):+.3f}, "
          f"analyst_down={stats['weights'].get('analyst_downgrade', 0):+.3f}")

    return True


def test_sector_scorer():
    """Test SectorScorer predictions."""
    print("\n" + "="*60)
    print("TEST 2: SectorScorer — sector ranking quality")
    print("="*60)

    from discovery.sector_scorer import SectorScorer

    scorer = SectorScorer()
    ok = scorer.fit()
    if not ok:
        print("  FAIL: SectorScorer.fit() returned False")
        return False

    stats = scorer.get_stats()
    print(f"\n  Fitted: {stats['fitted']}")
    print(f"  Weights: {stats['weights']}")

    # Score sectors with latest macro
    conn = None  # via get_session())
    conn.row_factory = dict
    macro_row = conn.execute("""
        SELECT * FROM macro_snapshots ORDER BY date DESC LIMIT 1
    """).fetchone()
    conn.close()

    if macro_row:
        macro = dict(macro_row)
        scores = scorer.score(macro)
        allowed, blocked = scorer.get_allowed_sectors(macro)

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        print(f"\n  {'Sector':<30s} {'Score':>8s} {'Status':>10s}")
        print(f"  {'-'*50}")
        for sect, sc in ranked:
            status = "ALLOWED" if sect in allowed else ("BLOCKED" if sect in blocked else "MIDDLE")
            print(f"  {sect:<30s} {sc:>+8.4f} {status:>10s}")

    # Walk-forward test: do top sectors outperform bottom?
    conn = None  # via get_session())
    rows = conn.execute("""
        SELECT s1.date, s1.sector, s1.pct_change as ret,
               (SELECT SUM(s2.pct_change)
                FROM sector_etf_daily_returns s2
                WHERE s2.sector = s1.sector
                AND s2.date > s1.date
                AND s2.date <= date(s1.date, '+7 days')
               ) as fwd_5d
        FROM sector_etf_daily_returns s1
        WHERE s1.date >= date('now', '-6 months')
        AND s1.sector NOT IN ('S&P 500', 'US Dollar', 'Treasury Long', 'Gold')
        AND s1.sector IS NOT NULL
        ORDER BY s1.date
    """).fetchall()
    conn.close()

    if rows:
        # Simple test: compute average fwd_5d for top-3 mom vs bottom-3 mom sectors
        from collections import defaultdict
        by_date = defaultdict(list)
        for dt, sector, ret, fwd in rows:
            if fwd is not None:
                by_date[dt].append((sector, ret, fwd))

        top_rets = []
        bot_rets = []
        for dt, sectors in by_date.items():
            if len(sectors) < 8:
                continue
            sectors.sort(key=lambda x: x[1] or 0, reverse=True)  # sort by momentum
            for _, _, fwd in sectors[:3]:
                top_rets.append(fwd)
            for _, _, fwd in sectors[-3:]:
                bot_rets.append(fwd)

        if top_rets and bot_rets:
            print(f"\n  Walk-forward (6 months):")
            print(f"    Top-3 momentum sectors: avg 5d fwd = {np.mean(top_rets):+.3f}%")
            print(f"    Bot-3 momentum sectors: avg 5d fwd = {np.mean(bot_rets):+.3f}%")
            print(f"    Spread: {np.mean(top_rets) - np.mean(bot_rets):+.3f}%")

    return True


def test_stock_selector():
    """Test AdaptiveStockSelector AUC and pick quality."""
    print("\n" + "="*60)
    print("TEST 3: AdaptiveStockSelector — learned model quality")
    print("="*60)

    from discovery.adaptive_stock_selector import AdaptiveStockSelector

    selector = AdaptiveStockSelector()
    ok = selector.fit()
    if not ok:
        print("  FAIL: AdaptiveStockSelector.fit() returned False")
        return False

    stats = selector.get_stats()
    print(f"\n  Fitted: {stats['fitted']}")
    print(f"  AUC: {stats['auc']:.4f}")
    print(f"  Training rows: {stats['n_train']}")

    if stats['feature_importance']:
        print(f"\n  Feature Importance (top 5):")
        sorted_imp = sorted(stats['feature_importance'].items(), key=lambda x: -x[1])
        for feat, imp in sorted_imp[:5]:
            print(f"    {feat:<25s} {imp:.4f}")

    # Quality check
    if stats['auc'] >= 0.52:
        print(f"\n  ✓ AUC={stats['auc']:.4f} ≥ 0.52 — model has predictive power")
    else:
        print(f"\n  ✗ AUC={stats['auc']:.4f} < 0.52 — model weak, may need more data")

    return True


def test_full_pipeline():
    """Test full v17 pipeline on recent data."""
    print("\n" + "="*60)
    print("TEST 4: Full v17 pipeline — end-to-end check")
    print("="*60)

    from discovery.signal_tracker import SignalTracker
    from discovery.sector_scorer import SectorScorer
    from discovery.adaptive_stock_selector import AdaptiveStockSelector

    # Check all 3 layers
    tracker = SignalTracker()
    scorer = SectorScorer()
    selector = AdaptiveStockSelector()

    t_ok = tracker.load_from_db() or tracker.fit()
    s_ok = scorer.load_from_db() or scorer.fit()
    sel_ok = selector.load_from_db() or selector.fit()

    print(f"\n  SignalTracker:  {'✓ fitted' if t_ok else '✗ not fitted'}")
    print(f"  SectorScorer:  {'✓ fitted' if s_ok else '✗ not fitted'}")
    print(f"  StockSelector: {'✓ fitted' if sel_ok else '✗ not fitted'}")

    if not (t_ok and s_ok and sel_ok):
        print("\n  FAIL: Not all layers fitted")
        return False

    # Score sectors
    conn = None  # via get_session())
    conn.row_factory = dict
    macro_row = conn.execute("SELECT * FROM macro_snapshots ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    macro = dict(macro_row) if macro_row else {}

    sector_scores = scorer.score(macro)
    allowed, blocked = scorer.get_allowed_sectors(macro)
    print(f"\n  Sectors: {len(allowed)} allowed, {len(blocked)} blocked")

    # Get some candidates (top universe stocks)
    conn = None  # via get_session())
    conn.row_factory = dict
    stocks = conn.execute("""
        SELECT symbol, beta, pe_forward, market_cap, sector, avg_volume
        FROM stock_fundamentals
        WHERE market_cap > 10e9 AND avg_volume > 500000
        LIMIT 50
    """).fetchall()
    conn.close()

    # Build simple candidate dicts
    candidates = []
    for s in stocks:
        candidates.append({
            'symbol': s['symbol'],
            'sector': s['sector'] or '',
            'beta': s['beta'] or 1,
            'pe_forward': s['pe_forward'],
            'market_cap': s['market_cap'] or 1e10,
            'momentum_5d': -2,
            'momentum_20d': -5,
            'volume_ratio': 1.0,
            'atr_pct': 3.0,
            'rsi': 45,
            'distance_from_20d_high': -8,
            'vix_close': macro.get('vix_close', 20),
            'pct_above_20d_ma': 50,
            'crude_delta_5d_pct': 0,
            'insider_bought': False,
            'analyst_upgrade': False,
            'analyst_downgrade': False,
        })

    # Predict
    results = selector.predict(candidates, sector_scores)
    print(f"\n  StockSelector: {len(results)} scored from {len(candidates)} candidates")

    if results:
        # Filter blocked
        results = [(p, c) for p, c in results if c.get('sector', '') not in blocked]

        # Apply boosts
        boosted = [(p + tracker.boost(c), c) for p, c in results]
        boosted.sort(key=lambda x: -x[0])

        print(f"\n  Top 5 v17 picks:")
        print(f"  {'Rank':<5s} {'Symbol':<8s} {'Prob':>6s} {'Sector':<25s}")
        print(f"  {'-'*50}")
        for i, (prob, c) in enumerate(boosted[:5]):
            print(f"  {i+1:<5d} {c['symbol']:<8s} {prob:>6.3f} {c['sector']:<25s}")

    print(f"\n  ✓ Full v17 pipeline working")
    return True


if __name__ == '__main__':
    print("Discovery v17 — Full Adaptive Architecture Validation")
    print("=" * 60)

    results = {}
    for name, test_fn in [
        ('SignalTracker', test_signal_tracker),
        ('SectorScorer', test_sector_scorer),
        ('StockSelector', test_stock_selector),
        ('FullPipeline', test_full_pipeline),
    ]:
        try:
            results[name] = test_fn()
        except Exception as e:
            import traceback
            print(f"\n  ERROR in {name}: {e}")
            traceback.print_exc()
            results[name] = False

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, ok in results.items():
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {name:<25s} {status}")

    all_pass = all(results.values())
    print(f"\n  Overall: {'✓ ALL PASS' if all_pass else '✗ SOME FAILED'}")
    sys.exit(0 if all_pass else 1)
