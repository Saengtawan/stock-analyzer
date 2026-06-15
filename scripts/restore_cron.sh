#!/usr/bin/env bash
# restore_cron.sh — install the crontab on a NEW machine, adjusting hardcoded paths.
# The committed deploy/crontab.txt has the original machine's absolute paths
# (/home/saengtawan/work/project/cc/stock-analyzer + /home/saengtawan/.pyenv...).
# This rewrites them to THIS machine's project dir + $HOME, then installs.
#
# Usage:  bash scripts/restore_cron.sh           # dry-run (prints adjusted crontab)
#         bash scripts/restore_cron.sh --install  # actually install (overwrites crontab!)
set -uo pipefail
cd "$(dirname "$0")/.."
PROJ="$(pwd -P)"
SRC="deploy/crontab.txt"
OLD_PROJ="/home/saengtawan/work/project/cc/stock-analyzer"
OLD_HOME="/home/saengtawan"
[[ -f "$SRC" ]] || { echo "❌ $SRC not found (is this a full clone?)"; exit 1; }

ADJ="$(sed -e "s#${OLD_PROJ}#${PROJ}#g" -e "s#${OLD_HOME}#${HOME}#g" "$SRC")"

echo "=== dependency check ==="
ok=1
command -v rclone >/dev/null && echo "  ✓ rclone" || { echo "  ✗ rclone (backup crons need it)"; ok=0; }
for env in issara cc; do
  [[ -x "$HOME/.pyenv/versions/$env/bin/python" ]] && echo "  ✓ pyenv:$env" \
    || { echo "  ✗ pyenv env '$env' missing → pyenv install 3.11.8 + pip install -r deploy/requirements_$env.txt"; ok=0; }
done
for svc in auto-trading stock-webapp; do
  [[ -f "$HOME/.config/systemd/user/$svc.service" ]] && echo "  ✓ systemd:$svc" \
    || echo "  ✗ systemd '$svc' → cp deploy/systemd/$svc.service ~/.config/systemd/user/ (adjust paths) + systemctl --user daemon-reload"
done
[[ "$PROJ" != "$OLD_PROJ" ]] && echo "  ℹ project path differs → paths rewritten to $PROJ"
[[ "$HOME" != "$OLD_HOME" ]] && echo "  ℹ home differs → rewritten to $HOME"

if [[ "${1:-}" == "--install" ]]; then
  crontab -l > "data/crontab_backup_preinstall_$(date +%Y%m%d_%H%M).txt" 2>/dev/null || true
  echo "$ADJ" | crontab -
  echo "=== ✓ installed. verify: crontab -l | grep -v '^#' | head ==="
  [[ $ok -eq 0 ]] && echo "⚠️  some deps missing above — those cron jobs will fail until fixed."
else
  echo
  echo "=== DRY-RUN (adjusted crontab, first 8 active lines) ==="
  echo "$ADJ" | grep -vE '^#|^$' | head -8
  echo "..."
  echo "→ run with --install to apply (backs up existing crontab first)"
fi
