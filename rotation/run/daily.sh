#!/usr/bin/env bash
# rotation/run/daily.sh — POST-CLOSE daily pass (~16:10 ET / 03:10 BKK).
#   (a) MECHANICAL, 0 tokens: build today's cross-asset snapshot -> data/rotation.db
#   (b) LEARN, 1 AI call: grade the prior session's "tomorrow" calls -> update rotation/memory.md
#   (c) DECIDE, 1 AI call: predict tomorrow/week/regime -> rotation/plans/<DATE>.json + DB
# FULLY ISOLATED + OFF-RECORD: writes only data/rotation.db + rotation/*. Touches NOTHING in
# resonance/overnight/exec_ai/swing. It is a forecaster, not a trader.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
mkdir -p rotation/plans

# --- (a) MECHANICAL cross-asset snapshot (zero AI tokens) ---
python -m rotation.data.snapshot "$DATE" || echo "🟠 [rotation] snapshot degraded ($DATE)"

# --- (b) LEARN: grade the prior session's calls, update linkage memory ---
LEARN_PROMPT="Today (ET) is $DATE, post-close. You are the rotation LEARN pass. Grade the prior
session's forecasts against today's completed tape and update the linkage memory. Execute exactly:
$(sed "s/<DATE>/$DATE/g; s/<TODAY>/$DATE/g" rotation/brain/learn.md)"
timeout 900 claude -p "$LEARN_PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tail -20

# --- (c) DECIDE: predict tomorrow/week/regime ---
DECIDE_PROMPT="Today (ET) is $DATE, post-close. You are the rotation DECIDE pass. Predict the next
session / this week / the regime. Execute exactly:
$(sed "s/<DATE>/$DATE/g" rotation/brain/decide.md)"
timeout 900 claude -p "$DECIDE_PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "rotation/plans/$DATE.txt"

echo "[rotation] daily pass done ($DATE) -> rotation/plans/$DATE.json (+ .txt receipt)"
