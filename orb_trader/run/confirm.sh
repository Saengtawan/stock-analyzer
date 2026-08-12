#!/usr/bin/env bash
# orb_trader / run / confirm.sh — cron ② OPEN DECIDE (PREDICT & ACT) (~09:33 ET / 20:33 BKK)
# The 1-min opening range (first 3 bars, 09:30-09:32) is complete at 09:33. This is a PREDICT pass,
# not a break-gate: the brain DECIDES which watchlist names to buy using its full context + the
# live price action as ONE input (not a required trigger). Entry = cur at ~09:33. Runs
# brain/confirm.md against this morning's plan; decided -> paper log.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/issara/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
ALERT="logs/ai_trader_ALERT.log"
PROMPT="Today (ET) is $DATE. You are the orb_trader brain. Execute PASS ② (DECIDE / predict-and-act) exactly as written below. The 1-minute opening range (first 3 bars, 09:30-09:32) is complete; it is ~09:33 ET now — use the current ET minute-from-midnight as MINUTE. You DECIDE with judgment; the live price action is one input, not a required gate.

$(sed "s/DATE/$DATE/g" orb_trader/brain/confirm.md)"

# No plan = nothing to confirm; that's a valid quiet day, not a failure.
if [ ! -f "orb_trader/plans/$DATE.plan.json" ]; then
  echo "[$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader confirm: no plan for $DATE (thesis abstained or failed) — nothing to do" >> logs/orb_trader.log
  exit 0
fi

OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash WebSearch Write Read" 2>&1)
RC=$?
echo "$OUT"

fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s)"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT"
[ ! -f "orb_trader/plans/$DATE.decision.json" ] && fail="${fail:+$fail; }NO decision file written for $DATE"

if [ -n "$fail" ]; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader CONFIRM FAILED: $fail" | tee -a "$ALERT"
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] orb_trader confirm OK ($DATE)" >> logs/orb_trader.log
