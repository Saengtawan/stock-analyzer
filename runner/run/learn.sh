#!/usr/bin/env bash
# runner/run/learn.sh — POST-CLOSE AI reflection (cron). The mechanical grade already ran (grade cron),
# so the numbers are safe in data/runner.db even if this AI pass is killed. This reads the graded picks
# and appends ONE dated section to runner/forward_record.md: hit/miss per pick, scoreboard, and any
# honest lesson (exit/window findings). Runs standalone under cron (not nested under an interactive
# session), so the host-kill seen for session-launched nested jobs does not apply here.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE=$(TZ=America/New_York date +%F)
python -m runner.lib.journal grade >/dev/null 2>&1   # idempotent: ensure today is graded

# skip if this date already has a section (avoid double-logging)
if grep -q "^## $DATE" runner/forward_record.md 2>/dev/null; then
  echo "[runner-learn] $DATE already recorded — skipping"; exit 0
fi
# skip if nothing was picked today
if ! python -c "import sqlite3,sys; sys.exit(0 if sqlite3.connect('data/runner.db').execute(\"SELECT COUNT(*) FROM picks WHERE date='$DATE'\").fetchone()[0] else 1)"; then
  echo "[runner-learn] no picks $DATE — nothing to record"; exit 0
fi

PROMPT="Today (ET) is $DATE, post-close. You are the runner LEARN pass. The picks are already graded.
1) Read the results: run  python -m runner.lib.journal recent  (hit=trade_pct>=+10% hold-to-close).
2) Read runner/forward_record.md for context and the running lessons.
3) Append ONE new dated section '## $DATE' to runner/forward_record.md: a compact table (pick/scan/
   entry/peak/hold-to-close/trail-ref), the scoreboard line, and any HONEST lesson the day earned —
   flag in-sample/small-n, note exit (hold-to-close vs trail) and window (10:30 vs late) findings, and
   never over-claim from one day. Tickers ARE allowed in forward_record (only decide.md stays ticker-free).
Write ONLY runner/forward_record.md. Touch NOTHING else (no resonance/overnight/exec_ai/swing/rotation)."
timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write" 2>&1 | tail -6
echo "[runner-learn] done ($DATE)"
