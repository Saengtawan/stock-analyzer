#!/bin/bash
# Run ml_filter scan + execute picks via IBKR.
# Cron schedule: every 5 min during 09:30-13:00 ET (= 20:30-00:00 BKK)

set -e
LOGFILE=/home/saengtawan/work/project/cc/stock-analyzer/logs/ml_filter_ibkr.log
mkdir -p "$(dirname $LOGFILE)"
exec >> "$LOGFILE" 2>&1

echo "=== $(date) ==="
cd /home/saengtawan/work/project/cc/stock-analyzer

# Ensure Gateway is up
/home/saengtawan/work/project/cc/stock-analyzer/scripts/ibkr_ensure_running.sh > /dev/null 2>&1

# Run scan + execute
/home/saengtawan/.pyenv/versions/cc/bin/python -m src.brokers.scan_to_ibkr
