#!/usr/bin/env bash
# backup_to_drive.sh — push the non-git artifacts (models + DBs + .env) to Google Drive.
# Code lives in git (github/gitlab); this covers what .gitignore excludes.
# Prereqs: rclone installed + a remote configured (default name 'gdrive').
# Usage:  bash scripts/backup_to_drive.sh            # full (incl 21GB trade_history)
#         bash scripts/backup_to_drive.sh --light    # skip trade_history.db (the 21GB one)
# Cron (weekly Sun 21:00 BKK):  0 21 * * 0 cd <proj> && bash scripts/backup_to_drive.sh >> logs/backup_drive.log 2>&1
set -uo pipefail
cd "$(dirname "$0")/.."
REMOTE="${RCLONE_REMOTE:-gdrive}"
DEST="$REMOTE:cc-stock-analyzer-backup"
LIGHT=0; [[ "${1:-}" == "--light" ]] && LIGHT=1

command -v rclone >/dev/null || { echo "❌ rclone not installed"; exit 1; }
rclone listremotes | grep -q "^${REMOTE}:" || { echo "❌ remote '$REMOTE' not configured (run: rclone config)"; exit 1; }

echo "=== backup -> $DEST  ($(date '+%F %T')) ==="

# 1. models (pkl + spec) — gitignored, ~200MB
echo "[1/4] models..."
rclone copy backtests/models_exit_v18  "$DEST/models/models_exit_v18"  -P --transfers 4
rclone copy backtests/models_prod_v23_h12a "$DEST/models/models_prod_v23_h12a" -P --transfers 4
rclone copy backtests/models_exit_v17c "$DEST/models/models_exit_v17c" -P --transfers 4 2>/dev/null || true

# 2. small DBs (journals + state) — daily-changing, small
echo "[2/4] small DBs..."
for db in scan_journal.db exit_ml_journal.db stock_analyzer.db; do
  [[ -f "data/$db" ]] && rclone copyto "data/$db" "$DEST/data/$db" -P
done

# 3. big DB (trade_history 21GB) — unless --light
if [[ $LIGHT -eq 0 ]]; then
  echo "[3/4] trade_history.db (21GB — may take a while)..."
  rclone copyto data/trade_history.db "$DEST/data/trade_history.db" -P --transfers 1
else
  echo "[3/4] SKIP trade_history.db (--light); rebuild on new machine via cron"
fi

# 4. .env (secrets) — to YOUR OWN private Drive only. Comment out if you prefer manual.
echo "[4/4] .env (secrets -> private Drive)..."
rclone copyto .env "$DEST/secret/.env" -P

echo "=== done $(date '+%F %T') ==="
