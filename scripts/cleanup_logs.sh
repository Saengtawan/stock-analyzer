#!/bin/bash
# Log Cleanup - Remove logs older than 7 days
# Runs daily at 04:30 Bangkok

PROJECT_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
LOG_DIR="$PROJECT_DIR/data/logs"
STATUS_FILE="$PROJECT_DIR/data/cron_status.json"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Count before
BEFORE_COUNT=$(find "$LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
BEFORE_SIZE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

# Delete logs older than 7 days
find "$LOG_DIR" -name "*.log" -type f -mtime +7 -delete 2>/dev/null

# Count after
AFTER_COUNT=$(find "$LOG_DIR" -name "*.log" -type f 2>/dev/null | wc -l)
AFTER_SIZE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

REMOVED=$((BEFORE_COUNT - AFTER_COUNT))

echo "[$TIMESTAMP] Log cleanup: removed $REMOVED files ($BEFORE_SIZE → $AFTER_SIZE)" >> "$LOG_DIR/cleanup.log"

# Update status
python3 -c "
import json
from datetime import datetime

status_file = '$STATUS_FILE'
try:
    with open(status_file, 'r') as f:
        status = json.load(f)
except:
    status = {}

status['log_cleanup'] = {
    'last_run': datetime.now().isoformat(),
    'status': 'ok',
    'removed': $REMOVED,
    'remaining': $AFTER_COUNT,
    'size': '$AFTER_SIZE'
}

with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
"
