#!/bin/bash
# swing_scan.sh — runs swing_filter strategy at market close.
# Scheduled via cron: 55 15 * * 1-5 (15:55 ET weekdays)
#
# ⚠️ DRAFT — will be activated after Phase 5/6 deploys winning config.

cd "$(dirname "$0")/.."

# Verify in time window 15:55-16:00 ET
ET_HOUR=$(TZ=America/New_York date +%H)
ET_MIN=$(TZ=America/New_York date +%M)
ET_TIME=$((10#$ET_HOUR * 60 + 10#$ET_MIN))
START_MIN=$((15 * 60 + 55))
END_MIN=$((16 * 60 + 0))

if [ $ET_TIME -lt $START_MIN ] || [ $ET_TIME -gt $END_MIN ]; then
    echo "[swing_scan] Out of window: ET $ET_HOUR:$ET_MIN (need 15:55-16:00)"
    exit 0
fi

echo "[swing_scan] ET $ET_HOUR:$ET_MIN — running swing_filter"
python3 -m src.scan.engine swing_filter
