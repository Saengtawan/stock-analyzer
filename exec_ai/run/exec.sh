#!/usr/bin/env bash
# exec_ai/run/exec.sh — ON-DEMAND execution pass. Reads today's resonance pick and decides
# entry + exit (via brain/decide.md). Run it after the resonance plan is written (~09:06 ET),
# ideally by ~09:20 ET so the entry limit is ready before the 09:30 open.
# Separate: own journal data/exec_ai.db, own plans. Read-only on trade_history.db. Does not affect resonance.
# Revise pass (~10:15 ET, drift-vs-fade):  bash exec_ai/run/exec.sh <DATE> revise
# Learn pass  (after close):               bash exec_ai/run/exec.sh <DATE> learn
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer

DATE="${1:-$(TZ=America/New_York date +%F)}"
MODE="${2:-decide}"
mkdir -p exec_ai/plans

if [ "$MODE" = "learn" ]; then
  PROMPT="Today (ET) is $DATE. You are the exec_ai brain doing the AFTER-CLOSE LEARN pass.
$(cat exec_ai/brain/learn.md)"
elif [ "$MODE" = "revise" ]; then
  PLAN="resonance/plans/$DATE.plan.json"
  if [ ! -f "$PLAN" ]; then echo "[exec_ai] no resonance plan for $DATE — nothing to revise"; exit 0; fi
  PROMPT="Today (ET) is $DATE and it is ~10:15 ET. You are the exec_ai brain doing the SECOND (REVISE) pass.
$(sed "s/<DATE>/$DATE/g" exec_ai/brain/revise.md)"
else
  PLAN="resonance/plans/$DATE.plan.json"
  if [ ! -f "$PLAN" ]; then echo "[exec_ai] no resonance plan for $DATE — nothing to execute"; exit 0; fi
  PROMPT="Today (ET) is $DATE. You are the exec_ai brain. resonance's pick is in resonance/plans/$DATE.plan.json.
Decide entry + exit exactly as written below.
$(sed "s/<DATE>/$DATE/g" exec_ai/brain/decide.md)"
fi

timeout 600 claude -p "$PROMPT" --permission-mode bypassPermissions \
  --allowedTools "Bash Read Write WebSearch" 2>&1 | tee "exec_ai/plans/$DATE.$MODE.txt"
echo "[exec_ai] $MODE done ($DATE) -> exec_ai/plans/$DATE.$MODE.txt"
