#!/usr/bin/env bash
# orb_trader / run / premarket.sh — cron ① PRE-MARKET THESIS (~09:05 ET / 20:05 BKK)
# Runs the brain headless with brain/thesis.md; writes orb_trader/plans/DATE.plan.json. No buy.
# Fires BEFORE the quota-reset collision zone that killed the old 09:32 run.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/issara/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
ALERT="logs/ai_trader_ALERT.log"
# Inline the prompt with DATE substituted (uppercase DATE is only the placeholder); MINUTE stays
# literal — the brain computes it. The brain reads memory/channels itself via its tools.
PROMPT="Today (ET) is $DATE. You are the orb_trader brain. Execute PASS ① exactly as written below.

$(sed "s/DATE/$DATE/g" orb_trader/brain/thesis.md)"

OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash WebSearch Write Read" 2>&1)
RC=$?
echo "$OUT"

fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s)"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT"
[ ! -f "orb_trader/plans/$DATE.plan.json" ] && fail="${fail:+$fail; }NO plan file written for $DATE"

if [ -n "$fail" ]; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader THESIS FAILED: $fail" | tee -a "$ALERT"
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader thesis OK ($DATE)" >> logs/orb_trader.log
