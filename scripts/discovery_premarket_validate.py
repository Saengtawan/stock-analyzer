#!/usr/bin/env python3
"""Discovery pre-market validation — cron: 0 22 * * 1-5 BKK (= 09:00 ET Mon-Fri).

Fetches pre-market prices for active Discovery picks and computes gap_pct.
Picks with gap >= 0% are CONFIRMED (IC=+0.229, WR 51.7% → 60.3%).
"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/discovery_premarket.log'),
        logging.StreamHandler(),
    ]
)

from src.discovery.engine import get_discovery_engine

if __name__ == '__main__':
    engine = get_discovery_engine()
    result = engine.validate_premarket()
    print(f"Pre-market validation: {result['confirmed']} confirmed, "
          f"{result['unconfirmed']} unconfirmed, {result['total']} total")
