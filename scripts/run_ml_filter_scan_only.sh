#!/bin/bash
# Run ml_filter scan only — record picks to scan_journal.db (no IBKR execution).
# Cron schedule: every 5 min during 09:30-10:45 ET (= 20:30-21:45 BKK).

LOGFILE=/home/saengtawan/work/project/cc/stock-analyzer/logs/ml_filter_scan.log
mkdir -p "$(dirname $LOGFILE)"

cd /home/saengtawan/work/project/cc/stock-analyzer

echo "=== $(date) ===" >> "$LOGFILE"
/home/saengtawan/.pyenv/versions/cc/bin/python3 -m src.scan.engine ml_filter >> "$LOGFILE" 2>&1
