#!/usr/bin/env bash
# bootstrap.sh — set up the FULL system on a NEW machine: code (git) + artifacts (Drive).
# Run this AFTER you have: git + rclone installed, rclone 'gdrive' remote configured.
#
# Usage on the new machine:
#   git clone git@github.com:Saengtawan/stock-analyzer-.git stock-analyzer
#   cd stock-analyzer
#   bash scripts/bootstrap.sh            # pulls models + DBs + .env from Drive
#   bash scripts/bootstrap.sh --light    # skip the 21GB trade_history (rebuild via cron)
set -uo pipefail
cd "$(dirname "$0")/.."
REMOTE="${RCLONE_REMOTE:-gdrive}"
SRC="$REMOTE:cc-stock-analyzer-backup"
LIGHT=0; [[ "${1:-}" == "--light" ]] && LIGHT=1

command -v rclone >/dev/null || { echo "❌ install rclone first: curl https://rclone.org/install.sh | sudo bash"; exit 1; }
rclone listremotes | grep -q "^${REMOTE}:" || { echo "❌ configure Drive first: rclone config (name it '$REMOTE')"; exit 1; }

mkdir -p data backtests logs data/exit_loops
echo "=== restoring artifacts from $SRC ==="

echo "[1/4] models..."
rclone copy "$SRC/models" backtests/ -P --transfers 4

echo "[2/4] small DBs..."
rclone copy "$SRC/data" data/ -P --exclude "trade_history.db" --transfers 4

if [[ $LIGHT -eq 0 ]]; then
  echo "[3/4] trade_history.db (21GB)..."
  rclone copyto "$SRC/data/trade_history.db" data/trade_history.db -P --transfers 1
else
  echo "[3/4] SKIP trade_history.db (--light). Build via cron, or re-run without --light later."
fi

echo "[4/4] .env (secrets)..."
if [[ ! -f .env ]]; then
  rclone copyto "$SRC/secret/.env" .env -P && echo "  .env restored." || echo "  ⚠️ no .env on Drive — copy .env.template -> .env and fill 49 keys"
else
  echo "  .env already exists — skipped (won't overwrite)"
fi

echo
echo "=== DONE. verify: ==="
echo "  ls backtests/models_exit_v18/   # should have sector_specialists.pkl"
echo "  ls -la data/trade_history.db    # 21GB"
echo "  systemctl --user start auto-trading.service stock-webapp.service"
echo "  + set up crontab (see data/crontab_backup_*.txt) — adjust paths if different"
