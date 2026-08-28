#!/usr/bin/env bash
# overnight/run/learn.sh — POST-AH-EXIT AI reflection (cron, ~20:15 ET after the 19:59 exit). The
# mechanical grade already ran (grade cron), so ah_mark/ah_pct are safe in data/overnight.db even if
# this AI pass is killed. This appends the graded RESULT + running record to overnight/forward_record.md.
# The scan already wrote the day's PICK section; here we add the OUTCOME (win/loss + updated tally).
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
bash overnight/run/grade.sh >/dev/null 2>&1   # idempotent: ensure graded

# skip if nothing was graded today
if ! python -c "import sqlite3,sys; sys.exit(0 if sqlite3.connect('data/overnight.db').execute(\"SELECT COUNT(*) FROM picks WHERE date='$DATE' AND graded=1\").fetchone()[0] else 1)"; then
  echo "[overnight-learn] nothing graded $DATE"; exit 0
fi
# skip if the RESULT is already recorded for this date
if grep -qiE "^\*\*RESULT.*$DATE|GRADED.*$DATE" overnight/forward_record.md 2>/dev/null; then
  echo "[overnight-learn] $DATE result already recorded"; exit 0
fi

PROMPT="Today (ET) is $DATE, after the 19:59 AH exit. You are the overnight LEARN pass. The pick(s) are
graded in data/overnight.db.
1) Read the graded result: python -c \"import sqlite3; [print(r) for r in sqlite3.connect('data/overnight.db').execute(\\\"SELECT date,sym,rth_close,ah_mark,ah_pct FROM picks WHERE date='$DATE'\\\")]\"
2) Read overnight/forward_record.md — it already has today's PICK section from the pre-close scan.
3) Into that same $DATE section, add the RESULT line (entry->AH exit = +/-x%) and update the running
   record tally (N-for-N, avg). Keep it honest: n is small, note any clean-blind-call losses, do not
   let a win streak inflate the stated lean. Write ONLY overnight/forward_record.md, nothing else."
timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write" 2>&1 | tail -6
echo "[overnight-learn] done ($DATE)"
