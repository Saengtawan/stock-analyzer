#!/usr/bin/env bash
# Manual H12-A model swap (human checkpoint after monthly_retrain_h12a.sh).
# Backs up live, swaps staging → live, restarts, re-verifies; rolls back on fail.
#
# Usage:  bash scripts/swap_h12a.sh <staging_models_dir> <staging_cells_json>
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$HOME/.pyenv/versions/issara/bin/python"
STAGE="${1:?usage: swap_h12a.sh <staging_models_dir> <staging_cells_json>}"
CELLS="${2:?usage: swap_h12a.sh <staging_models_dir> <staging_cells_json>}"
DATE="$(date +%Y-%m-%d_%H%M)"
LIVE="backtests/models_prod_v23_h12a"
LIVE_CELLS="configs/h12a_cell_ratings.json"
BK="backtests/models_prod_v23_h12a_pre_swap_${DATE}"
BK_CELLS="configs/h12a_cell_ratings_pre_swap_${DATE}.json"

[ -d "$STAGE" ] || { echo "✗ staging dir not found: $STAGE"; exit 1; }
[ -f "$CELLS" ] || { echo "✗ staging cells not found: $CELLS"; exit 1; }

echo "1) backup live → $BK"
cp -r "$LIVE" "$BK"; cp "$LIVE_CELLS" "$BK_CELLS"

echo "2) swap staging → live"
rm -rf "$LIVE"; cp -r "$STAGE" "$LIVE"; cp "$CELLS" "$LIVE_CELLS"

echo "3) restart auto-trading.service"
systemctl --user restart auto-trading.service; sleep 4
systemctl --user is-active auto-trading.service

echo "4) post-swap verify (live)"
set +e; $PY scripts/verify_h12a_full_backtest.py; RC=$?; set -e
if [ $RC -ne 0 ]; then
  echo "⚠️ POST-SWAP VERIFY FAILED — rolling back to $BK"
  rm -rf "$LIVE"; cp -r "$BK" "$LIVE"; cp "$BK_CELLS" "$LIVE_CELLS"
  systemctl --user restart auto-trading.service
  echo "rolled back. live = pre-swap."
  exit 1
fi
echo "✅ swap complete + verified. backup: $BK"
