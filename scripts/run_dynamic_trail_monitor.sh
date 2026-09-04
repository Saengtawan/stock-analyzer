#!/bin/bash
# Run dynamic trail monitor — adjust trail % per position based on profit threshold.
# Cron schedule: every 5 min during market hours

set -e
LOGFILE=/home/saengtawan/work/project/cc/stock-analyzer/logs/trail_monitor.log
mkdir -p "$(dirname $LOGFILE)"
exec >> "$LOGFILE" 2>&1

echo "=== $(date) ==="
cd /home/saengtawan/work/project/cc/stock-analyzer

# Ensure Gateway is up
/home/saengtawan/work/project/cc/stock-analyzer/scripts/ibkr_ensure_running.sh > /dev/null 2>&1

# Run trail monitor
/home/saengtawan/.pyenv/versions/cc/bin/python -m src.brokers.dynamic_trail_monitor
