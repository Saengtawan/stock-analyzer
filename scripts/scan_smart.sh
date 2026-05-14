#!/bin/bash
# scan_smart.sh — wait for 1-min bar to close before scanning.
#
# If invoked before 09:31:30 ET on a weekday, sleep until then so the
# engine has at least one closed 1-min bar (+30s ingestion buffer).
# After that, run ml_filter scan immediately.
#
# Use from any session/Claude:  bash scripts/scan_smart.sh
# Or via command alias.
#
# Behavior outside 09:30-13:00 ET: passes straight through to engine
# (engine itself returns out_of_window or skipped_gate as appropriate).

set -u
cd "$(dirname "$0")/.."

# Target: 09:31:30 ET (1 min after first bar closes + 30s buffer)
TARGET_ET="09:31:30"

# Get current ET time as seconds since midnight ET
read -r ET_HMS NOW_DOW < <(TZ=America/New_York date '+%H:%M:%S %u')
IFS=: read -r H M S <<<"$ET_HMS"
NOW_SECS=$((10#$H * 3600 + 10#$M * 60 + 10#$S))
TARGET_SECS=$((9 * 3600 + 31 * 60 + 30))   # 09:31:30
EARLY_START=$((9 * 3600 + 28 * 60))         # 09:28:00 — earliest auto-wait window

# Only auto-wait Mon-Fri (DoW 1-5)
if [[ "$NOW_DOW" -le 5 && "$NOW_SECS" -ge "$EARLY_START" && "$NOW_SECS" -lt "$TARGET_SECS" ]]; then
  WAIT=$((TARGET_SECS - NOW_SECS))
  echo "[scan_smart] ET $ET_HMS — waiting ${WAIT}s for 1-min bar @ $TARGET_ET ET"
  sleep "$WAIT"
fi

# Use the project's Python interpreter
PYTHON="/home/saengtawan/.pyenv/versions/issara/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="python3"

exec "$PYTHON" -m src.scan.engine "${1:-ml_filter}"
