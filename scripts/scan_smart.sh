#!/bin/bash
# scan_smart.sh — wait for next 5-min bar boundary + 30s buffer (Option A).
#
# 2026-05-16: Switched from 1-min to 5-min wait alignment.
# Training pkl uses 5-min bars + features computed at 5-min boundaries.
# WF perfect refit: 5-min train + 5-min test = +2096%/6mo (baseline).
# Prev (1-min): live used off-boundary mfo → phantom positives → WF predicts -2248%/6mo.
# Fix: wait until next 5-min boundary closes + 30s, then engine uses that mfo.
#
# Behavior:
# - Pre-09:35:30 ET on weekday: wait until 09:35:30 (first complete 5-min bar)
# - Mid-window (09:35:30+): wait until next 5-min boundary + 30s (e.g., 09:40:30)
# - Outside 09:30-13:00 ET window: passes straight through to engine

set -u
cd "$(dirname "$0")/.."

# Get current ET time as seconds since midnight ET
read -r ET_HMS NOW_DOW < <(TZ=America/New_York date '+%H:%M:%S %u')
IFS=: read -r H M S <<<"$ET_HMS"
NOW_SECS=$((10#$H * 3600 + 10#$M * 60 + 10#$S))

# Market window
MARKET_OPEN_SECS=$((9 * 3600 + 30 * 60))         # 09:30:00 ET
EARLIEST_SCAN_SECS=$((9 * 3600 + 35 * 60 + 30))  # 09:35:30 ET (first 5-min bar closed + buffer)
LATEST_SCAN_SECS=$((13 * 3600))                  # 13:00:00 ET (window end)

# Only auto-wait Mon-Fri (DoW 1-5) inside market window
if [[ "$NOW_DOW" -le 5 && "$NOW_SECS" -ge "$MARKET_OPEN_SECS" && "$NOW_SECS" -lt "$LATEST_SCAN_SECS" ]]; then
  if [[ "$NOW_SECS" -lt "$EARLIEST_SCAN_SECS" ]]; then
    # Before first valid scan time → wait to 09:35:30
    WAIT=$((EARLIEST_SCAN_SECS - NOW_SECS))
    TARGET_HMS="09:35:30"
  else
    # Mid-session → wait to next 5-min boundary + 30s
    # Next boundary: floor((NOW_SECS - MARKET_OPEN_SECS) / 300) * 300 + 300 + MARKET_OPEN_SECS + 30
    SECS_SINCE_OPEN=$((NOW_SECS - MARKET_OPEN_SECS))
    NEXT_BOUNDARY_OFFSET=$(( (SECS_SINCE_OPEN / 300 + 1) * 300 ))
    NEXT_SCAN_SECS=$((MARKET_OPEN_SECS + NEXT_BOUNDARY_OFFSET + 30))
    WAIT=$((NEXT_SCAN_SECS - NOW_SECS))
    # Format target HMS
    TH=$((NEXT_SCAN_SECS / 3600))
    TM=$(( (NEXT_SCAN_SECS % 3600) / 60 ))
    TS=$(( NEXT_SCAN_SECS % 60 ))
    TARGET_HMS=$(printf "%02d:%02d:%02d" $TH $TM $TS)
  fi
  if [[ "$WAIT" -gt 0 && "$WAIT" -lt 350 ]]; then
    echo "[scan_smart] ET $ET_HMS — waiting ${WAIT}s for 5-min bar @ $TARGET_HMS ET (Option A)"
    sleep "$WAIT"
  fi
fi

# Use the project's Python interpreter
PYTHON="/home/saengtawan/.pyenv/versions/issara/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="python3"

exec "$PYTHON" -m src.scan.engine "${1:-ml_filter}"
