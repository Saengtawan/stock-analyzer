#!/usr/bin/env bash
# swing/run/learn.sh — ON-DEMAND swing reflection (grade the forward record -> AI writes lessons).
# NOT on cron. Run it when you want to grade open picks (typically ~weekly, or whenever you say
# "check swing"). Mirrors resonance/run/learn.sh but fully separate: data/swing.db, swing/memory.md.
# Touches NOTHING in resonance/.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE="${1:-$(TZ=America/New_York date +%F)}"

# 1) mechanical grader: resolve open picks (target/stop/time) in data/swing.db
if ! python -m swing.lib.grade "$DATE"; then
  echo "🔴 swing grade failed for $DATE" ; exit 1
fi

# 2) AI reflection: judge resolved picks, append forward record + earn/revise lessons in swing/memory.md
if [ "${SWING_NO_AI:-0}" = "1" ]; then
  echo "[swing] graded only (SWING_NO_AI=1). memory.md not updated."
  exit 0
fi
PROMPT="Today (ET) is $DATE. You are the swing brain doing the AFTER-THE-FACT LEARN pass.
Execute the reflection exactly as written below.
$(cat swing/brain/learn.md)"
timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1
echo "[swing] learn done ($DATE) -> swing/memory.md"
