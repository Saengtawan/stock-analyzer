#!/usr/bin/env bash
# riser_watch.sh — live terminal monitor for the riser lane (entry pick + regime-aware exit).
# The cron runs riser_capture headless (-> logs/riser_momentum.log) and auto-launches an
# exit_loop per pick (-> data/exit_loops/SYM_DATE_riser.log). This tails BOTH live in one
# terminal so you can SEE the BUY suggestion + the EXIT verdicts (BULL hold / BEAR ~10:05 /
# peak-fade) as they fire. Run: bash scripts/riser_watch.sh   (Ctrl-C to stop)
set -u
cd "$(dirname "$0")/.."
ET_DATE=$(TZ=America/New_York date '+%Y-%m-%d')
RL="logs/riser_momentum.log"
mkdir -p data/exit_loops

cleanup() { local p; for p in $(jobs -p 2>/dev/null); do kill "$p" 2>/dev/null; done; rm -f /tmp/.riserwatch_* 2>/dev/null; echo; echo "[riser-watch stopped]"; exit 0; }
trap cleanup INT TERM

echo "=================================================================="
echo " RISER WATCH  $ET_DATE   (ET $(TZ=America/New_York date '+%H:%M %Z'))"
echo " cron picks ~09:38 ET. Ctrl-C to stop."
echo "=================================================================="
# show today's entry/pick so far (last riser_momentum block for today)
awk -v d="$ET_DATE" 'f{print} /riser_momentum @ /{f=($0 ~ d)}' "$RL" 2>/dev/null | tail -25
echo "------------------------- live -----------------------------------"

# follow the entry log (pick appears here when cron fires)
tail -n 0 -F "$RL" 2>/dev/null | sed -u 's/^/[entry] /' &

# follow today's exit logs; pick up new ones as the exit_loop creates them per pick
while true; do
  for f in data/exit_loops/*_"${ET_DATE}"_riser.log data/exit_loops/*_"${ET_DATE}"_entry.log; do
    [ -e "$f" ] || continue
    _m="/tmp/.riserwatch_$(basename "$f")"
    if [ ! -e "$_m" ]; then
      touch "$_m"
      _sym=$(basename "$f" | cut -d_ -f1)
      _kind=$([ "${f%_entry.log}" != "$f" ] && echo "fill $_sym" || echo "exit $_sym")
      tail -n 3 -F "$f" 2>/dev/null | sed -u "s/^/[$_kind] /" &
    fi
  done
  sleep 10
done
