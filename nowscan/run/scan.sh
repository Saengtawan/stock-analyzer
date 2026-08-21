#!/usr/bin/env bash
# nowscan/run/scan.sh — ON-DEMAND "what would I buy RIGHT NOW, hold to close" broad free screen.
# NOT resonance (no coiled pool). Builds the field live via WebSearch, judges freely, buys at the
# CURRENT price. FULLY ISOLATED + OFF-RECORD: writes ONLY to nowscan/plans/. Touches NOTHING in
# resonance/exec_ai/swing/overnight (no journal, no db, no plans of theirs).
#   Run any time:  bash nowscan/run/scan.sh
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

NOW_ET=$(TZ=America/New_York date '+%F %H:%M')
STAMP=$(TZ=America/New_York date '+%F_%H%M')
mkdir -p nowscan/plans

# Broad free screen at the CURRENT moment — decide.md carries the full method. Substitute the live
# ET time + the output stamp so the brain knows "now" and where to write.
PROMPT="It is $NOW_ET ET (right now). You are the nowscan brain — a buy-now, hold-to-close broad screen.
Execute exactly as written below.
$(sed -e "s/<NOW_ET>/$NOW_ET ET/g" -e "s/<STAMP>/$STAMP/g" nowscan/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "nowscan/plans/$STAMP.txt"
echo "[nowscan] scan done ($NOW_ET ET) -> nowscan/plans/$STAMP.txt"
