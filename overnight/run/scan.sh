#!/usr/bin/env bash
# overnight/run/scan.sh — ON-DEMAND after-hours-catalyst scan (~16:15+ ET, once the AH prints land).
# Finds tonight's after-hours movers -> fresh-vs-priced context/odds -> <=3 overnight-gap candidates.
# FULLY ISOLATED: own dir, own record (data/overnight.db + overnight/forward_record.md), off any live
# trading journal. Touches NOTHING in resonance/exec_ai/swing.
#   Grade the prior night at the next open:  bash overnight/run/grade.sh
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE="${1:-$(TZ=America/New_York date +%F)}"
mkdir -p overnight/plans

PROMPT="Today (ET) is $DATE, just after the close. You are the overnight brain. Execute exactly as written.
$(sed "s/<DATE>/$DATE/g" overnight/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "overnight/plans/$DATE.txt"
echo "[overnight] scan done ($DATE) -> overnight/plans/$DATE.txt"
