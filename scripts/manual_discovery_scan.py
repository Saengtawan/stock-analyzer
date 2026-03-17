#!/usr/bin/env python3
"""Quick manual scan using Discovery v3 kernel + ATR/vol gates.
Usage: python scripts/manual_discovery_scan.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from discovery.engine import DiscoveryEngine

def main():
    print("=" * 70)
    print("  DISCOVERY v3 — Manual Scan")
    print("=" * 70)

    engine = DiscoveryEngine()

    # Show kernel stats
    if engine.kernel:
        stats = engine.kernel.get_stats()
        print(f"\nKernel: {stats['n_rows']} training rows, "
              f"{stats['n_dates']} dates ({stats['date_range'][0]} to {stats['date_range'][1]})")
        print(f"Global mean return: {stats['global_mean']:+.2f}%")
    else:
        print("\nWARNING: Kernel not fitted, using v2 fallback")

    print(f"Mode: {'v3 kernel' if engine._v3_enabled else 'v2 score'}")
    print(f"\nStarting scan...")

    picks = engine.run_scan()

    print(f"\n{'='*70}")
    print(f"  RESULTS: {len(picks)} picks found")
    print(f"{'='*70}")

    if not picks:
        print("  No picks passed all filters today.")
        return

    print(f"\n  {'#':<3} {'Symbol':<7} {'E[R]%':>6} {'Tier':<4} {'Price':>8} "
          f"{'TP1%':>5} {'SL%':>5} {'ATR%':>5} {'Vol':>5} {'Sector':<20}")
    print(f"  {'-'*80}")

    for i, p in enumerate(picks, 1):
        print(f"  {i:<3} {p.symbol:<7} {p.layer2_score:>+5.2f} {p.score_tier:<4} "
              f"${p.scan_price:>7.2f} {p.tp1_pct:>4.1f}% {p.sl_pct:>4.1f}% "
              f"{p.atr_pct:>4.1f}% {p.volume_ratio:>4.2f} {p.sector:<20}")

    print(f"\n  TP target: {picks[0].tp1_pct:.1f}% | SL: {picks[0].sl_pct:.1f}%")
    print(f"  TP2 (stretch): {picks[0].tp2_pct:.1f}%")


if __name__ == '__main__':
    main()
