#!/usr/bin/env bash
# scripts/radar_loop.sh — daily runner-hunt RADAR. Fired by cron at ET 10:10 (Thai 21:10), loops every
# 5 min until 12:30 ET, appends igniting flags to data/radar_log/<DATE>.txt (mechanical, NO AI, NO trades).
# Forward-tracking logger: the agent-judge of each flag is done in-session when the log is reviewed.
# Off-record, isolated — touches nothing in resonance/overnight/exec_ai/swing/rotation/runner.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer
PY=~/.pyenv/versions/cc/bin/python
D=data/radar_log

# new day -> reset the dedup + no-chase state so first-flag prices start fresh
rm -f "$D/_prev.txt" "$D/_firstflag.json"
DATE=$(TZ=America/New_York date +%F)
echo "[radar] start $(TZ=America/New_York date '+%F %H:%M ET') -> $D/$DATE.txt"

# loop 10:10 -> 12:30 ET, every 5 min
while :; do
  hm=$(TZ=America/New_York date +%H%M)
  [ "$hm" -ge 1230 ] && break
  if [ "$hm" -ge 1010 ]; then
    $PY scripts/radar_scan.py 2>/dev/null || echo "[radar] scan error $(TZ=America/New_York date +%H:%M)"
  fi
  sleep 300
done
echo "[radar] done $(TZ=America/New_York date '+%H:%M ET') -> $(wc -l < "$D/$DATE.txt" 2>/dev/null || echo 0) flags logged"
