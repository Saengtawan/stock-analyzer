#!/usr/bin/env bash
# runner/run/scan.sh — ~10:30 ET scan: fresh-catalyst penny movers with a not-extended entry -> >+10%.
# (A 10:20 window was tried + reverted 08-25 = noise. Entry is ALWAYS modeled at the 10:30 bar.)
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

# Cron-bug guard: the entry is modeled at the 10:30 bar. If we fire well after 10:30 the post-10:30 tape
# is already known, so a fresh log would be a lookup, not a forecast. Flag a late fire loudly so the
# brain runs as a labelled replay (select on <=10:30 bars, log nothing) instead of faking early entries.
NOWMIN=$(( 10#$(TZ=America/New_York date '+%H') * 60 + 10#$(TZ=America/New_York date '+%M') ))
LATE=""
if [ "$NOWMIN" -gt 645 ]; then   # 645 = 10:45 ET
  LATE="⚠️ LATE FIRE: it is $NOW ET, past the 10:30 entry window. The post-10:30 tape is ALREADY KNOWN.
Run as a LABELLED REPLAY: select strictly on bars cut at 10:30, read post-10:30 tape ONLY after the call
is fixed, and LOG NOTHING NEW to the DB (a 10:30-priced entry logged now is a lookup, not a forecast).
"
fi

PROMPT="Today (ET) is $DATE, it is now $NOW ET (the ~10:30 window). $LATE You are the runner brain — find
fresh-catalyst penny movers with a not-extended entry likely to trail +10% from the ~10:30 bar. Execute exactly:
$(sed -e "s/<DATE>/$DATE/g" -e "s/<STAMP>/$STAMP/g" runner/brain/decide.md)"

timeout 900 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "runner/plans/$STAMP.txt"
echo "[runner] scan done ($DATE $NOW ET) -> runner/plans/$STAMP.txt"
