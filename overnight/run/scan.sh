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
MODE="${2:-pre}"   # pre = pre-close PREDICTION pass (buy-before, ~15:15-15:50 ET) ; post = confirm/grade
mkdir -p overnight/plans

if [ "$MODE" = "post" ]; then
  WHEN="just AFTER the close (~16:20 ET) — the CONFIRM/grade pass; the prints are landing"
else
  WHEN="BEFORE the close (~15:15-15:50 ET) — the PREDICTION pass; tonight's AH reporters have NOT printed yet, make the pre-print odds call so the user can buy before 16:00"
fi
PROMPT="Today (ET) is $DATE, $WHEN. You are the overnight brain. Execute exactly as written.
$(sed "s/<DATE>/$DATE/g" overnight/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "overnight/plans/$DATE.txt"
echo "[overnight] scan done ($DATE) -> overnight/plans/$DATE.txt"
