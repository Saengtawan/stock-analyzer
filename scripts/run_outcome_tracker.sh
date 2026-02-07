#!/bin/bash
# Outcome Tracker Cron Script
# Runs after US market close to track trade outcomes

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/data/logs"

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

exit $EXIT_CODE
