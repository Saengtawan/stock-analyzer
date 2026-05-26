#!/bin/bash
# swing_scan.sh — runs swing_filter strategy.
# Recommended cron: 0 3 * * 2-6 BKK (= 16:00 ET Mon-Fri, after US market close)
# User reviews picks any time before next market open at 20:30 BKK (= 09:30 ET).

cd "$(dirname "$0")/.."

ET_DATE=$(TZ=America/New_York date +%Y-%m-%d)
ET_TIME=$(TZ=America/New_York date "+%H:%M:%S")
BKK_TIME=$(date "+%Y-%m-%d %H:%M:%S %Z")

echo ""
echo "============================================================"
echo "[swing_scan] ET $ET_DATE $ET_TIME | BKK $BKK_TIME"
echo "============================================================"

# Run swing_filter (strategy enforces post-close window itself)
python3 -m src.scan.engine swing_filter

echo "[swing_scan] Done."
