#!/usr/bin/env bash
# Install Exit ML auto-scan cron entries (idempotent).
# Adds 4 daily scan_track triggers (Z1/Z2/Z3/Z4) Mon-Fri ET.
#
# Times are written in Bangkok local time (TZ=Asia/Bangkok already at top
# of user's crontab). During EDT (Mar-Nov): ET = BKK - 11h. During EST: -12h.
# This script installs the EDT mapping. Re-run after the DST flip in November
# to swap to the EST mapping.

set -euo pipefail

REPO="/home/saengtawan/work/project/cc/stock-analyzer"
MARKER="# === Exit ML auto-scan (scan_track) ==="
END_MARKER="# === end Exit ML auto-scan ==="

# Detect current DST: if EDT, use 20:xx; if EST, use 21:xx
ET_HOUR_FOR_0930=$(TZ=America/New_York date '+%H:%M' -d '2026-06-05 09:30 EDT' 2>/dev/null || echo "09:30")
NOW_ET_OFFSET=$(TZ=America/New_York date '+%z')
case "$NOW_ET_OFFSET" in
  -0400) BKK_HOUR=20 ;;  # EDT
  -0500) BKK_HOUR=21 ;;  # EST
  *)     BKK_HOUR=20 ;;  # fallback EDT
esac
echo "[cron-install] detected ET offset $NOW_ET_OFFSET → using BKK hour $BKK_HOUR for 09:30 ET"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

# Save current crontab, strip any old block
crontab -l 2>/dev/null | sed "/$MARKER/,/$END_MARKER/d" > "$TMP" || true

# Append new block
{
  echo ""
  echo "$MARKER"
  echo "# Fires scan_track.sh at each zone window. Picks → background exit_loop."
  echo "# Logs go to data/exit_loops/<SYM>_<DATE>_<HHMM>.log"
  echo "30 ${BKK_HOUR}  * * 1-5 cd $REPO && bash scripts/scan_track.sh >> logs/scan_track.log 2>&1   # ET 09:30 (Z1)"
  echo "40 ${BKK_HOUR}  * * 1-5 cd $REPO && bash scripts/scan_track.sh >> logs/scan_track.log 2>&1   # ET 09:40 (Z2)"
  echo "0  $((BKK_HOUR+1))  * * 1-5 cd $REPO && bash scripts/scan_track.sh >> logs/scan_track.log 2>&1   # ET 10:00 (Z3)"
  echo "45 $((BKK_HOUR+1))  * * 1-5 cd $REPO && bash scripts/scan_track.sh >> logs/scan_track.log 2>&1   # ET 10:45 (Z4)"
  echo "$END_MARKER"
} >> "$TMP"

# Install
crontab "$TMP"
echo
echo "[cron-install] installed. Current Exit ML cron block:"
crontab -l | sed -n "/$MARKER/,/$END_MARKER/p"
echo
echo "Note: After Nov DST flip, re-run this script to update BKK hours."
echo "      Stop auto-scan anytime with: crontab -e  (delete the block)"
