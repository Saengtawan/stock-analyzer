#!/usr/bin/env bash
# Exit ML v17c — auto-poll loop. Calls exit_check.sh every 5 minutes
# until 15:55 ET (market close) or manual stop.
#
# 2026-06-04: EXIT and CRISIS_HOLD no longer terminate the loop. The first
# EXIT triggers a loud banner + beep; subsequent EXIT iters are logged
# compactly. This lets the user track PnL/ML trajectory through and past
# the exit point (shadow-mode monitoring).
#
# Usage (same args as exit_check.sh):
#   bash scripts/exit_loop.sh SYM                       # lookup from active_positions
#   bash scripts/exit_loop.sh SYM 208.50 10:05          # explicit entry + time
#   bash scripts/exit_loop.sh SYM 46.47 09:35 2026-06-01  # historical replay
#   bash scripts/exit_loop.sh SYM --live                # mark journal LIVE
#
# Options:
#   POLL_SECONDS=300  (override poll interval, default 300 = 5 min)
#   QUIET=1           (don't beep on EXIT)

set -uo pipefail
cd "$(dirname "$0")/.."

if [ $# -eq 0 ]; then
  echo "Usage: bash scripts/exit_loop.sh SYM [ENTRY] [TIME] [DATE] [--live]" >&2
  exit 1
fi

POLL=${POLL_SECONDS:-300}
SYM="$1"

# ET clock — sanity bound
et_now() { TZ=America/New_York date '+%H:%M'; }
et_hhmm() { TZ=America/New_York date '+%H%M' | sed 's/^0//'; }
ts() { date '+%H:%M:%S'; }

cleanup() {
  echo
  echo "[$(ts)] === Loop stopped (signal/manual) ==="
  exit 0
}
trap cleanup INT TERM

beep() {
  [ -n "${QUIET:-}" ] && return
  for _ in 1 2 3; do printf '\a'; sleep 0.15; done
}

echo "[$(ts)] === Exit-loop started for $SYM (poll ${POLL}s) ==="
echo "[$(ts)] Press Ctrl+C to stop. Loop ends at 15:55 ET (EXIT/CRISIS_HOLD = alert only, keeps polling)."
echo

last_verdict=""
exit_fired=""
crisis_fired=""
iter=0
while true; do
  iter=$((iter+1))
  ET_NOW=$(et_now)
  NOW_NUM=$(et_hhmm)

  # Stop at 15:55 ET (market close)
  if [ -n "$NOW_NUM" ] && [ "$NOW_NUM" -ge 1555 ]; then
    echo "[$(ts)] === EOD reached (ET $ET_NOW >= 15:55) — stopping loop ==="
    exit 0
  fi

  # Run exit_check, capture output
  out=$(bash scripts/exit_check.sh "$@" 2>&1) || true
  verdict=$(printf '%s\n' "$out" | grep -E '^Verdict:' | head -1 | sed -E 's/^Verdict:[[:space:]]*[^A-Z]*//' | awk '{print $1}')
  if [ -z "$verdict" ]; then verdict=$(printf '%s\n' "$out" | grep -oE '(HOLD|EXIT|CRISIS_HOLD|ERROR)' | head -1); fi
  prob=$(printf '%s\n' "$out" | grep -oE 'ML p:[[:space:]]+[0-9.]+' | head -1 | awk '{print $NF}')
  pnl=$(printf '%s\n' "$out" | grep -oE 'PnL:[[:space:]]+[+-]?[0-9.]+%' | head -1 | awk '{print $NF}')

  compact="[$(ts)] ET $ET_NOW  iter=$iter  ${verdict:-?}"
  [ -n "$prob" ] && compact="$compact  p=$prob"
  [ -n "$pnl" ]  && compact="$compact  pnl=$pnl"

  case "$verdict" in
    EXIT)
      if [ -z "$exit_fired" ]; then
        echo
        echo "===================================================================="
        echo "⚠️⚠️⚠️  EXIT SIGNAL  ⚠️⚠️⚠️"
        echo "===================================================================="
        printf '%s\n' "$out"
        echo "===================================================================="
        echo "Time: $(ts) ET=$ET_NOW — GO SELL AT ALPACA NOW"
        beep
        exit_fired=1
      else
        echo "$compact  [post-EXIT, still monitoring]"
      fi
      ;;
    CRISIS_HOLD)
      if [ -z "$crisis_fired" ]; then
        echo "$compact"
        echo "[$(ts)] === CRISIS_HOLD (VIX gate) — Exit ML disabled for this trade ==="
        printf '%s\n' "$out" | tail -8
        crisis_fired=1
      else
        echo "$compact  [CRISIS_HOLD, still monitoring]"
      fi
      ;;
    ERROR)
      echo "$compact"
      if [ "$iter" -eq 1 ] || [ $((iter % 6)) -eq 0 ]; then
        # Show full error every 6 iters (every 30 min) — could be data lag
        printf '%s\n' "$out" | tail -5
      fi
      ;;
    HOLD)
      echo "$compact"
      ;;
    *)
      echo "$compact  (unparsed)"
      printf '%s\n' "$out" | tail -3
      ;;
  esac
  last_verdict="$verdict"

  sleep "$POLL"
done
