#!/usr/bin/env python3
"""Pre-market gap scan — runs 06:00-09:30 ET.

Scans ALL stocks via Alpaca + Yahoo prepost.
Saves PM-confirmed picks to gap_pm_cache table.
Triggers Discovery rescan with PM filter active.

Cron:
  0 9 * * 1-5 cd /home/saengtawan/work/project/cc/stock-analyzer && python3 scripts/run_pm_scan.py >> logs/pm_scan.log 2>&1
  (9:00 ET Mon-Fri = 30 min before market open)
"""
import os
import sys
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

def main():
    now_et = datetime.now(ZoneInfo('America/New_York'))
    logger.info(f"PM scan starting at {now_et.strftime('%H:%M ET')}")

    # Check: is it pre-market hours?
    if now_et.hour < 4 or now_et.hour >= 10:
        logger.info("Not pre-market hours (04:00-09:30 ET) — skipping")
        return

    from discovery.engine import get_discovery_engine
    engine = get_discovery_engine()

    # Trigger scan — PM filter will activate automatically (04:00-09:30 ET)
    picks = engine.run_scan()

    gap_picks = [p for p in picks if getattr(p, 'council', {}) and
                 p.council.get('strategy', {}).get('strategy') == 'GAP']

    logger.info(f"PM scan done: {len(picks)} total picks, {len(gap_picks)} gap picks")
    for p in gap_picks:
        logger.info(f"  GAP: {p.symbol} E[R]={p.layer2_score:+.1f}")


if __name__ == '__main__':
    main()
