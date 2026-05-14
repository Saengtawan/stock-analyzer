#!/bin/bash
# Monthly retrain ml_filter v22 — rebuild features (top 500) + train_v22 + 1m_profit
# Cron: 0 2 1 * * /path/to/monthly_retrain.sh

set -e
cd /home/saengtawan/work/project/cc/stock-analyzer

# DBUS env so `systemctl --user` works under cron
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

PYTHON=/home/saengtawan/.pyenv/versions/issara/bin/python3
LOG=logs/monthly_retrain.log
PKL=cache/bt_features/features.pkl

echo "=== Monthly retrain $(date) ===" >> $LOG

# Date range: 1y back from today
END=$(date +%Y-%m-%d)
START=$(date -d '365 days ago' +%Y-%m-%d)

mkdir -p cache/bt_features
echo "[$(date)] Rebuild features pkl (top 500, $START → $END) → $PKL..." >> $LOG
$PYTHON backtests/feature_builder.py --start $START --end $END --output $PKL --limit 500 >> $LOG 2>&1

# Symlinks for legacy consumers (train_v22 + tests reading /tmp/)
ln -sf "$(pwd)/$PKL" /tmp/bt_features_v27.pkl
ln -sf "$(pwd)/$PKL" /tmp/bt_features_v22.pkl

# Backup current models before retrain (versioning for replay)
BACKUP_DIR="backtests/models_prod_v22_$(date +%Y-%m-%d)"
if [ ! -d "$BACKUP_DIR" ]; then
    cp -r backtests/models_prod_v22 "$BACKUP_DIR"
    echo "[$(date)] Backed up 5m models → $BACKUP_DIR" >> $LOG
fi

echo "[$(date)] Train v22 + tech-specialized + multi-tf (bucket models)..." >> $LOG
$PYTHON -m backtests.train_v22 --end-date $END --train-v27-tf >> $LOG 2>&1

echo "[$(date)] Train MFO-zone models (Step 18: market labels + adaptlim)..." >> $LOG
$PYTHON scripts/train_zones.py --end-date $END --pkl $PKL >> $LOG 2>&1

# 49m bear-regime model retrain (MoE partner)
# Uses cache/bt_features_v27_500_4yr_full.pkl which spans 2022→ (49m of data).
# That pkl is built once during backfill — for now we don't auto-rebuild it.
# Skips with rc=2 if the 4yr pkl is missing or doesn't span 49m.
echo "[$(date)] Train 49m zone models (MoE bear partner)..." >> $LOG
BACKUP_49M="backtests/models_prod_v22_49m_$(date +%Y-%m-%d)"
if [ -d "backtests/models_prod_v22_49m" ] && [ ! -d "$BACKUP_49M" ]; then
    cp -r backtests/models_prod_v22_49m "$BACKUP_49M"
    echo "[$(date)] Backed up 49m models → $BACKUP_49M" >> $LOG
fi
if $PYTHON scripts/train_49m.py --end-date $END >> $LOG 2>&1; then
    echo "[$(date)] 49m retrain OK" >> $LOG
else
    rc=$?
    if [ $rc -eq 2 ]; then
        echo "[$(date)] 49m SKIPPED — 4yr pkl missing or too narrow (see log)" >> $LOG
    else
        echo "[$(date)] 49m retrain FAILED rc=$rc" >> $LOG
    fi
fi

# 1m_profit ensemble retrain (Triple Blend partner)
# Skips gracefully if cache/bt_features_500_profit_labels.pkl is stale (>45d) or missing.
# Refresh requires manual 1-min bar backfill: cache/p1_backfill.py + p2_labels_profit.py
echo "[$(date)] Train 1m_profit ensemble (Triple Blend partner)..." >> $LOG
BACKUP_1M="backtests/models_prod_v22_1m_$(date +%Y-%m-%d)"
if [ -d "backtests/models_prod_v22_1m" ] && [ ! -d "$BACKUP_1M" ]; then
    cp -r backtests/models_prod_v22_1m "$BACKUP_1M"
    echo "[$(date)] Backed up 1m models → $BACKUP_1M" >> $LOG
fi
if $PYTHON scripts/train_1m_profit.py --end-date $END >> $LOG 2>&1; then
    echo "[$(date)] 1m_profit retrain OK" >> $LOG
else
    rc=$?
    if [ $rc -eq 2 ]; then
        echo "[$(date)] 1m_profit SKIPPED — labels pkl stale or missing (see log)" >> $LOG
    else
        echo "[$(date)] 1m_profit retrain FAILED rc=$rc" >> $LOG
    fi
fi

# 2026-05-14: validate retrained models before deploying. Roll back on failure.
echo "[$(date)] Validate retrained models against WF baseline..." >> $LOG
if bash scripts/validate_retrain.sh >> $LOG 2>&1; then
    echo "[$(date)] ✅ Validation passed — restarting engine" >> $LOG
    systemctl --user restart auto-trading.service >> $LOG 2>&1 \
        || echo "[$(date)] WARN: engine restart failed" >> $LOG
else
    echo "[$(date)] ❌ Validation FAILED — rolling back zone models from $BACKUP_DIR" >> $LOG
    cp $BACKUP_DIR/lgb_*_Z*.txt backtests/models_prod_v22/ 2>/dev/null
    cp $BACKUP_DIR/lgb_adaptlim_*.txt backtests/models_prod_v22/ 2>/dev/null
    cp $BACKUP_DIR/features_zone_*.txt backtests/models_prod_v22/ 2>/dev/null
    echo "[$(date)] Rollback complete — engine NOT restarted (keep old models)" >> $LOG
fi

echo "[$(date)] DONE" >> $LOG
