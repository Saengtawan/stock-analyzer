#!/bin/bash
#
# Log Cleanup & Compression Script
# Part of Phase 1: Log Management
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
RETENTION_DAYS=7

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Log Cleanup & Compression"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Log Directory: $LOG_DIR"
echo "Retention: $RETENTION_DAYS days"
echo ""

# Step 1: Compress large log files (>5MB)
echo "[1/4] Compressing large log files (>5MB)..."
find "$LOG_DIR" -name "*.log" -size +5M -type f 2>/dev/null | while read -r logfile; do
    if [ -f "$logfile" ]; then
        echo "  Compressing: $(basename "$logfile") ($(du -h "$logfile" | cut -f1))"
        gzip -9 "$logfile" 2>/dev/null || true
    fi
done
echo "  ✓ Compressed large files"
echo ""

# Step 2: Delete old compressed logs (>7 days)
echo "[2/4] Deleting old compressed logs (>$RETENTION_DAYS days)..."
find "$LOG_DIR" -name "*.log.gz" -mtime +$RETENTION_DAYS -type f -delete 2>/dev/null || true
find "$LOG_DIR" -name "*.zip" -mtime +$RETENTION_DAYS -type f -delete 2>/dev/null || true
echo "  ✓ Deleted old compressed files"
echo ""

# Step 3: Delete old uncompressed logs (>7 days)
echo "[3/4] Deleting old uncompressed logs (>$RETENTION_DAYS days)..."
find "$LOG_DIR" -name "*.log" -mtime +$RETENTION_DAYS -type f ! -name "app_$(date +%Y-%m-%d).log" -delete 2>/dev/null || true
echo "  ✓ Deleted old log files"
echo ""

# Step 4: Clean up root directory log files
echo "[4/4] Cleaning up root directory log files..."
cd "$PROJECT_ROOT"
shopt -s nullglob
for logfile in *.log; do
    if [ -f "$logfile" ]; then
        echo "  Moving: $logfile → logs/"
        gzip -c "$logfile" > "$LOG_DIR/${logfile}.gz" 2>/dev/null || true
        rm "$logfile" 2>/dev/null || true
    fi
done
shopt -u nullglob
echo "  ✓ Cleaned up root log files"
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Current log directory size:"
du -sh "$LOG_DIR"
echo ""
echo "Recent log files:"
ls -lht "$LOG_DIR" | head -10
echo ""
echo "✓ Log cleanup completed successfully"

# Update cron_status.json
STATUS_FILE="$PROJECT_ROOT/data/cron_status.json"
LOG_SIZE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
REMOVED_COUNT=$(find "$LOG_DIR" -name "*.log.gz" -mtime +$RETENTION_DAYS -type f 2>/dev/null | wc -l)
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
    'removed': int('$REMOVED_COUNT'),
    'remaining': None,
    'size': '$LOG_SIZE',
}

with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)

print('  cron_status.json updated')
"
