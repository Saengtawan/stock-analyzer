#!/bin/bash
# Alert Cleanup - Remove alerts older than 30 days
# Runs daily at 04:00 Bangkok

PROJECT_DIR="/home/saengtawan/work/project/cc/stock-analyzer"
DATA_DIR="$PROJECT_DIR/data"
ALERTS_FILE="$DATA_DIR/alerts.json"
LOG_FILE="$DATA_DIR/logs/cleanup.log"
STATUS_FILE="$DATA_DIR/cron_status.json"

mkdir -p "$(dirname "$LOG_FILE")"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ ! -f "$ALERTS_FILE" ]; then
    echo "[$TIMESTAMP] No alerts.json found" >> "$LOG_FILE"
    exit 0
fi

# Clean old alerts using Python
python3 -c "
import json
from datetime import datetime, timedelta

alerts_file = '$ALERTS_FILE'
status_file = '$STATUS_FILE'
max_age_days = 30

try:
    with open(alerts_file, 'r') as f:
        data = json.load(f)

    alerts = data.get('alerts', [])
    cutoff = datetime.now() - timedelta(days=max_age_days)

    # Filter alerts newer than cutoff
    new_alerts = []
    for alert in alerts:
        try:
            alert_time = datetime.fromisoformat(alert.get('timestamp', ''))
            if alert_time > cutoff:
                new_alerts.append(alert)
        except:
            new_alerts.append(alert)  # Keep if can't parse

    removed = len(alerts) - len(new_alerts)
    data['alerts'] = new_alerts

    with open(alerts_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'Removed {removed} old alerts, kept {len(new_alerts)}')

    # Update status
    try:
        with open(status_file, 'r') as f:
            status = json.load(f)
    except:
        status = {}

    status['alert_cleanup'] = {
        'last_run': datetime.now().isoformat(),
        'status': 'ok',
        'removed': removed,
        'remaining': len(new_alerts)
    }

    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)

except Exception as e:
    print(f'Error: {e}')
" >> "$LOG_FILE" 2>&1

echo "[$TIMESTAMP] Alert cleanup complete" >> "$LOG_FILE"
