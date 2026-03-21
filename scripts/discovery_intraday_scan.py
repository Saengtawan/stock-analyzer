#!/usr/bin/env python3
"""Discovery intraday re-scan — cron: 0,30 23,0,1,2,3,4 * * 1-5 BKK (= 10:00-15:30 ET).

Lightweight scan that reuses evening-fitted kernels, shorter data period (1mo),
and lite enrichment. Re-ranks evening picks + finds up to 3 new intraday picks.
"""
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('logs/discovery_intraday.log'),
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)


def _in_market_hours() -> bool:
    """Check if current time is within intraday scan window (10:00-15:30 ET)."""
    try:
        import pytz
        et = pytz.timezone('US/Eastern')
        now_et = datetime.now(et)
        hour, minute = now_et.hour, now_et.minute
        if hour < 10 or (hour >= 15 and minute > 30) or hour >= 16:
            return False
        if now_et.weekday() >= 5:  # Sat/Sun
            return False
        return True
    except Exception:
        # Fallback: always run (let the engine decide)
        return True


if __name__ == '__main__':
    if not _in_market_hours():
        print("Outside market hours (10:00-15:30 ET) — skipping intraday scan")
        sys.exit(0)

    from src.discovery.engine import get_discovery_engine

    engine = get_discovery_engine()
    new_picks = engine.run_intraday_scan()
    print(f"Intraday scan: {len(new_picks)} new picks")
    for p in new_picks:
        print(f"  {p.symbol}: score={p.layer2_score:.1f}, sector={p.sector}")
