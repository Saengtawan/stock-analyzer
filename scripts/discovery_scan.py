#!/usr/bin/env python3
"""Discovery Engine — daily scan runner (cron: 0 9 * * 2-6 BKK = 20:00 ET)."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/discovery_scan.log'),
        logging.StreamHandler(),
    ]
)

from src.discovery.engine import get_discovery_engine

if __name__ == '__main__':
    engine = get_discovery_engine()
    picks = engine.run_scan()
    print(f"Discovery scan complete: {len(picks)} picks")
    for p in picks:
        print(f"  {p.symbol}: score={p.layer2_score:.1f}, SL={p.sl_pct:.1f}%, TP1={p.tp1_pct:.1f}%")
