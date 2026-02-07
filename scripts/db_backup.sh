#!/bin/bash
# DB Backup - Weekly backup of trade_history.db
# Runs every Sunday at 06:00 Bangkok

PROJECT_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
DATA_DIR="$PROJECT_DIR/data"
BACKUP_DIR="$DATA_DIR/backups"
LOG_FILE="$DATA_DIR/logs/db_backup.log"
STATUS_FILE="$DATA_DIR/cron_status.json"

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
DATE_SUFFIX=$(date '+%Y%m%d')

echo "[$TIMESTAMP] Starting DB backup..." >> "$LOG_FILE"

# Backup trade_history.db
if [ -f "$DATA_DIR/trade_history.db" ]; then
    cp "$DATA_DIR/trade_history.db" "$BACKUP_DIR/trade_history_$DATE_SUFFIX.db"
    echo "[$TIMESTAMP] ✅ Backed up trade_history.db" >> "$LOG_FILE"
else
    echo "[$TIMESTAMP] ⚠️ trade_history.db not found" >> "$LOG_FILE"
fi

# Keep only last 4 backups (4 weeks)
cd "$BACKUP_DIR"
ls -t trade_history_*.db 2>/dev/null | tail -n +5 | xargs -r rm
BACKUP_COUNT=$(ls trade_history_*.db 2>/dev/null | wc -l)

echo "[$TIMESTAMP] Backup complete. Total backups: $BACKUP_COUNT" >> "$LOG_FILE"

# Update cron status
python3 -c "
import json
from datetime import datetime

status_file = '$STATUS_FILE'
try:
    with open(status_file, 'r') as f:
        status = json.load(f)
except:
    status = {}

status['db_backup'] = {
    'last_run': datetime.now().isoformat(),
    'status': 'ok',
    'backup_count': $BACKUP_COUNT
}

with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
"
