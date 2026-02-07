#!/bin/bash
# Health Check - Ensure run_app.py is running
# Runs every 5 minutes via cron

PROJECT_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
LOG_FILE="$PROJECT_DIR/data/logs/health_check.log"
STATUS_FILE="$PROJECT_DIR/data/cron_status.json"
APP_LOG="/tmp/app.log"

mkdir -p "$(dirname "$LOG_FILE")"

# Check if run_app.py is running
RUNNING=$(pgrep -f "python3 src/run_app.py" | wc -l)

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$RUNNING" -eq 0 ]; then
    echo "[$TIMESTAMP] ❌ run_app.py NOT running - restarting..." >> "$LOG_FILE"

    cd "$PROJECT_DIR"

    # Activate venv if exists
    if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
        source "$PROJECT_DIR/venv/bin/activate"
    fi

    # Start app
    nohup python3 src/run_app.py > "$APP_LOG" 2>&1 &

    sleep 5

    # Verify restart
    NEW_RUNNING=$(pgrep -f "python3 src/run_app.py" | wc -l)
    if [ "$NEW_RUNNING" -gt 0 ]; then
        echo "[$TIMESTAMP] ✅ run_app.py restarted successfully" >> "$LOG_FILE"
    else
        echo "[$TIMESTAMP] ❌ FAILED to restart run_app.py!" >> "$LOG_FILE"
    fi
else
    # Just update status, don't log every check
    :
fi

# Update cron status file
python3 -c "
import json
import os
from datetime import datetime

status_file = '$STATUS_FILE'
try:
    with open(status_file, 'r') as f:
        status = json.load(f)
except:
    status = {}

status['health_check'] = {
    'last_run': datetime.now().isoformat(),
    'status': 'ok' if $RUNNING > 0 else 'restarted',
    'app_running': $RUNNING > 0
}

with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
"
