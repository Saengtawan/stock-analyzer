#!/usr/bin/env bash
# scan_track.sh — scan + auto-track any new picks in background.
# Wraps scan_smart.sh. When ml_filter emits picks, launches exit_loop.sh
# (one per pick) as a background process logging to data/exit_loops/.
#
# Usage:
#   bash scripts/scan_track.sh                    # auto strategy (= scan_smart.sh default)
#   bash scripts/scan_track.sh ml_filter          # force ml_filter
#
# Notes:
#   - exit_loop runs detached (nohup, no terminal needed). Survives if you
#     close this shell.
#   - Each pick gets its own log file in data/exit_loops/SYM_DATE_HHMM.log
#   - Already-tracked picks are skipped (de-duplicated by (sym, scan_ts))
#   - Stop a tracker:  pkill -f "exit_loop.sh SYM"  or  TaskStop in Claude

set -uo pipefail
cd "$(dirname "$0")/.."

LOG_DIR="data/exit_loops"
mkdir -p "$LOG_DIR"
JOURNAL="data/scan_journal.db"
TRACKED="$LOG_DIR/.tracked"
touch "$TRACKED"

START_TS=$(date -u '+%Y-%m-%d %H:%M:%S')   # UTC — matches scan_picks.created_at

echo "[scan_track] starting scan at UTC $START_TS"
bash scripts/scan_smart.sh "$@"
RC=$?

if [ "$RC" -ne 0 ]; then
  echo "[scan_track] scan_smart returned non-zero ($RC) — not tracking"
  exit "$RC"
fi

# Query picks created since this scan started, for ml_filter only
mapfile -t PICKS < <(sqlite3 "$JOURNAL" \
  "SELECT scan_ts || '|' || symbol || '|' || entry FROM scan_picks
   WHERE strategy='ml_filter' AND created_at >= '$START_TS'
   ORDER BY scan_ts, symbol")

if [ "${#PICKS[@]}" -eq 0 ]; then
  echo "[scan_track] no new picks → nothing to track"
  exit 0
fi

echo
echo "[scan_track] === ${#PICKS[@]} new pick(s) — launching trackers ==="
for row in "${PICKS[@]}"; do
  IFS='|' read -r scan_ts sym entry <<< "$row"
  key="$scan_ts|$sym"
  if grep -Fxq "$key" "$TRACKED"; then
    echo "[scan_track] skip $sym ($scan_ts) — already tracked"
    continue
  fi
  scan_date=${scan_ts:0:10}
  scan_hhmm=${scan_ts:11:5}  # HH:MM
  log_name="${sym}_${scan_date}_${scan_hhmm/:/}.log"
  log_path="$LOG_DIR/$log_name"

  nohup bash scripts/exit_loop.sh "$sym" "$entry" "$scan_hhmm" "$scan_date" \
    > "$log_path" 2>&1 < /dev/null &
  pid=$!
  disown "$pid" 2>/dev/null || true
  echo "$key" >> "$TRACKED"
  echo "  ✓ $sym @ \$$entry  scan=$scan_ts  PID=$pid  log=$log_path"
done

echo
echo "[scan_track] === Trackers running in background ==="
echo "[scan_track]   monitor:  tail -f $LOG_DIR/<SYM>_*.log"
echo "[scan_track]   stop one: pkill -f 'exit_loop.sh SYM'"
echo "[scan_track]   stop all: pkill -f 'exit_loop.sh'"
