#!/bin/bash
# Validate freshly retrained zone models via single-month WF before deploy.
#
# Called automatically by weekly_zone_retrain.sh + monthly_retrain.sh after
# train_zones.py completes. Exit code:
#   0 = validation passed (all zones meet floor) — caller restarts engine
#   1 = validation FAILED — caller rolls back models from backup dir
#
# Standalone usage (manual check after retrain):
#   bash scripts/validate_retrain.sh

set -e
cd "$(dirname "$0")/.."

PYTHON=/home/saengtawan/.pyenv/versions/issara/bin/python3
END=$(date +%Y-%m-%d)
PKL=cache/bt_features/features.pkl

if [ ! -f "$PKL" ]; then
    echo "❌ $PKL missing — run feature_builder.py first"
    exit 1
fi

$PYTHON scripts/validate_retrain.py --end-date $END --pkl $PKL
