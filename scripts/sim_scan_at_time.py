"""
Simulate ml_filter scan at arbitrary historical time.

Usage:
  python3 scripts/sim_scan_at_time.py 2026-05-26 09:48
  python3 scripts/sim_scan_at_time.py 2026-05-26 10:28

Strategy: import ml_filter FIRST (no global mock), then patch
ml_filter.datetime + base.current_et post-import. This avoids
breaking loguru and other libs that capture datetime at import.
"""
import sys
import pytz
from datetime import datetime as _real_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

ET = pytz.timezone('US/Eastern')


def main():
    if len(sys.argv) < 3:
        print("Usage: sim_scan_at_time.py YYYY-MM-DD HH:MM")
        return

    target_dt = ET.localize(_real_datetime.strptime(
        f"{sys.argv[1]} {sys.argv[2]}", "%Y-%m-%d %H:%M"
    ))
    print(f"📅 Simulating scan at: {target_dt.strftime('%Y-%m-%d %H:%M %Z')}", flush=True)

    # Import engine + strategy AFTER initial imports (NO global datetime patch)
    from scan.engine import run_scan, format_result
    from scan.strategies import ml_filter as ml_mod
    from scan.strategies.base import BaseStrategy

    # Build patched datetime class
    class _PatchedDT(_real_datetime):
        pass
    _PatchedDT.now = staticmethod(
        lambda tz=None: target_dt.astimezone(tz) if tz else target_dt.replace(tzinfo=None)
    )

    # Apply patches AFTER imports (surgical, not global)
    ml_mod.datetime = _PatchedDT
    BaseStrategy.current_et = lambda self: target_dt

    result = run_scan('ml_filter')
    print(format_result(result))


if __name__ == '__main__':
    main()
