#!/usr/bin/env bash
# H12-A monthly retrain → STAGING + validate + REPORT (no auto-swap).
# Respects the project's human-checkpoint discipline: this builds + validates a
# fresh model set in a staging dir; a human reviews then runs swap_h12a.sh.
#
# Cron:  0 3 1 * *  bash scripts/monthly_retrain_h12a.sh   (1st of month, 03:00)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$HOME/.pyenv/versions/issara/bin/python"
DATE="$(date +%Y-%m-%d)"
LOG="logs/h12a_retrain_${DATE}.log"
STAGE="backtests/models_prod_v23_h12a_staging_${DATE}"
PKL="cache/bt_features/features_5yr_staging_${DATE}.pkl"
LABELS="cache/bt_features/phase0_labels_staging_${DATE}.pkl"
CELLS="configs/h12a_cell_ratings_staging_${DATE}.json"
# 840d train window ending yesterday
END="$(date -d 'yesterday' +%Y-%m-%d)"
START="$(date -d '3 years ago' +%Y-%m-%d)"

exec >>"$LOG" 2>&1
echo "===== H12-A retrain $DATE (END=$END) ====="
echo "[1/5] rebuild feature pkl..."
$PY backtests/feature_builder.py --start "$START" --end "$END" --output "$PKL" --limit 500

echo "[2/5] rebuild phase0 labels..."
PHASE0_LABELS_OUT="$LABELS" $PY scripts/rebuild_phase0_labels.py

echo "[3/5] train H12-A → staging ($STAGE)..."
mkdir -p "$STAGE"
$PY scripts/train_h12a_v2_z1.py   --pkl "$PKL" --labels-pkl "$LABELS" --out "$STAGE/Z1"  --cutoff "$END"
$PY scripts/train_h12a_vc_z234.py --pkl "$PKL" --labels-pkl "$LABELS" --out "$STAGE"     --cutoff "$END" --zones Z2,Z3,Z4

echo "[4/5] generate cell ratings → staging..."
H12A_MODELS_DIR="$STAGE" H12A_CELLS_OUT="$CELLS" $PY scripts/generate_h12a_cell_ratings.py

echo "[5/5] VALIDATE staging (verify vs spec floors)..."
set +e
H12A_MODELS_DIR="$STAGE" H12A_CELLS="$CELLS" $PY scripts/verify_h12a_full_backtest.py
RC=$?
set -e

echo ""
if [ $RC -eq 0 ]; then
  echo "✅ STAGING VALIDATED. Review log then deploy:"
  echo "    bash scripts/swap_h12a.sh $STAGE $CELLS"
else
  echo "⚠️ STAGING FAILED validation (rc=$RC) — DO NOT swap. Live H12-A untouched."
fi
echo "Staging models: $STAGE | cells: $CELLS | pkl: $PKL"
echo "===== done $DATE ====="
