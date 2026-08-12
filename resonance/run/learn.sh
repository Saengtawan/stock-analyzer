#!/usr/bin/env bash
# resonance / run / learn.sh — cron ④ AFTER-CLOSE LEARN (~16:30 ET / 03:30 BKK next day)
#
#   (a) MECHANICAL, 0 tokens (cc pyenv): paper_buy each of the plan's picks at the 09:30 open and
#       realize the 15:55 close -> result% + vs_spy into data/resonance.db (execute.process_plan).
#   (b) BRAIN, 1 call: claude -p with brain/learn.md (DATE substituted) -> appends one forward line
#       to resonance/memory.md.
#   (c) ALERT to logs/ai_trader_ALERT.log on timeout / nonzero / session-limit.
#
# cc python first on PATH for the mechanical fill; ~/.local/bin carries the `claude` CLI.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
ALERT="logs/ai_trader_ALERT.log"
PLAN="resonance/plans/$DATE.plan.json"

# No plan today = nothing decided; a full-abstain day still writes a plan, so a missing file means
# the morning decide never ran — nothing to grade.
if [ ! -f "$PLAN" ]; then
  echo "[$(TZ=America/New_York date '+%F %H:%M ET')] resonance learn: no plan for $DATE — nothing to grade" >> logs/resonance.log
  exit 0
fi

# --- (a0) ensure today's EXTRAS intraday bars exist before we realize. The core collector covers
#          core names, but resonance EXTRAS need their own 5-min fetch or execute.realize() finds no
#          09:30/15:55 bar and the pick's outcome comes back empty (forward record can't be graded).
#          Runs at ~16:30 ET so SIP (15-min delay) is complete. Idempotent (INSERT OR IGNORE),
#          extras-only, ~20s. Non-fatal — a hiccup must not block grading core picks. --------------
if ! python -m resonance.universe.fetch_intraday "$DATE" >> logs/fetch_intraday_extras.log 2>&1; then
  echo "[$(TZ=America/New_York date '+%F %H:%M ET')] resonance learn: extras intraday fetch warned (non-fatal)" >> logs/resonance.log
fi

# --- (a) MECHANICAL: fill each pick's outcome (buy@open -> realize@close). Abstain plans have no
#         picks -> a clean empty fill. --------------------------------------------------------------
if ! python -m resonance.lib.execute plan "$DATE" live; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance MECHANICAL FAILED: execute plan $DATE" | tee -a "$ALERT"
  exit 1
fi

# --- (b) BRAIN: learn (1 call). learn.md uses the <DATE> placeholder (incl. plans/<DATE>.plan.json),
#         so substitute <DATE> to keep those paths valid. ----------------------------------------
PROMPT="Today (ET) is $DATE. You are the resonance brain. Execute the AFTER-CLOSE LEARN pass exactly as written below.

$(sed "s/<DATE>/$DATE/g" resonance/brain/learn.md)"

OUT=$(timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write" 2>&1)
RC=$?
echo "$OUT"

# --- (c) ALERT on any failure mode --------------------------------------------------------------
fail=""
[ $RC -eq 124 ] && fail="TIMEOUT (>600s)"
[ $RC -ne 0 ] && [ $RC -ne 124 ] && fail="claude exited $RC"
echo "$OUT" | grep -qi "session limit\|usage limit\|rate limit" && fail="SESSION/RATE LIMIT"

if [ -n "$fail" ]; then
  echo "🔴🔴🔴 [$(TZ=America/New_York date '+%F %H:%M ET')] resonance LEARN FAILED: $fail" | tee -a "$ALERT"
  exit 1
fi
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] resonance learn OK ($DATE)" >> logs/resonance.log
