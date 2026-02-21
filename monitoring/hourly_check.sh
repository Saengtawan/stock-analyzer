#!/bin/bash
# Hourly market regime check (runs during market hours 9AM-4PM ET)

WORK_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
cd "$WORK_DIR"

# Check if market hours (9 AM - 4 PM ET)
# Thailand is ET+12 hours, so market hours are 21:00 - 04:00 Thailand time
HOUR=$(date +%H)
if [ "$HOUR" -ge 21 ] || [ "$HOUR" -le 4 ]; then
    python3 "$WORK_DIR/monitoring/alert_market_ready.py"
    EXIT_CODE=$?

    # If high or critical alert, log it
    if [ $EXIT_CODE -ge 1 ]; then
        echo "[$(date)] Alert triggered (code: $EXIT_CODE)" >> "$WORK_DIR/logs/alerts.log"
    fi
else
    echo "Outside market hours, skipping check"
fi
