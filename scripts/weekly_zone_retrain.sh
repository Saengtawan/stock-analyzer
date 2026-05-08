#!/bin/bash
# Weekly retrain — rebuild features pkl + retrain zone models only.
# Cron: 0 2 * * 0 (Sunday 02:00 UTC = market closed, no engine activity)
# Faster than full monthly (skips bucket + tech + tf retrains).

set -e
cd /home/saengtawan/work/project/cc/stock-analyzer

# DBUS env so `systemctl --user` works under cron
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

PYTHON=/home/saengtawan/.pyenv/versions/issara/bin/python3
LOG=logs/weekly_zone_retrain.log

echo "=== Weekly zone retrain $(date) ===" >> $LOG

END=$(date +%Y-%m-%d)
START=$(date -d '365 days ago' +%Y-%m-%d)

echo "[$(date)] Rebuild features pkl (top 500, $START → $END)..." >> $LOG
$PYTHON backtests/feature_builder.py --start $START --end $END --output /tmp/bt_features_v27_500.pkl --limit 500 >> $LOG 2>&1

# Backup zone models before retrain (versioning for replay)
BACKUP_DIR="backtests/models_prod_v22_zone_$(date +%Y-%m-%d)"
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    cp backtests/models_prod_v22/lgb_*_Z*.txt "$BACKUP_DIR/" 2>/dev/null
    cp backtests/models_prod_v22/features_zone_*.txt "$BACKUP_DIR/" 2>/dev/null
    echo "[$(date)] Backed up zone models → $BACKUP_DIR" >> $LOG
fi

echo "[$(date)] Retrain zone models (Z1/Z2/Z3/Z4)..." >> $LOG
$PYTHON scripts/train_zones.py --end-date $END --pkl /tmp/bt_features_v27_500.pkl >> $LOG 2>&1

echo "[$(date)] Restart engine to pick up new zone models..." >> $LOG
systemctl --user restart auto-trading.service >> $LOG 2>&1 \
    || echo "[$(date)] WARN: engine restart failed" >> $LOG

echo "[$(date)] DONE" >> $LOG
