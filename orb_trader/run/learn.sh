#!/usr/bin/env bash
# orb_trader / run / learn.sh — cron ④ AFTER-CLOSE LEARN (16:30 ET / 03:30 BKK next day)
# Fills real 09:35->close outcomes, then the brain appends one forward line to orb_trader/memory.md.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/issara/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
ALERT="logs/ai_trader_ALERT.log"
PROMPT="Today (ET) is $DATE. You are the orb_trader brain. Execute PASS ④ (after-close reflection) exactly as written below.

$(sed "s/DATE/$DATE/g" orb_trader/brain/learn.md)"

# No decision today = nothing traded; still fine (a full-abstain day needs no learn write).
if [ ! -f "orb_trader/plans/$DATE.decision.json" ] && [ ! -f "orb_trader/plans/$DATE.plan.json" ]; then
  echo "[$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader learn: no plan/decision for $DATE — nothing to grade" >> logs/orb_trader.log
  exit 0
fi

OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Write Read" 2>&1)
RC=$?
echo "$OUT"

fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s)"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT"

if [ -n "$fail" ]; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader LEARN FAILED: $fail" | tee -a "$ALERT"
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader learn OK ($DATE)" >> logs/orb_trader.log
