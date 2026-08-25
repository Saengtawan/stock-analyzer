#!/usr/bin/env bash
# runner/run/scan.sh — ~10:20 ET scan: fresh-catalyst penny movers with a not-extended entry -> >+10%.
# Window moved 10:30->10:20 on 08-25: the 10:30 board was already extended (PRZO high 10:12, GRML 10:21).
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

PROMPT="Today (ET) is $DATE, it is now $NOW ET (the ~10:20 window). You are the runner brain — find
fresh-catalyst penny movers with a not-extended entry likely to trail +10% from the ~10:20 bar. Execute exactly:
$(sed -e "s/<DATE>/$DATE/g" -e "s/<STAMP>/$STAMP/g" runner/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "runner/plans/$STAMP.txt"
echo "[runner] scan done ($DATE $NOW ET) -> runner/plans/$STAMP.txt"
