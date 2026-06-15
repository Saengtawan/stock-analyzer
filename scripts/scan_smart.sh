#!/bin/bash
# scan_smart.sh — wait for the FIRST 5-min bar, then scan at 1-min granularity.
#
# 2026-06-11 change: only the FIRST scan waits for the 5-min bar (09:36:00 ET,
# when the 09:30 bar has closed + ingestion buffer). After that we do NOT wait
# for the next 5-min boundary — we snap to the next 1-MINUTE boundary + buffer
# so the latest 1-min bar is complete. Lets you re-scan every minute without the
# 5-min wait. (Model is 5-min-grid trained; off-grid mfo still scores via the
# mins_from_open feature — slightly off-distribution but intended here.)
#
# Use from any session/Claude:  bash scripts/scan_smart.sh
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
FIRST_SCAN=$((9 * 3600 + 36 * 60))           # 09:36:00 — first scan (5-min bar closed + buffer)
BUFFER=30                                    # ingestion buffer after bar close

# Only auto-wait Mon-Fri (DoW 1-5) inside the trade window
if [[ "$NOW_DOW" -le 5 && "$NOW_SECS" -ge "$EARLY_START" && "$NOW_SECS" -lt "$WINDOW_END" ]]; then
  if [[ "$NOW_SECS" -lt "$FIRST_SCAN" ]]; then
    # Before the first 5-min bar exists: wait until 09:35:30 ET
    WAIT=$((FIRST_SCAN - NOW_SECS))
    TARGET=$FIRST_SCAN
    MODE="first 5-min bar"
  else
    # After first bar: snap to next 1-MINUTE boundary + buffer (NOT 5-min)
    SEC_MIN=$((NOW_SECS % 60))                 # seconds into current minute
    if [[ "$SEC_MIN" -le "$BUFFER" ]]; then
      WAIT=$((BUFFER - SEC_MIN))               # just crossed minute; finish ingestion
    else
      WAIT=$((60 - SEC_MIN + BUFFER))          # wait next minute + buffer
    fi
    TARGET=$((NOW_SECS + WAIT))
    MODE="1-min bar"
  fi
  if [[ "$TARGET" -ge "$WINDOW_END" ]]; then   # past window — let engine reject now
    WAIT=0
  fi
  if [[ "$WAIT" -gt 0 ]]; then
    TGT_HMS=$(printf '%02d:%02d:%02d' $((TARGET / 3600)) $(((TARGET % 3600) / 60)) $((TARGET % 60)))
    echo "[scan_smart] ET $ET_HMS — waiting ${WAIT}s for $MODE @ $TGT_HMS ET"
    sleep "$WAIT"
  fi
fi

# Use the project's Python interpreter
PYTHON="/home/saengtawan/.pyenv/versions/issara/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="python3"

exec "$PYTHON" -m src.scan.engine "${1:-ml_filter}"
