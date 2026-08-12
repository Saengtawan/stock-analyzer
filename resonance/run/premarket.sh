#!/usr/bin/env bash
# resonance / run / premarket.sh — cron ① PRE-OPEN DECIDE (~09:00 ET / 20:00 BKK)
#
#   (a) MECHANICAL, 0 tokens (cc pyenv): build coil+prime features, then the high-recall pool.
#   (b) BRAIN, 1 call: claude -p with brain/decide.md (DATE substituted) -> writes
#       resonance/plans/<DATE>.plan.json (even when abstaining).
#   (c) ALERT to logs/ai_trader_ALERT.log on timeout / nonzero / session-limit / NO plan written.
#
# Fires BEFORE the 09:30 quota-reset collision zone. cc python is put first on PATH so `python`
# resolves to the production env; ~/.local/bin carries the `claude` CLI.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
ALERT="logs/ai_trader_ALERT.log"
PLAN="resonance/plans/$DATE.plan.json"

# --- (a0) LIVE premarket bars: fetch TODAY's premarket into intraday_bars_5m BEFORE features/pool.
#          At 09:00 ET the DB collectors have NOT yet written today's premarket (they run post-open,
#          ~10:29 ET, coverage spotty) and the resonance extras have no intraday at all — so
#          prime.premarket() (gap/wake) would be empty. This closes that gap live (Alpaca IEX).
#          If it fails, WARN to the ALERT file but STILL proceed: coil-only degraded > total failure.
if ! python -m resonance.universe.fetch_premarket "$DATE"; then
  echo "🟠 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance premarket fetch FAILED (DEGRADED: coil-only; prime gap/wake empty today): fetch_premarket $DATE" | tee -a "$ALERT"
fi

# --- (a) MECHANICAL: features -> pool (zero AI tokens over already-stored raw data) -----------
if ! python -m resonance.features.build "$DATE"; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance MECHANICAL FAILED: features.build $DATE" | tee -a "$ALERT"
  exit 1
fi
if ! python -m resonance.screen.pool "$DATE"; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance MECHANICAL FAILED: screen.pool $DATE" | tee -a "$ALERT"
  exit 1
fi

# --- (b) BRAIN: decide (1 call). decide.md uses the <DATE> placeholder (incl. cache/plan paths
#         like pool_<DATE>.json), so substitute <DATE> — keeps those paths valid. ---------------
PROMPT="Today (ET) is $DATE. You are the resonance brain. Execute the PRE-OPEN DECIDE pass exactly as written below.

$(sed "s/<DATE>/$DATE/g" resonance/brain/decide.md)"

OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1)
RC=$?
echo "$OUT"

# --- (c) ALERT on any failure mode --------------------------------------------------------------
fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s)"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT"
[ ! -f "$PLAN" ] && fail="${fail:+$fail; }NO plan file written for $DATE"

if [ -n "$fail" ]; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance DECIDE FAILED: $fail" | tee -a "$ALERT"
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] resonance decide OK ($DATE)" >> logs/resonance.log
