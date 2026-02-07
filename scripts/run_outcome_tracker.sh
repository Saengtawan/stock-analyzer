#!/bin/bash
# Outcome Tracker Cron Script
# Runs after US market close to track trade outcomes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/data/logs"
STATUS_FILE="$PROJECT_DIR/data/cron_status.json"

mkdir -p "$LOG_DIR"

# Activate virtual environment if exists
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

cd "$PROJECT_DIR"

LOG_FILE="$LOG_DIR/outcome_tracker_$(date +%Y%m%d).log"

echo "========================================" >> "$LOG_FILE"
echo "Outcome Tracker started at $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

python3 src/batch/outcome_tracker.py >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "Completed with exit code $EXIT_CODE at $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Update cron status
python3 -c "
import json
from datetime import datetime

status_file = '$STATUS_FILE'
exit_code = $EXIT_CODE

try:
    with open(status_file, 'r') as f:
        status = json.load(f)
except:
    status = {}

status['outcome_tracker'] = {
    'last_run': datetime.now().isoformat(),
    'status': 'ok' if exit_code == 0 else 'error',
    'exit_code': exit_code
}

with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
"

exit $EXIT_CODE
