#!/usr/bin/env bash
# ai_trader after-close REVIEW — the learning half of the loop. Fills today's outcomes, then the
# AI compares what it predicted vs what actually happened and appends an honest lesson to its own
# memory (data/ai_trader_memory.md) that it will read next morning. Run by cron ~16:20 ET.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer
DATE=$(TZ=America/New_York date +%F)

# 1) fill realized outcomes for today's picks
bash scripts/ai_trader_run.sh v2outcome "$DATE" >> logs/ai_trader_v2.log 2>&1 || true

read -r -d '' PROMPT <<EOF || true
You are the ai_trader v2 brain, reviewing your OWN trading day after the close. Today (ET) is $DATE. Work in $(pwd).
This is how you get better: compare what you predicted this morning to what actually happened, and teach your future self.

FITNESS is TWO things, scored separately (never a backtest number): (1) forward OUTCOME — your
pick vs the FIELD that day, net of cost; and (2) JUDGMENT QUALITY — was the process sound? A correct
ABSTAIN is a WIN. A lucky green on a story you should not have traded is a process LOSS. One day is
noise; the accumulating record is the judge.

1. Read this morning's decision + your 3-pass reasoning: cat plans/decisions/$DATE.json
2. Read what your picks ACTUALLY did (realized, held to close): bash scripts/ai_trader_run.sh v2report
   and how the FIELD did that day (the baselines line + bash scripts/ai_trader_data.sh winners $DATE).
   (per name if useful: sql on intraday_bars_5m.)
3. Read your current memory: cat data/ai_trader_memory.md
4. Ask honestly: was my read RIGHT or WRONG, and WHY? Did the SKEPTIC's objection turn out to matter?
   Did I chase the loud story / step on a knife / lean on a close-stamped label? Was the theme even
   knowable pre-open? If I abstained — was that the correct sit, or did I miss a foreseeable catalyst?
5. APPEND to data/ai_trader_memory.md under "Forward record", ONE honest line for the day:
      DATE | pick(s)+archetype (or ABSTAIN) | the skeptic objection | realized fwd vs field | JUDGMENT
   where JUDGMENT is exactly one of: "foreseeable catalyst caught" | "story I talked myself into" |
   "correct abstain" | "knife I stepped on" | "right process, unlucky tail".
   THEN, only if today taught something real, add/adjust a concise dated lesson under "Lessons" — and
   PRUNE any lesson the forward record now CONTRADICTS. Keep the file a tight BRAIN, not a log. Do not
   rewrite history or inflate results — the forward record is the one thing you trust over any backtest.
Print a 2-3 line summary of what you learned today (and whether it was a process win or loss).
EOF

OUT=$(timeout 500 claude -p "$PROMPT" --permission-mode bypassPermissions --allowedTools "Bash Write" 2>&1)
echo "$OUT"
echo "[$(TZ=America/New_York date '+%F %H:%M ET')] ai_trader review done ($DATE)" >> logs/ai_trader_v2.log
