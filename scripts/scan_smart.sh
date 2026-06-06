#!/bin/bash
# scan_smart.sh — snap to the 5-min bar boundary before scanning.
#
# The model is trained on a 5-min grid (mfo 0,5,10,...). Live 5-min bars
# close on :00/:05/:10... ET; we wait until the next boundary + 30s ingestion
# buffer so the freshest bar is complete and live mfo lands on the grid.
# The first regular-session bar (09:30) closes 09:35:00 ET -> 09:35:30 with
# the buffer, so that is the earliest scan.
#
# Use from any session/Claude:  bash scripts/scan_smart.sh
# Or via command alias.
#
# Behavior outside 09:30-13:00 ET: passes straight through to engine
# (engine itself returns out_of_window or skipped_gate as appropriate).

set -u
cd "$(dirname "$0")/.."

# Get current ET time as seconds since midnight ET
read -r ET_HMS NOW_DOW < <(TZ=America/New_York date '+%H:%M:%S %u')
IFS=: read -r H M S <<<"$ET_HMS"
NOW_SECS=$((10#$H * 3600 + 10#$M * 60 + 10#$S))
EARLY_START=$((9 * 3600 + 28 * 60))         # 09:28:00 — earliest auto-wait
WINDOW_END=$((13 * 3600))                    # 13:00:00 — ml_filter window close
FIRST_SCAN=$((9 * 3600 + 35 * 60 + 30))      # 09:35:30 — first complete 5-min bar
BUFFER=30                                    # ingestion buffer after bar close

# Only auto-wait Mon-Fri (DoW 1-5) inside the trade window
if [[ "$NOW_DOW" -le 5 && "$NOW_SECS" -ge "$EARLY_START" && "$NOW_SECS" -lt "$WINDOW_END" ]]; then
  SLOT=$((NOW_SECS % 300))                    # seconds into current 5-min slot
  if [[ "$SLOT" -le "$BUFFER" ]]; then
    WAIT=$((BUFFER - SLOT))                    # just crossed a boundary; finish ingestion
  else
    WAIT=$((300 - SLOT + BUFFER))              # wait for next boundary + buffer
  fi
  TARGET=$((NOW_SECS + WAIT))
  if [[ "$TARGET" -lt "$FIRST_SCAN" ]]; then   # never scan before first 5-min bar exists
    WAIT=$((WAIT + FIRST_SCAN - TARGET))
    TARGET=$FIRST_SCAN
  fi
  if [[ "$TARGET" -ge "$WINDOW_END" ]]; then   # next mark is past window — let engine reject now
    WAIT=0
  fi
  if [[ "$WAIT" -gt 0 ]]; then
    TGT_HMS=$(printf '%02d:%02d:%02d' $((TARGET / 3600)) $(((TARGET % 3600) / 60)) $((TARGET % 60)))
    echo "[scan_smart] ET $ET_HMS — waiting ${WAIT}s for 5-min bar @ $TGT_HMS ET"
    sleep "$WAIT"
  fi
fi

# Use the project's Python interpreter
PYTHON="/home/saengtawan/.pyenv/versions/issara/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="python3"

exec "$PYTHON" -m src.scan.engine "${1:-ml_filter}"
