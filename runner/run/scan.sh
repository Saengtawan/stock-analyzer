#!/usr/bin/env bash
# runner/run/scan.sh — ~10:30 ET confirm scan: penny top-gainers that CLOSE up >+10%.
# The edge is TIMING: direction is a coin flip at the 09:30 open but has resolved + persists by ~10:30.
# FULLY ISOLATED + OFF-RECORD: writes ONLY runner/plans/ + data/runner.db. Touches NOTHING in
# resonance/overnight/exec_ai/swing/rotation.
#   Grade at the close:  bash runner/run/grade.sh
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
NOW=$(TZ=America/New_York date '+%H:%M')
STAMP="${DATE}_$(TZ=America/New_York date '+%H%M')"
mkdir -p runner/plans

PROMPT="Today (ET) is $DATE, it is now $NOW ET (the ~10:30 confirm window). You are the runner brain —
scan the confirmed penny top-gainers and predict which CLOSE up >+10% on the day. Execute exactly:
$(sed -e "s/<DATE>/$DATE/g" -e "s/<STAMP>/$STAMP/g" runner/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "runner/plans/$STAMP.txt"
echo "[runner] scan done ($DATE $NOW ET) -> runner/plans/$STAMP.txt"
