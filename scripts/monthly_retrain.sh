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

echo "[$(date)] Train MFO-zone models (Step 18: market labels + adaptlim)..." >> $LOG
$PYTHON scripts/train_zones.py --end-date $END --pkl $PKL >> $LOG 2>&1

# 2026-05-14 Step 19: bucket / 49m / 1m_profit training removed.
# - USE_ZONES=True (always loads zone models, never falls back to bucket)
# - USE_MOE=False (49m never blended in)
# - USE_ENSEMBLE_1M=False (1m_profit never blended in)
# All three were taking ~25 min of cron time but their output was unused.
# To re-enable: uncomment below + flip the corresponding USE_* in ml_scorer.py.
#
# $PYTHON -m backtests.train_v22 --end-date $END --train-v27-tf  # bucket + tech_0930 + multi-tf
# $PYTHON scripts/train_49m.py --end-date $END                    # MoE bear partner
# $PYTHON scripts/train_1m_profit.py --end-date $END              # 1m ensemble

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
