#!/usr/bin/env bash
# watch_riser.sh — live terminal view of the riser lane (open this in a terminal tab
# before 09:31 ET; the riser BUY display (~09:37:45) and exit-tracker verdicts stream here).
# Tails logs/riser_momentum.log (capture+display) + data/exit_loops/*riser.log (exit verdicts).
cd "$(dirname "$0")/.."
LOG=logs/riser_momentum.log
mkdir -p data/exit_loops; touch "$LOG"

echo "=== watching riser lane (Ctrl-C to stop) ==="
echo "  capture/display : $LOG"
echo "  exit trackers   : data/exit_loops/*_riser.log"
echo "  ET now: $(TZ=America/New_York date '+%H:%M:%S')  | riser display ~09:37:45 ET"
echo "------------------------------------------------------------------"

# stream both the capture log and any riser exit-tracker logs, with a source tag + highlight
tail -n 5 -F "$LOG" data/exit_loops/*_riser.log 2>/dev/null | awk '
  /==> .* <==/ { f=$2; next }                                  # tail filename header
  /BUY|RISER|riser_momentum/ { print "\033[1;32m" $0 "\033[0m"; next }   # green: buy/display
  /TRAIL_EXIT|EXIT/          { print "\033[1;33m" $0 "\033[0m"; next }   # yellow: exit signal
  /HOLD/                     { print "\033[0;36m" $0 "\033[0m"; next }   # cyan: hold
  { print }
'
