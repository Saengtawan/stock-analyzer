#!/bin/bash
# Pre-Filter Cron Script
# Runs evening or pre-open scan based on argument

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/data/logs"

mkdir -p "$LOG_DIR"

# Activate virtual environment if exists
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

cd "$PROJECT_DIR"

SCAN_TYPE="${1:-evening}"
LOG_FILE="$LOG_DIR/prefilter_${SCAN_TYPE}_$(date +%Y%m%d).log"

echo "========================================" >> "$LOG_FILE"
echo "Pre-Filter $SCAN_TYPE scan started at $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

python3 src/pre_filter.py "$SCAN_TYPE" >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "Scan completed with exit code $EXIT_CODE at $(date)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

exit $EXIT_CODE
