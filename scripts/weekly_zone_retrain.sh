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
PKL=cache/bt_features/features.pkl

echo "=== Weekly zone retrain $(date) ===" >> $LOG

END=$(date +%Y-%m-%d)
START=$(date -d '365 days ago' +%Y-%m-%d)

mkdir -p cache/bt_features
echo "[$(date)] Rebuild features pkl (top 500, $START → $END) → $PKL..." >> $LOG
$PYTHON backtests/feature_builder.py --start $START --end $END --output $PKL --limit 500 >> $LOG 2>&1

# Backup zone models before retrain (versioning for replay)
BACKUP_DIR="backtests/models_prod_v22_zone_$(date +%Y-%m-%d)"
if [ ! -d "$BACKUP_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    cp backtests/models_prod_v22/lgb_*_Z*.txt "$BACKUP_DIR/" 2>/dev/null
    cp backtests/models_prod_v22/features_zone_*.txt "$BACKUP_DIR/" 2>/dev/null
    echo "[$(date)] Backed up zone models → $BACKUP_DIR" >> $LOG
fi

echo "[$(date)] Retrain zone models (Step 18: market labels + adaptlim + per-zone HP)..." >> $LOG
$PYTHON scripts/train_zones.py --end-date $END --pkl $PKL >> $LOG 2>&1

# 2026-05-14: validate new models before deploying. Roll back on failure.
echo "[$(date)] Validate retrained models against WF baseline..." >> $LOG
if bash scripts/validate_retrain.sh >> $LOG 2>&1; then
    echo "[$(date)] ✅ Validation passed — restarting engine" >> $LOG
    systemctl --user restart auto-trading.service >> $LOG 2>&1 \
        || echo "[$(date)] WARN: engine restart failed" >> $LOG
else
    echo "[$(date)] ❌ Validation FAILED — rolling back from $BACKUP_DIR" >> $LOG
    cp $BACKUP_DIR/lgb_*.txt backtests/models_prod_v22/ 2>/dev/null
    cp $BACKUP_DIR/features_zone_*.txt backtests/models_prod_v22/ 2>/dev/null
    echo "[$(date)] Rollback complete — engine NOT restarted (keep old models)" >> $LOG
fi

echo "[$(date)] DONE" >> $LOG
