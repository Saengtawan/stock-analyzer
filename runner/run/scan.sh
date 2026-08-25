#!/usr/bin/env bash
# runner/run/scan.sh — fresh-catalyst penny movers with a not-extended entry -> >+10%.
# FIRST run of the day = the standard 10:30 window. A manual RE-RUN (a plan file already exists for today)
# = the CURRENT window automatically, a genuine intraday forward call (RUNNER_ENTRY=now|HH:MM forces one).
# (A fixed 10:20 window was tried + reverted 08-25 = noise; the window is not the edge.)
# FULLY ISOLATED + OFF-RECORD: writes ONLY runner/plans/ + data/runner.db. Touches NOTHING in
# resonance/overnight/exec_ai/swing/rotation.
#   Grade at the close:  bash runner/run/grade.sh
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
NOW=$(TZ=America/New_York date '+%H:%M')
STAMP="${DATE}_$(TZ=America/New_York date '+%H%M')"
mkdir -p runner/plans

# Entry window:
#   * FIRST run of the day  -> the standard 10:30 window (a late first-fire runs a labelled replay).
#   * a manual RE-RUN       -> the CURRENT window automatically (today already has logged picks) — a
#                              genuine intraday forward call, entered live, tape ahead unknown, logged.
#   * RUNNER_ENTRY=now|HH:MM -> force a specific window (overrides the auto-detect).
NOWMIN=$(( 10#$(TZ=America/New_York date '+%H') * 60 + 10#$(TZ=America/New_York date '+%M') ))
# a run already happened today (pick OR abstain) if a plan file exists for $DATE -> this is a re-run
HAVE_TODAY=$(ls runner/plans/${DATE}_*.txt 2>/dev/null | wc -l | tr -d ' ')

# the current-window forward-call instruction, shared by an explicit override and an auto-detected re-run
current_window_note () {  # $1 = why
  printf '%s' "⚠️ ENTRY-WINDOW = CURRENT ($ENTRY ET) — $1. This takes precedence over any '10:30' in the
brief below. Model every entry at the $ENTRY bar, log scan_time='$ENTRY', and treat it as a GENUINE
FORWARD call: the post-$ENTRY tape is NOT known to you, so do NOT read bars after $ENTRY, and DO log the
picks normally (this is not a replay). Names logged earlier today at a different window stay untouched.
"
}

ENTRY="10:30"; OVERRIDE=""; LATE=""; MODE=""
if [ -n "${RUNNER_ENTRY:-}" ]; then
  ENTRY="${RUNNER_ENTRY}"; [ "$ENTRY" = "now" ] && ENTRY="$NOW"
  MODE="forced RUNNER_ENTRY=$ENTRY"; OVERRIDE="$(current_window_note "forced by RUNNER_ENTRY")"
elif [ "${HAVE_TODAY:-0}" -gt 0 ]; then
  ENTRY="$NOW"; MODE="re-run -> current window $ENTRY"
  OVERRIDE="$(current_window_note "this is a manual re-run, today's 10:30 pass already ran")"
elif [ "$NOWMIN" -gt 645 ]; then   # 645 = 10:45 ET — a late FIRST fire of the standard 10:30 window
  MODE="first-run, LATE -> 10:30 replay"
  LATE="⚠️ LATE FIRE: it is $NOW ET, past the 10:30 entry window, and nothing is logged today yet. The
post-10:30 tape is ALREADY KNOWN. Run as a LABELLED REPLAY: select strictly on bars cut at 10:30, read
post-10:30 tape ONLY after the call is fixed, and LOG NOTHING NEW (a 10:30-priced entry logged now is a
lookup, not a forecast). (To enter at the CURRENT window as a real forward call instead, re-run with
RUNNER_ENTRY=now.)
"
else
  MODE="first-run, standard 10:30 window"
fi
echo "[runner] mode: $MODE  (now $NOW ET, today rows=$HAVE_TODAY)"

PROMPT="Today (ET) is $DATE, it is now $NOW ET. The entry window is $ENTRY ET. $OVERRIDE$LATE You are the
runner brain — find fresh-catalyst penny movers with a not-extended entry likely to trail +10% from the
~$ENTRY bar. Execute exactly:
$(sed -e "s/<DATE>/$DATE/g" -e "s/<STAMP>/$STAMP/g" runner/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "runner/plans/$STAMP.txt"
echo "[runner] scan done ($DATE $NOW ET) -> runner/plans/$STAMP.txt"
